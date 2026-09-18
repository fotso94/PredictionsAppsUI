"""
Public match endpoints backed by the configured match-data provider (Live Score API by default)
and the configured forecast provider (GameForecastAPI by default). Expert predictions are always
returned separately from provider forecasts.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.predictions import Match, Prediction, PredictionStatus
from app.models.provider_data import ProviderEntityRef
from app.schemas.matches import serialize_expert_prediction, serialize_forecast, serialize_match
from app.services.forecast_service import ForecastService
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.providers.base import ProviderError

logger = logging.getLogger(__name__)
router = APIRouter()


def _published_predictions(db: Session, match_ids: List[uuid.UUID]) -> Dict[uuid.UUID, Prediction]:
    """Highest-priority PUBLISHED expert prediction per match."""
    if not match_ids:
        return {}
    rows = db.query(Prediction).filter(
        Prediction.match_id.in_(match_ids), Prediction.status == PredictionStatus.PUBLISHED,
        Prediction.deleted_at.is_(None)).order_by(Prediction.priority_level.desc(), Prediction.published_at.desc()).all()
    best: Dict[uuid.UUID, Prediction] = {}
    for p in rows:
        best.setdefault(p.match_id, p)
    return best


def _league_refs(db: Session, league_ids) -> Dict:
    refs = db.query(ProviderEntityRef).filter(ProviderEntityRef.entity_type == "league",
                                              ProviderEntityRef.entity_id.in_(list(league_ids))).all() if league_ids else []
    grouped: Dict = {}
    for r in refs:
        grouped.setdefault(r.entity_id, []).append(r)
    return grouped


def build_match_payloads(db: Session, matches: List[Match], service: MatchDataService, forecasts: ForecastService) -> List[Dict[str, Any]]:
    teams = service.registry.team_names(matches)
    leagues = service.registry.leagues_by_id(matches)
    league_refs = _league_refs(db, leagues.keys())
    experts = _published_predictions(db, [m.id for m in matches])
    payloads = []
    for match in matches:
        record = forecasts.forecast_for_match(match)
        freshness = forecasts.freshness(record, match)
        payloads.append(serialize_match(match, teams, leagues, serialize_forecast(record, freshness),
                                        serialize_expert_prediction(experts.get(match.id)), league_refs))
    return payloads


def _response(day: Optional[date], meta: SyncMeta, payloads: List[Dict[str, Any]], forecast_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"date": day.isoformat() if day else None, "provider": meta.provider, "source": meta.source, "stale": meta.stale,
            "fetched_at": meta.fetched_at, "errors": meta.errors, "forecast_sync": forecast_report, "matches": payloads}


@router.get("", summary="Matches for a UTC date (covered competitions)")
@router.get("/", include_in_schema=False)
async def list_matches(
    date_str: Optional[str] = Query(None, alias="date", description="UTC date YYYY-MM-DD (default: today)"),
    refresh: bool = Query(True, description="Refresh from the provider (cache and budget aware)"),
    db: Session = Depends(get_db),
):
    try:
        day = date.fromisoformat(date_str) if date_str else datetime.now(timezone.utc).date()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date must be YYYY-MM-DD")
    service = MatchDataService(db)
    forecasts = ForecastService(db)
    try:
        matches, meta = service.matches_for_day(day, refresh=refresh)
    except ProviderError as exc:  # no provider, no cache, no database rows worth returning
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    forecast_report = None
    if refresh and matches:
        try:
            forecast_report = forecasts.ensure_synced()
        except Exception as exc:  # forecasts must never break the fixtures list
            logger.warning("forecast sync failed: %s", exc)
            forecast_report = {"error": str(exc)}
    payloads = build_match_payloads(db, matches, service, forecasts)
    if not payloads and meta.errors and meta.source == "database":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"message": "Match data is temporarily unavailable", "errors": meta.errors})
    return _response(day, meta, payloads, forecast_report)


@router.get("/live", summary="Matches currently in play (covered competitions)")
async def live_matches(db: Session = Depends(get_db)):
    service = MatchDataService(db)
    forecasts = ForecastService(db)
    matches, meta = service.live_matches()
    return _response(datetime.now(timezone.utc).date(), meta, build_match_payloads(db, matches, service, forecasts))


@router.get("/{match_id}", summary="Match detail with expert prediction and provider forecast")
async def match_detail(match_id: str, db: Session = Depends(get_db)):
    service = MatchDataService(db)
    forecasts = ForecastService(db)
    resolved = service.registry.resolve_match_id(match_id)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    match = service.match_by_id(resolved)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    payload = build_match_payloads(db, [match], service, forecasts)[0]
    experts = db.query(Prediction).filter(Prediction.match_id == match.id, Prediction.status == PredictionStatus.PUBLISHED,
                                          Prediction.deleted_at.is_(None)).order_by(Prediction.priority_level.desc()).all()
    payload["expert_predictions"] = [serialize_expert_prediction(p) for p in experts]
    payload["provider_refs"] = [{"provider": r.provider, "external_id": r.external_id, "confidence": r.match_confidence, "matched_by": r.matched_by}
                                for r in service.registry.refs_for("match", match.id)]
    return payload
