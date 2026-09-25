"""
Request bodies for the personal selection-slip endpoints.

Responses are free-form mappings built by app/services/slips.py, for the same reason the favourites
responses are: a leg carries the match payload the match endpoints serve, and typing it twice would
let the two drift.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

NAME_MAX_LENGTH = 120
NOTE_MAX_LENGTH = 2000
REFERENCE_MAX_LENGTH = 120


class LegInput(BaseModel):
    match_id: str = Field(description="Internal match UUID")
    selection_id: str = Field(description="A selection id from GET /api/v1/matches/{id}/markets, e.g. total_goals:over@2.5")
    odds: Optional[float] = Field(default=None, gt=1.0, le=1000.0,
                                  description="Decimal price the reader's bookmaker offers for exactly this selection; optional")


class SlipCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=NAME_MAX_LENGTH)
    legs: List[LegInput] = Field(default_factory=list)


class SlipUpdate(BaseModel):
    """Every field optional; a field left out is left untouched. Refused on a recorded slip except name and note."""
    name: Optional[str] = Field(default=None, max_length=NAME_MAX_LENGTH)
    note: Optional[str] = Field(default=None, max_length=NOTE_MAX_LENGTH)
    status: Optional[str] = Field(default=None, pattern="^(draft|saved)$",
                                  description="draft or saved; 'recorded' is reached only through POST .../record")
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3, description="ISO 4217 code, e.g. XAF, EUR")
    stake: Optional[str] = Field(default=None, max_length=32,
                                 description="Stake as decimal text in that currency ('5050', '12.50'); empty string clears it")


class LegReplace(BaseModel):
    """Body of PUT .../legs/{leg_id}: another selection on the same fixture, swapped in one step."""
    selection_id: str = Field(description="The selection to put in this leg's place; same fixture")
    odds: Optional[float] = Field(default=None, gt=1.0, le=1000.0)


class LegOddsUpdate(BaseModel):
    odds: Optional[float] = Field(default=None, gt=1.0, le=1000.0, description="null clears a user-entered price")


class SlipRecord(BaseModel):
    """The reader's statement that this combination was placed elsewhere. Nothing here is verified."""
    reference: Optional[str] = Field(default=None, max_length=REFERENCE_MAX_LENGTH)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    stake: Optional[str] = Field(default=None, max_length=32)
    price: Optional[float] = Field(default=None, gt=1.0, le=100000.0,
                                   description="The combined decimal price the bookmaker gave; when omitted, the product of the legs' prices is used if every leg has one")
