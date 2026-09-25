"""
Suggested combinations, built deterministically from forecasts already stored.

WHAT THIS IS. A ranking, not a model. Every fixture in the window is reduced to its single
best-supported selection among the allowed markets - the one the provider gives the highest
probability, ties broken by a fixed market order - fixtures are ranked by that probability, and
combinations are cut from the ranking in disjoint blocks. The same stored data and the same
arguments always produce the same combinations; ``rules`` in the response is the complete
configuration that produced them.

WHAT IT REFUSES TO DO.
* Call the prediction provider. It reads ``provider_forecasts`` and nothing else.
* Pad a combination. Asked for four legs with three qualifying fixtures, it returns three and says
  why the fourth is missing.
* Present near-duplicates as alternatives. Combinations share no fixture, so the second one is a
  genuinely different set, not the first with one leg swapped.
* Call anything safe. A combined probability, when shown, is the product of the legs' published
  probabilities under an INDEPENDENCE assumption between different matches - an approximation the
  response labels as such, never a calibrated prediction.
* Price anything. A combined price appears only when every leg carries a provider price for exactly
  its selection, which today is only the 1X2 market.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.predictions import Match, MatchStatus
from app.schemas.matches import serialize_league, serialize_team
from app.services.forecast_markets import envelopes_for_matches
from app.services.forecast_service import ForecastService
from app.services.markets import (
    AWAY_TEAM_GOALS, BOTH_TEAMS_SCORE, DOUBLE_CHANCE, DRAW_NO_BET, FIRST_HALF_RESULT,
    HOME_TEAM_GOALS, MARKET_GROUP, MARKET_PRIORITY, MATCH_RESULT, TOTAL_GOALS,
)
from app.services.match_registry import MatchRegistry

RULES_VERSION = "suggestions.v1"

#: The markets a suggestion may draw from unless the caller narrows them. Exact score and team to
#: score first are left out by default: the first is a long shot by construction and the second
#: cannot be tracked automatically, so neither belongs in an unrequested suggestion.
DEFAULT_MARKETS: Tuple[str, ...] = (MATCH_RESULT, DOUBLE_CHANCE, DRAW_NO_BET, TOTAL_GOALS, BOTH_TEAMS_SCORE,
                                    HOME_TEAM_GOALS, AWAY_TEAM_GOALS, FIRST_HALF_RESULT)
ALL_MARKETS: Tuple[str, ...] = tuple(MARKET_PRIORITY)

DEFAULT_LEGS = 3
MIN_LEGS = 2
MAX_LEGS = 6
DEFAULT_MIN_PROBABILITY = 0.60
#: A published probability at or above this carries no information a combination can use - the
#: provider is saying the outcome is all but certain (San Marino conceding under 3.5 at home, say) -
#: so such selections are left out unless the caller raises the ceiling. Counted, never hidden.
DEFAULT_MAX_PROBABILITY = 0.95
DEFAULT_MAX_COMBINATIONS = 3
DEFAULT_DAYS_AHEAD = 7
MAX_DAYS_AHEAD = 30

INDEPENDENCE_NOTE = ("the product of the legs' published probabilities, assuming the matches are independent "
                     "of each other; an approximation for orientation, not a calibrated prediction")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return _aware(dt).isoformat().replace("+00:00", "Z") if dt else None


def _candidate(envelope: Dict[str, Any], markets: Sequence[str], settleable_only: bool,
               odds_range: Optional[Tuple[Optional[float], Optional[float]]],
               max_probability: float = DEFAULT_MAX_PROBABILITY) -> Tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    """The one selection this fixture contributes, or why it contributes none, and whether the ceiling removed anything."""
    priority = {m: i for i, m in enumerate(MARKET_PRIORITY)}
    best: Optional[Dict[str, Any]] = None
    best_key: Optional[Tuple[float, int, int]] = None
    seen_any = False
    odds_excluded = False
    above_ceiling = False
    order = 0
    for group in envelope.get("groups", []):
        for market in group.get("markets", []):
            if market["market_id"] not in markets:
                continue
            for selection in market.get("selections", []):
                order += 1
                if not selection.get("available") or selection.get("probability") is None:
                    continue
                seen_any = True
                if settleable_only and not selection["settlement"].get("capable"):
                    continue
                if float(selection["probability"]) > max_probability:
                    above_ceiling = True
                    continue
                if odds_range is not None:
                    price = (selection.get("odds") or {}).get("value")
                    low, high = odds_range
                    if price is None or (low is not None and price < low) or (high is not None and price > high):
                        odds_excluded = True
                        continue
                key = (-float(selection["probability"]), priority.get(market["market_id"], 99), order)
                if best_key is None or key < best_key:
                    best, best_key = dict(selection, market_warnings=list(market.get("warnings", []))), key
    if best is not None:
        return best, None, above_ceiling
    if not seen_any:
        return None, "no_available_market", above_ceiling
    if odds_excluded:
        return None, "odds_filter", above_ceiling
    if above_ceiling:
        return None, "above_ceiling", above_ceiling
    return None, "no_settleable_market", above_ceiling


def suggest(db: Session, *, now: Optional[datetime] = None, legs: int = DEFAULT_LEGS,
            min_probability: float = DEFAULT_MIN_PROBABILITY, markets: Optional[Sequence[str]] = None,
            competition_ids: Optional[Sequence[uuid.UUID]] = None, kickoff_from: Optional[datetime] = None,
            kickoff_to: Optional[datetime] = None, odds_min: Optional[float] = None, odds_max: Optional[float] = None,
            max_combinations: int = DEFAULT_MAX_COMBINATIONS, include_stale: bool = False,
            settleable_only: bool = True, max_probability: float = DEFAULT_MAX_PROBABILITY) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    legs = max(MIN_LEGS, min(MAX_LEGS, int(legs)))
    max_combinations = max(1, min(10, int(max_combinations)))
    min_probability = max(0.0, min(1.0, float(min_probability)))
    max_probability = max(min_probability, min(1.0, float(max_probability)))
    allowed = tuple(m for m in (markets or DEFAULT_MARKETS) if m in MARKET_GROUP) or DEFAULT_MARKETS
    start = _aware(kickoff_from) if kickoff_from else now
    end = _aware(kickoff_to) if kickoff_to else now + timedelta(days=DEFAULT_DAYS_AHEAD)
    start = max(start, now)  # nothing that has kicked off is ever suggested
    end = min(end, now + timedelta(days=MAX_DAYS_AHEAD))
    odds_range = (odds_min, odds_max) if odds_min is not None or odds_max is not None else None

    query = db.query(Match).filter(Match.status == MatchStatus.SCHEDULED,
                                   Match.match_date > start.replace(tzinfo=None),
                                   Match.match_date <= end.replace(tzinfo=None))
    if competition_ids:
        query = query.filter(Match.league_id.in_(list(competition_ids)))
    fixtures = query.order_by(Match.match_date.asc(), Match.id.asc()).all()

    forecasts = ForecastService(db)
    envelopes = envelopes_for_matches(db, fixtures, forecasts, now=now)
    registry = MatchRegistry(db)
    teams = registry.team_names(fixtures)
    leagues = registry.leagues_by_id(fixtures)

    excluded = {"no_forecast": 0, "stale": 0, "kickoff_passed": 0, "no_available_market": 0,
                "no_settleable_market": 0, "odds_filter": 0, "above_ceiling": 0, "below_threshold": 0}
    ranked: List[Dict[str, Any]] = []
    for match in fixtures:
        envelope = envelopes[match.id]
        state = envelope["forecast"].get("state")
        if envelope.get("reason") or state == "unavailable":
            excluded["no_forecast"] += 1
            continue
        if state == "kickoff_passed":
            excluded["kickoff_passed"] += 1
            continue
        if state == "stale" and not include_stale:
            excluded["stale"] += 1
            continue
        selection, why, ceiling_hit = _candidate(envelope, allowed, settleable_only, odds_range, max_probability)
        if selection is None:
            excluded[why or "no_available_market"] += 1
            continue
        if float(selection["probability"]) < min_probability:
            # A fixture whose only strong selection was a near-certainty is reported as such, not as weak.
            excluded["above_ceiling" if ceiling_hit else "below_threshold"] += 1
            continue
        kickoff = _aware(match.match_date)
        model_run = envelope["forecast"].get("model_run_at")
        retrieved = envelope["forecast"].get("retrieved_at")
        basis = model_run or retrieved
        age_hours = None
        if basis:
            age_hours = round((now - datetime.fromisoformat(basis.replace("Z", "+00:00"))).total_seconds() / 3600, 1)
        ranked.append({
            "match": {
                "id": str(match.id),
                "home": serialize_team(teams.get(match.home_team_id)),
                "away": serialize_team(teams.get(match.away_team_id)),
                "competition": serialize_league(leagues.get(match.league_id)),
                "kickoff_utc": _iso(match.match_date),
                "status": match.status.value if hasattr(match.status, "value") else str(match.status),
            },
            "selection": {k: v for k, v in selection.items() if k != "market_warnings"},
            "why": {
                "probability": float(selection["probability"]),
                "probability_source": selection["probability_source"],
                "threshold": min_probability, "ceiling": max_probability,
                "forecast": {"provider": envelope["provider"], "snapshot_id": envelope["forecast"]["snapshot_id"],
                             "model_run_at": model_run, "retrieved_at": retrieved, "state": state,
                             "age_hours": age_hours, "captured_before_kickoff": envelope["forecast"]["captured_before_kickoff"]},
                "warnings": [w for w in (selection.get("warnings", []) + selection.get("market_warnings", [])
                                         + envelope.get("anomalies", [])) if w.get("severity") == "warning"],
                "settlement": selection["settlement"],
                "provider_odds": selection.get("odds"),
            },
            "_sort": (-float(selection["probability"]), kickoff, str(match.id)),
        })
    ranked.sort(key=lambda r: r["_sort"])
    for rank, row in enumerate(ranked, start=1):
        row["why"]["rank"] = rank
        row.pop("_sort", None)

    combinations: List[Dict[str, Any]] = []
    shortfall: Optional[str] = None
    if not ranked:
        shortfall = "no fixture in the window has a selection at or above the requested probability"
    else:
        blocks = [ranked[i * legs:(i + 1) * legs] for i in range(max_combinations)]
        full = [b for b in blocks if len(b) == legs]
        if full:
            chosen = full
        else:
            chosen = [ranked[:legs]]
            shortfall = (f"only {len(ranked)} fixture{'s' if len(ranked) != 1 else ''} qualif"
                         f"{'y' if len(ranked) != 1 else 'ies'} for {legs} legs; the combination below is shorter than asked")
        for index, block in enumerate(chosen, start=1):
            combinations.append(_combination(index, block))
        if full and len(full) < max_combinations and len(ranked) >= legs:
            leftover = len(ranked) - len(full) * legs
            if leftover:
                shortfall = (f"{len(full)} full combination{'s' if len(full) != 1 else ''}; {leftover} further "
                             f"qualifying fixture{'s' if leftover != 1 else ''} could not make another set of {legs}")

    return {
        "generated_at": _iso(now),
        "rules": {
            "version": RULES_VERSION, "legs": legs, "min_probability": min_probability, "max_probability": max_probability,
            "markets": list(allowed),
            "max_combinations": max_combinations, "include_stale": include_stale, "settleable_only": settleable_only,
            "kickoff_from": _iso(start), "kickoff_to": _iso(end), "odds_min": odds_min, "odds_max": odds_max,
            "competition_ids": [str(c) for c in (competition_ids or [])],
            "selection_rule": "one selection per fixture: the highest published probability at or below the ceiling among the allowed markets, "
                              "ties broken by market order; fixtures ranked by that probability, earlier kickoff first on "
                              "equal probability; combinations cut from the ranking in disjoint blocks",
            "combined_probability": INDEPENDENCE_NOTE,
            "source": "stored provider forecasts only; no provider request is made by this service",
        },
        "pool": {"fixtures_in_window": len(fixtures), "qualifying": len(ranked), "excluded": excluded},
        "combinations": combinations,
        "shortfall": shortfall,
    }


DNB_WITHHELD = ("withheld: a draw-no-bet selection's probability is conditional on there being no draw, and "
                "conditional and unconditional probabilities cannot be multiplied into one figure; the legs' own "
                "probabilities are shown instead")


def _combination(index: int, block: List[Dict[str, Any]]) -> Dict[str, Any]:
    if any(leg["selection"]["market_id"] == DRAW_NO_BET for leg in block):
        combined: Dict[str, Any] = {"value": None, "basis": DNB_WITHHELD}
    else:
        product = Decimal(1)
        for leg in block:
            product *= Decimal(str(leg["why"]["probability"]))
        combined = {"value": float(product.quantize(Decimal("0.000001"))), "basis": INDEPENDENCE_NOTE}
    prices = [leg["why"].get("provider_odds") for leg in block]
    combined_odds = None
    if block and all(p and p.get("value") for p in prices):
        total = Decimal(1)
        for p in prices:
            total *= Decimal(str(p["value"]))
        combined_odds = {"value": float(total.quantize(Decimal("0.0001"))), "format": "decimal",
                         "source": "provider_snapshot", "note": "product of the provider's own 1X2 prices; the bookmaker is not named"}
    return {
        "index": index,
        "legs": block,
        "combined_probability": combined,
        "combined_odds": combined_odds,
    }
