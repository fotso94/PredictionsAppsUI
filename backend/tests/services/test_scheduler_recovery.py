"""
A match whose final score did not arrive must be recovered BY ITSELF, whenever the provider can
answer, and the sweep must say what it did - never more than that.

WHAT THE PROVIDER HAS BEEN SEEN TO DO, and what these tests therefore model. Every observation is in
docs/evidence/livescore-archive-observations.json with the date it was made.

  * `matches/history.json` ANSWERS PER COMPETITION AND DATE, national-team competitions included:
    it returned rows for the FIFA World Cup, AFCON, Copa America and the Women's World Cup. The
    double here is an archive keyed by (competition, date) that returns only what a call names.
  * IT HAS BEEN EMPTY FOR A DATE, and whether it fills in later is UNOBSERVED. On 2026-09-22 and
    again on 2026-09-25 it returned nothing dated 2026-09-18 or later, for club and national
    competitions alike, while La Liga answered for 09-16 and 09-17 both times. Why is not known,
    and no date has ever been seen to go from empty to answered. So the double starts empty, and a
    test that publishes into it later is modelling a POSSIBILITY the design must not rule out -
    not a behaviour the provider has been seen to have.
  * AN EMPTY ANSWER AND AN UNREACHABLE PROVIDER ARE DIFFERENT FACTS. `reachable = False` fails
    every endpoint, because an outage is not endpoint-shaped as a rule; `history_reachable = False`
    fails `matches/history.json` alone, which is the shape in which a results request actually
    goes out and fails (a whole outage fails the pass's live poll first, and the cool-down that
    sets means no results request leaves at all).
  * A REQUEST THAT WAS NEVER SENT IS NEITHER. A due ask skipped during a cool-down, or refused by
    an allowance before it left, is DEFERRED: nothing was asked, so nothing was unreachable.

WHAT IS DELIBERATELY NOT MODELLED. How long `matches/live.json` keeps a finished match is not
known: two observations on one evening show what it carried at those moments, and the provider's
own documentation describes finished matches staying after full time for durations it states
inconsistently. So no test here has the live feed hand back a match hours after kickoff, and no
test depends on it being unable to. Outside the one in-window test, the live feed holds nothing,
and the assertions are about what the sweep does with silence: it does not count it either way.

Every test drives the SHIPPED SCHEDULER - `SyncScheduler.run_once()`, nothing forced - over the
double and a fake clock, and asserts the requests made, because a repair that overspends is not a
repair and neither is one that stops asking where the answer may still come.

Requires PostgreSQL: the recovery bookkeeping is JSONB on the match and league rows, and settlement
reads real tables. Set TEST_DATABASE_URL; skipped when unreachable. No network.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.predictions import (
    Match, MatchStatus, Prediction, PredictionResult, PredictionSource, PredictionStatus,
)
from app.models.users import AccountStatus, User, UserType
from app.schemas.matches import serialize_recovery
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    MatchDataService, live_polls_today, note_live_poll, recovery_requests_today,
)
from app.services.match_registry import (
    RETRY_HORIZON, UNSETTLED_GRACE, ArchiveState, MatchRegistry, RecoveryOutcome, retry_due,
)
from app.services.settlement import OUTCOME_HOME
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_HALFTIME, MatchDataProvider, ProviderCompetition, ProviderFixture,
    ProviderTeam, ProviderUnavailableError,
)
from app.services.sync_scheduler import (
    TASK_LIVE, TASK_RECOVER, TASK_RESULTS, TASK_SETTLE, SyncScheduler,
)
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

#: A national-team competition. Nothing in the sweep may treat it differently from the club one.
KEY = "uefa_nations_league"
#: A club competition, one of the six that must keep working exactly as they do.
CLUB_KEY = "premier_league"
#: A competition nobody in these tests ever asks about.
NEVER_ASKED_KEY = "fifa_world_cup"
BOTH = pytest.mark.parametrize("key", [KEY, CLUB_KEY], ids=["national", "club"])

#: Late enough in the UTC day that the rollover test can cross midnight without moving it.
KICKOFF = datetime(2026, 9, 24, 22, 30, tzinfo=timezone.utc)
#: Past `UNSETTLED_GRACE`, this application's own 150-minute polling window.
AFTER_THE_WINDOW = KICKOFF + timedelta(hours=3)
#: For the in-window test: ninety minutes in, inside the polling window.
EVENING_KICKOFF = datetime(2026, 9, 24, 18, 45, tzinfo=timezone.utc)
INSIDE_THE_WINDOW = EVENING_KICKOFF + timedelta(minutes=90)
#: Two days before `KICKOFF`: behind the one-day results lookback when the clock is past midnight.
TWO_DAYS_BACK = KICKOFF - timedelta(days=2)
#: The first pass after the grace, one minute past it - where the week-long tests begin.
FIRST_PASS_AFTER_GRACE = UNSETTLED_GRACE + timedelta(minutes=1)


# ----------------------------------------------------------------------------- database
@pytest.fixture(scope="module")
def engine():
    try:
        eng = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
        with eng.connect() as conn:
            for schema in ("users", "predictions", "ml_models", "analytics", "audit"):
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.commit()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL test database not reachable: {exc}")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    """Session joined to an outer transaction; nothing a test writes survives it."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ----------------------------------------------------------------------------- the provider double
COMPETITIONS = {
    KEY: ProviderCompetition(provider="livescore", external_id="350", name="UEFA Nations League",
                             key=KEY, country="Europe"),
    CLUB_KEY: ProviderCompetition(provider="livescore", external_id="2", name="Premier League",
                                  key=CLUB_KEY, country="England"),
}
#: Invented clubs and nations: these are test doubles, and no real fixture's score is modelled.
TEAMS = {KEY: ("Northland", "Southmark"), CLUB_KEY: ("Riverside Town", "Hillcrest United")}


class ArchiveDouble(MatchDataProvider):
    """Live Score as it has been seen to behave, reachable or not as a test says.

    `archive` is what `matches/history.json` holds, per (competition, date). A results call is
    billed and answered per competition it names, exactly as Live Score bills it, and returns only
    the rows for the competitions and dates it asked for. It starts EMPTY - the state the archive was
    observed in for every date from 2026-09-18 - and `publish` is the archive catching up.

    `live` is what `matches/live.json` holds right now. Outside the in-window test it stays empty.
    """

    name = "livescore"
    integration_status = "primary"

    def __init__(self, *, reachable: bool = True, history_reachable: bool = True):
        self.archive: Dict[Tuple[str, date], List[ProviderFixture]] = {}
        self.live: List[ProviderFixture] = []
        self.reachable = reachable
        self.history_reachable = history_reachable
        self.live_calls = 0
        self.results_calls = 0
        self.results_requests = 0
        self.results_asked: List[Tuple[date, Tuple[str, ...]]] = []
        self.fixture_calls = 0

    def publish(self, fixture: ProviderFixture) -> None:
        where = (fixture.competition.key, fixture.kickoff_utc.date())
        self.archive.setdefault(where, []).append(fixture)

    def go_down(self) -> None:
        self.reachable = False

    def come_back(self) -> None:
        self.reachable = True
        self.history_reachable = True

    @property
    def requests(self) -> int:
        return self.live_calls + self.results_requests + self.fixture_calls

    def requests_for(self, key: str, day: date) -> int:
        return sum(1 for asked_day, keys in self.results_asked if asked_day == day and key in keys)

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return [COMPETITIONS[k] for k in keys if k in COMPETITIONS]

    def _refuse_if_down(self) -> None:
        if not self.reachable:
            raise ProviderUnavailableError("livescore: name resolution failed", provider=self.name)

    def get_fixtures(self, day: date, keys):
        self.fixture_calls += 1
        self._refuse_if_down()
        return []

    def get_live(self, keys):
        self.live_calls += 1
        self._refuse_if_down()
        return list(self.live)

    def get_results(self, date_from: date, date_to: date, keys):
        keys = tuple(keys)
        self.results_calls += 1
        self.results_requests += len(keys)
        self.results_asked.append((date_from, keys))
        self._refuse_if_down()
        if not self.history_reachable:
            raise ProviderUnavailableError("livescore: upstream error (HTTP 503)", provider=self.name)
        rows: List[ProviderFixture] = []
        day = date_from
        while day <= date_to:
            for key in keys:
                rows.extend(self.archive.get((key, day), []))
            day += timedelta(days=1)
        return rows

    def get_standings(self, key: str):
        return []


def provider_fixture(external_id: str, *, key: str, status: str, kickoff: datetime,
                     teams: Optional[Tuple[str, str]] = None, **scores) -> ProviderFixture:
    home, away = teams or TEAMS[key]

    def team(name: str) -> ProviderTeam:
        return ProviderTeam(provider="livescore", name=name,
                            external_id="ls-" + "".join(c for c in name.lower() if c.isalnum()))

    return ProviderFixture(provider="livescore", external_id=external_id,
                           competition=COMPETITIONS[key], home=team(home), away=team(away),
                           kickoff_utc=kickoff, status=status, **scores)


# ----------------------------------------------------------------------------- the harness
@pytest.fixture
def clock():
    return Clock(start=AFTER_THE_WINDOW)


@pytest.fixture
def cache(clock):
    return MatchCache(client=LockingFakeRedis(clock=clock))


@pytest.fixture(autouse=True)
def _covered(monkeypatch):
    monkeypatch.setattr(settings, "COVERED_COMPETITIONS", CLUB_KEY)
    monkeypatch.setattr(settings, "COVERED_NATIONAL_TEAM_COMPETITIONS", KEY)
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 1)


def build(db, cache, clock, provider: ArchiveDouble, tasks=(TASK_RECOVER,)) -> SyncScheduler:
    """The shipped scheduler over a real service, registry and database. Only the provider and
    the clock are doubles."""
    def match_factory(_db):
        return MatchDataService(_db, providers=[provider], cache=cache, now=clock(),
                                keys=[KEY, CLUB_KEY])

    return SyncScheduler(session_factory=lambda: db, cache=cache, now=clock,
                         match_service_factory=match_factory,
                         forecast_service_factory=lambda _db: None,
                         tasks=list(tasks), close_sessions=False)


def unattended(scheduler: SyncScheduler) -> Dict[str, object]:
    """One tick of the background loop: nothing named, nothing forced."""
    return scheduler.run_once()


def next_pass(clock: Clock) -> None:
    clock.tick(settings.SYNC_RECOVERY_INTERVAL_SECONDS)


_ids = iter(range(10_000))


def stranded_fixture(db, *, key: str, kickoff: datetime,
                     status: MatchStatus = MatchStatus.LIVE,
                     teams: Optional[Tuple[str, str]] = None) -> Match:
    """A fixture stored as still being played, written the way a real live poll wrote it."""
    fixture_id = f"ls-{key}-{next(_ids)}"
    match = MatchRegistry(db).upsert_fixture(provider_fixture(
        fixture_id, key=key, status=STATUS_HALFTIME, kickoff=kickoff, teams=teams))
    assert match is not None
    match.status = status
    meta = dict(match.match_metadata or {})
    meta["test_fixture_id"] = fixture_id
    meta["test_teams"] = list(teams or TEAMS[key])
    match.match_metadata = meta
    db.commit()
    return match


def final_score(match: Match, key: str) -> ProviderFixture:
    """The finished fixture as the archive hands it back, under the id the live poll stored."""
    return provider_fixture(match.match_metadata["test_fixture_id"], key=key,
                            status=STATUS_FINISHED,
                            kickoff=match.match_date.replace(tzinfo=timezone.utc),
                            teams=tuple(match.match_metadata["test_teams"]),
                            home_score=2, away_score=1)


def forecast_on(db, match: Match) -> Prediction:
    suffix = uuid.uuid4().hex[:8]
    expert = User(id=uuid.uuid4(), email=f"tipster-{suffix}@test.local", username=f"tipster_{suffix}",
                  password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                  account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(expert)
    db.flush()
    row = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                     created_by=expert.id, home_win_prob=Decimal("0.55"), draw_prob=Decimal("0.25"),
                     away_win_prob=Decimal("0.20"), confidence_score=Decimal("0.8"),
                     status=PredictionStatus.PUBLISHED, priority_level=100,
                     published_at=match.match_date - timedelta(hours=5),
                     reasoning="a forecast waiting on a final score")
    db.add(row)
    db.commit()
    return row


def settled(db, prediction: Prediction) -> Optional[PredictionResult]:
    return db.query(PredictionResult).filter(PredictionResult.prediction_id == prediction.id).first()


def recovery(report: Dict[str, object]) -> Dict[str, object]:
    entry = report["tasks"][TASK_RECOVER]
    assert entry.get("ran") is True, f"the recover task did not run: {entry}"
    return entry["result"]


def state(db, match: Match) -> Dict[str, object]:
    db.refresh(match)
    return MatchRegistry.recovery_state(match)


def archive(db, key: str, day: date) -> Dict[str, object]:
    return MatchRegistry(db).archive_observation(key, day)


# ================================================ 1. INSIDE the polling window: the live task
def test_a_pass_missed_inside_the_live_window_recovers_with_nobody_forcing_anything(db, cache,
                                                                                    clock):
    """
    A twenty-minute outage over a match ninety minutes in. The ORDINARY live task picks the final
    score up on its next tick and settlement scores the forecast in the same pass.

    The live feed carrying the match at 110 minutes is what "in play or just finished" means, and
    it is the one place these tests let the feed hold a fixture. The recovery task stays out of the
    way: inside the polling window nothing is stranded, so it has nothing to spend on.
    """
    clock.now = EVENING_KICKOFF - timedelta(minutes=30)
    match = stranded_fixture(db, key=KEY, kickoff=EVENING_KICKOFF, status=MatchStatus.SCHEDULED)
    prediction = forecast_on(db, match)
    provider = ArchiveDouble(reachable=False)
    scheduler = build(db, cache, clock, provider, tasks=(TASK_LIVE, TASK_RECOVER, TASK_SETTLE))

    clock.now = INSIDE_THE_WINDOW
    outage = unattended(scheduler)
    assert outage["tasks"][TASK_LIVE]["ran"] is True
    assert recovery(outage)["stranded"] == 0, "ninety minutes in, this match is being played"

    provider.come_back()
    provider.live = [final_score(match, KEY)]
    clock.tick(20 * 60)
    assert clock() - EVENING_KICKOFF < UNSETTLED_GRACE
    live_calls_before = provider.live_calls

    report = unattended(scheduler)

    db.refresh(match)
    assert match.status == MatchStatus.FINISHED
    assert (match.result.home_score, match.result.away_score) == (2, 1)
    assert report["tasks"][TASK_SETTLE]["ran"] is True
    result = settled(db, prediction)
    assert result is not None and result.actual_outcome == OUTCOME_HOME
    assert provider.live_calls - live_calls_before == 1
    assert provider.results_calls == 0
    repair = report["tasks"][TASK_RECOVER]
    assert repair["ran"] is False or repair["result"]["requests"] == 0


# ============================= 2. the archive answers, whatever kind of competition it is
@BOTH
def test_after_the_window_the_archive_recovers_a_fixture_whatever_its_competition(db, cache, clock,
                                                                                  key):
    """
    The same path for a national-team fixture as for a club one, because the archive has been
    seen to answer for both. Two days after kickoff, behind the results lookback, the recovery pass
    asks the archive for the fixture's competition and date, gets the final score, and the forecast
    is scored.
    """
    match = stranded_fixture(db, key=key, kickoff=TWO_DAYS_BACK)
    prediction = forecast_on(db, match)
    provider = ArchiveDouble()
    provider.publish(final_score(match, key))
    scheduler = build(db, cache, clock, provider, tasks=(TASK_RECOVER, TASK_SETTLE))

    report = unattended(scheduler)
    recovered = recovery(report)

    db.refresh(match)
    assert match.status == MatchStatus.FINISHED
    assert (match.result.home_score, match.result.away_score) == (2, 1)
    assert recovered["outcomes"][RecoveryOutcome.RECOVERED.value] == 1
    assert state(db, match)["recovered_as"] == f"{MatchStatus.FINISHED.value} 2-1"
    assert state(db, match)["recovered_by"] == "a fresh answer from livescore settled it"
    assert state(db, match).get("attempts", 0) == 0, "a recovery owes no attempt"
    assert settled(db, prediction).actual_outcome == OUTCOME_HOME

    seen = archive(db, key, TWO_DAYS_BACK.date())
    assert seen["state"] == ArchiveState.ANSWERED.value and seen["rows"] == 1

    assert provider.results_requests == 1 and recovered["results_requests"] == 1
    assert recovery_requests_today(cache, clock()) == 1
    assert recovered["live_requests"] == 1 and recovered["requests"] == 2
    assert recovered["failed_calls"] == []


# ====================== 3. THE CASE THE OLD DESIGN THREW AWAY: empty for days, then it answers
def test_an_archive_empty_for_days_that_then_returns_the_fixture_still_recovers_it(db, cache, clock):
    """
    A national-team fixture whose result the archive does not hold for four days, and then does.

    The design this replaces decided that national-team competitions had no archive and retired
    such a fixture six hours after kickoff, so this recovery could never have happened. The
    evidence never supported that: the archive has answered for national-team competitions, and
    its recent gap covered club competitions too.

    What must happen: the fixture is asked about on the retry schedule, each empty answer is
    recorded as EMPTY and as one attempt, nothing is retired, and the first scheduled ask after the
    archive catches up settles it and scores the forecast - with the schedule's own request count.
    """
    kickoff = datetime(2026, 9, 24, 16, 1, tzinfo=timezone.utc)
    clock.now = kickoff + FIRST_PASS_AFTER_GRACE
    match = stranded_fixture(db, key=KEY, kickoff=kickoff)
    prediction = forecast_on(db, match)
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider, tasks=(TASK_RESULTS, TASK_RECOVER, TASK_SETTLE))

    # -- four days of an empty archive, one pass every half hour.
    while clock() - kickoff < timedelta(days=4):
        unattended(scheduler)
        if clock() - kickoff > timedelta(hours=6, minutes=30):
            assert not state(db, match).get("gave_up_at"), (
                f"retired {clock() - kickoff} after kickoff; the archive may still answer")
        next_pass(clock)

    row = state(db, match)
    seen = archive(db, KEY, kickoff.date())
    # Asked at 2h31, then every pass to 6h, every 2h to 24h, every 6h to 3 days, every 12h after:
    # 8 + 8 + 8 + 2 = 26 asks, the last at 3 days 23h31. Each was answered, empty.
    assert provider.requests_for(KEY, kickoff.date()) == 26
    assert row["attempts"] == 26
    assert seen["state"] == ArchiveState.EMPTY.value and seen["times_asked"] == 26
    assert row["archive"]["state"] == "empty"
    db.refresh(match)
    assert match.status == MatchStatus.LIVE, "nothing is invented while the archive is empty"

    # -- the archive catches up.
    provider.publish(final_score(match, KEY))
    published_at = clock()
    while match.status != MatchStatus.FINISHED and clock() - published_at < timedelta(hours=13):
        unattended(scheduler)
        db.refresh(match)
        next_pass(clock)

    assert match.status == MatchStatus.FINISHED, "the fixture was still recoverable"
    assert (match.result.home_score, match.result.away_score) == (2, 1)
    assert clock() - published_at <= timedelta(hours=12, minutes=30), (
        "four days after kickoff the schedule asks every 12 hours, so the result lands within one")
    assert provider.requests_for(KEY, kickoff.date()) == 27, "one more ask, and it answered"
    row = state(db, match)
    assert row["recovered_as"] == f"{MatchStatus.FINISHED.value} 2-1"
    assert "livescore" in row["recovered_by"]
    assert not row.get("gave_up_at")
    assert archive(db, KEY, kickoff.date())["state"] == ArchiveState.ANSWERED.value
    # Four and a half days after kickoff is past the settle task's 3-day window; the late
    # recovery is scored all the same.
    assert clock() - kickoff > timedelta(days=settings.SYNC_SETTLE_LOOKBACK_DAYS)
    assert settled(db, prediction).actual_outcome == OUTCOME_HOME


# ======================================= 4. a successful empty answer, and a question never put
@BOTH
def test_a_successful_empty_answer_is_recorded_as_empty_and_one_attempt_and_never_as_recovered(
        db, cache, clock, key):
    """The provider answered and held nothing for that competition and date.

    That is recorded as EMPTY for the (competition, date) with the moment we asked - what the
    archive held then, nothing about later - and as exactly one attempt on the fixture. It is not a
    recovery, it is not an outage, and the pass that got it is a healthy pass.
    """
    match = stranded_fixture(db, key=key, kickoff=TWO_DAYS_BACK)
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    outcome = unattended(scheduler)["tasks"][TASK_RECOVER]
    report = outcome["result"]

    assert report["outcomes"][RecoveryOutcome.RECOVERED.value] == 0
    assert report["outcomes"][RecoveryOutcome.FRESH_UNANSWERED.value] == 1
    assert provider.results_requests == 1
    row = state(db, match)
    assert row["attempts"] == 1
    assert "0 row(s)" in row["last_outcome_detail"]
    seen = archive(db, key, TWO_DAYS_BACK.date())
    assert seen["state"] == ArchiveState.EMPTY.value and seen["rows"] == 0
    assert seen["asked_at"] == clock().isoformat()
    assert report["archive"][f"{key}@{TWO_DAYS_BACK.date().isoformat()}"]["state"] == "empty"
    db.refresh(match)
    assert match.status == MatchStatus.LIVE, "an empty list is not match data"

    assert outcome["ok"] is True, "an archive with nothing yet is not a failure of the pass"
    assert report["failed_calls"] == []
    served = serialize_recovery(match.match_metadata)
    assert served["last_outcome"] == "fresh_unanswered" and served["archive"]["state"] == "empty"
    assert served["gave_up_at"] is None and served["next_ask_after"]


@pytest.mark.parametrize("asked", [KEY, CLUB_KEY], ids=["national-asked", "club-asked"])
def test_a_competition_never_asked_about_reads_unknown_national_or_club_alike(db, cache, clock,
                                                                             asked):
    """UNKNOWN is the default for every competition, and nothing is inferred from its type.

    One competition is asked about and answers empty. The other covered competition on the same
    date, the asked one on another date, and a competition nobody covers here all stay UNKNOWN -
    whichever of the two kinds was the one asked.
    """
    other = CLUB_KEY if asked == KEY else KEY
    stranded_fixture(db, key=asked, kickoff=TWO_DAYS_BACK)
    scheduler = build(db, cache, clock, ArchiveDouble())

    unattended(scheduler)

    day = TWO_DAYS_BACK.date()
    assert archive(db, asked, day)["state"] == ArchiveState.EMPTY.value
    assert archive(db, other, day)["state"] == ArchiveState.UNKNOWN.value
    assert archive(db, asked, day - timedelta(days=1))["state"] == ArchiveState.UNKNOWN.value
    assert archive(db, NEVER_ASKED_KEY, day)["state"] == ArchiveState.UNKNOWN.value


# ================================================ 5. an outage is an outage, not an answer
def test_a_results_request_that_goes_out_and_fails_is_an_outage_on_the_row(db, cache, clock):
    """
    Five passes in which the results request about the fixture goes out and gets HTTP 503, then
    the archive answers, empty.

    During the outage: no attempt, nothing retired, the fixture stays due every pass (a failed call
    does not move the retry schedule), the archive's state for that date stays UNKNOWN with the
    failure noted beside it, every pass reports itself as failed, and every request that went out
    is charged - the provider billed it whether or not it answered. Afterwards the row, the status
    report and what a reader is served all tell "could not reach" from "had nothing".
    """
    match = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    provider = ArchiveDouble(history_reachable=False)
    scheduler = build(db, cache, clock, provider)

    for n in range(1, 6):
        outcome = unattended(scheduler)["tasks"][TASK_RECOVER]
        assert outcome["ok"] is False, "a pass whose request nobody answered is a failure"
        report = outcome["result"]
        assert report["outcomes"][RecoveryOutcome.PROVIDER_ERROR.value] == 1
        assert report["failed_calls"], "and says which calls failed"
        assert report["results_requests"] == 1, "the request went out, so it was spent"
        assert recovery_requests_today(cache, clock()) == n
        assert retry_due(match, clock()), "an outage does not push the next ask back"
        next_pass(clock)

    row = state(db, match)
    assert row.get("attempts", 0) == 0
    assert not row.get("gave_up_at")
    assert row["provider_errors"] == 5 and row["last_outcome"] == "provider_error"
    assert not row.get("deferrals")
    seen = archive(db, KEY, TWO_DAYS_BACK.date())
    assert seen["state"] == ArchiveState.UNKNOWN.value, "we could not ask, so nothing is known"
    assert seen["last_failed_at"]
    task = scheduler.status()["tasks"][TASK_RECOVER]
    assert task["consecutive_failures"] == 5 and "reached no provider" in task["last_error"]
    assert task["backoff_seconds"] is None, "the repair keeps its cadence through the outage"
    during = serialize_recovery(match.match_metadata)
    assert during["last_outcome"] == "provider_error" and during["provider_errors"] == 5
    assert during["attempts"] is None and during["archive"] is None

    provider.come_back()
    outcome = unattended(scheduler)["tasks"][TASK_RECOVER]

    assert outcome["ok"] is True
    assert scheduler.status()["tasks"][TASK_RECOVER]["consecutive_failures"] == 0
    row = state(db, match)
    assert row["attempts"] == 1 and row["provider_errors"] == 5
    assert archive(db, KEY, TWO_DAYS_BACK.date())["state"] == ArchiveState.EMPTY.value
    after = serialize_recovery(match.match_metadata)
    assert after["last_outcome"] == "fresh_unanswered" and after["archive"]["state"] == "empty"


def test_a_whole_provider_outage_fails_the_pass_and_defers_the_fixture_it_never_asked_about(
        db, cache, clock):
    """
    Every endpoint down for five passes. Each pass's live poll goes out and fails; the cool-down
    that failure sets means the results request about the fixture never leaves.

    So two different facts are written where each is true. The PASS sent a request nobody
    answered, and fails, and the poll is charged to the live ceiling. The FIXTURE was not asked
    about: its row says DEFERRED, not "could not reach the provider", the archive's state for its
    date is untouched - no failure is noted against an archive nobody asked - and nothing is
    charged to the recovery allowance, because no results request was sent.
    """
    match = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    provider = ArchiveDouble(reachable=False)
    scheduler = build(db, cache, clock, provider)
    live_before = live_polls_today(cache, clock())

    for n in range(1, 6):
        outcome = unattended(scheduler)["tasks"][TASK_RECOVER]
        assert outcome["ok"] is False, "the live poll went out and nobody answered it"
        report = outcome["result"]
        assert [c.split(":")[0] for c in report["failed_calls"]] == ["live"]
        assert report["outcomes"][RecoveryOutcome.DEFERRED.value] == 1
        assert report["outcomes"][RecoveryOutcome.PROVIDER_ERROR.value] == 0
        assert report["live_requests"] == 1 and report["results_requests"] == 0
        assert live_polls_today(cache, clock()) == live_before + n, "a failed poll is still a poll"
        assert retry_due(match, clock())
        next_pass(clock)

    assert provider.results_requests == 0, "no results request left during the outage"
    row = state(db, match)
    assert row.get("attempts", 0) == 0 and not row.get("gave_up_at")
    assert row["deferrals"] == 5 and row["last_outcome"] == "deferred"
    assert row["last_deferred_because"] == ["cooling_down"], (
        "a pause after a failed request, not a limit of ours")
    assert not row.get("provider_errors")
    assert "no request was made" in row["last_outcome_detail"]
    seen = archive(db, KEY, TWO_DAYS_BACK.date())
    assert seen["state"] == ArchiveState.UNKNOWN.value and not seen.get("last_failed_at")
    assert recovery_requests_today(cache, clock()) == 0
    served = serialize_recovery(match.match_metadata)
    assert served["last_outcome"] == "deferred" and served["deferrals"] == 5
    assert served["last_deferred_because"] == ["cooling_down"]
    assert served["provider_errors"] == 0, "a reader is not told of a request that was never made"


def test_an_outage_that_carries_a_fixture_past_the_horizon_still_retires_nothing(db, cache, clock):
    """The horizon ends the schedule only after an ANSWERED ask, however old the fixture is.

    A fixture the sweep has been asking about is fourteen days and two hours old and the provider
    is down. It stays selected and due. When the provider answers - empty - it is given up on, and
    the reason separates the answered ask from the failed calls.
    """
    match = stranded_fixture(db, key=KEY, kickoff=clock() - RETRY_HORIZON - timedelta(hours=2))
    MatchRegistry(db).record_recovery_outcome(match, RecoveryOutcome.PROVIDER_ERROR,
                                              "livescore: unreachable", clock() - timedelta(hours=3))
    db.commit()
    provider = ArchiveDouble(history_reachable=False)
    scheduler = build(db, cache, clock, provider)

    for _ in range(3):
        report = recovery(unattended(scheduler))
        assert report["stranded"] == 1 and report["due"] == 1
        next_pass(clock)
    assert not state(db, match).get("gave_up_at")

    provider.come_back()
    recovery(unattended(scheduler))

    row = state(db, match)
    assert row["gave_up_at"] and row["stopped_by"] == "retry_budget"
    assert "asked the results provider 1 time" in row["gave_up_reason"]
    assert "4 other requests went out and got no answer, and are not counted" in row["gave_up_reason"]


# ================================================ 6. the schedule thins out: a simulated week
def test_the_retry_schedule_thins_out_over_a_simulated_week(db, cache, clock):
    """
    WHAT THE BUDGET POLICY COSTS, counted rather than asserted in prose.

    One national-team fixture whose result the archive never returns, with the results and recovery
    tasks both running every half hour for seven days. The retry schedule allows an ask every pass
    until six hours after kickoff, then one every 2 h to a day, 6 h to three days, and 12 h to seven.
    First pass at 2h31: asks at 2h31..5h31 (7) and 7h31..23h31 (9) on day 0; then 4, 4, and 2 a day.

    A flat half-hourly cadence would have asked 336 times this week. The fixture is still being
    asked about at the end of it, because a result can appear days late.
    """
    kickoff = datetime(2026, 9, 24, 16, 1, tzinfo=timezone.utc)
    clock.now = kickoff + FIRST_PASS_AFTER_GRACE
    match = stranded_fixture(db, key=KEY, kickoff=kickoff)
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider, tasks=(TASK_RESULTS, TASK_RECOVER))

    per_day = [0] * 7
    live_per_day = [0] * 7
    passes = 0
    while clock() - kickoff < timedelta(days=7):
        before, live_before = provider.results_requests, provider.live_calls
        unattended(scheduler)
        day = (clock() - kickoff).days
        per_day[day] += provider.results_requests - before
        live_per_day[day] += provider.live_calls - live_before
        passes += 1
        next_pass(clock)

    assert passes == 331
    assert per_day == [16, 4, 4, 2, 2, 2, 2]
    assert sum(per_day) == 32 and provider.requests_for(KEY, kickoff.date()) == 32
    assert state(db, match)["attempts"] == 32
    assert not state(db, match).get("gave_up_at"), "a week in, it is still asked about"
    # The last ask was at 6d 23h31; past seven days the gap is 24 h, so the next is at 7d 23h31.
    assert not retry_due(match, kickoff + timedelta(days=7, hours=12))
    assert retry_due(match, kickoff + timedelta(days=7, hours=23, minutes=31))
    # The recovery pass's live poll is made only when something is due: every pass while the
    # fixture is under six hours old, and with each ask it makes itself once the day is behind the
    # results lookback. It thins out with the same schedule.
    assert live_per_day[0] == 7 and all(n <= 4 for n in live_per_day[1:])
    assert live_per_day[3:] == [2, 2, 2, 2]


# ============================================ 7. stopping is a budget decision, and reversible
def test_stopping_is_reversible_when_the_archive_later_answers_for_that_competition(db, cache, clock):
    """
    A fixture given up on at the end of its schedule is asked about again once the archive
    answers, after we stopped, for its competition on or after its date - and recovered.

    Nothing extra is spent to notice: the observation comes from the results task asking about a
    later fixture in the same competition, which it does anyway.
    """
    old = stranded_fixture(db, key=KEY, kickoff=clock() - RETRY_HORIZON + timedelta(hours=12))
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider, tasks=(TASK_RESULTS, TASK_RECOVER, TASK_SETTLE))

    recovery(unattended(scheduler))
    row = state(db, old)
    assert row["gave_up_at"] and row["stopped_by"] == "retry_budget"
    stopped_reason = row["gave_up_reason"]
    assert "not evidence that no result exists" in stopped_reason
    asked_before = provider.requests_for(KEY, old.match_date.date())

    next_pass(clock)
    recovery(unattended(scheduler))
    assert provider.requests_for(KEY, old.match_date.date()) == asked_before, (
        "a fixture we stopped asking about costs nothing")

    # -- a later fixture in the same competition, and the archive has caught up to both dates.
    later = stranded_fixture(db, key=KEY, kickoff=clock() - timedelta(hours=3))
    provider.publish(final_score(later, KEY))
    provider.publish(final_score(old, KEY))
    next_pass(clock)

    report = recovery(unattended(scheduler))

    db.refresh(later)
    db.refresh(old)
    assert later.status == MatchStatus.FINISHED, "the results task settled the later fixture"
    assert report["reopened"] == [str(old.id)]
    assert old.status == MatchStatus.FINISHED, "and the reopened fixture was asked and recovered"
    row = state(db, old)
    assert row["previous_stops"][-1]["gave_up_reason"] == stopped_reason
    assert later.match_date.date().isoformat() in row["reopened_because"]
    assert not row.get("gave_up_at")


def test_a_reopened_fixture_the_archive_still_lacks_is_stopped_again_and_not_reopened_twice(
        db, cache, clock):
    """Reopening buys one ask. If the archive has moved past the date and still lacks the
    fixture, the sweep stops again, records how far the archive reached, and the same evidence
    does not reopen it a second time."""
    old = stranded_fixture(db, key=KEY, kickoff=clock() - RETRY_HORIZON + timedelta(hours=12))
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider, tasks=(TASK_RESULTS, TASK_RECOVER))
    recovery(unattended(scheduler))
    assert state(db, old)["gave_up_at"]

    later = stranded_fixture(db, key=KEY, kickoff=clock() - timedelta(hours=3))
    provider.publish(final_score(later, KEY))
    next_pass(clock)
    report = recovery(unattended(scheduler))

    assert report["reopened"] == [str(old.id)]
    row = state(db, old)
    assert row["gave_up_at"], "asked once more, answered empty, stopped again"
    assert row["archive_answered_through"] == later.match_date.date().isoformat()
    asked = provider.requests_for(KEY, old.match_date.date())

    for _ in range(3):
        next_pass(clock)
        report = recovery(unattended(scheduler))
        assert report["reopened"] == []
    assert provider.requests_for(KEY, old.match_date.date()) == asked


def test_a_stop_made_under_a_removed_rule_is_undone_not_renamed(db, cache, clock, legacy_shape):
    """
    The rows stopped on 2026-09-24 carry bookkeeping from rules this work removed: the
    three-attempts rule ("no result after 3 attempts") and, on the QA copy, the six-hour stop for
    national-team fixtures. Neither wrote `stopped_by`.

    Such a stop is not attributed to the retry budget, which did not make it, and it does not
    stand under a rule that no longer exists. The first recovery pass takes it off the row - the
    old rule's prose withdrawn, its facts kept - and from then on the fixture is asked about
    exactly when the current schedule says, counting from the answered asks already on the row.
    When the archive answers, it is recovered and its forecast scored.
    """
    match = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    prediction = forecast_on(db, match)
    old = _legacy_stop(db, match, legacy_shape)
    served = serialize_recovery(match.match_metadata)
    assert served["gave_up_at"] and served["stopped_by"] is None, (
        "before it is undone it is served as what it is: a stop no current policy records making")
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider, tasks=(TASK_RESULTS, TASK_RECOVER, TASK_SETTLE))

    report = recovery(unattended(scheduler))

    assert report["stops_undone"] == [str(match.id)]
    row = state(db, match)
    for field in ("gave_up_at", "gave_up_reason", "stopped_by", "last_outcome_detail"):
        assert field not in row, f"{field} belonged to the removed rule"
    for prose in (old.get("gave_up_reason"), old.get("last_outcome_detail")):
        assert prose not in str(match.match_metadata), "the removed rule's conclusions are withdrawn"
    assert row["previous_stops"][-1] == {
        "gave_up_at": old["gave_up_at"], "attempts": old["attempts"], "stopped_by": None,
        "undone_at": clock().isoformat(), "withdrawn": ["gave_up_reason", "last_outcome_detail"]}
    assert row["attempts"] == old["attempts"] and row["last_attempt_at"] == old["last_attempt_at"]

    # -- on the CURRENT schedule: two days after kickoff, one ask per six hours from the last
    # answered ask on the row, which the removed rule made at 22:54 the evening before.
    last = datetime.fromisoformat(old["last_attempt_at"])
    assert report["due"] == 0 and provider.results_requests == 0, "not due again until last + 6 h"
    assert datetime.fromisoformat(row["next_ask_after"]) == last + timedelta(hours=6)
    served = serialize_recovery(match.match_metadata)
    assert served["gave_up_at"] is None and served["stopped_by"] is None
    assert served["next_ask_after"] == (last + timedelta(hours=6)).isoformat().replace("+00:00", "Z")

    provider.publish(final_score(match, KEY))
    while clock() < last + timedelta(hours=6):
        next_pass(clock)
    report = unattended(scheduler)

    db.refresh(match)
    assert match.status == MatchStatus.FINISHED, "asked on the schedule, and recovered"
    assert provider.requests_for(KEY, TWO_DAYS_BACK.date()) == 1
    assert settled(db, prediction).actual_outcome == OUTCOME_HOME


def test_a_removed_rule_s_stop_past_the_horizon_gets_one_answered_ask_then_a_current_stop(
        db, cache, clock):
    """Put back on the schedule means the whole schedule, its end included: a fixture older than
    the horizon is owed one answered ask, and an empty answer then stops it under the current
    policy - recorded as `retry_budget`, because that policy did make this stop."""
    match = stranded_fixture(db, key=KEY, kickoff=clock() - RETRY_HORIZON - timedelta(days=1))
    old = _legacy_stop(db, match, "three_attempts")
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    report = recovery(unattended(scheduler))

    assert report["stops_undone"] == [str(match.id)]
    assert not state(db, match).get("gave_up_at")
    # Past the horizon the gap is 24 h, counted from the last answered ask already on the row.
    last = datetime.fromisoformat(old["last_attempt_at"])
    while clock() < last + timedelta(hours=24):
        assert provider.requests_for(KEY, match.match_date.date()) == 0
        next_pass(clock)
        recovery(unattended(scheduler))

    assert provider.requests_for(KEY, match.match_date.date()) == 1
    row = state(db, match)
    assert row["gave_up_at"] and row["stopped_by"] == "retry_budget"
    assert row["attempts"] == 4
    assert row["previous_stops"][-1]["stopped_by"] is None

    next_pass(clock)
    report = recovery(unattended(scheduler))
    assert report["stops_undone"] == [], "a stop the current policy made stands"
    assert provider.requests_for(KEY, match.match_date.date()) == 1


#: The two shapes a removed rule left behind, as they stand in the databases on 2026-09-25.
LEGACY_STOPS = {
    # soccer_predictions: the three-attempts rule, on eight national-team fixtures from 09-24.
    "three_attempts": {
        "attempts": 3, "gave_up_at": "2026-09-24T22:54:27.881136+00:00",
        "gave_up_reason": "no result after 3 attempts",
        "last_attempt_at": "2026-09-24T22:54:27.881136+00:00",
        "last_outcome": "fresh_unanswered",
        "last_outcome_at": "2026-09-24T22:54:27.881136+00:00",
        "last_outcome_detail": "livescore answered and had no result for it"},
    # soccer_predictions_qa: the six-hour national-team stop, whose prose asserted a provider
    # limitation the archive observations do not show.
    "six_hour_national": {
        "attempts": 1, "gave_up_at": "2026-09-24T23:39:22.829080+00:00",
        "gave_up_reason": ("kickoff is 31 hours old and no endpoint still carries it: this "
                           "competition's archive answers nothing and the live feed's reach is "
                           "the live window, so nothing was asked after 6 hours"),
        "last_attempt_at": "2026-09-24T21:50:51.209810+00:00",
        "last_outcome": "provider_error",
        "last_outcome_at": "2026-09-24T23:39:22.829080+00:00",
        "provider_errors": 1,
        "last_outcome_detail": ("the live feed answered and no longer carries this fixture (31h "
                                "past kickoff, outside the live window), and its competition's "
                                "archive answers nothing"),
        "last_provider_error_at": "2026-09-24T23:39:22.829080+00:00"},
}


@pytest.fixture(params=sorted(LEGACY_STOPS))
def legacy_shape(request):
    return request.param


def _legacy_stop(db, match: Match, shape: str) -> Dict[str, object]:
    """Give `match` the bookkeeping a removed rule wrote when it stopped asking."""
    meta = dict(match.match_metadata)
    meta["recovery"] = dict(LEGACY_STOPS[shape])
    match.match_metadata = meta
    db.commit()
    return dict(meta["recovery"])


def _stop(db, match: Match) -> Dict[str, object]:
    """Give `match` a stop IN FORCE: the bookkeeping the retry schedule writes when it stops."""
    meta = dict(match.match_metadata)
    meta["recovery"] = {"attempts": 3, "gave_up_at": "2026-09-24T22:54:27.881136+00:00",
                        "gave_up_reason": "We asked the results provider 3 times ...",
                        "stopped_by": "retry_budget",
                        "last_attempt_at": "2026-09-24T22:54:27.881136+00:00",
                        "last_outcome": "fresh_unanswered"}
    match.match_metadata = meta
    db.commit()
    return dict(meta["recovery"])


def test_a_stopped_fixture_sharing_a_day_with_a_due_one_is_untouched_unless_the_answer_settles_it(
        db, cache, clock):
    """
    One results call answers for a whole competition-day, so a fixture we stopped asking about can
    be covered by a call made for another. An empty answer leaves its row exactly as it was - it
    was not the one asked about - and an answer that carries its result settles it.
    """
    stopped = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    as_stopped = _stop(db, stopped)
    # Same competition, same date, other teams: one results call answers for both.
    due = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK - timedelta(hours=2),
                           teams=("Eastvale", "Westmoor"))
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    recovery(unattended(scheduler))
    assert state(db, due)["attempts"] == 1
    assert state(db, stopped) == as_stopped, "an answer about the day is not an ask about it"

    provider.publish(final_score(stopped, KEY))
    clock.tick(6 * 3600)
    recovery(unattended(scheduler))

    db.refresh(stopped)
    assert stopped.status == MatchStatus.FINISHED, "the answer carried its result, so it counts"
    assert state(db, stopped)["recovered_as"] == f"{MatchStatus.FINISHED.value} 2-1"
    assert state(db, due)["attempts"] == 2


def test_a_stopped_fixture_whose_own_date_has_since_answered_without_it_is_not_reopened(
        db, cache, clock):
    """The archive answered, after we stopped, for this fixture's own competition and date, and
    the answer did not include it. That answer already covered it; reopening would repeat it."""
    stopped = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    _stop(db, stopped)
    other = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK - timedelta(hours=2),
                             teams=("Eastvale", "Westmoor"))
    provider = ArchiveDouble()
    provider.publish(final_score(other, KEY))
    scheduler = build(db, cache, clock, provider)

    report = recovery(unattended(scheduler))
    db.refresh(other)
    assert other.status == MatchStatus.FINISHED
    assert archive(db, KEY, TWO_DAYS_BACK.date())["state"] == ArchiveState.ANSWERED.value
    asked = provider.requests_for(KEY, TWO_DAYS_BACK.date())

    for _ in range(3):
        next_pass(clock)
        report = recovery(unattended(scheduler))
        assert report["reopened"] == []
    assert provider.requests_for(KEY, TWO_DAYS_BACK.date()) == asked
    assert state(db, stopped)["gave_up_at"]


# ============================================================= 8. budget decisions are not outages
def test_a_due_ask_the_allowance_cannot_cover_is_deferred_not_an_attempt(db, cache, clock,
                                                                         monkeypatch):
    """One results request left today and two competitions due on the same day behind the
    lookback. One is asked; the other is DEFERRED on its row - neither an answer nor an outage -
    and stays due for a later pass."""
    monkeypatch.setattr(settings, "SYNC_RECOVERY_MAX_REQUESTS_PER_DAY", 1)
    national = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    club = stranded_fixture(db, key=CLUB_KEY, kickoff=TWO_DAYS_BACK + timedelta(minutes=5))
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    outcome = unattended(scheduler)["tasks"][TASK_RECOVER]
    report = outcome["result"]

    assert provider.results_requests == 1 and report["results_requests"] == 1
    assert report["deferred"] == [f"{CLUB_KEY}@{TWO_DAYS_BACK.date().isoformat()}"]
    assert state(db, national)["attempts"] == 1
    club_row = state(db, club)
    assert club_row.get("attempts", 0) == 0 and club_row["last_outcome"] == "deferred"
    assert club_row["deferrals"] == 1 and retry_due(club, clock())
    assert club_row["last_deferred_because"] == ["our_allowance"]
    assert report["outcomes"][RecoveryOutcome.DEFERRED.value] == 1
    assert outcome["ok"] is True, "a spent allowance is a budget decision, not an outage"
    assert archive(db, CLUB_KEY, TWO_DAYS_BACK.date())["state"] == ArchiveState.UNKNOWN.value


def test_a_live_poll_refused_by_the_ceiling_is_a_policy_skip_not_an_error(db, cache, clock,
                                                                         monkeypatch):
    """The day's live ceiling is reached, so no live poll is made. The archive is still asked,
    nothing is filed as a provider error, and the pass is healthy."""
    match = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    monkeypatch.setattr(settings, "SYNC_LIVE_MAX_REQUESTS_PER_DAY", 1)
    note_live_poll(cache, clock())
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    outcome = unattended(scheduler)["tasks"][TASK_RECOVER]

    assert provider.live_calls == 0
    assert "ceiling" in outcome["result"]["live_note"]
    assert outcome["result"]["outcomes"][RecoveryOutcome.PROVIDER_ERROR.value] == 0
    assert state(db, match)["attempts"] == 1, "the archive was still asked"
    assert outcome["ok"] is True


# ========================================= 9. the live feed's silence is not evidence either way
def test_a_live_poll_that_does_not_mention_a_fixture_is_not_counted_about_it(db, cache, clock):
    """The live feed answered and did not mention the fixture. How long it keeps a finished match
    is not known, so that silence is no attempt, no error, and no reason to stop."""
    match = stranded_fixture(db, key=KEY, kickoff=KICKOFF)
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    report = recovery(unattended(scheduler))

    assert report["live"]["live_polled"] is True and provider.live_calls == 1
    assert report["outcomes"][RecoveryOutcome.NOT_ASKED.value] == 1
    assert "results lookback" in report["fixtures"][0]["detail"], (
        "its day is the results task's to ask about")
    assert state(db, match) == {}, "nothing happened to the fixture, so nothing is written"


# ================================================================ 10. the task itself
def test_a_repair_pass_that_reached_nobody_is_reported_as_a_failure_but_does_not_back_off(
        db, cache, clock):
    stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    scheduler = build(db, cache, clock, ArchiveDouble(reachable=False))

    outcome = unattended(scheduler)["tasks"][TASK_RECOVER]
    assert outcome["ok"] is False

    task = scheduler.state(TASK_RECOVER)
    assert task["consecutive_failures"] == 1 and task["last_error"]
    assert task["backoff_seconds"] is None
    due = datetime.fromisoformat(task["next_due_at"])
    assert due - clock() == timedelta(seconds=settings.SYNC_RECOVERY_INTERVAL_SECONDS)


def test_a_repair_pass_that_recovered_something_is_a_success(db, cache, clock):
    match = stranded_fixture(db, key=CLUB_KEY, kickoff=TWO_DAYS_BACK)
    provider = ArchiveDouble(reachable=False)
    scheduler = build(db, cache, clock, provider)

    unattended(scheduler)
    assert scheduler.state(TASK_RECOVER)["consecutive_failures"] == 1

    provider.come_back()
    provider.publish(final_score(match, CLUB_KEY))
    next_pass(clock)
    outcome = unattended(scheduler)["tasks"][TASK_RECOVER]

    assert outcome["ok"] is True
    task = scheduler.state(TASK_RECOVER)
    assert task["consecutive_failures"] == 0 and task["last_error"] is None


def test_a_pass_with_nothing_stranded_makes_no_request_at_all(db, cache, clock):
    stranded_fixture(db, key=KEY, kickoff=KICKOFF, status=MatchStatus.FINISHED)
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    report = recovery(unattended(scheduler))

    assert report["stranded"] == 0 and report["requests"] == 0
    assert provider.requests == 0


def test_a_pass_with_nothing_due_makes_no_request_at_all(db, cache, clock):
    """Asked an hour ago, two days after kickoff: the schedule waits six hours between asks."""
    match = stranded_fixture(db, key=CLUB_KEY, kickoff=TWO_DAYS_BACK)
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)
    unattended(scheduler)
    spent = provider.requests

    for _ in range(2):
        next_pass(clock)
        outcome = unattended(scheduler)["tasks"][TASK_RECOVER]
        assert outcome["ok"] is True
        assert outcome["result"]["due"] == 0
        assert outcome["result"]["outcomes"][RecoveryOutcome.NOT_ASKED.value] == 1

    assert provider.requests == spent
    assert state(db, match)["attempts"] == 1


def test_the_recovery_pass_stops_at_its_daily_results_allowance(db, cache, clock, monkeypatch):
    """The day's ceiling binds across passes: the second of two due days waits for tomorrow."""
    monkeypatch.setattr(settings, "SYNC_RECOVERY_MAX_REQUESTS_PER_DAY", 1)
    first = stranded_fixture(db, key=CLUB_KEY, kickoff=KICKOFF - timedelta(days=4))
    second = stranded_fixture(db, key=CLUB_KEY, kickoff=KICKOFF - timedelta(days=3))
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    report = recovery(unattended(scheduler))
    assert report["results_requests"] == 1 and provider.results_requests == 1
    assert state(db, first)["attempts"] == 1
    assert state(db, second)["last_outcome"] == "deferred"

    next_pass(clock)
    report = recovery(unattended(scheduler))
    assert provider.results_requests == 1, "the day's recovery allowance is spent"
    assert report["deferred"], "and the pass says what it did not ask about"
    assert state(db, second).get("attempts", 0) == 0
    assert recovery_requests_today(cache, clock()) == 1


def test_a_results_request_that_went_out_and_failed_is_charged_to_the_days_allowance(
        db, cache, clock):
    """The provider billed the request whether or not it answered, so the recovery allowance is
    charged for it too. An allowance that only counted answers would never bind during an outage,
    which is the one time a repair task runs pass after pass."""
    stranded_fixture(db, key=CLUB_KEY, kickoff=TWO_DAYS_BACK)
    provider = ArchiveDouble(history_reachable=False)
    scheduler = build(db, cache, clock, provider)

    report = recovery(unattended(scheduler))

    assert any(call.startswith("results") for call in report["failed_calls"])
    assert provider.results_requests == 1
    assert report["results_requests"] == 1
    assert recovery_requests_today(cache, clock()) == 1
    assert report["requests"] == 2, "the live poll and the failed results request"


def test_the_repair_poll_takes_no_second_share_of_the_live_ceiling(db, cache, clock):
    stranded_fixture(db, key=KEY, kickoff=KICKOFF)
    scheduler = build(db, cache, clock, ArchiveDouble())
    before = live_polls_today(cache, clock())

    recovery(unattended(scheduler))

    assert live_polls_today(cache, clock()) == before + 1


def test_a_recovery_pass_is_priced_before_it_runs(db, cache, clock):
    """Three hours after kickoff the fixture is due; its day is the results task's, so the pass
    would make only its live poll, and the estimate says so."""
    stranded_fixture(db, key=KEY, kickoff=KICKOFF)
    scheduler = build(db, cache, clock, ArchiveDouble())

    entry = scheduler.estimate(only=[TASK_RECOVER])["tasks"][TASK_RECOVER]

    assert entry["estimated_requests"] == 1
    assert "live poll" in entry["basis"] and "1 due under the retry schedule" in entry["basis"]


def test_a_pass_that_will_undo_a_removed_rule_s_stop_is_priced_with_it(db, cache, clock):
    """The estimate reads the rows without writing, so a stop the pass is about to undo is priced
    as the schedule will treat it once undone: here due, behind the lookback, one results request
    and the live poll - and the estimate makes no request and changes no row."""
    match = stranded_fixture(db, key=KEY, kickoff=TWO_DAYS_BACK)
    old = _legacy_stop(db, match, "three_attempts")
    clock.now = datetime.fromisoformat(old["last_attempt_at"]) + timedelta(hours=7)
    provider = ArchiveDouble()
    scheduler = build(db, cache, clock, provider)

    entry = scheduler.estimate(only=[TASK_RECOVER])["tasks"][TASK_RECOVER]

    assert entry["estimated_requests"] == 2, entry["basis"]
    assert "1 due under the retry schedule" in entry["basis"]
    assert provider.requests == 0
    assert state(db, match) == old, "pricing a pass writes nothing"

    report = recovery(unattended(scheduler))
    assert report["stops_undone"] == [str(match.id)]
    assert provider.requests_for(KEY, TWO_DAYS_BACK.date()) == 1 and provider.live_calls == 1


def test_the_repair_runs_unattended_on_this_installation():
    from app.services import sync_scheduler as module

    assert TASK_RECOVER in module.TASK_NAMES
    assert TASK_RECOVER in [n.strip() for n in settings.SYNC_SCHEDULER_TASKS.split(",")]
    assert module.TASK_NAMES.index(TASK_RECOVER) < module.TASK_NAMES.index(TASK_SETTLE)
    assert module.TASK_NAMES.index(TASK_RECOVER) > module.TASK_NAMES.index(TASK_RESULTS)


# ============================================================== 11. across a UTC midnight
def test_the_rollover_changes_nothing_about_which_fixtures_are_asked_about(db, cache, clock):
    """
    Two fixtures, one of each kind, both before midnight; the clock is 01:30 the next day.

    The club fixture two days back is behind the lookback: the recovery pass asks the archive and
    recovers it. The national fixture from last night is inside the lookback: the results task asks
    the archive about it in the same tick, and it is answered empty. Neither is lost at midnight,
    and neither is treated differently for the kind of competition it is in.
    """
    club = stranded_fixture(db, key=CLUB_KEY, kickoff=TWO_DAYS_BACK)
    national = stranded_fixture(db, key=KEY, kickoff=KICKOFF)
    prediction = forecast_on(db, club)
    provider = ArchiveDouble()
    provider.publish(final_score(club, CLUB_KEY))
    scheduler = build(db, cache, clock, provider, tasks=(TASK_RESULTS, TASK_RECOVER, TASK_SETTLE))

    clock.now = datetime(2026, 9, 25, 1, 30, tzinfo=timezone.utc)
    service = MatchDataService(db, providers=[provider], cache=cache, now=clock(),
                               keys=[KEY, CLUB_KEY])
    assert clock().date() != national.match_date.date()
    assert service._live_window_open() is False
    assert {m.id for m in service.registry.recoverable_unsettled(clock(), service.league_ids())} \
        == {club.id, national.id}

    report = unattended(scheduler)
    recovered = recovery(report)

    db.refresh(club)
    assert club.status == MatchStatus.FINISHED
    assert settled(db, prediction) is not None
    assert recovered["outcomes"][RecoveryOutcome.RECOVERED.value] == 1

    assert state(db, national)["attempts"] == 1, "asked by the results task, answered empty"
    assert archive(db, KEY, KICKOFF.date())["state"] == ArchiveState.EMPTY.value
    assert provider.requests_for(KEY, KICKOFF.date()) == 1
    assert MatchRegistry.overdue_state(national, clock())["overdue"] is True
    assert recovery_requests_today(cache, clock()) == 1


def test_the_live_window_no_longer_shuts_at_midnight_on_a_match_still_being_played(db, cache, clock):
    match = stranded_fixture(db, key=KEY, kickoff=datetime(2026, 9, 24, 23, 50, tzinfo=timezone.utc))
    clock.now = datetime(2026, 9, 25, 0, 20, tzinfo=timezone.utc)
    service = MatchDataService(db, providers=[ArchiveDouble()], cache=cache, now=clock(),
                               keys=[KEY, CLUB_KEY])

    assert match.match_date.date() != clock().date()
    assert service._live_window_open() is True


def test_the_live_window_opens_before_a_kickoff_on_the_other_side_of_midnight(db, cache, clock):
    stranded_fixture(db, key=KEY, kickoff=datetime(2026, 9, 25, 0, 5, tzinfo=timezone.utc),
                     status=MatchStatus.SCHEDULED)
    clock.now = datetime(2026, 9, 24, 23, 50, tzinfo=timezone.utc)
    service = MatchDataService(db, providers=[ArchiveDouble()], cache=cache, now=clock(),
                               keys=[KEY, CLUB_KEY])

    assert service._live_window_open() is True
