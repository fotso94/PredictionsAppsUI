"""
Public match endpoints backed by the configured match-data provider (Live Score API by default)
and the configured forecast provider (GameForecastAPI by default). Expert predictions are always
returned separately from provider forecasts.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.predictions import Match, Prediction, PredictionStatus
from app.models.provider_data import ProviderEntityRef
from app.schemas.matches import (
    serialize_expert_prediction,
    serialize_forecast,
    serialize_match,
    serialize_prediction_revision,
)
from app.services.expert_prediction import ExpertPredictionService
from app.services.forecast_service import ForecastService
from app.services.match_brief import build_brief, compact_brief
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.providers.base import ProviderError

logger = logging.getLogger(__name__)
router = APIRouter()

#: `tz_offset` is the viewer's offset in MINUTES east of UTC (the negation of the browser's
#: `Date.prototype.getTimezoneOffset()`). Real zones run from UTC-12:00 to UTC+14:00, so a slightly
#: wider range is accepted to leave room for historical/odd offsets.
TZ_OFFSET_MIN_MINUTES = -840
TZ_OFFSET_MAX_MINUTES = 840

#: Freshness ranking used when one answer is assembled from two UTC days: the combined response is
#: reported as the *weakest* of the two, never as fresher than it really is.
_SOURCE_RANK = {"database": 0, "stale-cache": 1, "cache": 2, "provider": 3}


def local_day_window(day: date, tz_offset_minutes: int,
                     tz_offset_end_minutes: Optional[int] = None) -> Tuple[datetime, datetime]:
    """
    Half-open UTC window ``[local midnight, next local midnight)`` of one local calendar day.

    Today/tomorrow must mean the viewer's calendar day. Bucketing by the UTC day instead makes a
    late-evening kickoff vanish from Today and reappear under Tomorrow for everyone east of UTC.

    A local day is not always 24 hours. On a daylight-saving transition it is 23 or 25, so the end is
    computed from its own offset rather than by adding a fixed day: in New York on 1 November 2026 the
    day runs 04:00Z to 05:00Z the next day, and a fixed 24-hour window would silently drop the first
    hour, taking any kickoff just after local midnight with it. `tz_offset_end_minutes` is the
    viewer's offset at the NEXT local midnight; without it the start offset is reused, which is
    correct on every day except a transition.
    """
    midnight = datetime.combine(day, time.min, tzinfo=timezone.utc)
    start = midnight - timedelta(minutes=tz_offset_minutes)
    end_offset = tz_offset_minutes if tz_offset_end_minutes is None else tz_offset_end_minutes
    end = midnight + timedelta(days=1) - timedelta(minutes=end_offset)
    # A nonsensical pair (end at or before start) is ignored rather than returning an empty day.
    return (start, end) if end > start else (start, start + timedelta(days=1))


def _merge_meta(first: Optional[SyncMeta], second: SyncMeta) -> SyncMeta:
    """Combine the sync metadata of the two UTC days a local day can straddle."""
    if first is None:
        return second
    weakest = min((first, second), key=lambda m: _SOURCE_RANK.get(m.source, 0))
    return SyncMeta(
        provider=first.provider or second.provider,
        source=weakest.source,
        stale=first.stale or second.stale,
        fetched_at=first.fetched_at or second.fetched_at,
        errors=first.errors + second.errors,
        live_polled=first.live_polled or second.live_polled,
        results_polled=first.results_polled or second.results_polled,
        ambiguous=first.ambiguous + second.ambiguous,
    )


def _matches_in_window(service: MatchDataService, start: datetime, end: datetime,
                       refresh: bool) -> Tuple[List[Match], SyncMeta]:
    """Matches kicking off inside a UTC window that may straddle two UTC calendar days."""
    utc_days = sorted({start.date(), (end - timedelta(microseconds=1)).date()})
    meta: Optional[SyncMeta] = None
    found: Dict[uuid.UUID, Match] = {}
    for day in utc_days:
        day_matches, day_meta = service.matches_for_day(day, refresh=refresh)
        meta = _merge_meta(meta, day_meta)
        for match in day_matches:
            found[match.id] = match
    start_naive, end_naive = start.replace(tzinfo=None), end.replace(tzinfo=None)
    matches = [m for m in found.values() if m.match_date is not None and start_naive <= m.match_date < end_naive]
    matches.sort(key=lambda m: m.match_date)
    return matches, meta or SyncMeta()


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


def build_match_payloads(db: Session, matches: List[Match], service: MatchDataService, forecasts: ForecastService,
                         full_brief: bool = False) -> List[Dict[str, Any]]:
    """Serialise matches with their forecast, expert prediction and evidence brief.

    The brief is assembled from values this loop already holds, so it costs no database query of its
    own: every list payload can carry the compact form. ``full_brief`` adds the complete brief and is
    used by the detail endpoint only, to keep a thirty-match list small rather than because the full
    brief is more expensive to build.
    """
    teams = service.registry.team_names(matches)
    leagues = service.registry.leagues_by_id(matches)
    league_refs = _league_refs(db, leagues.keys())
    experts = _published_predictions(db, [m.id for m in matches])
    payloads = []
    for match in matches:
        record = forecasts.forecast_for_match(match)
        freshness = forecasts.freshness(record, match)
        forecast = serialize_forecast(record, freshness)
        expert = serialize_expert_prediction(experts.get(match.id))
        payload = serialize_match(match, teams, leagues, forecast, expert, league_refs)
        brief = build_brief(match=payload, forecast=forecast, freshness=freshness, expert=expert)
        payload["brief_compact"] = compact_brief(brief)
        if full_brief:
            payload["brief"] = brief
        payloads.append(payload)
    return payloads


def _response(day: Optional[date], meta: SyncMeta, payloads: List[Dict[str, Any]], forecast_report: Optional[Dict[str, Any]] = None,
              tz_offset: Optional[int] = None, window: Optional[Tuple[datetime, datetime]] = None) -> Dict[str, Any]:
    body = {"date": day.isoformat() if day else None, "provider": meta.provider, "source": meta.source, "stale": meta.stale,
            "fetched_at": meta.fetched_at, "errors": meta.errors, "forecast_sync": forecast_report, "matches": payloads}
    # Echo which window actually produced this list, so the caller can tell a local day from a UTC one.
    body["tz_offset"] = tz_offset
    if window is not None:
        body["window_utc"] = {"start": window[0].isoformat().replace("+00:00", "Z"),
                              "end": window[1].isoformat().replace("+00:00", "Z")}
    return body


@router.get("", summary="Matches for a calendar date (covered competitions)")
@router.get("/", include_in_schema=False)
async def list_matches(
    date_str: Optional[str] = Query(None, alias="date", description="Date YYYY-MM-DD (default: today). Read as a UTC "
                                                                    "date, or as the caller's local date when tz_offset is sent"),
    refresh: bool = Query(True, description="Refresh from the provider (cache and budget aware)"),
    tz_offset: Optional[int] = Query(None, ge=TZ_OFFSET_MIN_MINUTES, le=TZ_OFFSET_MAX_MINUTES,
                                     description="Caller's UTC offset in MINUTES east of UTC (e.g. 120 for UTC+2, -300 for "
                                                 "UTC-5; that is -Date.getTimezoneOffset()). When sent, the matches "
                                                 "returned are the ones kicking off in the caller's local calendar day "
                                                 "[local midnight, next local midnight). When omitted, the UTC calendar "
                                                 "day is used, exactly as before."),
    tz_offset_end: Optional[int] = Query(None, ge=TZ_OFFSET_MIN_MINUTES, le=TZ_OFFSET_MAX_MINUTES,
                                         description="Caller's UTC offset in MINUTES at the NEXT local midnight. Only "
                                                     "differs from tz_offset on a daylight-saving transition, when the "
                                                     "local day is 23 or 25 hours rather than 24. Defaults to tz_offset."),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    default_day = (now + timedelta(minutes=tz_offset)).date() if tz_offset is not None else now.date()
    try:
        day = date.fromisoformat(date_str) if date_str else default_day
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date must be YYYY-MM-DD")
    service = MatchDataService(db)
    forecasts = ForecastService(db)
    window = local_day_window(day, tz_offset, tz_offset_end) if tz_offset is not None else None
    try:
        if window is None:
            matches, meta = service.matches_for_day(day, refresh=refresh)
        else:
            matches, meta = _matches_in_window(service, window[0], window[1], refresh=refresh)
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
    return _response(day, meta, payloads, forecast_report, tz_offset=tz_offset, window=window)


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
    payload = build_match_payloads(db, [match], service, forecasts, full_brief=True)[0]
    experts = db.query(Prediction).filter(Prediction.match_id == match.id, Prediction.status == PredictionStatus.PUBLISHED,
                                          Prediction.deleted_at.is_(None)).order_by(Prediction.priority_level.desc()).all()
    payload["expert_predictions"] = [serialize_expert_prediction(p) for p in experts]
    # An expert may correct a published view. The versions that correction replaced are preserved,
    # so the reader can see that the view changed and when, rather than only the latest numbers.
    # One query for every prediction on this match, never one per prediction.
    revisions = ExpertPredictionService(db).revisions_for([p.id for p in experts])
    payload["expert_prediction_revisions"] = [
        serialize_prediction_revision(row, index, match.match_date)
        for prediction in experts
        for index, row in enumerate(revisions.get(prediction.id, []), start=1)
    ]
    payload["provider_refs"] = [{"provider": r.provider, "external_id": r.external_id, "confidence": r.match_confidence, "matched_by": r.matched_by}
                                for r in service.registry.refs_for("match", match.id)]
    return payload
