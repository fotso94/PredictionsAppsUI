"""Provider status and manual synchronisation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user
from app.db.session import get_db
from app.models.users import User
from app.services.forecast_service import ForecastService
from app.services.match_data_service import MatchDataService

router = APIRouter()


@router.get("/status", summary="Active data/prediction providers, budgets and last errors")
async def provider_status(db: Session = Depends(get_db)):
    data = MatchDataService(db).provider_status()
    data["forecasts"] = ForecastService(db).status()
    data["checked_at"] = datetime.now(timezone.utc).isoformat()
    return data


@router.post("/sync", summary="Force a synchronisation (admin)")
async def force_sync(days: int = Query(2, ge=1, le=7), forecasts: bool = Query(True),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    service = MatchDataService(db)
    today = datetime.now(timezone.utc).date()
    report = {"days": {}}
    for offset in range(days):
        day = today + timedelta(days=offset)
        report["days"][day.isoformat()] = service.sync_day(day).to_dict()
    if forecasts:
        report["forecasts"] = ForecastService(db).ensure_synced(force=True)
    return report
