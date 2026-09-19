"""
Forecast synchronisation behaviour: rotation, quota handling, evidence and freshness.

No database and no network. The forecast provider is a stub that counts calls, so every test here
asserts something about how the small daily allowance is spent and about what is stored as evidence.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock

import httpx
import pytest

from app.models.predictions import Match, MatchStatus
from app.models.provider_data import ProviderForecastRecord
from app.services.forecast_service import STATUS_KEY, ForecastService, content_hash
from app.services.match_cache import MatchCache
from app.services.providers.base import ForecastProvider, ProviderForecast, ProviderQuotaError
from app.services.providers.budget import ProviderRateLimit, RequestBudget
from app.services.providers.gameforecast import GameForecastProvider
from app.services.providers.http import RateLimitReading
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


# ------------------------------------------------------- pausing on the provider's clock, not ours
#
# 2026-09-19T00:01:10Z: a 429 paused GameForecastAPI for ~86,000 seconds because the pause was a
# flat "until UTC midnight". The provider had told us, in the same response, when its own window
# would reopen. Pausing a full day on a window that reopens in three hours throws away the other
# twenty-one hours of allowance.

SECONDS_TO_MIDNIGHT = int((datetime(2026, 9, 21, tzinfo=timezone.utc) - NOW).total_seconds())


def _budgeted_provider(redis, *, remaining=None, reset_seconds=None, limit=10, status=429,
                       quota_status=None, daily_limit=8):
    """A stub provider with a real RequestBudget, optionally carrying a reading from the provider."""
    provider = StubForecastProvider(budget_after=0 if quota_status is not None else None)
    provider.budget = RequestBudget("stub", daily_limit, client=redis, now=NOW)
    if quota_status is not None:
        def raise_quota(key, date_from, date_to):
            raise ProviderQuotaError("stub: rate limit or quota exceeded (HTTP 429): You have "
                                     "exceeded the DAILY quota for Requests on your current plan, "
                                     "BASIC.", provider="stub", status_code=quota_status)
        provider.get_forecasts = raise_quota
    if remaining is not None or reset_seconds is not None:
        ProviderRateLimit("stub", client=redis, now=NOW).record(
            RateLimitReading(provider="stub", limit=limit, remaining=remaining,
                             reset_seconds=reset_seconds, observed_at=NOW, status_code=status))
    return provider


def test_a_429_carrying_a_reset_pauses_until_that_reset_rather_than_for_a_flat_day():
    redis = LockingFakeRedis()
    cache = MatchCache(client=redis)
    three_hours = 3 * 3600
    provider = _budgeted_provider(redis, remaining=0, reset_seconds=three_hours, quota_status=429)

    report = build(cache, provider=provider).ensure_synced(force=True)

    assert redis.ttls["forecast:cooldown:stub"] == three_hours, \
        "the provider said three hours; waiting a day discards the other twenty-one"
    assert redis.ttls["forecast:cooldown:stub"] < SECONDS_TO_MIDNIGHT
    assert "per the provider's own reset" in report["error"]


def test_a_429_with_no_usable_header_keeps_todays_behaviour_exactly():
    """Nothing learned, nothing changed: the flat day is still the fallback, to the second."""
    redis = LockingFakeRedis()
    cache = MatchCache(client=redis)
    provider = _budgeted_provider(redis, quota_status=429)

    report = build(cache, provider=provider).ensure_synced(force=True)

    assert redis.ttls["forecast:cooldown:stub"] == SECONDS_TO_MIDNIGHT
    assert "the provider published no reset" in report["error"]


def test_a_reset_further_out_than_our_own_day_is_still_honoured():
    """Both have to allow the request, so the pause runs to whichever window turns last."""
    redis = LockingFakeRedis()
    cache = MatchCache(client=redis)
    two_days = 2 * 24 * 3600
    provider = _budgeted_provider(redis, remaining=0, reset_seconds=two_days, quota_status=429)

    build(cache, provider=provider).ensure_synced(force=True)

    assert redis.ttls["forecast:cooldown:stub"] == two_days


def test_a_pass_does_not_start_a_turn_the_provider_has_already_said_it_will_not_serve():
    """Our counter was clean and the provider had nothing left. The turn must not be started."""
    redis = LockingFakeRedis()
    cache = MatchCache(client=redis)
    provider = _budgeted_provider(redis, remaining=0, reset_seconds=4 * 3600)

    report = build(cache, provider=provider).ensure_synced(force=True)

    assert provider.calls == [], "not one request may go out against a window the provider closed"
    assert provider.budget.used_today() == 0, "and nothing may be counted as spent"
    assert "remaining daily allowance (0" in report["error"]
    assert "what the provider itself reports is left in its own window" in report["error"]
    assert redis.ttls["forecast:cooldown:stub"] == 4 * 3600


def test_our_own_spent_ceiling_still_pauses_on_our_own_day():
    """When our cap is what stopped the pass, the provider's window is not the clock to wait on."""
    redis = LockingFakeRedis()
    cache = MatchCache(client=redis)
    provider = _budgeted_provider(redis, remaining=500, reset_seconds=3600, limit=500, status=200)
    for _ in range(8):
        provider.budget.consume()

    report = build(cache, provider=provider).ensure_synced(force=True)

    assert provider.calls == []
    assert redis.ttls["forecast:cooldown:stub"] == SECONDS_TO_MIDNIGHT
    assert "per the daily ceiling we configured" in report["error"]


def test_our_own_spent_ceiling_does_not_wait_on_a_window_that_is_not_what_refused():
    """The mirror of the defect this package fixes, and just as expensive.

    Our cap is 8 against a plan of 10, so when our counter is spent the provider still has two
    requests left in a window that - the whole premise here - is NOT the UTC day and therefore
    publishes a reset beyond our midnight. Our counter hands its allowance back at 00:00 and the
    provider is willing to serve then. Pausing until the provider's reset instead would sleep
    through those hours for a window that never refused anything.
    """
    redis = LockingFakeRedis()
    cache = MatchCache(client=redis)
    beyond_our_midnight = SECONDS_TO_MIDNIGHT + 7 * 3600 + 14 * 60
    provider = _budgeted_provider(redis, remaining=2, reset_seconds=beyond_our_midnight,
                                  limit=10, status=200)
    for _ in range(8):
        provider.budget.consume()

    report = build(cache, provider=provider).ensure_synced(force=True)

    assert provider.budget.limited_by() == "our_configured_ceiling", "our cap is what refused"
    assert provider.budget.provider_remaining() == 2, "the provider's window was never spent"
    assert redis.ttls["forecast:cooldown:stub"] == SECONDS_TO_MIDNIGHT, \
        "our day is the only window that has to turn; the provider's reset is not our clock"
    assert redis.ttls["forecast:cooldown:stub"] < beyond_our_midnight
    assert "is not what refused" in report["error"]


# ============================================================ REPLAY: 2026-09-19T00:01:10Z
#
# The measured sequence, reconstructed with httpx.MockTransport and nothing else:
#
#   provider:budget:gameforecast:20260919 = 3, by_reason {fetch: 2, discovery: 1}, refused 0
#   ligue_1          /events   -> 200, eight fixtures gained forecasts
#   champions_league /leagues  -> 200, league id 8 discovered and stored
#   champions_league /events   -> HTTP 429 "You have exceeded the DAILY quota ... plan, BASIC."
#
# Our counter said five of eight were left. The provider's plan is ten a day and it had served
# eight in the previous UTC day, so its window - which is not the UTC day - had two left and the
# third request was always going to be refused. The discovery request bought a league id that no
# fetch could use, and the 429 then paused us for a full day.

REPLAY_NOW = datetime(2026, 9, 19, 0, 1, 10, tzinfo=timezone.utc)
#: What the provider said in the 429: its window reopens ~7h12m into the new UTC day, not at
#: midnight. This is the number a flat "pause until UTC midnight" throws away.
REPLAY_RESET_SECONDS = 25972
LIGUE_1_LEAGUE_ID = "4"


def _replay_event(index):
    return {"id": 9000 + index, "league": {"id": 4, "name": "Ligue 1"},
            "team_home": {"id": index, "name": f"Home {index}"},
            "team_away": {"id": 100 + index, "name": f"Away {index}"},
            "start_at": "2026-09-20T19:00:00Z", "updated_at": "2026-09-19T00:00:00Z",
            "predictions": [{"run_at": "2026-09-19T00:00:00Z",
                             "match_result": {"home": 52, "draw": 26, "away": 22}}]}


def _replay_transport(remaining_at_start):
    """The provider as it behaved that night, with the headers it was already returning.

    `remaining_at_start` is what its own window had left when the pass resumed. It is the fact
    the old code had no way to see.
    """
    state = {"left": remaining_at_start}

    def headers():
        return {"x-ratelimit-requests-limit": "10",
                "x-ratelimit-requests-remaining": str(max(state["left"], 0)),
                "x-ratelimit-requests-reset": str(REPLAY_RESET_SECONDS)}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["left"] <= 0:
            # The provider serves while its window has allowance and refuses when it does not.
            # It reports the same three headers either way, which is the whole point.
            return httpx.Response(429, json={"message": "You have exceeded the DAILY quota for "
                                                        "Requests on your current plan, BASIC."},
                                  headers=headers())
        state["left"] -= 1
        if request.url.path == "/leagues":
            return httpx.Response(200, headers=headers(), json={"data": [
                {"id": 8, "name": "UEFA Champions League", "type": "cup", "women": False}]})
        return httpx.Response(200, headers=headers(), json={
            "data": [_replay_event(i) for i in range(8)], "pagination": {"hasMore": False}})

    return httpx.MockTransport(handler), state


def _replay_provider(redis, remaining_at_start):
    transport, state = _replay_transport(remaining_at_start)
    provider = GameForecastProvider(
        api_key="rapid-key", api_host="game-forecast-api.p.rapidapi.com",
        base_url="https://game-forecast-api.p.rapidapi.com", transport=transport,
        budget=RequestBudget("gameforecast", 8, client=redis, now=REPLAY_NOW),
        league_overrides={}, store=MatchCache(client=redis))
    provider.client.rate_limit_sink = ProviderRateLimit(
        "gameforecast", client=redis, now=REPLAY_NOW).record
    provider.client._now = lambda: REPLAY_NOW
    return provider, state


def _replay(redis, remaining_at_start, warm_reading=None):
    if warm_reading is not None:
        ProviderRateLimit("gameforecast", client=redis, now=REPLAY_NOW).record(warm_reading)
    provider, state = _replay_provider(redis, remaining_at_start)
    service = build(MatchCache(client=redis), provider=provider,
                    keys=["ligue_1", "champions_league"], now=REPLAY_NOW)
    # This replay is about what is spent and how long the pause lasts, not about matching a
    # forecast to a fixture: there is no database here, so every forecast that arrives is held
    # as unmatched. `fetched` still counts what the provider actually returned.
    service.attach_forecast = lambda forecast, key, league_id: {
        "result": "unmatched", "reason": "no fixtures exist in this replay"}
    return service.ensure_synced(force=True), provider, state


def test_replay_the_discovery_that_bought_nothing_is_never_paid_for():
    """The ligue_1 fetch still happens and still succeeds. The two wasted requests do not.

    After the ligue_1 response the provider has said, in a header, that it has one request left.
    The champions_league turn costs two - a /leagues discovery and then the /events fetch - so it
    is not started at all. That is the discovery request and the 429 both avoided.
    """
    redis = LockingFakeRedis()
    report, provider, _ = _replay(redis, remaining_at_start=2)

    assert provider.budget.used_today() == 1, "one request, not three"
    assert provider.budget.by_reason() == {"fetch": 1}, "no discovery was bought"
    assert "ligue_1" in report["competitions"] and "error" not in report["competitions"]["ligue_1"]
    assert report["competitions"]["ligue_1"]["fetched"] == 8, "the eight forecasts still arrive"
    assert "champions_league" not in report["competitions"]
    assert report["deferred"] == ["champions_league"]


def test_replay_the_pause_is_the_providers_seven_hours_not_a_flat_day():
    redis = LockingFakeRedis()
    report, _, _ = _replay(redis, remaining_at_start=2)

    paused_for = redis.ttls["forecast:cooldown:gameforecast"]
    assert paused_for == REPLAY_RESET_SECONDS, "the provider named the hour its window reopens"
    assert paused_for < 86000, "the measured pause was ~86,000s; this is ~7h"
    assert "what the provider itself reports is left in its own window" in report["error"]


def test_replay_the_two_accountings_are_both_published_afterwards():
    redis = LockingFakeRedis()
    _replay(redis, remaining_at_start=2)

    snapshot = RequestBudget("gameforecast", 8, client=redis, now=REPLAY_NOW).snapshot()
    assert (snapshot["used_today"], snapshot["remaining_today"]) == (1, 7)
    assert snapshot["provider_reported"]["remaining"] == 1
    assert snapshot["effective_remaining_today"] == 1 and snapshot["limited_by"] == "the_provider"
    assert snapshot["provider_reported"]["window_matches_utc_day"] is False


def test_replay_the_first_request_of_a_cold_pass_is_still_spent_before_anything_is_learned():
    """Honest limit of the fix: with nothing stored, the first request goes out blind.

    If the provider's window is already empty when the pass resumes, that first request is still
    spent on a 429 - the refusal is what teaches us. What changes is everything after it: the
    window is recorded, the pass stops instead of spending two more, and the pause is the
    provider's own reset rather than a flat day.
    """
    redis = LockingFakeRedis()
    report, provider, _ = _replay(redis, remaining_at_start=0)

    assert provider.budget.used_today() == 1, "one request was spent learning; three were not"
    assert "429" in report["competitions"]["ligue_1"]["error"]
    assert redis.ttls["forecast:cooldown:gameforecast"] == REPLAY_RESET_SECONDS
    assert "per the provider's own reset" in report["error"]
    assert ProviderRateLimit("gameforecast", client=redis, now=REPLAY_NOW).remaining_now() == 0


def test_replay_a_window_carried_over_from_yesterday_stops_the_pass_before_any_request():
    """Once a reading survives the day boundary, an empty window costs nothing at all to obey."""
    redis = LockingFakeRedis()
    yesterday = RateLimitReading(provider="gameforecast", limit=10, remaining=0,
                                 reset_seconds=REPLAY_RESET_SECONDS + 60,
                                 observed_at=REPLAY_NOW - timedelta(minutes=1), status_code=429)
    report, provider, state = _replay(redis, remaining_at_start=0, warm_reading=yesterday)

    assert provider.budget.used_today() == 0, "not one request against a window known to be shut"
    assert report["competitions"] == {}
    assert "remaining daily allowance (0" in report["error"]
