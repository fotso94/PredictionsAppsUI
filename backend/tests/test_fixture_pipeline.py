"""
What the fixture pipeline says when it is handed nothing.

On 2026-09-21 the store held 48 finished matches and one stuck live one, and no provider had
offered a fixture for today or any day after it - while `sync:task:fixtures` recorded three
consecutive runs with `source: "provider"`, `errors: []` and no other sign of trouble. The provider
was answering. It was answering with an empty list, because none of the six covered competitions
had a match inside the three days the task looks at. Nothing in the recorded result could tell that apart from a full
matchday, which is how a pipeline that stored nothing for three days went on looking healthy.

So these tests are about the reporting, not the football. A pass says how many fixtures it was
offered and how many of them reached the database; an empty answer stays a success - a league
between rounds genuinely has no match this week - but it is counted, and the run of empty passes
is carried forward. At the provider end, an empty window says whether the competition has no
calendar at all or simply no round before the window closes: every covered league that was probed
had a calendar, the earliest fixture in any of them on 9 October, and the two cases want opposite
responses.

The tests below exist mostly to keep that reporting able to see what it is for. Four things have
to stay true, and each is easy to break by accident:

  - only the FORWARD counters answer the forward question. One `sync_day` runs three ingests - the
    forward fixtures list, then results, then live scores - through one shared pair, and an
    unsettled match dated today that has already kicked off - or kicks off within the next
    quarter of an hour - makes `_sync_results` (at least 150 minutes after kickoff) or `_sync_live`
    (from 15 minutes before kickoff to 150 after) hand back a day of fixtures on a pass offered
    nothing to come;
  - a stale cached copy is not the provider answering today;
  - a pass where every provider raised is not a quiet calendar;
  - a pass covers `SYNC_FIXTURES_DAYS_AHEAD` days, three in production, and the states above are
    per pass rather than per day. A suite that only ever runs one day never sees how one day's
    answer combines with another's, and one that pins `matches_for_day` to `[]` disables both
    `_pending_results_exist` and `_live_window_open`, which is the only state in which the first
    point can fail. Neither is fixed here: the day count is set per test through the `days_ahead`
    fixture and the stored rows are a `build(...)` argument.

No database and no network: a fake clock, an in-memory Redis stand-in that honours TTLs against it,
a stub provider that records every call, and a mocked registry.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.config import settings
from app.models.predictions import MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.providers.base import (
    MatchDataProvider, ProviderCompetition, ProviderFixture, ProviderTeam,
    ProviderUnavailableError,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.sync_scheduler import TASK_FIXTURES, SyncScheduler
from tests.providers.support import FakeRedis, json_response, make_transport

NOW = datetime(2026, 9, 21, 11, 0, tzinfo=timezone.utc)
KEYS = ["premier_league"]
LOGGER = "app.services.providers.livescore_api"


# --------------------------------------------------------------------- doubles
class ExpiringFakeRedis(FakeRedis):
    """FakeRedis whose TTLs actually elapse against the fake clock.

    Expiry is load-bearing here: without it the second pass of a test would be served the first
    pass's cached payload and never reach the stub provider at all, so a test about what the
    provider returned would quietly stop asking it anything.
    """

    def __init__(self, clock=None):
        super().__init__()
        self.clock = clock
        self.expires: Dict[str, datetime] = {}

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
        return [k for k in list(self.store) if k.startswith((match or "*").rstrip("*"))]


class Clock:
    def __init__(self, start: datetime = NOW):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def tick(self, seconds: int) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def _fixture(kickoff: datetime, external_id: str) -> ProviderFixture:
    return ProviderFixture(
        provider="stub", external_id=external_id,
        competition=ProviderCompetition(provider="stub", external_id="1", name="Premier League",
                                        key="premier_league"),
        home=ProviderTeam(provider="stub", external_id="h", name="Home"),
        away=ProviderTeam(provider="stub", external_id="a", name="Away"),
        kickoff_utc=kickoff,
    )


class StubDataProvider(MatchDataProvider):
    """Answers each endpoint with whatever the test queued, and records that it was asked.

    The three endpoints are queued separately on purpose: the defect these tests are about is the
    forward fixtures list being empty while `results` or `live` hands back a full day, so a double
    that answered all three from one list could not express the case at all.
    """

    name = "stub"
    integration_status = "test"

    def __init__(self, fixtures: Optional[List[ProviderFixture]] = None,
                 results: Optional[List[ProviderFixture]] = None,
                 live: Optional[List[ProviderFixture]] = None,
                 fail: Optional[Exception] = None,
                 fail_days: Optional[List[date]] = None):
        self.fixtures = list(fixtures or [])
        self.results = list(results or [])
        self.live = list(live or [])
        #: Raised instead of answering, to drive the chain into its stale / no-answer paths.
        self.fail = fail
        #: Days whose fixtures call raises while the rest answer. A multi-day pass where some days
        #: are answered and others are not is a state `fail` alone cannot express.
        self.fail_days = set(fail_days or [])
        self.calls: List[str] = []
        self.budget = None

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def get_fixtures(self, day: date, keys) -> List[ProviderFixture]:
        self.calls.append(f"fixtures:{day.isoformat()}")
        if self.fail is not None or day in self.fail_days:
            raise self.fail or ProviderUnavailableError("upstream is down", provider="stub")
        return list(self.fixtures)

    def get_live(self, keys) -> List[ProviderFixture]:
        self.calls.append("live")
        if self.fail is not None:
            raise self.fail
        return list(self.live)

    def get_results(self, date_from: date, date_to: date, keys) -> List[ProviderFixture]:
        self.calls.append(f"results:{date_from.isoformat()}")
        if self.fail is not None:
            raise self.fail
        return list(self.results)

    def get_standings(self, key):
        return []


def _stored_match(kickoff: datetime, status: MatchStatus = MatchStatus.SCHEDULED):
    """A row as `MatchRegistry.matches_for_day` would return it: naive UTC, like the column."""
    match = MagicMock()
    match.status = status
    match.match_date = kickoff.replace(tzinfo=None)
    return match


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def cache(clock):
    return MatchCache(client=ExpiringFakeRedis(clock=clock))


@pytest.fixture(autouse=True)
def days_ahead(monkeypatch):
    """How many days one pass covers. One by default, so a count in an assertion is followable.

    Returned as a setter, not fixed: production runs three, the pass-level states are decided
    across all of them, and a suite that only ever runs one day cannot tell a rule that is per
    pass from one that is per day. Call `days_ahead(3)` before `build`.
    """
    def _set(days: int) -> int:
        monkeypatch.setattr(settings, "SYNC_FIXTURES_DAYS_AHEAD", days)
        return days

    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 0)
    _set(1)
    return _set


def build(cache, clock, provider: StubDataProvider, refuse: Optional[List[str]] = None,
          stored: Optional[List[Any]] = None, seed: Optional[datetime] = None,
          crash: Optional[Exception] = None):
    """The shipped scheduler and the shipped MatchDataService; only the provider and DB are doubles.

    `refuse` names the fixtures the registry cannot tell apart from a match it already holds, which
    is the one case where a fixture is offered and deliberately not stored.

    `stored` is what the database already holds for the day being synced. It is what decides
    whether `_sync_results` and `_sync_live` make a call at all, so a test that leaves it empty
    cannot reach the case where those two ingests hand back fixtures the forward list did not -
    which is the case the forward counters exist for. Pass it whenever that case is the subject.

    `seed` stands in for the newest row written ahead of its kickoff, the value the task falls back
    to when no stored summary carries a sighting.

    `crash` makes `sync_day` raise something the task does not catch - a failing commit, a
    malformed payload - which is how a pass ends up recording no summary at all.
    """
    refused = set(refuse or [])
    db = MagicMock()
    service = MatchDataService(db, providers=[provider], cache=cache, now=clock(), keys=list(KEYS))
    service.registry = MagicMock()
    service.registry.ensure_canonical_league.return_value = MagicMock(id="league-1")
    service.registry.matches_for_day.return_value = list(stored or [])
    service.registry.upsert_fixture.side_effect = \
        lambda fixture: None if fixture.external_id in refused else MagicMock()
    if seed is not None:
        service.last_forward_fixture_stored_at = lambda: seed
    if crash is not None:
        service.sync_day = MagicMock(side_effect=crash)

    def match_factory(_db):
        service._now = clock()
        return service

    scheduler = SyncScheduler(session_factory=lambda: MagicMock(), cache=cache, now=clock,
                              match_service_factory=match_factory,
                              forecast_service_factory=lambda db: MagicMock(),
                              tasks=[TASK_FIXTURES], close_sessions=False)
    return scheduler


def run(scheduler) -> Dict[str, Any]:
    return scheduler.run_once(only=[TASK_FIXTURES], force=True)["tasks"][TASK_FIXTURES]


# --------------------------------------------------------------------- the pass reports what it got
def test_a_pass_that_was_offered_nothing_says_so_instead_of_only_saying_it_succeeded(cache, clock):
    """The exact shape of the 2026-09-21 state: provider reached, no errors, nothing stored."""
    scheduler = build(cache, clock, StubDataProvider(fixtures=[]))

    outcome = run(scheduler)

    assert outcome["ok"] is True, "an empty answer is honest; it must not back the task off"
    result = outcome["result"]
    assert result["days"]["2026-09-21"]["source"] == "provider"
    assert result["days"]["2026-09-21"]["errors"] == []
    assert (result["fixtures_seen"], result["fixtures_stored"]) == (0, 0)
    assert (result["forward_seen"], result["forward_stored"]) == (0, 0)
    assert result["forward_answer"] == "empty"
    assert result["empty_passes"] == 1
    assert result["unanswered_passes"] == 0, "the provider answered; it simply had nothing"
    assert result["last_seen_at"] is None
    assert result["last_seen_basis"] is None, "nothing recorded and nothing to reconstruct"


def test_a_pass_that_was_offered_a_matchday_reports_both_counts(cache, clock):
    provider = StubDataProvider(fixtures=[_fixture(NOW + timedelta(hours=4), "f1"),
                                          _fixture(NOW + timedelta(hours=6), "f2")])
    scheduler = build(cache, clock, provider)

    result = run(scheduler)["result"]

    assert (result["fixtures_seen"], result["fixtures_stored"]) == (2, 2)
    assert (result["forward_seen"], result["forward_stored"]) == (2, 2)
    assert result["forward_answer"] == "fixtures"
    assert result["empty_passes"] == 0
    assert result["last_seen_at"] == NOW.isoformat()
    assert result["last_seen_basis"] == "sync_pass"


def test_a_fixture_the_registry_refused_counts_as_seen_but_not_as_stored(cache, clock):
    """Offered and stored are different numbers, and the gap is the thing worth seeing.

    A run where every fixture is refused as unidentifiable reaches the provider, records no error
    and changes nothing in the database - the same silence as an empty day, from a different cause.
    """
    provider = StubDataProvider(fixtures=[_fixture(NOW + timedelta(hours=4), "f1"),
                                          _fixture(NOW + timedelta(hours=6), "f2")])
    scheduler = build(cache, clock, provider, refuse=["f2"])

    result = run(scheduler)["result"]

    assert (result["fixtures_seen"], result["fixtures_stored"]) == (2, 1)
    assert (result["forward_seen"], result["forward_stored"]) == (2, 1)
    assert result["days"]["2026-09-21"]["ambiguous"] == 1


def test_empty_passes_accumulate_until_a_fixture_arrives(cache, clock):
    """Three quiet passes in a row is the signal the September state never produced."""
    provider = StubDataProvider(fixtures=[])
    scheduler = build(cache, clock, provider)

    streak = []
    for _ in range(3):
        streak.append(run(scheduler)["result"]["empty_passes"])
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)
    assert streak == [1, 2, 3]
    assert len(provider.calls) == 3, "each pass must really have asked; a cached answer proves nothing"

    provider.fixtures = [_fixture(clock() + timedelta(hours=3), "f1")]
    result = run(scheduler)["result"]

    assert result["forward_seen"] == 1
    assert result["empty_passes"] == 0
    assert result["last_seen_at"] == clock().isoformat()


def test_the_empty_streak_survives_the_pass_that_records_it(cache, clock):
    """The count lives in the stored task state, not in the process: a restart must not reset it."""
    provider = StubDataProvider(fixtures=[])
    build_first = build(cache, clock, provider)
    run(build_first)
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    restarted = build(cache, clock, provider)  # a new scheduler, as a redeploy would create
    result = run(restarted)["result"]

    assert result["empty_passes"] == 2
    assert restarted.state(TASK_FIXTURES)["last_result"]["empty_passes"] == 2


# ------------------------------------------------- only the FORWARD list answers the question
def test_a_result_ingest_is_not_a_forward_fixture(cache, clock):
    """One unsettled match that kicked off hours ago must not quiet the empty-calendar count.

    `sync_day` runs the forward fixtures list, then `_sync_results`, then `_sync_live` through the
    same `_store_fixtures`, so `fixtures_seen` counts fixtures from all three. Read it as the
    answer to the forward question and the six fixtures the results call hands back here look
    exactly like a healthy matchday - six offered, six stored, streak reset - on a pass whose
    forward list was empty. Only `forward_seen` and `forward_answer` may be read for that.

    One stuck unsettled row dated today is enough to hold the streak at 0 for as long as it stays
    unsettled, and such a row is not hypothetical: the duplicate Everton v Ipswich has read LIVE
    since 2026-09-19 and is kept out of this only by its date.
    """
    provider = StubDataProvider(
        fixtures=[],  # the forward list is empty, which is the whole point
        results=[_fixture(NOW - timedelta(hours=4), f"r{i}") for i in range(6)])
    # Kicked off four hours ago and still not settled: past the 150-minute results cutoff, and
    # past the live window, so `_sync_results` runs and `_sync_live` does not.
    scheduler = build(cache, clock, provider, stored=[_stored_match(NOW - timedelta(hours=4))])

    result = run(scheduler)["result"]

    assert "results:2026-09-21" in provider.calls, "the results ingest must really have run"
    assert result["fixtures_seen"] == 6, "six fixtures did arrive on this pass"
    assert result["forward_seen"] == 0, "none of them answered the forward question"
    assert result["forward_answer"] == "empty"
    assert result["empty_passes"] == 1, "the streak must advance despite the results ingest"
    assert result["last_seen_at"] is None


def test_a_live_ingest_is_not_a_forward_fixture(cache, clock):
    """The same defect through the other door: the live poll, which runs on any matchday."""
    provider = StubDataProvider(
        fixtures=[],
        live=[_fixture(NOW - timedelta(minutes=30), f"l{i}") for i in range(6)])
    # Kicked off half an hour ago: inside the live window, short of the results cutoff.
    scheduler = build(cache, clock, provider, stored=[_stored_match(NOW - timedelta(minutes=30))])

    result = run(scheduler)["result"]

    assert "live" in provider.calls, "the live ingest must really have run"
    assert result["fixtures_seen"] == 6
    assert result["forward_seen"] == 0
    assert result["forward_answer"] == "empty"
    assert result["empty_passes"] == 1
    assert result["last_seen_at"] is None


def test_the_day_report_says_where_the_forward_answer_itself_came_from(cache, clock):
    """`source` belongs to whichever call ran last, so the forward list carries its own."""
    provider = StubDataProvider(fixtures=[], live=[_fixture(NOW, "l1")])
    scheduler = build(cache, clock, provider, stored=[_stored_match(NOW - timedelta(minutes=30))])

    day = run(scheduler)["result"]["days"]["2026-09-21"]

    assert day["source"] == "provider", "the live call answered last and set this"
    assert day["forward_source"] == "provider", "and the forward list was asked too"
    assert (day["fixtures_seen"], day["forward_fixtures_seen"]) == (1, 0)


# ------------------------------------------------- an outage is not a quiet calendar
def _outage() -> ProviderUnavailableError:
    return ProviderUnavailableError("upstream is down", provider="stub")


def test_a_stale_cached_answer_does_not_count_as_a_fixture_being_offered(cache, clock):
    """A copy up to 24 hours old is not the provider saying anything today.

    `_call_chain` falls back to `get_stale` when every provider fails. Counting the fixtures in
    that copy as offered would move `last_seen_at` to now and hold `empty_passes` at 0, so a whole
    day of outage - four passes at the six-hour fixtures interval - would read as four healthy
    ones while nothing new reached the database. The fixtures in the copy are still re-stored;
    what the pass may not claim is that anyone answered it today.
    """
    provider = StubDataProvider(fixtures=[_fixture(NOW + timedelta(hours=30), "f1")])
    scheduler = build(cache, clock, provider)
    run(scheduler)                                        # warms the cache, and its stale copy

    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)   # past the 30-minute fixtures TTL
    provider.fail = _outage()
    result = run(scheduler)["result"]

    assert result["days"]["2026-09-21"]["forward_source"] == "stale-cache"
    assert result["forward_seen"] == 1, "the stale copy did hold a fixture, and it was re-stored"
    assert result["forward_answer"] == "not_answered", "but nothing was learned from the provider"
    assert result["unanswered_passes"] == 1
    assert result["empty_passes"] == 0, "no claim either way about the calendar"
    assert result["last_seen_at"] == NOW.isoformat(), "the sighting is the first pass's, not now"


def test_a_pass_where_every_provider_failed_is_not_recorded_as_a_quiet_calendar(cache, clock):
    """The streak an admin reads must not mean two different things.

    With no answer and no stale copy `sync_day` gives up before storing anything and leaves
    `forward_source` unset, so the pass learned nothing about the calendar. Advancing the
    empty-calendar streak for it would file an outage and a league between rounds under the same
    number on the status page; the outage gets `unanswered_passes` instead, and `empty_passes`
    holds its place.
    """
    scheduler = build(cache, clock, StubDataProvider(fail=_outage()))

    outcome = run(scheduler)
    result = outcome["result"]

    assert outcome["ok"] is False, "no data at all is a failure, and backs the task off"
    assert result["days_unanswered"] == 1
    assert result["forward_answer"] == "not_answered"
    assert result["unanswered_passes"] == 1
    assert result["empty_passes"] == 0


def test_an_outage_in_the_middle_of_a_quiet_spell_leaves_the_quiet_streak_alone(cache, clock):
    """Both streaks at once: the calendar count holds its place while the outage count runs."""
    provider = StubDataProvider(fixtures=[])
    scheduler = build(cache, clock, provider)
    streak = []
    for _ in range(2):
        result = run(scheduler)["result"]
        streak.append((result["empty_passes"], result["unanswered_passes"]))
        clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    provider.fail = _outage()
    result = run(scheduler)["result"]
    streak.append((result["empty_passes"], result["unanswered_passes"]))
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    provider.fail = None
    result = run(scheduler)["result"]
    streak.append((result["empty_passes"], result["unanswered_passes"]))

    assert streak == [(1, 0), (2, 0), (2, 1), (3, 0)]


# ------------------------------------------------- a pass is three days in production, not one
def test_a_three_day_pass_asks_for_every_day_and_counts_the_streak_once(cache, clock, days_ahead):
    """`SYNC_FIXTURES_DAYS_AHEAD=3` is what production runs. The states are per pass, not per day."""
    days_ahead(3)
    provider = StubDataProvider(fixtures=[])
    scheduler = build(cache, clock, provider)

    result = run(scheduler)["result"]

    assert provider.calls == ["fixtures:2026-09-21", "fixtures:2026-09-22", "fixtures:2026-09-23"]
    assert (result["days_requested"], result["days_answered"]) == (3, 3)
    assert result["forward_answer"] == "empty"
    assert result["empty_passes"] == 1, "three quiet days are one quiet pass, not three"


def test_one_answered_day_among_dead_ones_is_reported_as_fixtures_with_the_dead_days_beside_it(
        cache, clock, days_ahead):
    """A sighting outranks an outage, so `forward_answer` alone is not a report on the pass.

    Today answers with one fixture and the next two days raise. The pass lands in "fixtures" and
    both streaks reset, which is the documented precedence and not a claim that every day was
    answered - `days_unanswered` carries that, and the operator line has to print it, or a pass
    two thirds dead reads exactly like a clean one.
    """
    days_ahead(3)
    provider = StubDataProvider(fixtures=[_fixture(NOW + timedelta(hours=4), "f1")],
                                fail_days=[date(2026, 9, 22), date(2026, 9, 23)])
    scheduler = build(cache, clock, provider)

    result = run(scheduler)["result"]

    assert result["forward_answer"] == "fixtures"
    assert (result["days_answered"], result["days_unanswered"]) == (1, 2)
    assert (result["empty_passes"], result["unanswered_passes"]) == (0, 0)
    assert result["last_seen_at"] == NOW.isoformat()

    from scripts.sync_once import _summarise
    text = "\n".join(_summarise("fixtures", result))
    assert "1 forward fixture(s) offered" in text
    assert "2 of 3 day(s) were not answered" in text, \
        "a pass with two dead days must not print as a clean one"


# ------------------------------------------------- a pass with no stored summary must not claim "never"
def test_a_pass_with_no_stored_summary_does_not_claim_no_fixture_was_ever_seen(cache, clock):
    """48 fixtures arrived on 2026-09-18; a pass holding no summary must not report "never"."""
    arrived = datetime(2026, 9, 18, 6, 30, tzinfo=timezone.utc)
    scheduler = build(cache, clock, StubDataProvider(fixtures=[]), seed=arrived)

    result = run(scheduler)["result"]

    assert result["last_seen_at"] == arrived.isoformat()
    assert result["last_seen_basis"] == "matches_table", \
        "a row in the table is evidence a fixture arrived, not evidence a pass saw one"


def test_a_seeded_sighting_is_replaced_by_a_real_one_while_the_summary_survives(cache, clock):
    """The seed is a starting value: once a pass sees a fixture it owns the timestamp.

    "While the summary survives" is the whole of the claim. The sighting is carried in the stored
    task summary, so losing that summary brings the seed back - see the exception test below.
    """
    provider = StubDataProvider(fixtures=[])
    scheduler = build(cache, clock, provider, seed=datetime(2026, 9, 18, 6, 30, tzinfo=timezone.utc))
    run(scheduler)
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    provider.fixtures = [_fixture(clock() + timedelta(hours=3), "f1")]
    seen_pass = run(scheduler)["result"]
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)
    provider.fixtures = []
    later = run(scheduler)["result"]

    offered_at = (NOW + timedelta(seconds=settings.SYNC_FIXTURES_INTERVAL_SECONDS)).isoformat()
    assert (seen_pass["last_seen_at"], seen_pass["last_seen_basis"]) == (offered_at, "sync_pass")
    assert later["last_seen_basis"] == "sync_pass", "the seed must not come back while the summary does"
    assert later["last_seen_at"] == seen_pass["last_seen_at"]


# ------------------------------------------------- what a lost summary costs
def test_a_pass_that_raises_restarts_both_streaks_and_the_sighting(cache, clock):
    """The limit of the carry-forward, pinned so the comments describing it stay honest.

    Everything carried between passes lives in `last_result`, and `_maybe_run` records
    `last_result=None` for any exception the task itself does not catch - a failing commit, a
    malformed payload. The next pass therefore reads an empty previous: both streaks restart at 0
    and the sighting drops back to the reconstruction from the matches table. A state entry past
    its TTL and a pass run with Redis unavailable land in exactly the same place.

    This is not a defect being asserted as correct; it is the reach of these counters, and the
    reason nothing here may be worded as "since a fixture was last seen".
    """
    seed = datetime(2026, 9, 18, 6, 30, tzinfo=timezone.utc)
    provider = StubDataProvider(fixtures=[])
    scheduler = build(cache, clock, provider, seed=seed)
    run(scheduler)
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)
    before = run(scheduler)["result"]
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)

    crashed = run(build(cache, clock, provider, seed=seed, crash=RuntimeError("commit failed")))
    summary_after_the_crash = scheduler.state(TASK_FIXTURES)["last_result"]
    clock.tick(settings.SYNC_FIXTURES_INTERVAL_SECONDS)
    after = run(build(cache, clock, provider, seed=seed))["result"]

    assert before["empty_passes"] == 2
    assert crashed["ok"] is False and "commit failed" in crashed["error"]
    assert summary_after_the_crash is None, "the summary is what is lost"
    assert after["empty_passes"] == 1, "the streak counts passes since the last stored summary"
    assert (after["last_seen_at"], after["last_seen_basis"]) == (seed.isoformat(), "matches_table")


# ------------------------------------------------- what the operator actually reads
def test_the_one_shot_script_does_not_call_an_outage_a_quiet_calendar(cache, clock):
    """`scripts/sync_once.py` is where these numbers are read by hand."""
    from scripts.sync_once import _summarise

    scheduler = build(cache, clock, StubDataProvider(fail=_outage()))
    result = run(scheduler)["result"]

    text = "\n".join(_summarise("fixtures", result))

    assert "went unanswered" in text
    assert "no forward fixture offered" not in text, \
        "an outage must not be printed as the provider having nothing to give"


def test_the_one_shot_script_says_which_fixtures_were_forward_ones(cache, clock):
    from scripts.sync_once import _summarise

    provider = StubDataProvider(fixtures=[],
                                results=[_fixture(NOW - timedelta(hours=4), f"r{i}") for i in range(6)])
    scheduler = build(cache, clock, provider, stored=[_stored_match(NOW - timedelta(hours=4))])
    result = run(scheduler)["result"]

    text = "\n".join(_summarise("fixtures", result))

    assert "no forward fixture offered" in text
    assert "6 further fixture(s) came back on this pass" in text
    assert "6 fixture(s) offered, 6 stored" not in text, \
        "fixtures from the results ingest must not be printed as the forward list being answered"


def test_the_one_shot_script_never_prints_never(cache, clock):
    from scripts.sync_once import _summarise

    scheduler = build(cache, clock, StubDataProvider(fixtures=[]))
    text = "\n".join(_summarise("fixtures", run(scheduler)["result"]))

    assert "no sighting recorded and none could be reconstructed" in text
    assert "never" not in text, "nothing recorded is not the same as no fixture having arrived"


def test_the_one_shot_script_marks_a_reconstructed_sighting_as_reconstructed(cache, clock):
    from scripts.sync_once import _summarise

    scheduler = build(cache, clock, StubDataProvider(fixtures=[]),
                      seed=datetime(2026, 9, 18, 6, 30, tzinfo=timezone.utc))
    text = "\n".join(_summarise("fixtures", run(scheduler)["result"]))

    assert "2026-09-18T06:30:00+00:00" in text
    assert "no recorded sighting to carry" in text, "a reconstructed date must not pose as a sighting"


def test_the_one_shot_script_diagnoses_nothing_on_a_pass_with_no_summary(cache, clock, capsys):
    """A pass that raised has no counters, and none may be invented for it.

    The report entry for an uncaught exception carries an error and no `result` key at all. Every
    line below the error is read off the summary a completed pass records, so on this entry there
    is nothing to print: the error is the whole of what is known. Reading the missing counters
    anyway states an absence as a measurement - "unanswered for 0 of None day(s)" - which is a
    confident diagnosis of the forward list on a pass that never reached it.
    """
    from scripts.sync_once import _print_run

    entry = run(build(cache, clock, StubDataProvider(fixtures=[]),
                      crash=RuntimeError("commit failed")))

    assert "result" not in entry, "the shape this has to cope with"
    _print_run({"tasks": {TASK_FIXTURES: entry}})
    printed = capsys.readouterr().out

    assert "FAILED" in printed and "commit failed" in printed
    assert "day(s)" not in printed, "no count may be printed from a summary that was never written"
    assert "streak" not in printed and "last fixture seen" not in printed


def _not_due_scheduler(cache, clock):
    """A scheduler whose fixtures task has just run, so it is not due again for an interval."""
    scheduler = build(cache, clock, StubDataProvider(fixtures=[]))
    run(scheduler)
    assert scheduler.due(TASK_FIXTURES)[0] is False, \
        "a task that has just run is not due again until its interval has elapsed"
    return scheduler


def test_a_dry_run_describes_the_forced_pass_when_it_is_asked_about_one(cache, clock):
    """`--force --dry-run` estimates the pass `--force` would make, not the one it replaces.

    The task under test has just run, so an ordinary pass skips it and a forced one runs it: the
    two estimates describe different passes and must price them differently - zero for the pass
    that would do nothing, the real cost for the pass that would fetch. `due_now` stays false in
    both, because `--force` overrides the interval rather than making the task due.
    """
    scheduler = _not_due_scheduler(cache, clock)

    unforced = scheduler.estimate(only=[TASK_FIXTURES])
    forced = scheduler.estimate(only=[TASK_FIXTURES], force=True)

    assert unforced["tasks"][TASK_FIXTURES]["would_run"] is False
    assert unforced["total_requests"] == 0
    assert forced["tasks"][TASK_FIXTURES]["would_run"] is True
    assert forced["total_requests"] == forced["tasks"][TASK_FIXTURES]["estimated_requests"] > 0
    assert forced["tasks"][TASK_FIXTURES]["due_now"] is False, \
        "--force overrides the interval; it does not make the task due"


def test_a_forced_dry_run_prints_the_override_beside_the_interval(cache, clock, capsys):
    from scripts.sync_once import _print_estimate

    scheduler = _not_due_scheduler(cache, clock)

    _print_estimate(scheduler.estimate(only=[TASK_FIXTURES], force=True))
    printed = capsys.readouterr().out

    assert "would run" in printed
    assert "overridden by --force" in printed, \
        "a cost this same report prices must not be printed under a bare 'not due'"


def test_an_unforced_dry_run_says_nothing_about_a_flag_that_was_not_passed(cache, clock, capsys):
    from scripts.sync_once import _print_estimate

    scheduler = _not_due_scheduler(cache, clock)

    _print_estimate(scheduler.estimate(only=[TASK_FIXTURES]))
    printed = capsys.readouterr().out

    assert "would be skipped" in printed
    assert "--force" not in printed


def test_the_one_shot_script_reports_a_healthy_pass_plainly(cache, clock):
    from scripts.sync_once import _summarise

    provider = StubDataProvider(fixtures=[_fixture(NOW + timedelta(hours=4), "f1")])
    scheduler = build(cache, clock, provider)
    text = "\n".join(_summarise("fixtures", run(scheduler)["result"]))

    assert "1 forward fixture(s) offered, 1 stored" in text
    assert "unanswered" not in text


# ------------------------------------------------- the counters survive a two-UTC-day answer
def test_merging_two_utc_days_keeps_the_counters():
    """Both days' counts must survive the merge, the forward pair included.

    A local day can straddle two UTC days, and `_merge_meta` is what the endpoint reports for
    such a day. A count it does not add up is reported as the first day's figure alone, which
    understates what the pass did and does so only on the path a reader is least likely to check.
    """
    from app.api.v1.endpoints.matches import _merge_meta

    first = SyncMeta(source="provider", fixtures_seen=3, fixtures_stored=3,
                     forward_fixtures_seen=3, forward_fixtures_stored=2,
                     forward_source="provider", forward_fetched_at="2026-09-21T11:00:00+00:00")
    second = SyncMeta(source="stale-cache", stale=True, fixtures_seen=2, fixtures_stored=1,
                      forward_fixtures_seen=2, forward_fixtures_stored=1,
                      forward_source="stale-cache")

    merged = _merge_meta(first, second)

    assert (merged.fixtures_seen, merged.fixtures_stored) == (5, 4)
    assert (merged.forward_fixtures_seen, merged.forward_fixtures_stored) == (5, 3)
    assert merged.source == "stale-cache", "the pair is only as fresh as its weaker half"
    assert merged.forward_source == "stale-cache"


def test_merging_keeps_the_forward_answer_and_its_timestamp_together():
    """A day nobody answered must not come out carrying the other day's fetch time.

    `forward_source` and `forward_fetched_at` describe one answer. Merged by different rules -
    weakest source, first non-empty timestamp - the unanswered day wins the source (None ranks
    below every answered one) and the answered day supplies the timestamp, which reports a fetch
    that never happened for the answer being described.
    """
    from app.api.v1.endpoints.matches import _merge_meta

    never_answered = SyncMeta(source="database")
    answered = SyncMeta(source="provider", forward_source="provider",
                        forward_fetched_at="2026-09-21T11:00:00+00:00",
                        forward_fixtures_seen=2, forward_fixtures_stored=2)

    for merged in (_merge_meta(never_answered, answered), _merge_meta(answered, never_answered)):
        assert merged.forward_source is None
        assert merged.forward_fetched_at is None, "no answer, so no time at which one was fetched"
        assert merged.forward_fixtures_seen == 2, "the counts are still a sum of the two days"


# --------------------------------------------------------------------- the provider says which empty
@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """The real client spaces calls a second apart; a test must not wait for that."""
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr("app.services.providers.livescore_api.BURST_RETRY_DELAY", 0.0)


def _calendar(fixtures: List[Dict[str, Any]]):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "date" not in dict(request.url.params), "get_upcoming asks for the whole calendar"
        return json_response({"success": True, "data": {"fixtures": fixtures, "next_page": False}})
    return handler


def _upcoming(handler, days_ahead: int = 7):
    transport, recorder = make_transport(handler)
    provider = LiveScoreAPIProvider(
        api_key="trial-key", api_secret="trial-secret", transport=transport,
        budget=RequestBudget("livescore", 1200, client=FakeRedis()),
        competition_overrides={"premier_league": "2"}, store=MatchCache(client=FakeRedis()),
        use_default_ids=False)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 21, 11, 0, tzinfo=tz)

    with patch("app.services.providers.livescore_api.datetime", FrozenDatetime):
        return provider.get_upcoming("premier_league", days_ahead=days_ahead), recorder


def test_a_calendar_whose_next_round_is_past_the_window_says_when_that_round_is(caplog):
    """The 9 October case: fixtures exist, the seven-day window simply ends before the first one."""
    caplog.set_level("INFO", logger=LOGGER)
    fixtures, recorder = _upcoming(_calendar([
        {"id": "1877306", "date": "2026-10-10", "time": "11:30:00", "home": {"id": "18", "name": "Arsenal"},
         "away": {"id": "1131", "name": "Leeds United"}, "competition": {"id": "2", "name": "Premier League"}},
    ]))

    assert fixtures == [], "a fixture three weeks out is genuinely not in a seven-day window"
    assert len(recorder.requests) == 1
    assert "the competition calendar's next fixture is 2026-10-10" in caplog.text


def test_a_competition_with_no_calendar_at_all_is_reported_differently(caplog):
    """The failure the other message must not be confused with: nothing came back to skip."""
    caplog.set_level("INFO", logger=LOGGER)
    fixtures, _ = _upcoming(_calendar([]))

    assert fixtures == []
    assert "next fixture is not listed at all" in caplog.text


def test_a_fixture_inside_the_window_is_returned_and_nothing_is_reported_as_missing(caplog):
    caplog.set_level("INFO", logger=LOGGER)
    fixtures, _ = _upcoming(_calendar([
        {"id": "1901", "date": "2026-09-23", "time": "19:00:00", "home": {"id": "18", "name": "Arsenal"},
         "away": {"id": "17", "name": "Chelsea"}, "competition": {"id": "2", "name": "Premier League"}},
    ]))

    assert [f.external_id for f in fixtures] == ["1901"]
    assert "calendar's next fixture" not in caplog.text
