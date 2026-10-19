"""
The forecast sync lease over a pass longer than one term, on a controlled clock.

The sync lock used to be a plain key that expired five minutes after it was taken and was never
renewed. A pass that outlived it lost the lock without knowing; a second worker took it, and the two
overlapped - a duplicate paid request, and the older worker's late writes landing over the newer
one's. The lease that replaces it is renewed while the pass runs, renewed and released only by its
owner's token, fences the owner's writes, and stops the owner from reserving or sending anything
once it is lost.

Time here is simulated. `Clock` is the fake clock the Redis stand-in expires keys against, so "six
minutes later" is one assignment, and `Ticker` is the lease renewal worker's clock: it renews
exactly when a test ticks, never on its own. Two callers run as two threads over ONE Redis
stand-in and ONE RequestBudget, ordered by events, and every wait is bounded. The atomic Redis
scripts themselves are exercised against a real, isolated Redis in test_sync_lease_redis.py.

The first test is written against behaviour only - it imports nothing the fix added - so the same
file runs against the previous implementation, where it fails for the expiry defect.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from app.core.config import settings
from app.services.forecast_refresh_policy import (
    OUTCOME_SAME_DAY_RUN, POLICY_DAILY_SLOT, POLICY_ELAPSED_INTERVAL,
)
from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.base import ProviderError
from app.services.providers.budget import RequestBudget
from tests.services.test_forecast_refresh_policy import PROVIDER, DatedStubProvider
from tests.services.test_forecast_retention_db import (  # noqa: F401 - pytest fixtures
    KEY as DB_KEY, _store_the_fixture, db, engine,
)
from tests.services.test_forecast_sync_concurrency import (  # noqa: F401 - shared fixtures
    LOCK, START, WAIT_SECONDS, InThread, OneForecastProvider, StrictStubProvider, closed_network, daily_slot,
    harness as base_harness, service, wait,
)
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

TERM = timedelta(seconds=300)            # SYNC_LOCK_TTL_SECONDS, the term the old lock expired after


@pytest.fixture
def clock():
    return Clock(START)


@pytest.fixture
def redis(clock):
    return LockingFakeRedis(clock=clock)


class Ticker:
    """Controlled time for a lease's renewal worker: one renewal per `tick()`, never on its own.

    The lease calls it as its waiter (`waiter(seconds, stop)`), `wake()` when it is told to stop and
    `exited()` when its worker ends. `tick()` returns once the worker has finished acting on the
    tick - renewed and gone back to waiting, or exited - or False after a short bound when no
    worker is there to act on it at all (the previous implementation had none).
    """

    def __init__(self):
        self._cond = threading.Condition()
        self._issued = 0
        self._taken = 0
        self._idle = False
        self._exited = False

    def __call__(self, seconds, stop):
        with self._cond:
            self._idle = True
            self._cond.notify_all()
            while not stop.is_set() and self._taken >= self._issued:
                self._cond.wait(0.5)            # re-checks; `wake()` interrupts it at once
            self._idle = False
            if stop.is_set():
                return True
            self._taken += 1
            return False

    def wake(self):
        with self._cond:
            self._cond.notify_all()

    def exited(self):
        with self._cond:
            self._exited = True
            self._cond.notify_all()

    def tick(self, timeout: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            self._issued += 1
            self._cond.notify_all()
            while not (self._exited or (self._taken >= self._issued and self._idle)):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            return self._taken >= self._issued


class InFlightProvider(StrictStubProvider):
    """The strict dated stub, with the request reserved, recorded and stamped BEFORE `in_flight` runs:
    a call held there is a request that has left and whose answer has not come back yet."""

    in_flight = None

    def get_forecasts(self, key, date_from, date_to):
        if key not in self.expected:
            raise AssertionError(f"unexpected provider request for {key}")
        if self.during_fetch is not None:
            self.during_fetch(key)
        answer = DatedStubProvider.get_forecasts(self, key, date_from, date_to)
        if self.in_flight is not None:
            self.in_flight(key)
        return answer


def harness(clock, redis, keys, **kwargs):
    h = base_harness(clock, redis, keys, **kwargs)
    h.provider = InFlightProvider(h.budget, clock, expected=keys)
    return h


def hold_inside_the_fetch(h, thread_name: str, competition: str = None):
    """Hold `thread_name`'s request (optionally for one competition) on the network until released:
    already reserved and sent, answer not yet back. Every other call passes straight through."""
    inside, release = threading.Event(), threading.Event()

    def hold(key):
        if threading.current_thread().name == thread_name and competition in (None, key) and not release.is_set():
            inside.set()
            if not release.wait(WAIT_SECONDS):
                raise AssertionError(f"{thread_name} was never let out of its provider call")

    h.provider.in_flight = hold
    return inside, release


def renewal_workers_alive() -> List[str]:
    return [t.name for t in threading.enumerate() if t.name.endswith("lease-renewal") and t.is_alive()]


# ------------------------------------------------------------------ the decisive test
@pytest.mark.parametrize("policy", [POLICY_DAILY_SLOT, POLICY_ELAPSED_INTERVAL])
def test_a_pass_that_outlives_the_original_five_minutes_keeps_the_lock_and_nobody_overlaps(
        clock, redis, monkeypatch, policy):
    """
    A takes the lock at 13:00 and is held inside its provider call. At 13:03:20 its renewal interval
    elapses. At 13:06:40 - past the moment the old lock expired - caller B starts a pass. B must find
    the lock taken and fetch nothing; A then finishes. One fetch, one request charged, in all.
    """
    monkeypatch.setattr(settings, "GAMEFORECAST_REFRESH_POLICY", policy)
    h = harness(clock, redis, ["premier_league"])
    inside, release = hold_inside_the_fetch(h, "caller A")
    ticker = Ticker()
    a = service(h)
    a.lease_waiter = ticker                 # an attribute the previous implementation never reads

    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(inside, "A to be inside its provider call, holding the lock")

    clock.now = START + timedelta(seconds=200)
    ticker.tick()                           # one renewal interval; nothing asserted on it here
    clock.now = START + timedelta(seconds=400)
    assert clock.now > START + TERM, "this is past the old lock's expiry"

    b = service(h)
    report_b = InThread(lambda: b.ensure_synced(force=False), "caller B").join()
    assert "already running" in (report_b.get("error") or ""), (
        f"B ran a pass while A was still working: {report_b.get('competitions')}")

    release.set()
    report_a = first.join()
    assert report_a["competitions"]["premier_league"]["fetched"] == 1
    assert h.provider.calls == [("premier_league", START)], "exactly one fetch, A's"
    assert h.budget.used_today() == 1, "exactly one request charged"
    assert redis.get(LOCK) is None, "the lock is free afterwards"
    assert renewal_workers_alive() == []


# ------------------------------------------------------------------ renewal through a long pass
def test_the_lease_is_renewed_again_and_again_through_a_long_pass(clock, redis):
    """Fifteen simulated minutes inside one provider call, renewed every 150 s; a second caller
    tried twice on the way finds the lock taken both times."""
    h = harness(clock, redis, ["premier_league"])
    inside, release = hold_inside_the_fetch(h, "caller A")
    ticker = Ticker()
    a = service(h)
    a.lease_waiter = ticker
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(inside, "A to be inside its provider call")
    lease = a._lease

    for step in range(1, 7):
        clock.now = START + timedelta(seconds=150 * step)
        assert ticker.tick(), "the renewal worker acted on the tick"
        assert redis.expires[LOCK] == clock.now + TERM, "renewed to a full term from now"
        if step in (3, 6):
            report = InThread(lambda: service(h).ensure_synced(force=False), "caller B").join()
            assert "already running" in report["error"]
    assert lease.renewals >= 6 and not lease.lost

    release.set()
    first.join()
    assert [key for key, _ in h.provider.calls] == ["premier_league"] and h.budget.used_today() == 1
    assert redis.get(LOCK) is None and not lease.renewing


def test_a_successful_pass_stops_its_renewal_worker_and_releases(clock, redis):
    h = harness(clock, redis, ["premier_league"])
    ticker = Ticker()
    a = service(h)
    a.lease_waiter = ticker
    seen = {}
    h.provider.during_fetch = lambda key: seen.update(lease=a._lease, renewing=a._lease.renewing)
    report = a.ensure_synced(force=False)
    assert report["competitions"]["premier_league"]["fetched"] == 1
    assert seen["renewing"] is True, "renewal ran during the pass"
    assert not seen["lease"].renewing and redis.get(LOCK) is None and renewal_workers_alive() == []


# ------------------------------------------------------------------ crash and takeover
def test_a_crashed_workers_lease_lapses_and_another_worker_takes_over(clock, redis):
    """A worker that died after taking the lease leaves its key behind with nobody renewing it. The
    next caller is refused until one term has passed, then takes over and fetches."""
    from app.services.sync_lease import SyncLease

    h = harness(clock, redis, ["premier_league"])
    dead = SyncLease(redis, LOCK, 300)
    assert dead.acquire()                    # ... and then the process is gone

    clock.now = START + timedelta(seconds=299)
    report = service(h).ensure_synced(force=False)
    assert "already running" in report["error"] and h.provider.calls == []

    clock.now = START + timedelta(seconds=301)
    report = service(h).ensure_synced(force=False)
    assert report["competitions"]["premier_league"]["fetched"] == 1
    assert h.budget.used_today() == 1 and redis.get(LOCK) is None


# ------------------------------------------------------------------ lost ownership
def test_when_renewal_cannot_be_confirmed_the_worker_starts_no_further_request(clock, redis):
    """Redis stops answering A's lease scripts while A's la_liga request is in flight. The renewal
    fails, the lease is marked lost, and when the la_liga answer comes back A applies nothing and
    never asks for premier_league. A's key lapses after one term and B then takes over."""
    h = harness(clock, redis, ["la_liga", "premier_league"])
    inside, release = hold_inside_the_fetch(h, "caller A", "la_liga")
    ticker = Ticker()
    a = service(h)
    a.lease_waiter = ticker
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(inside, "A to be inside its la_liga request")
    lease = a._lease

    redis.lease_error = ConnectionError("isolated test: Redis unreachable from worker A")
    clock.now = START + timedelta(seconds=100)
    ticker.tick()
    assert lease.lost and "could not be confirmed" in lease.lost_reason

    release.set()
    report_a = first.join()
    assert report_a.get("lease_lost") is True
    assert [key for key, _ in h.provider.calls] == ["la_liga"], "no request after the loss"
    assert h.budget.used_today() == 1, "nothing reserved after the loss"
    assert "la_liga" not in report_a["competitions"]
    assert a.policy.slot("la_liga") == {} and h.cache.get(a._pending_key("la_liga")) is None, \
        "the late answer was not applied"

    redis.lease_error = None
    assert redis.get(LOCK) == lease.token, "A could not release a lease it could not reach"
    report = service(h).ensure_synced(force=False)
    assert "already running" in report["error"]
    clock.now = START + timedelta(seconds=301)
    report = service(h).ensure_synced(force=False)
    assert sorted(report["competitions"]) == ["la_liga", "premier_league"]
    assert h.budget.used_today() == 3 and redis.get(LOCK) is None


def test_a_delayed_old_worker_cannot_renew_release_or_write_under_its_successor(clock, redis):
    from app.services.sync_lease import SyncLease

    old = SyncLease(redis, LOCK, 300)
    assert old.acquire()
    clock.now = START + timedelta(seconds=301)          # old's renewer stalled for a whole term
    new = SyncLease(redis, LOCK, 300)
    assert new.acquire()
    expiry = redis.expires[LOCK]

    def delayed():
        """The old worker as it wakes up, still believing it holds the lease: every attempt below
        reaches the script and is refused there by the token comparison."""
        stale = SyncLease(redis, LOCK, 300)
        stale.token, stale.held = old.token, True
        return stale

    renewing = delayed()
    assert renewing.renew() is False and renewing.lost
    assert delayed().release() is False
    assert delayed().fenced_set(["forecast:refresh:stub:premier_league"], "{}", [60]) is False
    assert delayed().fenced_delete([LOCK]) is False
    assert redis.get(LOCK) == new.token and redis.expires[LOCK] == expiry, "the successor's lease is untouched"
    assert redis.get("forecast:refresh:stub:premier_league") is None

    assert new.fenced_set(["forecast:refresh:stub:premier_league"], "{}", [60]) is True
    assert new.renew() and new.release() and redis.get(LOCK) is None


def test_an_answer_that_arrives_after_the_lease_was_lost_overwrites_nothing(clock, redis):
    """A is inside its premier_league request when its renewer stalls for longer than a term (a
    paused process). B takes over, fetches premier_league and serie_a, records them and leaves. Then
    A's answer arrives. A must apply none of it and must not go on to serie_a.

    A's request had already left when the lease lapsed, so B's premier_league request is a second
    one: that is the boundary - a request in flight cannot be recalled - and the test pins it."""
    h = harness(clock, redis, ["premier_league", "serie_a"])
    inside, release = hold_inside_the_fetch(h, "caller A", "premier_league")
    ticker = Ticker()                        # never ticked: A's renewer is stalled
    a = service(h)
    a.lease_waiter = ticker
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(inside, "A to be inside its premier_league request")

    clock.now = START + timedelta(seconds=301)
    b = service(h)
    report_b = InThread(lambda: b.ensure_synced(force=False), "caller B").join()
    assert sorted(report_b["competitions"]) == ["premier_league", "serie_a"]
    taken_over = START + timedelta(seconds=301)

    release.set()
    report_a = first.join()

    assert report_a.get("lease_lost") is True and report_a["competitions"] == {}
    assert h.provider.calls == [("premier_league", START), ("premier_league", taken_over),
                                ("serie_a", taken_over)], "A asked nothing after its answer came back"
    assert h.budget.used_today() == 3
    slot = a.policy.slot("premier_league")
    assert slot["fetched_at"] == taken_over.isoformat() and slot["outcome"] == OUTCOME_SAME_DAY_RUN
    assert a._last_sync("premier_league") == taken_over
    pending = h.cache.get(a._pending_key("premier_league"))
    assert [item["fetched_at"] for item in pending] == [taken_over.isoformat()], "B's forecast, not A's"
    assert redis.get(LOCK) is None and renewal_workers_alive() == []


def test_a_write_after_the_last_check_is_still_refused_once_the_lease_is_gone(clock, redis):
    """A's answer arrives in time and passes the ownership check; then A stalls, after the check and
    before its writes, for longer than a term, and B takes over and records premier_league. A's
    writes must not land: a check followed by an unguarded write would let them. The fence refuses
    them inside the same Redis script that compares the token."""
    h = harness(clock, redis, ["premier_league"])
    a = service(h)
    a.lease_waiter = Ticker()
    after_check, resume = threading.Event(), threading.Event()
    unmatched = a.attach_forecast

    def stall_then_attach(forecast, key, league_id):
        if threading.current_thread().name == "caller A" and not resume.is_set():
            after_check.set()                # past `_confirm_lease`, before any write
            assert resume.wait(WAIT_SECONDS)
        return unmatched(forecast, key, league_id)

    a.attach_forecast = stall_then_attach
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(after_check, "A to have passed its last check")

    clock.now = START + timedelta(seconds=301)
    report_b = InThread(lambda: service(h).ensure_synced(force=False), "caller B").join()
    assert report_b["competitions"]["premier_league"]["fetched"] == 1
    taken_over = START + timedelta(seconds=301)

    resume.set()
    report_a = first.join()
    assert report_a.get("lease_lost") is True
    assert a.policy.slot("premier_league")["fetched_at"] == taken_over.isoformat()
    assert a._last_sync("premier_league") == taken_over
    pending = h.cache.get(a._pending_key("premier_league"))
    assert [item["fetched_at"] for item in pending] == [taken_over.isoformat()], "B's forecast stands"
    assert redis.get(LOCK) is None


def test_a_lost_lease_found_by_the_calendar_request_blames_no_provider(clock, redis):
    """The loss is noticed by the spending guard as the calendar request is about to be reserved:
    nothing is reserved on either budget, and no provider is paused for it."""
    from app.services.sync_lease import LeaseLost

    assert not issubclass(LeaseLost, ProviderError)
    match_budget = RequestBudget("livescore", 100, client=redis, now=clock)

    def calendar(key):
        redis.delete(LOCK)                   # the lease lapsed and is gone
        match_budget.consume(reason="fetch")  # the calendar request about to be reserved
        raise AssertionError("the calendar request was reserved after the lease was lost")

    h = harness(clock, redis, ["premier_league"], calendar=calendar)
    report = service(h).ensure_synced(force=False)
    assert report.get("lease_lost") is True
    assert match_budget.used_today() == 0 and h.budget.used_today() == 0 and h.provider.calls == []
    assert not h.paused() and service(h).policy.slot("premier_league") == {}


# ------------------------------------------------------------------ exceptions, cancellation, shutdown
class Cancelled(BaseException):
    """What a cancelled task delivers into the code it interrupts: not an Exception."""


@pytest.mark.parametrize("raised", [RuntimeError("unexpected"), Cancelled(), SystemExit(1), KeyboardInterrupt()],
                         ids=["exception", "cancellation", "shutdown", "interrupt"])
def test_an_exception_or_cancellation_releases_the_lease_and_stops_its_renewal(clock, redis, raised):
    h = harness(clock, redis, ["premier_league"])
    ticker = Ticker()
    a = service(h)
    a.lease_waiter = ticker
    seen = {}

    def interrupt(key):
        seen["lease"] = a._lease
        assert a._lease.renewing
        raise raised

    h.provider.during_fetch = interrupt
    worker = InThread(lambda: a.ensure_synced(force=False), "caller A")
    with pytest.raises(type(raised)):
        worker.join()
    assert redis.get(LOCK) is None, "released"
    assert not seen["lease"].renewing and renewal_workers_alive() == [], "renewal stopped"

    h.provider.during_fetch = None
    report = service(h).ensure_synced(force=False)       # and nobody is locked out
    assert report["competitions"]["premier_league"]["fetched"] == 1


# ------------------------------------------------------------------ the rules still hold
@pytest.mark.parametrize("policy", [POLICY_DAILY_SLOT, POLICY_ELAPSED_INTERVAL])
def test_both_policies_and_forced_refresh_keep_their_rules_under_the_lease(clock, redis, monkeypatch, policy):
    monkeypatch.setattr(settings, "GAMEFORECAST_REFRESH_POLICY", policy)
    h = harness(clock, redis, ["premier_league"])
    assert service(h).ensure_synced(force=False)["competitions"]["premier_league"]["fetched"] == 1
    clock.now = START + timedelta(minutes=30)
    again = service(h).ensure_synced(force=False)
    assert "premier_league" not in again["competitions"] and "premier_league" in again["skipped"]
    clock.now = START + timedelta(minutes=31)
    forced = service(h).ensure_synced(force=True)
    assert forced["competitions"]["premier_league"]["fetched"] == 1
    assert h.budget.used_today() == 2 and redis.get(LOCK) is None


# ------------------------------------------------------------------ against real storage
def test_against_the_real_registry_a_late_answer_leaves_the_successors_forecast_standing(db):
    """The late-answer interleaving over the test database: the forecast row and its snapshot carry
    B's retrieval, not A's."""
    start = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
    clock = Clock(start)
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    budget = RequestBudget(PROVIDER, 8, client=redis, now=clock)
    provider = OneForecastProvider(budget, clock, expected=[DB_KEY])
    registry = MatchRegistry(db)
    match = _store_the_fixture(registry)
    db.flush()

    inside, release = threading.Event(), threading.Event()
    send = provider.get_forecasts

    def in_flight(key, date_from, date_to):
        answer = send(key, date_from, date_to)              # reserved, sent and stamped
        if threading.current_thread().name == "caller A" and not release.is_set():
            inside.set()
            assert release.wait(WAIT_SECONDS)
        return answer

    provider.get_forecasts = in_flight

    def build() -> ForecastService:
        svc = ForecastService(db, provider=provider, cache=cache, now=clock(), keys=[DB_KEY], sync_fixtures=False)
        svc.registry = registry
        return svc

    a = build()
    a.lease_waiter = Ticker()
    first = InThread(lambda: a.ensure_synced(force=False), "caller A")
    wait(inside, "A to be inside its request")
    clock.now = start + timedelta(seconds=301)
    report_b = InThread(lambda: build().ensure_synced(force=False), "caller B").join()
    assert report_b["competitions"][DB_KEY]["attached"] == 1
    release.set()
    report_a = first.join()
    db.flush()

    taken_over = start + timedelta(seconds=301)
    assert report_a.get("lease_lost") is True and budget.used_today() == 2
    [snapshot] = a.snapshots_for_match(match.id, PROVIDER)
    as_utc = lambda value: value.replace(tzinfo=timezone.utc)  # noqa: E731 - stored naive UTC
    assert as_utc(snapshot.first_fetched_at) == as_utc(snapshot.last_fetched_at) == taken_over


def test_an_older_retrieval_never_replaces_a_newer_forecast_row(db):
    """The guard for the window a lease cannot close alone - a worker that confirmed its lease, then
    stalled past a term before writing - and for a pending forecast re-attached after a newer fetch
    of the same event: the current row and the snapshot's last retrieval never go backwards."""
    from app.models.provider_data import ProviderForecastRecord
    from app.services.providers.base import ProviderForecast
    from tests.services.test_forecast_retention_db import KICKOFF, _event

    now = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
    service = ForecastService(db, provider=None, cache=MatchCache(client=LockingFakeRedis()), now=now,
                              keys=[DB_KEY], sync_fixtures=False, use_default_provider=False)
    service.registry = MatchRegistry(db)
    match = _store_the_fixture(service.registry)
    league = service.registry.ensure_canonical_league(DB_KEY)
    db.flush()

    def forecast(retrieved, home_prob):
        return ProviderForecast(provider=PROVIDER, external_event_id="evt-27378", competition_key=DB_KEY,
                                home_name="Rep. Of Ireland", away_name="Kosovo", kickoff_utc=KICKOFF,
                                home_prob=home_prob, draw_prob=0.3, away_prob=round(0.7 - home_prob, 2),
                                model_run_at=retrieved.replace(hour=6, minute=0), fetched_at=retrieved, raw=_event())

    newer, older = now + timedelta(minutes=5), now
    assert service.attach_forecast(forecast(newer, 0.40), DB_KEY, league.id)["result"] == "attached"
    assert service.attach_forecast(forecast(older, 0.38), DB_KEY, league.id)["result"] == "attached"
    assert service.attach_forecast(forecast(older, 0.40), DB_KEY, league.id)["result"] == "attached"
    db.flush()

    row = db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == match.id).one()
    assert row.fetched_at.replace(tzinfo=timezone.utc) == newer and float(row.home_win_prob) == 0.40
    snapshots = service.snapshots_for_match(match.id, PROVIDER)
    latest = snapshots[-1]
    assert float(latest.home_win_prob) == 0.40
    assert latest.last_fetched_at.replace(tzinfo=timezone.utc) == newer, "never moved backwards"
    assert any(float(s.home_win_prob) == 0.38 for s in snapshots), "the older retrieval kept as history"
