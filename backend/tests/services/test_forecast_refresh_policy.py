"""
The forecast refresh policy on a simulated clock: one refresh slot per competition per UTC day.

What the earlier rule (`elapsed-interval`: 22 h since the last sync, behind the scheduler's noon
gate) got wrong was measured, not argued: a competition refreshed at 20:01 on day D was not
eligible at noon on D+1 (16 h elapsed) nor at 17:59 (21 h 58 min), and the next pass was gated
until noon on D+2 - forty hours without a refresh. `daily-slot` replaces elapsed time with the UTC
day, and this module pins the rest of the design note (docs/design/forecast-refresh-policy.md):
no fetch before the OBSERVED publication hour, one re-check a day for a fetch that bought an older
run and only from spare allowance, state that survives a restart, a deferral that leads the next
pass, a dormant competition that wakes up when its calendar lists a match, and an estimate that
agrees with the pass it describes.

No database and no network: a fake clock, an in-memory Redis stand-in whose TTLs expire against
that clock, a real `RequestBudget` counting in it, and a stub provider that dates its runs. Every
call the stub records is a request a real deployment would have paid for.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.config import settings
from app.services.forecast_refresh_policy import (
    OUTCOME_DEFERRED, OUTCOME_DORMANT, OUTCOME_OLDER_RUN, OUTCOME_SAME_DAY_RUN, POLICY_DAILY_SLOT,
    POLICY_ELAPSED_INTERVAL, judge_calendar,
)
from app.services.forecast_service import COOLDOWN_KEY, ForecastService
from app.services.match_cache import MatchCache
from app.services.match_data_service import SyncMeta
from app.services.providers.base import ForecastProvider, ProviderForecast
from app.services.providers.budget import RequestBudget, budget_key
from app.services.sync_scheduler import TASK_FORECASTS, SyncScheduler
from tests.providers.support import json_response
from tests.services import test_forecast_sync_order as real
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

PROVIDER = "stub"
DAY = datetime(2026, 10, 19, tzinfo=timezone.utc)
TODAY = DAY.date().isoformat()
KEYS = ["premier_league", "la_liga", "serie_a"]
#: Nearest kick-off first is the order within a priority, so la_liga leads, then premier_league.
KICKOFFS = {"premier_league": DAY + timedelta(days=2, hours=20),
            "la_liga": DAY + timedelta(days=1, hours=19),
            "serie_a": DAY + timedelta(days=3, hours=17)}
BY_KICKOFF = ["la_liga", "premier_league", "serie_a"]


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return DAY + timedelta(days=day, hours=hour, minutes=minute)


def todays_run(now: datetime) -> datetime:
    """The provider's dated run for the day of `now` - what a fetch obtains once it is published."""
    return now.replace(hour=6, minute=0, second=0, microsecond=0)


def yesterdays_run(now: datetime) -> datetime:
    return todays_run(now) - timedelta(days=1)


class DatedStubProvider(ForecastProvider):
    """Pays one request per fetch out of a real budget and dates its forecasts with `run_at(now)`."""

    name = PROVIDER
    integration_status = "test"

    def __init__(self, budget: RequestBudget, clock: Clock,
                 run_at: Optional[Callable[[datetime], Optional[datetime]]] = None,
                 costs: Optional[Dict[str, int]] = None):
        self.budget = budget
        self.clock = clock
        self.run_at = run_at or todays_run
        self.calls: List[Tuple[str, datetime]] = []
        self._costs = dict(costs or {})

    def is_configured(self) -> bool:
        return True

    def request_cost(self, key: str) -> int:
        return self._costs.get(key, 1)

    def get_forecasts(self, key, date_from, date_to):
        self.budget.consume(1, reason="fetch")
        now = self.clock()
        self.calls.append((key, now))
        return [ProviderForecast(provider=PROVIDER, external_event_id=f"{key}-{now.date().isoformat()}",
                                 home_name="Home", away_name="Away",
                                 kickoff_utc=KICKOFFS.get(key, now + timedelta(days=1)),
                                 home_prob=0.5, draw_prob=0.3, away_prob=0.2,
                                 model_run_at=self.run_at(now), fetched_at=now)]


class Harness:
    """A ForecastService over the fakes, rebuilt the way the scheduler rebuilds one each pass."""

    def __init__(self, clock: Clock, redis: LockingFakeRedis, *, keys=KEYS, limit: int = 8, run_at=None,
                 costs=None, kickoffs=None, counts: Optional[Dict[str, int]] = None, calendar=None):
        self.clock, self.redis = clock, redis
        self.cache = MatchCache(client=redis)
        self.budget = RequestBudget(PROVIDER, limit, client=redis, now=clock)
        self.provider = DatedStubProvider(self.budget, clock, run_at=run_at, costs=costs)
        self.keys = list(keys)
        self.kickoffs = dict(KICKOFFS if kickoffs is None else kickoffs)
        self.counts = counts if counts is not None else {}
        self.calendar = calendar
        self.service = self.new_service()

    def new_service(self) -> ForecastService:
        """A fresh instance over the same store: what a restart, or the next pass, builds."""
        service = ForecastService(MagicMock(), provider=self.provider, cache=self.cache, now=self.clock(),
                                  keys=list(self.keys), sync_fixtures=False)
        service.registry = MagicMock()
        service.registry.ensure_canonical_league.side_effect = lambda key: SimpleNamespace(id=key)
        service.registry.next_kickoff.side_effect = lambda league_id, start: self.kickoffs.get(league_id)
        service.registry.fixtures_in_window.side_effect = lambda league_id, start, end: self.counts.get(league_id, 1)
        # Binding is the registry's business and the registry is a double here; every forecast is
        # held as unmatched, which keeps the free re-attachment path exercised on every pass.
        service.attach_forecast = lambda forecast, key, league_id: {"result": "unmatched",
                                                                    "reason": "no fixtures in this harness"}
        if self.calendar is not None:
            service._fixtures, service._sync_fixtures = MagicMock(), True
            service._fixtures.sync_upcoming.side_effect = lambda key, days: self.calendar(key)
        return service

    def at(self, when: datetime, service: Optional[ForecastService] = None) -> ForecastService:
        self.clock.now = when
        service = service or self.service
        service._now = when
        return service

    def run(self, when: datetime, force: bool = False, service: Optional[ForecastService] = None):
        return self.at(when, service).ensure_synced(force=force)

    def calls(self) -> List[str]:
        return [key for key, _ in self.provider.calls]

    def policy(self):
        return self.service.policy

    def paused(self) -> bool:
        return self.cache.get(COOLDOWN_KEY.format(provider=PROVIDER)) is not None


@pytest.fixture(autouse=True)
def daily_slot(monkeypatch):
    """The branch default, pinned so these tests say which rule they are about."""
    monkeypatch.setattr(settings, "GAMEFORECAST_REFRESH_POLICY", POLICY_DAILY_SLOT)
    monkeypatch.setattr(settings, "SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR", 12)


@pytest.fixture
def clock():
    return Clock(at(0, 12, 1))


@pytest.fixture
def redis(clock):
    return LockingFakeRedis(clock=clock)


# ----------------------------------------------------------------- the regression the policy exists for
def test_a_competition_refreshed_at_20_01_is_refreshed_again_at_noon_the_next_day(clock, redis):
    """The 20:01 regression: a new UTC day is a new slot, however few hours have elapsed."""
    h = Harness(clock, redis)

    h.run(at(0, 20, 1), force=True)        # D 20:01: an evening refresh takes D's slot
    assert sorted(h.calls()) == sorted(KEYS)

    early = h.run(at(1, 6, 1))              # D+1 06:01: offered, and before the observed hour
    assert len(h.calls()) == 3 and early["skipped"] == KEYS and early.get("error") is None
    assert all("publication hour" in why for why in early["plan"]["ineligible"].values())

    noon = h.run(at(1, 12, 1))              # D+1 12:01: sixteen hours after the evening refresh
    assert len(h.calls()) == 6, "the elapsed-interval rule skipped this pass (16 h < 22 h) and waited for noon on D+2"
    assert noon["skipped"] == [] and [key for key, _ in h.provider.calls[3:]] == BY_KICKOFF
    assert h.provider.calls[3][1] - h.provider.calls[0][1] == timedelta(hours=16)


def test_the_elapsed_interval_rule_leaves_the_same_competition_forty_hours_without_a_refresh(clock, redis, monkeypatch):
    """Kept exactly, for the comparison: the gap the design note measured, reproduced."""
    monkeypatch.setattr(settings, "GAMEFORECAST_REFRESH_POLICY", POLICY_ELAPSED_INTERVAL)
    h = Harness(clock, redis)

    h.run(at(0, 20, 1), force=True)
    assert h.run(at(1, 12, 1))["skipped"] == KEYS, "16 h elapsed, inside the 22 h interval"
    assert h.run(at(1, 17, 59))["skipped"] == KEYS, "21 h 58 min elapsed, still inside it"
    assert len(h.calls()) == 3
    # The 00:01 and 06:01 passes of D+2 are gated by the scheduler (`due`, pinned in
    # test_sync_scheduler.py), so the next refresh is the noon pass of D+2.
    h.run(at(2, 12, 1))
    assert len(h.calls()) == 6
    assert h.provider.calls[3][1] - h.provider.calls[0][1] == timedelta(hours=40)


# ----------------------------------------------------------------- the observed publication hour
def test_no_fetch_is_made_before_the_observed_publication_hour(clock, redis):
    h = Harness(clock, redis)

    report = h.run(at(0, 11, 59))

    assert h.calls() == [] and report["skipped"] == KEYS
    assert report["plan"]["publication_hour"] == 12 and report["plan"]["hour_reached"] is False
    assert h.budget.used_today() == 0

    assert h.run(at(0, 12, 0))["skipped"] == [] and len(h.calls()) == 3


def test_a_same_day_run_observed_earlier_brings_the_hour_forward_and_a_later_one_never_pushes_it_back(clock, redis):
    """The hour is observed: the earliest same-day run of the last fortnight, never later than the baseline."""
    h = Harness(clock, redis, run_at=lambda now: now.replace(hour=5, minute=0))  # the run exists from 05:00
    h.run(at(0, 9, 30), force=True)         # a forced sync at 09:30 obtains the day's run: an observation at 9
    assert h.policy().publication_hour() == 9
    assert h.policy().publication_evidence()["observed"] == {TODAY: 9}

    h.run(at(1, 9, 31))                     # the next day, 09:31 is late enough
    assert len(h.calls()) == 6

    h.run(at(16, 9, 31))                    # a fortnight on, the observation has expired: back to the baseline
    assert len(h.calls()) == 6 and h.policy().publication_hour() == 12

    late = Harness(clock, LockingFakeRedis(clock=clock))
    late.run(at(0, 18, 5), force=True)      # a same-day run obtained at 18:05 is an observation at 18 ...
    assert late.policy().publication_evidence()["observed"] == {TODAY: 18}
    assert late.policy().publication_hour() == 12, "... and the baseline, itself an observation, is the earlier"


def test_a_fetch_returning_an_older_run_is_rechecked_once_later_the_same_day(clock, redis):
    """At noon the provider still serves yesterday's run; the re-check at six buys today's."""
    published_at = at(0, 15)

    def run_at(now):
        return todays_run(now) if now >= published_at else yesterdays_run(now)

    h = Harness(clock, redis, run_at=run_at)

    h.run(at(0, 12, 1))
    assert len(h.calls()) == 3
    for key in KEYS:
        slot = h.policy().slot(key)
        assert (slot["day"], slot["outcome"]) == (TODAY, OUTCOME_OLDER_RUN)
    assert h.policy().publication_evidence()["not_yet"] == {TODAY: 12}
    assert h.policy().publication_hour() == 12, "an older run moves the hour nowhere"

    evening = h.run(at(0, 18, 1))
    assert len(h.calls()) == 6 and evening["rechecked"] == BY_KICKOFF
    for key in KEYS:
        slot = h.policy().slot(key)
        assert slot["outcome"] == OUTCOME_SAME_DAY_RUN and slot["first_outcome"] == OUTCOME_OLDER_RUN
        assert slot["recheck"]["outcome"] == OUTCOME_SAME_DAY_RUN
    assert h.policy().publication_evidence()["observed"] == {TODAY: 18}

    late = h.run(at(0, 20, 1))
    assert len(h.calls()) == 6 and late["skipped"] == KEYS, "one re-check per competition per day"


def test_a_recheck_is_paid_from_spare_allowance_only(clock, redis):
    """Nothing spare, no re-check - and no deferral, no pause: a re-check is not owed."""
    h = Harness(clock, redis, limit=3, run_at=yesterdays_run)
    h.run(at(0, 12, 1))
    assert len(h.calls()) == 3 and h.budget.remaining() == 0

    evening = h.run(at(0, 18, 1))

    assert len(h.calls()) == 3
    assert set(evening["recheck_skipped"]) == set(KEYS)
    assert evening.get("error") is None and evening["deferred"] == [] and not h.paused()

    # One spare request buys exactly one re-check, nearest kick-off first.
    one_spare = Harness(clock, LockingFakeRedis(clock=clock), limit=4, run_at=yesterdays_run)
    one_spare.run(at(0, 12, 1))
    evening = one_spare.run(at(0, 18, 1))
    assert one_spare.calls()[3:] == ["la_liga"] and evening["rechecked"] == ["la_liga"]
    assert set(evening["recheck_skipped"]) == {"premier_league", "serie_a"}
    assert evening.get("error") is None and not one_spare.paused()


# ----------------------------------------------------------------- state, restarts, deferrals
def test_a_restart_does_not_refetch_a_day_already_fetched(clock, redis):
    h = Harness(clock, redis)
    h.run(at(0, 12, 1))
    assert len(h.calls()) == 3

    restarted = h.new_service()             # a new instance over the same Redis
    report = h.run(at(0, 13, 0), service=restarted)

    assert len(h.calls()) == 3 and report["skipped"] == KEYS
    assert all("one slot per UTC day" in why for why in report["plan"]["ineligible"].values())


def test_an_exhausted_allowance_defers_and_the_deferred_competition_leads_the_next_pass(clock, redis):
    h = Harness(clock, redis, limit=2)

    first = h.run(at(0, 12, 1))

    assert h.calls() == ["la_liga", "premier_league"], "nearest kick-off first, until the allowance runs out"
    assert first["deferred"] == ["serie_a"]
    assert "serie_a" in first["error"] and "leads the next pass" in first["error"]
    assert h.policy().slot("serie_a")["outcome"] == OUTCOME_DEFERRED
    assert h.paused(), "nothing more can be bought until the allowance comes back"

    second = h.run(at(1, 12, 1))            # the next day: a fresh allowance, and the pause has expired

    assert second.get("paused") is None
    assert second["plan"]["deferred_first"] == ["serie_a"]
    assert h.calls() == ["la_liga", "premier_league", "serie_a", "la_liga"], \
        "the deferred competition goes first, ahead of nearer kick-offs"
    assert second["deferred"] == ["premier_league"]


def test_a_dormant_competition_wakes_up_when_its_calendar_lists_a_fixture(clock, redis):
    counts = {"serie_a": 0}
    h = Harness(clock, redis, counts=counts,
                calendar=lambda key: SyncMeta(source="provider", provider="livescore"))

    first = h.run(at(0, 12, 1))

    assert h.calls() == ["la_liga", "premier_league"] and first["dormant"] == ["serie_a"]
    assert first["competitions"]["serie_a"]["skipped"] == "no fixture in window"
    assert h.policy().slot("serie_a")["outcome"] == OUTCOME_DORMANT
    assert h.budget.used_today() == 2, "a dormant turn costs nothing"

    counts["serie_a"] = 2                   # the calendar now lists a match inside the window
    second = h.run(at(1, 12, 1))

    assert "dormant" not in second and h.calls()[3:].count("serie_a") == 1


# ----------------------------------------------------------------- the estimate and the pass agree
def _scheduler(h: Harness, service: ForecastService) -> SyncScheduler:
    return SyncScheduler(session_factory=lambda: MagicMock(), cache=h.cache, now=h.clock,
                         forecast_service_factory=lambda _db: service, tasks=[TASK_FORECASTS],
                         close_sessions=False, budget_client=h.redis)


def test_the_estimate_agrees_with_the_pass_a_deferral_a_dormant_competition_and_a_fetch(clock, redis, monkeypatch):
    """Dormancy from the evidence a turn recorded an hour earlier, a deferral by the allowance that is
    left, and the fetch that fits: the dry run prices the pass it describes."""
    monkeypatch.setattr(settings, "SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR", 0)   # the rule is off, so the evening and the small hours both count
    counts = {"serie_a": 0}
    h = Harness(clock, redis, counts=counts, calendar=lambda key: SyncMeta(source="provider", provider="livescore"))
    h.run(at(0, 23, 30))                    # D 23:30: two fetches, serie_a found dormant (evidence recorded)
    assert h.calls() == ["la_liga", "premier_league"]

    service = h.at(at(1, 0, 30), h.new_service())   # D+1 00:30, with one request left in the new day's allowance
    redis.store[budget_key(PROVIDER, at(1, 0, 30))] = 7
    entry = _scheduler(h, service).estimate(only=[TASK_FORECASTS])["tasks"][TASK_FORECASTS]

    assert len(h.calls()) == 2, "an estimate makes no provider request"
    assert entry["estimated_requests"] == 1
    assert "1 dormant on recorded calendar evidence" in entry["basis"]
    assert "1 deferred by the remaining" in entry["basis"]

    report = service.ensure_synced()

    assert h.calls()[2:] == ["la_liga"] and report["deferred"] == ["premier_league"]
    assert report["dormant"] == ["serie_a"]
    assert h.budget.used_today() == 8 and entry["estimated_requests"] == 1


def test_the_estimate_prices_discovery_the_way_the_pass_then_pays_for_it(clock, redis):
    """Six real competitions over the real provider: five recorded ids and one discovery, 7 for 7."""
    cache = MatchCache(client=redis)
    budget = RequestBudget("gameforecast", 8, client=redis, now=clock)
    service, recorder = real.build(clock, cache, budget)

    entry = real.estimate_for(clock, cache, service)
    assert recorder.requests == []
    service.ensure_synced()

    assert entry["estimated_requests"] == 7 == budget.used_today() == len(real.paths(recorder))
    assert real.paths(recorder).count("/leagues") == 1
    assert "1 costing 2 (a league-id discovery, then the fetch)" in entry["basis"]


def test_a_two_page_competition_is_priced_at_two_once_a_fetch_has_shown_it(clock, redis):
    """Pagination is priced from the last fetch: quoted at one page until seen, exact from then on."""
    def two_pages(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/events", f"unexpected provider call: {request.url.path}"
        page = int(dict(request.url.params).get("page", "1"))
        return json_response({"data": [], "pagination": {"hasMore": page == 1}})

    cache = MatchCache(client=redis)
    budget = RequestBudget("gameforecast", 8, client=redis, now=clock)
    day_one, recorder = real.build(clock, cache, budget, keys=["premier_league"], handler=two_pages)

    first = real.estimate_for(clock, cache, day_one)
    day_one.ensure_synced()
    assert first["estimated_requests"] == 1 and len(real.paths(recorder)) == 2, \
        "the first fetch of a two-page competition costs one more than quoted"
    assert day_one.provider.request_cost("premier_league") == 2

    clock.now = at(1, 12, 1)
    day_two, recorder = real.build(clock, cache, budget, keys=["premier_league"], handler=two_pages)
    second = real.estimate_for(clock, cache, day_two)
    day_two.ensure_synced()

    assert second["estimated_requests"] == 2 == len(real.paths(recorder)) == budget.used_today()
    assert "1 costing 2 (the last fetch needed two pages)" in second["basis"]


# ----------------------------------------------------------------- the dormancy verdict itself
@pytest.mark.parametrize("ran, source, stale, errors, asked, count, dormant", [
    (False, None, False, [], None, 0, False),            # no fixture sync ran: the empty window says nothing
    (True, "provider", False, ["upstream down"], 7, 0, False),  # the sync failed
    (True, "stale-cache", True, [], 7, 0, False),        # the 24-hour stale copy
    (True, "database", False, [], 7, 0, False),          # the chain never answered
    (True, "provider", False, [], 3, 0, False),          # asked for three days of a seven-day window
    (True, "provider", False, [], 7, 2, False),          # fixtures inside the window
    (True, "provider", False, [], 7, None, False),       # the database could not be counted
    (True, "provider", False, [], 7, 0, True),           # sufficient, and empty
    (True, "cache", False, [], 7, 0, True),              # a fresh cache copy is the provider's answer
], ids=["no-sync", "failed", "stale", "unanswered", "incomplete", "fixtures", "uncounted", "empty", "cached-empty"])
def test_dormancy_needs_every_condition(ran, source, stale, errors, asked, count, dormant):
    evidence = judge_calendar("serie_a", at(0, 12), 7, ran=ran, source=source, stale=stale, errors=errors,
                              asked_days=asked, count=lambda: count)
    assert evidence.dormant is dormant, evidence.reason
    assert evidence.reason


def test_the_database_is_only_counted_once_the_calendar_answer_qualifies():
    """A count of zero against a calendar nobody answered is the empty window that says nothing."""
    counted = MagicMock(return_value=0)
    judge_calendar("serie_a", at(0, 12), 7, ran=True, source="database", stale=False, errors=[],
                   asked_days=7, count=counted)
    assert not counted.called
    judge_calendar("serie_a", at(0, 12), 7, ran=True, source="provider", stale=False, errors=[],
                   asked_days=7, count=counted)
    assert counted.called
