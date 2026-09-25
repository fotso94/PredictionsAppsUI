"""
Market envelopes for stored fixtures: the bridge between the pure market contract
(app/services/markets.py) and the rows that hold forecasts.

Reads only. Nothing here asks a provider for anything: a fixture with no stored forecast gets an
envelope that says so, and a page that shows markets costs the provider nothing.

WHICH SNAPSHOT A MARKET COMES FROM. The current ``provider_forecasts`` row is overwritten whenever
the provider changes its mind; ``provider_forecast_snapshots`` keeps every version. A leg taken
from a page must be attributable to the version that was on the page, so each envelope names the
snapshot whose content hash equals the current row's content (the adapter's own ``content_hash``),
falling back to the newest snapshot when no hash matches - a row written before snapshots were
kept has none.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from app.models.predictions import Match
from app.models.provider_data import ProviderForecastRecord, ProviderForecastSnapshot
from app.services.forecast_service import ForecastService, content_hash
from app.services.markets import PROVIDER_GAMEFORECAST, markets_for_forecast, no_forecast_envelope
from app.services.providers.gameforecast import parse_event


def _snapshot_for(record: ProviderForecastRecord, snapshots: List[ProviderForecastSnapshot]) -> Optional[ProviderForecastSnapshot]:
    if not snapshots:
        return None
    digest = None
    if isinstance(record.raw_payload, dict):
        forecast = parse_event(record.raw_payload)
        if forecast is not None:
            digest = content_hash(forecast)
    ordered = sorted(snapshots, key=lambda s: (s.first_fetched_at or datetime.min), reverse=True)
    if digest:
        for snapshot in ordered:
            if snapshot.content_hash == digest:
                return snapshot
    return ordered[0]


def envelopes_for_matches(db: Session, matches: Iterable[Match], forecasts: Optional[ForecastService] = None,
                          provider: str = PROVIDER_GAMEFORECAST, now: Optional[datetime] = None) -> Dict[uuid.UUID, Dict[str, Any]]:
    """One envelope per fixture, keyed by match id, in three queries however many fixtures there are."""
    matches = list(matches)
    now = now or datetime.now(timezone.utc)
    forecasts = forecasts or ForecastService(db)
    ids = [m.id for m in matches]
    if not ids:
        return {}
    records = {r.match_id: r for r in db.query(ProviderForecastRecord)
               .filter(ProviderForecastRecord.match_id.in_(ids), ProviderForecastRecord.provider == provider).all()}
    snapshots: Dict[uuid.UUID, List[ProviderForecastSnapshot]] = {}
    for snapshot in db.query(ProviderForecastSnapshot).filter(
            ProviderForecastSnapshot.match_id.in_(ids), ProviderForecastSnapshot.provider == provider).all():
        snapshots.setdefault(snapshot.match_id, []).append(snapshot)
    out: Dict[uuid.UUID, Dict[str, Any]] = {}
    for match in matches:
        record = records.get(match.id)
        freshness = forecasts.freshness(record, match)
        if record is None or not isinstance(record.raw_payload, dict):
            out[match.id] = no_forecast_envelope(str(match.id), freshness, now)
            continue
        snapshot = _snapshot_for(record, snapshots.get(match.id, []))
        out[match.id] = markets_for_forecast(
            match_id=str(match.id), event=record.raw_payload, provider=record.provider,
            record_id=str(record.id), snapshot_id=str(snapshot.id) if snapshot else None,
            captured_before_kickoff=snapshot.captured_before_kickoff if snapshot else None,
            retrieved_at=record.fetched_at, model_run_at=record.model_run_at,
            provider_updated_at=record.provider_updated_at, freshness=freshness, now=now)
    return out


def envelope_for_match(db: Session, match: Match, forecasts: Optional[ForecastService] = None,
                       now: Optional[datetime] = None) -> Dict[str, Any]:
    return envelopes_for_matches(db, [match], forecasts, now=now)[match.id]


def envelope_for_snapshot(snapshot: ProviderForecastSnapshot, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Markets rebuilt from one historical snapshot, stamped with the snapshot's own times."""
    if not isinstance(snapshot.raw_payload, dict):
        return no_forecast_envelope(str(snapshot.match_id), {"state": "unavailable", "reason": "the snapshot holds no payload"}, now)
    return markets_for_forecast(
        match_id=str(snapshot.match_id), event=snapshot.raw_payload, provider=snapshot.provider,
        record_id=None, snapshot_id=str(snapshot.id), captured_before_kickoff=snapshot.captured_before_kickoff,
        retrieved_at=snapshot.first_fetched_at, model_run_at=snapshot.model_run_at,
        provider_updated_at=snapshot.provider_updated_at,
        freshness={"state": "snapshot", "reason": "rebuilt from a stored snapshot, not refreshed"}, now=now)
