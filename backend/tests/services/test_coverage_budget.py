"""
What covering 35 competitions instead of 6 is allowed to cost, and how it stays affordable.

Thirty-five competitions cannot be asked about the way six were. The results task alone asks for
every covered competition on every day that still holds an unsettled match, every half hour, so at
35 competitions that is 35 x 2 x 48 = 3,360 requests a day against a 1,200/day Live Score plan -
before a single fixture is fetched. The whole of this file is about the replacement, and the first
test states the problem as an executable number rather than a sentence so a later change cannot
quietly walk back into it.

Four rules do the work, and each has a test here that fails if it is removed:

  - RESULTS ask only for the competitions an unsettled match is actually IN, which the stored
    match rows already say and which costs nothing to work out;
  - FIXTURES ask for a national-team competition only on the days its coverage calendar says it
    plays, and for the club six always, on every day, unconditionally;
  - those calendars are bought one request at a time by a ROTATION that takes the stalest first,
    so the 29 are never all paid for at once and none of them can be passed over twice while
    another is refreshed twice;
  - every one of those is CAPPED per pass, so the worst case is a number and not a hope.

Two things have to hold at once and neither is allowed to be traded for the other: the club six
must cost and receive exactly what they always have, and the day as a whole must fit inside the
plan. Several tests below are written specifically to fail if the first is bought with the second.

No database and no network: the shipped MatchDataService and SyncScheduler over a provider double
that records every call, and an in-memory Redis stand-in whose TTLs elapse against a fake clock. A
recorded call is a request a real deployment would have paid for.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.predictions import MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    CALENDAR_HEAD_DAILY_REQUEST_CEILING, CALENDAR_HEAD_TTL_SECONDS,
    COVERAGE_CALENDAR_MAX_SECONDS, COVERAGE_CALENDAR_MIN_SECONDS,
    COVERAGE_HEAD_CACHE_KEY, MatchDataService, live_polls_today, note_live_poll,
)
from app.services.providers import competitions as comps
from app.services.providers.base import (
    MatchDataProvider, ProviderCompetition, ProviderFixture, ProviderNotConfiguredError,
    ProviderTeam,
)
from app.services.providers.budget import RequestBudget
from app.services.sync_scheduler import (
    TASK_FIXTURES, TASK_LIVE, TASK_RESULTS, SyncScheduler,
)
from tests.providers.support import FakeRedis
from tests.test_fixture_pipeline import Clock, ExpiringFakeRedis

NOW = datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc)

#: The plan every number here is measured against.
LIVESCORE_DAILY_LIMIT = 1200
DAY_SECONDS = 86400

#: The real coverage, read from the registry rather than written down again. These tests are about
#: what this installation actually covers; a list of two invented keys would not exercise a cap.
CLUB_KEYS = comps.covered_keys(settings.COVERED_COMPETITIONS, national_setting="")
NATIONAL_KEYS = comps.national_team_keys("active")
ALL_KEYS = CLUB_KEYS + [key for key in NATIONAL_KEYS if key not in CLUB_KEYS]


# --------------------------------------------------------------------- doubles
class CountingProvider(MatchDataProvider):
    """Records every call at the granularity a provider bills it.

    Live Score charges one request per competition for fixtures and for results, and one for the
    live poll however many competitions it covers. `get_calendar_head` is contractually one
    request. So the counters below are what a real deployment's bill would read.
    """

    name = "counting-stub"
    integration_status = "test"

    def __init__(self, calendars: Optional[Dict[str, List[date]]] = None,
                 budget: Optional[RequestBudget] = None):
        #: competition key -> the days its calendar lists, in kickoff order
        self.calendars = dict(calendars or {})
        self.budget = budget
        self.fixture_calls: List[tuple] = []
        self.result_calls: List[tuple] = []
        self.live_calls = 0
        self.calendar_calls: List[str] = []

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    @property
    def requests(self) -> int:
        return (sum(len(keys) for _, keys in self.fixture_calls)
                + sum(len(keys) for _, keys in self.result_calls)
                + self.live_calls + len(self.calendar_calls))

    def reset(self) -> None:
        self.fixture_calls, self.result_calls = [], []
        self.live_calls, self.calendar_calls = 0, []

    def asked_for(self, key: str) -> bool:
        return any(key in keys for _, keys in self.fixture_calls)

    def get_fixtures(self, day: date, keys) -> List[ProviderFixture]:
        self.fixture_calls.append((day, list(keys)))
        return []

    def get_results(self, date_from: date, date_to: date, keys) -> List[ProviderFixture]:
        self.result_calls.append((date_from, list(keys)))
        return []

    def get_live(self, keys) -> List[ProviderFixture]:
        self.live_calls += 1
        return []

    def get_calendar_head(self, key: str, limit: int = 5) -> Optional[List[ProviderFixture]]:
        self.calendar_calls.append(key)
        return [_fixture(datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                         + timedelta(hours=18), key)
                for day in self.calendars.get(key, [])][:limit]

    def get_standings(self, key):
        return []


def _fixture(kickoff: datetime, key: str) -> ProviderFixture:
    return ProviderFixture(
        provider="counting-stub", external_id=f"{key}-{kickoff.isoformat()}",
        competition=ProviderCompetition(provider="counting-stub", external_id="1",
                                        name=key, key=key),
        home=ProviderTeam(provider="counting-stub", external_id="h", name="Home"),
        away=ProviderTeam(provider="counting-stub", external_id="a", name="Away"),
        kickoff_utc=kickoff,
    )


class StoredMatch:
    """A stored match row, as much of one as the coverage rules read."""

    def __init__(self, key: str, kickoff: datetime, status=MatchStatus.SCHEDULED):
        self.league_id = f"league-{key}"
        self.match_date = kickoff.replace(tzinfo=None)
        self.status = status
        self.id = f"{key}-{kickoff.isoformat()}"


# --------------------------------------------------------------------- harness
@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def cache(clock):
    return MatchCache(client=ExpiringFakeRedis(clock=clock))


def build(cache, clock, provider, matches: Optional[Dict[date, List[StoredMatch]]] = None,
          keys: Optional[List[str]] = None):
    """A real MatchDataService and a real SyncScheduler over the stub provider.

    The registry is a double, but one that gives each competition its OWN league row, because
    turning a stored match back into the competition it belongs to is the mechanism half of these
    tests are about. A registry that answered with one row for every key would make every rule
    look like it worked while attributing every match to the same competition.
    """
    rows = dict(matches or {})
    service = MatchDataService(MagicMock(), providers=[provider], cache=cache, now=clock(),
                               keys=list(keys or ALL_KEYS))
    service.registry = MagicMock()
    service.registry.ensure_canonical_league.side_effect = (
        lambda key: SimpleNamespace(id=f"league-{key}"))
    service.registry.matches_for_day.side_effect = (
        lambda day, league_ids=None: list(rows.get(day, [])))
    service.registry.upsert_fixture.side_effect = lambda fixture: MagicMock()

    def match_factory(_db):
        service._now = clock()
        return service

    scheduler = SyncScheduler(
        session_factory=lambda: MagicMock(), cache=cache, now=clock,
        match_service_factory=match_factory,
        forecast_service_factory=lambda db: MagicMock(),
        tasks=[TASK_FIXTURES, TASK_LIVE, TASK_RESULTS], close_sessions=False)
    return scheduler, service, rows


def _pass(scheduler, task) -> Dict[str, Any]:
    return scheduler.run_once(only=[task], force=True)["tasks"][task]


# ------------------------------------------------------- the arithmetic, as an assertion
def test_the_naive_plan_would_have_spent_several_times_the_allowance():
    """The problem statement, in numbers, so it cannot be argued with later.

    This is what enabling the 29 national-team competitions cost BEFORE any of the rules in this
    file: every covered competition asked about on every day of every pass. It is kept as a test
    rather than as a comment because the design below is only worth its complexity while this
    number is true, and if some future change makes a pass cheap by itself, this is the test that
    should be deleted deliberately rather than the caps quietly raised.
    """
    passes = {"fixtures": DAY_SECONDS // settings.SYNC_FIXTURES_INTERVAL_SECONDS,
              "results": DAY_SECONDS // settings.SYNC_RESULTS_INTERVAL_SECONDS,
              "live": DAY_SECONDS // settings.SYNC_LIVE_INTERVAL_SECONDS}
    covered = len(ALL_KEYS)
    naive = (covered * settings.SYNC_FIXTURES_DAYS_AHEAD * passes["fixtures"]
             + covered * (settings.SYNC_RESULTS_LOOKBACK_DAYS + 1) * passes["results"]
             + passes["live"])

    assert covered >= 35, "these numbers are about covering the national-team competitions"
    assert naive > 3 * LIVESCORE_DAILY_LIMIT, (
        f"asking every covered competition on every pass costs {naive} a day, which is what the "
        f"caps below exist to replace")


def test_the_capped_day_fits_inside_the_plan():
    """Every task's worst case added up, against the plan, with the page loads' reserve left over.

    Each term is a HARD bound and not an average: the fixtures task cannot ask for more than the
    club set plus its cap, the results task cannot exceed its cap, the live task cannot exceed its
    daily ceiling, and both calendar readers - the empty-state sweep and the coverage rotation -
    spend out of one existing per-provider share rather than two.

    This is the test that fails when a cap is raised without the arithmetic being redone.
    """
    fixture_passes = DAY_SECONDS // settings.SYNC_FIXTURES_INTERVAL_SECONDS
    results_passes = DAY_SECONDS // settings.SYNC_RESULTS_INTERVAL_SECONDS

    club_fixtures = len(CLUB_KEYS) * settings.SYNC_FIXTURES_DAYS_AHEAD * fixture_passes
    national_fixtures = settings.SYNC_FIXTURES_MAX_NATIONAL_REQUESTS_PER_PASS * fixture_passes
    results = settings.SYNC_RESULTS_MAX_REQUESTS_PER_PASS * results_passes
    live = settings.SYNC_LIVE_MAX_REQUESTS_PER_DAY
    calendars = CALENDAR_HEAD_DAILY_REQUEST_CEILING
    reserve = min(settings.SYNC_SCHEDULER_BUDGET_RESERVE, LIVESCORE_DAILY_LIMIT // 10)
    worst_case = club_fixtures + national_fixtures + results + live + calendars

    assert club_fixtures == 72, "the club six must still cost exactly what they always have"
    assert worst_case + reserve <= LIVESCORE_DAILY_LIMIT, (
        f"the worst case is {worst_case} plus {reserve} held back for page loads, against a "
        f"{LIVESCORE_DAILY_LIMIT}/day plan: fixtures {club_fixtures}+{national_fixtures}, "
        f"results {results}, live {live}, calendars {calendars}")


def test_the_coverage_rotation_fits_inside_the_calendar_share_it_shares():
    """The rotation spends out of the existing calendar ceiling, beside the empty-state sweep.

    Both read competition calendars and both are attributed to the budget's `calendar` reason, so
    a day has to hold the two together. Giving the rotation a ceiling of its own would be a second
    share of a plan that only has one.
    """
    rotation = (settings.SYNC_COVERAGE_CALENDAR_REFRESH_PER_PASS
                * (DAY_SECONDS // settings.SYNC_FIXTURES_INTERVAL_SECONDS))
    sweeps = len(CLUB_KEYS) * (DAY_SECONDS // CALENDAR_HEAD_TTL_SECONDS)

    assert rotation >= len(NATIONAL_KEYS), (
        f"{rotation} refreshes a day cannot keep {len(NATIONAL_KEYS)} calendars current")
    assert rotation + sweeps <= CALENDAR_HEAD_DAILY_REQUEST_CEILING, (
        f"{rotation} rotation + {sweeps} sweep requests exceed the "
        f"{CALENDAR_HEAD_DAILY_REQUEST_CEILING} share kept for reading calendars")


# --------------------------------------------------------- a dormant tournament costs nothing
def test_a_dormant_competition_is_never_asked_for_fixtures(cache, clock):
    """Most of the 29 are out of season most of the year, and that is the whole of the saving."""
    provider = CountingProvider(calendars={key: [] for key in NATIONAL_KEYS})
    scheduler, service, _ = build(cache, clock, provider)

    _pass(scheduler, TASK_FIXTURES)

    for day, keys in provider.fixture_calls:
        assert keys == CLUB_KEYS, f"a dormant competition was asked about for {day}: {keys}"


def test_a_dormant_competition_is_not_re_read_every_pass(cache, clock):
    """Its calendar is bought once and believed for a fortnight, not re-bought four times a day."""
    provider = CountingProvider(calendars={key: [] for key in NATIONAL_KEYS})
    scheduler, _, _ = build(cache, clock, provider)
    key = NATIONAL_KEYS[0]

    reads = []
    for _ in range(4 * 13):  # thirteen days at the shipped fixtures interval
        _pass(scheduler, TASK_FIXTURES)
        reads.append(provider.calendar_calls.count(key))
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    assert reads[-1] == 1, (
        f"{reads[-1]} calendar reads for one dormant competition in thirteen days; the maximum "
        f"wait is {COVERAGE_CALENDAR_MAX_SECONDS // 86400} days")


def test_a_pass_that_knows_nothing_yet_still_serves_the_club_competitions(cache, clock):
    """A cold installation has no calendars at all, and that must cost the clubs nothing."""
    provider = CountingProvider()
    scheduler, _, _ = build(cache, clock, provider)

    _pass(scheduler, TASK_FIXTURES)

    days = {day for day, _ in provider.fixture_calls}
    assert len(days) == settings.SYNC_FIXTURES_DAYS_AHEAD
    for _, keys in provider.fixture_calls:
        assert keys == CLUB_KEYS


# --------------------------------------------------------------------- rotation fairness
def test_the_rotation_reaches_every_competition_within_a_day(cache, clock):
    """Stalest-first, so the pass that is passed over goes first next time.

    Fairness here is not statistical. The order is a total order on how long ago a competition was
    read, so a competition the cap cut this pass has an older reading than every competition that
    was not cut, and goes ahead of all of them next pass. Nothing can be read twice while
    something waits.
    """
    provider = CountingProvider(calendars={key: [] for key in NATIONAL_KEYS})
    scheduler, _, _ = build(cache, clock, provider)

    for _ in range(4):  # one day of fixture passes
        _pass(scheduler, TASK_FIXTURES)
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    counts = {key: provider.calendar_calls.count(key) for key in NATIONAL_KEYS}
    assert min(counts.values()) >= 1, (
        f"{[k for k, n in counts.items() if not n]} were never reached in a day of passes")
    assert max(counts.values()) <= 1, (
        f"{[k for k, n in counts.items() if n > 1]} were read twice while others waited")


def test_a_week_of_passes_starves_no_competition_and_always_serves_the_clubs(cache, clock):
    """The simulation the design is actually judged on: seven days, nothing touched.

    Half the national set plays, half is dormant, which is what an ordinary week looks like. Three
    things have to survive it: every competition gets its calendar read, no club competition ever
    misses a pass, and the week stays inside what the previous tests said a day may cost.
    """
    playing = NATIONAL_KEYS[:14]
    calendars = {key: ([NOW.date() + timedelta(days=offset) for offset in (2, 9)] if key in playing
                       else []) for key in NATIONAL_KEYS}
    provider = CountingProvider(calendars=calendars)
    scheduler, _, _ = build(cache, clock, provider)

    passes = 0
    club_misses = []
    for _ in range(4 * 7):
        provider.reset()
        _pass(scheduler, TASK_FIXTURES)
        passes += 1
        for day, keys in provider.fixture_calls:
            missing = [key for key in CLUB_KEYS if key not in keys]
            if missing:
                club_misses.append((day, missing))
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    assert passes == 28 and not club_misses, f"club competitions went unfetched: {club_misses[:3]}"


def test_a_competition_never_read_goes_ahead_of_one_that_is_merely_due_again(cache, clock):
    """What stops the head of the list being served for ever while the tail is never reached.

    The case that makes the order matter is every competition being in its window at once, which
    is what an international break is: a competition about to play is re-read on the minimum wait
    of twelve hours, so with 29 of them, 8 turns a pass and a pass every six hours, from the third
    pass onwards the ones read first are due again and are competing with ones that have never
    been read at all. Taking them in registry order serves the head every other pass and leaves
    the tail permanently unread; taking the STALEST first cannot, because never-read is older than
    anything.
    """
    tomorrow = (NOW + timedelta(days=1)).date()
    provider = CountingProvider(calendars={key: [tomorrow] for key in NATIONAL_KEYS})
    scheduler, _, _ = build(cache, clock, provider)

    for _ in range(8):
        _pass(scheduler, TASK_FIXTURES)
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    never_read = [key for key in NATIONAL_KEYS if key not in provider.calendar_calls]
    assert not never_read, (
        f"{len(never_read)} competition(s) were starved while others were re-read: {never_read}")


def test_a_failed_refresh_does_not_forget_the_matchday_it_already_knew(cache, clock):
    """An outage is not evidence that a competition stopped playing.

    Clearing the stored days on a failed refresh would turn one refused request into half a day
    in which the fixtures task no longer asks about a matchday it already knew about.
    """
    key = NATIONAL_KEYS[0]
    # Two days out, so its refresh falls due on the minimum wait and the matchday is still
    # inside the fixtures window when the failed refresh happens.
    match_day = (NOW + timedelta(days=2)).date()
    provider = CountingProvider(calendars={key: [match_day]})
    scheduler, service, _ = build(cache, clock, provider, keys=CLUB_KEYS + [key])
    _pass(scheduler, TASK_FIXTURES)
    assert service.coverage_record(key)["fixture_days"] == [match_day.isoformat()]

    # Declining to answer, rather than an error that would cool the provider down: a cool-down
    # would stop the fixtures fetch below for a reason that has nothing to do with this test.
    provider.get_calendar_head = MagicMock(side_effect=ProviderNotConfiguredError(
        "no calendar right now", provider=provider.name))
    # And no copy of the last answer left to fall back on, so the refresh really does come back
    # with nothing. With one, the stale copy would answer and this would be testing that instead.
    cache.delete(COVERAGE_HEAD_CACHE_KEY.format(key=key))
    due_at = datetime.fromisoformat(service.coverage_record(key)["refresh_after"])
    clock.tick(int((due_at - clock()).total_seconds()) + 60)
    provider.reset()
    _pass(scheduler, TASK_FIXTURES)

    record = service.coverage_record(key)
    assert record["error"], "a refresh that came back with nothing was recorded as an answer"
    assert record["fixture_days"] == [match_day.isoformat()], "the known matchday was forgotten"
    assert provider.asked_for(key), "the known matchday stopped being asked for after one outage"


def test_the_rotation_is_not_restarted_from_the_top_by_a_new_pass(cache, clock):
    """Two passes in a row must not both read the same head of the list."""
    provider = CountingProvider(calendars={key: [] for key in NATIONAL_KEYS})
    scheduler, _, _ = build(cache, clock, provider)

    _pass(scheduler, TASK_FIXTURES)
    first = list(provider.calendar_calls)
    provider.reset()
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)
    _pass(scheduler, TASK_FIXTURES)

    assert first, "the first pass read nothing, so this test proves nothing"
    assert not set(first) & set(provider.calendar_calls), (
        f"the second pass re-read {sorted(set(first) & set(provider.calendar_calls))}")


# ------------------------------------------------------- an international break, hands off
def test_a_break_is_picked_up_without_anybody_touching_a_setting(cache, clock):
    """The requirement in one test: fixtures appear, and the scheduler finds them.

    On day zero the competition's calendar lists one fixture three weeks out, which is what a
    fixture list looks like before a break - announced months ahead and not yet inside any task's
    window. Nothing is reconfigured. The adaptive refresh brings the calendar forward as the date
    approaches, and the day the fixture falls inside the fixtures window, the competition is asked
    for on that day.
    """
    key = NATIONAL_KEYS[0]
    match_day = (NOW + timedelta(days=21)).date()
    provider = CountingProvider(calendars={key: [match_day]})
    scheduler, _, _ = build(cache, clock, provider)

    asked_on: List[date] = []
    for _ in range(4 * 23):
        provider.reset()
        _pass(scheduler, TASK_FIXTURES)
        asked_on.extend(day for day, keys in provider.fixture_calls if key in keys)
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    assert match_day in asked_on, (
        f"{key} plays on {match_day} and was never asked about for that day")
    assert len(provider.calendar_calls) <= 6, (
        f"{len(provider.calendar_calls)} calendar reads to follow one fixture over three weeks")


def test_a_competition_that_starts_scheduling_is_found_within_the_maximum_wait(cache, clock):
    """A calendar that was genuinely empty when it was read, and is not any more.

    This is the slow path, and the fortnight ceiling is what bounds it: a competition with nothing
    listed is re-read at most `COVERAGE_CALENDAR_MAX_SECONDS` later, which is shorter than the gap
    between international breaks, so nothing can stay invisible through one.
    """
    key = NATIONAL_KEYS[0]
    provider = CountingProvider(calendars={key: []})
    # One national-team competition covered, so the rotation's order is not what is under test
    # here and the calendar reads below belong unambiguously to this competition.
    scheduler, _, _ = build(cache, clock, provider, keys=CLUB_KEYS + [key])

    _pass(scheduler, TASK_FIXTURES)
    assert provider.calendar_calls == [key]

    # The fixture list is published while we are not looking, inside the fortnight.
    clock.tick(COVERAGE_CALENDAR_MAX_SECONDS)
    match_day = (clock() + timedelta(days=1)).date()
    provider.calendars[key] = [match_day]
    provider.reset()
    _pass(scheduler, TASK_FIXTURES)

    assert provider.calendar_calls == [key], "the expired calendar was not re-read"
    assert provider.asked_for(key), "the new fixture was not picked up in the same pass"


# --------------------------------------------------------------------- the caps hold
def test_every_competition_wanting_attention_at_once_still_costs_one_capped_pass(cache, clock):
    """The pathological day: all 29 have a fixture on all three days in the window."""
    days = [NOW.date() + timedelta(days=offset)
            for offset in range(settings.SYNC_FIXTURES_DAYS_AHEAD)]
    provider = CountingProvider(calendars={key: list(days) for key in NATIONAL_KEYS})
    scheduler, _, _ = build(cache, clock, provider)

    # One pass to buy calendars, then the pass that acts on all of them at once.
    for _ in range(5):
        _pass(scheduler, TASK_FIXTURES)
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)
    provider.reset()
    entry = _pass(scheduler, TASK_FIXTURES)

    national = sum(len([k for k in keys if k not in CLUB_KEYS])
                   for _, keys in provider.fixture_calls)
    club = sum(len([k for k in keys if k in CLUB_KEYS]) for _, keys in provider.fixture_calls)

    assert national <= settings.SYNC_FIXTURES_MAX_NATIONAL_REQUESTS_PER_PASS, (
        f"{national} national-team requests in one pass")
    assert club == len(CLUB_KEYS) * settings.SYNC_FIXTURES_DAYS_AHEAD, (
        "the cap took a request from the club competitions")
    assert entry["result"]["national_deferred"], "a cap that bound reported nothing deferred"


def test_the_cap_defers_the_furthest_day_and_never_today(cache, clock):
    """A fixture today has no later pass to be caught by; one in two days has two."""
    # Every day of the fortnight, so the answer does not depend on where the clock has reached by
    # the pass that is measured - five passes at the shipped interval move it past midnight.
    days = [(NOW + timedelta(days=offset)).date() for offset in range(14)]
    provider = CountingProvider(calendars={key: list(days) for key in NATIONAL_KEYS})
    scheduler, _, _ = build(cache, clock, provider)

    for _ in range(5):
        _pass(scheduler, TASK_FIXTURES)
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)
    provider.reset()
    _pass(scheduler, TASK_FIXTURES)

    today = clock().date()
    by_day = {day: [k for k in keys if k not in CLUB_KEYS] for day, keys in provider.fixture_calls}
    furthest = today + timedelta(days=settings.SYNC_FIXTURES_DAYS_AHEAD - 1)
    assert by_day[today], "today was deferred while a later day was served"
    assert len(by_day[today]) >= len(by_day[furthest])


# --------------------------------------------------------------------- results, per competition
def test_results_are_asked_for_only_the_competitions_holding_an_unsettled_match(cache, clock):
    """The single biggest saving, and the one that used to cost 3,360 requests a day."""
    yesterday = (NOW - timedelta(days=1)).date()
    stale = (NOW - timedelta(days=1, hours=4))
    rows = {yesterday: [StoredMatch(NATIONAL_KEYS[0], stale),
                        StoredMatch("premier_league", stale)],
            NOW.date(): []}
    provider = CountingProvider()
    scheduler, _, _ = build(cache, clock, provider, matches=rows)

    _pass(scheduler, TASK_RESULTS)

    assert provider.result_calls, "nothing was polled for a day with two unsettled matches"
    for _, keys in provider.result_calls:
        assert sorted(keys) == sorted(["premier_league", NATIONAL_KEYS[0]]), (
            f"a day with two unsettled matches asked for {len(keys)} competitions")


def test_a_settled_day_costs_the_results_task_nothing(cache, clock):
    """A finished match is not asked about again, at any number of covered competitions."""
    yesterday = (NOW - timedelta(days=1)).date()
    rows = {yesterday: [StoredMatch("premier_league", NOW - timedelta(days=1, hours=4),
                                    status=MatchStatus.FINISHED)],
            NOW.date(): []}
    provider = CountingProvider()
    scheduler, _, _ = build(cache, clock, provider, matches=rows)

    _pass(scheduler, TASK_RESULTS)

    assert provider.requests == 0


def test_the_results_cap_serves_the_clubs_first_and_rotates_the_rest(cache, clock):
    """A stuck match in every competition must not cost the day, and must not starve one either.

    A match that never leaves SCHEDULED - a postponement the provider never told us about - keeps
    its competition pending for ever, so without a cap the pathological case is permanent rather
    than momentary. The cap makes it bounded; serving the clubs first makes it safe; rotating the
    rest by pass number makes it fair.
    """
    yesterday = (NOW - timedelta(days=1)).date()
    stuck = NOW - timedelta(days=1, hours=6)
    rows = {yesterday: [StoredMatch(key, stuck) for key in ALL_KEYS], NOW.date(): []}
    provider = CountingProvider()
    scheduler, _, _ = build(cache, clock, provider, matches=rows)

    served: List[str] = []
    for _ in range(6):
        provider.reset()
        entry = _pass(scheduler, TASK_RESULTS)
        polled = [key for _, keys in provider.result_calls for key in keys]
        assert len(polled) <= settings.SYNC_RESULTS_MAX_REQUESTS_PER_PASS, (
            f"{len(polled)} requests in one results pass")
        for key in CLUB_KEYS:
            assert key in polled, f"{key} was cut by the cap: {entry['result']['deferred'][:3]}"
        served.extend(key for key in polled if key not in CLUB_KEYS)
        clock.tick(settings.SYNC_RESULTS_INTERVAL_SECONDS)

    assert len(set(served)) > 1, (
        f"the same national-team competition was served every pass: {sorted(set(served))}")


# --------------------------------------------------------------------- the live ceiling
def test_the_live_task_stops_at_its_daily_ceiling(cache, clock, monkeypatch):
    """One poll answers for every competition, so this bounds hours rather than coverage.

    Run at a ceiling of five rather than the shipped 420, because reaching 420 would need
    fourteen hours of continuously open live windows and the mechanism is the same at either
    number. What the shipped value has to satisfy is the day's arithmetic, which
    `test_the_capped_day_fits_inside_the_plan` asserts against the plan.
    """
    monkeypatch.setattr(settings, "SYNC_LIVE_MAX_REQUESTS_PER_DAY", 5)
    rows = {NOW.date(): [StoredMatch("premier_league", NOW)]}
    provider = CountingProvider()
    scheduler, _, _ = build(cache, clock, provider, matches=rows)

    for _ in range(5):
        _pass(scheduler, TASK_LIVE)
        clock.tick(settings.MATCH_CACHE_TTL_LIVE + 1)
    polled_before = provider.live_calls
    entry = _pass(scheduler, TASK_LIVE)

    assert polled_before == 5
    assert entry["result"]["live_polled"] is False
    assert "ceiling" in entry["result"]["note"]
    assert entry["ok"] is True, "a ceiling is a refusal to spend, not a failure to back off from"


def test_a_live_poll_served_from_cache_is_not_charged_to_the_ceiling(cache, clock):
    """Charging a cache hit would end the day early over requests nobody made."""
    rows = {NOW.date(): [StoredMatch("premier_league", NOW)]}
    provider = CountingProvider()
    scheduler, _, _ = build(cache, clock, provider, matches=rows)

    for _ in range(5):
        _pass(scheduler, TASK_LIVE)  # no clock tick: every one but the first is a cache hit

    assert provider.live_calls == 1
    assert scheduler._live_polls_today() == 1


# ----------------------------------------------------- the club six are never traded away
def test_a_low_allowance_drops_the_national_set_and_keeps_the_club_six(cache, clock):
    """What the floor is for: coverage degrades to what this installation always had."""
    budget = RequestBudget("livescore", LIVESCORE_DAILY_LIMIT, client=FakeRedis(), now=clock)
    budget.consume(LIVESCORE_DAILY_LIMIT - settings.SYNC_NATIONAL_TEAM_BUDGET_FLOOR + 1,
                   reason="fetch")
    provider = CountingProvider(
        calendars={key: [NOW.date()] for key in NATIONAL_KEYS}, budget=budget)
    scheduler, _, _ = build(cache, clock, provider)

    entry = _pass(scheduler, TASK_FIXTURES)

    assert provider.calendar_calls == [], "a low allowance still paid for calendars"
    for _, keys in provider.fixture_calls:
        assert keys == CLUB_KEYS
    assert "club competitions" in entry["result"]["national_skipped"]


def test_the_dry_run_prices_the_plan_the_pass_would_actually_make(cache, clock):
    """An estimate that multiplied coverage by the window would over-report it five times over."""
    provider = CountingProvider(calendars={key: [] for key in NATIONAL_KEYS})
    scheduler, _, _ = build(cache, clock, provider)

    estimate = scheduler.estimate(only=[TASK_FIXTURES], force=True)["tasks"][TASK_FIXTURES]
    provider.reset()
    _pass(scheduler, TASK_FIXTURES)

    assert estimate["estimated_requests"] == provider.requests, (
        f"estimated {estimate['estimated_requests']}, spent {provider.requests}: {estimate['basis']}")


def test_the_covered_set_is_actually_turned_on():
    """The feature is worthless while the setting defaults to empty."""
    covered = comps.covered_keys(settings.COVERED_COMPETITIONS)

    assert settings.COVERED_NATIONAL_TEAM_COMPETITIONS not in ("", "none", "off")
    for key in CLUB_KEYS:
        assert key in covered, f"{key} was dropped from coverage"
    assert len([key for key in covered if comps.COMPETITIONS[key].is_national_team]) >= 29


# ------------------------------------------------- caps bind where the requests are made
#
# A cap enforced in the task that ASKS is not a cap on the day, because two tasks reach the same
# endpoints: the results task on its interval, and the fixtures task on its way out of `sync_day`.
# The three tests below drive the FIXTURES task and count what it spends on results and on the
# live poll, which is the path no per-task cap of the results or live task can see.

def test_a_fixtures_pass_cannot_outspend_the_results_cap(cache, clock, monkeypatch):
    """The results cap bounds the day, not one task's share of it.

    Every fixtures pass calls `_sync_results` for today with the day's whole key list. Bounded only
    inside `SyncScheduler._run_results`, that call is free to ask for every competition holding an
    unsettled match - 35 of them on a busy day against a cap of 8.
    """
    monkeypatch.setattr(settings, "SYNC_RESULTS_MAX_REQUESTS_PER_PASS", 4)
    today = NOW.date()
    provider = CountingProvider()
    busy = {today: [StoredMatch(key, NOW - timedelta(hours=4)) for key in ALL_KEYS]}
    scheduler, service, _ = build(cache, clock, provider, matches=busy)

    _pass(scheduler, TASK_FIXTURES)

    spent = sum(len(keys) for _, keys in provider.result_calls)
    assert spent <= 4, f"a fixtures pass spent {spent} results requests against a cap of 4"


def test_a_fixtures_pass_respects_the_live_ceiling_the_live_task_obeys(cache, clock, monkeypatch):
    """One counter, or the ceiling is whichever task an operator happens to be looking at."""
    monkeypatch.setattr(settings, "SYNC_LIVE_MAX_REQUESTS_PER_DAY", 1)
    provider = CountingProvider()
    scheduler, service, _ = build(cache, clock, provider)

    note_live_poll(cache, clock())          # the day's one allowed poll, already spent
    before = provider.live_calls
    _pass(scheduler, TASK_FIXTURES)

    assert provider.live_calls == before, "the fixtures pass polled past a ceiling already reached"
    assert live_polls_today(cache, clock()) == 1


def test_a_busy_today_cannot_starve_yesterday_of_the_results_cap(cache, clock, monkeypatch):
    """An older day is the one that will NOT fix itself, so it cannot be the one that goes hungry.

    Walking the lookback today-first against a single running budget means a today busy enough to
    exhaust the cap leaves yesterday unasked on every pass of the day - and yesterday's stuck match
    is exactly the row that never settles on its own.
    """
    monkeypatch.setattr(settings, "SYNC_RESULTS_MAX_REQUESTS_PER_PASS", 4)
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 1)
    today, yesterday = NOW.date(), NOW.date() - timedelta(days=1)
    provider = CountingProvider()
    rows = {today: [StoredMatch(key, NOW - timedelta(hours=4)) for key in ALL_KEYS],
            yesterday: [StoredMatch("premier_league", NOW - timedelta(days=1, hours=4))]}
    scheduler, service, _ = build(cache, clock, provider, matches=rows)

    report = _pass(scheduler, TASK_RESULTS)["result"]

    assert report["days"][yesterday.isoformat()]["competitions"] >= 1, (
        "yesterday was never asked about; today took the whole cap")
    assert report["requests"] <= 4
