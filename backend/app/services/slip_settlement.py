"""
Settling one selection against a stored result, and a slip against its legs.

The same rules the forecast scoring follows (app/services/settlement.py) decide every regulation-time
market here, through the same ``regulation_score``: a stored 90-minute score wins, a tie that went
past 90 minutes with no 90-minute score stored is withheld, and a plain stored score stands as the
regulation score. Extra time and shoot-outs settle nothing.

Every state is one of five and each means one thing:

    pending     the fixture has not finished (or has, and no result has reached us yet)
    won / lost  decided by the stored result under the market's own rule
    void        the selection cannot be decided by the rules and is treated as if never made: the
                fixture was cancelled or postponed, or draw-no-bet met a draw
    unresolved  the fixture finished but the data this market needs is not held - no regulation
                score can be read, no half-time score is stored, the order of goals is unknown.
                Nothing is guessed; the reason is written on the leg.

A slip's state follows its legs: any lost leg loses it; every non-void leg won (and at least one
of them) wins it; every leg void voids it; an unresolved leg with nothing lost leaves it
unresolved; otherwise it is pending. A void leg drops out of the combination and its price with it,
which is stated where the price is shown.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Tuple

from app.models.predictions import Match, MatchResult, MatchStatus
from app.models.slips import (
    STATE_LOST, STATE_PENDING, STATE_UNRESOLVED, STATE_VOID, STATE_WON, SelectionSlip, SelectionSlipLeg,
)
from app.services.markets import (
    AWAY_TEAM_GOALS, BOTH_TEAMS_SCORE, DOUBLE_CHANCE, DRAW_NO_BET, EXACT_SCORE, FIRST_HALF_RESULT,
    HOME_TEAM_GOALS, MATCH_RESULT, TEAM_TO_SCORE_FIRST, TOTAL_GOALS,
)
from app.services.settlement import RegulationScore, regulation_score

RULES_VERSION = "slip-settlement.v1"


def _entry(state: str, rule: str, basis: str, **extra: Any) -> Dict[str, Any]:
    body = {"state": state, "rule": rule, "basis": basis, "rules_version": RULES_VERSION}
    body.update(extra)
    return body


def _totals(outcome: str, line: float, goals: int) -> str:
    if outcome == "over":
        return STATE_WON if goals > line else STATE_LOST
    if outcome == "under":
        return STATE_WON if goals < line else STATE_LOST
    return STATE_UNRESOLVED


def settle_selection(market_id: str, outcome: str, line: Optional[float], match_status: MatchStatus,
                     result: Optional[MatchResult]) -> Dict[str, Any]:
    """The state of one selection, with the rule and the evidence that decided it."""
    if match_status in (MatchStatus.CANCELLED, MatchStatus.POSTPONED):
        return _entry(STATE_VOID, "a fixture never played to a result voids every selection on it", "fixture",
                      reason=f"the fixture is {match_status.value}")
    if match_status != MatchStatus.FINISHED:
        return _entry(STATE_PENDING, "the fixture has not finished", "fixture")

    if market_id == FIRST_HALF_RESULT:
        if result is None or result.home_score_ht is None or result.away_score_ht is None:
            return _entry(STATE_UNRESOLVED, "settles on the stored half-time score only", "half_time",
                          reason="no half-time score is stored for this fixture; nothing is inferred from the final score")
        half = RegulationScore(int(result.home_score_ht), int(result.away_score_ht))
        return _entry(STATE_WON if half.outcome == outcome else STATE_LOST, "settles on the stored half-time score",
                      "half_time", actual=half.label, actual_outcome=half.outcome)

    score, withheld = regulation_score(result)
    if score is None:
        return _entry(STATE_UNRESOLVED, "settles on the regulation-time score only", "regulation_time", reason=withheld)

    evidence = {"actual": score.label, "actual_outcome": score.outcome}
    if market_id == MATCH_RESULT:
        return _entry(STATE_WON if score.outcome == outcome else STATE_LOST, "regulation-time result", "regulation_time", **evidence)
    if market_id == DOUBLE_CHANCE:
        covered = {"1x": ("home", "draw"), "12": ("home", "away"), "x2": ("draw", "away")}.get(outcome, ())
        return _entry(STATE_WON if score.outcome in covered else STATE_LOST,
                      "regulation-time result; either covered outcome wins", "regulation_time", **evidence)
    if market_id == DRAW_NO_BET:
        if score.outcome == "draw":
            return _entry(STATE_VOID, "a draw after 90 minutes voids draw-no-bet", "regulation_time", **evidence)
        return _entry(STATE_WON if score.outcome == outcome else STATE_LOST, "regulation-time result, draw void", "regulation_time", **evidence)
    if market_id == TOTAL_GOALS and line is not None:
        return _entry(_totals(outcome, line, score.total), f"regulation-time goals against the {line:g} line",
                      "regulation_time", goals=score.total, **evidence)
    if market_id == HOME_TEAM_GOALS and line is not None:
        return _entry(_totals(outcome, line, score.home), f"home team's regulation-time goals against the {line:g} line",
                      "regulation_time", goals=score.home, **evidence)
    if market_id == AWAY_TEAM_GOALS and line is not None:
        return _entry(_totals(outcome, line, score.away), f"away team's regulation-time goals against the {line:g} line",
                      "regulation_time", goals=score.away, **evidence)
    if market_id == BOTH_TEAMS_SCORE:
        happened = "yes" if score.both_scored else "no"
        return _entry(STATE_WON if outcome == happened else STATE_LOST, "both teams scored in regulation time", "regulation_time",
                      both_scored=score.both_scored, **evidence)
    if market_id == EXACT_SCORE:
        return _entry(STATE_WON if score.label == outcome else STATE_LOST, "regulation-time scoreline", "regulation_time", **evidence)
    if market_id == TEAM_TO_SCORE_FIRST:
        if score.total == 0:
            return _entry(STATE_WON if outcome == "neither" else STATE_LOST,
                          "nobody scored in regulation time, which decides 'neither' without the order of goals",
                          "regulation_time", **evidence)
        return _entry(STATE_UNRESOLVED, "needs the order of goals", "event_order",
                      reason="no configured result source records which team scored first; this selection is not tracked automatically",
                      **evidence)
    return _entry(STATE_UNRESOLVED, "no settlement rule for this market", "none",
                  reason=f"this build has no rule for {market_id}")


def slip_state(states: Iterable[str]) -> str:
    states = list(states)
    if not states:
        return STATE_PENDING
    if STATE_LOST in states:
        return STATE_LOST
    if all(s == STATE_VOID for s in states):
        return STATE_VOID
    if STATE_PENDING in states:
        return STATE_PENDING
    if STATE_UNRESOLVED in states:
        return STATE_UNRESOLVED
    decided = [s for s in states if s != STATE_VOID]
    return STATE_WON if decided and all(s == STATE_WON for s in decided) else STATE_PENDING


def settle_leg(leg: SelectionSlipLeg, match: Match, result: Optional[MatchResult], now: datetime) -> bool:
    """Apply the rule to one leg. Returns True when the stored state changed. Final states are never reopened."""
    if leg.state in (STATE_WON, STATE_LOST, STATE_VOID):
        return False
    line = float(leg.line) if leg.line is not None else None
    outcome = settle_selection(leg.market_id, leg.outcome, line, match.status, result)
    state = outcome["state"]
    changed = state != leg.state or (leg.settlement or {}).get("reason") != outcome.get("reason")
    leg.state = state
    leg.settlement = outcome
    if state in (STATE_WON, STATE_LOST, STATE_VOID):
        leg.settled_at = now.replace(tzinfo=None) if now.tzinfo else now
    return changed


def settle_slip(slip: SelectionSlip, matches: Dict[Any, Match], now: Optional[datetime] = None) -> bool:
    """Settle every leg of a slip from the stored fixtures, then the slip. Idempotent."""
    now = now or datetime.now(timezone.utc)
    changed = False
    for leg in slip.legs:
        match = matches.get(leg.match_id)
        if match is None:
            continue
        changed = settle_leg(leg, match, match.result, now) or changed
    state = slip_state(leg.state for leg in slip.legs)
    if state != slip.state:
        slip.state = state
        changed = True
    final = slip.legs and all(leg.state in (STATE_WON, STATE_LOST, STATE_VOID) for leg in slip.legs)
    if final and slip.settled_at is None:
        slip.settled_at = now.replace(tzinfo=None) if now.tzinfo else now
        changed = True
    return changed


def effective_price(legs: Iterable[SelectionSlipLeg]) -> Tuple[Optional[Decimal], Optional[str], int]:
    """The combined decimal price of the non-void legs, its source, and how many legs carry no price.

    Only computed when EVERY non-void leg carries a price for exactly its selection. A missing price
    is a missing price: nothing is invented for it, and the count says how many are missing.
    """
    total = Decimal(1)
    sources = set()
    missing = 0
    counted = 0
    for leg in legs:
        if leg.state == STATE_VOID:
            continue
        if leg.odds_value is None:
            missing += 1
            continue
        total *= Decimal(leg.odds_value)
        sources.add(leg.odds_source or "user")
        counted += 1
    if missing or counted == 0:
        return None, None, missing
    source = sources.pop() if len(sources) == 1 else "mixed"
    return total.quantize(Decimal("0.0001")), source, 0
