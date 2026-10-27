"""
A forecast pass interrupted after one competition is finished within minutes, not after six hours.

WHAT HAPPENED, 2026-10-24 (live release 69ac15f8). The Mac was asleep, dark-waking for a few seconds
every fifteen to twenty minutes. The day's forecast pass ran inside the 30-second wake of 12:09:25Z:
it took the sync lease, fetched Serie A and recorded Serie A's daily slot at 12:09:30, renewed the
lease for Bundesliga's turn, and at 12:09:32 its next fenced write was refused - "the lease is no
longer this worker's". Seven seconds into a five-minute term, with nobody else running.

The lease had expired in Redis, prematurely. The most likely cause - an inference from Redis's own
RDB-save log, not a direct observation - is the clock of Docker Desktop's Linux VM, where Redis runs:
it stands still while the host sleeps and is stepped forward some seconds after a wake. The saves
("1 changes in 900 seconds") fired that morning at the first seconds of some wakes, never at the
earlier wakes where the application had written, and one fired at 12:09:32.309 - the instant the pass
lost its lease. A lease taken under a clock about 35 minutes behind, then stepped past the term, is a
lease that has expired. Renewal cannot protect against that: PEXPIRE is relative to the same clock.

The pass was then recorded as a FAILURE, and the scheduler's failure backoff is the task's own
interval: six hours. Bundesliga, the Premier League, La Liga and Ligue 1 were fetched at 18:10Z.
Eleven fixtures kicked off in the gap, each still showing the previous day's forecast. The
allowance stood at 5 of 8; nothing stopped a retry but the schedule.

WHAT HOLDS NOW. A forecasts pass that stops for a reason of coordination - its lease lost mid-pass,
or held by another worker when the pass comes due - is retried on a short, bounded schedule: one
lease term, then double, three times, then the ordinary backoff. The retry buys only what is still
owed: the daily-slot policy keeps every slot the interrupted pass recorded, so Serie A is never
bought twice. Ownership is checked exactly as before, a stale owner's late answer is still refused,
a competing worker's lease is never cleared, a paused provider is waited for, a spent allowance is
skipped. The schedule lives in the task's state in Redis, so a restart neither resets it nor repeats
finished work. The pass and the task now say how they ended: completed, partial, deferred or failed.

HOW TIME IS SIMULATED. Two clocks: `clock` is the application's (the host's, which was right), and
`redis_clock` is the Redis stand-in's own, which expires keys - started 2140 s behind and stepped to
real time at the moment the incident's is inferred to have been. The decisive tests import nothing this round added, so
this file runs against the previous implementation and fails there for the six-hour wait. The same
interruption runs against a real, isolated Redis at the end, where "the clock stepped past the term"
is produced the way test_sync_lease_redis.py produces a lapsed lease. The network is closed.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest

from app.services.forecast_refresh_policy import OUTCOME_SAME_DAY_RUN
from app.services.forecast_service import SYNC_LOCK_KEY, ForecastService
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.base import (
    ProviderCompetition, ProviderFixture, ProviderForecast, ProviderTeam, ProviderUnavailableError,
)
from app.services.providers.budget import RequestBudget
from app.services.settlement import prematch_snapshots
from app.services.sync_lease import SyncLease
from app.services.sync_scheduler import TASK_FORECASTS, SyncScheduler
from tests.services.test_forecast_refresh_policy import PROVIDER, Harness
from tests.services.test_forecast_retention_db import (  # noqa: F401 - pytest fixtures
    KEY as DB_KEY, _event, _store_the_fixture, db, engine,
)
from tests.services.test_forecast_sync_concurrency import (  # noqa: F401 - shared fixtures
    InThread, StrictStubProvider, daily_slot, wait,
)
from tests.services.test_forecast_sync_lease import (
    Ticker, harness as in_flight_harness, hold_inside_the_fetch, renewal_workers_alive,
)
from tests.services.test_sync_lease_redis import (  # noqa: F401 - the isolated real Redis, if any
    identity, lapse, only_the_isolated_redis, real,
)
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

#: The pass of the incident began at 12:09:25Z, the first second of a 30-second dark wake.
START = datetime(2026, 10, 24, 12, 9, 25, tzinfo=timezone.utc)
#: By that inference the server's clock had stood still through the two host sleeps before that wake
#: (11:33:40 to 11:51:34 and 11:51:39 to 12:09:25) and was stepped forward at 12:09:32.
LAG = timedelta(seconds=2140)
TERM = timedelta(seconds=300)                # SYNC_LOCK_TTL_SECONDS
FIFTEEN_MINUTES = timedelta(minutes=15)
KEYS = ["serie_a", "bundesliga", "premier_league", "la_liga", "ligue_1"]
REMAINING = KEYS[1:]
#: The day's first kick-offs per competition: Serie A leads the plan, and the four others all
#: kicked off before 18:10Z, the pass that eventually fetched them.
KICKOFFS = {"serie_a": START.replace(hour=13, minute=0, second=0),
            "bundesliga": START.replace(hour=13, minute=30, second=0),
            "premier_league": START.replace(hour=14, minute=0, second=0),
            "la_liga": START.replace(hour=14, minute=15, second=0),
            "ligue_1": START.replace(hour=18, minute=45, second=0)}
LOCK = SYNC_LOCK_KEY.format(provider=PROVIDER)
REAL_URL = os.environ.get("LEASE_TEST_REDIS_URL")


@pytest.fixture
def clock():
    return Clock(START)


@pytest.fixture
def redis_clock():
    """The Redis server's clock as the incident is inferred to have found it: behind, about to be stepped."""
    return Clock(START - LAG)


@pytest.fixture
def redis(redis_clock):
    return LockingFakeRedis(clock=redis_clock)


# ------------------------------------------------------------------ the two interruptions
def stepping_the_server_clock_before(svc: ForecastService, key: str, redis_clock: Clock, clock: Clock) -> ForecastService:
    """Right before `key`'s turn records its calendar evidence - after the lease was renewed for the
    turn, before the turn's first fenced write - the server's clock catches up with real time."""
    policy = svc.policy
    record = policy.record_calendar

    def caught_up(evidence):
        if evidence.key == key:
            redis_clock.now = clock.now
        return record(evidence)

    policy.record_calendar = caught_up
    return svc


def lapsing_the_lease_before(svc: ForecastService, key: str, client, once: dict) -> ForecastService:
    """The same moment on a real Redis: the key is let expire, as a clock stepped past the term leaves
    it. Once: the server's clock is stepped at the wake of the incident, not at every pass."""
    policy = svc.policy
    record = policy.record_calendar

    def gone(evidence):
        if evidence.key == key and not once.get("done") and client.exists(LOCK):
            once["done"] = True
            lapse(client, LOCK)
        return record(evidence)

    policy.record_calendar = gone
    return svc


def scheduler_over(h: Harness, clock: Clock, prepare=None, session=None) -> SyncScheduler:
    """The shipped scheduler over the harness's store, building a fresh service each pass as it does."""
    def build(_db):
        svc = h.new_service()
        return prepare(svc) if prepare else svc

    return SyncScheduler(session_factory=lambda: session if session is not None else MagicMock(),
                         cache=h.cache, now=clock, match_service_factory=lambda db: MagicMock(),
                         forecast_service_factory=build, tasks=[TASK_FORECASTS], close_sessions=False,
                         budget_client=h.redis)


def run(scheduler: SyncScheduler) -> dict:
    return scheduler.run_once(only=[TASK_FORECASTS])["tasks"][TASK_FORECASTS]


def next_due(scheduler: SyncScheduler) -> datetime:
    return datetime.fromisoformat(scheduler.state(TASK_FORECASTS)["next_due_at"])


def advance(clock: Clock, redis_clock: Clock, to: datetime) -> None:
    """Real time passes for both; the server's clock, once stepped, keeps up with the host's."""
    clock.now = to
    redis_clock.now = to


# ================================================================== 1. the incident, reproduced
def test_the_incident_a_server_clock_step_past_the_term_ends_the_pass_after_one_competition(clock, redis, redis_clock):
    """Serie A is fetched and its slot recorded; the lease is renewed for Bundesliga's turn; then the
    turn's first write is refused, with the message the live log carries, and the pass stops having
    bought exactly one competition."""
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    svc = stepping_the_server_clock_before(h.new_service(), "bundesliga", redis_clock, clock)

    report = svc.ensure_synced()

    assert report.get("lease_lost") is True
    assert "a write was refused: the lease is no longer this worker's" in report["error"]
    assert report["plan"]["fetch"] == KEYS, "every competition was eligible, Serie A first by kick-off"
    assert list(report["competitions"]) == ["serie_a"]
    assert h.calls() == ["serie_a"] and h.budget.used_today() == 1
    assert svc.policy.slot("serie_a")["outcome"] == OUTCOME_SAME_DAY_RUN, "the day's slot, taken and kept"
    assert all(svc.policy.slot(key) == {} for key in REMAINING), "nothing recorded for the four not reached"
    assert redis.get(LOCK) is None and renewal_workers_alive() == []


# ================================================================== 2. the decisive regression
def test_an_interrupted_pass_is_retried_within_fifteen_minutes_and_finishes_what_it_owed(clock, redis, redis_clock):
    """The previous implementation recorded the interrupted pass as a failure and backed it off the
    task's own interval: six hours, during which eleven fixtures kicked off. Now the retry comes
    within one lease term, and buys exactly the four competitions still owed - Serie A once."""
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))

    first = run(scheduler)
    assert first["ran"] and first["result"].get("lease_lost") is True and h.calls() == ["serie_a"]
    due = next_due(scheduler)
    assert due <= clock.now + FIFTEEN_MINUTES, (
        f"the retry waits {due - clock.now}; the previous implementation waited the whole "
        f"{scheduler.interval(TASK_FORECASTS)} s interval as its backoff")
    assert due >= clock.now + TERM, "no sooner than a lease nobody renews takes to lapse"

    advance(clock, redis_clock, due - timedelta(seconds=1))
    assert scheduler.due(TASK_FORECASTS)[0] is False
    assert run(scheduler)["ran"] is False and h.calls() == ["serie_a"], "no busy loop before the retry is due"

    advance(clock, redis_clock, due)
    retry = run(scheduler)
    assert retry["ran"] and retry["ok"] is True
    assert h.calls() == KEYS, "the retry bought the four competitions still owed, and nothing twice"
    assert h.budget.used_today() == 5
    assert retry["result"]["plan"]["ineligible"]["serie_a"].startswith(f"{OUTCOME_SAME_DAY_RUN} for 2026-10-24")
    policy = h.new_service().policy
    assert all(policy.slot(key)["outcome"] == OUTCOME_SAME_DAY_RUN for key in KEYS)
    assert all(datetime.fromisoformat(policy.slot(key)["fetched_at"]) < KICKOFFS[key] for key in REMAINING), (
        "each forecast received before its first kick-off of the day")
    state = scheduler.state(TASK_FORECASTS)
    assert state["consecutive_failures"] == 0 and state["backoff_seconds"] is None
    # The ordinary cadence resumes on its own grid: the first slot at least an hour after a pass
    # that spent requests, 18:12 - not six hours after the retry's completion, which is what
    # drifted live's passes by hours after every host sleep (tests/services/test_forecast_cadence.py),
    # and not the 12:12 slot minutes away, which could only re-check what was just fetched.
    assert next_due(scheduler) == START.replace(hour=18, minute=12, second=0)
    assert next_due(scheduler) < clock.now + timedelta(seconds=scheduler.interval(TASK_FORECASTS))


def test_repeated_interruptions_are_retried_on_a_bounded_schedule_and_then_backed_off(clock, redis, redis_clock):
    """Three retries, each twice the wait before - 5, 10, 20 minutes - and the fourth interruption
    is treated as the failure it has become. None of them spends a request: the lease is lost
    before Bundesliga's turn reserves one, and Serie A's slot stands throughout."""
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)

    def lagging_again(svc):
        redis_clock.now = clock.now - LAG               # the server's clock is behind again...
        return stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock)   # ...and steps

    scheduler = scheduler_over(h, clock, lagging_again)
    waits = []
    for _ in range(4):
        assert run(scheduler)["result"].get("lease_lost") is True
        due = next_due(scheduler)
        waits.append(due - clock.now)
        advance(clock, redis_clock, due)

    assert waits[:3] == [timedelta(seconds=300), timedelta(seconds=600), timedelta(seconds=1200)]
    assert waits[3] == timedelta(seconds=scheduler.interval(TASK_FORECASTS)), "the ordinary backoff, once the retries are spent"
    state = scheduler.state(TASK_FORECASTS)
    assert state["consecutive_failures"] == 1 and state["backoff_seconds"] == scheduler.interval(TASK_FORECASTS)
    assert h.calls() == ["serie_a"] and h.budget.used_today() == 1, "no retry spent anything"
    assert h.new_service().policy.slot("serie_a")["outcome"] == OUTCOME_SAME_DAY_RUN


# ================================================================== 3. what the retry meets
def test_a_competing_worker_holding_the_lease_when_the_retry_is_due_defers_it_without_a_request(clock, redis, redis_clock):
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))
    run(scheduler)
    assert h.calls() == ["serie_a"]
    advance(clock, redis_clock, next_due(scheduler))

    other = SyncLease(redis, LOCK, 300)
    assert other.acquire(), "another worker is mid-pass when the retry comes due"
    deferred = run(scheduler)
    assert deferred["ran"] and deferred["ok"] is False and "already running" in deferred["result"]["error"]
    assert h.calls() == ["serie_a"], "nothing bought, nothing cleared"
    assert redis.get(LOCK) == other.token, "the other worker's lease was left exactly as it was"
    again = next_due(scheduler)
    assert clock.now + TERM <= again <= clock.now + FIFTEEN_MINUTES
    assert scheduler.state(TASK_FORECASTS).get("consecutive_failures", 0) == 0, "a deferral is not a failure"

    assert other.release()
    advance(clock, redis_clock, again)
    done = run(scheduler)
    assert done["ok"] is True and h.calls() == KEYS and h.budget.used_today() == 5


def test_a_provider_cooldown_at_retry_time_defers_the_retry_until_the_cooldown_ends(clock, redis, redis_clock):
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))
    run(scheduler)
    retry_at = next_due(scheduler)

    advance(clock, redis_clock, retry_at - timedelta(seconds=60))
    h.new_service()._pause("the provider answered 503 to a page load", 7200)   # set by another path
    paused_until = clock.now + timedelta(seconds=7200)
    advance(clock, redis_clock, retry_at)
    deferred = run(scheduler)
    assert deferred["ran"] and deferred["result"].get("paused") is True
    assert h.calls() == ["serie_a"], "a paused provider is not called"
    assert next_due(scheduler) == paused_until, "the retry waits for the pause, not a fixed delay"
    assert scheduler.state(TASK_FORECASTS).get("consecutive_failures", 0) == 0

    advance(clock, redis_clock, paused_until)
    done = run(scheduler)
    assert done["ok"] is True and h.calls() == KEYS and h.budget.used_today() == 5


def test_an_exhausted_allowance_at_retry_time_is_skipped_like_any_pass_and_resumes_at_the_reset(clock, redis, redis_clock):
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))
    run(scheduler)
    for _ in range(7):
        h.budget.consume(1, reason="fetch")              # page loads spent the rest of the day's eight
    assert h.budget.used_today() == 8
    advance(clock, redis_clock, next_due(scheduler))

    skipped = run(scheduler)
    assert skipped["ran"] is False and skipped["skipped"] == "budget_spent"
    assert h.calls() == ["serie_a"] and h.budget.used_today() == 8, "no request and no refused reservation"
    assert redis.get(h.budget._refused_key()) is None

    reset = datetime(2026, 10, 25, 0, 1, tzinfo=timezone.utc)
    assert next_due(scheduler) <= reset
    advance(clock, redis_clock, reset.replace(hour=12, minute=1))
    tomorrow = run(scheduler)
    assert tomorrow["ok"] is True and h.calls() == ["serie_a"] + KEYS, "a new day: every slot fresh, nothing carried"


def test_a_restart_between_the_interruption_and_the_retry_keeps_the_schedule_and_the_finished_slot(clock, redis, redis_clock):
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    before = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))
    run(before)
    retry_at = next_due(before)
    assert h.calls() == ["serie_a"]

    after = scheduler_over(h, clock)                   # the backend restarted: a fresh scheduler over the same Redis
    advance(clock, redis_clock, retry_at - timedelta(seconds=1))
    assert after.due(TASK_FORECASTS)[0] is False and run(after)["ran"] is False
    advance(clock, redis_clock, retry_at)
    done = run(after)
    assert done["ok"] is True
    assert h.calls() == KEYS and h.budget.used_today() == 5, "the finished slot was not repeated after the restart"
    assert next_due(after) == START.replace(hour=18, minute=12, second=0), "the grid, not six hours after the retry"


def test_a_late_answer_from_the_previous_owner_cannot_overwrite_what_the_retry_fetched(clock, redis, redis_clock):
    """After the scheduler's interrupted pass, a hand-run worker takes the lease and stalls inside
    its Bundesliga request without renewing. Its lease lapses; the scheduler's retry fetches the
    four competitions; the stalled worker's answer then arrives and writes nothing."""
    h = in_flight_harness(clock, redis, KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))
    run(scheduler)
    retry_at = next_due(scheduler)
    assert h.calls() == ["serie_a"]

    stalled = h.new_service()
    stalled.lease_waiter = Ticker()                     # its renewal worker never gets to run
    inside, release = hold_inside_the_fetch(h, "caller A", "bundesliga")
    worker = InThread(lambda: stalled.ensure_synced(), "caller A")
    wait(inside, "the hand-run worker to be inside its Bundesliga request")
    assert h.calls() == ["serie_a", "bundesliga"], "its request has left; the answer is not back"

    advance(clock, redis_clock, retry_at)              # one term later: the stalled lease has lapsed
    retry = run(scheduler)
    assert retry["ok"] is True
    assert h.calls() == ["serie_a", "bundesliga", "bundesliga", "premier_league", "la_liga", "ligue_1"]

    release.set()
    late = worker.join()
    assert late.get("lease_lost") is True and late["competitions"] == {}
    policy = h.new_service().policy
    assert all(policy.slot(key)["fetched_at"] == retry_at.isoformat() for key in REMAINING), "the retry's records stand"
    pending = h.cache.get(stalled._pending_key("bundesliga"))
    assert [item["fetched_at"] for item in pending] == [retry_at.isoformat()], "the late answer was dropped"
    assert h.budget.used_today() == 6, "the request that had already left was charged; nothing after it"
    assert redis.get(LOCK) is None and renewal_workers_alive() == []


# ================================================================== 4. how the pass and the task say they ended
def test_the_pass_report_and_the_task_state_say_how_the_pass_ended(clock, redis, redis_clock):
    from app.services.forecast_service import PASS_COMPLETED, PASS_DEFERRED, PASS_FAILED, PASS_PARTIAL
    from app.services.sync_scheduler import FORECASTS_RECOVERY_MAX_RETRIES, FORECASTS_RECOVERY_RETRY_SECONDS

    assert FORECASTS_RECOVERY_RETRY_SECONDS == 300 and FORECASTS_RECOVERY_MAX_RETRIES == 3
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))

    partial = run(scheduler)
    assert partial["result"]["outcome"] == partial["outcome"] == PASS_PARTIAL
    assert partial["result"]["unfinished"] == REMAINING
    state = scheduler.state(TASK_FORECASTS)
    assert state["last_outcome"] == PASS_PARTIAL
    assert state["recovery"]["attempts"] == 1 and state["recovery"]["unfinished"] == REMAINING
    assert state["recovery"]["retry_at"] == state["next_due_at"] and state["recovery"]["reason"] == PASS_PARTIAL
    status = scheduler.status()["tasks"][TASK_FORECASTS]
    assert status["last_outcome"] == PASS_PARTIAL and status["recovery"] == state["recovery"]

    advance(clock, redis_clock, next_due(scheduler))
    other = SyncLease(redis, LOCK, 300)
    assert other.acquire()
    deferred = run(scheduler)
    assert deferred["result"]["outcome"] == PASS_DEFERRED and deferred["result"].get("lease_held") is True
    assert scheduler.state(TASK_FORECASTS)["recovery"]["attempts"] == 2
    assert other.release()

    advance(clock, redis_clock, next_due(scheduler))
    answer = h.provider.get_forecasts

    def refusing(key, date_from, date_to):
        raise ProviderUnavailableError("upstream is down", provider=PROVIDER)

    h.provider.get_forecasts = refusing
    failed = run(scheduler)
    assert failed["result"]["outcome"] == PASS_FAILED and failed["result"]["unfinished"] == REMAINING
    state = scheduler.state(TASK_FORECASTS)
    assert state["last_outcome"] == PASS_FAILED and "recovery" not in state
    assert state["last_recovery"]["ended"] == PASS_FAILED and state["last_recovery"]["attempts"] == 2
    assert state["consecutive_failures"] == 1 and state["backoff_seconds"] == scheduler.interval(TASK_FORECASTS), (
        "a provider failure keeps the backoff it always had")

    h.provider.get_forecasts = answer
    advance(clock, redis_clock, next_due(scheduler))
    completed = run(scheduler)
    assert completed["result"]["outcome"] == completed["outcome"] == PASS_COMPLETED
    assert scheduler.state(TASK_FORECASTS)["last_outcome"] == PASS_COMPLETED
    assert h.calls() == KEYS and h.budget.used_today() == 5


# ================================================================== 5. against the real registry
class TwoFixturesProvider(StrictStubProvider):
    """Forecasts for two stored fixtures, spelled as the match provider spells them, so they bind; the
    probabilities move from one day to the next, so each day's fetch is new content and a new snapshot."""

    FIXTURES = {
        "serie_a": ("Inter", "Milan", "evt-sa-1"),
        DB_KEY: ("Rep. Of Ireland", "Kosovo", "evt-27378"),
    }

    def __init__(self, budget, clock, kickoffs, expected):
        super().__init__(budget, clock, expected=expected)
        self.kickoffs = kickoffs

    def get_forecasts(self, key, date_from, date_to):
        if key not in self.expected:
            raise AssertionError(f"unexpected provider request for {key}")
        self.budget.consume(1, reason="fetch")
        now = self.clock()
        self.calls.append((key, now))
        home, away, event = self.FIXTURES[key]
        home_prob = 0.38 if now.date() < START.date() else 0.41
        return [ProviderForecast(provider=PROVIDER, external_event_id=event, competition_key=key,
                                 home_name=home, away_name=away, kickoff_utc=self.kickoffs[key],
                                 home_prob=home_prob, draw_prob=0.32, away_prob=round(0.68 - home_prob, 2),
                                 model_run_at=now.replace(hour=6, minute=0, second=0, microsecond=0),
                                 fetched_at=now, raw=_event())]


def test_against_the_real_registry_the_retry_adds_no_duplicate_snapshot_and_scoring_keeps_the_prematch_one(db):
    """Yesterday's pass left a prematch snapshot on both fixtures. Today's pass is interrupted after
    Serie A; the second fixture kicks off before the retry. The retry fetches it once more, after
    kick-off: that snapshot is stored, flagged as captured after kick-off, and never scored - the
    prematch one still is. Serie A keeps exactly the snapshots its two fetches produced."""
    keys = ["serie_a", DB_KEY]
    # Both kick off inside the gap between the interruption (12:09:25Z) and the retry; the plan walks
    # the nearer kick-off first, so Serie A is the competition the interrupted pass does fetch.
    kickoffs = {"serie_a": START + timedelta(minutes=1, seconds=35),       # 12:11:00Z
                DB_KEY: START + timedelta(minutes=3, seconds=35)}          # 12:13:00Z
    clock = Clock(START - timedelta(days=1, minutes=4, seconds=25))   # yesterday's pass, 12:05Z
    redis_clock = Clock(clock.now)
    redis = LockingFakeRedis(clock=redis_clock)
    cache = MatchCache(client=redis)
    budget = RequestBudget(PROVIDER, 8, client=redis, now=clock)
    provider = TwoFixturesProvider(budget, clock, kickoffs, expected=keys)
    registry = MatchRegistry(db)
    serie_a = registry.upsert_fixture(ProviderFixture(
        provider="livescore", external_id="ls-sa-1",
        competition=ProviderCompetition(provider="livescore", external_id="4", name="Serie A", key="serie_a"),
        home=ProviderTeam(provider="livescore", external_id="ls-inter", name="Inter"),
        away=ProviderTeam(provider="livescore", external_id="ls-milan", name="Milan"),
        kickoff_utc=kickoffs["serie_a"], status="scheduled"))
    second = _store_the_fixture(registry, kickoff=kickoffs[DB_KEY])
    db.flush()

    def build(step: Optional[str] = None) -> ForecastService:
        svc = ForecastService(db, provider=provider, cache=cache, now=clock(), keys=keys, sync_fixtures=False)
        svc.registry = registry
        return stepping_the_server_clock_before(svc, step, redis_clock, clock) if step else svc

    scheduler = SyncScheduler(session_factory=lambda: db, cache=cache, now=clock,
                              match_service_factory=lambda _db: MagicMock(),
                              forecast_service_factory=lambda _db: build(DB_KEY),
                              tasks=[TASK_FORECASTS], close_sessions=False, budget_client=redis)

    yesterday = run(scheduler)                           # D-1 12:05Z: both fetched, both prematch
    assert yesterday["ok"] is True and [k for k, _ in provider.calls] == keys
    db.flush()
    assert len(build().snapshots_for_match(serie_a.id, PROVIDER)) == 1
    [first_second] = build().snapshots_for_match(second.id, PROVIDER)
    assert first_second.captured_before_kickoff is True

    advance(clock, redis_clock, START)                   # D 12:09:25Z, the server's clock behind again
    redis_clock.now = START - LAG
    today = run(scheduler)
    assert today["result"].get("lease_lost") is True and [k for k, _ in provider.calls] == keys + ["serie_a"]
    retry_at = next_due(scheduler)
    assert retry_at <= START + FIFTEEN_MINUTES
    assert kickoffs["serie_a"] < kickoffs[DB_KEY] < retry_at, "both fixtures kick off inside the gap"

    advance(clock, redis_clock, retry_at)
    retry = run(scheduler)
    assert retry["ok"] is True and [k for k, _ in provider.calls] == keys + ["serie_a", DB_KEY]
    db.flush()

    serie_a_snapshots = build().snapshots_for_match(serie_a.id, PROVIDER)
    assert len(serie_a_snapshots) == 2 and all(s.captured_before_kickoff is True for s in serie_a_snapshots), (
        "yesterday's and today's content, both prematch; the retry added none")
    second_snapshots = build().snapshots_for_match(second.id, PROVIDER)
    assert len(second_snapshots) == 2
    prematch, late = second_snapshots
    assert prematch.id == first_second.id and prematch.captured_before_kickoff is True
    assert prematch.first_fetched_at.replace(tzinfo=timezone.utc) == START - timedelta(days=1, minutes=4, seconds=25), (
        "the original retrieval time is untouched")
    assert late.captured_before_kickoff is False
    assert late.first_fetched_at.replace(tzinfo=timezone.utc) == retry_at
    chosen = prematch_snapshots(db, [serie_a.id, second.id])
    assert chosen[(second.id, PROVIDER)].id == prematch.id, "scoring keeps the prematch snapshot"
    assert chosen[(serie_a.id, PROVIDER)].id == serie_a_snapshots[-1].id
    assert budget.used_today() == 2 and provider.budget is budget


# ================================================================== 6. on a real, isolated Redis
@pytest.mark.skipif(not REAL_URL, reason="LEASE_TEST_REDIS_URL is not set: no isolated Redis to run the real scripts on")
def test_on_a_real_redis_the_interrupted_pass_is_retried_within_fifteen_minutes_and_finishes(real, clock):
    h = Harness(clock, real, keys=KEYS, kickoffs=KICKOFFS)
    stepped = {}
    scheduler = scheduler_over(h, clock, lambda svc: lapsing_the_lease_before(svc, "bundesliga", real, stepped))

    first = run(scheduler)
    assert first["result"].get("lease_lost") is True
    assert "a write was refused: the lease is no longer this worker's" in first["result"]["error"]
    assert h.calls() == ["serie_a"] and h.budget.used_today() == 1, "the real budget counter moved once"
    due = next_due(scheduler)
    assert clock.now + TERM <= due <= clock.now + FIFTEEN_MINUTES
    assert not real.exists(LOCK)

    clock.now = due
    retry = run(scheduler)
    assert retry["ok"] is True and h.calls() == KEYS and h.budget.used_today() == 5
    assert not real.exists(LOCK) and renewal_workers_alive() == []
    policy = h.new_service().policy
    assert all(policy.slot(key)["outcome"] == OUTCOME_SAME_DAY_RUN for key in KEYS)


# ================================================================== 7. the retry owes the turns, not the re-check; midnight is not a deadline
def test_a_recovery_retry_leaves_an_older_model_re_check_to_the_ordinary_pass(clock, redis, redis_clock):
    """12:00: Serie A is served yesterday's run and takes its slot as `older-run`, which owes the day
    ONE re-check later. The lease is lost before Bundesliga finishes. 12:05: the retry buys Bundesliga
    and nothing else - it does not spend Serie A's re-check on a run that has not changed. Today's run
    is published at 13:00; the ordinary pass of 18:05 re-checks Serie A and gets it (and re-checks
    Bundesliga too, which the retry had been served the same old run for)."""
    from tests.services.test_forecast_refresh_policy import todays_run, yesterdays_run
    from app.services.forecast_refresh_policy import OUTCOME_OLDER_RUN

    noon = START.replace(hour=12, minute=0, second=0)
    published = noon.replace(hour=13)
    advance(clock, redis_clock, noon)
    redis_clock.now = noon - LAG
    keys = ["serie_a", "bundesliga"]
    h = Harness(clock, redis, keys=keys, kickoffs=KICKOFFS,
                run_at=lambda now: todays_run(now) if now >= published else yesterdays_run(now))
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))

    first = run(scheduler)
    assert first["result"].get("lease_lost") is True and h.calls() == ["serie_a"]
    slot = h.new_service().policy.slot("serie_a")
    assert slot["outcome"] == OUTCOME_OLDER_RUN and "recheck" not in slot

    advance(clock, redis_clock, next_due(scheduler))                       # 12:05
    retry = run(scheduler)
    assert retry["ok"] is True
    assert h.calls() == ["serie_a", "bundesliga"], "the retry bought the unfinished competition and nothing else"
    assert "recheck" not in h.new_service().policy.slot("serie_a"), "Serie A's one re-check of the day is still owed"
    assert retry["result"].get("rechecked", []) == []
    assert "serie_a" in retry["result"].get("recheck_skipped", {})

    later = next_due(scheduler)
    # The ordinary slot after a pass that spent requests is the first one at least an hour after it
    # ended: 18:12 on the grid, not the 12:12 slot seven minutes away, which could only have spent
    # Serie A's one re-check of the day on a run that had not changed.
    assert later == START.replace(hour=18, minute=12, second=0)                             # 18:12
    advance(clock, redis_clock, later)
    ordinary = run(scheduler)
    assert ordinary["ok"] is True and h.calls() == ["serie_a", "bundesliga", "serie_a", "bundesliga"]
    for key in keys:
        slot = h.new_service().policy.slot(key)
        assert slot["outcome"] == OUTCOME_SAME_DAY_RUN and slot["first_outcome"] == OUTCOME_OLDER_RUN
        assert slot["recheck"]["outcome"] == OUTCOME_SAME_DAY_RUN
    assert ordinary["result"]["rechecked"] == ["serie_a", "bundesliga"]
    assert h.budget.used_today() == 4, "four requests in the day: two turns and the two re-checks they earned, none wasted"


def test_an_interruption_just_before_midnight_still_waits_the_recovery_minimum(clock, redis, redis_clock):
    """23:59: the pass is interrupted. The retry is due at 00:04 - one lease term - and not at 00:01,
    the budget reset two minutes away. On the new day, before the publication hour, the retry finds
    nothing eligible and buys nothing: the reset gave back an allowance, not a reason to fetch."""
    late = START.replace(hour=23, minute=59, second=0)
    advance(clock, redis_clock, late)
    redis_clock.now = late - LAG
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))

    assert run(scheduler)["result"].get("lease_lost") is True and h.calls() == ["serie_a"]
    due = next_due(scheduler)
    assert due == late + TERM, f"the retry waits {due - late}: one lease term across midnight, not the reset at 00:01"

    advance(clock, redis_clock, due)                                        # 00:04 the next day
    retry = run(scheduler)
    assert retry["ok"] is True and h.calls() == ["serie_a"], "nothing is eligible before the publication hour, so nothing was bought"
    assert all("publication hour" in why for why in retry["result"]["plan"]["ineligible"].values())
    assert "recovery" not in scheduler.state(TASK_FORECASTS)

    # The ordinary grid resumes. The episode spent a request, so the slot twelve minutes after the
    # retry (00:12) is skipped for the first one at least an hour away: 06:12, before the hour,
    # buys nothing; 12:12 buys the new day.
    advance(clock, redis_clock, next_due(scheduler))                        # 06:12: still before the hour
    assert clock.now == late.replace(hour=6, minute=12) + timedelta(days=1)
    assert run(scheduler)["ok"] is True and h.calls() == ["serie_a"]
    advance(clock, redis_clock, next_due(scheduler))                        # 12:12: the new day's pass
    assert clock.now == late.replace(hour=12, minute=12) + timedelta(days=1)
    assert run(scheduler)["ok"] is True and h.calls() == ["serie_a"] + KEYS, "the new day's slots, bought at the ordinary hour"


def test_a_provider_pause_that_outlasts_midnight_is_waited_for_in_full(clock, redis, redis_clock):
    late = START.replace(hour=23, minute=50, second=0)
    advance(clock, redis_clock, late)
    redis_clock.now = late - LAG
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))
    run(scheduler)
    retry_at = next_due(scheduler)                                           # 23:55

    advance(clock, redis_clock, retry_at - timedelta(seconds=60))
    h.new_service()._pause("the provider answered 503 to a page load", 5760)   # until 01:30
    paused_until = clock.now + timedelta(seconds=5760)
    advance(clock, redis_clock, retry_at)
    deferred = run(scheduler)
    assert deferred["result"].get("paused") is True and h.calls() == ["serie_a"]
    assert next_due(scheduler) == paused_until, "the pause is waited for in full; the reset at 00:01 does not cut it short"

    advance(clock, redis_clock, paused_until)                                # 01:30: before the publication hour
    done = run(scheduler)
    assert done["ok"] is True and h.calls() == ["serie_a"], "the pause ended, the gate still applies: nothing bought"
    assert "recovery" not in scheduler.state(TASK_FORECASTS)


def test_an_episode_crosses_midnight_and_a_restart_without_losing_count_and_ends_in_completion(clock, redis, redis_clock):
    """23:52 interrupted; 23:57 and 00:07 (after a restart) the lease is another worker's; 00:27 still
    - the third retry is the last, and the ordinary backoff follows. The count survives midnight and
    the restart. Once the other worker lets go, the next ordinary pass after the hour completes."""
    late = START.replace(hour=23, minute=52, second=0)
    advance(clock, redis_clock, late)
    redis_clock.now = late - LAG
    h = Harness(clock, redis, keys=KEYS, kickoffs=KICKOFFS)
    scheduler = scheduler_over(h, clock, lambda svc: stepping_the_server_clock_before(svc, "bundesliga", redis_clock, clock))
    assert run(scheduler)["result"].get("lease_lost") is True and h.calls() == ["serie_a"]
    assert next_due(scheduler) == late + TERM                               # 23:57

    def another_worker_is_at_it():
        """Each time the retry comes due, some other worker holds the lease (its own, taken just now)."""
        other = SyncLease(redis, LOCK, 300)
        assert other.acquire()
        return other

    advance(clock, redis_clock, next_due(scheduler))
    other = another_worker_is_at_it()
    assert "already running" in run(scheduler)["result"]["error"]
    assert next_due(scheduler) == clock.now + timedelta(seconds=600)        # 00:07, across midnight
    assert other.release()

    restarted = scheduler_over(h, clock)                                    # the backend restarted meanwhile
    advance(clock, redis_clock, next_due(restarted))
    other = another_worker_is_at_it()
    assert "already running" in run(restarted)["result"]["error"]
    state = restarted.state(TASK_FORECASTS)
    assert state["recovery"]["attempts"] == 3, "the third attempt of ONE episode, not the first of a new day's"
    assert next_due(restarted) == clock.now + timedelta(seconds=1200)       # 00:27
    assert other.release()

    advance(clock, redis_clock, next_due(restarted))
    other = another_worker_is_at_it()
    assert "already running" in run(restarted)["result"]["error"]
    state = restarted.state(TASK_FORECASTS)
    assert "recovery" not in state and state["last_recovery"]["attempts"] == 3 and state["last_recovery"].get("exhausted_at")
    assert state["consecutive_failures"] == 1 and state["backoff_seconds"] == restarted.interval(TASK_FORECASTS)
    assert next_due(restarted) == clock.now + timedelta(seconds=restarted.interval(TASK_FORECASTS))   # 06:27
    assert h.calls() == ["serie_a"], "no retry spent anything while the lease was another worker's"

    assert other.release()
    advance(clock, redis_clock, next_due(restarted))                        # 06:27: before the hour
    assert run(restarted)["ok"] is True and h.calls() == ["serie_a"]
    advance(clock, redis_clock, next_due(restarted))                        # 12:27
    done = run(restarted)
    assert done["ok"] is True and h.calls() == ["serie_a"] + KEYS
    assert restarted.state(TASK_FORECASTS)["last_outcome"] == "completed"
