"""
Suggested combinations and the market capability matrix. Stored data only; never a provider call.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.services.markets import CAPABILITIES, MARKET_GROUP, NORMALISATION_VERSION
from app.services.suggestions import (
    DEFAULT_LEGS, DEFAULT_MAX_COMBINATIONS, DEFAULT_MAX_PROBABILITY, DEFAULT_MIN_PROBABILITY, MAX_LEGS, MIN_LEGS, suggest,
)

router = APIRouter()


def _parse_when(value: Optional[str], name: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{name} is not an ISO-8601 instant")


@router.get("", summary="Deterministic suggested combinations from stored forecasts (no provider request)")
async def suggestions(
    legs: int = Query(default=DEFAULT_LEGS, ge=MIN_LEGS, le=MAX_LEGS),
    min_probability: float = Query(default=DEFAULT_MIN_PROBABILITY, ge=0.0, le=1.0),
    max_probability: float = Query(default=DEFAULT_MAX_PROBABILITY, ge=0.0, le=1.0,
                                   description="Selections published above this are left out (near-certainties carry no information)"),
    markets: Optional[str] = Query(default=None, description="Comma-separated market ids; default excludes exact score and team to score first"),
    competitions: Optional[str] = Query(default=None, description="Comma-separated competition UUIDs"),
    kickoff_from: Optional[str] = Query(default=None, alias="from"),
    kickoff_to: Optional[str] = Query(default=None, alias="to"),
    odds_min: Optional[float] = Query(default=None, gt=1.0),
    odds_max: Optional[float] = Query(default=None, gt=1.0),
    max_combinations: int = Query(default=DEFAULT_MAX_COMBINATIONS, ge=1, le=10),
    include_stale: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    market_ids: Optional[List[str]] = None
    if markets:
        market_ids = [m.strip() for m in markets.split(",") if m.strip()]
        unknown = [m for m in market_ids if m not in MARKET_GROUP]
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown market id(s): {', '.join(unknown)}")
    competition_ids: Optional[List[uuid.UUID]] = None
    if competitions:
        competition_ids = []
        for raw in competitions.split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                competition_ids.append(uuid.UUID(raw))
            except ValueError:
                raise HTTPException(status_code=422, detail=f"'{raw}' is not a competition id")
    if odds_min is not None and odds_max is not None and odds_min > odds_max:
        raise HTTPException(status_code=422, detail="odds_min is above odds_max")
    if max_probability < min_probability:
        raise HTTPException(status_code=422, detail="max_probability is below min_probability")
    return suggest(db, legs=legs, min_probability=min_probability, max_probability=max_probability, markets=market_ids, competition_ids=competition_ids,
                   kickoff_from=_parse_when(kickoff_from, "from"), kickoff_to=_parse_when(kickoff_to, "to"),
                   odds_min=odds_min, odds_max=odds_max, max_combinations=max_combinations, include_stale=include_stale)


@router.get("/capabilities", summary="Which market families this installation serves, calculates, or cannot")
async def capabilities():
    return {"normalisation_version": NORMALISATION_VERSION, "families": CAPABILITIES}
