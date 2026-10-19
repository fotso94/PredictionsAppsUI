"""
Two forecast passes that overlap, made to interleave on purpose.

`ensure_synced` serialises spending with a Redis lock (`SYNC_LOCK_KEY`). The defect pinned here was
WHERE the eligibility decision was made: the plan was built before the lock was taken. A caller that
decided "premier_league is due" and then waited for the lock, while another caller fetched
premier_league and released it, went on to execute a plan that was no longer true: a second paid
request for a competition already refreshed today, out of an allowance of eight that other
competitions need.

Nothing here relies on timing, and no two calls are merely run one after the other. Each test runs
two ForecastService instances in two threads over ONE in-memory Redis (the lock, the daily slots,
the cool-down, the pending store) and ONE RequestBudget, and forces the interleaving with events
at a fixed point: the call that takes the lock, or the provider call made while holding it. Every
wait is bounded, so a regression fails instead of hanging.

The provider is a stub that dates its run TODAY, so a second fetch can never pass for a legitimate
re-check of an older run, and both callers use force=False. The network is closed: touching a
socket or an HTTP transport raises at once.
"""
from __future__ import annotations

import socket
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest

from app.core.config import settings
from app.services.forecast_refresh_policy import (
    OUTCOME_SAME_DAY_RUN, POLICY_DAILY_SLOT, POLICY_ELAPSED_INTERVAL,
)
from app.services.forecast_service import SYNC_LOCK_KEY, ForecastService
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.base import ProviderForecast, ProviderQuotaError
from app.services.providers.budget import RequestBudget
from tests.services.test_forecast_refresh_policy import PROVIDER, DatedStubProvider, Harness, at
from tests.services.test_forecast_retention_db import (  # noqa: F401 - pytest fixtures
    KEY as DB_KEY, KICKOFF as DB_KICKOFF, _event, _store_the_fixture, db, engine,
)
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

#: Long enough for any healthy step, short enough that a broken interleaving fails the run quickly.
WAIT_SECONDS = 5
LOCK = SYNC_LOCK_KEY.format(provider=PROVIDER)
START = at(0, 13, 0)                       # 2026-10-19 13:00 UTC, past the publication hour of 12
TODAY = START.date().isoformat()


# ------------------------------------------------------------------ fixtures and helpers
@pytest.fixture(autouse=True)
def closed_network(monkeypatch):
    """Any attempt to reach the outside world fails immediately instead of waiting on a timeout."""
    def refuse(*args, **kwargs):
        raise AssertionError("a network request was attempted from a concurrency test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


@pytest.fixture(autouse=True)
def daily_slot(monkeypatch):
    monkeypatch.setattr(settings, "GAMEFORECAST_REFRESH_POLICY", POLICY_DAILY_SLOT)
    monkeypatch.setattr(settings, "SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR", 12)


@pytest.fixture
def clock():
    return Clock(START)


@pytest.fixture
def redis(clock):
    return LockingFakeRedis(clock=clock)


class StrictStubProvider(DatedStubProvider):
    """The policy tests' dated stub, refusing any competition it was not told to expect, with an
    optional hook that runs inside the provider call (that is, while the caller holds the lock)."""

    def __init__(self, *args, expected: List[str], during_fetch: Optional[Callable[[str], None]] = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.expected = set(expected)
        self.during_fetch = during_fetch

    def get_forecasts(self, key, date_from, date_to):
        if key not in self.expected:
            raise AssertionError(f"unexpected provider request for {key}")
        if self.during_fetch is not None:
            self.during_fetch(key)
        return super().get_forecasts(key, date_from, date_to)


def harness(clock, redis, keys: List[str], **kwargs) -> Harness:
    h = Harness(clock, redis, keys=keys, **kwargs)
    h.provider = StrictStubProvider(h.budget, clock, expected=keys)
    return h


def service(h: Harness, keys: Optional[List[str]] = None) -> ForecastService:
    """A separate instance over the same Redis, budget and provider, built at the clock's time."""
    built = h.new_service()
    assert built.provider is h.provider
    if keys is not None:
        built.keys = list(keys)
    return built


class InThread:
    """Run one call on its own thread; join with a bound and hand back its result or its error."""

    def __init__(self, fn: Callable[[], Any], name: str):
        self.result: Any = None
        self.error: Optional[BaseException] = None
        self.thread = threading.Thread(target=self._run, args=(fn,), name=name, daemon=True)
        self.thread.start()

    def _run(self, fn):
        try:
            self.result = fn()
        except BaseException as exc:  # handed to the test thread, never swallowed
            self.error = exc

    def join(self) -> Any:
        self.thread.join(WAIT_SECONDS)
        assert not self.thread.is_alive(), f"{self.thread.name} did not finish within {WAIT_SECONDS}s"
        if self.error is not None:
            raise self.error
        return self.result


def pause_before_the_lock(svc: ForecastService) -> SimpleNamespace:
    """Hold `svc` at the point just before it takes the sync lock until the test lets it go.

    `at_lock` is set once it gets there; `stale` is the plan its own state yields at that instant -
    the decision a caller that planned before locking would carry through the wait.
    """
    gate = SimpleNamespace(at_lock=threading.Event(), go=threading.Event(), stale=None)
    take_the_lock = svc._acquire_sync_lock

    def paused():
        gate.stale = svc._plan(False)
        gate.at_lock.set()
        if not gate.go.wait(WAIT_SECONDS):
            raise AssertionError("never released from the point before the lock")
        return take_the_lock()

    svc._acquire_sync_lock = paused
    return gate


def wait(event: threading.Event, what: str) -> None:
    assert event.wait(WAIT_SECONDS), f"timed out waiting for {what}"


# ------------------------------------------------------------------ the stale-plan interleaving
@pytest.mark.parametrize("policy", [POLICY_DAILY_SLOT, POLICY_ELAPSED_INTERVAL])
def test_a_caller_that_planned_before_the_lock_does_not_refetch_what_another_caller_just_fetched(
        clock, redis, monkeypatch, policy):
    """
    1. A (force=False) is held at the point before it takes the lock; at that instant its view says
       premier_league is due.
    2. B (force=False) runs its whole pass: takes the lock, fetches premier_league (today's run),
       records the slot, releases the lock.
    3. A is released, takes the now-free lock, and must decide again from what B left behind.
    """
    monkeypatch.setattr(settings, "GAMEFORECAST_REFRESH_POLICY", policy)
    h = harness(clock, redis, ["premier_league"])
    a = service(h)
    gate = pause_before_the_lock(a)

    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(gate.at_lock, "A to reach the point before the lock")
    assert gate.stale.fetch == ["premier_league"], "A's view before the lock: premier_league is due"
    assert redis.get(LOCK) is None and h.provider.calls == []

    clock.now = START + timedelta(seconds=5)
    b = service(h)
    second = InThread(lambda: b.ensure_synced(force=False), "caller B")
    report_b = second.join()
    assert report_b["competitions"]["premier_league"]["fetched"] == 1
    assert redis.get(LOCK) is None, "B released the lock"

    clock.now = START + timedelta(seconds=10)
    gate.go.set()
    report_a = first.join()

    # Exactly one provider fetch and one request charged, both B's.
    assert h.provider.calls == [("premier_league", START + timedelta(seconds=5))]
    assert h.budget.used_today() == 1
    # A did not execute its outdated decision: the plan it walked was made after the lock.
    assert report_a["plan"]["fetch"] == [] and report_a["plan"]["recheck"] == []
    assert "premier_league" in report_a["skipped"]
    assert "premier_league" not in report_a["competitions"]
    # The record shows the one successful fetch.
    if policy == POLICY_DAILY_SLOT:
        slot = a.policy.slot("premier_league")
        assert slot["day"] == TODAY and slot["outcome"] == OUTCOME_SAME_DAY_RUN
        assert slot["fetched_at"] == (START + timedelta(seconds=5)).isoformat()
    assert a._last_sync("premier_league") == START + timedelta(seconds=5)
    # The storage this harness exercises (forecasts held pending in Redis) holds it once.
    pending = h.cache.get(a._pending_key("premier_league"))
    assert [item["external_event_id"] for item in pending] == [f"premier_league-{TODAY}"]
    assert redis.get(LOCK) is None, "the lock is free afterwards"


def test_the_duplicate_no_longer_costs_another_competition_its_turn(clock, redis):
    """The waste the defect caused, measured on a two-request allowance. B refreshes la_liga alone
    (a page asking for one competition); A, the scheduler's pass over both, was held before the lock
    with la_liga and premier_league due. Re-deciding under the lock, A spends the request la_liga no
    longer needs on premier_league instead of fetching la_liga twice and deferring premier_league."""
    h = harness(clock, redis, ["la_liga", "premier_league"], limit=2)
    a = service(h)
    gate = pause_before_the_lock(a)

    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(gate.at_lock, "A to reach the point before the lock")
    assert gate.stale.fetch == ["la_liga", "premier_league"]

    clock.now = START + timedelta(seconds=5)
    b = service(h, keys=["la_liga"])
    InThread(lambda: b.ensure_synced(force=False), "caller B").join()

    clock.now = START + timedelta(seconds=10)
    gate.go.set()
    report_a = first.join()

    assert [key for key, _ in h.provider.calls] == ["la_liga", "premier_league"]
    assert h.budget.used_today() == 2
    assert report_a["plan"]["fetch"] == ["premier_league"]
    assert not report_a["deferred"] and not report_a.get("error")
    assert a.policy.slot("premier_league")["outcome"] == OUTCOME_SAME_DAY_RUN
    assert redis.get(LOCK) is None


def test_a_pause_the_lock_holder_set_is_honoured_by_the_caller_that_waited(clock, redis):
    """B's fetch is refused for quota and B pauses the provider. A, held before the lock with its
    cool-down check already passed, must read the pause after taking the lock and ask nothing."""
    h = harness(clock, redis, ["premier_league"])
    a = service(h)
    gate = pause_before_the_lock(a)

    def refused(key):
        raise ProviderQuotaError("daily quota reached", provider=PROVIDER, status_code=429)

    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(gate.at_lock, "A to reach the point before the lock")

    h.provider.during_fetch = refused
    b = service(h)
    report_b = InThread(lambda: b.ensure_synced(force=False), "caller B").join()
    assert "quota" in report_b["error"] and h.paused()
    h.provider.during_fetch = None

    gate.go.set()
    report_a = first.join()

    assert h.provider.calls == [], "A asked a provider that B had just paused"
    assert h.budget.used_today() == 0
    assert report_a.get("paused") is True and "quota" in report_a["error"]
    assert "premier_league" not in report_a["competitions"]
    assert redis.get(LOCK) is None


# ------------------------------------------------------------------ the lock while it is held
def test_a_second_caller_arriving_while_the_first_holds_the_lock_fetches_nothing(clock, redis):
    """B takes the lock and is held inside its provider call; A arrives, finds the lock taken, re-attaches
    what is cached (free) and returns without a request. B then completes; one fetch in all."""
    h = harness(clock, redis, ["premier_league"])
    inside, finish = threading.Event(), threading.Event()

    def hold(key):
        inside.set()
        if not finish.wait(WAIT_SECONDS):
            raise AssertionError("B was never let out of its provider call")

    h.provider.during_fetch = hold
    b = service(h)
    holder = InThread(lambda: b.ensure_synced(force=False), "caller B")
    wait(inside, "B to be inside its provider call, holding the lock")
    assert redis.get(LOCK) is not None

    a = service(h)
    retried: List[str] = []
    a._retry_pending = lambda key: retried.append(key) or None
    report_a = a.ensure_synced(force=False)
    assert "already running" in report_a["error"]
    assert retried == ["premier_league"], "the free re-attachment still ran"

    finish.set()
    report_b = holder.join()
    assert report_b["competitions"]["premier_league"]["fetched"] == 1
    assert [key for key, _ in h.provider.calls] == ["premier_league"]
    assert h.budget.used_today() == 1
    assert redis.get(LOCK) is None


# ------------------------------------------------------------------ the lock is always given back
def test_an_error_while_planning_under_the_lock_releases_it(clock, redis):
    h = harness(clock, redis, ["premier_league"])
    broken = service(h)

    def failing_plan(force=False):
        assert redis.get(LOCK) is not None, "planning happens while the lock is held"
        raise RuntimeError("the policy could not read its state")

    broken._plan = failing_plan
    with pytest.raises(RuntimeError, match="could not read its state"):
        broken.ensure_synced(force=False)
    assert redis.get(LOCK) is None

    report = service(h).ensure_synced(force=False)       # the next caller is not locked out
    assert report["competitions"]["premier_league"]["fetched"] == 1


def test_an_unexpected_error_mid_pass_releases_the_lock(clock, redis):
    h = harness(clock, redis, ["premier_league"])

    def crash(key):
        raise RuntimeError("an unexpected failure inside the pass")

    h.provider.during_fetch = crash
    with pytest.raises(RuntimeError, match="unexpected failure"):
        service(h).ensure_synced(force=False)
    assert redis.get(LOCK) is None

    h.provider.during_fetch = None
    report = service(h).ensure_synced(force=False)
    assert report["competitions"]["premier_league"]["fetched"] == 1
    assert h.budget.used_today() == 1


# ------------------------------------------------------------------ forced refresh is unchanged
def test_a_forced_refresh_still_fetches_after_another_callers_automatic_fetch(clock, redis):
    """`force` bypasses eligibility by design and nothing else; revalidating under the lock must not
    turn a deliberate refresh into a no-op. The budget still counts it."""
    h = harness(clock, redis, ["premier_league"])
    service(h).ensure_synced(force=False)
    clock.now = START + timedelta(minutes=1)
    report = service(h).ensure_synced(force=True)
    assert report["competitions"]["premier_league"]["fetched"] == 1
    assert h.budget.used_today() == 2


# ------------------------------------------------------------------ against real storage
class OneForecastProvider(StrictStubProvider):
    """Returns the recorded provider event for the stored fixture, dated today, stamped with the
    clock at the moment of the call - so a second fetch would leave a trace on the snapshot."""

    def get_forecasts(self, key, date_from, date_to):
        if key not in self.expected:
            raise AssertionError(f"unexpected provider request for {key}")
        self.budget.consume(1, reason="fetch")
        now = self.clock()
        self.calls.append((key, now))
        return [ProviderForecast(
            provider=PROVIDER, external_event_id="evt-27378", competition_key=key,
            home_name="Rep. Of Ireland", away_name="Kosovo", kickoff_utc=DB_KICKOFF,
            home_prob=0.38, draw_prob=0.32, away_prob=0.30,
            model_run_at=now.replace(hour=6, minute=0, second=0, microsecond=0), fetched_at=now,
            raw=_event())]


def test_against_the_real_registry_the_overlap_stores_one_forecast_retrieved_once(db, monkeypatch):
    """The same interleaving over the test database: the fixture is real, the forecast binds to it,
    and the evidence tables say the forecast was retrieved once, by B. Both instances share the
    session; the events guarantee only one thread uses it at a time."""
    start = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
    clock = Clock(start)
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    budget = RequestBudget(PROVIDER, 8, client=redis, now=clock)
    provider = OneForecastProvider(budget, clock, expected=[DB_KEY])
    registry = MatchRegistry(db)
    match = _store_the_fixture(registry)
    db.flush()

    def build() -> ForecastService:
        svc = ForecastService(db, provider=provider, cache=cache, now=clock(), keys=[DB_KEY],
                              sync_fixtures=False)
        svc.registry = registry
        return svc

    a = build()
    gate = pause_before_the_lock(a)
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(gate.at_lock, "A to reach the point before the lock")
    assert gate.stale.fetch == [DB_KEY]

    clock.now = start + timedelta(seconds=5)
    b = build()
    report_b = InThread(lambda: b.ensure_synced(force=False), "caller B").join()
    assert report_b["competitions"][DB_KEY]["attached"] == 1

    clock.now = start + timedelta(seconds=10)
    gate.go.set()
    report_a = first.join()
    db.flush()

    retrieved = start + timedelta(seconds=5)
    assert provider.calls == [(DB_KEY, retrieved)] and budget.used_today() == 1
    assert DB_KEY not in report_a["competitions"]
    [snapshot] = b.snapshots_for_match(match.id, PROVIDER)
    as_utc = lambda value: value.replace(tzinfo=timezone.utc)  # noqa: E731 - stored naive UTC
    assert as_utc(snapshot.first_fetched_at) == retrieved
    assert as_utc(snapshot.last_fetched_at) == retrieved, "no second retrieval touched the evidence"
    assert redis.get(LOCK) is None
