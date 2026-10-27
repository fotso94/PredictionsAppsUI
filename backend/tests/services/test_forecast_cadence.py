"""
The forecasts task keeps a fixed cadence through sleeps, late passes and recovery retries.

WHAT HAPPENED, 2026-10-26/27 (live release 45c8b0cf). The next ordinary pass was scheduled six hours
after the previous one COMPLETED. The Mac slept across the 18:14 UTC pass on 10-26; the pass ran at
the wake, 20:51, and the next one six hours after that - 02:51, 08:51, 14:51. A second sleep on
10-27 moved the day's first post-noon pass to 15:18 (interrupted; its retry at 15:34) and the cadence
to 03:34 / 09:34 / 15:34 / 21:34. Every sleep moved the day's first eligible pass later, and nothing
ever moved it back: a fixture kicking off between the 12:00 UTC publication hour and a cadence that
had drifted to 15:34 would miss the day's model.

WHAT HOLDS NOW. Ordinary passes sit on a grid: `SYNC_FORECASTS_SLOT_ANCHOR_UTC` (12:12) plus
multiples of `SYNC_FORECASTS_INTERVAL_SECONDS` - 00:12, 06:12, 12:12, 18:12 UTC. A pass is followed
by the first grid slot after it BEGAN, never by its interval counted from completion. So a sleep
across any number of slots costs exactly one catch-up pass (the one due when the host slept), after
which the slots stand where they always were; a pass long enough to cross the next slot is followed
by that slot at once, once; a recovery retry keeps its own timing (5, 10, 20 minutes) and the grid
resumes from the interruption, not from the retry; a spent allowance waits for the next slot; a
failed pass keeps its backoff and is never a refresh; the publication gate, the one-slot-a-day rule,
the re-check rule, pauses, held leases and concurrent workers are untouched - the cadence only
decides WHEN the policy is offered the pass, never what it may buy.

HOW TIME IS SIMULATED. `Clock` is the host's; `LockingFakeRedis` expires keys on the same clock. A
sleep is the clock jumping; a long pass is a stub whose `ensure_synced` advances the clock. The
decisive tests use only `SyncScheduler.run_once()` and the task's own state, so this file runs
against the previous implementation and fails there with "six hours after the delayed completion".
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.services import sync_scheduler
from app.services.forecast_refresh_policy import OUTCOME_SAME_DAY_RUN
from app.services.forecast_service import PASS_COMPLETED, PASS_PARTIAL
from app.services.match_cache import MatchCache
from app.services.providers.budget import RequestBudget, budget_key
from app.services.sync_scheduler import FORECASTS_RECOVERY_RETRY_SECONDS, TASK_FORECASTS, SyncScheduler

try:
    from app.services.sync_scheduler import forecast_slot_after, parse_slot_anchor
except ImportError:  # the previous implementation: the decisive tests below fail there on the state, not here
    forecast_slot_after = parse_slot_anchor = None
from tests.services.test_forecast_recovery import scheduler_over
from tests.services.test_forecast_refresh_policy import KEYS as POLICY_KEYS, Harness
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis, StubForecastService

INTERVAL = 6 * 3600
DAY = datetime(2026, 10, 26, tzinfo=timezone.utc)
SLOTS = [DAY.replace(hour=h, minute=12) for h in (0, 6, 12, 18)]
NOON, EVENING, MIDNIGHT = SLOTS[2], SLOTS[3], SLOTS[0] + timedelta(days=1)


# ------------------------------------------------------------------ harness
class RecordingForecastService(StubForecastService):
    """A stub that records when it was asked and can take time doing it."""

    def __init__(self, clock: Clock, report: Optional[Dict[str, Any]] = None, takes: int = 0,
                 reports: Optional[List[Dict[str, Any]]] = None):
        super().__init__(report=report)
        self.clock = clock
        self.takes = takes
        self.reports = list(reports or [])
        self.asked_at: List[datetime] = []
        self.asked_with: List[Dict[str, Any]] = []

    def ensure_synced(self, *args, **kwargs) -> Dict[str, Any]:
        self.asked_at.append(self.clock())
        self.asked_with.append(dict(kwargs))
        if self.takes:
            self.clock.tick(self.takes)
        self.calls += 1
        if self.reports:
            return dict(self.reports.pop(0))
        return dict(self._report)


def completed() -> Dict[str, Any]:
    return {"provider": "stub", "competitions": {}, "outcome": PASS_COMPLETED}


def interrupted(unfinished: List[str]) -> Dict[str, Any]:
    return {"provider": "stub", "competitions": {}, "outcome": PASS_PARTIAL, "lease_lost": True,
            "unfinished": list(unfinished), "error": "stopped: this worker lost the stub sync lease"}


@pytest.fixture
def clock():
    return Clock(NOON)


@pytest.fixture
def redis(clock):
    return LockingFakeRedis(clock=clock)


@pytest.fixture
def cache(redis):
    return MatchCache(client=redis)


@pytest.fixture(autouse=True)
def _grid(monkeypatch):
    if hasattr(settings, "SYNC_FORECASTS_SLOT_ANCHOR_UTC"):      # absent on the previous implementation
        monkeypatch.setattr(settings, "SYNC_FORECASTS_SLOT_ANCHOR_UTC", "12:12")
    monkeypatch.setattr(settings, "SYNC_FORECASTS_INTERVAL_SECONDS", INTERVAL)


def build(cache, clock, forecast=None, budget_client=None) -> SyncScheduler:
    forecast = forecast if forecast is not None else RecordingForecastService(clock, completed())
    return SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                         match_service_factory=lambda db: MagicMock(), forecast_service_factory=lambda db: forecast,
                         tasks=[TASK_FORECASTS], close_sessions=False,
                         budget_client=budget_client if budget_client is not None else cache._redis())


def run(scheduler: SyncScheduler) -> Dict[str, Any]:
    return scheduler.run_once(only=[TASK_FORECASTS])["tasks"][TASK_FORECASTS]


def next_due(scheduler: SyncScheduler) -> datetime:
    return datetime.fromisoformat(scheduler.state(TASK_FORECASTS)["next_due_at"])


# ------------------------------------------------------------------ the grid itself
def grid_or_skip():
    if parse_slot_anchor is None:
        pytest.skip("the previous implementation has no grid")


def test_the_grid_is_the_anchor_plus_multiples_of_the_interval():
    grid_or_skip()
    anchor = parse_slot_anchor("12:12")
    assert forecast_slot_after(NOON - timedelta(seconds=1), anchor, INTERVAL) == NOON
    assert forecast_slot_after(NOON, anchor, INTERVAL) == EVENING, "strictly after: a pass on its slot is not followed by itself"
    assert forecast_slot_after(DAY.replace(hour=15, minute=18, second=33), anchor, INTERVAL) == EVENING
    assert forecast_slot_after(DAY.replace(hour=23, minute=59), anchor, INTERVAL) == MIDNIGHT
    assert forecast_slot_after(MIDNIGHT - timedelta(minutes=12), anchor, INTERVAL) == MIDNIGHT


def test_a_grid_needs_an_anchor_and_an_interval_that_divides_a_day():
    grid_or_skip()
    assert parse_slot_anchor("") is None and parse_slot_anchor("noon") is None and parse_slot_anchor("25:00") is None
    assert parse_slot_anchor("00:00") == time(0, 0) and parse_slot_anchor("23:59") == time(23, 59)
    assert forecast_slot_after(NOON, parse_slot_anchor("12:12"), 7 * 3600) is None, "seven hours do not divide a day"
    assert forecast_slot_after(NOON, None, INTERVAL) is None


# ------------------------------------------------------------------ decisive: no drift
def test_a_pass_on_its_slot_is_followed_by_the_next_slot(cache, clock):
    scheduler = build(cache, clock)
    assert run(scheduler)["ran"] is True
    assert next_due(scheduler) == EVENING


def test_a_late_pass_is_followed_by_the_grid_not_by_six_hours_after_itself(cache, clock):
    """The 10-26 incident: the 18:14 pass ran at the wake, 20:51, and the next one at 02:51."""
    scheduler = build(cache, clock)
    run(scheduler)                                           # 12:12, on its slot
    clock.now = DAY.replace(hour=20, minute=51, second=7)    # the host slept across 18:12 and woke here
    late = run(scheduler)
    assert late["ran"] is True
    assert next_due(scheduler) == MIDNIGHT, (
        f"next due {next_due(scheduler)}; the previous implementation scheduled "
        f"{clock.now + timedelta(seconds=INTERVAL)}, six hours after the delayed completion")


def test_a_sleep_across_one_slot_costs_exactly_one_catch_up(cache, clock):
    scheduler = build(cache, clock)
    run(scheduler)
    clock.now = DAY.replace(hour=20, minute=30)
    assert run(scheduler)["ran"] is True, "the pass due at 18:12 runs once at the wake"
    clock.now = DAY.replace(hour=20, minute=31)
    assert run(scheduler)["ran"] is False, "and only once"
    clock.now = MIDNIGHT - timedelta(seconds=1)
    assert run(scheduler)["ran"] is False
    clock.now = MIDNIGHT
    assert run(scheduler)["ran"] is True


def test_a_sleep_across_several_slots_costs_exactly_one_catch_up(cache, clock):
    """Asleep from 12:13 on the 26th to 08:00 on the 27th: 18:12, 00:12 and 06:12 missed, one pass runs."""
    forecast = RecordingForecastService(clock, completed())
    scheduler = build(cache, clock, forecast)
    run(scheduler)
    clock.now = DAY + timedelta(days=1, hours=8)
    assert run(scheduler)["ran"] is True
    assert run(scheduler)["ran"] is False, "the missed slots are not replayed"
    assert forecast.calls == 2
    assert next_due(scheduler) == NOON + timedelta(days=1), "the day's first post-noon slot is where it always was"


def test_waking_before_noon_keeps_the_noon_slot(cache, clock):
    scheduler = build(cache, clock)
    run(scheduler)
    clock.now = DAY + timedelta(days=1, hours=11, minutes=50)
    assert run(scheduler)["ran"] is True                      # the catch-up, before the gate
    clock.now = DAY + timedelta(days=1, hours=12, minutes=12)
    assert run(scheduler)["ran"] is True, "noon is still noon"


def test_waking_after_noon_runs_the_catch_up_and_then_the_evening_slot(cache, clock):
    scheduler = build(cache, clock)
    run(scheduler)
    clock.now = DAY + timedelta(days=1, hours=15, minutes=18)
    assert run(scheduler)["ran"] is True
    assert next_due(scheduler) == EVENING + timedelta(days=1)


def test_the_grid_crosses_utc_midnight(cache, clock):
    scheduler = build(cache, clock)
    clock.now = DAY.replace(hour=23, minute=50)
    run(scheduler)
    assert next_due(scheduler) == MIDNIGHT
    clock.now = MIDNIGHT + timedelta(hours=2)                 # slept across 00:12
    assert run(scheduler)["ran"] is True
    assert next_due(scheduler) == MIDNIGHT + timedelta(hours=6)


def test_a_restart_after_a_delayed_pass_keeps_the_grid(cache, clock):
    scheduler = build(cache, clock)
    clock.now = DAY.replace(hour=15, minute=18)
    run(scheduler)
    restarted = build(cache, clock)                           # a fresh scheduler over the same store
    clock.now = DAY.replace(hour=17)
    assert restarted.due(TASK_FORECASTS)[0] is False
    clock.now = EVENING
    assert restarted.due(TASK_FORECASTS)[0] is True
    assert run(restarted)["ran"] is True and next_due(restarted) == MIDNIGHT


def test_a_long_pass_that_crosses_a_slot_is_followed_by_that_slot_once(cache, clock):
    """Began at 11:50, took forty minutes: the 12:12 slot it crossed is due at once, then 18:12."""
    forecast = RecordingForecastService(clock, completed(), takes=40 * 60)
    scheduler = build(cache, clock, forecast)
    clock.now = DAY.replace(hour=11, minute=50)
    run(scheduler)
    assert clock.now == DAY.replace(hour=12, minute=30)
    assert next_due(scheduler) == NOON and scheduler.due(TASK_FORECASTS)[0] is True
    forecast.takes = 0
    assert run(scheduler)["ran"] is True
    assert next_due(scheduler) == EVENING
    assert run(scheduler)["ran"] is False


# ------------------------------------------------------------------ what the catch-up may buy
def test_a_catch_up_before_the_publication_hour_buys_nothing(clock, redis):
    """The policy decides what a pass buys; a catch-up at 08:00 is before the gate and fetches nothing."""
    h = Harness(clock, redis, keys=POLICY_KEYS)
    scheduler = scheduler_over(h, clock)
    clock.now = DAY.replace(hour=8)                           # as if the 00:12 and 06:12 slots were slept through
    report = run(scheduler)
    assert report["ran"] is True and report["ok"] is True
    assert h.calls() == [] and h.budget.used_today() == 0
    assert all("before the observed publication hour" in why
               for why in report["result"]["plan"]["ineligible"].values())
    assert next_due(scheduler) == NOON
    clock.now = NOON
    report = run(scheduler)
    assert sorted(h.calls()) == sorted(POLICY_KEYS) and h.budget.used_today() == len(POLICY_KEYS), "the noon slot buys the day"
    assert next_due(scheduler) == EVENING


def test_already_served_competitions_are_ineligible_on_a_catch_up(clock, redis):
    h = Harness(clock, redis, keys=POLICY_KEYS)
    scheduler = scheduler_over(h, clock)
    run(scheduler)                                            # 12:12: every slot same-day-run
    assert sorted(h.calls()) == sorted(POLICY_KEYS)
    clock.now = DAY.replace(hour=20, minute=51)               # slept across 18:12
    report = run(scheduler)
    assert report["ran"] is True
    assert sorted(h.calls()) == sorted(POLICY_KEYS) and h.budget.used_today() == len(POLICY_KEYS), "nothing bought twice"
    policy = h.new_service().policy
    assert all(policy.slot(key)["outcome"] == OUTCOME_SAME_DAY_RUN for key in POLICY_KEYS)
    assert next_due(scheduler) == MIDNIGHT


def test_a_spent_allowance_waits_for_the_next_slot_and_is_not_a_refresh(cache, clock, redis):
    budget = RequestBudget("stub-forecast", daily_limit=8, client=redis, now=clock)
    redis.store[budget_key("stub-forecast", clock.now)] = 8
    forecast = RecordingForecastService(clock, completed())
    forecast.provider = MagicMock(budget=budget)
    scheduler = build(cache, clock, forecast)
    clock.now = DAY.replace(hour=15, minute=18)
    report = run(scheduler)
    assert report["ran"] is False and report["skipped"] == "budget_spent" and forecast.calls == 0
    state = scheduler.state(TASK_FORECASTS)
    assert state.get("last_success_at") is None and state.get("last_run_at") is None
    assert next_due(scheduler) == EVENING, "the next slot, not six hours after the skip"


def test_a_failed_pass_keeps_its_backoff_and_is_not_a_refresh(cache, clock):
    forecast = RecordingForecastService(clock, completed())
    scheduler = build(cache, clock, forecast)
    run(scheduler)                                            # 12:12, fine
    forecast._report = {"provider": "stub", "error": "boom", "outcome": "failed"}
    clock.now = EVENING
    failed = run(scheduler)
    assert failed["ran"] is True and failed["ok"] is False
    state = scheduler.state(TASK_FORECASTS)
    assert state["consecutive_failures"] == 1 and state["backoff_seconds"] == INTERVAL
    assert datetime.fromisoformat(state["last_success_at"]) == NOON, "the failure is no refresh"
    reset = sync_scheduler._next_budget_reset(clock.now)
    assert next_due(scheduler) == min(clock.now + timedelta(seconds=INTERVAL), reset), "the backoff, clamped to the reset, as before"
    forecast._report = completed()
    clock.now = next_due(scheduler)
    assert run(scheduler)["ok"] is True
    assert next_due(scheduler) == MIDNIGHT, "back on the grid after the pass that succeeds"


def test_a_fetching_pass_is_not_followed_by_a_slot_minutes_away(clock, redis):
    """A catch-up at 12:05 that bought the day: 12:12 would only re-check what it just fetched, and
    the policy allows one re-check a day - so the next slot is 18:12."""
    h = Harness(clock, redis, keys=POLICY_KEYS)
    scheduler = scheduler_over(h, clock)
    clock.now = DAY.replace(hour=12, minute=5)
    run(scheduler)
    assert h.budget.used_today() == len(POLICY_KEYS)
    assert next_due(scheduler) == EVENING, "not 12:12"


def test_a_pass_that_spent_nothing_is_followed_by_the_slot_it_crossed(clock, redis):
    h = Harness(clock, redis, keys=POLICY_KEYS)
    scheduler = scheduler_over(h, clock)
    clock.now = DAY.replace(hour=11, minute=58)
    run(scheduler)                                            # before the hour: nothing bought
    assert h.budget.used_today() == 0
    assert next_due(scheduler) == NOON, "the slot fourteen minutes away is still the day's first eligible pass"


def test_a_provider_pause_still_floors_the_wait(cache, clock):
    until = DAY.replace(hour=23)
    forecast = RecordingForecastService(clock, {"provider": "stub", "error": "skipped (recent failure: 503)",
                                                 "paused": True, "paused_until": until.isoformat(),
                                                 "outcome": "deferred"})
    scheduler = build(cache, clock, forecast)
    run(scheduler)
    assert next_due(scheduler) >= until, "no retry under a pause, grid or no grid"


def test_a_concurrent_worker_changes_nothing(cache, clock, redis):
    scheduler, other = build(cache, clock), build(cache, clock)
    assert other._acquire_lock(TASK_FORECASTS)
    try:
        report = run(scheduler)
    finally:
        other._release_lock(TASK_FORECASTS)
    assert report["ran"] is False and report["skipped"] == "locked"
    assert scheduler.state(TASK_FORECASTS) == {}


# ------------------------------------------------------------------ recovery retries and the grid
def test_recovery_retries_keep_their_timing_and_the_grid_resumes_from_the_interruption(cache, clock):
    forecast = RecordingForecastService(clock, completed(), reports=[interrupted(["bundesliga"]), completed()])
    scheduler = build(cache, clock, forecast)
    first = run(scheduler)
    assert first["outcome"] == PASS_PARTIAL and first["recovery"]["attempts"] == 1
    retry_at = next_due(scheduler)
    assert retry_at == NOON + timedelta(seconds=FORECASTS_RECOVERY_RETRY_SECONDS), "five minutes, not a slot"
    clock.now = retry_at
    retry = run(scheduler)
    assert retry["ok"] is True and forecast.asked_with[-1].get("recovery") is True
    assert next_due(scheduler) == EVENING, "the grid, counted from the interruption, not from the retry"


def test_an_interruption_inside_a_late_pass_is_retried_and_the_grid_resumes(cache, clock):
    """The 10-27 incident on the grid: the 12:12 slot ran at 15:18, was interrupted at 15:18:33, retried."""
    forecast = RecordingForecastService(clock, completed(), reports=[interrupted(["premier_league"]), completed()])
    scheduler = build(cache, clock, forecast)
    clock.now = DAY.replace(hour=15, minute=18, second=33)
    run(scheduler)
    retry_at = next_due(scheduler)
    assert retry_at == clock.now + timedelta(seconds=FORECASTS_RECOVERY_RETRY_SECONDS)
    clock.now = DAY.replace(hour=15, minute=34, second=38)    # the host slept through the retry's due time
    assert run(scheduler)["ok"] is True
    assert next_due(scheduler) == EVENING, "18:12, not 21:34"


def test_a_slot_crossed_during_an_episode_is_run_once_the_episode_closes(cache, clock):
    forecast = RecordingForecastService(clock, completed(), reports=[interrupted(["serie_a"]), completed(), completed()])
    scheduler = build(cache, clock, forecast)
    clock.now = EVENING - timedelta(minutes=2)                # a late pass that began at 18:10
    run(scheduler)
    clock.now = next_due(scheduler)                           # the retry, 18:15
    run(scheduler)
    assert next_due(scheduler) == EVENING and scheduler.due(TASK_FORECASTS)[0] is True, "18:12 was crossed"
    assert run(scheduler)["ran"] is True
    assert next_due(scheduler) == MIDNIGHT
    assert forecast.calls == 3


# ------------------------------------------------------------------ fallback and other tasks
def test_without_an_anchor_the_interval_counts_from_completion(cache, clock, monkeypatch):
    monkeypatch.setattr(settings, "SYNC_FORECASTS_SLOT_ANCHOR_UTC", "")
    scheduler = build(cache, clock)
    clock.now = DAY.replace(hour=15, minute=18)
    run(scheduler)
    assert next_due(scheduler) == clock.now + timedelta(seconds=INTERVAL), "the previous behaviour, by choice"


def test_the_other_tasks_keep_their_intervals(cache, clock):
    grid_or_skip()
    scheduler = build(cache, clock)
    assert scheduler.slot_anchor(sync_scheduler.TASK_FIXTURES) is None
    assert scheduler._ordinary_due(sync_scheduler.TASK_FIXTURES, clock.now) == clock.now + timedelta(
        seconds=scheduler.interval(sync_scheduler.TASK_FIXTURES))
