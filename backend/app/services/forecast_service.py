"""
Third-party forecast synchronisation and freshness rules.

Forecasts are fetched per covered competition within the provider's daily budget, matched to
internal matches with `match_matching.find_match` (provider refs first, then competition + teams
+ kickoff), and stored in `provider_forecasts`. Ambiguous or unmatched forecasts are counted and
logged but never attached.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.predictions import Match, MatchStatus
from app.models.provider_data import ProviderForecastRecord
from app.services import match_matching
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry, _aware_utc
from app.services.providers import competitions as comps
from app.services.providers.base import (
    ProviderQuotaError,
    ProviderAuthError,
    parse_utc,
    ForecastProvider, ProviderError, ProviderForecast, ProviderNotConfiguredError,
)
from app.services.providers.registry import forecast_provider as default_forecast_provider

if TYPE_CHECKING:  # pragma: no cover
    from app.services.match_data_service import MatchDataService

logger = logging.getLogger(__name__)

LAST_SYNC_KEY = "forecast:last_sync:{provider}:{key}"
STATUS_KEY = "forecast:status:{provider}"
PENDING_KEY = "forecast:pending:{provider}:{key}"
COOLDOWN_KEY = "forecast:cooldown:{provider}"
AUTH_COOLDOWN_SECONDS = 10 * 60
UNAVAILABLE_COOLDOWN_SECONDS = 2 * 60


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - now).total_seconds()), 60)
PENDING_TTL_SECONDS = 48 * 3600

_DATETIME_FIELDS = ("kickoff_utc", "model_run_at", "provider_updated_at")


def _forecast_to_dict(forecast: ProviderForecast) -> Dict[str, Any]:
    data = asdict(forecast)
    for field_name in _DATETIME_FIELDS:
        value = data.get(field_name)
        data[field_name] = value.isoformat() if isinstance(value, datetime) else value
    return data


def _forecast_from_dict(data: Dict[str, Any]) -> ProviderForecast:
    payload = dict(data)
    for field_name in _DATETIME_FIELDS:
        payload[field_name] = parse_utc(payload.get(field_name)) if payload.get(field_name) else None
    return ProviderForecast(**payload)


def _dec(value: Optional[float]) -> Optional[Decimal]:
    return Decimal(str(round(value, 4))) if value is not None else None


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


class ForecastService:
    def __init__(self, db: Session, provider: Optional[ForecastProvider] = None, cache: Optional[MatchCache] = None,
                 now: Optional[datetime] = None, keys: Optional[List[str]] = None, use_default_provider: bool = True,
                 fixtures: Optional["MatchDataService"] = None, sync_fixtures: bool = True):
        self.db = db
        self.registry = MatchRegistry(db)
        self.cache = cache or MatchCache()
        self._provider = provider
        self._use_default = use_default_provider and provider is None
        self._now = now
        self.keys = keys or comps.covered_keys(settings.COVERED_COMPETITIONS)
        self._fixtures = fixtures
        self._sync_fixtures = sync_fixtures

    @property
    def fixtures(self) -> Optional["MatchDataService"]:
        """Match-data service used to make sure fixtures exist before forecasts are attached."""
        if self._fixtures is None and self._sync_fixtures:
            from app.services.match_data_service import MatchDataService
            self._fixtures = MatchDataService(self.db, cache=self.cache, now=self._now, keys=self.keys)
        return self._fixtures

    @property
    def now(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    @property
    def provider(self) -> Optional[ForecastProvider]:
        if self._provider is None and self._use_default:
            self._provider = default_forecast_provider()
            self._use_default = False
        return self._provider

    # ------------------------------------------------------------------ sync
    def _last_sync(self, key: str) -> Optional[datetime]:
        if not self.provider:
            return None
        value = self.cache.get(LAST_SYNC_KEY.format(provider=self.provider.name, key=key))
        return datetime.fromisoformat(value) if value else None

    def _mark_synced(self, key: str) -> None:
        if self.provider:
            self.cache.set(LAST_SYNC_KEY.format(provider=self.provider.name, key=key), self.now.isoformat(),
                           ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)

    def _record_status(self, report: Dict[str, Any]) -> None:
        if self.provider:
            self.cache.set(STATUS_KEY.format(provider=self.provider.name), report, ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)

    def ensure_synced(self, days_ahead: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        """Sync every covered competition whose last sync is older than the configured interval."""
        report: Dict[str, Any] = {"provider": self.provider.name if self.provider else None, "competitions": {}, "skipped": []}
        if not self.provider:
            report["error"] = "no prediction provider configured"
            return report
        interval = timedelta(hours=settings.GAMEFORECAST_SYNC_INTERVAL_HOURS)
        days_ahead = days_ahead or settings.GAMEFORECAST_SYNC_DAYS_AHEAD
        report["retried"] = {}
        cooling = self.cache.get(COOLDOWN_KEY.format(provider=self.provider.name))
        if isinstance(cooling, dict) and cooling.get("reason"):
            report["error"] = f"skipped (recent failure: {cooling['reason']})"
            report["synced_at"] = self.now.isoformat()
            return report
        for key in self.keys:
            last = self._last_sync(key)
            if not force and last and self.now - last < interval:
                report["skipped"].append(key)
                # fixtures may have appeared since the last provider call: re-attach pending forecasts for free
                retried = self._retry_pending(key)
                if retried:
                    report["retried"][key] = retried
                continue
            try:
                # Forecasts can only be attached to fixtures we know about: fill the calendar first (cached,
                # one provider request per competition at most every few hours).
                fixture_errors = self._ensure_fixtures(key, days_ahead)
                report["competitions"][key] = self.sync_competition(key, self.now.date(), self.now.date() + timedelta(days=days_ahead))
                if fixture_errors:
                    report["competitions"][key]["fixture_errors"] = fixture_errors
                self._mark_synced(key)
            except ProviderNotConfiguredError as exc:
                report["error"] = str(exc)
                break
            except ProviderError as exc:
                report["competitions"][key] = {"error": str(exc)}
                logger.warning("Forecast sync for %s failed: %s", key, exc)
                # quota/auth failures affect every competition: stop here and back off
                seconds = _seconds_until_utc_midnight(self.now) if isinstance(exc, ProviderQuotaError) else (
                    AUTH_COOLDOWN_SECONDS if isinstance(exc, ProviderAuthError) else UNAVAILABLE_COOLDOWN_SECONDS)
                self.cache.set(COOLDOWN_KEY.format(provider=self.provider.name), {"reason": str(exc)}, ttl=seconds, stale_ttl=seconds)
                break
        report["synced_at"] = self.now.isoformat()
        self._record_status(report)
        return report

    def _ensure_fixtures(self, key: str, days_ahead: int) -> List[str]:
        fixtures = self.fixtures
        if fixtures is None:
            return []
        try:
            meta = fixtures.sync_upcoming(key, days_ahead)
            return list(meta.errors)
        except Exception as exc:  # fixture problems must not block forecast handling
            logger.warning("Fixture sync before forecasts failed for %s: %s", key, exc)
            return [str(exc)]

    def sync_competition(self, key: str, date_from: date, date_to: date) -> Dict[str, Any]:
        assert self.provider is not None
        forecasts = self.provider.get_forecasts(key, date_from, date_to)
        league = self.registry.ensure_canonical_league(key)
        stats = {"fetched": len(forecasts), "attached": 0, "ambiguous": 0, "unmatched": 0, "without_markets": 0, "details": []}
        pending: List[Dict[str, Any]] = []
        for forecast in forecasts:
            outcome = self.attach_forecast(forecast, key, league.id)
            stats[outcome["result"]] += 1
            if outcome["result"] != "attached":
                stats["details"].append({k: v for k, v in outcome.items() if k != "result"} | {"result": outcome["result"]})
            if outcome["result"] in ("unmatched", "ambiguous"):
                pending.append(_forecast_to_dict(forecast))
        self.db.commit()
        self._store_pending(key, pending)
        stats["details"] = stats["details"][:25]
        return stats

    # ------------------------------------------------------------------ pending (unmatched) forecasts
    def _pending_key(self, key: str) -> str:
        return PENDING_KEY.format(provider=self.provider.name if self.provider else "none", key=key)

    def _store_pending(self, key: str, pending: List[Dict[str, Any]]) -> None:
        if pending:
            self.cache.set(self._pending_key(key), pending, ttl=PENDING_TTL_SECONDS, stale_ttl=PENDING_TTL_SECONDS)
        else:
            self.cache.delete(self._pending_key(key))

    def _retry_pending(self, key: str) -> Optional[Dict[str, int]]:
        """Attach previously unmatched forecasts to fixtures that exist now. No provider request is made."""
        pending = self.cache.get(self._pending_key(key)) or []
        if not pending:
            return None
        league = self.registry.ensure_canonical_league(key)
        counts = {"pending": len(pending), "attached": 0}
        still_pending: List[Dict[str, Any]] = []
        for item in pending:
            forecast = _forecast_from_dict(item)
            outcome = self.attach_forecast(forecast, key, league.id)
            if outcome["result"] == "attached":
                counts["attached"] += 1
            elif outcome["result"] in ("unmatched", "ambiguous"):
                still_pending.append(item)
        self.db.commit()
        self._store_pending(key, still_pending)
        return counts

    def attach_forecast(self, forecast: ProviderForecast, key: str, league_id) -> Dict[str, Any]:
        if not forecast.has_any_market():
            return {"result": "without_markets", "event": forecast.external_event_id}
        # 1. previously linked event id -> same match (survives rescheduling)
        match = self.registry.match_by_ref(forecast.provider, forecast.external_event_id)
        confidence, matched_by = "exact", "provider_id"
        if match is None:
            # 2. competition + teams + kickoff
            candidates = self.registry.candidates_for(league_id, forecast.kickoff_utc, competition_key=key) if forecast.kickoff_utc else []
            decision = match_matching.find_match(forecast.home_name, forecast.away_name, forecast.kickoff_utc, key, candidates)
            if not decision.attached:
                result = "ambiguous" if decision.confidence == "ambiguous" else "unmatched"
                logger.info("Forecast %s (%s vs %s @ %s) not attached: %s", forecast.external_event_id, forecast.home_name,
                            forecast.away_name, forecast.kickoff_utc, decision.reason)
                return {"result": result, "event": forecast.external_event_id, "home": forecast.home_name,
                        "away": forecast.away_name, "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None,
                        "reason": decision.reason, "candidates": decision.candidate_ids}
            match = self.db.query(Match).filter(Match.id == uuid.UUID(decision.match_id)).first()
            confidence, matched_by = decision.confidence, "name_kickoff"
            self.registry.set_ref("match", match.id, forecast.provider, forecast.external_event_id, confidence=confidence,
                                  matched_by=matched_by, metadata={"home": forecast.home_name, "away": forecast.away_name,
                                                                   "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None})
        self._upsert_record(match, forecast, confidence, matched_by)
        return {"result": "attached", "event": forecast.external_event_id, "match_id": str(match.id)}

    def _upsert_record(self, match: Match, forecast: ProviderForecast, confidence: str, matched_by: str) -> ProviderForecastRecord:
        record = self.db.query(ProviderForecastRecord).filter(
            ProviderForecastRecord.match_id == match.id, ProviderForecastRecord.provider == forecast.provider).first()
        if record is None:
            record = ProviderForecastRecord(id=uuid.uuid4(), match_id=match.id, provider=forecast.provider,
                                            external_event_id=forecast.external_event_id, match_confidence=confidence,
                                            matched_by=matched_by, fetched_at=_naive(self.now))
            self.db.add(record)
        record.external_event_id = forecast.external_event_id
        record.home_win_prob = _dec(forecast.home_prob)
        record.draw_prob = _dec(forecast.draw_prob)
        record.away_win_prob = _dec(forecast.away_prob)
        record.btts_yes_prob = _dec(forecast.btts_yes_prob)
        record.btts_no_prob = _dec(forecast.btts_no_prob)
        record.total_goals_over_25_prob = _dec(forecast.over_25_prob)
        record.total_goals_under_25_prob = _dec(forecast.under_25_prob)
        record.total_goals_over_35_prob = _dec(forecast.over_35_prob)
        record.total_goals_under_35_prob = _dec(forecast.under_35_prob)
        record.exact_score = forecast.exact_score
        record.recommended_bets = forecast.recommended_bets
        record.reasoning = forecast.reasoning
        record.confidence = _dec(forecast.confidence)
        record.match_confidence = confidence
        record.matched_by = matched_by
        record.model_run_at = _naive(forecast.model_run_at)
        record.provider_updated_at = _naive(forecast.provider_updated_at)
        record.fetched_at = _naive(self.now)
        record.raw_payload = forecast.raw or None
        self.db.flush()
        return record

    # ------------------------------------------------------------------ reads
    def forecast_for_match(self, match: Match, provider_name: Optional[str] = None) -> Optional[ProviderForecastRecord]:
        query = self.db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == match.id)
        name = provider_name or (self.provider.name if self.provider else settings.PREDICTION_PROVIDER)
        if name and name != "none":
            query = query.filter(ProviderForecastRecord.provider == name)
        return query.order_by(ProviderForecastRecord.fetched_at.desc()).first()

    def freshness(self, record: Optional[ProviderForecastRecord], match: Match) -> Dict[str, Any]:
        """Never present an old forecast as current: report stale/kickoff_passed explicitly."""
        if record is None:
            return {"state": "unavailable", "reason": "no forecast for this match"}
        now = self.now
        kickoff = _aware_utc(match.match_date)
        if match.status == MatchStatus.FINISHED or (kickoff + timedelta(minutes=150) < now):
            return {"state": "kickoff_passed", "reason": "match already played; forecast shown for reference only"}
        generated = record.model_run_at or record.provider_updated_at or record.fetched_at
        if generated is not None:
            age = now - _aware_utc(generated)
            if age > timedelta(hours=settings.FORECAST_MAX_AGE_HOURS):
                return {"state": "stale", "reason": f"forecast generated {int(age.total_seconds() // 3600)} h ago"}
        return {"state": "available", "reason": None}

    def status(self) -> Dict[str, Any]:
        provider = self.provider
        payload = {"active_provider": settings.PREDICTION_PROVIDER, "configured": bool(provider and provider.is_configured()),
                   "integration_status": provider.integration_status if provider else None}
        if provider:
            budget = getattr(provider, "budget", None)
            payload["budget"] = budget.snapshot() if budget else None
            payload["last_sync"] = self.cache.get(STATUS_KEY.format(provider=provider.name))
            cooling = self.cache.get(COOLDOWN_KEY.format(provider=provider.name))
            payload["cooling_down"] = cooling.get("reason") if isinstance(cooling, dict) else None
        return payload
