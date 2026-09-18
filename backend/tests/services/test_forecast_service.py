"""
Forecast synchronisation behaviour: rotation, quota handling, evidence and freshness.

No database and no network. The forecast provider is a stub that counts calls, so every test here
asserts something about how the small daily allowance is spent and about what is stored as evidence.
"""

from datetime import date, datetime, timedelta, timezone
from typing import List
from unittest.mock import MagicMock

import pytest

from app.models.predictions import Match, MatchStatus
from app.models.provider_data import ProviderForecastRecord
from app.services.forecast_service import ForecastService, content_hash
from app.services.match_cache import MatchCache
from app.services.providers.base import ForecastProvider, ProviderForecast, ProviderQuotaError
from tests.providers.support import FakeRedis

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
KEYS = ["premier_league", "la_liga", "serie_a", "bundesliga", "ligue_1", "champions_league"]


class LockingFakeRedis(FakeRedis):
    """FakeRedis plus the SET NX EX used by the sync lock and the scan used by cache invalidation."""

    def set(self, key, value, nx=False, ex=None, **kwargs):
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def scan_iter(self, match=None, count=None):
        prefix = (match or "*").rstrip("*")
        return [k for k in list(self.store) if k.startswith(prefix)]


class StubForecastProvider(ForecastProvider):
    name = "stub"
    integration_status = "test"

    def __init__(self, per_key=None, budget_after=None):
        self._per_key = per_key or {}
        self.calls: List[str] = []
        self._budget_after = budget_after

    def is_configured(self):
        return True

    def get_forecasts(self, key, date_from, date_to):
        if self._budget_after is not None and len(self.calls) >= self._budget_after:
            raise ProviderQuotaError("Daily request budget for stub exhausted", provider=self.name)
        self.calls.append(key)
        return list(self._per_key.get(key, []))


def build(cache, provider=None, keys=None, now=NOW):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    service = ForecastService(db, provider=provider or StubForecastProvider(), cache=cache,
                              now=now, keys=keys or list(KEYS), sync_fixtures=False)
    service.registry = MagicMock()
    service.registry.ensure_canonical_league.return_value = MagicMock(id="league-1")
    return service


@pytest.fixture
def cache():
    return MatchCache(client=LockingFakeRedis())


# --------------------------------------------------------------------- rotation
def test_sync_order_puts_never_synced_competitions_first(cache):
    service = build(cache)
    for key in ("premier_league", "la_liga"):
        service._mark_synced(key)
    order = service.sync_order()
    assert order[:4] == ["serie_a", "bundesliga", "ligue_1", "champions_league"]


def test_sync_order_puts_the_least_recently_synced_first(cache):
    service = build(cache)
    for offset, key in enumerate(KEYS):
        service._now = NOW - timedelta(hours=len(KEYS) - offset)
        service._mark_synced(key)
    service._now = NOW
    assert service.sync_order() == KEYS  # oldest first, which is the original order here


def test_a_spent_allowance_defers_the_tail_and_it_goes_first_next_time(cache):
    """The competitions that did not get their turn must lead the next run, not be starved again."""
    provider = StubForecastProvider(budget_after=2)
    service = build(cache, provider=provider)
    report = service.ensure_synced(force=True)
    assert provider.calls == ["premier_league", "la_liga"]
    assert report["deferred"][0] == "serie_a"
    assert "champions_league" in report["deferred"]

    service.clear_cooldown()
    later = build(cache, provider=StubForecastProvider(), now=NOW + timedelta(days=1))
    assert later.sync_order()[0] == "serie_a"


# --------------------------------------------------------------------- pending forecasts
def test_pending_forecasts_are_merged_not_replaced(cache):
    """A later fetch covering a shorter window must not discard a forecast already paid for."""
    service = build(cache)
    service._store_pending("serie_a", [{"external_event_id": "1", "home_name": "A"}])
    service._store_pending("serie_a", [{"external_event_id": "2", "home_name": "B"}])
    stored = cache.get(service._pending_key("serie_a"))
    assert {item["external_event_id"] for item in stored} == {"1", "2"}


def test_pending_forecasts_are_retried_when_the_allowance_is_spent(cache):
    """Attaching a cached forecast costs nothing, so it must happen exactly when nothing can be fetched."""
    provider = StubForecastProvider(budget_after=0)
    service = build(cache, provider=provider)
    retried = []
    service._retry_pending = lambda key: retried.append(key) or {"pending": 1, "attached": 1}
    report = service.ensure_synced(force=True)
    assert provider.calls == []
    assert set(retried) == set(KEYS)
    assert report["retried"]


def test_pending_forecasts_are_retried_while_the_provider_is_paused(cache):
    service = build(cache)
    service._pause("allowance spent", 3600)
    retried = []
    service._retry_pending = lambda key: retried.append(key) or None
    report = service.ensure_synced(force=True)
    assert set(retried) == set(KEYS)
    assert report["paused"] is True


# --------------------------------------------------------------------- concurrency
def test_a_second_sync_does_not_spend_the_allowance_twice(cache):
    provider = StubForecastProvider()
    first = build(cache, provider=provider)
    assert first._acquire_sync_lock() is True

    second = build(cache, provider=provider)
    report = second.ensure_synced(force=True)
    assert provider.calls == []
    assert "already running" in report["error"]

    first._release_sync_lock()
    assert second._acquire_sync_lock() is True


# --------------------------------------------------------------------- freshness
def _record(**overrides):
    record = ProviderForecastRecord(
        provider="stub", external_event_id="1", match_confidence="exact", matched_by="provider_id",
        fetched_at=NOW.replace(tzinfo=None), model_run_at=NOW.replace(tzinfo=None))
    for name, value in overrides.items():
        setattr(record, name, value)
    return record


def _match(kickoff=NOW + timedelta(hours=6), status=MatchStatus.SCHEDULED):
    match = Match()
    match.match_date = kickoff.replace(tzinfo=None)
    match.status = status
    return match


def test_a_paused_refresh_is_reported_separately_from_an_absent_forecast(cache):
    service = build(cache)
    service._pause("daily request allowance for stub is spent", 3600)

    absent = service.freshness(None, _match())
    assert absent["state"] == "unavailable"
    assert absent["refresh_blocked"] is True

    present = service.freshness(_record(), _match())
    assert present["state"] == "available"
    assert present["refresh_blocked"] is True
    assert "allowance" in present["refresh_blocked_reason"]


def test_freshness_is_not_blocked_when_the_provider_is_healthy(cache):
    service = build(cache)
    assert service.freshness(_record(), _match())["refresh_blocked"] is False


def test_a_played_match_never_reports_its_forecast_as_current(cache):
    service = build(cache)
    state = service.freshness(_record(), _match(kickoff=NOW - timedelta(hours=4), status=MatchStatus.FINISHED))
    assert state["state"] == "kickoff_passed"


# --------------------------------------------------------------------- evidence
def _forecast(**overrides):
    payload = dict(provider="stub", external_event_id="1", home_name="Alpha", away_name="Beta",
                   kickoff_utc=NOW + timedelta(hours=6), home_prob=0.5, draw_prob=0.3, away_prob=0.2)
    payload.update(overrides)
    return ProviderForecast(**payload)


def test_the_content_hash_ignores_when_we_fetched_it(cache):
    """Re-fetching the same forecast is the same evidence and must not look like a new snapshot."""
    early = _forecast(fetched_at=NOW)
    late = _forecast(fetched_at=NOW + timedelta(hours=5))
    assert content_hash(early) == content_hash(late)


def test_the_content_hash_changes_when_the_model_changes_its_mind(cache):
    assert content_hash(_forecast()) != content_hash(_forecast(home_prob=0.6))
    assert content_hash(_forecast()) != content_hash(_forecast(model_run_at=NOW))


def test_retrieval_time_comes_from_the_provider_response_not_the_attach_moment(cache):
    """A forecast replayed from the pending cache two days later is not a fresh forecast."""
    from app.services.forecast_service import _retrieved_at
    retrieved = NOW - timedelta(days=2)
    assert _retrieved_at(_forecast(fetched_at=retrieved), NOW) == retrieved
    assert _retrieved_at(_forecast(), NOW) == NOW


# --------------------------------------------------------------------- request cost
class CountingRedis(LockingFakeRedis):
    """FakeRedis that also serves the budget counters, so a whole sync can be priced."""

    def incrby(self, key, amount):
        self.store[key] = int(self.store.get(key) or 0) + int(amount)
        return self.store[key]

    def hincrby(self, key, field, amount):
        bucket = self.store.setdefault(key, {})
        bucket[field] = int(bucket.get(field) or 0) + int(amount)
        return bucket[field]

    def hgetall(self, key):
        return dict(self.store.get(key) or {})


def _gameforecast_with_transport(store_client, budget_client, league_pages=True):
    """A GameForecastProvider whose HTTP calls are counted, sharing one Redis stand-in."""
    import httpx
    from app.services.providers.budget import RequestBudget
    from app.services.providers.gameforecast import GameForecastProvider

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "/leagues" in request.url.path:
            name = request.url.params.get("name", "League")
            return httpx.Response(200, json={"data": [{"id": abs(hash(name)) % 1000, "name": name,
                                                       "type": "league", "women": False}]})
        return httpx.Response(200, json={"data": [], "pagination": {"hasMore": False}})

    provider = GameForecastProvider(
        api_key="test-key", transport=httpx.MockTransport(handler),
        budget=RequestBudget("gameforecast", 100, client=budget_client),
        store=MatchCache(client=store_client), league_overrides={})
    return provider, seen


def test_a_cold_sync_only_pays_discovery_for_ids_we_do_not_already_know():
    """Prices a full run so a ten-request daily plan can be reasoned about rather than guessed.

    Every competition costs one events request. Discovery is only paid for a competition whose
    provider id is not already recorded in code, which today is the Champions League alone.
    """
    from app.services.providers import competitions as comps
    shared = CountingRedis()
    cache = MatchCache(client=shared)
    provider, seen = _gameforecast_with_transport(shared, shared)
    build(cache, provider=provider).ensure_synced(force=True)

    unknown = [key for key in KEYS if comps.get(key).gameforecast_id is None]
    discovery = [url for url in seen if "/leagues" in url]
    events = [url for url in seen if "/events" in url]
    assert len(discovery) == len(unknown)
    assert len(events) == len(KEYS)
    assert len(seen) == len(KEYS) + len(unknown)


def test_a_warm_sync_reuses_the_stored_league_ids():
    """The second day must not pay for discovery again: ids are persisted, not re-derived."""
    shared = CountingRedis()
    cache = MatchCache(client=shared)

    first, _ = _gameforecast_with_transport(shared, shared)
    build(cache, provider=first).ensure_synced(force=True)

    second, seen = _gameforecast_with_transport(shared, shared)
    warm = build(cache, provider=second, now=NOW + timedelta(days=1))
    warm.ensure_synced(force=True)

    assert [url for url in seen if "/leagues" in url] == []
    assert len(seen) == len(KEYS)               # events only
