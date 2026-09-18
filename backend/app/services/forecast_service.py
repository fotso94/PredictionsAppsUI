"""
Third-party forecast synchronisation and freshness rules.

Forecasts are fetched per covered competition within the provider's daily budget, matched to
internal matches with `match_matching.find_match` (provider refs first, then competition + teams
+ kickoff), and stored in `provider_forecasts`. Ambiguous or unmatched forecasts are counted and
logged but never attached.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.predictions import Match, MatchStatus, Team
from app.models.provider_data import ProviderForecastRecord, ProviderForecastSnapshot
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
#: What ONE competition's turn actually fetched, kept under that competition's own key.
#:
#: `STATUS_KEY` holds the last run of any kind and is rewritten by every later code path, including
#: the cooling-down early return that makes no provider request at all. That is how the only real
#: fetch of a day gets erased by a no-op hours later, leaving a fixture with no record that can say
#: whether the provider returned it. This key is written ONLY by a turn that actually called the
#: provider, so an unrelated later pass cannot overwrite it, and it carries the retrieval time and
#: the window it covered so a reader can tell a record that is older than the fixture it would
#: explain from one that is not.
COMPETITION_STATUS_KEY = "forecast:status:{provider}:{key}"
COMPETITION_STATUS_TTL_SECONDS = 7 * 24 * 3600
PENDING_KEY = "forecast:pending:{provider}:{key}"
COOLDOWN_KEY = "forecast:cooldown:{provider}"
SYNC_LOCK_KEY = "forecast:sync_lock:{provider}"
SYNC_LOCK_TTL_SECONDS = 300

_UNSET = object()
AUTH_COOLDOWN_SECONDS = 30 * 60
UNAVAILABLE_COOLDOWN_SECONDS = 2 * 60


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - now).total_seconds()), 60)
PENDING_TTL_SECONDS = 48 * 3600

_DATETIME_FIELDS = ("kickoff_utc", "model_run_at", "provider_updated_at", "fetched_at")


# ------------------------------------------------------- which snapshot is "the" snapshot
#: The order of forecast evidence: oldest first, so the newest version of it is the last row.
#:
#: ``first_fetched_at`` decides, and stays the primary key of the decision: the forecast a reader
#: saw is the one the provider last published before they looked. It is not unique, and that is not
#: corruption. The migration that backfilled this table stamped its one row per forecast with the
#: record's retrieval time, and ``scripts/repair_forecasts.py`` appends its corrected re-reading of
#: the same payload under the SAME retrieval time deliberately, because a repair retrieves nothing
#: and must not move the clock forward. Rows that share a retrieval time therefore describe a single
#: retrieval, and the row written last is the corrected reading of it - so ``created_at`` breaks the
#: tie, and the later-created row wins.
#:
#: ``id`` closes the order. ``created_at`` comes from a Python-side default, so two rows written in
#: one transaction can carry the same value to the microsecond; with no unique final key the
#: database is free to return such rows in any order it likes, and "any order it likes" changes
#: when a row is updated and rewritten elsewhere in the heap. That is exactly the failure this
#: ordering exists to prevent: scoring picked one twin, the performance read picked the other, and
#: a scored forecast was reported as still pending.
SNAPSHOT_ORDER = (
    ProviderForecastSnapshot.first_fetched_at.asc(),
    ProviderForecastSnapshot.created_at.asc(),
    ProviderForecastSnapshot.id.asc(),
)


def order_snapshots(query):
    """Apply :data:`SNAPSHOT_ORDER` to a snapshot query. The one place that orders this table."""
    return query.order_by(*SNAPSHOT_ORDER)


def choose_snapshots(query) -> Dict[Tuple[uuid.UUID, str], ProviderForecastSnapshot]:
    """The chosen snapshot per (match, provider) out of an already-filtered snapshot query.

    The single place in the codebase that answers "which snapshot is the forecast?". Callers differ
    only in what they filter to - settlement scores prematch snapshots, a resync compares against
    the newest one of any kind - and never in how the winner is picked, because a scorer and a
    reader that disagree about the row produce a score that the page cannot find.

    Cost: one indexed query over the rows the caller filtered to, read rather than reduced in SQL.
    The table holds one row per distinct forecast content per match and provider - a handful - so
    the alternative, a per-key DISTINCT ON, would buy nothing and split the rule into SQL.
    """
    chosen: Dict[Tuple[uuid.UUID, str], ProviderForecastSnapshot] = {}
    for row in order_snapshots(query).all():
        chosen[(row.match_id, row.provider)] = row  # oldest first, so the newest row lands last
    return chosen


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


#: Values that define a distinct forecast. Two payloads with the same values are the same evidence.
_SNAPSHOT_FIELDS = (
    "home_prob", "draw_prob", "away_prob", "btts_yes_prob", "btts_no_prob",
    "over_25_prob", "under_25_prob", "over_35_prob", "under_35_prob",
    "exact_score", "exact_score_other_prob", "recommended_bets", "reasoning", "confidence",
)


def content_hash(forecast: ProviderForecast) -> str:
    """Stable hash of a forecast's values, used to tell a genuinely new snapshot from a re-fetch."""
    payload = {name: getattr(forecast, name) for name in _SNAPSHOT_FIELDS}
    payload["model_run_at"] = forecast.model_run_at.isoformat() if forecast.model_run_at else None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _retrieved_at(forecast: ProviderForecast, fallback: datetime) -> datetime:
    """When this forecast actually came off the wire.

    Stamping the attach moment instead would make a forecast replayed from the pending cache two
    days later look like it was just retrieved, and freshness is judged on this value.
    """
    return getattr(forecast, "fetched_at", None) or fallback


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
        self._lock_token = uuid.uuid4().hex
        self._cooldown_cache: Any = _UNSET

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

    def sync_order(self) -> List[str]:
        """Covered competitions, least recently synced first.

        The daily allowance (10 requests on the GameForecastAPI free plan) is usually too small for
        all six competitions in one run. Always starting at the head of the configured list would
        spend the whole allowance on the same leagues and never reach the tail, so the competitions
        that did not get their turn yesterday go first today. Never-synced competitions come first.
        """
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return sorted(self.keys, key=lambda key: (self._last_sync(key) or epoch, self.keys.index(key)))

    def _budget_remaining(self) -> Optional[int]:
        budget = getattr(self.provider, "budget", None)
        if budget is None or not getattr(budget, "daily_limit", 0):
            return None
        try:
            return budget.remaining()
        except Exception:  # pragma: no cover - budget is best effort
            return None

    def _turn_cost(self, key: str) -> int:
        """How many outbound requests this competition's turn will cost, before it is started.

        Only the provider knows, because only it knows whether it still has to discover the
        competition's league id: that discovery is a second request, paid BEFORE the fetch. A
        provider that does not price its turns is charged one, which is what the gate assumed for
        every competition before - and why a turn that needed two could be started with one left.
        """
        price = getattr(self.provider, "request_cost", None)
        if not callable(price):
            return 1
        try:
            return max(int(price(key)), 0)
        except Exception as exc:  # pragma: no cover - pricing must never break a sync
            logger.debug("Could not price the %s turn for %s (%s); assuming one request",
                         getattr(self.provider, "name", "provider"), key, exc)
            return 1

    def _unaffordable(self, key: str, remaining: Optional[int]) -> Optional[str]:
        """Why this competition's turn cannot be started now, or None when it can be paid for.

        The turn is all-or-nothing. Starting one whose discovery fits but whose fetch does not
        spends the last unit on a league id and returns no forecast at all, which is worse than
        not starting: the allowance is gone and the competition is no better off. So the whole
        cost has to fit, and when it does not the pass stops here rather than half-spending.

        It stops rather than moving on to a cheaper competition behind it. Letting price decide
        the order would put an expensive competition permanently last, and permanently last with
        a small daily allowance means never fetched. The starved competition keeps its place at
        the head of the next run, which is the only thing that eventually feeds it.
        """
        if remaining is None:
            return None
        cost = self._turn_cost(key)
        if cost == 0 or remaining >= cost:
            return None
        detail = "a league-id discovery and then a fetch" if cost > 1 else "a fetch"
        return (f"{self.provider.name}'s remaining daily allowance ({remaining}) cannot cover the "
                f"next competition's turn: {key} costs {cost} request(s) ({detail}). Stopped "
                f"rather than spending part of it, and rather than reordering by price, which "
                f"would starve {key} permanently")

    def ensure_synced(self, days_ahead: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        """Sync every covered competition whose last sync is older than the configured interval."""
        report: Dict[str, Any] = {"provider": self.provider.name if self.provider else None, "competitions": {}, "skipped": []}
        if not self.provider:
            report["error"] = "no prediction provider configured"
            return report
        interval = timedelta(hours=settings.GAMEFORECAST_SYNC_INTERVAL_HOURS)
        days_ahead = days_ahead or settings.GAMEFORECAST_SYNC_DAYS_AHEAD
        report["retried"] = {}
        report["deferred"] = []
        # The memo exists so one page render does not ask Redis the same question thirty times.
        # A sync is a new operation, so it re-reads: another worker may have paused the provider since.
        self._cooldown_cache = _UNSET
        cooling = self._cooldown_reason()
        if cooling:
            # No provider calls while paused, but forecasts fetched earlier can still be attached to
            # fixtures that appeared (or became matchable) since.
            self._retry_all_pending(self.keys, report)
            report["error"] = f"skipped (recent failure: {cooling})"
            report["paused"] = True
            report["synced_at"] = self.now.isoformat()
            self._record_status(report)
            return report
        order = self.sync_order()
        report["order"] = order
        if not self._acquire_sync_lock():
            # Another worker is already spending the allowance. Attaching cached forecasts is free,
            # so that still runs; nothing is fetched twice.
            report["error"] = f"a {self.provider.name} sync is already running"
            self._retry_all_pending(order, report)
            report["synced_at"] = self.now.isoformat()
            return report
        stop_reason: Optional[str] = None
        try:
            for key in order:
                last = self._last_sync(key)
                if not force and last and self.now - last < interval:
                    report["skipped"].append(key)
                    continue
                unaffordable = self._unaffordable(key, self._budget_remaining())
                if unaffordable:
                    # Stop before reserving anything: what is left cannot pay for this turn in
                    # full, and the competitions that did not get their turn - this one first -
                    # keep their place at the head of tomorrow's order.
                    stop_reason = unaffordable
                    self._pause(stop_reason, _seconds_until_utc_midnight(self.now))
                    break
                try:
                    # Forecasts can only be attached to fixtures we know about: fill the calendar first
                    # (cached, one provider request per competition at most every few hours).
                    fixture_errors = self._ensure_fixtures(key, days_ahead)
                    report["competitions"][key] = self.sync_competition(
                        key, self.now.date(), self.now.date() + timedelta(days=days_ahead))
                    if fixture_errors:
                        report["competitions"][key]["fixture_errors"] = fixture_errors
                    self._mark_synced(key)
                except ProviderNotConfiguredError as exc:
                    stop_reason = str(exc)
                    break
                except ProviderError as exc:
                    report["competitions"][key] = {"error": str(exc)}
                    logger.warning("Forecast sync for %s failed: %s", key, exc)
                    # quota/auth failures affect every competition: stop here and back off
                    seconds = _seconds_until_utc_midnight(self.now) if isinstance(exc, ProviderQuotaError) else (
                        AUTH_COOLDOWN_SECONDS if isinstance(exc, ProviderAuthError) else UNAVAILABLE_COOLDOWN_SECONDS)
                    stop_reason = str(exc)
                    self._pause(stop_reason, seconds)
                    break
        finally:
            self._release_sync_lock()
        # Whatever stopped the run, forecasts already paid for can still be attached to fixtures that
        # exist now. This costs no provider request, so it must happen on every path - especially the
        # path where the allowance ran out, which is exactly when the cache is all there is.
        self._retry_all_pending(order, report)
        if stop_reason:
            # A competition whose own request failed was not synced either: it belongs at the head of
            # the next run just like the ones that were never reached.
            succeeded = {k for k, v in report["competitions"].items() if not (isinstance(v, dict) and v.get("error"))}
            deferred = [k for k in order if k not in succeeded and k not in report["skipped"]]
            report["deferred"] = deferred
            report["error"] = stop_reason + (
                f"; {len(deferred)} competition(s) deferred to the next reset" if deferred else "")
        report["synced_at"] = self.now.isoformat()
        self._record_status(report)
        return report

    def _retry_all_pending(self, keys: List[str], report: Dict[str, Any]) -> None:
        """Attach every cached unmatched forecast we already paid for. Makes no provider request."""
        for key in keys:
            try:
                retried = self._retry_pending(key)
            except Exception as exc:  # a broken cache entry must not abort the whole run
                logger.warning("Retrying pending forecasts for %s failed: %s", key, exc)
                continue
            if retried:
                report.setdefault("retried", {})[key] = retried

    def _pause(self, reason: str, seconds: int) -> None:
        self.cache.set(COOLDOWN_KEY.format(provider=self.provider.name), {"reason": reason},
                       ttl=seconds, stale_ttl=seconds)
        self._cooldown_cache = reason

    # ------------------------------------------------------------------ concurrency
    def _acquire_sync_lock(self) -> bool:
        """Stop two workers both deciding a competition is due and each paying for it.

        Best effort: without Redis there is nothing to coordinate through and the sync proceeds.
        """
        client = getattr(self.cache, "_redis", lambda: None)()
        if client is None or not self.provider:
            return True
        try:
            return bool(client.set(SYNC_LOCK_KEY.format(provider=self.provider.name),
                                   self._lock_token, nx=True, ex=SYNC_LOCK_TTL_SECONDS))
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.debug("Sync lock unavailable (%s); proceeding without it", exc)
            return True

    def _release_sync_lock(self) -> None:
        client = getattr(self.cache, "_redis", lambda: None)()
        if client is None or not self.provider:
            return
        key = SYNC_LOCK_KEY.format(provider=self.provider.name)
        try:
            # compare-and-delete so a lock that already expired and was retaken is not released here
            if client.get(key) in (self._lock_token, self._lock_token.encode("utf-8")):
                client.delete(key)
        except Exception:  # pragma: no cover
            pass

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
        # Free first: fixtures may have appeared since the last run, so attach what we already paid for
        # before spending anything. Without this the retry never runs on the path that actually fetches.
        retried = self._retry_pending(key)
        forecasts = self.provider.get_forecasts(key, date_from, date_to)
        league = self.registry.ensure_canonical_league(key)
        stats: Dict[str, Any] = {"fetched": len(forecasts), "attached": 0, "ambiguous": 0, "unmatched": 0,
                                 "without_markets": 0, "details": []}
        if retried:
            stats["retried"] = retried
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
        self._record_competition_fetch(key, stats)
        return stats

    def _record_competition_fetch(self, key: str, stats: Dict[str, Any]) -> None:
        """Retain what this competition's turn actually fetched, under its own key.

        Written here and nowhere else, so only a turn that really called the provider leaves a
        record: a cooling-down early return, a run that skipped this competition as not due, and a
        turn whose request failed (this is never reached, the exception propagates) all leave the
        last real record standing instead of replacing it with a no-op.

        Bounded by construction: the provider's own report names discarded events by id, teams and
        reason up to its cap and never carries a payload, this adds counters only, and the key
        expires. Six covered competitions means at most six of these.
        """
        if not self.provider:
            return
        reported = getattr(self.provider, "last_fetch", None)
        # Only a report that names THIS competition is used. A report left over from another
        # competition's turn would attribute one response's events to a different league, and a
        # reader would then evidence "the provider did not return this fixture" from a listing
        # that was never about it. Mis-attributed evidence is worse than none.
        if not (isinstance(reported, dict) and reported.get("key") == key):
            reported = None
        record: Dict[str, Any] = dict(reported) if reported else {}
        record.setdefault("provider", self.provider.name)
        record.setdefault("key", key)
        # The provider stamps the moment the response was read. Only a provider that reports
        # nothing falls back to now, and a record with no real retrieval time can still be placed
        # against a fixture row by the reader, who checks this field before trusting anything else.
        record.setdefault("fetched_at", self.now.isoformat())
        record["recorded_at"] = self.now.isoformat()
        for name in ("fetched", "attached", "unmatched", "ambiguous", "without_markets"):
            record[name] = stats.get(name, 0)
        self.cache.set(COMPETITION_STATUS_KEY.format(provider=self.provider.name, key=key), record,
                       ttl=COMPETITION_STATUS_TTL_SECONDS, stale_ttl=COMPETITION_STATUS_TTL_SECONDS)

    # ------------------------------------------------------------------ pending (unmatched) forecasts
    def _pending_key(self, key: str) -> str:
        return PENDING_KEY.format(provider=self.provider.name if self.provider else "none", key=key)

    def _store_pending(self, key: str, pending: List[Dict[str, Any]], replace: bool = False) -> None:
        """Keep unmatched forecasts so they can be attached later without paying for them again.

        Merged by provider event id rather than replaced: a fetch that covers the next seven days
        must not discard a forecast for day eight that an earlier fetch already paid for out of a
        ten-request daily allowance.
        """
        pending_key = self._pending_key(key)
        merged: Dict[str, Dict[str, Any]] = {}
        if not replace:
            for item in (self.cache.get(pending_key) or []):
                if isinstance(item, dict) and item.get("external_event_id"):
                    merged[str(item["external_event_id"])] = item
        for item in pending:
            if item.get("external_event_id"):
                merged[str(item["external_event_id"])] = item
        if merged:
            self.cache.set(pending_key, list(merged.values()), ttl=PENDING_TTL_SECONDS, stale_ttl=PENDING_TTL_SECONDS)
        else:
            self.cache.delete(pending_key)

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
        # `still_pending` is the full remaining set, so this call replaces rather than merges
        self._store_pending(key, still_pending, replace=True)
        return counts

    def attach_forecast(self, forecast: ProviderForecast, key: str, league_id) -> Dict[str, Any]:
        if not forecast.has_any_market():
            return {"result": "without_markets", "event": forecast.external_event_id}
        # 1. previously linked event id -> same match (survives rescheduling)
        match = self.registry.match_by_ref(forecast.provider, forecast.external_event_id)
        confidence, matched_by = "exact", "provider_id"
        if match is not None and not self._ref_still_describes(match, forecast):
            # Provider event ids are small integers and get recycled between seasons. A ref that no
            # longer names the same teams is not evidence, so the forecast is refused rather than
            # attached to whatever match happens to hold that id.
            logger.warning("Forecast %s claims match %s but names %s vs %s; refusing to attach",
                           forecast.external_event_id, match.id, forecast.home_name, forecast.away_name)
            return {"result": "ambiguous", "event": forecast.external_event_id, "home": forecast.home_name,
                    "away": forecast.away_name,
                    "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None,
                    "reason": "provider event id no longer names the same teams in the same order",
                    "candidates": [str(match.id)]}
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
            if match is None:
                # The candidate came from this same session, so it should still be there. If it is
                # not - deleted underneath us, or a stale id - refusing is the only safe answer:
                # attaching a forecast to a match we cannot load is exactly the uncertain association
                # this whole path exists to prevent.
                logger.warning("Forecast %s matched match %s, which no longer exists; refusing to attach",
                               forecast.external_event_id, decision.match_id)
                return {"result": "unmatched", "event": forecast.external_event_id, "home": forecast.home_name,
                        "away": forecast.away_name,
                        "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None,
                        "reason": "matched match no longer exists", "candidates": [decision.match_id]}
            confidence, matched_by = decision.confidence, "name_kickoff"
            self.registry.set_ref("match", match.id, forecast.provider, forecast.external_event_id, confidence=confidence,
                                  matched_by=matched_by, metadata={"home": forecast.home_name, "away": forecast.away_name,
                                                                   "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None})
        self._upsert_record(match, forecast, confidence, matched_by)
        return {"result": "attached", "event": forecast.external_event_id, "match_id": str(match.id)}

    def _ref_still_describes(self, match: Match, forecast: ProviderForecast) -> bool:
        """Does the match a provider id points at still have the teams, in the order, just named?

        The orientation has to agree, not just the pair of names. Two reasons:

        - every probability is orientation-bound. Attaching a forecast listed the other way round
          would put the away side's win probability on the home side, which is worse than having no
          forecast at all.
        - in a two-legged tie, Liverpool v Everton and Everton v Liverpool are different matches, so
          a reversed pair is not evidence that this is the same fixture.

        The owner's rule is to reject a swapped fixture rather than guess, so a reversed listing
        fails this check and the forecast is refused.
        """
        if not forecast.home_name or not forecast.away_name:
            return True  # nothing to check against; the ref stands
        home = self.db.query(Team).filter(Team.id == match.home_team_id).first()
        away = self.db.query(Team).filter(Team.id == match.away_team_id).first()
        if home is None or away is None:
            return True
        return (match_matching.team_names_match(forecast.home_name, home.name)
                and match_matching.team_names_match(forecast.away_name, away.name))

    def _upsert_record(self, match: Match, forecast: ProviderForecast, confidence: str, matched_by: str) -> ProviderForecastRecord:
        record = self.db.query(ProviderForecastRecord).filter(
            ProviderForecastRecord.match_id == match.id, ProviderForecastRecord.provider == forecast.provider).first()
        if record is None:
            record = ProviderForecastRecord(id=uuid.uuid4(), match_id=match.id, provider=forecast.provider,
                                            external_event_id=forecast.external_event_id, match_confidence=confidence,
                                            matched_by=matched_by,
                                            fetched_at=_naive(_retrieved_at(forecast, self.now)))
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
        record.exact_score_other_prob = _dec(forecast.exact_score_other_prob)
        record.recommended_bets = forecast.recommended_bets
        record.reasoning = forecast.reasoning
        record.confidence = _dec(forecast.confidence)
        record.anomalies = forecast.anomalies or None
        record.match_confidence = confidence
        record.matched_by = matched_by
        record.model_run_at = _naive(forecast.model_run_at)
        record.provider_updated_at = _naive(forecast.provider_updated_at)
        record.fetched_at = _naive(_retrieved_at(forecast, self.now))
        record.raw_payload = forecast.raw or None
        self._record_snapshot(match, forecast, confidence, matched_by)
        self.db.flush()
        return record

    def _record_snapshot(self, match: Match, forecast: ProviderForecast, confidence: str,
                         matched_by: str) -> ProviderForecastSnapshot:
        """Append this forecast to the evidence history, or mark the existing one as seen again.

        A forecast is the record of what a model said before a match was played, so the current-row
        update must never be the only trace. Unchanged content only moves `last_fetched_at`, which
        keeps the table proportional to how often the model actually changes its mind.
        """
        digest = content_hash(forecast)
        retrieved = _naive(_retrieved_at(forecast, self.now))
        # The same "which snapshot is the forecast?" question settlement asks, so it goes through
        # the same helper: comparing new content against one twin while settlement scores the other
        # is how a duplicate snapshot gets appended for content that had not changed at all.
        latest = choose_snapshots(
            self.db.query(ProviderForecastSnapshot)
            .filter(ProviderForecastSnapshot.match_id == match.id,
                    ProviderForecastSnapshot.provider == forecast.provider)
        ).get((match.id, forecast.provider))
        now = _naive(self.now)
        if latest is not None and self._same_content(latest, forecast, digest):
            latest.content_hash = digest  # backfilled rows carry no hash until they are seen again
            latest.last_fetched_at = retrieved or now
            return latest
        kickoff = _naive(_aware_utc(match.match_date)) if match.match_date else None
        snapshot = ProviderForecastSnapshot(
            id=uuid.uuid4(), match_id=match.id, provider=forecast.provider,
            external_event_id=forecast.external_event_id, content_hash=digest,
            home_win_prob=_dec(forecast.home_prob), draw_prob=_dec(forecast.draw_prob),
            away_win_prob=_dec(forecast.away_prob),
            btts_yes_prob=_dec(forecast.btts_yes_prob), btts_no_prob=_dec(forecast.btts_no_prob),
            total_goals_over_25_prob=_dec(forecast.over_25_prob),
            total_goals_under_25_prob=_dec(forecast.under_25_prob),
            total_goals_over_35_prob=_dec(forecast.over_35_prob),
            total_goals_under_35_prob=_dec(forecast.under_35_prob),
            exact_score=forecast.exact_score,
            exact_score_other_prob=_dec(forecast.exact_score_other_prob),
            recommended_bets=forecast.recommended_bets, reasoning=forecast.reasoning,
            confidence=_dec(forecast.confidence), anomalies=forecast.anomalies or None,
            match_confidence=confidence, matched_by=matched_by,
            model_run_at=_naive(forecast.model_run_at),
            provider_updated_at=_naive(forecast.provider_updated_at),
            first_fetched_at=retrieved or now, last_fetched_at=retrieved or now, kickoff_at_capture=kickoff,
            # NULL when the kickoff was not known: a stored False would assert "not prematch",
            # which is a claim we cannot make.
            captured_before_kickoff=((retrieved or now) < kickoff) if kickoff else None,
            raw_payload=forecast.raw or None,
        )
        self.db.add(snapshot)
        return snapshot

    @staticmethod
    def _same_content(snapshot: ProviderForecastSnapshot, forecast: ProviderForecast, digest: str) -> bool:
        if snapshot.content_hash:
            return snapshot.content_hash == digest
        # Rows backfilled by the migration have no hash: compare the stored values instead.
        pairs = (
            (snapshot.home_win_prob, forecast.home_prob), (snapshot.draw_prob, forecast.draw_prob),
            (snapshot.away_win_prob, forecast.away_prob),
            (snapshot.btts_yes_prob, forecast.btts_yes_prob), (snapshot.btts_no_prob, forecast.btts_no_prob),
            (snapshot.total_goals_over_25_prob, forecast.over_25_prob),
            (snapshot.total_goals_under_25_prob, forecast.under_25_prob),
            (snapshot.total_goals_over_35_prob, forecast.over_35_prob),
            (snapshot.total_goals_under_35_prob, forecast.under_35_prob),
            (snapshot.exact_score_other_prob, forecast.exact_score_other_prob),
        )
        for stored, fresh in pairs:
            if (stored is None) != (fresh is None):
                return False
            if stored is not None and abs(float(stored) - float(fresh)) > 1e-6:
                return False
        return (snapshot.exact_score or None) == (forecast.exact_score or None) and \
               _naive(forecast.model_run_at) == snapshot.model_run_at

    def snapshots_for_match(self, match_id, provider_name: Optional[str] = None) -> List[ProviderForecastSnapshot]:
        """Full forecast history for a match, oldest first. Evidence for later evaluation.

        Ordered by :data:`SNAPSHOT_ORDER`, so the last row of this history is the row settlement
        scores: a reader scrolling to the bottom of the evidence sees the forecast that was scored.
        """
        query = self.db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.match_id == match_id)
        name = provider_name or (self.provider.name if self.provider else settings.PREDICTION_PROVIDER)
        if name and name != "none":
            query = query.filter(ProviderForecastSnapshot.provider == name)
        return order_snapshots(query).all()

    # ------------------------------------------------------------------ reads
    def forecast_for_match(self, match: Match, provider_name: Optional[str] = None) -> Optional[ProviderForecastRecord]:
        query = self.db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == match.id)
        name = provider_name or (self.provider.name if self.provider else settings.PREDICTION_PROVIDER)
        if name and name != "none":
            query = query.filter(ProviderForecastRecord.provider == name)
        return query.order_by(ProviderForecastRecord.fetched_at.desc()).first()

    def _cooldown_reason(self) -> Optional[str]:
        """Why forecast refreshes are paused, or None. Read once per service instance.

        A page renders thirty matches; each one must not hit Redis for the same answer.
        """
        if self._cooldown_cache is _UNSET:
            reason = None
            if self.provider:
                cooling = self.cache.get(COOLDOWN_KEY.format(provider=self.provider.name))
                if isinstance(cooling, dict):
                    reason = cooling.get("reason")
            self._cooldown_cache = reason
        return self._cooldown_cache

    def freshness(self, record: Optional[ProviderForecastRecord], match: Match) -> Dict[str, Any]:
        """Never present an old forecast as current: report stale/kickoff_passed explicitly.

        A paused refresh is reported separately from an absent forecast. "We cannot refresh this
        right now" and "no such forecast exists" are different statements, and only one of them is
        a reason to distrust the number on screen.
        """
        paused = self._cooldown_reason()
        if record is None:
            if paused:
                return {"state": "unavailable", "reason": "no forecast for this match",
                        "refresh_blocked": True, "refresh_blocked_reason": paused}
            return {"state": "unavailable", "reason": "no forecast for this match", "refresh_blocked": False}
        extra: Dict[str, Any] = {"refresh_blocked": bool(paused)}
        if paused:
            extra["refresh_blocked_reason"] = paused
        now = self.now
        kickoff = _aware_utc(match.match_date)
        if match.status == MatchStatus.FINISHED or (kickoff + timedelta(minutes=150) < now):
            return {"state": "kickoff_passed",
                    "reason": "match already played; forecast shown for reference only", **extra}
        generated = record.model_run_at or record.provider_updated_at or record.fetched_at
        if generated is not None:
            age = now - _aware_utc(generated)
            if age > timedelta(hours=settings.FORECAST_MAX_AGE_HOURS):
                hours = int(age.total_seconds() // 3600)
                reason = f"forecast generated {hours} h ago"
                if paused:
                    reason += "; refresh is paused, so it cannot be updated yet"
                return {"state": "stale", "reason": reason, **extra}
        return {"state": "available", "reason": None, **extra}

    def clear_cooldown(self) -> None:
        self._cooldown_cache = _UNSET
        if self.provider:
            self.cache.delete(COOLDOWN_KEY.format(provider=self.provider.name))

    def status(self) -> Dict[str, Any]:
        provider = self.provider
        payload = {"active_provider": settings.PREDICTION_PROVIDER, "configured": bool(provider and provider.is_configured()),
                   "integration_status": provider.integration_status if provider else None}
        if provider:
            budget = getattr(provider, "budget", None)
            payload["budget"] = budget.snapshot() if budget else None
            payload["last_sync"] = self.cache.get(STATUS_KEY.format(provider=provider.name))
            payload["cooling_down"] = self._cooldown_reason()
        return payload
