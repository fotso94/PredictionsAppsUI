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
serialised forecast, the freshness verdict and the serialised expert prediction), so it costs no
database query of its own and can be tested without a database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import settings

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

# ------------------------------------------------------------------ accuracy
#: Nothing in this application has ever scored a prediction against a result, so no accuracy figure
#: exists for any source. This is stated as a fact of its own so a confidence value published by a
#: source can never be read as a measured accuracy. When result scoring lands, this becomes a lookup.
ACCURACY_MEASURED = False
ACCURACY_DETAIL = ("No prediction has been scored against a match result yet, so no accuracy has "
                   "ever been measured for this source.")


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
    scope it actually applies to. GameForecastAPI publishes no confidence at all; an expert who
    filled nothing in is stored as 0.0 by a NOT NULL column, which is an absence rather than a
    published zero, and is reported as such.
    """
    if source == MODEL:
        value = (forecast or {}).get("confidence")
        return (value is not None, float(value) if value is not None else None,
                "forecast" if value is not None else None)
    spec = definition.get("expert_confidence")
    if not spec or not expert:
        return False, None, None
    value = expert.get(spec[0])
    if value is None or float(value) <= 0:
        # 0.0 is the column default for "the expert did not fill this in", not a published zero.
        return False, None, None
    return True, float(value), spec[1]


def _source_block(source: str, state: str, reason: Optional[str], detail: Optional[str],
                  outcomes: Sequence[Dict[str, Any]], summary: Optional[str],
                  confidence_published: bool, confidence: Optional[float],
                  confidence_scope: Optional[str], extra: Optional[Dict[str, Any]] = None
                  ) -> Dict[str, Any]:
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
        "accuracy_measured": ACCURACY_MEASURED,
        "accuracy_detail": ACCURACY_DETAIL,
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
                now: Optional[datetime] = None) -> Dict[str, Any]:
    """Assemble the brief for one match.

    ``match`` is the serialised match payload, ``forecast`` the serialised provider forecast (None
    when no forecast record exists), ``freshness`` the verdict from ``ForecastService.freshness``
    (needed when ``forecast`` is None, because "we cannot refresh right now" still holds then), and
    ``expert`` the serialised expert prediction.
    """
    now = now or datetime.now(timezone.utc)
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
        model_conf = _confidence(MODEL, definition, forecast, expert)
        if model_outcomes:
            model_markets.append(key)
            state = STATE_STALE if stale else (STATE_REFERENCE_ONLY if reference_only else STATE_AVAILABLE)
            model_block = _source_block(
                MODEL, state, FORECAST_STALE if stale else None,
                _stale_detail(fresh) if stale else fresh.get("state_reason") if reference_only else None,
                model_outcomes, _summary(MODEL, definition, model_outcomes, other_scorelines),
                *model_conf,
                extra={"other_scorelines_probability": other_scorelines,
                       "other_scorelines_percent": _pct(other_scorelines) if other_scorelines is not None else None}
                if is_scores else None)
        else:
            # A confidence attached to a market the source never supplied would be meaningless, so
            # the unavailable block carries none at all rather than the forecast-wide value.
            model_block = _source_block(MODEL, STATE_UNAVAILABLE, model_gap_reason, model_gap_detail,
                                        [], None, False, None, None,
                                        extra={"other_scorelines_probability": None,
                                               "other_scorelines_percent": None} if is_scores else None)
            missing.append({"scope": "market", "source": MODEL, "market": key,
                            "reason": model_gap_reason, "detail": model_gap_detail})

        if not definition["expert"]:
            expert_detail = "Experts do not publish scoreline probabilities."
            expert_block = _source_block(EXPERT, STATE_UNAVAILABLE, NOT_OFFERED_BY_SOURCE,
                                         expert_detail, [], None, False, None, None)
            missing.append({"scope": "market", "source": EXPERT, "market": key,
                            "reason": NOT_OFFERED_BY_SOURCE, "detail": expert_detail})
        else:
            expert_outcomes = _supplied(expert, definition)
            expert_conf = _confidence(EXPERT, definition, forecast, expert)
            if expert_outcomes:
                expert_markets.append(key)
                expert_block = _source_block(
                    EXPERT, STATE_REFERENCE_ONLY if reference_only else STATE_AVAILABLE, None,
                    None, expert_outcomes, _summary(EXPERT, definition, expert_outcomes), *expert_conf)
            else:
                reason = NO_EXPERT_PREDICTION if expert is None else MARKET_NOT_SUPPLIED
                detail = ("No expert has published a prediction for this fixture." if expert is None
                          else "The expert published a prediction for this fixture, but left this "
                               "market out of it.")
                expert_block = _source_block(EXPERT, STATE_UNAVAILABLE, reason, detail, [], None,
                                             False, None, None)
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
    expert_confidence = (expert or {}).get("confidence_score")
    expert_confidence = None if expert_confidence is None or float(expert_confidence) <= 0 else float(expert_confidence)

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
            "accuracy_measured": ACCURACY_MEASURED,
            "results_scored": ACCURACY_MEASURED,
            "detail": ACCURACY_DETAIL,
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
        "accuracy_measured": ACCURACY_MEASURED,
    }
