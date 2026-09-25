"""
The market contract: every selection a reader can take from a stored provider forecast, read the
same way every time, with its source, its validity and what can settle it written beside it.

WHAT THIS IS BUILT FROM. The stored GameForecastAPI event (``raw_payload`` on
``provider_forecasts`` and on every ``provider_forecast_snapshots`` row). The five markets the rest
of the product already normalises - 1X2, both teams to score, over/under 2.5 and 3.5, exact score -
are read through the provider adapter's own ``parse_event`` so this module cannot disagree with the
forecast page about them. The payload also carries, in the same ``predictions[]`` entry, markets the
adapter never stored as columns: total-goals lines 0.5 and 1.5, each team's own goal totals at four
lines, the first-half result, and which team scores first. Those are read here, validated by the
same rules, and served as selections.

NOTHING IS PREDICTED HERE. Every probability is either the provider's own number
(``probability_source: provider``) or an arithmetic consequence of the provider's own numbers
(``probability_source: calculated``) with the formula and the inputs kept on the selection: double
chance is the sum of two 1X2 outcomes, draw-no-bet is a 1X2 outcome conditioned on there being no
draw. Both need a COMPLETE 1X2 whose outcomes sum to one within the adapter's tolerance; a partial
or inconsistent 1X2 yields no derived market, because a sum built on it would be an invention.
Nothing is ever derived from the exact-score table: it is truncated by construction (the provider
keeps a remainder in an "other" bucket), so any market read off it would silently drop that bucket.

WHAT A SELECTION KNOWS ABOUT SETTLING ITSELF. Each carries a ``settlement`` block: the basis it
would settle on (regulation time, the half-time score, the order of goals) and whether this
installation holds that data. Regulation-time markets settle on the same ``regulation_score`` the
forecast scoring uses (app/services/settlement.py); the first-half result needs a stored half-time
score and says so; "team to score first" needs the order of goals, which no configured source
supplies, and is served as NOT automatically trackable rather than guessed from the final score
(the one case the score does decide - nobody scored - is the exception, and is settled).

REPROCESSING IS NOT FETCHING. ``built_at`` is when this normalisation ran; ``retrieved_at``,
``model_run_at`` and ``provider_updated_at`` are the forecast's own times and travel unchanged, so
markets rebuilt from a months-old snapshot are stamped with the snapshot's times, never with now.
``normalisation_version`` names the rules that read the payload, so a leg saved under one version
can be told apart from one saved under the next.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.providers.base import parse_utc
from app.services.providers.gameforecast import SUM_TOLERANCE, ZERO_TOLERANCE, parse_event, to_probability

NORMALISATION_VERSION = "markets.v1"
PROVIDER_GAMEFORECAST = "gameforecast"

# ------------------------------------------------------------------------------ vocabulary
MATCH_RESULT = "match_result"
DOUBLE_CHANCE = "double_chance"
DRAW_NO_BET = "draw_no_bet"
TOTAL_GOALS = "total_goals"
HOME_TEAM_GOALS = "home_team_goals"
AWAY_TEAM_GOALS = "away_team_goals"
BOTH_TEAMS_SCORE = "both_teams_score"
FIRST_HALF_RESULT = "first_half_result"
TEAM_TO_SCORE_FIRST = "team_to_score_first"
EXACT_SCORE = "exact_score"

PERIOD_REGULATION = "regulation"
PERIOD_FIRST_HALF = "first_half"

GROUP_OUTCOME = "outcome"
GROUP_GOALS = "goals"
GROUP_FIRST_HALF = "first_half"
GROUP_TEAM = "team"
GROUP_EXACT_SCORE = "exact_score"

#: The order groups and markets are served in. The frontend keeps it.
GROUP_ORDER = (GROUP_OUTCOME, GROUP_GOALS, GROUP_FIRST_HALF, GROUP_TEAM, GROUP_EXACT_SCORE)
MARKET_GROUP = {
    MATCH_RESULT: GROUP_OUTCOME, DOUBLE_CHANCE: GROUP_OUTCOME, DRAW_NO_BET: GROUP_OUTCOME,
    TOTAL_GOALS: GROUP_GOALS, BOTH_TEAMS_SCORE: GROUP_GOALS,
    FIRST_HALF_RESULT: GROUP_FIRST_HALF,
    HOME_TEAM_GOALS: GROUP_TEAM, AWAY_TEAM_GOALS: GROUP_TEAM, TEAM_TO_SCORE_FIRST: GROUP_TEAM,
    EXACT_SCORE: GROUP_EXACT_SCORE,
}
#: Tie-break order when two selections share a probability (suggestions read this).
MARKET_PRIORITY = (MATCH_RESULT, DOUBLE_CHANCE, DRAW_NO_BET, TOTAL_GOALS, BOTH_TEAMS_SCORE,
                   HOME_TEAM_GOALS, AWAY_TEAM_GOALS, FIRST_HALF_RESULT, TEAM_TO_SCORE_FIRST, EXACT_SCORE)

GOAL_LINES = (0.5, 1.5, 2.5, 3.5)

# ------------------------------------------------------------------------------ settlement statements
SETTLE_REGULATION = {
    "capable": True, "basis": "regulation_time",
    "rule": "Settles on the regulation-time score (90 minutes plus stoppage). Extra time and "
            "penalties settle nothing; a fixture never played to a result is void.",
}
SETTLE_DRAW_NO_BET = {
    "capable": True, "basis": "regulation_time",
    "rule": "Settles on the regulation-time score; a draw after 90 minutes voids the selection.",
}
SETTLE_HALF_TIME = {
    "capable": True, "basis": "half_time",
    "rule": "Settles on the stored half-time score. Left unresolved when no half-time score is "
            "stored for the fixture; nothing is inferred from the final score.",
}
SETTLE_EVENT_ORDER = {
    "capable": False, "basis": "event_order",
    "rule": "Needs the order in which the goals were scored, which no configured source supplies. "
            "Not tracked automatically, except that a 0-0 after 90 minutes settles 'neither'.",
    "reason": "no configured result source records the order of goals",
}
MARKET_SETTLEMENT = {
    MATCH_RESULT: SETTLE_REGULATION, DOUBLE_CHANCE: SETTLE_REGULATION, DRAW_NO_BET: SETTLE_DRAW_NO_BET,
    TOTAL_GOALS: SETTLE_REGULATION, HOME_TEAM_GOALS: SETTLE_REGULATION, AWAY_TEAM_GOALS: SETTLE_REGULATION,
    BOTH_TEAMS_SCORE: SETTLE_REGULATION, EXACT_SCORE: SETTLE_REGULATION,
    FIRST_HALF_RESULT: SETTLE_HALF_TIME, TEAM_TO_SCORE_FIRST: SETTLE_EVENT_ORDER,
}
MARKET_PERIOD = {market: (PERIOD_FIRST_HALF if market == FIRST_HALF_RESULT else PERIOD_REGULATION)
                 for market in MARKET_GROUP}


# ------------------------------------------------------------------------------ value objects
def selection_key(market_id: str, outcome: str, line: Optional[float] = None) -> str:
    """The stable id of one selection: ``total_goals:over@2.5``, ``match_result:home``, ``exact_score:1-0``."""
    return f"{market_id}:{outcome}" + (f"@{_line_text(line)}" if line is not None else "")


def parse_selection_key(key: str) -> Optional[Tuple[str, str, Optional[float]]]:
    """The inverse of ``selection_key``; None for anything that is not one."""
    if not isinstance(key, str) or ":" not in key:
        return None
    market_id, _, rest = key.partition(":")
    outcome, _, line_text = rest.partition("@")
    if not market_id or not outcome:
        return None
    if line_text == "":
        return market_id, outcome, None
    try:
        return market_id, outcome, float(line_text)
    except ValueError:
        return None


def _line_text(line: float) -> str:
    return f"{line:g}"


@dataclass
class Selection:
    market_id: str
    outcome: str
    line: Optional[float]
    period: str
    probability: Optional[float]
    probability_source: str = "provider"
    calculation: Optional[Dict[str, Any]] = None
    available: bool = True
    unavailable_reason: Optional[str] = None
    warnings: List[Dict[str, str]] = field(default_factory=list)
    odds: Optional[Dict[str, Any]] = None

    @property
    def selection_id(self) -> str:
        return selection_key(self.market_id, self.outcome, self.line)

    @property
    def settlement(self) -> Dict[str, Any]:
        return dict(MARKET_SETTLEMENT[self.market_id])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "market_id": self.market_id,
            "outcome": self.outcome,
            "line": self.line,
            "period": self.period,
            "probability": self.probability,
            "probability_source": self.probability_source,
            "calculation": self.calculation,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "warnings": list(self.warnings),
            "settlement": self.settlement,
            "odds": self.odds,
        }


@dataclass
class Market:
    market_id: str
    line: Optional[float]
    selections: List[Selection]
    available: bool
    unavailable_reason: Optional[str] = None
    warnings: List[Dict[str, str]] = field(default_factory=list)
    #: The provider's remainder for scorelines it did not list; exact score only, never a selection.
    remainder: Optional[float] = None

    @property
    def group(self) -> str:
        return MARKET_GROUP[self.market_id]

    @property
    def period(self) -> str:
        return MARKET_PERIOD[self.market_id]

    def to_dict(self) -> Dict[str, Any]:
        body = {
            "market_id": self.market_id,
            "group": self.group,
            "period": self.period,
            "line": self.line,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "warnings": list(self.warnings),
            "settlement": dict(MARKET_SETTLEMENT[self.market_id]),
            "selections": [s.to_dict() for s in self.selections],
        }
        if self.market_id == EXACT_SCORE:
            body["remainder"] = self.remainder
        return body


# ------------------------------------------------------------------------------ reading one block
def _warn(code: str, message: str) -> Dict[str, str]:
    return {"severity": "warning", "code": code, "message": message}


def _note(code: str, message: str) -> Dict[str, str]:
    return {"severity": "note", "code": code, "message": message}


def _read_values(block: Any, keys: Sequence[str]) -> Tuple[Dict[str, Optional[float]], List[str]]:
    """Read the named keys of one provider block as 0-1 probabilities.

    Returns the values and the keys that were PRESENT but unreadable (not a finite number in
    0..100). Absent and unreadable are different facts and are reported differently.
    """
    values: Dict[str, Optional[float]] = {}
    invalid: List[str] = []
    source = block if isinstance(block, dict) else {}
    for key in keys:
        raw = source.get(key)
        probability = to_probability(raw)
        if raw is not None and probability is None:
            invalid.append(key)
        values[key] = probability
    return values, invalid


def _validate(label: str, values: Dict[str, Optional[float]], invalid: Sequence[str]) -> Tuple[bool, Optional[str], List[Dict[str, str]]]:
    """Whether a block is usable as a market, why not, and what is worth knowing about it.

    * nothing supplied            -> unavailable: not published.
    * every value zero            -> unavailable: a placeholder, not a forecast of anything.
    * some outcomes missing       -> the published outcomes stay usable; the market is partial
                                     and says so (a probability the provider published is not
                                     made false by a sibling it did not).
    * outcomes do not sum to one  -> usable, with a warning the reader must see; the numbers are
                                     the provider's and are not corrected here.
    A genuine zero inside a distribution that otherwise sums to one is kept as zero.
    """
    warnings: List[Dict[str, str]] = []
    for key in invalid:
        warnings.append(_warn("invalid_value", f"{label}: the value for '{key}' is not a percentage between 0 and 100"))
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        reason = "not published by the provider" if not invalid else "every published value was unreadable"
        return False, reason, warnings
    if sum(present.values()) <= ZERO_TOLERANCE:
        warnings.append(_warn("market_all_zero", f"{label}: every value is zero; a placeholder, not a forecast"))
        return False, "published as all zeros, which is a placeholder rather than a forecast", warnings
    if len(present) < len(values):
        missing = [k for k, v in values.items() if v is None]
        warnings.append(_note("market_incomplete", f"{label}: {', '.join(missing)} not supplied"))
        return True, None, warnings
    total = sum(present.values())
    if abs(total - 1.0) > SUM_TOLERANCE:
        warnings.append(_warn("sum_out_of_tolerance", f"{label}: probabilities sum to {round(total * 100, 1)}%"))
    return True, None, warnings


def _consistent(values: Dict[str, Optional[float]]) -> bool:
    """A complete distribution whose outcomes sum to one within tolerance - what a derivation may use."""
    if any(v is None for v in values.values()):
        return False
    return abs(sum(values.values()) - 1.0) <= SUM_TOLERANCE


def _market(market_id: str, line: Optional[float], label: str, values: Dict[str, Optional[float]],
            invalid: Sequence[str]) -> Market:
    available, reason, warnings = _validate(label, values, invalid)
    period = MARKET_PERIOD[market_id]
    selections = []
    for outcome, probability in values.items():
        if available and probability is not None:
            selections.append(Selection(market_id, outcome, line, period, probability))
        else:
            why = reason or "not published by the provider"
            selections.append(Selection(market_id, outcome, line, period, None, available=False, unavailable_reason=why))
    return Market(market_id, line, selections, available, reason, warnings)


# ------------------------------------------------------------------------------ the payload
#: The blocks a selection can be taken from. The digest below is what makes two payloads "the same
#: evidence": a change in ANY of these, or in the carried prices, is a new forecast snapshot.
SELECTABLE_BLOCKS = ("match_result", "total_goals", "home_team_goals", "away_team_goals", "both_teams_score",
                     "first_half_winner", "team_to_score_first", "exact_score")


def markets_digest(event: Any) -> Optional[str]:
    """A stable hash of every selectable block and the carried odds of the latest prediction entry.

    Selecting only the adapter's five stored markets for the snapshot hash let a payload whose
    first-half block, team totals, 0.5/1.5 lines, first scorer or prices had changed pass as
    "unchanged": no new snapshot was written, and a leg taken from the new numbers was attributed
    to a snapshot holding the old ones. Everything a leg can be read from is in here.
    """
    if not isinstance(event, dict):
        return None
    prediction = latest_prediction(event)
    if prediction is None:
        return None
    body = {"blocks": {name: prediction.get(name) for name in SELECTABLE_BLOCKS},
            "run_at": prediction.get("run_at"), "odds": event.get("odds")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def latest_prediction(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The prediction entry the adapter reads: the most recent ``run_at``."""
    predictions = event.get("predictions") if isinstance(event, dict) else None
    if not isinstance(predictions, list) or not predictions:
        return None
    entries = [p for p in predictions if isinstance(p, dict)]
    if not entries:
        return None
    return max(entries, key=lambda p: str(p.get("run_at") or ""))


def _totals_market(market_id: str, label: str, block: Any, line: float) -> Market:
    tag = _line_text(line).replace(".", "_")
    values, invalid = _read_values(block, (f"over_{tag}", f"under_{tag}"))
    renamed = {"over": values[f"over_{tag}"], "under": values[f"under_{tag}"]}
    invalid_renamed = [k.split("_")[0] for k in invalid]
    return _market(market_id, line, f"{label} {_line_text(line)}", renamed, invalid_renamed)


def _derived_from_1x2(result: Market) -> List[Market]:
    """Double chance and draw-no-bet, from a complete and consistent 1X2 only."""
    values = {s.outcome: s.probability for s in result.selections}
    if not result.available or not _consistent(values):
        reason = ("calculated from the 1X2 market, which is " +
                  ("not available" if not result.available else "incomplete or does not sum to one") +
                  " for this fixture")
        empty = []
        for market_id, outcomes in ((DOUBLE_CHANCE, ("1x", "12", "x2")), (DRAW_NO_BET, ("home", "away"))):
            selections = [Selection(market_id, o, None, PERIOD_REGULATION, None, "calculated",
                                    available=False, unavailable_reason=reason) for o in outcomes]
            empty.append(Market(market_id, None, selections, False, reason))
        return empty
    home, draw, away = values["home"], values["draw"], values["away"]
    inputs = {"home": home, "draw": draw, "away": away}

    def calc(formula: str, keys: Sequence[str]) -> Dict[str, Any]:
        return {"formula": formula, "inputs": {k: inputs[k] for k in keys},
                "source_market": MATCH_RESULT, "note": "calculated from provider probabilities"}

    double_chance = Market(DOUBLE_CHANCE, None, [
        Selection(DOUBLE_CHANCE, "1x", None, PERIOD_REGULATION, home + draw, "calculated",
                  calc("P(1X) = P(home) + P(draw)", ("home", "draw"))),
        Selection(DOUBLE_CHANCE, "12", None, PERIOD_REGULATION, home + away, "calculated",
                  calc("P(12) = P(home) + P(away)", ("home", "away"))),
        Selection(DOUBLE_CHANCE, "x2", None, PERIOD_REGULATION, draw + away, "calculated",
                  calc("P(X2) = P(draw) + P(away)", ("draw", "away"))),
    ], True)
    not_draw = home + away
    if not_draw <= ZERO_TOLERANCE:
        reason = "the provider gives the draw the whole probability, so nothing is left to condition on"
        dnb = Market(DRAW_NO_BET, None, [
            Selection(DRAW_NO_BET, o, None, PERIOD_REGULATION, None, "calculated", available=False,
                      unavailable_reason=reason) for o in ("home", "away")], False, reason)
    else:
        dnb = Market(DRAW_NO_BET, None, [
            Selection(DRAW_NO_BET, "home", None, PERIOD_REGULATION, home / not_draw, "calculated",
                      calc("P(home | no draw) = P(home) / (P(home) + P(away))", ("home", "away"))),
            Selection(DRAW_NO_BET, "away", None, PERIOD_REGULATION, away / not_draw, "calculated",
                      calc("P(away | no draw) = P(away) / (P(home) + P(away))", ("home", "away"))),
        ], True)
    return [double_chance, dnb]


def _exact_score_market(parsed_scores: Optional[Dict[str, float]], other: Optional[float],
                        raw_block: Any, anomalies: Sequence[Dict[str, str]]) -> Market:
    warnings = [a for a in anomalies if a.get("code") in ("score_unreadable", "score_zero_dropped", "score_sum_out_of_tolerance")]
    if not parsed_scores:
        reason = "not published by the provider" if not isinstance(raw_block, dict) or not raw_block \
            else "no readable scoreline with a probability above zero"
        return Market(EXACT_SCORE, None, [], False, reason, warnings, other)
    selections = [Selection(EXACT_SCORE, label, None, PERIOD_REGULATION, probability)
                  for label, probability in sorted(parsed_scores.items(), key=lambda kv: (-kv[1], kv[0]))]
    return Market(EXACT_SCORE, None, selections, True, None, warnings, other)


def _provider_odds(event: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
    """The 1X2 decimal prices the payload carries, keyed by outcome, and a description of them.

    GameForecast's ``odds`` entries name no bookmaker; they are served as a provider odds snapshot
    dated with the entry's ``run_at`` and are attached to the match-result selections only. No
    other market's price is derived from them: a double-chance or draw-no-bet price is a
    bookmaker's number with a bookmaker's margin in it, not an arithmetic consequence of these.
    """
    entries = event.get("odds") if isinstance(event, dict) else None
    if not isinstance(entries, list):
        return {}, None
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("key") != "match_winner":
            continue
        values = entry.get("values") if isinstance(entry.get("values"), dict) else {}
        captured = parse_utc(entry.get("run_at"))
        prices: Dict[str, Dict[str, Any]] = {}
        for provider_name, outcome in (("Home", "home"), ("Draw", "draw"), ("Away", "away")):
            raw = values.get(provider_name)
            try:
                price = float(raw)
            except (TypeError, ValueError):
                continue
            if not (price > 1.0):
                continue
            prices[outcome] = {"value": price, "format": "decimal", "source": "provider_snapshot",
                               "provider": PROVIDER_GAMEFORECAST,
                               "captured_at": captured.isoformat() if captured else None}
        if prices:
            description = {"market_id": MATCH_RESULT, "source": "provider_snapshot", "provider": PROVIDER_GAMEFORECAST,
                           "bookmaker": None, "captured_at": captured.isoformat() if captured else None,
                           "note": "decimal prices carried in the provider payload; the bookmaker is not named"}
            return prices, description
    return {}, None


# ------------------------------------------------------------------------------ recommended bets
_TOKEN_MARKET = {
    "matchResult": MATCH_RESULT, "totalGoals": TOTAL_GOALS, "bothTeamsScore": BOTH_TEAMS_SCORE,
    "homeTeamGoals": HOME_TEAM_GOALS, "awayTeamGoals": AWAY_TEAM_GOALS, "firstHalfWinner": FIRST_HALF_RESULT,
    "teamToScoreFirst": TEAM_TO_SCORE_FIRST, "exactScore": EXACT_SCORE, "doubleChance": DOUBLE_CHANCE,
    "drawNoBet": DRAW_NO_BET,
}
_TOKEN_OUTCOME = {
    "homewinprobability": "home", "drawprobability": "draw", "awaywinprobability": "away",
    "home": "home", "draw": "draw", "away": "away", "homeprobability": "home", "awayprobability": "away",
    "neitherprobability": "neither", "neither": "neither", "yes": "yes", "no": "no",
    "1x": "1x", "12": "12", "x2": "x2",
}
_TOTALS_TOKEN = re.compile(r"^(over|under)(\d)_(\d)$", re.IGNORECASE)
_SCORE_TOKEN = re.compile(r"^(\d+)_(\d+)$")


def resolve_recommended_bet(token: Any) -> Tuple[Optional[Tuple[str, str, Optional[float]]], Optional[str]]:
    """Map one provider ``recommended_bets`` value to (market, outcome, line), or say why not.

    The provider writes references like ``matchResult.homeWinProbability`` or
    ``totalGoals.under2_5``. A reference without a market prefix (``awayWinProbability`` has been
    seen) is ambiguous between the match result and the first-half result and is NOT guessed.
    """
    if not isinstance(token, str) or not token.strip():
        return None, "empty or not a text reference"
    text = token.strip()
    if "." not in text:
        return None, "no market prefix; ambiguous between markets with the same outcome names"
    prefix, _, rest = text.partition(".")
    market_id = _TOKEN_MARKET.get(prefix)
    if market_id is None:
        return None, f"unknown market prefix '{prefix}'"
    if market_id in (TOTAL_GOALS, HOME_TEAM_GOALS, AWAY_TEAM_GOALS):
        found = _TOTALS_TOKEN.match(rest)
        if not found:
            return None, f"unreadable totals outcome '{rest}'"
        return (market_id, found.group(1).lower(), float(f"{found.group(2)}.{found.group(3)}")), None
    if market_id == EXACT_SCORE:
        found = _SCORE_TOKEN.match(rest)
        if not found:
            return None, f"unreadable scoreline '{rest}'"
        return (market_id, f"{found.group(1)}-{found.group(2)}", None), None
    outcome = _TOKEN_OUTCOME.get(rest.lower())
    if outcome is None:
        return None, f"unknown outcome '{rest}' for {market_id}"
    return (market_id, outcome, None), None


# ------------------------------------------------------------------------------ the builder
def build_markets(event: Dict[str, Any]) -> Dict[str, Any]:
    """Every market the stored event supports, validated, with derivations and provider odds.

    Pure: reads the payload and nothing else. The envelope around it (which fixture, which
    snapshot, when it was fetched, how fresh it is) is added by ``markets_for_forecast``.
    """
    forecast = parse_event(event) if isinstance(event, dict) else None
    prediction = latest_prediction(event) if isinstance(event, dict) else None
    anomalies = list(forecast.anomalies) if forecast is not None and forecast.anomalies else []

    markets: List[Market] = []
    if prediction is None:
        return {"markets": [], "recommended_bets": [], "provider_odds": None, "anomalies": anomalies,
                "reason": "the stored event carries no prediction entry"}

    result_values, result_invalid = _read_values(prediction.get("match_result"), ("home", "draw", "away"))
    result = _market(MATCH_RESULT, None, "match result", result_values, result_invalid)
    prices, odds_description = _provider_odds(event)
    for selection in result.selections:
        if selection.available and selection.outcome in prices:
            selection.odds = prices[selection.outcome]
    markets.append(result)
    markets.extend(_derived_from_1x2(result))

    totals = prediction.get("total_goals")
    for line in GOAL_LINES:
        markets.append(_totals_market(TOTAL_GOALS, "total goals over/under", totals, line))
    btts_values, btts_invalid = _read_values(prediction.get("both_teams_score"), ("yes", "no"))
    markets.append(_market(BOTH_TEAMS_SCORE, None, "both teams to score", btts_values, btts_invalid))

    fh_values, fh_invalid = _read_values(prediction.get("first_half_winner"), ("home", "draw", "away"))
    markets.append(_market(FIRST_HALF_RESULT, None, "first-half result", fh_values, fh_invalid))

    for market_id, key, label in ((HOME_TEAM_GOALS, "home_team_goals", "home team goals over/under"),
                                  (AWAY_TEAM_GOALS, "away_team_goals", "away team goals over/under")):
        block = prediction.get(key)
        for line in GOAL_LINES:
            markets.append(_totals_market(market_id, label, block, line))
    first_values, first_invalid = _read_values(prediction.get("team_to_score_first"), ("home", "away", "neither"))
    markets.append(_market(TEAM_TO_SCORE_FIRST, None, "team to score first", first_values, first_invalid))

    markets.append(_exact_score_market(forecast.exact_score if forecast else None,
                                       forecast.exact_score_other_prob if forecast else None,
                                       prediction.get("exact_score"), anomalies))

    by_key = {s.selection_id: s for m in markets for s in m.selections}
    recommended: List[Dict[str, Any]] = []
    raw_recommended = prediction.get("recommended_bets")
    if isinstance(raw_recommended, dict):
        for rank, token in sorted(raw_recommended.items(), key=lambda kv: str(kv[0])):
            resolved, why = resolve_recommended_bet(token)
            entry: Dict[str, Any] = {"rank": str(rank), "raw": token, "selection_id": None, "resolved": False, "reason": why}
            if resolved is not None:
                key = selection_key(*resolved)
                selection = by_key.get(key)
                if selection is None:
                    entry["reason"] = f"refers to {key}, which this build does not serve"
                elif not selection.available:
                    entry["reason"] = f"refers to {key}, which is not available: {selection.unavailable_reason}"
                else:
                    entry.update({"selection_id": key, "resolved": True, "reason": None})
            recommended.append(entry)

    return {
        "markets": [m.to_dict() for m in markets],
        "recommended_bets": recommended,
        "provider_odds": odds_description,
        "anomalies": anomalies,
        "reason": None,
    }


def group_markets(markets: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The served shape: markets under their groups, in the fixed order."""
    buckets: Dict[str, List[Dict[str, Any]]] = {group: [] for group in GROUP_ORDER}
    for market in markets:
        buckets.setdefault(market["group"], []).append(market)
    return [{"group": group, "markets": buckets[group]} for group in GROUP_ORDER]


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def markets_for_forecast(*, match_id: str, event: Dict[str, Any], provider: str, record_id: Optional[str],
                         snapshot_id: Optional[str], captured_before_kickoff: Optional[bool],
                         retrieved_at: Optional[datetime], model_run_at: Optional[datetime],
                         provider_updated_at: Optional[datetime], freshness: Optional[Dict[str, Any]],
                         now: Optional[datetime] = None) -> Dict[str, Any]:
    """The full envelope for one fixture's forecast, from the stored event."""
    now = now or datetime.now(timezone.utc)
    built = build_markets(event)
    return {
        "match_id": match_id,
        "provider": provider,
        "normalisation_version": NORMALISATION_VERSION,
        "built_at": _iso(now),
        "forecast": {
            "record_id": record_id,
            "snapshot_id": snapshot_id,
            "captured_before_kickoff": captured_before_kickoff,
            "retrieved_at": _iso(retrieved_at),
            "model_run_at": _iso(model_run_at),
            "provider_updated_at": _iso(provider_updated_at),
            "state": (freshness or {}).get("state"),
            "state_reason": (freshness or {}).get("reason"),
        },
        "groups": group_markets(built["markets"]),
        "recommended_bets": built["recommended_bets"],
        "provider_odds": built["provider_odds"],
        "anomalies": built["anomalies"],
        "reason": built["reason"],
    }


def no_forecast_envelope(match_id: str, freshness: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    return {
        "match_id": match_id, "provider": None, "normalisation_version": NORMALISATION_VERSION,
        "built_at": _iso(now),
        "forecast": {"record_id": None, "snapshot_id": None, "captured_before_kickoff": None, "retrieved_at": None,
                     "model_run_at": None, "provider_updated_at": None,
                     "state": (freshness or {}).get("state", "unavailable"),
                     "state_reason": (freshness or {}).get("reason", "no forecast for this match")},
        "groups": group_markets([]), "recommended_bets": [], "provider_odds": None, "anomalies": [],
        "reason": "no stored forecast for this fixture",
    }


def find_selection(envelope: Dict[str, Any], selection_id: str) -> Optional[Dict[str, Any]]:
    for group in envelope.get("groups", []):
        for market in group.get("markets", []):
            for selection in market.get("selections", []):
                if selection.get("selection_id") == selection_id:
                    return selection
    return None


def available_selections(envelope: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [s for group in envelope.get("groups", []) for market in group.get("markets", [])
            for s in market.get("selections", []) if s.get("available")]


# ------------------------------------------------------------------------------ capability matrix
#: What this installation can and cannot serve, market family by market family. The document
#: version with the research behind it is docs/markets-capability-matrix.md; this is the machine
#: form the API serves so the page can say what is missing without listing it as an option.
CAPABILITIES: List[Dict[str, Any]] = [
    {"family": "match_result", "markets": [MATCH_RESULT], "status": "served",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "predictions[].match_result.{home,draw,away}",
     "settlement": "regulation-time score", "cost": "included"},
    {"family": "double_chance", "markets": [DOUBLE_CHANCE], "status": "calculated",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "calculated from match_result (sum of two outcomes)",
     "settlement": "regulation-time score", "cost": "included"},
    {"family": "draw_no_bet", "markets": [DRAW_NO_BET], "status": "calculated",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "calculated from match_result (conditioned on no draw)",
     "settlement": "regulation-time score; void on a draw", "cost": "included"},
    {"family": "total_goals", "markets": [TOTAL_GOALS], "status": "served",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "predictions[].total_goals.{over,under}_{0_5,1_5,2_5,3_5}",
     "settlement": "regulation-time score", "cost": "included"},
    {"family": "team_goals", "markets": [HOME_TEAM_GOALS, AWAY_TEAM_GOALS], "status": "served",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "predictions[].{home,away}_team_goals.{over,under}_{0_5..3_5}",
     "settlement": "regulation-time score", "cost": "included"},
    {"family": "both_teams_score", "markets": [BOTH_TEAMS_SCORE], "status": "served",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "predictions[].both_teams_score.{yes,no}",
     "settlement": "regulation-time score", "cost": "included"},
    {"family": "first_half_result", "markets": [FIRST_HALF_RESULT], "status": "served",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "predictions[].first_half_winner.{home,draw,away}",
     "settlement": "stored half-time score; unresolved when none is stored", "cost": "included"},
    {"family": "team_to_score_first", "markets": [TEAM_TO_SCORE_FIRST], "status": "served_not_tracked",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "predictions[].team_to_score_first.{home,away,neither}",
     "settlement": "needs the order of goals, which no configured source records; only 'neither' on a 0-0 settles",
     "cost": "included"},
    {"family": "exact_score", "markets": [EXACT_SCORE], "status": "served",
     "provider": PROVIDER_GAMEFORECAST, "payload_field": "predictions[].exact_score (listed scorelines; 'other' is a remainder, never a selection)",
     "settlement": "regulation-time score", "cost": "included"},
    {"family": "half_time_full_time", "markets": [], "status": "unavailable",
     "provider": None, "payload_field": None,
     "settlement": "would need a half-time and a regulation-time score (both stored here)",
     "reason": "no configured source publishes a joint half-time/full-time probability; it is not derived by "
               "multiplying the first-half and full-time markets, which are not independent"},
    {"family": "clean_sheet", "markets": [], "status": "unavailable", "provider": None, "payload_field": None,
     "settlement": "regulation-time score", "reason": "not published; a team's under 0.5 goals is the same event and IS served under team_goals"},
    {"family": "corners_cards_shots", "markets": [], "status": "unavailable", "provider": None, "payload_field": None,
     "settlement": "would need corner/card/shot counts per fixture (match_results holds corner and card columns, unfilled by the active provider)",
     "reason": "no configured prediction source publishes them and no result source fills them; not invented from unrelated statistics"},
    {"family": "fouls_penalties_players", "markets": [], "status": "unavailable", "provider": None, "payload_field": None,
     "settlement": "would need event-level result data", "reason": "no configured source; see docs/markets-capability-matrix.md for paid options left to the owner"},
]
