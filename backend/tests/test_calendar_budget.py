"""
What a FAILING competition-calendar sweep is allowed to cost.

`tests/test_upcoming_fixtures.py` covers what a sweep answers and what a SUCCESSFUL one costs: six
requests, cached for six hours, so four sweeps a day. This file is about the other half of the
bill. Only a success is written to the cache, so a failing sweep leaves the TTL nothing to hold
and the next reader of an empty day meets a cold cache again. The floor is then the refresh lock,
120 seconds, which a stream of readers turns into six requests every two minutes - of the order of
a thousand a day, on a feature that exists to fill an empty page, spent out of the same Live Score
allowance the fixtures, live and results tasks run on.

Two things bound it, and both are tested here.

  - A backoff of the calendar's OWN: the wait after a failed sweep doubles from 120 seconds to a
    ceiling of 40 minutes, and a success clears it. It must be the calendar that is suppressed and
    not the provider: the general cool-down the live and results paths run through has to stay at
    its own short value, and a test that cannot tell the two apart is not testing this at all.

  - A daily ceiling read from the budget's own `calendar` attribution, so the number the ceiling
    enforces is the number the provider counted rather than a second count of our own. It is one
    ceiling PER PROVIDER, because a budget is per provider: a provider whose share is spent is
    passed over and the sweep moves down the chain, and only when nobody is left does the reader
    get told we could not find out - which is a state this endpoint already models, and never
    that the calendars are empty. What it counts is granted requests, so it bounds rather than
    equals what the feature costs a plan; the test that pins the difference says why.

No database and no network: the shipped MatchDataService and the shipped RequestBudget over
in-memory Redis stand-ins whose TTLs elapse against a fake clock.
"""

import asyncio
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.api.v1.endpoints.matches import upcoming_matches
from app.core.config import settings
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    CALENDAR_BUDGET_REASON, CALENDAR_HEAD_BACKOFF_BASE_SECONDS,
    CALENDAR_HEAD_BACKOFF_CEILING_SECONDS, CALENDAR_HEAD_BACKOFF_KEY,
    CALENDAR_HEAD_DAILY_REQUEST_CEILING, CALENDAR_HEAD_LOCK_KEY, CALENDAR_HEAD_LOCK_SECONDS,
    COOLDOWN_KEY, UNAVAILABLE_COOLDOWN_SECONDS, MatchDataService,
)
from app.services.providers import competitions as comps
from app.services.providers.base import ProviderUnavailableError
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from tests.providers.support import FakeRedis, json_response, make_transport
from tests.test_fixture_pipeline import Clock, ExpiringFakeRedis
from tests.test_upcoming_fixtures import KEYS, NOW, CalendarProvider, _fixture, _service

#: The Live Score trial plan these ceilings were sized against.
LIVESCORE_DAILY_LIMIT = 1200

#: One sweep costs one request per covered competition. Most tests here run on the two
#: `tests/test_upcoming_fixtures.py` defines, so the cost is read off that rather than written
#: down twice.
SWEEP_COST = len(KEYS)

#: What this installation actually covers, read from the same setting the service reads.
#:
#: A day-long simulation has to run on this rather than on the two keys above, because the two
#: guards divide the day between them differently at different competition counts: at two
#: competitions the backoff alone keeps a day of outage under the ceiling, and a test that names
#: the ceiling while running at that count is watching the backoff do all the work.
COVERED_KEYS = comps.covered_keys(settings.COVERED_COMPETITIONS)
COVERED_SWEEP_COST = len(COVERED_KEYS)


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def cache(clock):
    return MatchCache(client=ExpiringFakeRedis(clock=clock))


def _budget(clock, daily_limit: int = LIVESCORE_DAILY_LIMIT) -> RequestBudget:
    """A real RequestBudget on the fake clock, so its day key is the day the test is in."""
    return RequestBudget("livescore", daily_limit, client=FakeRedis(), now=clock)


def _metered(provider: CalendarProvider, budget: RequestBudget) -> CalendarProvider:
    """Give a calendar stub a budget, which is what the daily ceiling reads."""
    provider.budget = budget
    return provider


def _failing(reason: str = "upstream is down") -> CalendarProvider:
    provider = CalendarProvider({}, fail=ProviderUnavailableError(reason, provider="calendar-stub"))
    return provider


def _answering() -> CalendarProvider:
    return CalendarProvider({key: [_fixture(NOW + timedelta(days=19), key, key, "A", "B")]
                             for key in KEYS})


def _sweep(cache, clock, provider):
    """One reader arriving at a cold cache. Returns (answer, meta)."""
    return _service(cache, clock, [provider]).next_fixtures()


def _release_lock(cache) -> None:
    """Drop the one-sweep-at-a-time lock.

    The lock and the FIRST backoff wait are both 120 seconds, so a test that leaves the lock in
    place cannot say which of the two refused the next reader. Dropping it leaves the backoff as
    the only thing that can.
    """
    cache._redis().delete(CALENDAR_HEAD_LOCK_KEY)


def _backoff(cache) -> dict:
    return cache.get(CALENDAR_HEAD_BACKOFF_KEY) or {}


# ------------------------------------------------------------------ a failure backs off
def test_a_failed_sweep_is_not_retried_by_the_next_reader(cache, clock):
    """Without this the next page load re-sweeps, and six requests become a per-reader cost."""
    provider = _failing()
    answer, _ = _sweep(cache, clock, provider)
    # A sweep that fails stops there rather than asking the remaining competitions, so one entry
    # here is one sweep. A provider that fails on the LAST competition costs the full six.
    assert answer is None and provider.asked == KEYS[:1], "the first reader paid for one sweep"
    _release_lock(cache)

    answer, meta = _sweep(cache, clock, provider)

    assert provider.asked == KEYS[:1], "the second reader must not pay for a sweep of its own"
    assert answer is None, "and must not be handed an empty calendar it never read"
    assert any("could not be read" in error for error in meta.errors)


def test_the_first_retry_is_no_slower_than_the_floor_that_already_existed(cache, clock):
    """A single bad minute must stay cheap to recover from: one failure, one short wait."""
    _sweep(cache, clock, _failing())

    assert _backoff(cache)["wait_seconds"] == CALENDAR_HEAD_BACKOFF_BASE_SECONDS
    assert CALENDAR_HEAD_BACKOFF_BASE_SECONDS == CALENDAR_HEAD_LOCK_SECONDS, \
        "the first wait is the lock's own floor, so one blip costs a reader nothing extra"


def test_the_wait_doubles_with_each_failure_in_a_row(cache, clock):
    """A provider that keeps failing is asked less and less often, not every two minutes."""
    provider = _failing()
    waits = []
    for _ in range(4):
        _sweep(cache, clock, provider)
        waits.append(_backoff(cache)["wait_seconds"])
        clock.tick(waits[-1] + 1)
        _release_lock(cache)

    assert waits == [120, 240, 480, 960]
    assert len(provider.asked) == 4, "each of those four windows paid for one sweep and no more"


def test_the_wait_stops_growing_at_its_ceiling(cache, clock):
    provider = _failing()
    for _ in range(12):
        _sweep(cache, clock, provider)
        clock.tick(_backoff(cache)["wait_seconds"] + 1)
        _release_lock(cache)

    assert _backoff(cache)["wait_seconds"] == CALENDAR_HEAD_BACKOFF_CEILING_SECONDS
    assert CALENDAR_HEAD_BACKOFF_CEILING_SECONDS == 40 * 60, \
        "tens of minutes for an answer that changes weekly, not hours"


def test_a_reader_arriving_inside_a_grown_wait_is_still_turned_away(cache, clock):
    """The wait is what refuses, and by the second failure it outlasts the lock and the cool-down."""
    provider = _failing()
    _sweep(cache, clock, provider)                       # wait 120s
    clock.tick(CALENDAR_HEAD_BACKOFF_BASE_SECONDS + 1)
    _release_lock(cache)
    _sweep(cache, clock, provider)                       # wait 240s
    asked_twice = list(provider.asked)
    _release_lock(cache)

    clock.tick(CALENDAR_HEAD_BACKOFF_BASE_SECONDS + 1)   # past the lock, inside the wait
    _sweep(cache, clock, provider)
    assert provider.asked == asked_twice, "still inside the second wait"

    clock.tick(CALENDAR_HEAD_BACKOFF_BASE_SECONDS + 1)   # now past the wait as well
    _sweep(cache, clock, provider)
    assert provider.asked == asked_twice + KEYS[:1], "and free to try again once it has elapsed"


def test_a_sweep_that_answers_clears_the_streak(cache, clock):
    """One bad minute must not suppress the feature for the rest of the hour."""
    provider = _failing()
    for _ in range(3):
        _sweep(cache, clock, provider)
        clock.tick(_backoff(cache)["wait_seconds"] + 1)
        _release_lock(cache)
    assert _backoff(cache)["failures"] == 3

    _sweep(cache, clock, _answering())

    assert _backoff(cache) == {}, "the answer is the evidence that the streak is over"


def test_a_streak_that_was_cleared_starts_again_at_the_floor(cache, clock):
    """Cleared means forgotten. A later failure must not resume at the wait the last streak reached."""
    provider = _failing()
    for _ in range(3):
        _sweep(cache, clock, provider)
        clock.tick(_backoff(cache)["wait_seconds"] + 1)
        _release_lock(cache)
    _sweep(cache, clock, _answering())

    clock.tick(7 * 3600)  # past the cached answer's own TTL, so the next reader sweeps again
    _release_lock(cache)
    _sweep(cache, clock, provider)

    assert _backoff(cache)["failures"] == 1
    assert _backoff(cache)["wait_seconds"] == CALENDAR_HEAD_BACKOFF_BASE_SECONDS


def test_a_cached_answer_is_served_without_consulting_the_backoff(cache, clock):
    """The backoff governs spending. An answer already held costs nothing and is not spending."""
    _sweep(cache, clock, _answering())
    cache.set(CALENDAR_HEAD_BACKOFF_KEY,
              {"failures": 9, "wait_seconds": CALENDAR_HEAD_BACKOFF_CEILING_SECONDS,
               "retry_at": (NOW + timedelta(hours=1)).isoformat()},
              ttl=3600, stale_ttl=3600)

    answer, meta = _sweep(cache, clock, _answering())

    assert meta.source == "cache"
    assert [f["external_id"] for f in answer["fixtures"]] == list(KEYS)


def test_a_stale_answer_is_served_rather_than_unknown_while_backing_off(cache, clock):
    """A copy we already hold is free, and a dated calendar beats no calendar at all."""
    _sweep(cache, clock, _answering())
    clock.tick(7 * 3600)                     # the fresh copy has expired; the stale one has not
    _release_lock(cache)
    _sweep(cache, clock, _failing())         # fails, and starts the backoff
    _release_lock(cache)

    answer, meta = _sweep(cache, clock, _failing())

    assert meta.source == "stale-cache" and meta.stale is True
    assert [f["external_id"] for f in answer["fixtures"]] == list(KEYS)


# ------------------------------------------- the general cool-down the other paths depend on
def test_the_calendar_backoff_does_not_lengthen_the_general_provider_cool_down(cache, clock):
    """Live and results run through `COOLDOWN_KEY`. Stretching it here would stall both.

    The calendar backs off for four minutes after its second failure; the provider as a whole is
    still only in cool-down for the two that `_call_chain` sets for any upstream failure.
    """
    provider = _failing()
    service = _service(cache, clock, [provider])
    service.next_fixtures()
    clock.tick(CALENDAR_HEAD_BACKOFF_BASE_SECONDS + 1)
    _release_lock(cache)
    _service(cache, clock, [provider]).next_fixtures()   # second failure: the wait is now 240s

    cooldown_ttl = cache._redis().ttls[COOLDOWN_KEY.format(name="calendar-stub")]
    assert cooldown_ttl == UNAVAILABLE_COOLDOWN_SECONDS == 120

    clock.tick(CALENDAR_HEAD_BACKOFF_BASE_SECONDS + 1)
    later = _service(cache, clock, [provider])
    assert later._cooldown("calendar-stub") is None, \
        "the live and results paths may call this provider again"
    assert later._calendar_backoff_refusal() is not None, \
        "while the calendar, which failed twice, is still waiting"


def test_the_backoff_key_is_the_calendars_own(cache, clock):
    """Keyed to the sweep, not to the provider: nothing else may be suppressed by it."""
    _sweep(cache, clock, _failing())

    assert CALENDAR_HEAD_BACKOFF_KEY not in {COOLDOWN_KEY.format(name="calendar-stub"),
                                             CALENDAR_HEAD_LOCK_KEY}
    assert cache.get(CALENDAR_HEAD_BACKOFF_KEY) is not None


# ------------------------------------------------------------------ the daily ceiling
def test_the_ceiling_refuses_the_sweep_once_the_days_share_is_spent(cache, clock):
    budget = _budget(clock)
    budget.consume(CALENDAR_HEAD_DAILY_REQUEST_CEILING - 1, reason=CALENDAR_BUDGET_REASON)
    provider = _metered(_answering(), budget)

    answer, meta = _sweep(cache, clock, provider)

    assert provider.asked == [], "119 spent plus a 2-request sweep is over a ceiling of 120"
    assert answer is None
    assert any("share of the request allowance" in error for error in meta.errors)


def test_a_sweep_that_still_fits_under_the_ceiling_goes_ahead(cache, clock):
    """The control for the test above: the ceiling refuses what does not fit, and only that."""
    budget = _budget(clock)
    budget.consume(CALENDAR_HEAD_DAILY_REQUEST_CEILING - SWEEP_COST, reason=CALENDAR_BUDGET_REASON)
    provider = _metered(_answering(), budget)

    answer, _ = _sweep(cache, clock, provider)

    assert provider.asked == KEYS and answer is not None


def test_a_refusal_by_the_ceiling_reads_as_unknown_and_not_as_an_empty_calendar(cache, clock):
    """The reader is told we could not find out. "No football is scheduled" would be a lie."""
    budget = _budget(clock)
    budget.consume(CALENDAR_HEAD_DAILY_REQUEST_CEILING, reason=CALENDAR_BUDGET_REASON)
    service = _service(cache, clock, [_metered(_answering(), budget)])

    with patch("app.api.v1.endpoints.matches.MatchDataService", return_value=service):
        body = asyncio.run(upcoming_matches(limit=5, db=MagicMock()))

    assert body["known"] is False, "an answer nobody paid for is not the answer 'nothing'"
    assert body["fixtures"] == [] and body["next_kickoff"] is None
    assert body["source"] is None
    assert any("share of the request allowance" in error for error in body["errors"])


def test_the_ceiling_takes_no_lock_it_will_not_use(cache, clock):
    """A reader turned away must not hold the guard that the next affordable sweep needs."""
    budget = _budget(clock)
    budget.consume(CALENDAR_HEAD_DAILY_REQUEST_CEILING, reason=CALENDAR_BUDGET_REASON)

    _sweep(cache, clock, _metered(_answering(), budget))

    assert cache._redis().get(CALENDAR_HEAD_LOCK_KEY) is None


def test_the_ceiling_counts_the_budgets_own_calendar_attribution(cache, clock):
    """Read from `by_reason`, not from a counter of our own that could drift from it.

    A day of heavy fixture syncing spends hundreds under "fetch". None of it is calendar
    spending, and charging it to this ceiling would shut the feature off on a day it cost nothing.
    """
    budget = _budget(clock)
    budget.consume(600, reason="fetch")
    provider = _metered(_answering(), budget)

    answer, _ = _sweep(cache, clock, provider)

    assert budget.by_reason() == {"fetch": 600}, "none of it attributed to the calendar"
    assert provider.asked == KEYS, "600 requests of fixture syncing is not calendar spending"
    assert answer is not None


def test_the_sweep_it_pays_for_is_attributed_where_the_ceiling_reads_it(cache, clock):
    """The ceiling is only self-limiting if a granted sweep lands in the field it counts."""
    budget = _budget(clock)
    before = budget.by_reason().get(CALENDAR_BUDGET_REASON, 0)
    budget.consume(SWEEP_COST, reason=CALENDAR_BUDGET_REASON)

    assert budget.by_reason()[CALENDAR_BUDGET_REASON] == before + SWEEP_COST
    assert budget.used_today() == SWEEP_COST, "and against the day's total as well"


def test_a_retry_the_provider_charges_itself_is_outside_what_the_ceiling_counts(monkeypatch, clock):
    """What the ceiling counts is GRANTED requests, which is a bound and not an equality.

    Live Score API answers a burst of calls with a 401, and `livescore_api._get` retries once
    before believing it. That retry is a second outbound request and the provider charges it,
    under `retry` rather than under the caller's reason - so one granted calendar request can cost
    the plan two while the ceiling counts one. One retry is the most a request can add, so the
    ceiling still bounds the feature at twice its number; the docstring on
    `_calendar_ceiling_refusal` says so, and this is what holds it to saying it.
    """
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr("app.services.providers.livescore_api.BURST_RETRY_DELAY", 0.0)
    burst_401 = {"success": False,
                 "error": "This API key and secret do not have access to our data enabled"}
    calls = {"n": 0}

    def burst_then_answer(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return json_response(burst_401, 401)
        return json_response({"success": True, "data": {"fixtures": [], "next_page": False}})

    transport, recorder = make_transport(burst_then_answer)
    budget = _budget(clock)
    provider = LiveScoreAPIProvider(api_key="trial-key", api_secret="trial-secret",
                                    transport=transport, budget=budget,
                                    competition_overrides={"premier_league": "2"},
                                    store=MatchCache(client=FakeRedis()), use_default_ids=False)

    provider.get_calendar_head("premier_league", limit=5)

    assert len(recorder.requests) == 2, "the burst 401 and the retry that followed it"
    assert budget.by_reason() == {CALENDAR_BUDGET_REASON: 1, "retry": 1}, \
        "the retry is charged to the day, and not to the share the ceiling reads"
    assert budget.used_today() == 2, "so the plan paid twice for the one request the ceiling saw"


def test_the_ceiling_is_scaled_down_for_a_plan_too_small_to_carry_it(cache, clock):
    """A 6-request sweep has no business on a 10-request plan, and a tenth of 10 says so."""
    provider = _metered(_answering(), _budget(clock, daily_limit=10))

    answer, meta = _sweep(cache, clock, provider)

    assert provider.asked == [] and answer is None
    assert any("share of the request allowance" in error for error in meta.errors)


def test_a_provider_with_no_budget_at_all_is_not_stopped_by_the_ceiling(cache, clock):
    """An unmetered provider has no attribution to read, so nothing here can say it is out."""
    provider = _answering()
    assert provider.budget is None

    answer, _ = _sweep(cache, clock, provider)

    assert provider.asked == KEYS and answer is not None


def test_a_provider_whose_share_is_spent_is_passed_over_and_the_next_one_answers(cache, clock):
    """The decision this feature makes when the primary is capped and a fallback is not.

    A ceiling is per provider because a budget is, so the capped provider must not be swept even
    though the sweep as a whole goes ahead. Both stubs here would answer if asked, which is what
    makes the assertion sharp: a chain that consulted the ceiling once and then called whoever
    was first would charge the capped primary and this would fail.

    Spending the fallback is deliberate, not a side effect: it is protected by its own copy of the
    ceiling, and the scheduled tasks fall down the same chain when the primary is out, so the
    share that protects them travels with the work.
    """
    capped, spare = _answering(), _answering()
    capped.name, spare.name = "capped-stub", "spare-stub"
    _metered(capped, _budget(clock))
    _metered(spare, _budget(clock))
    capped.budget.consume(CALENDAR_HEAD_DAILY_REQUEST_CEILING, reason=CALENDAR_BUDGET_REASON)

    answer, meta = _service(cache, clock, [capped, spare]).next_fixtures()

    assert capped.asked == [], "the provider with no share left may not be the one that pays"
    assert spare.asked == KEYS and answer is not None
    assert meta.provider == "spare-stub"
    assert any("capped-stub" in error and "share of the request allowance" in error
               for error in meta.errors), "and the reader is told which provider was passed over"


def test_the_ceiling_binds_on_a_capped_primary_even_with_a_fallback_behind_it(cache, clock):
    """The configured chain carries three budgets, and a share of three plans is not one share.

    `DATA_PROVIDER_FALLBACKS` means `self.providers` is normally more than one provider, each with
    a budget of its own. If room anywhere let the sweep proceed against the primary regardless,
    the primary's ceiling would never refuse anything on the shipped configuration.
    """
    capped, spare = _answering(), _answering()
    capped.name, spare.name = "capped-stub", "spare-stub"
    _metered(capped, _budget(clock))
    _metered(spare, _budget(clock))
    capped.budget.consume(CALENDAR_HEAD_DAILY_REQUEST_CEILING, reason=CALENDAR_BUDGET_REASON)
    spent_before = capped.budget.used_today()

    # Two sweeps seven hours apart: far enough that the second meets an expired answer and pays
    # again, close enough that both fall inside 2026-09-21. A share is a share of a UTC DAY, so a
    # clock carried past midnight would hand the capped provider a fresh one - correctly, and not
    # what this test is about, which is why the day's spending is read while the day is still on.
    for sweep in range(2):
        if sweep:
            clock.tick(7 * 3600)
            _release_lock(cache)
        _service(cache, clock, [capped, spare]).next_fixtures()
        assert capped.budget.used_today() == spent_before, "not one request more at the capped plan"

    assert capped.asked == []
    assert spare.asked == KEYS * 2, "the two sweeps were paid for where there was room to pay"


def test_every_provider_out_of_share_refuses_before_any_lock_is_taken(cache, clock):
    """When there is nobody left to move on to, the chain-level check answers and stops."""
    first, second = _answering(), _answering()
    first.name, second.name = "first-stub", "second-stub"
    for provider in (first, second):
        _metered(provider, _budget(clock))
        provider.budget.consume(CALENDAR_HEAD_DAILY_REQUEST_CEILING, reason=CALENDAR_BUDGET_REASON)

    answer, meta = _service(cache, clock, [first, second]).next_fixtures()

    assert answer is None and first.asked == [] and second.asked == []
    assert cache._redis().get(CALENDAR_HEAD_LOCK_KEY) is None
    assert any("first-stub" in error and "second-stub" in error for error in meta.errors), \
        "one refusal naming both, not a chain walked one failure at a time"


def test_the_ceiling_leaves_the_scheduled_tasks_their_allowance(cache, clock):
    """What the ceiling was chosen against, kept as an assertion rather than a comment.

    The scheduler holds `SYNC_SCHEDULER_BUDGET_RESERVE` back for interactive page loads; this
    ceiling holds allowance back from one interactive page load for the scheduler. Both together
    have to leave the fixtures, live and results tasks more than the heaviest day this
    installation has recorded (683 requests on 2026-09-20).
    """
    reserve = min(int(settings.SYNC_SCHEDULER_BUDGET_RESERVE), LIVESCORE_DAILY_LIMIT // 10)
    left_for_sync = LIVESCORE_DAILY_LIMIT - CALENDAR_HEAD_DAILY_REQUEST_CEILING - reserve

    assert CALENDAR_HEAD_DAILY_REQUEST_CEILING <= LIVESCORE_DAILY_LIMIT // 10
    assert left_for_sync >= 1000, f"only {left_for_sync} left for fixtures, live and results"


def test_a_whole_day_of_outage_leaves_the_synchronisation_its_allowance(cache, clock):
    """The question both guards exist to answer, run rather than reasoned about.

    A reader of an empty day arrives every minute for twenty-four hours and every sweep fails.
    The backoff thins those readers from 1440 arrivals to a few dozen sweeps and the ceiling stops
    the rest, and what has to survive it is the allowance the fixtures, live and results tasks run
    on.

    It runs on `COVERED_KEYS`, the competitions this installation actually covers, and not on the
    two most of this file uses, because that is what decides whether the ceiling is in the story
    at all: a day of outage is about forty backoff windows, which at two competitions is 80
    requests and already under a ceiling of 120, so at that count the backoff alone would carry
    the whole assertion and the ceiling would refuse nothing. At six it is 240, and the ceiling is
    what holds a day to 120 - which the refusal count below is here to show, so that a future
    change to either guard cannot quietly leave this testing only the other one.

    Spending is read at its high-water mark rather than at the end, because the share is a share
    of a UTC DAY and twenty-four hours from 11:00 crosses a midnight: the budget the last reader
    sees is the second day's, and the first day's bill would go unexamined.

    The stub reaches the provider without billing anything, so a sweep that actually happened is
    charged here at what one costs the real provider: one request per covered competition.
    """
    budget = _budget(clock)
    provider = _metered(_failing(), budget)
    sweeps, refused_by_ceiling, refused_by_backoff, worst_day = 0, 0, 0, 0
    while clock.now - NOW < timedelta(hours=24):
        service = MatchDataService(MagicMock(), providers=[provider], cache=cache, now=clock(),
                                   keys=list(COVERED_KEYS))
        service.registry = MagicMock()
        asked_before = len(provider.asked)
        _, meta = service.next_fixtures()
        if len(provider.asked) > asked_before:
            sweeps += 1
            if budget.can_afford(COVERED_SWEEP_COST):
                budget.consume(COVERED_SWEEP_COST, reason=CALENDAR_BUDGET_REASON)
            worst_day = max(worst_day, budget.by_reason().get(CALENDAR_BUDGET_REASON, 0))
        elif any("share of the request allowance" in error for error in meta.errors):
            refused_by_ceiling += 1
        elif any("could not be read" in error for error in meta.errors):
            refused_by_backoff += 1
        clock.tick(60)
        _release_lock(cache)

    assert refused_by_backoff > 0, "the backoff thinned the readers"
    assert refused_by_ceiling > 0, \
        (f"the ceiling refused nothing: {sweeps} sweeps, and the heaviest day of them spent "
         f"{worst_day} of {CALENDAR_HEAD_DAILY_REQUEST_CEILING}, so the backoff alone kept the "
         f"day under the ceiling and this test is not exercising the ceiling it names")
    assert worst_day <= CALENDAR_HEAD_DAILY_REQUEST_CEILING, \
        f"{sweeps} sweeps of outage, and the heaviest day of them spent {worst_day}"
    assert budget.remaining() >= LIVESCORE_DAILY_LIMIT - CALENDAR_HEAD_DAILY_REQUEST_CEILING, \
        "a cosmetic empty-state feature must not eat the day the synchronisation runs on"


def test_the_admin_escape_hatch_reaches_the_calendar_backoff(cache, clock):
    """An operator who has fixed credentials must not wait out a forty-minute calendar backoff.

    `clear_cooldowns` is what the admin sync calls once credentials are corrected. The calendar
    backoff is keyed separately from the per-provider cool-downs precisely so that nothing else
    can clear it, which is exactly why this one has to.
    """
    provider = _failing()
    for _ in range(5):
        _sweep(cache, clock, provider)
        clock.tick(_backoff(cache)["wait_seconds"] + 1)
        _release_lock(cache)
    _sweep(cache, clock, provider)   # the sixth failure, and this one is not waited out
    _release_lock(cache)

    assert _backoff(cache)["wait_seconds"] == CALENDAR_HEAD_BACKOFF_CEILING_SECONDS
    service = _service(cache, clock, [provider])
    assert service._calendar_backoff_refusal() is not None

    service.clear_cooldowns()

    assert _backoff(cache) == {}
    assert service._calendar_backoff_refusal() is None, "the next reader may sweep again now"
    _release_lock(cache)
    healthy = _answering()
    answer, _ = _sweep(cache, clock, healthy)
    assert healthy.asked == KEYS and answer is not None
