"""
Whether fixture and result updates can reach this installation at all, read from what is recorded.

THE QUESTION THIS ANSWERS, AND THE ONE IT DOES NOT. A reader needs to know whether the fixtures,
kick-off times, scores and results on a page can still change: whether new ones are arriving, or
whether what is on screen is the last copy we will have until somebody restores a provider's access.
That is a different question from "did the last scheduled pass succeed" - the recover and settle
passes succeed every half hour without asking anyone for anything - and from "is a provider cooling
down", which is a two-minute flag for most refusals. Neither of those may stand in for it.

So the answer is derived from three recorded facts and nothing else:

  * what each configured match-data source last did, from its status record
    (`MatchDataService._record_status`): its last success, its last error, and what KIND of error
    that was;
  * how the scheduler's fixtures and results tasks are faring (their failure streaks), never the
    recover or settle tasks, which fetch nothing;
  * when a provider last WROTE a match row: the newest `match_metadata.last_synced_at` per provider,
    each CHECKED AGAINST THAT PROVIDER'S OWN RECORD. The registry stamps the time of the store, and
    it stores a copy served from the match cache exactly like an answer - including the 24-hour
    stale copy `_call_chain` falls back to once every provider has failed, which the fixtures,
    results and recovery passes store again. Taken as it stands, that stamp read "minutes ago"
    through the first day of an outage and kept the six-hour silence below from ever starting. So
    a stamp later than a failure that followed its provider's last answer, or more than
    `STORE_ALLOWANCE` after that answer, is a copy, and counts only as that answer
    (`newest_provider_write`). `matches.updated_at` is not it and must never become it: recovery
    bookkeeping bumps that column on every pass, so on 2026-10-07 it read "4 minutes ago" over a
    table no provider had written to since 2 October.

Nothing here sends a provider request or spends any allowance. The pure functions below take plain
dicts; `match_data_state` gathers those from Redis and one cached SQL aggregate.

THE STATES.

  ok        a configured source is answering and nothing on the fixture side is failing.
  degraded  something is wrong but data can still arrive: the primary failed while a fallback
            answers, or a single pass failed. Not worth a site-wide banner.
  blocked   no configured source is answering, AND either every one of them refused (access or
            plan) or ran out of allowance, or the fixtures/results passes have failed at least
            three times running with nothing a provider's answer wrote for six hours (a copy
            stored again is not that, see above). Also blocked: those passes still failing that
            way while every source has failed since the last write, even if one of them has
            "succeeded" since - a fallback that answers a live poll with nothing and
            refuses every fixtures call on its plan has not started delivering data. New fixtures,
            kick-off changes, live scores, results and automatic settlement cannot happen until
            that changes.
  unknown   nothing recorded to judge by: no status records and no scheduler state. Never shown as
            ok, because not knowing is not the same as being fine.

KNOWN LIMIT. Each source is judged by its LATEST record. A source that refused its last call but
still delivers on others would read as refused; if every source were in that position the state
would read blocked while some data still arrived. Since 201442e a provider is asked only about
competitions it holds an id for, so such a refusal now means its plan does not cover a competition
or season we need; the pages then overstate the gap rather than hide it.

A refusal is judged by its KIND, recorded when it happened, and not by `cooling_down`: API-Football's
plan refusal and TheSportsDB's invalid-key refusal are raised as unavailability errors and cool down
for only 120 seconds, so a state built on the cool-down would flicker between blocked and ok while
nothing at all had changed.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.predictions import Match, MatchStatus
from app.services.match_registry import UNSETTLED_GRACE
from app.services.providers.base import ProviderAuthError, ProviderQuotaError

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------- vocabulary
#: What a recorded provider error was, in the four kinds a reader's sentence turns on.
ERROR_PLAN = "plan"                # the plan we hold does not cover what was asked
ERROR_ACCESS = "access"            # the provider refused our credentials or has not enabled access
ERROR_QUOTA = "quota"              # an allowance - the provider's or our own - is spent
ERROR_UNAVAILABLE = "unavailable"  # anything else: the network, a 5xx, a malformed answer
ERROR_KINDS = (ERROR_PLAN, ERROR_ACCESS, ERROR_QUOTA, ERROR_UNAVAILABLE)

STATE_OK = "ok"
STATE_DEGRADED = "degraded"
STATE_BLOCKED = "blocked"
STATE_UNKNOWN = "unknown"

#: What one source's latest record amounts to.
ANSWER_OK = "ok"
ANSWER_REFUSED = "refused"            # access or plan: it will not answer until somebody changes that
ANSWER_ALLOWANCE = "allowance"        # an allowance is spent: it comes back when the allowance does
ANSWER_FAILING = "failing"            # it did not give a usable answer, for no reason we can name
ANSWER_NEVER_ANSWERED = "never_answered"  # no record of either an answer or an error

ANSWER_FOR_KIND = {
    ERROR_PLAN: ANSWER_REFUSED,
    ERROR_ACCESS: ANSWER_REFUSED,
    ERROR_QUOTA: ANSWER_ALLOWANCE,
    ERROR_UNAVAILABLE: ANSWER_FAILING,
}

#: The scheduler tasks that FETCH fixture data. A streak on these is evidence that nothing is
#: arriving; recover and settle are left out on purpose (see the module docstring).
STREAK_TASKS = ("fixtures", "results")
#: The fixture-side tasks whose failed last pass makes a healthy chain read as degraded.
FIXTURE_SIDE_TASKS = ("fixtures", "live", "results")
#: The tasks whose next due time is when anything will next try to reach a provider for this data.
NEXT_CHECK_TASKS = ("fixtures", "results", "recover")

#: Three failed passes in a row is not a blip. One or two can be a bad minute on the network.
BLOCKED_STREAK = 3
#: And nothing written for six hours - one fixtures interval - rules out a streak that started a
#: moment ago on a table that is otherwise current.
BLOCKED_SILENCE = timedelta(hours=6)

#: What cannot happen while blocked, and what still works. Published so a page does not have to
#: decide for itself which of its features depend on match data.
AFFECTS = ["new_fixtures", "kickoff_changes", "live_scores", "results", "automatic_settlement"]
STILL_AVAILABLE = ["stored_fixtures", "stored_forecasts", "suggestions_from_stored_fixtures", "slips"]

#: `since` is a row a provider's answer wrote...
SINCE_BASIS = "last_provider_write"
#: ...or, when the newest stamp is a cached copy stored again, the last answer of the provider that
#: produced it: the copy's data can be no newer than that.
SINCE_BASIS_ANSWER = "last_provider_answer"

#: How long after a provider's recorded answer the rows from it may still be being stamped. The
#: answer is recorded the moment it arrives (`MatchDataService._record_status`) and each row is
#: stamped as it is stored, one after another, which takes seconds for a full matchday. Ten
#: minutes is far beyond any store, and is also the most a stamp re-stored from the 30-minute fresh
#: copy, with no failure in between to give it away, can read late by.
STORE_ALLOWANCE = timedelta(minutes=10)

# ----------------------------------------------------------------------------- the classifier
#: API-Football's own error key (`{'plan': 'Free plans do not have access to this season...'}`)
#: and the phrasings a plan restriction is written in. Narrow on purpose: a quota message that
#: ends "Upgrade your plan at ..." is a QUOTA refusal, and the word "plan" alone would misfile it.
_PLAN = re.compile(
    r"""['"]plan['"]\s*:|\bfree plans?\b|\bplans? do(?:es)? not (?:have|include|cover|allow)"""
    r"""|\bnot (?:available|included|covered) (?:on|in|by) your (?:current )?plan""",
    re.IGNORECASE,
)
_ACCESS = re.compile(
    r"\bhttp 40[13]\b|authentication rejected|\binvalid\b.{0,40}\bapi key\b|do not have access"
    r"|does not have access|access (?:is )?(?:denied|not enabled)|\bunauthori[sz]ed\b|\bforbidden\b",
    re.IGNORECASE,
)
_QUOTA = re.compile(
    r"\bhttp 429\b|\bquota\b|rate limit|\ballowance\b|request limit|\bbudget\b.{0,40}\bspent\b",
    re.IGNORECASE,
)


def _is_class(error: Any, cls: type) -> bool:
    if error is None:
        return False
    return isinstance(error, cls) or (isinstance(error, type) and issubclass(error, cls))


def classify_provider_error(message: Optional[str], error: Any = None) -> str:
    """What kind of refusal a provider error was: plan, access, quota or unavailable.

    `error` is the exception (or its class) when the caller has it; a record written before the kind
    was kept has only its message, and is classified from that alone.

    THE ORDER IS THE POINT.
      1. A quota error is a quota error whatever its message says. GameForecast's 429 ends "Upgrade
         your plan at ...", and that is an allowance running out, not a plan restriction.
      2. A plan restriction before an access refusal: "Free plans do not have access to this
         season" contains "do not have access", and the access branch would misfile it.
      3. An authentication error by class, then the phrasings of one by message: HTTP 401/403,
         "authentication rejected", an invalid API key (TheSportsDB answers a bad key with HTTP 400
         and "Invalid Premium API key"), "do not have access".
      4. A quota phrasing by message, for records that predate the class being kept.
      5. Everything else is `unavailable`: something failed and we cannot say it was a refusal.
    """
    if _is_class(error, ProviderQuotaError):
        return ERROR_QUOTA
    text = message or ""
    if _PLAN.search(text):
        return ERROR_PLAN
    if _is_class(error, ProviderAuthError) or _ACCESS.search(text):
        return ERROR_ACCESS
    if _QUOTA.search(text):
        return ERROR_QUOTA
    return ERROR_UNAVAILABLE


# ----------------------------------------------------------------------------- the derivation
def _parse(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _source(entry: Mapping[str, Any], active_provider: Optional[str]) -> Dict[str, Any]:
    """One chain entry, read as an answer.

    `answer` is what the LATEST record says. `kind` is the kind of the last recorded failure,
    published even when a success has come since - a success clears the message but not the time
    of the failure, and the kind travels with that time - so a page can still say why a source that
    answered a live poll with nothing has not been delivering fixtures.
    """
    success = _parse(entry.get("last_success_at"))
    error = _parse(entry.get("last_error_at"))
    kind = entry.get("last_error_kind")
    if kind not in ERROR_KINDS:
        # A record written before the kind was kept: the message is all there is, if it is there.
        kind = classify_provider_error(entry.get("last_error")) if entry.get("last_error") else None
    if error is not None and (success is None or error > success):
        answer = ANSWER_FOR_KIND[kind or ERROR_UNAVAILABLE]
    elif success is not None:
        answer = ANSWER_OK
    else:
        answer = ANSWER_NEVER_ANSWERED
    name = entry.get("name")
    return {
        "name": name,
        "role": "primary" if active_provider and name == active_provider else "fallback",
        "configured": entry.get("configured", True) is not False,
        "answer": answer,
        "kind": kind if error is not None else None,
        "last_success_at": _iso(success),
        "last_error_at": _iso(error),
    }


def _tasks(scheduler: Optional[Mapping[str, Any]]) -> Dict[str, Mapping[str, Any]]:
    """The scheduler's per-task state, or nothing when it cannot be read."""
    if not scheduler or not scheduler.get("state_store_available", True):
        return {}
    tasks = scheduler.get("tasks") or {}
    return {name: task for name, task in tasks.items()
            if isinstance(task, Mapping) and task.get("enabled", True) is not False}


def forecasts_waiting(forecasts: Optional[Mapping[str, Any]]) -> Optional[int]:
    """Forecasts already paid for that were still waiting for their fixture at the last forecast pass.

    Read from the last forecast run's `retried` block - per competition, how many stored forecasts
    were retried against the fixtures we hold and how many of those attached. What did not attach is
    waiting for a fixture row that only a match-data provider can write. None when no forecast run
    is recorded at all: unknown, not zero.

    A count AT THAT PASS, not now: the pending entries expire after 48 hours, so the number can fall
    for reasons other than their fixtures arriving.
    """
    last_sync = (forecasts or {}).get("last_sync")
    if not isinstance(last_sync, Mapping):
        return None
    total = 0
    for counts in (last_sync.get("retried") or {}).values():
        if not isinstance(counts, Mapping):
            continue
        try:
            total += max(int(counts.get("pending") or 0) - int(counts.get("attached") or 0), 0)
        except (TypeError, ValueError):
            continue
    return total


def newest_provider_write(writes: Optional[Mapping[Optional[str], Any]],
                          chain: Iterable[Mapping[str, Any]]) -> Tuple[Optional[datetime], Optional[str]]:
    """(when a provider's answer last wrote a match row, the basis of that time), from the stamps.

    `writes` is the newest `last_synced_at` per provider (`last_provider_writes`). Each one is
    checked against its own provider's status record before it counts, because the registry stamps
    the STORE and stores a copy from the match cache exactly like an answer (module docstring).

    A provider's data reaches a row only through one of its answers, and every answer is recorded
    as its `last_success_at` before the rows from it are stored. So a stamp that answer cannot
    account for is a copy stored again:

      * one later than a failure that came after the provider's last answer - the stale copy
        `_call_chain` serves once every provider has failed, which is the outage case;
      * one more than `STORE_ALLOWANCE` after the last answer - the 30-minute fresh copy, served to
        a later pass with no failure in between.

    Such a stamp counts as the provider's last answer, basis `SINCE_BASIS_ANSWER`: the copy's data
    can be no newer than that. When the provider has failed and has no answer on record at all,
    nothing says when its data arrived and its stamp counts for nothing. A provider with no record
    to check against - not in the chain any more, or no status record because Redis was not there
    to keep one - keeps its stamp: a copy from a provider out of the chain is never served, and
    without Redis there is no cached copy to store again.

    What this cannot recover is the write the copy's stamp replaced, a few seconds after that same
    answer; and when the provider's last answer was one that wrote nothing - a live poll with
    nothing in play - the bound is that answer and not the older write. Both are the registry
    stamping the store; recording the time the provider produced the data is what would end them.
    """
    records = {entry.get("name"): entry for entry in chain or [] if isinstance(entry, Mapping)}
    best: Optional[datetime] = None
    basis: Optional[str] = None
    for name, value in (writes or {}).items():
        stamp = _parse(value)
        if stamp is None:
            continue
        when, why = stamp, SINCE_BASIS
        record = records.get(name)
        if record is not None:
            answered = _parse(record.get("last_success_at"))
            failed = _parse(record.get("last_error_at"))
            after_refusal = failed is not None and (answered is None or failed > answered) and stamp > failed
            long_after = answered is not None and stamp > answered + STORE_ALLOWANCE
            if after_refusal or long_after:
                when, why = answered, SINCE_BASIS_ANSWER
        if when is not None and (best is None or when > best):
            best, basis = when, why
    return best, basis


def derive_match_data_state(*, chain: Iterable[Mapping[str, Any]], active_provider: Optional[str],
                            scheduler: Optional[Mapping[str, Any]], last_write_at: Optional[datetime] = None,
                            provider_writes: Optional[Mapping[Optional[str], Any]] = None,
                            forecasts: Optional[Mapping[str, Any]] = None,
                            upcoming_stored: Optional[int] = None, overdue_results: Optional[int] = None,
                            now: Optional[datetime] = None) -> Dict[str, Any]:
    """The match-data block: one state for the whole chain, and the facts a page words it from.

    Pure: everything it reads is passed in, so the rules can be exercised without Redis, a database
    or a clock. See the module docstring for what each state means.

    `since` is when a provider's answer last wrote a match row, and nothing else: the newest of
    `last_write_at` - a time the caller already knows to be such a write - and `provider_writes`,
    the newest stamp per provider, each checked against that provider's record
    (`newest_provider_write`). A provider's `last_success_at` can only ever pull a stamp BACK to the
    answer it came from; it never stands in for a write on its own (on 2026-10-07 two fallbacks had
    "succeeded" on 5 and 6 October without a row being written after 2 October). Never a scheduler
    success, and never `matches.updated_at`.
    """
    now = now or datetime.now(timezone.utc)
    chain = [entry for entry in chain or [] if isinstance(entry, Mapping)]
    last_write_at, since_basis = _parse(last_write_at), SINCE_BASIS
    checked, checked_basis = newest_provider_write(provider_writes, chain)
    if checked is not None and (last_write_at is None or checked > last_write_at):
        last_write_at, since_basis = checked, checked_basis
    sources = [_source(entry, active_provider) for entry in chain]
    configured = [source for source in sources if source["configured"]]
    tasks = _tasks(scheduler)

    answers = [source["answer"] for source in configured]
    any_ok = ANSWER_OK in answers
    streak = max((int(tasks[name].get("consecutive_failures") or 0) for name in STREAK_TASKS if name in tasks),
                 default=0)
    side_failing = any(int(tasks[name].get("consecutive_failures") or 0) > 0
                       for name in FIXTURE_SIDE_TASKS if name in tasks)
    silent = last_write_at is None or now - last_write_at > BLOCKED_SILENCE
    stuck = streak >= BLOCKED_STREAK and silent
    evidence = any(answer != ANSWER_NEVER_ANSWERED for answer in answers) or any(
        tasks[name].get("last_run_at") for name in FIXTURE_SIDE_TASKS if name in tasks)
    # Every configured source has failed at least once since a provider last wrote a row. With the
    # fetching passes still failing, a success recorded after that is an answer that brought
    # nothing - API-Football answers a live poll on its free plan and refuses every fixtures and
    # results call - and is not data arriving.
    failed_since_write = bool(configured) and all(
        source["last_error_at"] is not None
        and (last_write_at is None or _parse(source["last_error_at"]) > last_write_at)
        for source in configured)

    if not any_ok:
        if not evidence:
            state = STATE_UNKNOWN
        elif (answers and all(answer in (ANSWER_REFUSED, ANSWER_ALLOWANCE) for answer in answers)) or stuck:
            state = STATE_BLOCKED
        else:
            state = STATE_DEGRADED
    elif stuck and failed_since_write:
        state = STATE_BLOCKED
    else:
        # A fallback standing in for a primary that does not answer still gets data through, which
        # is degraded and not blocked. A stale error on a fallback nobody has needed since is not
        # a fault: fallbacks are only asked when the primary fails.
        primary_ok = bool(configured) and configured[0]["answer"] == ANSWER_OK
        state = STATE_OK if primary_ok and not side_failing else STATE_DEGRADED

    due = [_parse(tasks[name].get("next_due_at")) for name in NEXT_CHECK_TASKS if name in tasks]
    due = [value for value in due if value is not None]

    return {
        "state": state,
        "since": _iso(last_write_at),
        "since_basis": since_basis if last_write_at else None,
        "sources": sources,
        "affects": list(AFFECTS) if state in (STATE_BLOCKED, STATE_DEGRADED) else [],
        "still_available": list(STILL_AVAILABLE),
        "upcoming_stored": upcoming_stored,
        "overdue_results": overdue_results,
        "forecasts_waiting_for_fixtures": forecasts_waiting(forecasts),
        "next_check_at": _iso(min(due)) if due else None,
        "checked_at": now.isoformat(),
    }


# ----------------------------------------------------------------------------- gathering it
#: How long the stored-match aggregate is reused. The status endpoint is read on every page load;
#: the numbers it carries move when a provider writes, which is minutes apart at the very fastest.
STORED_COUNTS_TTL_SECONDS = 60

_stored_counts: Dict[str, Any] = {}


def forget_stored_counts() -> None:
    """Drop the cached aggregate, so the next read measures the database again (tests use this)."""
    _stored_counts.clear()


def stored_match_counts(db: Session, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The newest stamp per provider, the upcoming fixtures held and the results overdue, cached ~60 s.

    Two aggregates over `matches`, read at most once a minute per process. The stamps are cached
    as they are, per provider, and checked against the provider records on every read
    (`newest_provider_write`): those records move between two reads of the table, and the check
    costs nothing. A database that cannot answer leaves every figure None - unknown - rather than
    failing the status page that carries them, and the failed transaction is rolled back so the
    request's session stays usable.
    """
    cached = _stored_counts.get("value")
    if cached is not None and time.monotonic() - _stored_counts.get("at", 0.0) < STORED_COUNTS_TTL_SECONDS:
        return cached
    from app.services.match_data_service import last_provider_writes

    now = now or datetime.now(timezone.utc)
    # Kickoffs are stored as naive UTC, and compared as such everywhere else.
    naive_now = now.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        upcoming, overdue = db.query(
            func.count(Match.id).filter(Match.status == MatchStatus.SCHEDULED, Match.match_date >= naive_now),
            # The backend's own deadline for a result (`result_expected_by`): kickoff plus the grace.
            func.count(Match.id).filter(Match.status.in_([MatchStatus.SCHEDULED, MatchStatus.LIVE]),
                                        Match.match_date < naive_now - UNSETTLED_GRACE),
        ).one()
        value = {"provider_writes": last_provider_writes(db), "upcoming_stored": int(upcoming),
                 "overdue_results": int(overdue)}
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Stored match counts could not be read: %s", exc)
        db.rollback()
        return {"provider_writes": None, "upcoming_stored": None, "overdue_results": None}
    _stored_counts.update({"value": value, "at": time.monotonic()})
    return value


def match_data_state(db: Session, *, chain: Iterable[Mapping[str, Any]], active_provider: Optional[str],
                     scheduler: Optional[Mapping[str, Any]], forecasts: Optional[Mapping[str, Any]],
                     now: Optional[datetime] = None) -> Dict[str, Any]:
    """The match-data block from the status payload's own parts plus the stored-match aggregate.

    Takes the chain, scheduler and forecast blocks rather than reading them again, so the status
    endpoint that already holds them pays only for the aggregate. The same chain the block reports
    is the one each provider's stamp is checked against. Sends no provider request.
    """
    now = now or datetime.now(timezone.utc)
    counts = stored_match_counts(db, now)
    return derive_match_data_state(
        chain=chain, active_provider=active_provider, scheduler=scheduler,
        provider_writes=counts["provider_writes"], forecasts=forecasts,
        upcoming_stored=counts["upcoming_stored"], overdue_results=counts["overdue_results"], now=now)
