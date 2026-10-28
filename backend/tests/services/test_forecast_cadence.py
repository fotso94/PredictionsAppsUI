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
failed pass keeps its backoff and is never a refresh. The cadence decides WHEN the policy is offered
a pass, never what it may buy - and the policy, new this round, re-checks no competition within
`RECHECK_MIN_GAP` (one hour) of the fetch it would re-check, measured from that request's own time
as the slot in Redis records it, per competition: a slot minutes after a late pass costs nothing, a
competition's re-check that is still owed is made at the first slot an hour or more after its fetch
(17:12 permits 18:12), and one competition's fresh fetch never holds up another's re-check.

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
from app.services.forecast_refresh_policy import OUTCOME_OLDER_RUN, OUTCOME_SAME_DAY_RUN
from app.services.forecast_service import PASS_COMPLETED, PASS_PARTIAL
from types import SimpleNamespace

from app.services.match_cache import MatchCache
from app.services.providers.budget import RequestBudget, budget_key
from app.services.sync_scheduler import FORECASTS_RECOVERY_RETRY_SECONDS, TASK_FORECASTS, SyncScheduler

try:
    from app.services.sync_scheduler import forecast_slot_after, parse_slot_anchor
except ImportError:  # the previous implementation: the decisive tests below fail there on the state, not here
    forecast_slot_after = parse_slot_anchor = None
from tests.services.test_forecast_recovery import LOCK, scheduler_over
from tests.services.test_forecast_refresh_policy import KEYS as POLICY_KEYS, Harness, todays_run, yesterdays_run
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


def test_a_pass_is_followed_by_the_slot_it_crossed_whatever_it_spent(clock, redis):
    h = Harness(clock, redis, keys=POLICY_KEYS)
    scheduler = scheduler_over(h, clock)
    clock.now = DAY.replace(hour=5)
    run(scheduler)                                            # a pass at 05:00, before the hour: next 06:12
    assert h.budget.used_today() == 0 and next_due(scheduler) == DAY.replace(hour=6, minute=12)
    clock.now = DAY.replace(hour=12, minute=5)                # slept through 06:12; the catch-up buys the day
    assert run(scheduler)["ran"] is True
    assert h.budget.used_today() == len(POLICY_KEYS) and next_due(scheduler) == NOON, "12:12 still comes"


# ------------------------------------------------------------------ the re-check gap: request timing, per competition
PUBLISHED_AT_13 = lambda now: todays_run(now) if now.hour >= 13 else yesterdays_run(now)  # noqa: E731
#: A fixture sync that answers from the provider, so dormancy can be judged from the harness's counts.
ANSWERED_CALENDAR = lambda key: SimpleNamespace(source="provider", stale=False, errors=[])  # noqa: E731


def test_a_re_check_waits_an_hour_after_the_fetch_it_re_checks(clock, redis):
    """The run is published at 13:00 today. A catch-up at 12:05 is served yesterday's run (older-run);
    the 12:12 slot seven minutes later re-checks nothing; 18:12 re-checks and gets today's."""
    h = Harness(clock, redis, keys=POLICY_KEYS, run_at=PUBLISHED_AT_13)
    scheduler = scheduler_over(h, clock)
    clock.now = DAY.replace(hour=12, minute=5)
    run(scheduler)
    policy = h.new_service().policy
    assert all(policy.slot(k)["outcome"] == OUTCOME_OLDER_RUN for k in POLICY_KEYS) and h.budget.used_today() == 3
    clock.now = NOON
    soon = run(scheduler)
    assert soon["ok"] is True and h.budget.used_today() == 3, "nothing re-checked within the hour"
    assert all("waits until at least 60 min after that fetch" in why for why in soon["result"]["plan"]["ineligible"].values())
    assert all("recheck" not in h.new_service().policy.slot(k) for k in POLICY_KEYS), "the day's re-check is still owed"
    clock.now = EVENING
    later = run(scheduler)
    assert sorted(later["result"]["rechecked"]) == sorted(POLICY_KEYS) and h.budget.used_today() == 6
    assert all(h.new_service().policy.slot(k)["recheck"]["outcome"] == OUTCOME_SAME_DAY_RUN for k in POLICY_KEYS)


def test_the_gap_is_at_least_one_hour_to_the_minute(clock, redis):
    """A fetch at 17:12 permits the 18:12 re-check; a fetch at 17:13 does not."""
    for minute, permitted in ((12, True), (13, False)):
        h = Harness(clock, redis, keys=["premier_league"], run_at=yesterdays_run)   # always an older run
        scheduler = scheduler_over(h, clock)
        clock.now = DAY.replace(hour=17, minute=minute)
        run(scheduler)                                        # older-run, fetched at 17:12 or 17:13
        clock.now = EVENING
        report = run(scheduler)
        assert (report["result"].get("rechecked") == ["premier_league"]) is permitted, minute
        redis.store.clear()


def test_one_competitions_fresh_fetch_does_not_hold_up_anothers_re_check(clock, redis):
    """Serie A older-run at 12:12; La Liga fetched at 17:40 (a recovery retry's turn, say) and served
    today's run. At 18:12 Serie A's re-check is made - an hour after ITS fetch - and La Liga, fetched
    thirty minutes earlier, is simply not due anything: the gap is per competition."""
    h = Harness(clock, redis, keys=["serie_a", "la_liga"], run_at=PUBLISHED_AT_13, calendar=ANSWERED_CALENDAR,
                kickoffs={"serie_a": EVENING + timedelta(hours=2), "la_liga": None})
    h.counts["la_liga"] = 0                                   # no La Liga fixture in the window at noon: dormant
    scheduler = scheduler_over(h, clock)
    clock.now = NOON
    run(scheduler)
    assert h.calls() == ["serie_a"] and h.new_service().policy.slot("serie_a")["outcome"] == OUTCOME_OLDER_RUN
    at_1740 = DAY.replace(hour=17, minute=40)
    h.new_service().policy.record_fetch("la_liga", fetched_at=at_1740, model_run_at=todays_run(at_1740), forecasts=1)
    h.counts["la_liga"], h.kickoffs["la_liga"] = 1, EVENING + timedelta(hours=3)
    clock.now = EVENING
    report = run(scheduler)
    assert report["result"]["rechecked"] == ["serie_a"], "Serie A's re-check is not held up by La Liga's fetch"
    assert "la_liga" in report["result"]["plan"]["ineligible"] and h.calls() == ["serie_a", "serie_a"]


def test_case_a_a_lease_held_retry_and_an_empty_recovery_keep_the_grid_and_the_re_check(clock, redis):
    """12:00 partial pass spends one (Serie A, older-run); 12:05 retry finds the lease held and spends
    zero; 12:15 the recovery completes spending zero because the other worker bought Bundesliga.
    The grid's next slot, 12:12, is due at once: it re-checks nothing (Serie A was fetched fifteen
    minutes ago) and spends nothing; 18:12 re-checks Serie A."""
    from tests.services.test_forecast_recovery import stepping_the_server_clock_before
    redis_clock = clock                                        # one clock: the lease is lost by an explicit lapse below
    h = Harness(clock, redis, keys=["serie_a", "bundesliga"], run_at=PUBLISHED_AT_13,
                kickoffs={"serie_a": EVENING + timedelta(hours=1), "bundesliga": EVENING + timedelta(hours=2)})
    noon = DAY.replace(hour=12, minute=0)
    clock.now = noon

    once = {}

    def lose_the_lease_before_bundesliga(svc):
        record = svc.policy.record_calendar

        def gone(evidence):
            if evidence.key == "bundesliga" and not once.get("done"):
                once["done"] = True
                redis.delete(LOCK)                             # the lease expired under us, this once
            return record(evidence)

        svc.policy.record_calendar = gone
        return svc

    scheduler = scheduler_over(h, clock, lose_the_lease_before_bundesliga)
    first = run(scheduler)
    assert first["outcome"] == PASS_PARTIAL and h.calls() == ["serie_a"]
    assert next_due(scheduler) == noon + timedelta(minutes=5)
    clock.now = noon + timedelta(minutes=5)
    redis.set(LOCK, "another-worker", ex=300)                  # another worker holds the lease...
    held = run(scheduler)
    assert held["outcome"] == "deferred" and held["result"].get("lease_held") is True and h.calls() == ["serie_a"]
    redis.delete(LOCK)
    other = h.new_service().ensure_synced()                    # ...and does the outstanding work outside the scheduler
    assert other.get("outcome") == PASS_COMPLETED and h.calls() == ["serie_a", "bundesliga"]
    retry_at = next_due(scheduler)
    assert retry_at == noon + timedelta(minutes=15), "the second retry, ten minutes on"
    clock.now = retry_at
    done = run(scheduler)
    assert done["ok"] is True and h.calls() == ["serie_a", "bundesliga"], "nothing left to buy: the other worker did it"
    assert next_due(scheduler) == NOON and scheduler.due(TASK_FORECASTS)[0] is True, "the grid: 12:12, crossed during the episode"
    soon = run(scheduler)
    assert soon["ok"] is True and h.calls() == ["serie_a", "bundesliga"], "no re-check within an hour of the 12:00 fetch"
    assert "serie_a" in soon["result"]["plan"]["ineligible"] and "recheck" not in h.new_service().policy.slot("serie_a")
    assert next_due(scheduler) == EVENING
    clock.now = EVENING
    evening = run(scheduler)
    slot = h.new_service().policy.slot("bundesliga")
    assert "bundesliga" not in evening["result"]["plan"]["ineligible"], (
        evening["result"]["plan"]["ineligible"].get("bundesliga"), slot.get("outcome"), slot.get("recheck"), slot.get("fetched_at"))
    assert evening["result"]["rechecked"] == ["serie_a", "bundesliga"], "both re-checks, still owed, made at 18:12"


def test_case_b_a_sleep_after_an_interruption_keeps_the_evening_slot(clock, redis):
    """12:12 partial pass spends one (Serie A). The host sleeps through the retries. 18:05 the recovery
    runs and spends zero (Bundesliga has no fixture in the window). The grid's next slot is 18:12 -
    not midnight - and Serie A's re-check, owed since 12:12, is made there."""
    h = Harness(clock, redis, keys=["serie_a", "bundesliga"], run_at=PUBLISHED_AT_13, calendar=ANSWERED_CALENDAR,
                kickoffs={"serie_a": EVENING + timedelta(hours=1), "bundesliga": EVENING + timedelta(hours=2)})

    once = {}

    def lose_the_lease_before_bundesliga(svc):
        record = svc.policy.record_calendar

        def gone(evidence):
            if evidence.key == "bundesliga" and not once.get("done"):
                once["done"] = True
                redis.delete(LOCK)
            return record(evidence)

        svc.policy.record_calendar = gone
        return svc

    scheduler = scheduler_over(h, clock, lose_the_lease_before_bundesliga)
    first = run(scheduler)
    assert first["outcome"] == PASS_PARTIAL and h.calls() == ["serie_a"] and next_due(scheduler) == NOON + timedelta(minutes=5)
    clock.now = DAY.replace(hour=18, minute=5)                 # the host slept through 12:17
    h.counts["bundesliga"] = 0                                 # nothing to buy for the owed turn: no fixture in the window
    h.kickoffs["bundesliga"] = None
    recovered = run(scheduler_over(h, clock))
    assert recovered["ok"] is True and h.calls() == ["serie_a"], ("the recovery spent nothing", recovered["result"])
    assert "serie_a" in recovered["result"].get("recheck_skipped", {}), "the owed re-check is left to the ordinary pass"
    assert next_due(scheduler) == EVENING, "18:12, not midnight: the grid counts from the interruption"
    clock.now = EVENING
    report = run(scheduler_over(h, clock))
    assert report["result"]["rechecked"] == ["serie_a"] and h.calls() == ["serie_a", "serie_a"]


def test_a_delayed_wake_before_the_hour_then_the_grid(clock, redis):
    h = Harness(clock, redis, keys=POLICY_KEYS, run_at=PUBLISHED_AT_13)
    scheduler = scheduler_over(h, clock)
    clock.now = DAY.replace(hour=9, minute=40)                 # woke late; the 06:12 slot was due
    run(scheduler)
    assert h.budget.used_today() == 0 and next_due(scheduler) == NOON
    clock.now = NOON
    run(scheduler)
    assert h.budget.used_today() == 3 and next_due(scheduler) == EVENING


def test_an_exhausted_allowance_leaves_the_re_check_owed_for_the_next_slot(clock, redis):
    h = Harness(clock, redis, keys=["serie_a"], limit=1, run_at=PUBLISHED_AT_13)
    scheduler = scheduler_over(h, clock)
    clock.now = NOON
    run(scheduler)                                             # the one request of the day: older-run
    assert h.budget.used_today() == 1 and h.new_service().policy.slot("serie_a")["outcome"] == OUTCOME_OLDER_RUN
    clock.now = EVENING
    report = run(scheduler)
    assert report["ran"] is False and report["skipped"] == "budget_spent"
    assert next_due(scheduler) == MIDNIGHT and "recheck" not in h.new_service().policy.slot("serie_a")


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
