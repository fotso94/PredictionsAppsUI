"""
The remaining ways a worker that lost the forecast sync lease could still act after a takeover.

1. **Between the ownership check and the reservation.** `RequestBudget.consume` checked the lease,
   then reserved. A worker paused between the two could resume after another had taken over and
   reserve - and send - one more request. The reservation is now owner-checked inside its own
   script.
2. **The provider's own bookkeeping.** GameForecast records the page count, league ids and
   negative-discovery markers - and the HTTP client the provider's reading of its window - before
   the service gets the answer back to check ownership. A stale worker's late answer could replace
   what its successor had recorded. Those control-state writes are now fenced; the records of what
   was actually sent and charged are not, so a lost lease never erases real expenditure.
3. **Redis failure as permission.** A cache whose Redis failed to initialise gave an unmanaged lease
   and an uncoordinated fetch. Now a provider-fetching pass that cannot coordinate does not fetch.

Every interleaving is forced with events at a fixed point and bounded waits, on the controlled clock
(`Clock`, against which the Redis stand-in expires keys) and the controlled renewal `Ticker`. The
network is closed. Tests that only the fix can run import what the fix added inside the test body;
the decisive ones import nothing new, so this file also runs against the previous implementation.
(4, the first insert of a forecast row, needs real PostgreSQL: test_forecast_first_insert_pg.py.)
"""
from __future__ import annotations

import threading
from datetime import timedelta
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock

import httpx
import pytest

from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.providers import gameforecast as gf
from app.services.providers.budget import RequestBudget
from app.services.providers.gameforecast import GameForecastProvider
from tests.providers.support import make_transport
from tests.providers.test_gameforecast import event
from tests.services.test_forecast_sync_concurrency import (  # noqa: F401 - shared fixtures
    LOCK, START, WAIT_SECONDS, InThread, closed_network, daily_slot, service, wait,
)
from tests.services.test_forecast_sync_lease import Ticker, harness, hold_inside_the_fetch
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

LAPSED = START + timedelta(seconds=301)          # one term after A took the lease, never renewed


@pytest.fixture
def clock():
    return Clock(START)


@pytest.fixture
def redis(clock):
    return LockingFakeRedis(clock=clock)


# ================================================================== 1. check, then reserve
def pause_between_check_and_reservation(budget: RequestBudget, thread_name: str):
    """Hold `thread_name` inside `consume`, after its ownership check and before its reservation.

    `_provider_refusal` is the step `consume` takes between the two in both the previous and the
    current implementation, so the pause lands at the same point in each."""
    paused, resume = threading.Event(), threading.Event()
    refusal = budget._provider_refusal

    def held(amount):
        if threading.current_thread().name == thread_name and not resume.is_set():
            paused.set()
            if not resume.wait(WAIT_SECONDS):
                raise AssertionError(f"{thread_name} was never resumed")
        return refusal(amount)

    budget._provider_refusal = held
    return paused, resume


def test_a_worker_paused_between_its_check_and_its_reservation_reserves_nothing_after_takeover(clock, redis):
    """A passes its ownership check for premier_league and is paused before reserving. Its lease
    lapses; B takes over, fetches premier_league and leaves. A resumes. A's reservation must be
    refused and the counter must not move: one request in all, B's."""
    h = harness(clock, redis, ["premier_league"])
    paused, resume = pause_between_check_and_reservation(h.budget, "caller A")
    a = service(h)
    a.lease_waiter = Ticker()                        # never ticked: A's renewer has stalled too
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(paused, "A to have checked ownership and not yet reserved")

    clock.now = LAPSED
    report_b = InThread(lambda: service(h).ensure_synced(force=False), "caller B").join()
    assert report_b["competitions"]["premier_league"]["fetched"] == 1
    assert h.budget.used_today() == 1

    resume.set()
    report_a = first.join()
    assert h.budget.used_today() == 1, "A's stale reservation moved the counter"
    assert h.provider.calls == [("premier_league", LAPSED)], "A sent a request after the takeover"
    assert report_a.get("lease_lost") is True and report_a["competitions"] == {}
    assert redis.get(LOCK) is None


def test_the_same_pause_while_the_successor_is_still_working_is_refused_too(clock, redis):
    """As above, but B is still inside its own request when A resumes: the lease A checks against
    now carries B's token."""
    h = harness(clock, redis, ["premier_league"])
    paused, resume = pause_between_check_and_reservation(h.budget, "caller A")
    b_inside, b_release = hold_inside_the_fetch(h, "caller B")
    a = service(h)
    a.lease_waiter = Ticker()
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(paused, "A to have checked ownership and not yet reserved")

    clock.now = LAPSED
    second = InThread(lambda: service(h).ensure_synced(force=False), "caller B")
    wait(b_inside, "B to be inside its request, holding the lease")
    assert h.budget.used_today() == 1

    resume.set()
    report_a = first.join()
    assert h.budget.used_today() == 1, "A reserved while B held the lease"
    assert [key for key, _ in h.provider.calls] == ["premier_league"]
    assert report_a.get("lease_lost") is True

    b_release.set()
    assert second.join()["competitions"]["premier_league"]["fetched"] == 1
    assert h.budget.used_today() == 1 and redis.get(LOCK) is None


# ================================================================== 2. the provider's own bookkeeping
def rate_limit_headers(remaining: int) -> dict:
    return {"x-ratelimit-requests-limit": "10", "x-ratelimit-requests-remaining": str(remaining),
            "x-ratelimit-requests-reset": "3600"}


def gameforecast_worker(clock, redis, store, handler, keys: List[str]):
    """One worker: its own provider instance and budget object over the SHARED store and budget
    counters, as two backend processes would have."""
    transport, recorder = make_transport(handler)
    budget = RequestBudget("gameforecast", 8, client=redis, now=clock)
    provider = GameForecastProvider(api_key="rapid-key", api_host="gf.test", base_url="https://gf.test",
                                    transport=transport, budget=budget, league_overrides={}, store=store)
    svc = ForecastService(MagicMock(), provider=provider, cache=MatchCache(client=redis), now=clock(),
                          keys=list(keys), sync_fixtures=False)
    svc.registry = MagicMock()
    svc.registry.ensure_canonical_league.side_effect = lambda key: SimpleNamespace(id=key)
    svc.registry.next_kickoff.side_effect = lambda league_id, start: start + timedelta(days=1)
    svc.registry.fixtures_in_window.side_effect = lambda league_id, start, end: 1
    svc.attach_forecast = lambda forecast, key, league_id: {"result": "unmatched", "reason": "harness"}
    return SimpleNamespace(service=svc, provider=provider, budget=budget, requests=recorder.requests)


def test_a_late_answer_cannot_replace_the_page_count_or_window_reading_its_successor_recorded(clock, redis):
    """A asks for premier_league's events; its answer - one page, provider says 9 left - is held on
    the network while A's lease lapses. B takes over: two pages, provider says 8 then 7. Then A's
    answer arrives. The page count must stay B's 2 and the window reading B's 7; A's request stays
    on record as spent."""
    store = MatchCache(client=redis)
    a_inside, a_release = threading.Event(), threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/events":
            raise AssertionError(f"unexpected request {request.url.path}")
        if threading.current_thread().name == "caller A":
            a_inside.set()
            assert a_release.wait(WAIT_SECONDS)
            return httpx.Response(200, json={"data": [event(901)], "pagination": {"hasMore": False}},
                                  headers=rate_limit_headers(9))
        page = int(dict(request.url.params).get("page", "1"))
        return httpx.Response(200, json={"data": [event(500 + page)], "pagination": {"hasMore": page == 1}},
                              headers=rate_limit_headers(9 - page))

    a = gameforecast_worker(clock, redis, store, handler, ["premier_league"])
    a.service.lease_waiter = Ticker()
    first = InThread(lambda: a.service.ensure_synced(force=False), "caller A")
    wait(a_inside, "A's request to be on the network")

    clock.now = LAPSED
    b = gameforecast_worker(clock, redis, store, handler, ["premier_league"])
    report_b = InThread(lambda: b.service.ensure_synced(force=False), "caller B").join()
    assert report_b["competitions"]["premier_league"]["fetched"] == 2
    assert store.get(gf.PAGES_KEY.format(key="premier_league"))["pages"] == 2

    a_release.set()
    report_a = first.join()
    assert store.get(gf.PAGES_KEY.format(key="premier_league"))["pages"] == 2, "A's late page count replaced B's"
    assert b.budget.rate_limit.read()["remaining"] == 7, "A's late window reading replaced B's"
    assert report_a.get("lease_lost") is True
    assert b.budget.used_today() == 3, "A's request is still on record as spent"
    pending = store.get(b.service._pending_key("premier_league"))
    assert sorted(item["external_event_id"] for item in pending) == ["501", "502"], "A's answer was applied"


def test_a_late_discovery_answer_cannot_mark_a_league_unresolved_that_its_successor_found(clock, redis):
    """A asks /leagues for the Champions League; its answer - nothing found - is held while A's lease
    lapses. B takes over, finds the league (id 22), records it and fetches. Then A's answer arrives.
    No "unresolved" marker may appear - it would stop discovery for six hours - and B's league id
    must stand."""
    store = MatchCache(client=redis)
    a_inside, a_release = threading.Event(), threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/leagues":
            if threading.current_thread().name == "caller A":
                a_inside.set()
                assert a_release.wait(WAIT_SECONDS)
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json={"data": [{"id": 22, "name": "UEFA Champions League",
                                                       "type": "cup", "women": False}]})
        if request.url.path == "/events":
            return httpx.Response(200, json={"data": [event(701)], "pagination": {"hasMore": False}})
        raise AssertionError(f"unexpected request {request.url.path}")

    a = gameforecast_worker(clock, redis, store, handler, ["champions_league"])
    a.service.lease_waiter = Ticker()
    first = InThread(lambda: a.service.ensure_synced(force=False), "caller A")
    wait(a_inside, "A's /leagues request to be on the network")

    clock.now = LAPSED
    b = gameforecast_worker(clock, redis, store, handler, ["champions_league"])
    report_b = InThread(lambda: b.service.ensure_synced(force=False), "caller B").join()
    assert report_b["competitions"]["champions_league"]["fetched"] == 1

    a_release.set()
    report_a = first.join()
    assert store.get(GameForecastProvider.unresolved_key("champions_league")) is None, \
        "A's late empty answer marked the league unresolved"
    assert (store.get(gf.LEAGUE_STORE_KEY) or {}).get("champions_league", {}).get("external_id") == "22"
    assert report_a.get("lease_lost") is True
    assert b.budget.used_today() == 3, "A's discovery request is still on record as spent"


# ================================================================== 3. Redis failure is not permission
def plain_service(h, cache) -> ForecastService:
    svc = ForecastService(MagicMock(), provider=h.provider, cache=cache, now=h.clock(),
                          keys=list(h.keys), sync_fixtures=False)
    svc.registry = MagicMock()
    svc.registry.ensure_canonical_league.side_effect = lambda key: SimpleNamespace(id=key)
    svc.registry.next_kickoff.side_effect = lambda league_id, start: None
    svc.registry.fixtures_in_window.side_effect = lambda league_id, start, end: 1
    svc.attach_forecast = lambda forecast, key, league_id: {"result": "unmatched", "reason": "harness"}
    return svc


@pytest.mark.parametrize("force", [False, True], ids=["automatic", "forced"])
def test_a_cache_whose_redis_failed_to_initialise_refuses_the_fetching_pass(clock, redis, monkeypatch, force):
    """The forecast cache cannot reach Redis at start-up. Neither an automatic nor a forced pass may
    fetch: no coordination, no fetch. The request budget is untouched."""
    import app.core.redis as core_redis

    def down():
        raise ConnectionError("isolated test: Redis unreachable at start-up")

    monkeypatch.setattr(core_redis, "get_match_data_redis", down)
    h = harness(clock, redis, ["premier_league"])
    report = plain_service(h, MatchCache()).ensure_synced(force=force)
    assert h.provider.calls == [], "an uncoordinated fetch was made"
    assert h.budget.used_today() == 0
    assert "refused" in (report.get("error") or "")


def test_a_redis_that_fails_while_the_lease_is_taken_refuses_the_pass(clock, redis):
    class FailingLease(LockingFakeRedis):
        def set(self, key, value, nx=False, ex=None, **kwargs):
            if nx:
                raise ConnectionError("isolated test: SET NX failed")
            return super().set(key, value, nx=nx, ex=ex, **kwargs)

    h = harness(clock, redis, ["premier_league"])
    report = plain_service(h, MatchCache(client=FailingLease(clock=clock))).ensure_synced(force=True)
    assert h.provider.calls == [] and h.budget.used_today() == 0, "a fetch started without the lease"
    # Reported as what it is, not as "another worker is running":
    assert report.get("coordination_unavailable") is True and "could not be taken" in report["error"]


def test_a_reservation_whose_owner_check_cannot_run_is_refused_not_counted(clock, redis):
    """The lease renews fine, but the owner-checked reservation itself fails (the budget store errors
    on the script). Nothing may be reserved by any other path, and nothing is sent."""
    from app.services.providers.budget import FENCED_RESERVE_LUA

    class ReservationFails(LockingFakeRedis):
        def _run_lease_script(self, script, keys, args):
            if script == FENCED_RESERVE_LUA:
                raise ConnectionError("isolated test: the reservation script failed")
            return super()._run_lease_script(script, keys, args)

    shared = ReservationFails(clock=clock)
    h = harness(clock, shared, ["premier_league"])
    report = service(h).ensure_synced(force=False)
    assert report.get("lease_lost") is True
    assert h.provider.calls == [] and h.budget.used_today() == 0


def test_a_budget_store_on_another_redis_server_cannot_be_owner_checked_and_is_refused(clock, redis):
    from app.services.sync_lease import LeaseLost, SyncLease, lease_scope

    elsewhere = LockingFakeRedis(clock=clock)                 # a different server, as far as the lease can tell
    budget = RequestBudget("gameforecast", 8, client=elsewhere, now=clock)
    lease = SyncLease(redis, LOCK, 300)
    assert lease.acquire()
    with lease_scope(lease), pytest.raises(LeaseLost, match="not on the lease's Redis server"):
        budget.consume(reason="fetch")
    assert budget.used_today() == 0
