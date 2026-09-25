"""
The signed-in reader's own selection slips: /api/v1/me/slips.

Stored data only. Building, saving, recording and reading a slip never asks a provider for
anything; the probabilities beside a leg come from forecasts already on disk. Every read settles
pending legs against stored results first, so what is served is never behind the results task.

A refusal raises before the service writes anything (see SlipService: every check precedes the
row), so no handler rolls back by hand. The request-scoped session is discarded on the error path
by ``get_db``, and a test session joined to an outer transaction keeps its own fixtures.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_db
from app.models.users import User
from app.schemas.slips import LegInput, LegOddsUpdate, SlipCreate, SlipRecord, SlipUpdate
from app.services.slips import SlipError, SlipService

router = APIRouter()


def _raise(error: SlipError) -> None:
    raise HTTPException(status_code=error.status_code, detail={"message": error.detail, "code": error.code})


@router.get("/slips", summary="This reader's slips, newest first, settled against stored results")
async def list_slips(
    slip_status: Optional[str] = Query(default=None, alias="status", pattern="^(draft|saved|recorded)$"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    service = SlipService(db)
    slips = service.list(current_user, slip_status)
    if service.settle(slips):
        db.commit()
    return {"slips": service.serialize_many(slips)}


@router.post("/slips", status_code=status.HTTP_201_CREATED, summary="Start a slip, optionally with selections")
async def create_slip(body: SlipCreate, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.create(current_user, body.name, body.legs)
    except SlipError as error:
        _raise(error)
    db.commit()
    return service.serialize(slip)


@router.get("/slips/{slip_id}", summary="One slip")
async def get_slip(slip_id: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
    except SlipError as error:
        _raise(error)
    if service.settle([slip]):
        db.commit()
    return service.serialize(slip)


@router.patch("/slips/{slip_id}", summary="Rename, annotate, save, or set the stake")
async def update_slip(slip_id: str, body: SlipUpdate, current_user: User = Depends(get_current_active_user),
                      db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
        service.update(current_user, slip, name=body.name, note=body.note, status=body.status, currency=body.currency,
                       stake=body.stake, fields_set=body.model_fields_set)
    except SlipError as error:
        _raise(error)
    db.commit()
    return service.serialize(slip)


@router.delete("/slips/{slip_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a draft or saved slip")
async def delete_slip(slip_id: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
        service.delete(current_user, slip)
    except SlipError as error:
        _raise(error)
    db.commit()
    return None


@router.post("/slips/{slip_id}/legs", status_code=status.HTTP_201_CREATED, summary="Add one selection")
async def add_leg(slip_id: str, body: LegInput, current_user: User = Depends(get_current_active_user),
                  db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
        service.add_leg(current_user, slip, body.match_id, body.selection_id, body.odds)
    except SlipError as error:
        _raise(error)
    db.commit()
    return service.serialize(slip)


@router.delete("/slips/{slip_id}/legs/{leg_id}", summary="Remove one selection")
async def remove_leg(slip_id: str, leg_id: str, current_user: User = Depends(get_current_active_user),
                     db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
        service.remove_leg(current_user, slip, leg_id)
    except SlipError as error:
        _raise(error)
    db.commit()
    return service.serialize(slip)


@router.patch("/slips/{slip_id}/legs/{leg_id}", summary="Set or clear the price the reader's bookmaker offers for a leg")
async def set_leg_odds(slip_id: str, leg_id: str, body: LegOddsUpdate, current_user: User = Depends(get_current_active_user),
                       db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
        service.set_leg_odds(current_user, slip, leg_id, body.odds)
    except SlipError as error:
        _raise(error)
    db.commit()
    return service.serialize(slip)


@router.post("/slips/{slip_id}/record", summary="Record that this combination was placed elsewhere (immutable afterwards)")
async def record_slip(slip_id: str, body: SlipRecord, current_user: User = Depends(get_current_active_user),
                      db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
        service.record(current_user, slip, reference=body.reference, currency=body.currency, stake=body.stake, price=body.price)
    except SlipError as error:
        _raise(error)
    db.commit()
    return service.serialize(slip)


@router.post("/slips/{slip_id}/duplicate", status_code=status.HTTP_201_CREATED, summary="A new draft with the same selections")
async def duplicate_slip(slip_id: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)):
    service = SlipService(db)
    try:
        slip = service.get(current_user, slip_id)
        copy = service.duplicate(current_user, slip)
    except SlipError as error:
        _raise(error)
    db.commit()
    return service.serialize(copy)
