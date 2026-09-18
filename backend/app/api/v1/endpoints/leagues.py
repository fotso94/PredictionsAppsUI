"""Covered competitions, standings and calendars."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.endpoints.matches import _league_refs, build_match_payloads
from app.db.session import get_db
from app.models.predictions import League, Team
from app.models.provider_data import ProviderEntityRef
from app.schemas.matches import serialize_league, serialize_standing
from app.services.forecast_service import ForecastService
from app.services.match_data_service import MatchDataService

router = APIRouter()


def _league_or_404(db: Session, league_id: str) -> League:
    try:
        league_uuid = uuid.UUID(league_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    league = db.query(League).filter(League.id == league_uuid).first()
    if not league:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return league


def _key(league: League) -> str:
    key = (league.league_metadata or {}).get("canonical_key")
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League is not a covered competition")
    return key


@router.get("", summary="Covered competitions")
@router.get("/", include_in_schema=False)
async def list_leagues(db: Session = Depends(get_db)):
    service = MatchDataService(db)
    leagues = service.competitions()
    refs = _league_refs(db, [l.id for l in leagues])
    return {"provider": service.primary_name, "competitions": [serialize_league(l, refs.get(l.id)) for l in leagues]}


@router.get("/{league_id}", summary="Competition")
async def get_league(league_id: str, db: Session = Depends(get_db)):
    league = _league_or_404(db, league_id)
    return serialize_league(league, _league_refs(db, [league.id]).get(league.id))


@router.get("/{league_id}/standings", summary="Competition standings")
async def league_standings(league_id: str, db: Session = Depends(get_db)):
    league = _league_or_404(db, league_id)
    key = _key(league)
    service = MatchDataService(db)
    rows, meta = service.standings(key)
    # map provider team ids to internal teams when known
    refs = db.query(ProviderEntityRef).filter(ProviderEntityRef.entity_type == "team",
                                              ProviderEntityRef.external_id.in_([r.team.external_id for r in rows])).all() if rows else []
    teams = {t.id: t for t in db.query(Team).filter(Team.id.in_([r.entity_id for r in refs])).all()} if refs else {}
    lookup = {r.external_id: teams.get(r.entity_id) for r in refs if r.provider == (meta.provider or "")}
    return {"league_id": str(league.id), "key": key, "provider": meta.provider, "source": meta.source, "stale": meta.stale,
            "errors": meta.errors, "standings": [serialize_standing(r, lookup) for r in rows]}


@router.get("/{league_id}/matches", summary="Upcoming and recent matches of a competition")
async def league_matches(league_id: str, days_ahead: int = Query(14, ge=1, le=60), days_back: int = Query(7, ge=0, le=60),
                         refresh: bool = Query(True), db: Session = Depends(get_db)):
    league = _league_or_404(db, league_id)
    key = _key(league)
    service = MatchDataService(db)
    forecasts = ForecastService(db)
    meta = service.sync_upcoming(key, days_ahead) if refresh else None
    now = datetime.now(timezone.utc)
    matches = service.registry.matches_between(now - timedelta(days=days_back), now + timedelta(days=days_ahead + 1), [league.id])
    return {"league_id": str(league.id), "key": key, "provider": meta.provider if meta else None, "source": meta.source if meta else "database",
            "stale": meta.stale if meta else False, "errors": meta.errors if meta else [],
            "matches": build_match_payloads(db, matches, service, forecasts)}
