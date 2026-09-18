"""
Schemas for the personal favourites endpoints (followed teams and leagues, saved matches).

The match object inside a saved entry is deliberately typed as a free-form mapping: it is produced
by ``app.schemas.matches.serialize_match``, exactly as the match endpoints produce it, and must reach
the client unchanged. Declaring it field by field here would create a second definition of the match
payload that could silently drift from the first, and a response model that filters keys would drop
whatever the matches package adds next.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

#: A note is a short personal reminder, not a document. The column is TEXT; this is the API cap.
NOTE_MAX_LENGTH = 2000

#: Kept in step with the caps enforced by PUT /api/v1/users/me/preferences, which writes the same
#: two JSONB columns. Two writers with different limits would let one of them store a list the other
#: refuses to accept back.
MAX_FAVOURITE_TEAMS = 10
MAX_FAVOURITE_LEAGUES = 5


class SavedMatchUpsert(BaseModel):
    """Body of PUT /api/v1/me/saved-matches/{match_id}. Every field is optional."""

    note: Optional[str] = Field(
        default=None, max_length=NOTE_MAX_LENGTH,
        description="The owner's private note. Omit the field to leave an existing note untouched; "
                    "send null or an empty string to clear it. Never visible to anybody else.")


class SavedMatchEntry(BaseModel):
    """One saved fixture: the match payload the match endpoints return, plus this user's own data."""

    match_id: str = Field(description="Internal match UUID")
    note: Optional[str] = Field(default=None, description="Private to the owner of the save")
    saved_at: Optional[str] = Field(default=None, description="When the match was saved (UTC, ISO-8601 with Z)")
    updated_at: Optional[str] = Field(default=None, description="When the note was last changed (UTC, ISO-8601 with Z)")
    match: Dict[str, Any] = Field(description="Exactly the payload GET /api/v1/matches returns for this fixture")


class SavedMatchWriteResponse(SavedMatchEntry):
    """Result of saving a match. ``created`` is false when the match was already saved."""

    created: bool = Field(description="True when this call added the save, false when it already existed")


class SavedMatchDeleteResponse(BaseModel):
    """Result of unsaving a match. Removing a match that was not saved is not an error."""

    match_id: str
    removed: bool = Field(description="True when a save was deleted, false when there was nothing to delete")


class SavedMatchesResponse(BaseModel):
    """
    The user's saved matches, split by state.

    ``live`` is what is in play now and ``finished`` what has been played; ``upcoming`` is everything
    else, so a postponed or cancelled fixture stays there and carries its real status in the match
    payload rather than being reported as finished. ``upcoming`` and ``live`` run earliest kickoff
    first, ``finished`` most recent first.
    """

    upcoming: List[SavedMatchEntry] = Field(default_factory=list)
    live: List[SavedMatchEntry] = Field(default_factory=list)
    finished: List[SavedMatchEntry] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict, description="upcoming / live / finished / total")


class FavouriteLimits(BaseModel):
    teams: int = MAX_FAVOURITE_TEAMS
    leagues: int = MAX_FAVOURITE_LEAGUES


class UnresolvedFavourites(BaseModel):
    """
    Followed ids that no longer match a row we hold.

    Reported rather than dropped: "we are following something we cannot show you" is a different
    statement from "you follow nothing", and only the client can decide how to say it.
    """

    teams: List[str] = Field(default_factory=list)
    leagues: List[str] = Field(default_factory=list)


class FavouritesResponse(BaseModel):
    """Everything the personal dashboard needs in one stored-data-only read."""

    teams: List[Dict[str, Any]] = Field(default_factory=list, description="Followed teams, in the order they were added")
    leagues: List[Dict[str, Any]] = Field(default_factory=list, description="Followed leagues, in the order they were added")
    team_ids: List[str] = Field(default_factory=list, description="Exactly what is stored, unresolved ids included")
    league_ids: List[str] = Field(default_factory=list)
    unresolved: UnresolvedFavourites = Field(default_factory=UnresolvedFavourites)
    saved_matches: SavedMatchesResponse = Field(default_factory=SavedMatchesResponse,
                                                description="Same shape as GET /api/v1/me/saved-matches")
    limits: FavouriteLimits = Field(default_factory=FavouriteLimits)


class FollowResponse(BaseModel):
    """Result of following or unfollowing a team or a league."""

    kind: str = Field(description="'team' or 'league'")
    id: str = Field(description="Internal UUID of the team or league acted on")
    following: bool = Field(description="State after the call")
    changed: bool = Field(description="False when the call was a no-op (already followed / not followed)")
    ids: List[str] = Field(default_factory=list, description="The full followed list after the call")
    limit: int = Field(description="How many of this kind may be followed")
