"""
Personal favourites: the teams and leagues a user follows, and the matches they saved.

Two stores, on purpose:

* Followed teams and leagues stay in the ``users.user_preferences`` JSONB columns that already exist
  (``favorite_teams``, ``favorite_leagues``) and that ``PUT /api/v1/users/me/preferences`` already
  writes. A follow is a bare id with nothing attached to it, and a second store for the same fact
  would diverge from the first the moment either endpoint were used.
* Saved matches live in ``users.saved_matches``. A save carries its own data - when it happened and
  the owner's private note - and is read by joining to the fixture and ordering by kickoff.

Every read here is stored-data only. Nothing in this module refreshes anything: no provider request
is issued on any path, whatever the provider budgets happen to allow, which is the same guarantee
``refresh=false`` gives on the match endpoints. The match payload itself is built by the matches
package's own ``build_match_payloads`` so a saved fixture is serialised exactly like any other.

The note is private. Every statement below filters on ``user_id`` before anything else, so one user's
note cannot be read, written or deleted by another, and no aggregate in this module touches it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.matches import build_match_payloads
from app.core.deps import get_current_active_user, get_db
from app.models.predictions import League, Match, MatchStatus, Team
from app.models.users import SavedMatch, User, UserPreference
from app.schemas.favourites import (
    MAX_FAVOURITE_LEAGUES,
    MAX_FAVOURITE_TEAMS,
    FavouriteLimits,
    FavouritesResponse,
    FollowResponse,
    SavedMatchDeleteResponse,
    SavedMatchEntry,
    SavedMatchUpsert,
    SavedMatchWriteResponse,
    SavedMatchesResponse,
    UnresolvedFavourites,
)
from app.schemas.matches import iso_utc, serialize_league, serialize_team
from app.services.forecast_service import ForecastService
from app.services.match_data_service import MatchDataService
from app.services.match_registry import MatchRegistry

router = APIRouter()

#: Sort key for a fixture whose kickoff is missing; it sorts first rather than raising.
_NO_KICKOFF = datetime.min


# --------------------------------------------------------------------------- small helpers
def _as_uuid(raw: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(raw).strip())
    except (AttributeError, TypeError, ValueError):
        return None


def _id_list(raw: Any) -> List[str]:
    """The stored favourite ids, defensively.

    The column is free-form JSONB written by two endpoints and by hand over the life of the database,
    so anything that is not a list of usable strings is treated as an empty list rather than trusted.
    """
    if not isinstance(raw, list):
        return []
    ids: List[str] = []
    seen = set()
    for value in raw:
        if isinstance(value, (dict, list)):
            continue
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            ids.append(text)
    return ids


def _preferences(db: Session, user: User, create: bool = False) -> Optional[UserPreference]:
    prefs = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if prefs is None and create:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        db.flush()
    return prefs


def _clean_note(note: Optional[str]) -> Optional[str]:
    """Whitespace is not a note: an empty one is stored as NULL so "no note" has a single spelling."""
    if note is None:
        return None
    trimmed = note.strip()
    return trimmed or None


# --------------------------------------------------------------------------- resolving ids
def _resolve_team_id(db: Session, raw: str) -> Optional[str]:
    """The internal id of an existing team, or None. A favourite may never point at nothing."""
    candidate = _as_uuid(raw)
    if candidate is None:
        return None
    found = db.query(Team.id).filter(Team.id == candidate).first()
    return str(found[0]) if found else None


def _resolve_league_id(db: Session, raw: str) -> Optional[str]:
    """As above for leagues, which may also be addressed by their canonical key (``premier_league``).

    Whatever came in, the internal UUID is what gets stored, so one league has one spelling on disk.
    """
    candidate = _as_uuid(raw)
    if candidate is not None:
        found = db.query(League.id).filter(League.id == candidate).first()
        return str(found[0]) if found else None
    league = MatchRegistry(db).league_for_key(str(raw).strip())
    return str(league.id) if league is not None else None


def _resolve_match(db: Session, raw: str) -> Optional[Match]:
    """The fixture a client-supplied match identifier names, accepting every form the match endpoints do."""
    resolved = MatchRegistry(db).resolve_match_id(raw)
    if resolved is None:
        return None
    return db.query(Match).filter(Match.id == resolved).first()


# --------------------------------------------------------------------------- serialisation
def _match_payloads(db: Session, matches: List[Match]) -> List[Dict[str, Any]]:
    """The match endpoints' own payload, built from stored rows only.

    ``sync_fixtures=False`` and the absence of any ``ensure_synced`` call are what keep this read free:
    the forecast service only looks up forecasts already in the database.
    """
    if not matches:
        return []
    service = MatchDataService(db)
    forecasts = ForecastService(db, sync_fixtures=False)
    return build_match_payloads(db, matches, service, forecasts)


def _entry(row: SavedMatch, match: Match, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"match_id": str(match.id), "note": row.note, "saved_at": iso_utc(row.created_at),
            "updated_at": iso_utc(row.updated_at), "match": payload}


def _saved_pairs(db: Session, user: User) -> List[Tuple[Match, Dict[str, Any]]]:
    """This user's saves, each with its fixture. Rows only ever come from this user's own saves."""
    rows = db.query(SavedMatch).filter(SavedMatch.user_id == user.id).order_by(SavedMatch.created_at.desc()).all()
    if not rows:
        return []
    matches = {m.id: m for m in db.query(Match).filter(Match.id.in_([r.match_id for r in rows])).all()}
    # A save whose fixture is gone has nothing to render. The cascade normally removes it with the
    # fixture; if one ever survives, it is skipped here rather than turning the whole list into a 500.
    pairs = [(row, matches[row.match_id]) for row in rows if row.match_id in matches]
    payloads = _match_payloads(db, [match for _, match in pairs])
    return [(match, _entry(row, match, payload)) for (row, match), payload in zip(pairs, payloads)]


def _saved_matches(db: Session, user: User) -> SavedMatchesResponse:
    buckets: Dict[str, List[Tuple[Match, Dict[str, Any]]]] = {"upcoming": [], "live": [], "finished": []}
    for match, entry in _saved_pairs(db, user):
        if match.status == MatchStatus.LIVE:
            buckets["live"].append((match, entry))
        elif match.status == MatchStatus.FINISHED:
            buckets["finished"].append((match, entry))
        else:
            # Scheduled, postponed and cancelled all sit here; each entry carries its real status.
            buckets["upcoming"].append((match, entry))

    def kickoff(pair: Tuple[Match, Dict[str, Any]]) -> datetime:
        return pair[0].match_date or _NO_KICKOFF

    upcoming = [entry for _, entry in sorted(buckets["upcoming"], key=kickoff)]
    live = [entry for _, entry in sorted(buckets["live"], key=kickoff)]
    finished = [entry for _, entry in sorted(buckets["finished"], key=kickoff, reverse=True)]
    return SavedMatchesResponse(
        upcoming=[SavedMatchEntry(**e) for e in upcoming],
        live=[SavedMatchEntry(**e) for e in live],
        finished=[SavedMatchEntry(**e) for e in finished],
        counts={"upcoming": len(upcoming), "live": len(live), "finished": len(finished),
                "total": len(upcoming) + len(live) + len(finished)},
    )


def _hydrate(rows: Dict[uuid.UUID, Any], ids: List[str], serialize) -> Tuple[List[Dict[str, Any]], List[str]]:
    found: List[Dict[str, Any]] = []
    missing: List[str] = []
    for raw in ids:
        candidate = _as_uuid(raw)
        row = rows.get(candidate) if candidate is not None else None
        if row is None:
            missing.append(raw)
        else:
            found.append(serialize(row))
    return found, missing


# --------------------------------------------------------------------------- follow / unfollow
def _follow(db: Session, user: User, kind: str, entity_id: str, limit: int, field: str) -> FollowResponse:
    prefs = _preferences(db, user, create=True)
    ids = _id_list(getattr(prefs, field))
    if entity_id in ids:
        return FollowResponse(kind=kind, id=entity_id, following=True, changed=False, ids=ids, limit=limit)
    if len(ids) >= limit:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"You already follow {limit} {kind}s. Unfollow one before adding another.")
    ids = ids + [entity_id]
    # JSONB change tracking is by identity: a new list must be assigned, not the old one mutated.
    setattr(prefs, field, ids)
    prefs.updated_at = datetime.utcnow()
    db.commit()
    return FollowResponse(kind=kind, id=entity_id, following=True, changed=True, ids=ids, limit=limit)


def _unfollow(db: Session, user: User, kind: str, entity_id: str, limit: int, field: str) -> FollowResponse:
    prefs = _preferences(db, user)
    ids = _id_list(getattr(prefs, field)) if prefs is not None else []
    if entity_id not in ids:
        # Unfollowing something you do not follow is not an error; the state asked for is the state there is.
        return FollowResponse(kind=kind, id=entity_id, following=False, changed=False, ids=ids, limit=limit)
    ids = [i for i in ids if i != entity_id]
    setattr(prefs, field, ids)
    prefs.updated_at = datetime.utcnow()
    db.commit()
    return FollowResponse(kind=kind, id=entity_id, following=False, changed=True, ids=ids, limit=limit)


# --------------------------------------------------------------------------- endpoints
@router.get("/favourites", response_model=FavouritesResponse,
            summary="Teams, leagues and matches this user follows")
async def list_favourites(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Everything the personal dashboard needs, from stored data only (no provider request).

    Followed ids that no longer resolve to a row are reported under ``unresolved`` instead of being
    dropped, so the client can say so rather than quietly showing a shorter list.
    """
    prefs = _preferences(db, current_user)
    team_ids = _id_list(prefs.favorite_teams if prefs is not None else None)
    league_ids = _id_list(prefs.favorite_leagues if prefs is not None else None)

    team_uuids = [u for u in (_as_uuid(i) for i in team_ids) if u is not None]
    league_uuids = [u for u in (_as_uuid(i) for i in league_ids) if u is not None]
    teams_by_id = {t.id: t for t in db.query(Team).filter(Team.id.in_(team_uuids)).all()} if team_uuids else {}
    leagues_by_id = {lg.id: lg for lg in db.query(League).filter(League.id.in_(league_uuids)).all()} if league_uuids else {}

    teams, unresolved_teams = _hydrate(teams_by_id, team_ids, serialize_team)
    leagues, unresolved_leagues = _hydrate(leagues_by_id, league_ids, lambda lg: serialize_league(lg, None))

    return FavouritesResponse(
        teams=teams, leagues=leagues, team_ids=team_ids, league_ids=league_ids,
        unresolved=UnresolvedFavourites(teams=unresolved_teams, leagues=unresolved_leagues),
        saved_matches=_saved_matches(db, current_user),
        limits=FavouriteLimits(teams=MAX_FAVOURITE_TEAMS, leagues=MAX_FAVOURITE_LEAGUES),
    )


@router.put("/favourites/teams/{team_id}", response_model=FollowResponse, summary="Follow a team")
async def follow_team(
    team_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Idempotent: following a team you already follow reports ``changed: false``, not an error."""
    resolved = _resolve_team_id(db, team_id)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return _follow(db, current_user, "team", resolved, MAX_FAVOURITE_TEAMS, "favorite_teams")


@router.delete("/favourites/teams/{team_id}", response_model=FollowResponse, summary="Unfollow a team")
async def unfollow_team(
    team_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Idempotent, and it never 404s.

    Existence is not checked on the way out: a team removed from our data would otherwise leave an id
    in the list that could never be taken out again.
    """
    resolved = _resolve_team_id(db, team_id) or str(team_id).strip()
    return _unfollow(db, current_user, "team", resolved, MAX_FAVOURITE_TEAMS, "favorite_teams")


@router.put("/favourites/leagues/{league_id}", response_model=FollowResponse, summary="Follow a league")
async def follow_league(
    league_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Accepts the internal UUID or the canonical key; the UUID is what is stored."""
    resolved = _resolve_league_id(db, league_id)
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="League not found")
    return _follow(db, current_user, "league", resolved, MAX_FAVOURITE_LEAGUES, "favorite_leagues")


@router.delete("/favourites/leagues/{league_id}", response_model=FollowResponse, summary="Unfollow a league")
async def unfollow_league(
    league_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Idempotent, and it never 404s (see ``unfollow_team``)."""
    resolved = _resolve_league_id(db, league_id) or str(league_id).strip()
    return _unfollow(db, current_user, "league", resolved, MAX_FAVOURITE_LEAGUES, "favorite_leagues")


@router.get("/saved-matches", response_model=SavedMatchesResponse,
            summary="Matches this user saved, split into upcoming / live / finished")
async def list_saved_matches(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    The user's own saves, each carrying the match payload the match endpoints return plus their note.

    Stored data only: no provider request is issued, and no forecast sync is triggered.
    """
    return _saved_matches(db, current_user)


@router.put("/saved-matches/{match_id}", response_model=SavedMatchWriteResponse, summary="Save a match")
async def save_match(
    match_id: str,
    payload: Optional[SavedMatchUpsert] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Save a fixture, optionally with a private note. Saving twice is idempotent (``created: false``).

    Omitting ``note`` leaves any existing note untouched, so a plain re-save never destroys what the
    user wrote; sending ``null`` or an empty string clears it.
    """
    match = _resolve_match(db, match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    note_given = payload is not None and "note" in payload.model_fields_set
    row = db.query(SavedMatch).filter(
        SavedMatch.user_id == current_user.id, SavedMatch.match_id == match.id).first()
    created = row is None
    if created:
        row = SavedMatch(user_id=current_user.id, match_id=match.id)
        db.add(row)
    if note_given:
        row.note = _clean_note(payload.note)
    try:
        db.commit()
    except IntegrityError:
        # Two saves of the same fixture in flight at once: the unique constraint stops the second
        # insert, and the call still succeeds against the row that won.
        db.rollback()
        row = db.query(SavedMatch).filter(
            SavedMatch.user_id == current_user.id, SavedMatch.match_id == match.id).first()
        if row is None:
            raise
        created = False
        if note_given:
            row.note = _clean_note(payload.note)
            db.commit()

    return SavedMatchWriteResponse(created=created, **_entry(row, match, _match_payloads(db, [match])[0]))


@router.delete("/saved-matches/{match_id}", response_model=SavedMatchDeleteResponse, summary="Unsave a match")
async def unsave_match(
    match_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Idempotent: removing a match that was not saved reports ``removed: false``, not a 404."""
    match = _resolve_match(db, match_id)
    target = match.id if match is not None else _as_uuid(match_id)
    removed = False
    if target is not None:
        row = db.query(SavedMatch).filter(
            SavedMatch.user_id == current_user.id, SavedMatch.match_id == target).first()
        if row is not None:
            db.delete(row)
            db.commit()
            removed = True
    return SavedMatchDeleteResponse(match_id=str(target) if target is not None else str(match_id).strip(),
                                    removed=removed)
