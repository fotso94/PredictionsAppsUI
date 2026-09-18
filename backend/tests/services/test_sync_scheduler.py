"""
What the background refresh is allowed to cost.

The scheduler exists to keep stored data fresh, but the failure it is actually designed against is
a runaway loop on a trial plan. Every test here is about restraint: a task that is not due does not
run, a spent allowance stops a task without inflating the refused counter, a failure backs off
instead of retrying, two workers cannot both pay for the same task, live scores are not polled
outside a live window, and restarting the backend does not buy a fresh pass.

No database and no network: a fake clock, an in-memory Redis stand-in and stub providers that
record every call they receive. If a stub is called, a real deployment would have spent a request.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.predictions import MatchStatus
from app.services import sync_scheduler
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService
from app.services.providers.base import (
    MatchDataProvider, ProviderCompetition, ProviderFixture, ProviderTeam, ProviderUnavailableError,
)
from app.services.providers.budget import RequestBudget, budget_key, refused_key
from app.services.sync_scheduler import (
    TASK_FIXTURES, TASK_FORECASTS, TASK_LIVE, TASK_RESULTS, SyncScheduler,
)
from tests.providers.support import FakeRedis

NOW = datetime(2026, 9, 18, 18, 0, tzinfo=timezone.utc)
KEYS = ["premier_league", "la_liga"]


# --------------------------------------------------------------------- doubles
class LockingFakeRedis(FakeRedis):
    """FakeRedis plus SET NX EX (the task locks) and TTLs that actually expire against the fake clock.

    Expiry matters here: the provider caches and the post-failure cool-downs are a large part of what
    keeps the spend down, and a stand-in that never forgets anything would make the scheduler look
    thriftier than it is.
    """

    def __init__(self, clock=None):
        super().__init__()
        self.clock = clock
        self.expires = {}

    def _expire_due(self) -> None:
        if self.clock is None:
            return
        now = self.clock()
        for key in [k for k, at in self.expires.items() if at <= now]:
            self.store.pop(key, None)
            self.ttls.pop(key, None)
            self.expires.pop(key, None)

    def _schedule(self, key, ttl) -> None:
        if ttl is None:
            return
        self.ttls[key] = ttl
        if self.clock is not None:
            self.expires[key] = self.clock() + timedelta(seconds=int(ttl))

    def get(self, key):
        self._expire_due()
        return super().get(key)

    def set(self, key, value, nx=False, ex=None, **kwargs):
        self._expire_due()
        if nx and key in self.store:
            return None
        self.store[key] = value
        self._schedule(key, ex)
        return True

    def setex(self, key, ttl, value):
        self._expire_due()
        self.store[key] = value
        self._schedule(key, ttl)

    def expire(self, key, ttl):
        self._schedule(key, ttl)

    def scan_iter(self, match=None, count=None):
        self._expire_due()
        prefix = (match or "*").rstrip("*")
        return [k for k in list(self.store) if k.startswith(prefix)]


class Clock:
    """Fake clock; `tick` moves it forward the way waiting for the next interval would."""

    def __init__(self, start: datetime = NOW):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: int) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _fixture(kickoff: datetime, key: str = "premier_league") -> ProviderFixture:
    return ProviderFixture(
        provider="stub", external_id=f"f-{kickoff.isoformat()}",
        competition=ProviderCompetition(provider="stub", external_id="1", name="Premier League", key=key),
        home=ProviderTeam(provider="stub", external_id="h", name="Home"),
        away=ProviderTeam(provider="stub", external_id="a", name="Away"),
        kickoff_utc=kickoff,
    )


class StubDataProvider(MatchDataProvider):
    """Records every call. A recorded call is a request a real deployment would have paid for."""

    name = "stub"
    integration_status = "test"

    def __init__(self, budget: Optional[RequestBudget] = None, fail: bool = False):
        self.calls: List[str] = []
        self.budget = budget
        self.fail = fail

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def _maybe_fail(self) -> None:
        if self.fail:
            raise ProviderUnavailableError("upstream is down", provider=self.name)

    def get_fixtures(self, day: date, keys) -> List[ProviderFixture]:
        self.calls.append(f"fixtures:{day.isoformat()}")
        self._maybe_fail()
        return [_fixture(NOW + timedelta(days=1))]

    def get_live(self, keys) -> List[ProviderFixture]:
        self.calls.append("live")
        self._maybe_fail()
        return []

    def get_results(self, date_from: date, date_to: date, keys) -> List[ProviderFixture]:
        self.calls.append(f"results:{date_from.isoformat()}")
        self._maybe_fail()
        return []

    def get_standings(self, key):
        return []


class StubForecastService:
    """Stands in for ForecastService: the scheduler must delegate, not reimplement the rotation."""

    def __init__(self, report: Optional[Dict[str, Any]] = None, provider: Any = None):
        self.calls = 0
        self._report = report if report is not None else {"provider": "stub", "competitions": {}}
        self.provider = provider

    def ensure_synced(self, *args, **kwargs) -> Dict[str, Any]:
        self.calls += 1
        return dict(self._report)


class FakeMatch:
    def __init__(self, kickoff: datetime, status=MatchStatus.SCHEDULED):
        self.match_date = kickoff.replace(tzinfo=None)
        self.status = status
        self.id = f"m-{kickoff.isoformat()}"


# --------------------------------------------------------------------- harness
@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def redis_client(clock):
    return LockingFakeRedis(clock=clock)


@pytest.fixture
def cache(redis_client):
    return MatchCache(client=redis_client)


def build_match_service(cache, provider, clock, matches: Optional[List[FakeMatch]] = None) -> MatchDataService:
    """Real MatchDataService (so the live window and results gating are the shipped ones), stub provider."""
    db = MagicMock()
    service = MatchDataService(db, providers=[provider], cache=cache, now=clock(), keys=list(KEYS))
    service.registry = MagicMock()
    service.registry.ensure_canonical_league.return_value = MagicMock(id="league-1")
    service.registry.matches_for_day.return_value = list(matches or [])
    service.registry.upsert_fixture.side_effect = lambda fixture: MagicMock()
    return service


def build(cache, clock, provider=None, forecast=None, matches=None, tasks=None):
    provider = provider if provider is not None else StubDataProvider()
    forecast = forecast if forecast is not None else StubForecastService()
    match_service = build_match_service(cache, provider, clock, matches)

    def match_factory(_db):
        # The real scheduler builds a fresh service each pass, so its clock advances. Keep one
        # instance (tests assert against it) but move its clock the way a new pass would.
        match_service._now = clock()
        return match_service

    scheduler = SyncScheduler(
        session_factory=lambda: MagicMock(),
        cache=cache,
        now=clock,
        match_service_factory=match_factory,
        forecast_service_factory=lambda db: forecast,
        tasks=tasks if tasks is not None else [TASK_FIXTURES, TASK_LIVE, TASK_RESULTS, TASK_FORECASTS],
        close_sessions=False,
    )
    return scheduler, provider, forecast, match_service


@pytest.fixture(autouse=True)
def _small_fixture_window(monkeypatch):
    """Keep the day loops short so a test reads as a test, not as a week of calendar."""
    monkeypatch.setattr(settings, "SYNC_FIXTURES_DAYS_AHEAD", 1)
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 0)


# --------------------------------------------------------------------- cadence
def test_a_task_that_has_never_run_is_due(cache, clock):
    scheduler, _, _, _ = build(cache, clock)
    assert scheduler.due(TASK_FIXTURES) == (True, None)
    assert scheduler.status()["tasks"][TASK_FIXTURES]["never_run"] is True


def test_a_task_is_not_due_again_until_its_interval_has_passed(cache, clock):
    scheduler, provider, _, _ = build(cache, clock)
    first = scheduler.run_once(only=[TASK_FIXTURES])
    assert first["tasks"][TASK_FIXTURES]["ran"] is True
    assert provider.calls, "the first pass must actually fetch"
    calls_after_first = len(provider.calls)

    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS - 60)
    second = scheduler.run_once(only=[TASK_FIXTURES])
    assert second["tasks"][TASK_FIXTURES] == {
        "ran": False, "skipped": "not_due",
        "reason": second["tasks"][TASK_FIXTURES]["reason"],
    }
    assert len(provider.calls) == calls_after_first, "a task that is not due must not call the provider"

    clock.tick(120)
    third = scheduler.run_once(only=[TASK_FIXTURES])
    assert third["tasks"][TASK_FIXTURES]["ran"] is True
    assert len(provider.calls) > calls_after_first


def test_a_tick_with_nothing_due_opens_no_database_connection(cache, clock):
    """The loop wakes every minute. Deciding due-ness from Redis keeps the idle tick free."""
    sessions = []
    scheduler, _, _, _ = build(cache, clock)
    scheduler._session_factory = lambda: sessions.append(MagicMock()) or sessions[-1]

    scheduler.run_once(only=[TASK_FIXTURES])
    assert len(sessions) == 1

    clock.tick(60)
    scheduler.run_once(only=[TASK_FIXTURES])
    assert len(sessions) == 1, "an idle tick must not open a connection"


def test_force_runs_a_task_that_is_not_due(cache, clock):
    scheduler, provider, _, _ = build(cache, clock)
    scheduler.run_once(only=[TASK_FIXTURES])
    calls = len(provider.calls)

    clock.tick(settings.MATCH_CACHE_TTL_FIXTURES + 60)  # past the provider cache, still inside the interval
    assert scheduler.due(TASK_FIXTURES)[0] is False
    scheduler.run_once(only=[TASK_FIXTURES], force=True)

    assert len(provider.calls) > calls


# --------------------------------------------------------------------- restart
def test_restarting_the_backend_does_not_force_an_immediate_sync(cache, clock):
    """The due-times live in Redis, so a new process inherits them instead of starting from zero."""
    scheduler, provider, _, _ = build(cache, clock)
    scheduler.run_once(only=[TASK_FIXTURES])
    calls_before_restart = len(provider.calls)

    clock.tick(30)  # a developer restarts the backend half a minute later
    restarted, restarted_provider, _, _ = build(cache, clock, provider=provider)
    assert restarted.due(TASK_FIXTURES)[0] is False
    report = restarted.run_once(only=[TASK_FIXTURES])

    assert report["tasks"][TASK_FIXTURES]["skipped"] == "not_due"
    assert len(restarted_provider.calls) == calls_before_restart, "a restart must not buy a fresh pass"


def test_the_loop_waits_before_its_first_tick(cache, clock):
    """Second line of defence for the restart case: nothing runs during the startup grace period."""
    import inspect
    source = inspect.getsource(SyncScheduler.run_forever)
    assert "SYNC_SCHEDULER_STARTUP_DELAY_SECONDS" in source
    assert source.index("asyncio.sleep(delay)") < source.index("run_in_executor")
    assert settings.SYNC_SCHEDULER_STARTUP_DELAY_SECONDS > 0


# --------------------------------------------------------------------- budget ceiling
def _spend_budget(redis_client, provider_name: str, amount: int) -> None:
    redis_client.store[budget_key(provider_name)] = amount


def test_a_spent_budget_stops_the_task_without_calling_the_provider(cache, clock, redis_client):
    budget = RequestBudget("stub", daily_limit=10, client=redis_client)
    _spend_budget(redis_client, "stub", 10)
    scheduler, provider, _, _ = build(cache, clock, provider=StubDataProvider(budget=budget))

    report = scheduler.run_once(only=[TASK_FIXTURES])

    assert report["tasks"][TASK_FIXTURES]["skipped"] == "budget_spent"
    assert "spent" in report["tasks"][TASK_FIXTURES]["reason"]
    assert provider.calls == []


def test_a_spent_budget_does_not_generate_refused_reservations(cache, clock, redis_client):
    """The refused counter measures requests the app tried to send. A skip never tried."""
    budget = RequestBudget("stub", daily_limit=10, client=redis_client)
    _spend_budget(redis_client, "stub", 10)
    scheduler, _, _, _ = build(cache, clock, provider=StubDataProvider(budget=budget))

    for _ in range(3):
        scheduler.run_once(only=[TASK_FIXTURES], force=True)

    assert redis_client.store.get(refused_key("stub")) is None
    assert budget.refused_today() == 0
    assert budget.used_today() == 10, "a skipped task must not move the usage counter either"


def test_a_budget_skip_resumes_at_the_daily_reset_not_a_full_interval_later(cache, clock, redis_client):
    """Blocked at 22:00 with a 6 h interval, the next attempt is just after the UTC reset, not 04:00."""
    clock.now = NOW.replace(hour=22, minute=0)
    budget = RequestBudget("stub", daily_limit=10, client=redis_client)
    _spend_budget(redis_client, "stub", 10)
    scheduler, _, _, _ = build(cache, clock, provider=StubDataProvider(budget=budget))

    scheduler.run_once(only=[TASK_FIXTURES])

    next_due = datetime.fromisoformat(scheduler.state(TASK_FIXTURES)["next_due_at"])
    assert next_due.date() == (clock.now + timedelta(days=1)).date()
    assert next_due.hour == 0, "the allowance comes back at UTC midnight; resume then"


def test_the_reserve_keeps_requests_back_for_page_loads(cache, clock, redis_client, monkeypatch):
    monkeypatch.setattr(settings, "SYNC_SCHEDULER_BUDGET_RESERVE", 50)
    budget = RequestBudget("stub", daily_limit=1200, client=redis_client)
    _spend_budget(redis_client, "stub", 1160)  # 40 left, below the 50 reserve
    scheduler, provider, _, _ = build(cache, clock, provider=StubDataProvider(budget=budget))

    report = scheduler.run_once(only=[TASK_FIXTURES])

    assert report["tasks"][TASK_FIXTURES]["skipped"] == "budget_spent"
    assert provider.calls == []


def test_the_reserve_never_freezes_out_a_tiny_allowance(cache, clock, redis_client, monkeypatch):
    """A 10/day plan with a flat 50-request reserve would never sync at all. Cap it at a tenth."""
    monkeypatch.setattr(settings, "SYNC_SCHEDULER_BUDGET_RESERVE", 50)
    budget = RequestBudget("stub", daily_limit=10, client=redis_client)
    _spend_budget(redis_client, "stub", 2)
    scheduler, provider, _, _ = build(cache, clock, provider=StubDataProvider(budget=budget))

    report = scheduler.run_once(only=[TASK_FIXTURES])

    assert report["tasks"][TASK_FIXTURES]["ran"] is True
    assert provider.calls


def test_a_fallback_with_allowance_left_keeps_the_task_running(cache, clock, redis_client):
    """The ceiling stops a task only when every provider it could reach is out, not just the first."""
    spent = RequestBudget("stub", daily_limit=10, client=redis_client)
    _spend_budget(redis_client, "stub", 10)
    fallback_budget = RequestBudget("stub-fallback", daily_limit=1000, client=redis_client)
    primary, fallback = StubDataProvider(budget=spent), StubDataProvider(budget=fallback_budget)
    fallback.name = "stub-fallback"
    match_service = build_match_service(cache, primary, clock, matches=[FakeMatch(NOW)])
    match_service._providers = [primary, fallback]
    scheduler = SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                              match_service_factory=lambda db: match_service,
                              forecast_service_factory=lambda db: StubForecastService(),
                              tasks=[TASK_LIVE], close_sessions=False)

    report = scheduler.run_once(only=[TASK_LIVE])

    assert report["tasks"][TASK_LIVE]["ran"] is True


def test_a_spent_forecast_allowance_stops_the_forecast_task(cache, clock, redis_client):
    budget = RequestBudget("stub-forecast", daily_limit=8, client=redis_client)
    _spend_budget(redis_client, "stub-forecast", 8)
    forecast = StubForecastService(provider=MagicMock(budget=budget))
    scheduler, _, _, _ = build(cache, clock, forecast=forecast)

    report = scheduler.run_once(only=[TASK_FORECASTS])

    assert report["tasks"][TASK_FORECASTS]["skipped"] == "budget_spent"
    assert forecast.calls == 0
    assert budget.refused_today() == 0


# --------------------------------------------------------------------- backoff
def test_a_failing_task_backs_off_instead_of_retrying_on_the_next_tick(cache, clock):
    matches = [FakeMatch(NOW)]  # inside the live window, so the task really tries to poll
    scheduler, provider, _, _ = build(cache, clock, provider=StubDataProvider(fail=True), matches=matches)

    report = scheduler.run_once(only=[TASK_LIVE])
    assert report["tasks"][TASK_LIVE]["ok"] is False
    state = scheduler.state(TASK_LIVE)
    assert state["consecutive_failures"] == 1
    assert state["backoff_seconds"] >= sync_scheduler.BACKOFF_MIN_SECONDS
    assert state["backoff_seconds"] > scheduler.interval(TASK_LIVE), "backoff must exceed the normal interval"

    clock.tick(scheduler.interval(TASK_LIVE) + 1)  # the next normal tick
    assert scheduler.due(TASK_LIVE)[0] is False
    calls = len(provider.calls)
    scheduler.run_once(only=[TASK_LIVE])
    assert len(provider.calls) == calls, "a failing task must not retry immediately"


def test_repeated_failures_back_off_further_and_are_capped(cache, clock):
    matches = [FakeMatch(NOW)]
    scheduler, _, _, _ = build(cache, clock, provider=StubDataProvider(fail=True), matches=matches)

    backoffs = []
    for _ in range(3):
        scheduler.run_once(only=[TASK_LIVE], force=True)
        backoffs.append(scheduler.state(TASK_LIVE)["backoff_seconds"])

    assert backoffs == sorted(backoffs) and backoffs[0] < backoffs[-1]
    assert all(b <= sync_scheduler.BACKOFF_MAX_SECONDS for b in backoffs)
    assert scheduler.state(TASK_LIVE)["consecutive_failures"] == 3


def test_a_success_clears_the_backoff(cache, clock):
    matches = [FakeMatch(NOW)]
    provider = StubDataProvider(fail=True)
    scheduler, _, _, _ = build(cache, clock, provider=provider, matches=matches)
    scheduler.run_once(only=[TASK_LIVE], force=True)
    assert scheduler.state(TASK_LIVE)["consecutive_failures"] == 1

    provider.fail = False
    clock.tick(300)  # past the provider's own post-failure cool-down and the 60 s live cache
    scheduler.run_once(only=[TASK_LIVE], force=True)

    state = scheduler.state(TASK_LIVE)
    assert state["consecutive_failures"] == 0
    assert state["last_error"] is None
    assert state["backoff_seconds"] is None


def test_an_unexpected_exception_is_recorded_and_does_not_escape(cache, clock):
    scheduler, _, _, match_service = build(cache, clock)
    match_service.sync_day = MagicMock(side_effect=RuntimeError("registry exploded"))

    report = scheduler.run_once(only=[TASK_FIXTURES])

    assert report["tasks"][TASK_FIXTURES] == {
        "ran": True, "ok": False, "error": "registry exploded",
        "next_due_at": report["tasks"][TASK_FIXTURES]["next_due_at"],
        "consecutive_failures": 1,
    }
    assert scheduler.state(TASK_FIXTURES)["last_error"] == "registry exploded"


def test_one_failing_task_does_not_stop_the_others(cache, clock):
    matches = [FakeMatch(NOW)]
    scheduler, _, forecast, match_service = build(cache, clock, matches=matches)
    match_service.sync_day = MagicMock(side_effect=RuntimeError("boom"))

    report = scheduler.run_once()

    assert report["tasks"][TASK_FIXTURES]["ok"] is False
    assert report["tasks"][TASK_FORECASTS]["ok"] is True
    assert forecast.calls == 1


# --------------------------------------------------------------------- concurrency
def test_two_concurrent_runs_do_not_both_call_the_provider(cache, clock):
    """The lock is in Redis, so it also covers scripts/sync_once.py run against a live backend."""
    matches = [FakeMatch(NOW)]
    provider = StubDataProvider()
    match_service = build_match_service(cache, provider, clock, matches)

    def make():
        return SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                             match_service_factory=lambda db: match_service,
                             forecast_service_factory=lambda db: StubForecastService(),
                             tasks=[TASK_LIVE], close_sessions=False)

    worker_a, worker_b = make(), make()
    assert worker_a._acquire_lock(TASK_LIVE) is True  # worker A is mid-pass

    report = worker_b.run_once(only=[TASK_LIVE])

    assert report["tasks"][TASK_LIVE]["skipped"] == "locked"
    assert provider.calls == []

    worker_a._release_lock(TASK_LIVE)
    worker_b.run_once(only=[TASK_LIVE])
    assert provider.calls == ["live"]


def test_a_lock_is_released_even_when_the_task_fails(cache, clock):
    matches = [FakeMatch(NOW)]
    scheduler, _, _, match_service = build(cache, clock, matches=matches)
    match_service._sync_live = MagicMock(side_effect=RuntimeError("boom"))

    scheduler.run_once(only=[TASK_LIVE])

    assert scheduler._acquire_lock(TASK_LIVE) is True, "the lock must not survive a failed task"


# --------------------------------------------------------------------- live window
def test_the_live_task_does_nothing_outside_a_live_window(cache, clock):
    tomorrow = [FakeMatch(NOW + timedelta(days=1))]
    scheduler, provider, _, _ = build(cache, clock, matches=tomorrow)

    report = scheduler.run_once(only=[TASK_LIVE])

    assert report["tasks"][TASK_LIVE]["ok"] is True
    assert report["tasks"][TASK_LIVE]["result"]["live_window_open"] is False
    assert provider.calls == [], "polling live scores with nothing in play is pure waste"


def test_the_live_task_polls_inside_a_live_window(cache, clock):
    kicked_off = [FakeMatch(NOW - timedelta(minutes=20))]
    scheduler, provider, _, _ = build(cache, clock, matches=kicked_off)

    report = scheduler.run_once(only=[TASK_LIVE])

    assert report["tasks"][TASK_LIVE]["result"]["live_window_open"] is True
    assert provider.calls == ["live"]


def test_a_finished_match_does_not_hold_the_live_window_open(cache, clock):
    finished = [FakeMatch(NOW - timedelta(minutes=20), status=MatchStatus.FINISHED)]
    scheduler, provider, _, _ = build(cache, clock, matches=finished)

    scheduler.run_once(only=[TASK_LIVE])

    assert provider.calls == []


# --------------------------------------------------------------------- results
def test_results_are_not_polled_for_a_day_with_nothing_left_to_settle(cache, clock):
    upcoming = [FakeMatch(NOW + timedelta(hours=3))]
    scheduler, provider, _, _ = build(cache, clock, matches=upcoming)

    report = scheduler.run_once(only=[TASK_RESULTS])

    assert report["tasks"][TASK_RESULTS]["result"]["polled"] is False
    assert provider.calls == []


def test_results_are_polled_once_a_match_is_overdue(cache, clock):
    overdue = [FakeMatch(NOW - timedelta(hours=4))]
    scheduler, provider, _, _ = build(cache, clock, matches=overdue)

    report = scheduler.run_once(only=[TASK_RESULTS])

    assert report["tasks"][TASK_RESULTS]["result"]["polled"] is True
    assert provider.calls == [f"results:{NOW.date().isoformat()}"]


# --------------------------------------------------------------------- forecasts
def test_the_forecast_task_delegates_to_the_forecast_service(cache, clock):
    """Rotation, the per-competition interval and the sync lock stay in ForecastService."""
    forecast = StubForecastService(report={"provider": "stub", "competitions": {"premier_league": {}}})
    scheduler, _, _, _ = build(cache, clock, forecast=forecast)

    report = scheduler.run_once(only=[TASK_FORECASTS])

    assert forecast.calls == 1
    assert report["tasks"][TASK_FORECASTS]["ok"] is True
    assert report["tasks"][TASK_FORECASTS]["result"]["competitions"] == {"premier_league": {}}


def test_a_paused_forecast_provider_is_a_failure_and_backs_off(cache, clock):
    forecast = StubForecastService(report={"provider": "stub", "error": "skipped (recent failure: 401)"})
    scheduler, _, _, _ = build(cache, clock, forecast=forecast)

    report = scheduler.run_once(only=[TASK_FORECASTS])

    assert report["tasks"][TASK_FORECASTS]["ok"] is False
    assert scheduler.state(TASK_FORECASTS)["backoff_seconds"] >= sync_scheduler.BACKOFF_MIN_SECONDS


# --------------------------------------------------------------------- task selection
def test_disabled_tasks_are_not_run(cache, clock):
    scheduler, provider, forecast, _ = build(cache, clock, tasks=[TASK_FIXTURES])

    report = scheduler.run_once()

    assert list(report["tasks"]) == [TASK_FIXTURES]
    assert forecast.calls == 0


def test_an_unknown_task_name_is_rejected(cache, clock):
    scheduler, _, _, _ = build(cache, clock)
    with pytest.raises(ValueError, match="Unknown sync task"):
        scheduler.run_once(only=["standings"])


def test_an_empty_task_list_runs_nothing(cache, clock):
    scheduler, provider, forecast, _ = build(cache, clock, tasks=[])

    report = scheduler.run_once()

    assert report["tasks"] == {}
    assert provider.calls == [] and forecast.calls == 0


# --------------------------------------------------------------------- dry run
def test_a_dry_run_estimates_the_cost_without_calling_anything(cache, clock):
    kicked_off = [FakeMatch(NOW - timedelta(minutes=20))]
    scheduler, provider, forecast, _ = build(cache, clock, matches=kicked_off)

    report = scheduler.estimate()

    assert provider.calls == [] and forecast.calls == 0, "a dry run must make no provider request"
    assert report["tasks"][TASK_FIXTURES]["estimated_requests"] == len(KEYS) * settings.SYNC_FIXTURES_DAYS_AHEAD
    assert report["tasks"][TASK_LIVE]["estimated_requests"] == 1
    assert report["total_requests"] >= 1


def test_a_dry_run_costs_nothing_for_a_task_with_no_work(cache, clock):
    tomorrow = [FakeMatch(NOW + timedelta(days=1))]
    scheduler, _, _, _ = build(cache, clock, matches=tomorrow)

    report = scheduler.estimate(only=[TASK_LIVE, TASK_RESULTS])

    assert report["tasks"][TASK_LIVE]["estimated_requests"] == 0
    assert report["tasks"][TASK_RESULTS]["estimated_requests"] == 0
    assert report["total_requests"] == 0


def test_a_dry_run_reports_a_blocked_task_as_not_running(cache, clock, redis_client):
    budget = RequestBudget("stub", daily_limit=10, client=redis_client)
    _spend_budget(redis_client, "stub", 10)
    scheduler, _, _, _ = build(cache, clock, provider=StubDataProvider(budget=budget))

    report = scheduler.estimate(only=[TASK_FIXTURES])

    entry = report["tasks"][TASK_FIXTURES]
    assert entry["would_run"] is False
    assert "spent" in entry["blocked"]
    assert report["total_requests"] == 0


# --------------------------------------------------------------------- status
def test_status_is_honest_about_a_task_that_has_never_run(cache, clock):
    scheduler, _, _, _ = build(cache, clock)

    status = scheduler.status()

    fixtures = status["tasks"][TASK_FIXTURES]
    assert fixtures["never_run"] is True
    assert fixtures["last_success_at"] is None and fixtures["last_run_at"] is None
    assert fixtures["runs"] == 0
    assert status["running"] is False, "nothing started the loop in this process"


def test_status_reports_what_the_last_pass_did(cache, clock):
    scheduler, _, _, _ = build(cache, clock)
    scheduler.run_once(only=[TASK_FIXTURES])

    fixtures = scheduler.status()["tasks"][TASK_FIXTURES]

    assert fixtures["never_run"] is False
    assert fixtures["last_success_at"] == NOW.isoformat()
    assert fixtures["next_due_at"] == (NOW + timedelta(seconds=scheduler.interval(TASK_FIXTURES))).isoformat()
    assert fixtures["runs"] == 1 and fixtures["failures"] == 0
    assert list(fixtures["last_result"]["days"]) == [NOW.date().isoformat()]


def test_status_reports_why_a_task_is_skipping(cache, clock, redis_client):
    budget = RequestBudget("stub", daily_limit=10, client=redis_client)
    _spend_budget(redis_client, "stub", 10)
    scheduler, _, _, _ = build(cache, clock, provider=StubDataProvider(budget=budget))
    scheduler.run_once(only=[TASK_FIXTURES])

    fixtures = scheduler.status()["tasks"][TASK_FIXTURES]

    assert fixtures["never_run"] is True, "a skipped task has still never actually run"
    assert "spent" in fixtures["last_skip_reason"]
    assert fixtures["last_skipped_at"] == NOW.isoformat()


def test_status_says_when_the_state_store_is_unavailable(clock):
    """Without Redis the scheduler cannot remember when anything last ran; freshness must not be faked."""
    scheduler = SyncScheduler(cache=MatchCache(client=None), now=clock)
    scheduler.cache._checked = True  # no Redis, and do not go looking for one

    status = scheduler.status()

    assert status["state_store_available"] is False
    assert all(task["never_run"] for task in status["tasks"].values())


# --------------------------------------------------------------------- one-shot script
def test_the_one_shot_script_shares_the_scheduler_and_calls_nothing_on_a_dry_run(monkeypatch):
    from scripts import sync_once

    calls = {"estimate": 0, "run_once": 0}

    class Recording(SyncScheduler):
        def estimate(self, only=None):
            calls["estimate"] += 1
            return {"tasks": {}, "total_requests": 0, "estimated_at": NOW.isoformat()}

        def run_once(self, only=None, force=False):  # pragma: no cover - must not be reached
            calls["run_once"] += 1
            return {"tasks": {}}

    monkeypatch.setattr(sync_once, "SyncScheduler", Recording)
    assert sync_once.main(["--dry-run"]) == 0
    assert calls == {"estimate": 1, "run_once": 0}


def test_the_one_shot_script_rejects_an_unknown_task():
    from scripts import sync_once
    with pytest.raises(SystemExit):
        sync_once.main(["--task", "standings"])


# ------------------------------------------------------------------ settlement is scheduled
def test_settle_is_one_of_the_scheduled_tasks():
    """Results were being ingested with nothing to score them.

    The results task and the settlement service were built in parallel and neither wired the two
    together, so final scores landed in the database and prediction_results stayed empty. This
    pins the connection.
    """
    from app.services import sync_scheduler as module

    assert module.TASK_SETTLE in module.TASK_NAMES
    assert module.TASK_SETTLE in settings.SYNC_SCHEDULER_TASKS.split(",")
    # and it runs after results, so a score ingested this pass is settled in the same pass
    assert module.TASK_NAMES.index(module.TASK_SETTLE) > module.TASK_NAMES.index(module.TASK_RESULTS)


def test_scoring_costs_no_provider_request_and_no_allowance_can_block_it():
    """A spent allowance must never stop us scoring what we already hold."""
    from app.services import sync_scheduler as module

    services = object.__new__(module._Services)
    # no provider is reachable for this task, so the budget ceiling has nothing to stop
    assert module.SyncScheduler._providers_for(services, module.TASK_SETTLE) == []
    scheduler = module.SyncScheduler(tasks=[module.TASK_SETTLE])
    assert scheduler._budget_block(services, module.TASK_SETTLE) is None
