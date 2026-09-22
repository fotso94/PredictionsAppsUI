"""
Public match endpoints backed by the configured match-data provider (Live Score API by default)
and the configured forecast provider (GameForecastAPI by default). Expert predictions are always
returned separately from provider forecasts.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
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
from app.services.match_brief import build_brief, compact_brief, current_scoring_summary
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.providers.base import ProviderError, parse_utc

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
    """Combine the sync metadata of the two UTC days a local day can straddle.

    Built by copying `first` and overriding the fields whose combination is defined below, never
    by naming every field in a constructor call. The rule matters because this runs only on a
    local day that straddles two UTC days, which is the code path a reader is least likely to
    check: a field added to SyncMeta and not named here then survives with the first day's value,
    which is wrong for a sum but is at least not a fabricated zero reported as a real count.

    `forward_source` and `forward_fetched_at` describe one and the same answer, so both are taken
    from the same day.
    """
    if first is None:
        return second
    weakest = min((first, second), key=lambda m: _SOURCE_RANK.get(m.source, 0))
    merged = replace(first)
    merged.source = weakest.source
    merged.provider = first.provider or second.provider
    merged.stale = first.stale or second.stale
    merged.fetched_at = first.fetched_at or second.fetched_at
    merged.errors = first.errors + second.errors
    merged.live_polled = first.live_polled or second.live_polled
    merged.results_polled = first.results_polled or second.results_polled
    merged.ambiguous = first.ambiguous + second.ambiguous
    merged.fixtures_seen = first.fixtures_seen + second.fixtures_seen
    merged.fixtures_stored = first.fixtures_stored + second.fixtures_stored
    merged.forward_fixtures_seen = first.forward_fixtures_seen + second.forward_fixtures_seen
    merged.forward_fixtures_stored = first.forward_fixtures_stored + second.forward_fixtures_stored
    # The forward answer of the pair is the weaker of the two, by the same ranking as `source`;
    # a day whose forward list was never answered (None) ranks below every answered one. The
    # timestamp comes from that same day rather than from whichever day happens to have one:
    # merged separately, an unanswered day (source None) could be reported carrying the other
    # day's fetch time, which reads as an answer that was never given.
    weakest_forward = min((first, second), key=lambda m: _SOURCE_RANK.get(m.forward_source, 0))
    merged.forward_source = weakest_forward.forward_source
    merged.forward_fetched_at = weakest_forward.forward_fetched_at
    return merged


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

    The brief is assembled from values this loop already holds, so it costs no database query per
    match: every list payload can carry the compact form. ``full_brief`` adds the complete brief and
    is used by the detail endpoint only, to keep a thirty-match list small rather than because the
    full brief is more expensive to build.

    The one thing a brief cannot read off those values is how much has been scored against a
    result, and that is measured ONCE here, for the whole request, on the session this request was
    already given. Leaving it out is what the briefs used to do, and ``build_brief`` then fell back
    to opening a ``SessionLocal`` of its own whenever its sixty-second cache was cold — a second
    session and a second transaction inside a request that already had one, on the hot path of
    every match list and every match page.
    """
    teams = service.registry.team_names(matches)
    leagues = service.registry.leagues_by_id(matches)
    league_refs = _league_refs(db, leagues.keys())
    experts = _published_predictions(db, [m.id for m in matches])
    # Nothing to describe means nothing to measure: an empty day costs no measurement at all.
    scoring = current_scoring_summary(db) if matches else None
    payloads = []
    for match in matches:
        record = forecasts.forecast_for_match(match)
        freshness = forecasts.freshness(record, match)
        forecast = serialize_forecast(record, freshness)
        expert = serialize_expert_prediction(experts.get(match.id))
        payload = serialize_match(match, teams, leagues, forecast, expert, league_refs)
        brief = build_brief(match=payload, forecast=forecast, freshness=freshness, expert=expert,
                            scoring=scoring)
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


#: Fixtures `/upcoming` will name at once. An empty matchday needs to say when football resumes and
#: who plays, not to reproduce a round, and the cap is here rather than left to the caller so one
#: query string cannot turn a small answer into a long one.
UPCOMING_MAX_FIXTURES = 10


def _upcoming_fixture(payload: Dict[str, Any]) -> Dict[str, Any]:
    """One calendar fixture, reduced to what naming it requires.

    Deliberately not `serialize_match`: that describes a stored match, and these are rows read
    from a provider's calendar that this installation has not stored and has no id for. Handing
    back a match-shaped object without an id would invite a caller to link to a page that does
    not exist.
    """
    competition = payload.get("competition") or {}
    return {
        "competition": {"key": competition.get("key"), "name": competition.get("name")},
        "home": (payload.get("home") or {}).get("name"),
        "away": (payload.get("away") or {}).get("name"),
        "kickoff_utc": payload.get("kickoff_utc"),
    }


def _kickoff_still_ahead(row: Dict[str, Any], now: datetime) -> bool:
    """True when this calendar row's kickoff reads as an instant and that instant has not arrived.

    A row whose kickoff cannot be read is not ahead of anything: there is no date to compare, and
    offering it as a fixture to come would be naming a match we cannot place in time.
    """
    kickoff = parse_utc(row.get("kickoff_utc"))
    return kickoff is not None and kickoff > now


@router.get("/upcoming", summary="The next fixtures the provider's calendar lists (covered competitions)")
async def upcoming_matches(
    limit: int = Query(5, ge=1, le=UPCOMING_MAX_FIXTURES,
                       description="How many fixtures to name, earliest first"),
    db: Session = Depends(get_db),
):
    """When the covered competitions play next, for a day that holds no fixture at all.

    Read from the competition calendar, which is one provider request per competition and is
    cached for hours (see `CALENDAR_HEAD_TTL_SECONDS`); it is not the day-by-day fixtures path and
    must not be called on a day that has fixtures to show.

    The calendar is filtered against the clock when it is fetched and then served for hours, so
    the clock is applied again here: a fixture that has kicked off since the sweep is no longer
    one to come, however fresh the copy holding it.

    Two fields carry the honesty of this answer, and a caller needs both.

    `known` says whether this answer can still speak for the calendar. `true`: `fixtures` is what
    it listed that is still to be played, and an empty `fixtures` means nothing is listed to come.
    `false`: either nobody could tell us, or every fixture in the copy we hold has now been
    played — a calendar that ran out before it expired says nothing about what comes next. Both
    are "we do not know", and a caller must say so rather than render the empty list as "no
    football is scheduled".

    `unanswered` names the covered competitions nobody could be asked about. It is normally empty.
    When it is not, the answer is partial however true `known` is: those competitions may play
    before anything in `fixtures`, so `next_kickoff` is the earliest of what was read and not the
    date football resumes, and a caller must not present it as the latter.
    """
    service = MatchDataService(db)
    now = datetime.now(timezone.utc)
    try:
        answer, meta = service.next_fixtures()
    except ProviderError as exc:  # no provider, no cache: still an answer, just not a known one
        logger.info("Upcoming fixtures could not be read: %s", exc)
        answer, meta = None, SyncMeta(errors=[str(exc)])
    rows = list((answer or {}).get("fixtures") or [])
    # The stored answer was filtered against the clock of the sweep that fetched it, and is then
    # served fresh for hours and stale for a day. Filtering again against this request's clock is
    # what stops a reader being told football resumes on a date that has passed.
    ahead = [row for row in rows if _kickoff_still_ahead(row, now)]
    # A calendar that listed fixtures and has none left to list has run out; it no longer says
    # when football resumes, and serving it as an empty list would turn a copy that went out of
    # date into the claim that nothing is scheduled. A calendar that listed nothing in the first
    # place is untouched by the clock and stays the known, empty answer it was.
    known = answer is not None and (bool(ahead) or not rows)
    return {
        "known": known,
        "as_of": now.isoformat().replace("+00:00", "Z"),
        # The earliest kickoff of the WHOLE answer rather than of the capped list, so the date
        # does not move when a caller asks for fewer fixtures to be named. What it is the earliest
        # OF is whatever `unanswered` leaves: the competitions that were actually read.
        "next_kickoff": (ahead[0].get("kickoff_utc") if ahead else None),
        "fixtures": [_upcoming_fixture(item) for item in ahead][:limit],
        # The competitions this answer does not speak for. Kept beside the fixtures rather than
        # among the diagnostics below, because it changes what the fixtures mean.
        "unanswered": list((answer or {}).get("unanswered") or []),
        "provider": meta.provider,
        # Where the answer was read: the provider, the cache, or a stale copy of it. An answer
        # nobody could give was read from nowhere, and SyncMeta's default would name "database",
        # which this path never touches.
        "source": meta.source if answer is not None else None,
        "stale": meta.stale,
        "fetched_at": meta.fetched_at,
        "errors": meta.errors,
    }


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
