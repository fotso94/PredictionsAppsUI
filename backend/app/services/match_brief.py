"""
The evidence brief for one match: ordinary application logic, not generated prose.

Every sentence in here is assembled from values a source actually published. Nothing is inferred,
interpolated, renormalised or filled in, and no language model is involved. The point of the brief
is that the UI can render it without interpreting anything itself, and that four situations which
currently look identical on screen stay distinguishable in the payload:

  * no forecast was ever retrieved for this fixture          -> ``no_forecast_retrieved``
  * a forecast exists but this market was not part of it     -> ``market_not_in_forecast``
  * a forecast exists and is older than the freshness limit  -> ``forecast_stale``
  * a refresh is blocked right now (allowance spent)         -> ``refresh_blocked``

"We do not know" and "nobody has asked recently" are different statements and are reported as
different reasons. A market a source did not supply is reported as unavailable with its reason; it
never appears as 0%, because a 0% we invented is a forecast the source never made.

The builder is a pure function over data the caller already has (the serialised match, the
serialised forecast, the freshness verdict and the serialised expert prediction) PLUS one measured
scoring summary, so it costs no per-match database query and can be tested without a database by
passing ``scoring=``. The one thing the brief cannot read off its own inputs is how much has been
scored against a result, and that is the one thing it used to state as a constant; see
``summarise_scoring`` and ``current_scoring_summary`` below for where the figures come from and
what they cost.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.services import settlement as settlement_service

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ sources
MODEL = "model"
EXPERT = "expert"

#: How each source is named in a sentence. A forecast provider is "the model"; a person is "the expert".
_SUBJECT = {MODEL: "The model", EXPERT: "The expert"}

# ------------------------------------------------------------------ reason codes
#: Nothing has ever been retrieved for this fixture: the source's view is genuinely unknown.
NO_FORECAST_RETRIEVED = "no_forecast_retrieved"
#: A forecast was retrieved, but it did not carry this market. Different from "unknown fixture".
MARKET_NOT_IN_FORECAST = "market_not_in_forecast"
#: We hold a forecast, but it is older than FORECAST_MAX_AGE_HOURS.
FORECAST_STALE = "forecast_stale"
#: Refreshing is paused (daily allowance spent, provider cooling down). Nobody has asked recently.
REFRESH_BLOCKED = "refresh_blocked"
#: No expert has published anything for this fixture.
NO_EXPERT_PREDICTION = "no_expert_prediction"
#: The expert published a prediction, but left this market out of it.
MARKET_NOT_SUPPLIED = "market_not_supplied"
#: This source does not publish this market at all (experts do not publish scorelines).
NOT_OFFERED_BY_SOURCE = "not_offered_by_source"

#: The four reasons B1 requires to stay distinguishable from one another.
MISSING_DATA_REASONS: Tuple[str, ...] = (
    NO_FORECAST_RETRIEVED, MARKET_NOT_IN_FORECAST, FORECAST_STALE, REFRESH_BLOCKED)

# ------------------------------------------------------------------ market states
STATE_AVAILABLE = "available"
STATE_STALE = "stale"
STATE_REFERENCE_ONLY = "reference_only"   # kickoff has passed; kept for reference, not as a forecast
STATE_UNAVAILABLE = "unavailable"

_PRESENT_STATES = (STATE_AVAILABLE, STATE_STALE, STATE_REFERENCE_ONLY)

# ------------------------------------------------------------- accuracy: measured, never asserted
#: The three honest answers to "is there an accuracy figure?", named exactly as
#: ``/api/v1/data-providers/coverage`` names them.
#:
#: WHAT USED TO BE HERE. Two constants: ``ACCURACY_MEASURED = False`` and a sentence beginning "No
#: prediction has been scored against a match result yet". Both were true on the day they were
#: written. Both went on being served, verbatim, at ``data-testid="brief-accuracy"`` on every match
#: page after settlement had scored four provider forecasts from the same database that
#: /performance/sources was reporting them from. A constant cannot notice that the data moved,
#: which is the whole reason a fact about the data may not be written as one.
#:
#: WHY THREE STATES AND NOT A BOOLEAN. "Nothing has been scored" and "something has been scored,
#: but too little to publish a rate" are different facts about this installation. Collapsing them
#: is precisely how the coverage endpoint's own reason string went on claiming nothing had been
#: scored long after scoring started, and the fix there was to keep them apart. The brief is the
#: second copy of that defect, so it is repaired the same way, with the same names, the same
#: derivation and the same source of counts — see ``summarise_scoring``. Two surfaces answering one
#: question about one database must not be free to word it differently.
ACCURACY_NOTHING_SCORED = "nothing_scored"
ACCURACY_BELOW_MINIMUM_SAMPLE = "below_minimum_sample"
ACCURACY_AVAILABLE = "available"
#: Not a fourth answer to that question but the answer to a different one: the counts could not be
#: read at all. It exists because this module resolves its own figures when the caller supplies
#: none (``current_scoring_summary``), and a read that failed must never come out as "nothing has
#: been scored" — that would be the original defect with an extra step in front of it.
ACCURACY_UNKNOWN = "unknown"
#: Nor is this a fifth answer to that question: it is the answer to "whose record is this block
#: about?" when the answer is nobody. A market block is rendered for both sources on every match,
#: including the ones no expert has touched and the ones no forecast was retrieved for, and a block
#: with no source of its own has no scored record to be in any of the three states above.
#:
#: WHAT USED TO BE HERE. Nothing: ``_source_accuracy`` fell back to the installation-wide state and
#: sentence whenever it was handed no source id. No expert prediction is published anywhere on this
#: installation, so that fallback was what every expert block on every match page rendered, and
#: what it rendered was the model provider's scored record — "4 of 4 eligible prediction(s) on this
#: installation ... have been scored" — inside a block about experts. The same package had just
#: argued that a per-source block must state what is true of THAT source; this is that rule applied
#: to the case where the source is not there at all.
ACCURACY_NO_SOURCE = "no_source_on_fixture"

#: The per-source counters ``settlement.measure_sources`` publishes, summed to answer "how much of
#: this installation has been scored?".
_COUNT_KEYS: Tuple[str, ...] = ("eligible", "scored", "pending", "void", "not_scored")

#: How long one measured summary is reused. The brief is built once per match, so a thirty-fixture
#: list would otherwise run the measurement thirty times in a single request; with this it runs at
#: most once a minute per process however much anyone browses. What the window costs is that the
#: sentence can trail settlement by up to a minute — a lag in a measurement, which is a different
#: thing from a standing claim, and it is bounded and stated rather than invisible.
#:
#: WHY A CACHE SHARED ACROSS REQUESTS IS SAFE HERE, which is not true of every cache:
#:
#: * WHAT IT HOLDS is one installation-wide measurement over a fixed 90-day kickoff window —
#:   per-source counts and the states derived from them. Nothing in it is about one match, one
#:   viewer or one request, so there is no figure belonging to one reader that another could be
#:   served. ``summarise_scoring`` also drops ``source_label`` (a username or an email address)
#:   before anything is cached, so what is shared is counts and opaque ids.
#: * WHICH DATABASE IT IS ABOUT cannot vary within a process: ``SessionLocal`` is bound to one
#:   engine built from one ``DATABASE_URL``, and the caller-supplied sessions come from the same
#:   ``get_db``. A process serving two databases would need this keyed by database; it does not
#:   serve two, and a second one would have to key it.
#: * WHAT A STALE ENTRY CAN DO is bounded to the lag. The summary is only ever quoted — it is
#:   never combined with the fresher per-match values in this brief to derive a third number — so
#:   the worst case is a sentence counted up to a minute ago, and it travels with the
#:   ``measured_at`` and ``window`` it was counted over, so the reader can see how old it is.
#:   Nothing in ``app/`` calls ``reset_scoring_cache``, so a settlement run that scores more
#:   results can take up to this long to show; that is the same bounded lag, not a stale claim.
#: * WHAT WOULD NOT BE SAFE, and is not done: caching per-match figures, anything read under a
#:   viewer's own permissions, or a failed read for the full minute (see the failure TTL below).
SCORING_CACHE_TTL_SECONDS = 60.0
#: A failed read is held far more briefly: it must clear as soon as the database is reachable again.
SCORING_FAILURE_TTL_SECONDS = 10.0

_scoring_cache: Optional[Tuple[float, Dict[str, Any]]] = None


def _figures(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """The counters of these measured sources, summed, plus how many figures they actually publish.

    ``published_figures`` is not re-decided here: whether a rate may be published is read off the
    per-market ``hit_rate_available`` / ``brier_available`` flags that ``settlement`` itself sets
    from the minimum sample. Asking the module that owns the rule is what stops a second, drifting
    copy of it appearing in this file.
    """
    rows = list(rows)
    totals = {key: sum(int(row.get(key) or 0) for row in rows) for key in _COUNT_KEYS}
    totals["published_figures"] = sum(
        1 for row in rows for market in (row.get("markets") or [])
        if market.get("hit_rate_available") or market.get("brier_available"))
    return totals


def _figures_of_kind(scoring: Dict[str, Any], source_type: str) -> Dict[str, int]:
    """The counters of every measured source of one kind, summed.

    A third scope, between "this source" and "this installation", and the only measured thing that
    is still about the right kind when this fixture has no source of that kind on it. It is summed
    from the per-source entries ``summarise_scoring`` already built rather than re-read, so it
    costs nothing and cannot disagree with them.
    """
    entries = [entry for key, entry in (scoring.get("sources") or {}).items()
               # The key carries the kind too. Either identifies it; reading both means a summary
               # assembled by hand cannot silently sum to nothing and turn a record into "no
               # source of this kind has ever been scored", which would be a false sentence.
               if entry.get("source_type") == source_type or key.split(":", 1)[0] == source_type]
    return {key: sum(int(entry.get(key) or 0) for entry in entries)
            for key in _COUNT_KEYS + ("published_figures",)}


def _state_of(figures: Dict[str, int]) -> str:
    if figures["published_figures"]:
        return ACCURACY_AVAILABLE
    if figures["scored"]:
        return ACCURACY_BELOW_MINIMUM_SAMPLE
    return ACCURACY_NOTHING_SCORED


def _span(scoring: Dict[str, Any]) -> str:
    window = scoring.get("window") or {}
    start, end = window.get("start"), window.get("end")
    return f"{start} to {end}" if start and end else "the measured window"


def _counts_clause(figures: Dict[str, int], span: str) -> str:
    """Why nothing is scored yet, in counted terms rather than as a shrug."""
    if not figures["eligible"]:
        return f"no prediction with a kickoff in {span} is eligible for scoring yet"
    parts = [f"{figures['eligible']} prediction(s) with a kickoff in {span} are eligible"]
    if figures["pending"]:
        parts.append(f"{figures['pending']} are still waiting to be scored")
    if figures["void"]:
        parts.append(f"{figures['void']} were voided")
    if figures["not_scored"]:
        parts.append(f"{figures['not_scored']} cannot be scored")
    return ", ".join(parts)


def _accuracy_detail(state: str, figures: Dict[str, int], *, minimum: Any, span: str,
                     subject: str, unit: str = "market") -> str:
    """The one sentence a surface renders, assembled from the counts it is about.

    ``subject`` names whose record this is ("on this installation", "from gameforecast"), so the
    same three branches serve the whole-installation statement and the per-source ones without a
    second set of wordings to keep in step. ``unit`` is what has to clear the minimum sample: a
    single source and market across the installation, one market within one source.

    The below-minimum branch is the coverage endpoint's sentence word for word apart from the
    scope clause ``subject`` adds, which is the one thing that genuinely differs between a
    statement about the whole installation and one about a named source.
    """
    if state == ACCURACY_UNKNOWN:
        return ("The scored-result counts could not be read just now, so nothing is stated either "
                "way about how often anything here has been right.")
    if state == ACCURACY_NOTHING_SCORED:
        return (f"No prediction {subject} has been scored against a match result yet "
                f"({_counts_clause(figures, span)}), so no accuracy figure has been measured for it.")
    counted = (f"{figures['scored']} of {figures['eligible']} eligible prediction(s) {subject} with "
               f"a kickoff in {span} have been scored")
    if state == ACCURACY_BELOW_MINIMUM_SAMPLE:
        return (f"{counted}, but no {unit} has reached the minimum of {minimum} scored predictions "
                f"an accuracy figure is published from. The counts are published; the rate is not.")
    return (f"{counted}, and {figures['published_figures']} {unit} figure(s) have reached the "
            f"minimum sample of {minimum}. A published rate always carries the sample it was "
            f"counted from; a probability here is not one.")


def _no_source_detail(absent: str, figures: Dict[str, int], *, kind: str, minimum: Any,
                      span: str) -> str:
    """What a block whose source is not on this fixture at all may say.

    Two sentences, two scopes, each named where it stands. The first is the fact about this
    fixture: nobody of that kind published a view of it, which is why there is no record here to
    report. The second is the only measured thing left that is about the right kind — what every
    source of that kind has had scored — and it always ends by saying that none of it belongs to
    this match, so the two can never be read as one claim.

    What is deliberately NOT said is the installation-wide figure, which on an installation whose
    only scored predictions are a forecast provider's is a statement about that provider and has
    no business in a block about experts.
    """
    if not figures["scored"]:
        return (f"{absent} Nor has any {kind} on this installation had a prediction scored against "
                f"a match result in the {span} window, so there is no {kind} record anywhere here "
                f"to put in its place.")
    counted = (f"Across every {kind} on this installation, {figures['scored']} of "
               f"{figures['eligible']} eligible prediction(s) with a kickoff in {span} have been "
               f"scored")
    if not figures["published_figures"]:
        return (f"{absent} {counted}, short of the minimum of {minimum} scored predictions any one "
                f"{kind} and market must reach before a rate is published — and none of that "
                f"record is this match's in any case.")
    # The closing clause says only what is known: none of that record is this match's. It used to
    # say "because no {kind} published a view of it", which for a forecast provider is a claim
    # about the PROVIDER when all we hold is that nothing was RETRIEVED — the very distinction the
    # module exists to keep ("we do not know" is not "nobody has asked recently"), and the one most
    # likely to be false while refreshing is paused. ``absent`` already states the fixture fact in
    # the terms each kind can actually be held to.
    return (f"{absent} {counted}, and {figures['published_figures']} figure(s) have reached the "
            f"minimum sample of {minimum} — but none of that record is this match's in any case.")


def summarise_scoring(measured: Dict[str, Any]) -> Dict[str, Any]:
    """Turn one ``settlement.measurement`` payload into the brief's scoring answer.

    A pure function over the measurement, so the brief and
    ``/api/v1/data-providers/coverage`` can be driven from a single payload in a test and shown to
    reach the same state. The per-source entries carry counts and a state only — never the
    ``source_label`` settlement attaches, which for an expert is a username or an email address and
    has no business on a public match payload.
    """
    rows = measured.get("sources") or []
    window = measured.get("window") or {}
    minimum = measured.get("minimum_sample")
    overall = _figures(rows)
    state = _state_of(overall)
    summary: Dict[str, Any] = {
        "accuracy_state": state,
        "accuracy_measured": state == ACCURACY_AVAILABLE,
        "results_scored": overall["scored"] > 0,
        "minimum_sample": minimum,
        "window": window,
        "measured_at": measured.get("measured_at"),
        "counted_by": "app.services.settlement.measurement, the counts /performance/sources publishes",
        "published_by": "/api/v1/performance/sources",
        "sources": {},
        **overall,
    }
    for row in rows:
        figures = _figures([row])
        summary["sources"][f"{row.get('source_type')}:{row.get('source_id')}"] = {
            # The kind travels as a field rather than only inside the key, so summing one kind
            # (see _figures_of_kind) never has to parse an id back out of a string.
            "source_type": row.get("source_type"), "state": _state_of(figures), **figures}
    summary["detail"] = _accuracy_detail(state, overall, minimum=minimum, span=_span(summary),
                                         subject="on this installation",
                                         # Across the whole installation the thing that has to
                                         # clear the sample is one source's one market, which is
                                         # exactly how /data-providers/coverage words it.
                                         unit="single source and market")
    return summary


def unknown_scoring_summary(reason: str) -> Dict[str, Any]:
    """What to say when the counts could not be read. Never "nothing has been scored"."""
    summary: Dict[str, Any] = {
        "accuracy_state": ACCURACY_UNKNOWN,
        "accuracy_measured": False,
        # Not False: nobody measured it. False here would be the asserted absence all over again.
        "results_scored": None,
        "minimum_sample": None,
        "window": {},
        "measured_at": None,
        "unavailable_reason": reason,
        "sources": {},
        **{key: None for key in _COUNT_KEYS},
    }
    summary["published_figures"] = None
    summary["detail"] = _accuracy_detail(ACCURACY_UNKNOWN, {}, minimum=None, span="", subject="")
    return summary


def scoring_summary(db: Any, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The measured scoring answer for a caller that already holds a session.

    Cost: one ``settlement.measurement``, the same fixed five to seven indexed queries
    /api/v1/data-providers/coverage pays on a page load, bounded by the 90-day kickoff window that
    is published with the counts. A caller with a session should use this and pass the result to
    ``build_brief`` once per request, rather than letting each brief fall back to the cache below.
    """
    return summarise_scoring(settlement_service.measurement(db, now=now))


def reset_scoring_cache() -> None:
    """Forget the cached summary. For tests, and for anything that has just run settlement."""
    global _scoring_cache
    _scoring_cache = None


def current_scoring_summary(db: Any = None) -> Dict[str, Any]:
    """The cached measured summary, re-counted when the cache window has passed.

    ``db`` IS THE CALLER'S OWN SESSION and every caller that has one must pass it. The match
    endpoints do: ``build_match_payloads`` measures once for the whole request on the session
    FastAPI already injected, so a page load with a cold cache no longer opens a second session
    beside the open one. That second session is what this argument exists to prevent; it was not
    a leak (it was closed in a ``finally``) but it was one connection and one transaction more
    than the request needed, on the hot path of every match list and every match page.

    WHO GENUINELY HAS NO SESSION, and so keeps the fallback below: anything building a brief
    outside a request — a script under ``scripts/``, a shell, a test — and the
    ``build_brief(scoring=None)`` path itself, which exists for exactly those callers. No endpoint
    in this application is one of them any more.

    Cost either way: at most one ``settlement.measurement`` per ``SCORING_CACHE_TTL_SECONDS`` per
    process, shared by every brief built in that window. See that constant for why sharing one
    measurement across requests is safe for what it holds.
    """
    global _scoring_cache
    entry = _scoring_cache
    if entry is not None and entry[0] > monotonic():
        return entry[1]
    try:
        if db is not None:
            summary = scoring_summary(db)
        else:
            from app.db.session import SessionLocal  # local: this module must import without a database

            own = SessionLocal()
            try:
                summary = scoring_summary(own)
            finally:
                own.close()
        _scoring_cache = (monotonic() + SCORING_CACHE_TTL_SECONDS, summary)
    except Exception as exc:  # unreachable database, migration in flight, anything at all
        logger.warning("scoring summary unavailable, reporting it as unknown: %s", exc)
        _scoring_cache = (monotonic() + SCORING_FAILURE_TTL_SECONDS, unknown_scoring_summary(str(exc)))
        if db is not None:
            # The read failed on the CALLER's transaction, which on PostgreSQL is now aborted: every
            # later query in that request would fail too, and the brief must never take the page
            # down with it. Rolling back returns the session usable. There is nothing of the
            # caller's to lose — the measurement is a read, and the endpoints that pass a session
            # here are GETs whose earlier writes are already committed by the services that made
            # them — and a rollback that itself fails leaves us no worse off than not trying.
            try:
                db.rollback()
            except Exception:  # pragma: no cover - the session is unusable either way
                logger.warning("could not roll back the caller's session after a failed measurement")
    return _scoring_cache[1]


def _source_accuracy(scoring: Dict[str, Any], source_type: str, source_id: Optional[str],
                     subject: str, *, kind: str, absent: str) -> Dict[str, Any]:
    """The measured accuracy position of one source of this brief, as three payload fields.

    Four situations, and the whole point of the function is that they stay apart:

      * the counts could not be read at all      -> ``unknown``, and never "nothing was scored"
      * this fixture has no source of this kind  -> ``no_source_on_fixture``, see ``absent``
      * the source published here but was never
        measured inside settlement's window      -> ``nothing_scored``, about that source
      * the source was measured                  -> its own counts and its own state

    ``subject`` names the source in a sentence ("from gameforecast", "from this expert") and is
    used only where there IS a source to name. ``kind`` names what sort of source the block is
    for ("expert", "forecast provider") and ``absent`` is the fixture-level fact for the second
    case: they are what keeps a block with no source of its own from reaching for the
    installation-wide sentence, which is a statement about whichever sources HAVE been scored and
    on this installation is the model provider's record.
    """
    if scoring.get("accuracy_state") == ACCURACY_UNKNOWN:
        return {"accuracy_state": ACCURACY_UNKNOWN, "accuracy_measured": False,
                "accuracy_detail": scoring.get("detail")}
    span = _span(scoring)
    if source_id is None:
        # No source of this kind on this fixture: nothing here has a record, not even an empty one,
        # because there is nobody for the record to belong to.
        return {"accuracy_state": ACCURACY_NO_SOURCE, "accuracy_measured": False,
                "accuracy_detail": _no_source_detail(
                    absent, _figures_of_kind(scoring, source_type), kind=kind,
                    minimum=scoring.get("minimum_sample"), span=span)}
    figures = (scoring.get("sources") or {}).get(f"{source_type}:{source_id}")
    if figures is None:
        # Absence from the measured rows is itself a measurement: nothing of this source's fell
        # inside the window settlement looked at.
        return {"accuracy_state": ACCURACY_NOTHING_SCORED, "accuracy_measured": False,
                "accuracy_detail": (f"Nothing {subject} has been scored against a match result in "
                                    f"the {span} window, so no accuracy figure has been measured "
                                    f"for it.")}
    state = figures["state"]
    return {"accuracy_state": state, "accuracy_measured": state == ACCURACY_AVAILABLE,
            "accuracy_detail": _accuracy_detail(state, figures, minimum=scoring.get("minimum_sample"),
                                                span=span, subject=subject)}


def _outcome(key: str, label: str, phrase: str, field: str) -> Dict[str, str]:
    return {"key": key, "label": label, "phrase": phrase, "field": field}


#: The markets the payload can carry, in the order the UI should show them. ``expert`` is False for
#: a market the expert side has no columns for at all.
MARKET_DEFS: Tuple[Dict[str, Any], ...] = (
    {
        "key": "match_result", "label": "Match result", "kind": "ranked", "expert": True,
        "expert_confidence": ("confidence_score", "prediction"),
        "outcomes": (
            _outcome("home_win", "Home win", "a home win", "home_win_prob"),
            _outcome("draw", "Draw", "a draw", "draw_prob"),
            _outcome("away_win", "Away win", "an away win", "away_win_prob"),
        ),
    },
    {
        "key": "btts", "label": "Both teams to score", "kind": "pair", "expert": True,
        "expert_confidence": ("btts_confidence", "market"),
        "outcomes": (
            _outcome("yes", "Both teams score", "both teams scoring", "btts_yes_prob"),
            _outcome("no", "At least one team does not score", "at least one team not scoring",
                     "btts_no_prob"),
        ),
    },
    {
        "key": "over_under_25", "label": "Total goals 2.5", "kind": "pair", "expert": True,
        "expert_confidence": ("total_goals_confidence", "market"),
        "outcomes": (
            _outcome("over", "Over 2.5 goals", "over 2.5 goals", "total_goals_over_25_prob"),
            _outcome("under", "Under 2.5 goals", "under 2.5 goals", "total_goals_under_25_prob"),
        ),
    },
    {
        "key": "over_under_35", "label": "Total goals 3.5", "kind": "pair", "expert": True,
        "expert_confidence": ("total_goals_confidence", "market"),
        "outcomes": (
            _outcome("over", "Over 3.5 goals", "over 3.5 goals", "total_goals_over_35_prob"),
            _outcome("under", "Under 3.5 goals", "under 3.5 goals", "total_goals_under_35_prob"),
        ),
    },
    {
        "key": "exact_score", "label": "Exact score", "kind": "scores", "expert": False,
        "expert_confidence": None, "outcomes": (),
    },
)

MARKET_KEYS: Tuple[str, ...] = tuple(d["key"] for d in MARKET_DEFS)


# ------------------------------------------------------------------ small helpers
def _pct(probability: float) -> float:
    """A 0-1 probability as a percentage, rounded for display only. Never rescaled or renormalised."""
    return round(float(probability) * 100, 1)


def _pct_text(probability: float) -> str:
    value = _pct(probability)
    return str(int(value)) if float(value).is_integer() else str(value)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse one of our own ISO-8601 Z timestamps. Returns None for anything unreadable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:  # a timestamp we cannot read is an unknown timestamp, not a guess
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _supplied(payload: Optional[Dict[str, Any]], definition: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Outcomes this payload actually carries for this market, in the market's own order.

    A field the source left out is simply absent from the list. It is never added with a zero.
    """
    if not payload:
        return []
    found = []
    for spec in definition["outcomes"]:
        value = payload.get(spec["field"])
        if value is None:
            continue
        found.append({"key": spec["key"], "label": spec["label"], "phrase": spec["phrase"],
                      "probability": float(value), "percent": _pct(value),
                      "percent_text": _pct_text(value)})
    ranked = sorted(range(len(found)), key=lambda i: (-found[i]["probability"], i))
    for rank, index in enumerate(ranked, start=1):
        found[index]["rank"] = rank
        found[index]["most_likely"] = rank == 1
    return found


def _score_outcomes(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Listed scorelines, most likely first. The provider's "every other scoreline" bucket is not
    one of these and is reported separately, so it can never be rendered as a scoreline."""
    scores = (payload or {}).get("exact_score") or {}
    if not isinstance(scores, dict):
        return []
    rows = [(str(score), float(prob)) for score, prob in scores.items() if prob is not None]
    rows.sort(key=lambda row: (-row[1], row[0]))
    return [{"key": score, "label": score, "phrase": score, "probability": prob,
             "percent": _pct(prob), "percent_text": _pct_text(prob),
             "rank": index, "most_likely": index == 1}
            for index, (score, prob) in enumerate(rows, start=1)]


def _missing_phrase(definition: Dict[str, Any], present: Sequence[Dict[str, Any]]) -> Optional[str]:
    present_keys = {row["key"] for row in present}
    for spec in definition["outcomes"]:
        if spec["key"] not in present_keys:
            return spec["phrase"]
    return None


def _summary(source: str, definition: Dict[str, Any], outcomes: Sequence[Dict[str, Any]],
             other_scorelines: Optional[float] = None) -> Optional[str]:
    """One plain-language line about what this source published for this market.

    It states probabilities and nothing else: no recommendation, no certainty, no advice. A
    probability is never reported as an outcome that "will" happen, and an unsupplied side of a
    market is named as unsupplied rather than completed with the remainder.
    """
    if not outcomes:
        return None
    subject = _SUBJECT[source]
    kind = definition["kind"]
    if kind == "ranked":
        ranked = sorted(outcomes, key=lambda row: row["rank"])
        top = ranked[0]
        if len(ranked) == 1:
            return (f"{subject} puts {top['phrase']} at {top['percent_text']}%, and published no "
                    f"other outcome for this market.")
        second = ranked[1]
        return (f"{subject} makes {top['phrase']} the most likely single outcome at "
                f"{top['percent_text']}%, with {second['phrase']} at {second['percent_text']}%.")
    if kind == "pair":
        if len(outcomes) == 1:
            only = outcomes[0]
            absent = _missing_phrase(definition, outcomes)
            tail = f", and published nothing for {absent}" if absent else ""
            return f"{subject} puts {only['phrase']} at {only['percent_text']}%{tail}."
        first, second = outcomes[0], outcomes[1]
        return (f"{subject} puts {first['phrase']} at {first['percent_text']}% and "
                f"{second['phrase']} at {second['percent_text']}%.")
    # scorelines
    top = outcomes[0]
    line = f"{subject}'s most likely listed scoreline is {top['label']} at {top['percent_text']}%."
    if other_scorelines is not None:
        line += f" Every other scoreline is grouped together at {_pct_text(other_scorelines)}%."
    return line


def _confidence(source: str, definition: Dict[str, Any], forecast: Optional[Dict[str, Any]],
                expert: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[float], Optional[str]]:
    """Whether this source published a confidence for this market, and which one.

    A confidence is not an accuracy and not a probability, so it is carried separately with the
    scope it actually applies to. GameForecastAPI publishes no confidence at all, and an expert
    may publish one or not.

    The test is `is None`, never a truth test, and the difference is a whole statement. The
    confidence columns are nullable, so an absence has its own value and a stored zero means what
    it says: an expert who rated their own conviction at nothing. A falsy test would swallow that
    0% and report the expert as having said nothing at all, which is the opposite of what they did.
    """
    if source == MODEL:
        value = (forecast or {}).get("confidence")
        return (value is not None, float(value) if value is not None else None,
                "forecast" if value is not None else None)
    spec = definition.get("expert_confidence")
    if not spec or not expert:
        return False, None, None
    value = expert.get(spec[0])
    if value is None:
        return False, None, None
    return True, float(value), spec[1]


def _source_block(source: str, state: str, reason: Optional[str], detail: Optional[str],
                  outcomes: Sequence[Dict[str, Any]], summary: Optional[str],
                  confidence_published: bool, confidence: Optional[float],
                  confidence_scope: Optional[str], extra: Optional[Dict[str, Any]] = None,
                  *, accuracy: Dict[str, Any]) -> Dict[str, Any]:
    block = {
        "source": source,
        "state": state,
        "available": state in _PRESENT_STATES,
        "reason": reason,
        "detail": detail,
        # Empty when nothing was supplied. A market with no outcomes renders as unavailable; it is
        # never shown as 0%.
        "outcomes": list(outcomes),
        "summary": summary,
        # Three separate facts, deliberately not conflatable: the probabilities above, whether the
        # source published a confidence, and whether any accuracy was ever measured.
        "confidence_published": confidence_published,
        "confidence": confidence,
        "confidence_percent": _pct(confidence) if confidence is not None else None,
        "confidence_scope": confidence_scope,
        # Measured, per source, from settlement's counts: see _source_accuracy. Three fields so a
        # reader of the payload can tell "no figure exists" from "a figure exists" from "the
        # counts could not be read", which one boolean could not.
        "accuracy_state": accuracy["accuracy_state"],
        "accuracy_measured": accuracy["accuracy_measured"],
        "accuracy_detail": accuracy["accuracy_detail"],
    }
    block.update(extra or {})
    return block


def _freshness(forecast: Optional[Dict[str, Any]], freshness: Dict[str, Any],
               now: datetime) -> Dict[str, Any]:
    """The three provenance times, kept apart, plus which of them is unknown.

    model_run_at (the provider's own model run), provider_updated_at (when the provider last touched
    the event) and retrieved_at (when we fetched it) answer different questions. The age below says
    which field it was computed from instead of falling back silently.
    """
    source = forecast or {}
    state = source.get("state") or freshness.get("state") or STATE_UNAVAILABLE
    times = {
        "model_run_at": source.get("model_run_at"),
        "provider_updated_at": source.get("provider_updated_at"),
        "retrieved_at": source.get("fetched_at"),
    }
    basis = next((name for name in ("model_run_at", "provider_updated_at", "retrieved_at")
                  if times[name]), None)
    age_hours = None
    if basis is not None:
        parsed = _parse_iso(times[basis])
        if parsed is not None:
            age_hours = round((now - parsed).total_seconds() / 3600, 1)
    return {
        "state": state,
        "state_reason": source.get("state_reason") or freshness.get("reason"),
        "stale": state == STATE_STALE,
        "kickoff_passed": state == "kickoff_passed",
        **times,
        "model_run_at_known": times["model_run_at"] is not None,
        "provider_updated_at_known": times["provider_updated_at"] is not None,
        "retrieved_at_known": times["retrieved_at"] is not None,
        "unknown_timestamps": [name for name, value in times.items() if value is None],
        "age_basis": basis,
        "age_hours": age_hours,
        "max_age_hours": settings.FORECAST_MAX_AGE_HOURS,
        "refresh_blocked": bool(source.get("refresh_blocked", freshness.get("refresh_blocked"))),
        "refresh_blocked_reason": (source.get("refresh_blocked_reason")
                                   or freshness.get("refresh_blocked_reason")),
    }


def _stale_detail(fresh: Dict[str, Any]) -> str:
    age = fresh.get("age_hours")
    basis = {"model_run_at": "the provider's model run", "provider_updated_at": "the provider's own update",
             "retrieved_at": "our retrieval"}.get(fresh.get("age_basis") or "", "the latest known time")
    if age is None:
        return (f"The forecast we hold is older than the {fresh['max_age_hours']} h freshness limit "
                f"and has not been refreshed since.")
    return (f"The forecast we hold is {age:g} h old measured from {basis}, past the "
            f"{fresh['max_age_hours']} h freshness limit, and has not been refreshed since.")


def build_brief(*, match: Dict[str, Any], forecast: Optional[Dict[str, Any]],
                freshness: Optional[Dict[str, Any]] = None,
                expert: Optional[Dict[str, Any]] = None,
                now: Optional[datetime] = None,
                scoring: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Assemble the brief for one match.

    ``match`` is the serialised match payload, ``forecast`` the serialised provider forecast (None
    when no forecast record exists), ``freshness`` the verdict from ``ForecastService.freshness``
    (needed when ``forecast`` is None, because "we cannot refresh right now" still holds then), and
    ``expert`` the serialised expert prediction.

    ``scoring`` is one ``scoring_summary(db)`` / ``summarise_scoring(...)`` result: how much of
    this installation has been scored against a result. A caller building many briefs in one
    request should measure it once, on the session it already holds, and pass it to all of them —
    which is what the match endpoints do. Left out, it comes from the cached
    ``current_scoring_summary()``, whose fallback opens a session of its own and is there for
    callers that genuinely have none (scripts, shells, tests). It is measured either way: the one
    thing this function may never do is state the scoring position from a literal.
    """
    now = now or datetime.now(timezone.utc)
    scoring = scoring if scoring is not None else current_scoring_summary()
    provider = (forecast or {}).get("provider")
    # Each block is told its own source, and what to say when this fixture has none of that kind.
    # Neither is ever handed the installation-wide sentence: that one belongs to ``reliability``,
    # where it is scoped in its own words, and it is a statement about whoever has been scored.
    model_accuracy = _source_accuracy(
        # The subject is only ever used where there is a provider to name; the guard is here so a
        # future edit to that branch cannot put the string "from None" in front of a reader.
        scoring, "model_provider", provider, f"from {provider}" if provider else "from this provider",
        kind="forecast provider", absent="No provider forecast has been retrieved for this match.")
    expert_accuracy = _source_accuracy(
        scoring, "expert", (expert or {}).get("created_by"), "from this expert", kind="expert",
        absent="No expert has published a prediction for this match.")
    fresh = _freshness(forecast, freshness or {}, now)
    stale, blocked = fresh["stale"], fresh["refresh_blocked"]
    reference_only = fresh["kickoff_passed"]

    missing: List[Dict[str, Any]] = []
    markets: List[Dict[str, Any]] = []

    if forecast is None:
        model_gap_reason: Optional[str] = NO_FORECAST_RETRIEVED
        model_gap_detail: Optional[str] = ("No forecast has ever been retrieved for this fixture, so "
                                           "the model's view of it is unknown.")
        missing.append({"scope": "source", "source": MODEL, "market": None,
                        "reason": NO_FORECAST_RETRIEVED, "detail": model_gap_detail})
    else:
        model_gap_reason, model_gap_detail = MARKET_NOT_IN_FORECAST, (
            "A forecast was retrieved for this fixture, but it did not include this market.")
        if stale:
            missing.append({"scope": "source", "source": MODEL, "market": None,
                            "reason": FORECAST_STALE, "detail": _stale_detail(fresh)})

    if blocked and (forecast is None or stale):
        # Distinct from "we do not know": the provider has an answer we have not asked for, because
        # asking is currently blocked.
        reason_text = fresh.get("refresh_blocked_reason") or "refreshing is paused"
        missing.append({"scope": "source", "source": MODEL, "market": None, "reason": REFRESH_BLOCKED,
                        "detail": f"Nobody has asked the provider recently: {reason_text}."})

    if expert is None:
        missing.append({"scope": "source", "source": EXPERT, "market": None,
                        "reason": NO_EXPERT_PREDICTION,
                        "detail": "No expert has published a prediction for this fixture."})

    model_markets: List[str] = []
    expert_markets: List[str] = []

    for definition in MARKET_DEFS:
        key = definition["key"]
        is_scores = definition["kind"] == "scores"
        model_outcomes = _score_outcomes(forecast) if is_scores else _supplied(forecast, definition)
        other_scorelines = (forecast or {}).get("exact_score_other_prob") if is_scores else None
        if model_outcomes:
            model_conf = _confidence(MODEL, definition, forecast, expert)
            model_markets.append(key)
            state = STATE_STALE if stale else (STATE_REFERENCE_ONLY if reference_only else STATE_AVAILABLE)
            model_block = _source_block(
                MODEL, state, FORECAST_STALE if stale else None,
                _stale_detail(fresh) if stale else fresh.get("state_reason") if reference_only else None,
                model_outcomes, _summary(MODEL, definition, model_outcomes, other_scorelines),
                *model_conf,
                extra={"other_scorelines_probability": other_scorelines,
                       "other_scorelines_percent": _pct(other_scorelines) if other_scorelines is not None else None}
                if is_scores else None,
                accuracy=model_accuracy)
        else:
            # A confidence attached to a market the source never supplied would be meaningless, so
            # the unavailable block carries none at all rather than the forecast-wide value.
            model_block = _source_block(MODEL, STATE_UNAVAILABLE, model_gap_reason, model_gap_detail,
                                        [], None, False, None, None,
                                        extra={"other_scorelines_probability": None,
                                               "other_scorelines_percent": None} if is_scores else None,
                                        accuracy=model_accuracy)
            missing.append({"scope": "market", "source": MODEL, "market": key,
                            "reason": model_gap_reason, "detail": model_gap_detail})

        if not definition["expert"]:
            expert_detail = "Experts do not publish scoreline probabilities."
            expert_block = _source_block(EXPERT, STATE_UNAVAILABLE, NOT_OFFERED_BY_SOURCE,
                                         expert_detail, [], None, False, None, None,
                                         accuracy=expert_accuracy)
            missing.append({"scope": "market", "source": EXPERT, "market": key,
                            "reason": NOT_OFFERED_BY_SOURCE, "detail": expert_detail})
        else:
            expert_outcomes = _supplied(expert, definition)
            if expert_outcomes:
                # A conviction is only ever read where the market has outcomes to attach it to.
                # The expert API now refuses a body that would store btts_confidence or
                # total_goals_confidence over a withdrawn market (MARKET_CONVICTIONS in
                # app/schemas/predictions.py), but rows written before that rule existed can
                # still hold the shape, and a 90% conviction beside an empty outcome list is not
                # something this brief should ever put in front of a reader.
                expert_conf = _confidence(EXPERT, definition, forecast, expert)
                expert_markets.append(key)
                expert_block = _source_block(
                    EXPERT, STATE_REFERENCE_ONLY if reference_only else STATE_AVAILABLE, None,
                    None, expert_outcomes, _summary(EXPERT, definition, expert_outcomes), *expert_conf,
                    accuracy=expert_accuracy)
            else:
                reason = NO_EXPERT_PREDICTION if expert is None else MARKET_NOT_SUPPLIED
                detail = ("No expert has published a prediction for this fixture." if expert is None
                          else "The expert published a prediction for this fixture, but left this "
                               "market out of it.")
                expert_block = _source_block(EXPERT, STATE_UNAVAILABLE, reason, detail, [], None,
                                             False, None, None, accuracy=expert_accuracy)
                missing.append({"scope": "market", "source": EXPERT, "market": key,
                                "reason": reason, "detail": detail})

        markets.append({
            "key": key, "label": definition["label"], "kind": definition["kind"],
            "supplied_by": [name for name, block in ((MODEL, model_block), (EXPERT, expert_block))
                            if block["available"]],
            MODEL: model_block, EXPERT: expert_block,
        })

    headline = next((block["summary"] for market in markets
                     for block in (market[MODEL], market[EXPERT]) if block["summary"]), None)
    if headline is None:
        headline = missing[0]["detail"] if missing else None

    model_confidence = (forecast or {}).get("confidence")
    # `is None`, not falsiness and not `<= 0`. The reliability block below turns this into two
    # separate claims - whether the expert published a conviction at all, and what it was - and a
    # zero has to survive as the second answer to the first question, because an expert who rates
    # their own prediction at 0% has said something and the block renders it as 0%. The `<= 0`
    # form this replaces came from the era when the column was NOT NULL and 0.0000 was what a
    # blank field became; it now silently deletes real convictions of zero. (Negatives cannot
    # occur: ck_predictions_confidence keeps the column inside 0-1.)
    expert_confidence = (expert or {}).get("confidence_score")
    expert_confidence = None if expert_confidence is None else float(expert_confidence)

    return {
        "match_id": match.get("id"),
        "assembled_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "headline": headline,
        "known": {
            "kickoff_utc": match.get("kickoff_utc"),
            "kickoff_known": match.get("kickoff_utc") is not None,
            "status": match.get("status"),
            "competition": match.get("competition"),
            "competition_known": match.get("competition") is not None,
            "model_markets": model_markets,
            "expert_markets": expert_markets,
            "sources": [
                {"source": MODEL, "present": forecast is not None,
                 "provider": (forecast or {}).get("provider"),
                 "external_event_id": (forecast or {}).get("external_event_id"),
                 "match_confidence": (forecast or {}).get("match_confidence"),
                 "matched_by": (forecast or {}).get("matched_by"),
                 "markets": model_markets},
                {"source": EXPERT, "present": expert is not None,
                 "prediction_id": (expert or {}).get("id"),
                 "published_at": (expert or {}).get("published_at"),
                 "created_by": (expert or {}).get("created_by"),
                 "markets": expert_markets},
            ],
        },
        "markets": markets,
        "missing": missing,
        "missing_reasons": sorted({entry["reason"] for entry in missing}),
        "freshness": fresh,
        "reliability": {
            # A published probability, a published confidence and a measured accuracy are three
            # different things. They are carried as three fields so the UI cannot merge them.
            MODEL: {
                "confidence_published": model_confidence is not None,
                "confidence": float(model_confidence) if model_confidence is not None else None,
                "detail": ("This provider published a confidence value with the forecast."
                           if model_confidence is not None
                           else "This provider publishes no confidence value with its forecasts."),
            },
            EXPERT: {
                "confidence_published": expert_confidence is not None,
                "confidence": expert_confidence,
                "detail": ("The expert published a confidence value with this prediction."
                           if expert_confidence is not None
                           else "The expert published no confidence value with this prediction."),
            },
            # Measured on every load from settlement's own counts, and kept as three separate
            # facts: which of the three states this installation is in, whether a figure exists at
            # all, and whether anything has been scored. The old payload answered all three with
            # one hardcoded False and one hardcoded sentence.
            "accuracy_state": scoring["accuracy_state"],
            "accuracy_measured": scoring["accuracy_measured"],
            "results_scored": scoring["results_scored"],
            "detail": scoring["detail"],
            "scoring": {key: scoring.get(key) for key in
                        ("accuracy_state", "eligible", "scored", "pending", "void", "not_scored",
                         "published_figures", "minimum_sample", "window", "measured_at",
                         "counted_by", "published_by", "unavailable_reason")
                        if key in scoring},
        },
        "anomalies": (forecast or {}).get("anomalies") or [],
    }


def compact_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    """The part of the brief a match card needs, derived from the full brief with no extra work.

    Built from the same in-memory values, so adding it to the list payload costs no database query
    per match.
    """
    fresh = brief["freshness"]
    return {
        "match_id": brief["match_id"],
        "headline": brief["headline"],
        "supplied_markets": {MODEL: brief["known"]["model_markets"],
                             EXPERT: brief["known"]["expert_markets"]},
        "missing_markets": {
            MODEL: [entry["market"] for entry in brief["missing"]
                    if entry["scope"] == "market" and entry["source"] == MODEL],
            EXPERT: [entry["market"] for entry in brief["missing"]
                     if entry["scope"] == "market" and entry["source"] == EXPERT],
        },
        "missing_reasons": brief["missing_reasons"],
        "forecast_state": fresh["state"],
        "stale": fresh["stale"],
        "refresh_blocked": fresh["refresh_blocked"],
        "refresh_blocked_reason": fresh["refresh_blocked_reason"],
        "confidence_published": {MODEL: brief["reliability"][MODEL]["confidence_published"],
                                 EXPERT: brief["reliability"][EXPERT]["confidence_published"]},
        # Carried as the state as well as the boolean: a card that only knows "no figure" cannot
        # tell a brand-new installation from one whose sample is still building.
        "accuracy_state": brief["reliability"]["accuracy_state"],
        "accuracy_measured": brief["reliability"]["accuracy_measured"],
    }
