"""Measured performance: what the sources actually got right, counted from settled results.

Every number here is computed from stored score rows by `app.services.settlement`. Nothing is
estimated, and a source with nothing scored says "not measured yet" with the reason rather than
showing a zero. An accuracy figure is never published without the sample it was computed from, its
definition and the rule that settled it, and it is withheld entirely below the minimum sample.

No provider request is made by any endpoint in this file.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user
from app.db.session import get_db
from app.models.users import User
from app.services import settlement as settlement_service

router = APIRouter()

MAX_WINDOW_DAYS = settlement_service.MAX_WINDOW_DAYS


def _validated_window(start: Optional[date], end: Optional[date]) -> Dict[str, date]:
    """Reject a window that cannot be answered honestly before doing any work."""
    today = datetime.now(timezone.utc).date()
    end_date = end or today
    start_date = start or (end_date - timedelta(days=settlement_service.DEFAULT_WINDOW_DAYS))
    if start_date > end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="start must not be after end")
    if (end_date - start_date).days + 1 > MAX_WINDOW_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"the window may not exceed {MAX_WINDOW_DAYS} days; ask for a shorter range")
    return {"start": start_date, "end": end_date}


@router.get("/rules", summary="The settlement rules every score on this installation was computed with")
async def rules() -> Dict[str, Any]:
    """The full ruleset, published on its own so a figure can always be checked against it."""
    return settlement_service.settlement_rules()


@router.get("/sources", summary="Measured performance per source, counted from settled results")
async def sources(
    start: Optional[date] = Query(None, description="First kickoff date to include (UTC). Defaults to 90 days back."),
    end: Optional[date] = Query(None, description="Last kickoff date to include (UTC). Defaults to today."),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Per source - each model provider and each expert - over a window of kickoffs.

    For every source: how many predictions were eligible, scored, still pending, void or refused,
    then per market the hit rate of the most likely outcome and a Brier score over the published
    probabilities. Both carry their sample size and their definition, and both are withheld with a
    stated reason below the minimum sample rather than shown from a handful of matches.
    """
    window = _validated_window(start, end)
    return settlement_service.measurement(db, start=window["start"], end=window["end"])


@router.post("/settle", summary="Score settled matches against the stored forecasts (admin)")
async def settle(
    start: Optional[date] = Query(None, description="First kickoff date to settle (UTC). Defaults to 90 days back."),
    end: Optional[date] = Query(None, description="Last kickoff date to settle (UTC). Defaults to today."),
    limit: Optional[int] = Query(None, ge=1, le=5000, description="Maximum matches to process in this run"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Run settlement over a window. Idempotent: re-running changes nothing already scored.

    Reads only stored data - stored fixtures, stored results, stored forecast snapshots - and makes
    no provider request, so it is safe to run as often as wanted.
    """
    window = _validated_window(start, end)
    start_dt, end_dt = settlement_service.window_bounds(window["start"], window["end"])
    report = settlement_service.SettlementService(db).settle_range(start=start_dt, end=end_dt, limit=limit)
    report["window"] = {"start": window["start"].isoformat(), "end": window["end"].isoformat(),
                        "basis": "kickoff date in UTC, both ends included"}
    report["settled_by"] = str(current_user.id)
    return report
