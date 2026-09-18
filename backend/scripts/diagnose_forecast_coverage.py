"""
Why does an upcoming fixture have no prematch forecast?

Read-only diagnosis of forecast coverage. Makes NO provider request and writes NOTHING: every
answer comes from what is already stored (Postgres, the forecast caches in Redis, the budget
ledger), so running it costs nothing against a trial allowance.

For each covered competition it reports the fixtures in the horizon, how many carry a PREMATCH
forecast, and puts every fixture that does not into exactly one cause:

  not_fetched            the competition's turn never ran while this fixture existed
                         (daily allowance spent, provider paused, not due again yet, ...)
  provider_no_forecast   the competition WAS fetched and the provider's response carried no
                         usable forecast for this fixture
  identity_unresolved    the competition or the teams could not be identified with confidence,
                         so a forecast was refused rather than guessed
  not_attached           a forecast was retrieved and is held, but is not on the fixture
  only_after_kickoff     the only forecast retrieved for this fixture came after kick-off; it is
                         NOT prematch evidence and is never counted as coverage
  unexplained            none of the above can be evidenced from what is stored

The last bucket is the point of the tool. A cause is only reported when a stored record proves it;
a fixture whose cause cannot be evidenced is named as unexplained, together with the record that
is missing, rather than folded into the most plausible bucket. In particular
`provider_no_forecast` needs a retained fetch report for that competition: either a per-competition
report (`forecast:status:{provider}:{key}`, written only by a pass that really called the provider
for it) or the last run's own per-competition statistics showing that nothing it fetched was left
unattached. With neither, the fixture is unexplained.

A per-competition report settles which of the two silences it was, and each answer has its own
proof obligation:

  "it returned this fixture with nothing usable in it"  the report names the discarded event and
                                                        why it was discarded
  "it did not return this fixture at all"               the report's listing was complete, its
                                                        discarded list was not truncated, and the
                                                        window it covered contains this kick-off

A report that satisfies neither - including one written before the fixture row existed, or one
whose timestamps cannot be read - evidences nothing, and the fixture stays unexplained. Nothing
here is ever backfilled: a fixture from before the report existed keeps its honest "unexplained"
until a real pass writes a real record.

    cd backend
    ./venv/bin/python scripts/diagnose_forecast_coverage.py
    ./venv/bin/python scripts/diagnose_forecast_coverage.py --json
    ./venv/bin/python scripts/diagnose_forecast_coverage.py --days 3 --provider gameforecast
"""

import argparse
import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.predictions import League, Match, MatchStatus, Team
from app.models.provider_data import ProviderEntityRef, ProviderForecastRecord, ProviderForecastSnapshot
from app.services import match_matching
from app.services.forecast_service import (
    COMPETITION_STATUS_KEY, LAST_SYNC_KEY, PENDING_KEY, STATUS_KEY, _forecast_from_dict,
)
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers import competitions as comps
from app.services.providers.budget import RequestBudget
from app.services.providers.gameforecast import LEAGUE_STORE_KEY as GAMEFORECAST_LEAGUE_STORE_KEY

#: `COMPETITION_STATUS_KEY` is the per-competition fetch report, written only by a turn that
#: actually called the provider for that competition, so a no-op run cannot destroy the last real
#: one. It is imported from the writer rather than re-spelled here: a reader looking under a key
#: nobody writes reports "no record" forever and looks exactly like honest ignorance.

#: Where each provider keeps the competition ids it has resolved, and how it marks one it could not.
LEAGUE_STORE_KEYS = {"gameforecast": GAMEFORECAST_LEAGUE_STORE_KEY}

#: Configured daily allowance per provider (never modified here, only read and reported).
DAILY_BUDGETS = {
    "gameforecast": "GAMEFORECAST_DAILY_REQUEST_BUDGET",
    "livescore": "LIVESCORE_DAILY_REQUEST_BUDGET",
}

#: Only a fixture that is still going to be played can be missing a forecast. A postponed or
#: cancelled row with a future kickoff is excluded and counted separately, so the denominator and
#: the numerator here always describe the same set of fixtures.
COUNTED_STATUSES = (MatchStatus.SCHEDULED, MatchStatus.LIVE)

#: find_match reasons that mean the TEAMS could not be identified, as opposed to a fixture that is
#: simply not in our calendar. Both refuse the forecast; only these are an identity failure.
_IDENTITY_REASONS = ("no candidate with matching team names", "teams match only with home/away swapped")

CAUSES = ("not_fetched", "provider_no_forecast", "identity_unresolved", "not_attached",
          "only_after_kickoff", "unexplained")


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """Stored timestamps are naive UTC; comparisons here are all timezone-aware."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return _aware(value).isoformat() if value else None


#: Exactly the shapes `datetime.isoformat()` writes, which is what every timestamp this tool reads
#: was written by: date, "T", time, an optional 3- or 6-digit fraction, an optional +HH:MM offset.
#:
#: Validating before parsing rather than just wrapping `fromisoformat` in a try/except is what
#: makes the answer the same on both interpreters this repo runs. Python 3.11 accepts a trailing
#: "Z" and 3.9 raises on it; a diagnosis whose cause depends on which interpreter printed it is
#: worse than one that says it cannot read the value. Nothing here writes a "Z", so a stamp
#: carrying one was written by something this tool knows nothing about - precisely the case where
#: it must not infer.
_READABLE_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3}|\.\d{6})?([+-]\d{2}:\d{2})?$")


def _stamp(value: Any) -> Optional[datetime]:
    """Read one stored ISO timestamp, or None when it cannot be read.

    Every timestamp here comes out of a cache entry another process wrote, so it is input, not a
    value this code controls, and one malformed key must not take the whole report down.

    Unreadable degrades to None, never to a guess: a stamp this tool cannot read is not evidence
    of when anything happened, so every caller treats None as "cannot be placed in time" and the
    fixture ends up `unexplained` rather than in a bucket chosen without the timestamp.
    """
    if not isinstance(value, str) or not _READABLE_STAMP.match(value):
        return None
    try:
        return _aware(datetime.fromisoformat(value))
    except (TypeError, ValueError):  # pragma: no cover - the pattern already rejects these
        return None


# ----------------------------------------------------------------- stored state, read not inferred
def budget_ledger(provider: str, client=None) -> Dict[str, Any]:
    """Today's budget counters for a provider, with the one reading that needs explaining flagged."""
    limit = getattr(settings, DAILY_BUDGETS.get(provider, ""), 0) or 0
    ledger = RequestBudget(provider, limit, client=client).snapshot()
    used, configured = ledger.get("used_today") or 0, ledger.get("daily_limit") or 0
    ledger.setdefault("over_limit", bool(configured and used > configured))
    if ledger["over_limit"]:
        # A counter above the limit is not overspend. The atomic reservation in
        # app/services/providers/budget.py only advances the counter when the request is allowed
        # out, so it cannot produce this; an older accounting that incremented first and checked
        # afterwards could, by moving the counter for a reservation it then refused. The absence
        # of the `:refused` counter and the `:by_reason` hash - both written by the current code
        # on every reservation - dates the counter to before that change.
        ledger["over_limit_note"] = (
            f"{used} counted against a limit of {configured}: a stale counter, not overspend. "
            "The current reservation is atomic and only counts a request it lets out; the absence "
            "of the refused/by_reason counters below dates this key to the earlier accounting, "
            "which counted a refused reservation too. Requests actually sent: at most the limit.")
    return ledger


def league_store(cache: MatchCache, provider: str) -> Dict[str, Any]:
    key = LEAGUE_STORE_KEYS.get(provider)
    return (cache.get(key) or {}) if key else {}


def unresolved_marker(cache: MatchCache, provider: str, key: str) -> bool:
    """Did the provider record that it could not resolve this competition's id?"""
    store = LEAGUE_STORE_KEYS.get(provider)
    return bool(store and cache.get(f"{store}:unresolved:{key}"))


def last_run_report(cache: MatchCache, provider: str) -> Dict[str, Any]:
    return cache.get(STATUS_KEY.format(provider=provider)) or {}


def competition_report(cache: MatchCache, provider: str, key: str) -> Optional[Dict[str, Any]]:
    return cache.get(COMPETITION_STATUS_KEY.format(provider=provider, key=key))


def competition_state(cache: MatchCache, provider: str, key: Optional[str],
                      run: Dict[str, Any], covered: bool = True) -> Dict[str, Any]:
    """Everything stored about one competition's last turn, with no inference on top.

    `key` may be None: a fixture can sit in a league that predates the canonical registry, or in
    one the product does not cover. Such a competition simply has no stored turn, and every field
    below is still present so the classifier never has to guess whether a key exists.

    `covered` says whether the forecast sync actually walks this competition, i.e. whether its key
    is in the covered set this run reads. HAVING a canonical key is not the same thing: a league
    row can carry a `canonical_key` the covered list leaves out (or one the registry does not know
    at all), and no allowance was ever going to be spent on it. Deriving this from "the key is not
    None" blamed the spent daily allowance for a competition whose turn never comes.
    """
    if key is None:
        return {"key": None, "last_sync": None, "provider_league_id": None, "league_id_source": None,
                "unresolved_marker": False, "in_last_order": False, "skipped_as_not_due": False,
                "deferred_by_last_run": False, "last_run_stats": None, "retained_report": None,
                "covered": False, "provider": provider}
    canonical = comps.COMPETITIONS.get(key)
    stored = league_store(cache, provider).get(key) or {}
    configured_id = getattr(canonical, f"{provider}_id", None) if canonical else None
    raw_last_sync = cache.get(LAST_SYNC_KEY.format(provider=provider, key=key))
    stats = (run.get("competitions") or {}).get(key)
    return {
        "key": key,
        "last_sync": raw_last_sync,
        "provider_league_id": str(configured_id) if configured_id else (stored.get("external_id") or None),
        "league_id_source": ("configured" if configured_id else "discovered" if stored.get("external_id") else None),
        "unresolved_marker": unresolved_marker(cache, provider, key),
        "in_last_order": key in (run.get("order") or []),
        "skipped_as_not_due": key in (run.get("skipped") or []),
        "deferred_by_last_run": key in (run.get("deferred") or []),
        "last_run_stats": stats if isinstance(stats, dict) else None,
        "retained_report": competition_report(cache, provider, key),
        "covered": bool(covered),
        "provider": provider,
    }


def pending_forecasts(db, cache: MatchCache, registry: MatchRegistry, provider: str,
                      key: str) -> List[Dict[str, Any]]:
    """Forecasts already paid for that are held unattached, each with the reason it is refused.

    The cache stores the forecast only, not the decision that refused it, so the decision is
    replayed here against the fixtures that exist NOW. Replaying is read-only and gives the reason
    that applies today, which is the one that matters for "why is this fixture still uncovered".
    """
    entries = cache.get(PENDING_KEY.format(provider=provider, key=key)) or []
    league = registry.league_for_key(key)
    out: List[Dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        try:
            forecast = _forecast_from_dict(item)
        except Exception as exc:  # a broken cache entry is itself a finding, not a crash
            out.append({"event": item.get("external_event_id"), "unreadable": str(exc)})
            continue
        candidates = (registry.candidates_for(league.id if league else None, forecast.kickoff_utc,
                                              competition_key=key) if forecast.kickoff_utc else [])
        decision = match_matching.find_match(forecast.home_name, forecast.away_name,
                                             forecast.kickoff_utc, key, candidates)
        out.append({
            "event": forecast.external_event_id,
            "home": forecast.home_name, "away": forecast.away_name,
            "kickoff_utc": _iso(forecast.kickoff_utc),
            "reason": decision.reason,
            "confidence": decision.confidence,
            "identity_failure": decision.reason in _IDENTITY_REASONS,
            "match_ids": list(decision.candidate_ids or []),
            "would_attach": decision.attached,
        })
    return out


# ----------------------------------------------------------------------------------- classifier
def classify(fixture: Dict[str, Any], comp: Dict[str, Any], pending: List[Dict[str, Any]],
             run: Dict[str, Any], ledger: Dict[str, Any]) -> Dict[str, Any]:
    """The cause of one uncovered fixture, plus the stored record that puts it in that bucket.

    Deliberately ordered from the most direct evidence to the least, and it stops at the first
    cause it can actually evidence. Nothing here falls through to a default bucket: a fixture the
    stored records cannot explain comes back as `unexplained` naming what is missing.
    """
    last_sync = _stamp(comp.get("last_sync"))
    #: The marker says the competition WAS fetched, but its timestamp cannot be read. Everything
    #: from step 5 on turns on when that fetch happened relative to this fixture row, so none of
    #: it may be claimed. Steps 1-4 do not use the stamp at all and still stand.
    unreadable_sync = bool(comp.get("last_sync")) and last_sync is None
    created = _aware(fixture["created_at"])

    # 1. A forecast that exists but arrived too late is never prematch evidence, whatever else is true.
    if fixture["has_post_kickoff_forecast"]:
        return {"cause": "only_after_kickoff",
                "evidence": f"the only stored forecast for this fixture was retrieved at "
                            f"{fixture['first_forecast_at']}, after the {fixture['kickoff']} kick-off; "
                            "a forecast retrieved after kick-off is not prematch evidence and is not "
                            "counted as coverage"}

    # 2. Competition identity: a competition whose provider id could not be resolved can never be
    #    fetched, so this outranks any statement about its turn.
    if comp["unresolved_marker"]:
        return {"cause": "identity_unresolved",
                "evidence": f"the provider recorded competition '{comp['key']}' as unresolvable "
                            "(no league id could be matched by name); the marker is still live"}

    # 3. A forecast we already hold that names this fixture, or whose teams we cannot identify.
    for entry in pending:
        if entry.get("unreadable"):
            continue
        if fixture["match_id"] in (entry.get("match_ids") or []):
            if entry["identity_failure"]:
                return {"cause": "identity_unresolved",
                        "evidence": f"held forecast {entry['event']} ({entry['home']} v {entry['away']}) "
                                    f"is refused: {entry['reason']}"}
            return {"cause": "not_attached",
                    "evidence": f"held forecast {entry['event']} ({entry['home']} v {entry['away']}) "
                                f"names this fixture but is not attached: {entry['reason']}"}

    # 4. Stored but not surfaced: the forecast reached the database and stopped short of the history.
    if fixture["has_record"]:
        return {"cause": "not_attached",
                "evidence": "a provider_forecasts row exists for this fixture but no snapshot was "
                            "written, so nothing reaches the reader"}
    if fixture["has_ref"]:
        return {"cause": "not_attached",
                "evidence": f"the provider links event {fixture['ref_external_id']} to this fixture "
                            "but no forecast row was stored for it"}

    # 5. The competition's turn never ran while this fixture existed.
    if unreadable_sync:
        # "Never fetched" is the wrong answer here and it is the one the code below would give:
        # a cause invented out of a record that could not be read is exactly what this tool must
        # never print. Nothing is held and nothing is orphaned either, or step 3 or 4 would have
        # answered already, so there is nothing left to evidence.
        return {"cause": "unexplained",
                "evidence": f"the last-fetch marker for {comp['key']} holds {comp['last_sync']!r}, "
                            "which is not a timestamp this tool can read, so its turn cannot be "
                            "placed against this fixture row in time and neither 'never fetched' "
                            "nor 'the provider returned nothing' can be evidenced. Unreadable "
                            f"record: {LAST_SYNC_KEY.format(provider=comp.get('provider', '?'), key=comp['key'])}"}
    if last_sync is None or last_sync < created:
        never = last_sync is None
        why = "the competition has never been fetched" if never else (
            f"the competition was last fetched at {comp['last_sync']}, before this fixture row "
            f"existed ({_iso(created)})")
        if not comp.get("covered", True):
            # No allowance was ever going to be spent here, so blaming the budget would be wrong.
            return {"cause": "not_fetched", "sub_cause": "competition_not_covered",
                    "evidence": f"{why}: this fixture's league is not one of the covered "
                                "competitions the forecast sync walks, so no forecast is requested "
                                "for it at all"}
        if comp["deferred_by_last_run"]:
            return {"cause": "not_fetched", "sub_cause": "daily_allowance_spent",
                    "evidence": f"{why}; the last run deferred it to the next reset: "
                                f"{run.get('error') or 'no reason recorded'}"}
        if ledger.get("daily_limit") and not ledger.get("remaining_today"):
            return {"cause": "not_fetched", "sub_cause": "daily_allowance_spent",
                    "evidence": f"{why}; today's allowance is spent "
                                f"({ledger.get('used_today')}/{ledger.get('daily_limit')} counted, "
                                f"0 remaining), so its turn cannot run again today"
                                + (f"; last run: {run['error']}" if run.get("error") else "")}
        if run.get("paused"):
            return {"cause": "not_fetched", "sub_cause": "provider_paused",
                    "evidence": f"{why}; the provider is paused: {run.get('error')}"}
        if comp["skipped_as_not_due"]:
            return {"cause": "not_fetched", "sub_cause": "not_due_yet",
                    "evidence": f"{why}; the last run skipped it as not yet due"}
        if not comp["in_last_order"] and run:
            return {"cause": "not_fetched", "sub_cause": "not_in_sync_order",
                    "evidence": f"{why}; it was not in the last run's order"}
        return {"cause": "not_fetched", "sub_cause": "unattributed",
                "evidence": f"{why}; no stored run report says why its turn did not run"}

    # 6. The competition WAS fetched after this fixture existed. Only a retained fetch report can
    #    say the provider returned nothing usable for it.
    retained = comp.get("retained_report") or {}
    if retained and not _report_covers_fixture(retained, created):
        # A report written before this fixture row existed cannot say the provider did not publish
        # it: the fixture was not in our calendar when that response was read. An unreadable or
        # missing retrieval time lands here too - a report that cannot be placed in time proves
        # nothing about a fixture.
        retained = {}
    if retained and retained.get("key", comp["key"]) != comp["key"]:
        # The writer refuses to store a report that names a different competition, but the record
        # is input here, not something this tool wrote. A listing about another league says
        # nothing about this fixture, and attributing it would be the worst outcome of all: a
        # confident cause drawn from a response that was never about this competition.
        retained = {}
    discarded = retained.get("discarded_events") or []
    for event in discarded:
        # The strongest evidence there is: the provider returned THIS fixture and the response
        # carried nothing usable in it. It names the event, so it needs no window argument.
        if _names_this_fixture(event, fixture):
            return {"cause": "provider_no_forecast",
                    "evidence": f"the fetch report for {comp['key']} at {retained.get('fetched_at')} "
                                f"records event {event.get('external_event_id')} as returned by the "
                                f"provider and discarded: {event.get('reason')}"}
    if retained.get("events_returned") is not None and _listing_is_exhaustive_for(retained, fixture):
        return {"cause": "provider_no_forecast",
                "evidence": f"the fetch report for {comp['key']} at {retained.get('fetched_at')} lists "
                            f"{retained['events_returned']} event(s) returned for "
                            f"{retained.get('window_from')}..{retained.get('window_to')} - a complete "
                            f"listing - and this fixture's {fixture['kickoff']} kick-off falls inside "
                            "that window while none of the events returned is this fixture: the "
                            "provider did not return this fixture at all"}
    stats = comp.get("last_run_stats") or {}
    if _run_left_nothing_unattached(stats, last_sync, created, run):
        return {"cause": "provider_no_forecast",
                "evidence": f"the run at {comp['last_sync']} fetched {stats.get('fetched')} forecast(s) "
                            f"for {comp['key']} and attached all of them (unmatched "
                            f"{stats.get('unmatched', 0)}, ambiguous {stats.get('ambiguous', 0)}), so "
                            "the provider's response carried no usable forecast for this fixture. "
                            "Whether it omitted the event, returned it without predictions, or "
                            "returned predictions with no market cannot be told apart from what is "
                            "stored"}

    stored = "no fetch report for that run survives" if not comp.get("retained_report") else (
        "the retained fetch report cannot be placed against this fixture (it predates the fixture "
        "row, its listing was incomplete or truncated, or its window does not contain this kick-off)")
    return {"cause": "unexplained",
            "evidence": f"{comp['key']} was fetched at {comp['last_sync']}, after this fixture row "
                        f"existed ({_iso(created)}); nothing is held for it and nothing is orphaned, "
                        "which is consistent with the provider returning no usable forecast - but "
                        f"{stored}, so that cannot be evidenced. Record needed: "
                        f"{COMPETITION_STATUS_KEY.format(provider=comp.get('provider', '?'), key=comp['key'])} "
                        "from a pass that actually fetched this competition (the last run's global "
                        "per-competition statistics do not survive a later no-op run)"}


def _report_covers_fixture(retained: Dict[str, Any], created: Optional[datetime]) -> bool:
    """Was this fetch report written while the fixture row already existed?

    A report with no timestamp, or one whose timestamp cannot be read, cannot be placed against
    the fixture at all, so it is not used.
    """
    fetched_at = _stamp(retained.get("fetched_at"))
    if fetched_at is None or created is None:
        return False
    return fetched_at >= created


def _listing_is_exhaustive_for(retained: Dict[str, Any], fixture: Dict[str, Any]) -> bool:
    """Can "none of the events returned is this fixture" be concluded from this report?

    Only from a listing that was actually exhaustive for this fixture, which takes three things
    the report has to state itself. Each absent one is a way the conclusion could be false:

    - `complete`: the provider said there was no further page. A listing cut off at the page cap
      may simply not have reached this fixture.
    - a window containing this kick-off: a response for 18..25 September says nothing whatsoever
      about a fixture on the 28th, and the diagnosis horizon is free to be longer than the fetch
      window, so the two must be compared rather than assumed equal.
    - the discarded list not truncated: the events that produced no forecast are what is checked
      by name just above, and a capped list may not name this fixture even though it was returned.

    Missing or unreadable means no, which sends the fixture to `unexplained`.

    The truncation flag is taken from the record, so the record's own arithmetic has to agree with
    it: a report that counted more discards than it named has returned events nobody can check
    this fixture against, whatever the flag says. Trusting the flag over the count would let a
    record that contradicts itself produce the one claim this tool must never make on thin
    evidence - and the flag is input, written by another process, not a value this code controls.
    """
    if retained.get("complete") is not True or retained.get("discarded_truncated"):
        return False
    if (retained.get("discarded") or 0) > len(retained.get("discarded_events") or []):
        return False
    kickoff = _stamp(fixture.get("kickoff"))
    if kickoff is None:
        return False
    try:
        window_from = date.fromisoformat(str(retained.get("window_from")))
        window_to = date.fromisoformat(str(retained.get("window_to")))
    except (TypeError, ValueError):
        return False
    return window_from <= kickoff.date() <= window_to


def _names_this_fixture(event: Dict[str, Any], fixture: Dict[str, Any]) -> bool:
    """Does a discarded provider event describe this fixture? Names in both orders are required."""
    return (match_matching.team_names_match(event.get("home"), fixture["home"])
            and match_matching.team_names_match(event.get("away"), fixture["away"]))


def _run_left_nothing_unattached(stats: Dict[str, Any], last_sync: Optional[datetime],
                                 created: Optional[datetime], run: Dict[str, Any]) -> bool:
    """Do the last run's statistics account for every forecast it fetched for this competition?

    Only then does "this fixture is not among them" follow from them. A run that errored, that
    reports nothing, or that ran before the fixture row existed says nothing about this fixture.
    """
    if not stats or stats.get("error") or stats.get("fetched") is None:
        return False
    if last_sync is None or created is None or last_sync < created:
        return False
    if run.get("synced_at"):
        # The statistics live in a single global report that any later run overwrites. Trust them
        # only while they still describe the run that fetched this competition - and a timestamp
        # this tool cannot read cannot establish that, so it refuses rather than assuming.
        report_at = _stamp(run["synced_at"])
        if report_at is None or abs((report_at - last_sync).total_seconds()) > 3600:
            return False
    return not (stats.get("unmatched") or stats.get("ambiguous") or stats.get("without_markets"))


# ------------------------------------------------------------------------------------ the report
def diagnose(db, cache: Optional[MatchCache] = None, provider: Optional[str] = None,
             now: Optional[datetime] = None, days: Optional[int] = None,
             keys: Optional[List[str]] = None, budget_client=None) -> Dict[str, Any]:
    """Classify every uncovered fixture in the horizon. Reads only; makes no provider request."""
    cache = cache if cache is not None else MatchCache()
    provider = provider or settings.PREDICTION_PROVIDER
    now = _aware(now) or datetime.now(timezone.utc)
    days = settings.GAMEFORECAST_SYNC_DAYS_AHEAD if days is None else days
    keys = keys or comps.covered_keys(settings.COVERED_COMPETITIONS)
    registry = MatchRegistry(db)
    horizon_end = now + timedelta(days=days)

    run = last_run_report(cache, provider)
    ledger = budget_ledger(provider, client=budget_client)
    states = {key: competition_state(cache, provider, key, run) for key in keys}
    held = {key: pending_forecasts(db, cache, registry, provider, key) for key in keys}

    rows = _fixtures_in_horizon(db, now, horizon_end)

    by_competition: Dict[str, Dict[str, Any]] = {}
    unexplained: List[Dict[str, Any]] = []
    for key in keys:
        by_competition[key] = {"competition": key, "fixtures": 0, "with_prematch_forecast": 0,
                               "without": 0, "causes": {}, "missing": [], "state": states[key],
                               "held_unattached": held[key]}
    other: Dict[str, Dict[str, Any]] = {}
    excluded_by_status = 0

    for match, league, home, away in rows:
        if match.status not in COUNTED_STATUSES:
            excluded_by_status += 1
            continue
        key = registry.canonical_key_for_league(league.id)
        bucket = by_competition.get(key)
        if bucket is None:
            # A league the run does not cover, or one with no canonical key at all. It still gets
            # a full state so the classifier reads the same fields for it as for any other.
            bucket = other.setdefault(key or f"uncovered:{league.name}", {
                "competition": key, "league": league.name, "fixtures": 0, "with_prematch_forecast": 0,
                "without": 0, "causes": {}, "missing": [],
                # Not in `keys`, so this competition's turn never comes however much allowance is
                # left: it is not covered, whether or not it has a canonical key.
                "state": competition_state(cache, provider, key, run, covered=False),
                "held_unattached": pending_forecasts(db, cache, registry, provider, key) if key else []})
        bucket["league"] = league.name
        bucket["fixtures"] += 1
        fixture = _fixture_facts(db, match, home, away, provider)
        if fixture["has_prematch_forecast"]:
            bucket["with_prematch_forecast"] += 1
            continue
        bucket["without"] += 1
        verdict = classify(fixture, bucket["state"], bucket["held_unattached"], run, ledger)
        entry = {"match_id": fixture["match_id"], "kickoff": fixture["kickoff"],
                 "fixture": f"{fixture['home']} v {fixture['away']}", **verdict}
        bucket["missing"].append(entry)
        bucket["causes"][verdict["cause"]] = bucket["causes"].get(verdict["cause"], 0) + 1
        if verdict["cause"] == "unexplained":
            unexplained.append(entry)

    competitions = list(by_competition.values()) + list(other.values())
    totals = {"fixtures": sum(c["fixtures"] for c in competitions),
              "with_prematch_forecast": sum(c["with_prematch_forecast"] for c in competitions),
              "without": sum(c["without"] for c in competitions),
              "causes": {}}
    for comp in competitions:
        for cause, count in comp["causes"].items():
            totals["causes"][cause] = totals["causes"].get(cause, 0) + count

    return {
        "provider": provider,
        "generated_at": now.isoformat(),
        "horizon": {"from": now.isoformat(), "to": horizon_end.isoformat(), "days": days},
        "excluded_by_status": excluded_by_status,
        "budget": ledger,
        "last_run": {k: run.get(k) for k in ("synced_at", "error", "paused", "order", "skipped", "deferred")},
        "totals": totals,
        # Every covered competition is listed, including one with no fixtures at all: "0 of 0" is
        # the answer to "why has it no forecasts", and dropping it would hide that it has no
        # calendar rather than no forecasts.
        "competitions": competitions,
        "unexplained": unexplained,
    }


def _fixtures_in_horizon(db, start: datetime, end: datetime):
    """(match, league, home team, away team) for every fixture whose kickoff is in the horizon."""
    home, away = aliased(Team), aliased(Team)
    return (db.query(Match, League, home, away)
            .join(League, League.id == Match.league_id)
            .join(home, home.id == Match.home_team_id)
            .join(away, away.id == Match.away_team_id)
            .filter(Match.match_date >= start.replace(tzinfo=None),
                    Match.match_date <= end.replace(tzinfo=None))
            .order_by(Match.match_date.asc()).all())


def _fixture_facts(db, match: Match, home: Team, away: Team, provider: str) -> Dict[str, Any]:
    """What is stored for one fixture: its snapshots, its forecast row, its provider link."""
    kickoff = _aware(match.match_date)
    snapshots = (db.query(ProviderForecastSnapshot)
                 .filter(ProviderForecastSnapshot.match_id == match.id,
                         ProviderForecastSnapshot.provider == provider).all())
    prematch = [s for s in snapshots
                if s.captured_before_kickoff is True
                or (s.captured_before_kickoff is None and _aware(s.first_fetched_at) < kickoff)]
    record = (db.query(ProviderForecastRecord)
              .filter(ProviderForecastRecord.match_id == match.id,
                      ProviderForecastRecord.provider == provider).first())
    ref = (db.query(ProviderEntityRef)
           .filter(ProviderEntityRef.entity_type == "match", ProviderEntityRef.provider == provider,
                   ProviderEntityRef.entity_id == match.id).first())
    first = min((_aware(s.first_fetched_at) for s in snapshots), default=None)
    return {
        "match_id": str(match.id), "home": home.name, "away": away.name,
        "kickoff": _iso(match.match_date), "created_at": match.created_at,
        "has_prematch_forecast": bool(prematch),
        "has_post_kickoff_forecast": bool(snapshots) and not prematch,
        "first_forecast_at": _iso(first),
        "has_record": record is not None and not snapshots,
        "has_ref": ref is not None and record is None,
        "ref_external_id": ref.external_id if ref else None,
    }


# ------------------------------------------------------------------------------------- rendering
def _label(comp: Dict[str, Any]) -> str:
    """What to call a competition in the report: its league name, or its key when it has no fixtures."""
    return comp.get("league") or comp.get("competition") or "?"


def render(result: Dict[str, Any]) -> str:
    out: List[str] = []
    totals = result["totals"]
    out.append(f"Forecast coverage for {result['provider']}, "
               f"kickoff {result['horizon']['from'][:16]} .. {result['horizon']['to'][:16]} "
               f"({result['horizon']['days']} days)")
    out.append("")
    out.append(f"  {'competition':16} {'fixtures':>8} {'forecast':>9} {'missing':>8}   causes")
    for comp in sorted(result["competitions"], key=_label):
        causes = ", ".join(f"{name} {count}" for name, count in sorted(comp["causes"].items())) or "-"
        out.append(f"  {_label(comp)[:16]:16} "
                   f"{comp['fixtures']:>8} {comp['with_prematch_forecast']:>9} {comp['without']:>8}   {causes}")
    out.append(f"  {'TOTAL':16} {totals['fixtures']:>8} {totals['with_prematch_forecast']:>9} "
               f"{totals['without']:>8}   " +
               (", ".join(f"{k} {v}" for k, v in sorted(totals["causes"].items())) or "-"))
    if result["excluded_by_status"]:
        out.append(f"  ({result['excluded_by_status']} fixture(s) in the horizon excluded: not scheduled or live)")

    budget = result["budget"]
    out.append("")
    out.append(f"Budget ledger ({budget['provider']}): used {budget['used_today']}/"
               f"{budget['daily_limit']}, refused {budget['refused_today']}, "
               f"by reason {budget['by_reason'] or '{}'}")
    if budget.get("over_limit_note"):
        for line in _wrap(budget["over_limit_note"], 92):
            out.append(f"  ! {line}")

    run = result["last_run"]
    out.append(f"Last run: {run.get('synced_at') or 'never'}"
               + (f", paused: {run.get('error')}" if run.get("paused") else
                  (f", error: {run['error']}" if run.get("error") else "")))
    if run.get("order"):
        out.append(f"  order {', '.join(run['order'])}"
                   + (f"; deferred {', '.join(run['deferred'])}" if run.get("deferred") else ""))

    for comp in sorted(result["competitions"], key=_label):
        if not comp["missing"] and not comp["held_unattached"]:
            continue
        state = comp["state"]
        out.append("")
        out.append(f"{_label(comp)} - {comp['without']} fixture(s) without a prematch forecast")
        out.append(f"  competition id {state.get('provider_league_id') or 'unresolved'}"
                   f" ({state.get('league_id_source') or 'none'})"
                   f", last fetched {state.get('last_sync') or 'never'}"
                   f", fetch report retained: {'yes' if state.get('retained_report') else 'no'}")
        for entry in comp["missing"]:
            out.append(f"  [{entry['cause']}{'/' + entry['sub_cause'] if entry.get('sub_cause') else ''}] "
                       f"{entry['kickoff'][:16]}  {entry['fixture']}")
            for line in _wrap(entry["evidence"], 88):
                out.append(f"        {line}")
        for entry in comp["held_unattached"]:
            out.append(f"  [held] event {entry.get('event')} {entry.get('home')} v {entry.get('away')} "
                       f"-> {entry.get('reason') or entry.get('unreadable')}")

    if result["unexplained"]:
        out.append("")
        out.append(f"{len(result['unexplained'])} fixture(s) could not be explained from stored records. "
                   "They are NOT counted as provider silence:")
        for entry in result["unexplained"]:
            out.append(f"  {entry['kickoff'][:16]}  {entry['fixture']}")
    return "\n".join(out)


def _wrap(text_value: str, width: int) -> List[str]:
    words, lines, line = text_value.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=None,
                        help=f"horizon in days (default: GAMEFORECAST_SYNC_DAYS_AHEAD = {settings.GAMEFORECAST_SYNC_DAYS_AHEAD})")
    parser.add_argument("--provider", default=None,
                        help=f"forecast provider to diagnose (default: PREDICTION_PROVIDER = {settings.PREDICTION_PROVIDER})")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()
    # This is a report, not a debugging session: the engine's statement echo (on when the backend
    # runs with DEBUG) would bury it. Nothing else about the engine is changed, and this process
    # is its own, so no running backend is affected.
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)

    db = SessionLocal()
    bind = db.get_bind()
    if getattr(bind, "echo", False):
        bind.echo = False
    try:
        # Belt and braces: the diagnosis only ever issues SELECTs, and the database is told to
        # refuse anything else. A read-only report must not be able to change what it reports on.
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
        except Exception:  # pragma: no cover - not every backend supports it
            db.rollback()
        result = diagnose(db, provider=args.provider, days=args.days)
    finally:
        db.rollback()
        db.close()

    print(json.dumps(result, indent=2, default=str) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
