"""
Forecast synchronisation behaviour: rotation, quota handling, evidence and freshness.

No database and no network. The forecast provider is a stub that counts calls, so every test here
asserts something about how the small daily allowance is spent and about what is stored as evidence.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock

import pytest

from app.models.predictions import Match, MatchStatus
from app.models.provider_data import ProviderForecastRecord
from app.services.forecast_service import STATUS_KEY, ForecastService, content_hash
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


# ------------------------------------------------- the allowance gate: a turn is all or nothing
class PricedStubProvider(StubForecastProvider):
    """A stub that quotes a price per competition and reports a fixed allowance left.

    The budget never moves, so a turn that gets started shows up as a call the gate should not
    have allowed - which is the thing under test, rather than what the call would have cost.
    """

    def __init__(self, costs, remaining, **kwargs):
        super().__init__(**kwargs)
        self.costs = costs
        self.budget = SimpleNamespace(daily_limit=8, remaining=lambda: remaining)

    def request_cost(self, key):
        return self.costs.get(key, 1)


def _gameforecast(shared, events=(), limit=8):
    """A real GameForecastProvider over MockTransport, sharing one Redis stand-in. No network."""
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
        return httpx.Response(200, json={"data": list(events), "pagination": {"hasMore": False}})

    provider = GameForecastProvider(
        api_key="test-key", transport=httpx.MockTransport(handler),
        budget=RequestBudget("gameforecast", limit, client=shared),
        store=MatchCache(client=shared), league_overrides={})
    return provider, seen


def test_a_turn_that_needs_discovery_is_not_started_with_one_request_left():
    """The gate that starved a competition: one unit bought a league id and no forecast.

    A competition whose provider league id is not recorded costs a /leagues lookup and THEN an
    /events fetch. Started with one request left it spends that request on the lookup and is
    refused the fetch, so the allowance is gone and the competition still has nothing.
    """
    from app.services.providers.budget import budget_key
    from app.services.providers.gameforecast import LEAGUE_STORE_KEY

    shared = CountingRedis()
    shared.store[budget_key("gameforecast")] = 7          # 7 of 8 spent: one request left
    cache = MatchCache(client=shared)
    provider, seen = _gameforecast(shared)
    service = build(cache, provider=provider, keys=["champions_league"])

    report = service.ensure_synced(force=True)

    assert seen == [], "no request may be sent for a turn that cannot be paid for in full"
    assert int(shared.store[budget_key("gameforecast")]) == 7, "the last unit must be left unspent"
    assert "champions_league" in report["error"] and "2 request(s)" in report["error"]
    assert report["deferred"] == ["champions_league"]
    assert not (cache.get(LEAGUE_STORE_KEY) or {}), "no league id was bought with the last unit"


def test_a_turn_that_fits_in_what_is_left_is_still_started():
    """The gate must refuse only what it cannot pay for; one unit still buys a one-request turn."""
    provider = PricedStubProvider({"premier_league": 1}, remaining=1)
    service = build(cache=MatchCache(client=LockingFakeRedis()), provider=provider,
                    keys=["premier_league"])

    service.ensure_synced(force=True)

    assert provider.calls == ["premier_league"]


def test_a_starved_competition_is_not_skipped_for_a_cheaper_one_behind_it(cache):
    """Stopping is correct; reordering by price is not, because it starves the dear one forever.

    One request is left, the competition at the head of the order needs two and the one behind it
    needs one. Spending the unit on the cheaper competition would make the expensive one cheaper
    than nothing to skip again tomorrow, and the day after, and it would never be fetched.
    """
    provider = PricedStubProvider({"champions_league": 2, "premier_league": 1}, remaining=1)
    service = build(cache, provider=provider, keys=["champions_league", "premier_league"])

    report = service.ensure_synced(force=True)

    assert provider.calls == [], "the affordable competition behind it must not be promoted"
    assert report["deferred"] == ["champions_league", "premier_league"]
    assert "champions_league costs 2 request(s)" in report["error"]

    service.clear_cooldown()
    later = build(cache, provider=PricedStubProvider({}, remaining=8),
                  keys=["champions_league", "premier_league"], now=NOW + timedelta(days=1))
    assert later.sync_order()[0] == "champions_league", "the starved competition keeps the head"


def test_the_gate_charges_one_request_to_a_provider_that_does_not_price_its_turns():
    """An unpriced provider behaves exactly as before: one request per turn, nothing refused."""
    provider = StubForecastProvider()
    provider.budget = SimpleNamespace(daily_limit=8, remaining=lambda: 1)
    service = build(cache=MatchCache(client=LockingFakeRedis()), provider=provider,
                    keys=["premier_league"])

    service.ensure_synced(force=True)

    assert provider.calls == ["premier_league"]


# ------------------------------------------------- per-competition evidence of what was fetched
def test_a_competitions_fetch_record_survives_an_unrelated_later_pass():
    """The only real fetch of a day must not be erased by a no-op hours later.

    The global status key holds the last run of ANY kind, including the cooling-down early return
    that makes no provider request at all. A record written per competition, only by a turn that
    actually called the provider, is what lets a later reader say what that response contained.
    """
    from app.services.forecast_service import COMPETITION_STATUS_KEY

    shared = CountingRedis()
    cache = MatchCache(client=shared)
    provider, _ = _gameforecast(shared, limit=100)
    key = COMPETITION_STATUS_KEY.format(provider="gameforecast", key="premier_league")

    build(cache, provider=provider, keys=["premier_league"]).ensure_synced(force=True)
    after_fetch = cache.get(key)

    assert after_fetch is not None, "a turn that called the provider must leave a record"
    assert after_fetch["events_returned"] == 0 and after_fetch["complete"] is True
    assert after_fetch["window_from"] == NOW.date().isoformat()
    assert after_fetch["fetched"] == 0 and after_fetch["attached"] == 0

    # An unrelated later pass: the provider is paused, so it returns early having fetched nothing.
    later = build(cache, provider=_gameforecast(shared, limit=100)[0], keys=["premier_league"],
                  now=NOW + timedelta(hours=12))
    later._pause("skipped (recent failure: budget exhausted)", 3600)
    report = later.ensure_synced(force=True)

    assert report["paused"] is True
    assert cache.get(STATUS_KEY.format(provider="gameforecast"))["paused"] is True, \
        "the global key is the one that gets overwritten"
    assert cache.get(key) == after_fetch, "the per-competition record must be untouched by it"


def test_a_turn_whose_request_failed_leaves_the_last_real_record_standing():
    """A failed turn knows nothing about the provider's response; it must not replace what does."""
    from app.services.forecast_service import COMPETITION_STATUS_KEY

    shared = CountingRedis()
    cache = MatchCache(client=shared)
    key = COMPETITION_STATUS_KEY.format(provider="stub", key="premier_league")

    good = StubForecastProvider()
    build(cache, provider=good, keys=["premier_league"]).ensure_synced(force=True)
    recorded = cache.get(key)
    assert recorded is not None and recorded["fetched"] == 0

    failing = StubForecastProvider(budget_after=0)
    later = build(cache, provider=failing, keys=["premier_league"], now=NOW + timedelta(hours=12))
    later.ensure_synced(force=True)

    assert cache.get(key) == recorded


def test_the_fetch_record_carries_what_the_provider_reported_about_what_it_dropped():
    """The evidence the coverage diagnosis needs: the events returned and discarded, by name."""
    from app.services.forecast_service import COMPETITION_STATUS_KEY

    empty_event = {"id": 909, "league": {"id": 15, "name": "Premier League"},
                   "team_home": {"id": 1, "name": "Arsenal"}, "team_away": {"id": 2, "name": "Chelsea"},
                   "start_at": "2026-09-21T14:00:00Z", "predictions": []}
    shared = CountingRedis()
    cache = MatchCache(client=shared)
    provider, _ = _gameforecast(shared, events=[empty_event], limit=100)

    build(cache, provider=provider, keys=["premier_league"]).ensure_synced(force=True)

    record = cache.get(COMPETITION_STATUS_KEY.format(provider="gameforecast", key="premier_league"))
    assert record["events_returned"] == 1 and record["discarded"] == 1
    assert record["discarded_events"][0]["external_event_id"] == "909"
    assert record["discarded_events"][0]["home"] == "Arsenal"


def test_a_fetch_record_never_adopts_another_competitions_report():
    """Evidence attributed to the wrong league is worse than none: the record refuses it."""
    from app.services.forecast_service import COMPETITION_STATUS_KEY

    shared = CountingRedis()
    cache = MatchCache(client=shared)
    provider = StubForecastProvider()
    provider.last_fetch = {"key": "serie_a", "events_returned": 12, "complete": True}
    build(cache, provider=provider, keys=["premier_league"]).ensure_synced(force=True)

    record = cache.get(COMPETITION_STATUS_KEY.format(provider="stub", key="premier_league"))
    assert record["key"] == "premier_league"
    assert "events_returned" not in record, "a listing about Serie A says nothing about this league"
