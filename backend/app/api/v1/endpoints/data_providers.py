"""Provider status and manual synchronisation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user
from app.db.session import get_db
from app.models.predictions import Match, MatchStatus, Prediction, PredictionStatus
from app.models.provider_data import ProviderForecastRecord, ProviderForecastSnapshot
from app.models.users import User
from app.services.forecast_service import ForecastService
from app.services.match_data_service import MatchDataService
from app.services.providers import competitions as comps
from app.core.config import settings

router = APIRouter()


@router.get("/status", summary="Active data/prediction providers, budgets and last errors")
async def provider_status(db: Session = Depends(get_db)):
    data = MatchDataService(db).provider_status()
    data["forecasts"] = ForecastService(db).status()
    data["checked_at"] = datetime.now(timezone.utc).isoformat()
    return data


@router.get("/coverage", summary="Measured coverage of the data actually held")
async def coverage(db: Session = Depends(get_db)):
    """Counts of what this installation actually holds right now.

    Every number is measured from the database. No accuracy, success-rate or user-count figure is
    published here: scoring a forecast needs settled results and a complete history, and neither
    exists yet. Anything unavailable is reported as such rather than estimated.
    """
    now = datetime.now(timezone.utc)
    keys = comps.covered_keys(settings.COVERED_COMPETITIONS)
    upcoming = (db.query(Match)
                .filter(Match.match_date >= now.replace(tzinfo=None),
                        Match.status.in_([MatchStatus.SCHEDULED, MatchStatus.LIVE]))
                .count())
    forecasts = db.query(ProviderForecastRecord).count()
    upcoming_with_forecast = (db.query(ProviderForecastRecord)
                              .join(Match, Match.id == ProviderForecastRecord.match_id)
                              .filter(Match.match_date >= now.replace(tzinfo=None))
                              .count())
    published = (db.query(Prediction)
                 .filter(Prediction.status == PredictionStatus.PUBLISHED)
                 .count())
    return {
        "competitions_covered": len(keys),
        "competition_keys": keys,
        "upcoming_matches": upcoming,
        "matches_stored": db.query(Match).count(),
        "model_forecasts": forecasts,
        "upcoming_matches_with_forecast": upcoming_with_forecast,
        "forecast_snapshots": db.query(ProviderForecastSnapshot).count(),
        "expert_predictions_published": published,
        # Deliberately absent: accuracy, success rate, active users. They would have to be invented.
        "accuracy_available": False,
        "accuracy_unavailable_reason": "no settled results have been scored yet",
        "measured_at": now.isoformat(),
    }


@router.post("/sync", summary="Force a synchronisation (admin)")
async def force_sync(days: int = Query(2, ge=1, le=7), forecasts: bool = Query(True),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    service = MatchDataService(db)
    service.clear_cooldowns()  # an admin-triggered sync retries providers even after recent failures
    today = datetime.now(timezone.utc).date()
    report = {"days": {}}
    for offset in range(days):
        day = today + timedelta(days=offset)
        report["days"][day.isoformat()] = service.sync_day(day).to_dict()
    if forecasts:
        forecast_service = ForecastService(db)
        forecast_service.clear_cooldown()
        report["forecasts"] = forecast_service.ensure_synced(force=True)
    return report
