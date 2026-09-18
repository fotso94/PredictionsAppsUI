"""Team search and team pages, served from the internal registry."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.v1.endpoints.matches import _league_refs, build_match_payloads
from app.db.session import get_db
from app.models.predictions import League, Match, Team
from app.schemas.matches import serialize_league, serialize_team
from app.services.forecast_service import ForecastService
from app.services.match_data_service import MatchDataService

router = APIRouter()


@router.get("/search", summary="Search teams and competitions by name")
async def search(q: str = Query(..., min_length=2, max_length=80), limit: int = Query(10, ge=1, le=25), db: Session = Depends(get_db)):
    pattern = f"%{q.strip()}%"
    teams = db.query(Team).filter(Team.name.ilike(pattern), Team.is_active.is_(True)).order_by(Team.name.asc()).limit(limit).all()
    leagues = db.query(League).filter(or_(League.name.ilike(pattern), League.display_name.ilike(pattern)),
                                      League.external_api_source == "canonical").limit(limit).all()
    refs = _league_refs(db, [l.id for l in leagues])
    return {"query": q, "teams": [serialize_team(t) for t in teams], "competitions": [serialize_league(l, refs.get(l.id)) for l in leagues]}


@router.get("/{team_id}", summary="Team with upcoming and recent matches")
async def team_detail(team_id: str, db: Session = Depends(get_db)):
    try:
        team_uuid = uuid.UUID(team_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    team = db.query(Team).filter(Team.id == team_uuid).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    service = MatchDataService(db)
    forecasts = ForecastService(db)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    base = db.query(Match).filter(or_(Match.home_team_id == team.id, Match.away_team_id == team.id))
    upcoming = base.filter(Match.match_date >= now - timedelta(hours=3)).order_by(Match.match_date.asc()).limit(10).all()
    recent = base.filter(Match.match_date < now - timedelta(hours=3)).order_by(Match.match_date.desc()).limit(10).all()
    return {"team": serialize_team(team),
            "upcoming": build_match_payloads(db, upcoming, service, forecasts),
            "recent": build_match_payloads(db, recent, service, forecasts)}
