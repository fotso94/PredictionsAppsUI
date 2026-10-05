"""
A provider that cannot be asked about a competition has not answered for it.

THE DEFECT THIS PINS. API-Football and TheSportsDB hold an id for the six club competitions and
for none of the 29 national-team ones. Their `get_results` skipped a competition they had no id
for and returned what they had for the rest - for a national-team competition, an empty list,
with no request sent - and the call chain took that list as an answer. So whenever Live Score was
out of the chain (cooling down after a failure, and since 2026-10-05 refusing every request with
HTTP 401) the results and recovery passes wrote "api_football answered for this competition on
<day> with 0 row(s)" onto national-team fixtures nobody had asked about: an attempt spent, the
retry schedule pushed back a day, and an EMPTY archive observation written over whatever the
archive had really said. The application's own record shows it on 2026-10-02 (API-Football at
08:12 UTC, TheSportsDB at 08:43) and on every pass from 2026-10-05 03:23 UTC.

WHAT MUST HOLD INSTEAD:
  * a provider is asked only about the competitions it can name (`MatchDataProvider.askable`);
  * one that can name none of them is passed over the way any provider that sent nothing is -
    no cool-down, no failure on its status, nothing charged - and the chain moves on;
  * an answer speaks only for the competitions it was asked about; the rest go on down the chain;
  * when no provider can be asked, the fixture's row says so (DEFERRED, "not_served" among the
    reasons), its attempts and retry schedule stay exactly where they were, and no archive
    observation is written;
  * what was spent is what was sent: a competition nobody could name reserves nothing, and a
    provider with no budget to read is charged for the competitions it was actually asked about.

The scenario tests drive the shipped scheduler over the REAL API-Football and TheSportsDB classes,
on mock transports that record every request, behind a Live Score double inside the 30-minute
cool-down its 401 sets. Those need PostgreSQL (TEST_DATABASE_URL; skipped when unreachable); the
rest need nothing. No network.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.predictions import Match, MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    AUTH_COOLDOWN_SECONDS, COOLDOWN_KEY, MatchDataService, SyncMeta,
)
from app.services.match_registry import (
    ArchiveState, MatchRegistry, RecoveryOutcome, classify_recovery_outcome, retry_due,
)
from app.services.providers import competitions as comps
from app.services.providers.api_football_provider import APIFootballProvider
from app.services.providers.base import (
    STATUS_HALFTIME, MatchDataProvider, ProviderAuthError, ProviderCompetition, ProviderFixture,
    ProviderStanding, ProviderTeam, parse_utc,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.providers.sample import SampleDataProvider
from app.services.providers.thesportsdb_provider import TheSportsDBProvider
from app.services.sync_scheduler import TASK_RECOVER, TASK_RESULTS, SyncScheduler
from tests.providers.support import FakeRedis, Recorder, json_response, make_transport
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

NATIONAL = "national_teams_friendlies"
CLUB = "premier_league"
#: What Live Score has answered to every request since 2026-10-05 03:23 UTC.
REFUSAL = ("livescore: authentication rejected (HTTP 401): This API key and secret do not have "
           "access to our data enabled")
#: The stranded day: behind the one-day results lookback once `PASS_AT` is the time.
KICKOFF = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
DAY = KICKOFF.date()
#: Two days and three hours on, which is the recovery pass's territory and not the results task's.
PASS_AT = KICKOFF + timedelta(days=2, hours=3)
LIVESCORE_IDS = {NATIONAL: "371", CLUB: "2"}
#: Invented teams: nothing here models a real match's score.
TEAMS = {NATIONAL: ("Northland", "Southmark"), CLUB: ("Riverside Town", "Hillcrest United")}


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


@pytest.fixture(autouse=True)
def _covered(monkeypatch):
    monkeypatch.setattr(settings, "COVERED_COMPETITIONS", CLUB)
    monkeypatch.setattr(settings, "COVERED_NATIONAL_TEAM_COMPETITIONS", NATIONAL)
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 1)


# ----------------------------------------------------------------------------- the providers
class RefusedLiveScore(MatchDataProvider):
    """Live Score as it has answered since 2026-10-05 03:23 UTC: HTTP 401 to every request."""

    name = "livescore"
    integration_status = "primary"

    def __init__(self):
        self.calls: List[str] = []

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def _refuse(self, endpoint: str):
        self.calls.append(endpoint)
        raise ProviderAuthError(REFUSAL, provider=self.name, status_code=401)

    def get_fixtures(self, day, keys):
        self._refuse("fixtures")

    def get_live(self, keys):
        self._refuse("live")

    def get_results(self, date_from, date_to, keys):
        self._refuse("results")

    def get_standings(self, key):
        self._refuse("standings")


def api_football(redis, clock: Optional[Callable[[], datetime]] = None
                 ) -> Tuple[APIFootballProvider, Recorder]:
    """The REAL API-Football class over a recording transport.

    It answers the two requests its free plan has been seen to answer - the live poll and a club
    league's fixtures - with nothing in them. Anything else gets a 500, so a request this test does
    not expect cannot pass for an answer; the recorder is what each test reads.
    """
    club_league = str(comps.get(CLUB).api_football_id)

    def handler(request):
        params = dict(request.url.params)
        if "live" in params or params.get("league") == club_league:
            return json_response({"response": [], "errors": []})
        return json_response({"message": "not modelled by this test"}, status_code=500)

    transport, recorder = make_transport(handler)
    return APIFootballProvider(api_key="test-api-football-key", transport=transport,
                               budget=RequestBudget("api_football", 90, client=redis, now=clock)), recorder


def thesportsdb(redis, clock: Optional[Callable[[], datetime]] = None
                ) -> Tuple[TheSportsDBProvider, Recorder]:
    """The REAL TheSportsDB class over a recording transport that answers every request empty."""
    transport, recorder = make_transport(lambda request: json_response({"events": []}))
    return TheSportsDBProvider(api_key="test-thesportsdb-key", transport=transport,
                               budget=RequestBudget("thesportsdb", 1000, client=redis, now=clock)), recorder


class NationalSource(MatchDataProvider):
    """A provider further down a chain that DOES hold an id for the national-team competition."""

    name = "national_source"
    integration_status = "test"

    def __init__(self):
        self.standings_asked: List[str] = []

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def get_fixtures(self, day, keys):
        return []

    def get_live(self, keys):
        return []

    def get_results(self, date_from, date_to, keys):
        return []

    def get_standings(self, key):
        self.standings_asked.append(key)
        return [ProviderStanding(position=1, points=3, team=ProviderTeam(
            provider=self.name, external_id="n-1", name=TEAMS[NATIONAL][0]))]


class ClubOnly(MatchDataProvider):
    """A provider with NO budget to read that holds an id for the club competition alone."""

    name = "club_only"
    integration_status = "test"

    def __init__(self):
        self.results_asked: List[Tuple[str, ...]] = []

    def askable(self, keys):
        return [key for key in keys if key == CLUB]

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys):
        return []

    def get_fixtures(self, day, keys):
        return []

    def get_live(self, keys):
        return []

    def get_results(self, date_from, date_to, keys):
        self.results_asked.append(tuple(keys))
        return []

    def get_standings(self, key):
        return []


class NoIds(ClubOnly):
    """A provider with no budget to read that holds an id for nothing that is asked of it."""

    name = "no_ids"

    def askable(self, keys):
        return []


def cooling_down(cache: MatchCache) -> None:
    """Live Score inside the 30-minute cool-down its 401 sets, as on every pass since 03:23 UTC."""
    cache.set(COOLDOWN_KEY.format(name="livescore"),
              {"reason": REFUSAL, "until_seconds": AUTH_COOLDOWN_SECONDS, "cause": "failure"},
              ttl=AUTH_COOLDOWN_SECONDS, stale_ttl=AUTH_COOLDOWN_SECONDS)


# ----------------------------------------------------------------------------- the harness
def stranded(db, key: str, kickoff: datetime, *, recovery: Optional[Dict] = None) -> Match:
    """A fixture stored as still being played, written the way a live poll writes it."""
    home, away = TEAMS[key]

    def team(name: str) -> ProviderTeam:
        return ProviderTeam(provider="livescore", name=name,
                            external_id="ls-" + "".join(c for c in name.lower() if c.isalnum()))

    fixture = ProviderFixture(
        provider="livescore", external_id=f"ls-{key}-{uuid.uuid4().hex[:8]}",
        competition=ProviderCompetition(provider="livescore", external_id=LIVESCORE_IDS[key],
                                        name=comps.get(key).name, key=key),
        home=team(home), away=team(away), kickoff_utc=kickoff, status=STATUS_HALFTIME)
    match = MatchRegistry(db).upsert_fixture(fixture)
    assert match is not None
    match.status = MatchStatus.LIVE
    if recovery is not None:
        match.match_metadata = {**(match.match_metadata or {}), "recovery": recovery}
    db.commit()
    return match


def scheduler(db, cache: MatchCache, clock: Clock, providers: List[MatchDataProvider],
              task: str) -> SyncScheduler:
    """The shipped scheduler over a real service, registry and database."""
    def match_factory(_db):
        return MatchDataService(_db, providers=providers, cache=cache, now=clock(), keys=[CLUB, NATIONAL])

    return SyncScheduler(session_factory=lambda: db, cache=cache, now=clock,
                         match_service_factory=match_factory, forecast_service_factory=lambda _db: None,
                         tasks=[task], close_sessions=False, budget_client=cache._redis())


def state(db, match: Match) -> Dict[str, object]:
    db.refresh(match)
    return MatchRegistry.recovery_state(match)


def archive(db, key: str, day: date) -> Dict[str, object]:
    return MatchRegistry(db).archive_observation(key, day)


def results_asked(recorder: Recorder) -> List[Dict[str, str]]:
    """API-Football's results requests: every `/fixtures` call that is not the live poll."""
    return [dict(r.url.params) for r in recorder.requests if "live" not in r.url.params]


# ============================================== 1. who can be asked about what, before anything is sent
def test_the_fallbacks_can_be_asked_about_the_club_competitions_and_no_national_team_one():
    """The registry gives API-Football and TheSportsDB an id for each club competition and for no
    national-team competition, so that is exactly what each says it can be asked about - in the
    order it was handed the keys, and without a request to find out."""
    national = comps.select_keys(national_teams=True)
    club = list(comps.DEFAULT_COVERED_KEYS)
    redis = FakeRedis()
    af, af_requests = api_football(redis)
    tsdb, tsdb_requests = thesportsdb(redis)

    assert af.askable(national + club) == club
    assert tsdb.askable(club + national) == club
    assert af.askable(national) == [] and tsdb.askable(national) == []
    assert SampleDataProvider().askable(national + club) == club, "it has invented teams for these six"
    assert af_requests.requests == [] and tsdb_requests.requests == []


def test_live_score_can_be_asked_about_every_competition_it_can_name_and_only_those(monkeypatch):
    """Live Score names a competition by an id from the registry, an override or its catalogue.

    With the registry's ids every covered competition is askable and nothing is sent to decide it.
    One it cannot name at all - no default, no override, not in the catalogue it was handed - is
    left out rather than "asked" and answered with nothing.
    """
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)
    covered = list(comps.DEFAULT_COVERED_KEYS) + [NATIONAL]
    transport, recorder = make_transport(lambda request: json_response(
        {"success": True, "data": {"competition": [], "next_page": False}}))
    with_defaults = LiveScoreAPIProvider(
        api_key="test-key", api_secret="test-secret", transport=transport,
        budget=RequestBudget("livescore", 1200, client=FakeRedis()), competition_overrides={},
        store=MatchCache(client=FakeRedis()), use_default_ids=True)
    assert with_defaults.askable(covered) == covered
    assert recorder.requests == [], "every covered competition has a registry id"

    override_only = LiveScoreAPIProvider(
        api_key="test-key", api_secret="test-secret", transport=transport,
        budget=RequestBudget("livescore", 1200, client=FakeRedis()),
        competition_overrides={CLUB: "2"}, store=MatchCache(client=FakeRedis()), use_default_ids=False)
    assert override_only.askable([NATIONAL, CLUB]) == [CLUB]


# ======================================== 2. a provider that cannot be asked is passed over, not believed
def test_a_fixtures_call_no_provider_can_be_asked_about_is_not_an_empty_calendar():
    """Neither fallback can name a national-team competition, so neither is asked and nobody
    answered: the forward list is UNANSWERED, never an empty day, and nothing was spent."""
    redis = FakeRedis()
    af, af_requests = api_football(redis)
    tsdb, tsdb_requests = thesportsdb(redis)
    service = MatchDataService(MagicMock(), providers=[af, tsdb], cache=MatchCache(client=FakeRedis()),
                               now=PASS_AT, keys=[CLUB, NATIONAL])

    meta = service.sync_day(PASS_AT.date() + timedelta(days=3), keys=[NATIONAL])

    assert af_requests.requests == [] and tsdb_requests.requests == []
    assert meta.forward_source is None, "nobody answered, so nothing is known about that day"
    assert meta.source == "database" and meta.provider is None
    assert meta.not_sent == ["not_served", "not_served"]
    assert [reason.split(":")[0] for reason in meta.declined] == ["api_football", "thesportsdb"]
    assert meta.errors == ["; ".join(meta.declined)], "the day went unanswered, and says why once"
    assert meta.requests == 0


def test_a_fixtures_call_asks_each_provider_only_about_what_it_can_name():
    """A mixed day: API-Football answers for the club competition alone. The national-team one
    is left out of its request, and the meta says so - beside the errors, not among them."""
    redis = FakeRedis()
    af, af_requests = api_football(redis)
    service = MatchDataService(MagicMock(), providers=[af], cache=MatchCache(client=FakeRedis()),
                               now=PASS_AT, keys=[CLUB, NATIONAL])

    meta = service.sync_day(PASS_AT.date() + timedelta(days=3), keys=[CLUB, NATIONAL])

    assert [dict(r.url.params).get("league") for r in af_requests.requests] == [
        str(comps.get(CLUB).api_football_id)]
    assert meta.forward_source == "provider" and meta.errors == []
    assert meta.declined == [f"api_football: not asked about {NATIONAL}: it holds no competition id "
                             f"for it, so no request could name it"]


def test_a_live_poll_only_thesportsdb_could_take_is_not_a_poll():
    """TheSportsDB's v1 API publishes no live scores. Reached with every provider ahead of it out,
    it handed back an empty list, recorded as a poll that found nothing in play - by a provider
    that sent no request. Now the poll is unanswered, and says why."""
    tsdb, tsdb_requests = thesportsdb(FakeRedis())
    service = MatchDataService(MagicMock(), providers=[tsdb], cache=MatchCache(client=FakeRedis()),
                               now=PASS_AT, keys=[CLUB, NATIONAL])
    meta = SyncMeta()

    service._sync_live(meta, require_window=False)

    assert meta.live_polled is False and meta.provider is None
    assert meta.not_sent == ["not_served"] and tsdb_requests.requests == []
    assert meta.errors == ["live: thesportsdb: not asked for live scores: its v1 API publishes none"]


def test_a_meta_holding_only_providers_that_could_not_be_asked_is_a_deferral():
    """Nothing was sent and something was due: DEFERRED, never NOT_ASKED and never an outage."""
    meta = SyncMeta(not_sent=["not_served"], declined=["api_football: not asked about it"])

    outcome, detail = classify_recovery_outcome(meta, settled_before=False, settled_now=False)

    assert outcome is RecoveryOutcome.DEFERRED
    assert "api_football: not asked about it" in detail


def test_standings_no_provider_can_be_asked_for_are_unknown_not_an_empty_table():
    """A capability gap is not a failure: neither provider is put in cool-down or shown as failing,
    and the empty table is reported as nobody's answer rather than as API-Football's."""
    redis = FakeRedis()
    af, af_requests = api_football(redis)
    tsdb, tsdb_requests = thesportsdb(redis)
    service = MatchDataService(MagicMock(), providers=[af, tsdb], cache=MatchCache(client=FakeRedis()),
                               now=PASS_AT, keys=[CLUB, NATIONAL])

    rows, meta = service.standings(NATIONAL)

    assert rows == [] and meta.source == "database" and meta.provider is None
    assert af_requests.requests == [] and tsdb_requests.requests == []
    assert service._cooldown("api_football") is None and service._cooldown("thesportsdb") is None
    chain = {entry["name"]: entry for entry in service.provider_status()["chain"]}
    assert chain["api_football"].get("last_error") is None
    assert chain["thesportsdb"].get("last_error") is None


def test_the_chain_moves_on_past_a_provider_that_cannot_be_asked():
    """The next provider that CAN be asked answers, and only it is charged for the call."""
    redis = FakeRedis()
    af, af_requests = api_football(redis)
    source = NationalSource()
    service = MatchDataService(MagicMock(), providers=[af, source], cache=MatchCache(client=FakeRedis()),
                               now=PASS_AT, keys=[CLUB, NATIONAL])

    rows, meta = service.standings(NATIONAL)

    assert [row.team.name for row in rows] == [TEAMS[NATIONAL][0]]
    assert meta.provider == "national_source" and meta.source == "provider"
    assert source.standings_asked == [NATIONAL]
    assert meta.not_sent == ["not_served"]
    assert af_requests.requests == [] and af.budget.granted == 0
    assert meta.requests == 1, "the provider that answered keeps no budget: one call, one request"
    assert service._cooldown("api_football") is None


# ===================================== 3. the reported pass, end to end through the shipped scheduler
def test_a_recovery_pass_no_provider_can_serve_records_no_answer_and_moves_nothing(db):
    """
    The pass of 2026-10-05 03:54 UTC: Live Score cooling down after its 401, a National Teams
    Friendlies fixture from 28 September due its next ask, 24 answered asks behind it, and an
    archive that last ANSWERED for that date with six rows.

    Before the fix that pass recorded "api_football answered for this competition on 2026-09-28
    with 0 row(s)": a 25th attempt, the next ask a day later, and the archive's ANSWERED overwritten
    with EMPTY - from a provider that sent nothing, holding no id to send it with. Now: nothing was
    asked, so nothing is recorded as asked.
    """
    clock = Clock(start=PASS_AT)
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    cooling_down(cache)
    last_asked = PASS_AT - timedelta(hours=25)
    match = stranded(db, NATIONAL, KICKOFF, recovery={
        "attempts": 24, "first_attempt_at": (KICKOFF + timedelta(hours=2, minutes=40)).isoformat(),
        "last_attempt_at": last_asked.isoformat(), "last_outcome": "fresh_unanswered",
        "last_outcome_at": last_asked.isoformat(),
        "last_outcome_detail": ("livescore answered for this competition on 2026-09-28 with 6 row(s), "
                                "none of them a result for this match"),
        "archive": {"state": "answered", "rows": 6, "asked_at": last_asked.isoformat()}})
    MatchRegistry(db).record_archive_observation(NATIONAL, DAY, 6, provider="livescore", asked_at=last_asked)
    db.commit()
    archive_before = archive(db, NATIONAL, DAY)
    assert retry_due(match, clock()), "the fixture is due an ask on this pass"
    livescore = RefusedLiveScore()
    af, af_requests = api_football(redis, clock)
    tsdb, tsdb_requests = thesportsdb(redis, clock)

    outcome = scheduler(db, cache, clock, [livescore, af, tsdb], TASK_RECOVER).run_once()["tasks"][TASK_RECOVER]
    report = outcome["result"]

    # -- what was sent: the live poll, at the one provider that can poll, and nothing else.
    assert livescore.calls == [], "Live Score was cooling down; nothing was sent to it"
    assert [r.url.params.get("live") for r in af_requests.requests] == [str(comps.get(CLUB).api_football_id)]
    assert results_asked(af_requests) == [], "API-Football holds no id for the competition"
    assert tsdb_requests.requests == []
    assert report["results_requests"] == 0 and report["live_requests"] == 1

    # -- the fixture: not asked, so no attempt, and the schedule exactly where it was.
    row = state(db, match)
    assert row["attempts"] == 24
    assert row["last_attempt_at"] == last_asked.isoformat()
    assert row["last_outcome"] == RecoveryOutcome.DEFERRED.value and row["deferrals"] == 1
    assert {"cooling_down", "not_served"} <= set(row["last_deferred_because"])
    detail = row["last_outcome_detail"]
    assert "no request was made" in detail
    assert "api_football" in detail and "thesportsdb" in detail
    assert "answered for this competition" not in detail, "the row may not say anybody answered"
    assert row["archive"] == {"state": "answered", "rows": 6, "asked_at": last_asked.isoformat()}
    assert retry_due(match, clock()), "nothing was asked, so it is still due"
    assert parse_utc(row["next_ask_after"]) <= clock()

    # -- the archive: what Live Score last said for that date is still what it says.
    assert archive(db, NATIONAL, DAY) == archive_before
    assert archive_before["state"] == ArchiveState.ANSWERED.value and archive_before["rows"] == 6

    # -- and the pass says the same thing about itself.
    day = report["days"][DAY.isoformat()]
    assert day["call"] == "deferred" and day["requests"] == 0
    assert day["source"] == "database" and day["provider"] is None and day["results_polled"] is False
    assert report["outcomes"][RecoveryOutcome.DEFERRED.value] == 1
    assert report["outcomes"][RecoveryOutcome.FRESH_UNANSWERED.value] == 0
    assert report["deferred"] == [f"{NATIONAL}@{DAY.isoformat()}"]
    assert report["archive"] == {}
    assert report["failed_calls"] == [] and outcome["ok"] is True


def test_the_results_task_records_nothing_for_a_competition_no_provider_could_be_asked_about(db):
    """The same defect inside the results lookback: on 2026-10-05 the results task wrote three
    "answered" attempts on every 2 and 3 October national-team fixture while no provider that
    could name them was in the chain. Now the day is unanswered and the fixture untouched."""
    kickoff = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    clock = Clock(start=kickoff + timedelta(hours=3))
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    cooling_down(cache)
    match = stranded(db, NATIONAL, kickoff)
    af, af_requests = api_football(redis, clock)
    tsdb, tsdb_requests = thesportsdb(redis, clock)

    outcome = scheduler(db, cache, clock, [RefusedLiveScore(), af, tsdb], TASK_RESULTS).run_once()["tasks"][TASK_RESULTS]

    day = outcome["result"]["days"][kickoff.date().isoformat()]
    assert day["requests"] == 0 and day["results_polled"] is False
    assert day["source"] == "database" and day["provider"] is None
    assert af_requests.requests == [] and tsdb_requests.requests == []
    row = state(db, match)
    assert row.get("attempts", 0) == 0 and not row.get("last_attempt_at")
    assert row["last_outcome"] == RecoveryOutcome.DEFERRED.value
    assert "not_served" in row["last_deferred_because"]
    assert archive(db, NATIONAL, kickoff.date())["state"] == ArchiveState.UNKNOWN.value


def test_an_answer_counts_for_the_competitions_it_was_asked_about_and_no_other(db):
    """
    A club and a national-team fixture stranded on the same day, in one results call.

    API-Football can name the club competition and is asked about it alone: its empty answer is
    an attempt on the club fixture and an EMPTY observation for the club competition, both true.
    The national-team competition goes on down the chain, where nobody can name it either, and is
    deferred without an attempt or an observation. Reserved equals sent: two requests, both real.
    """
    clock = Clock(start=PASS_AT)
    redis = LockingFakeRedis(clock=clock)
    cache = MatchCache(client=redis)
    cooling_down(cache)
    national = stranded(db, NATIONAL, KICKOFF)
    club = stranded(db, CLUB, KICKOFF + timedelta(hours=3))
    af, af_requests = api_football(redis, clock)
    tsdb, tsdb_requests = thesportsdb(redis, clock)

    outcome = scheduler(db, cache, clock, [RefusedLiveScore(), af, tsdb], TASK_RECOVER).run_once()["tasks"][TASK_RECOVER]
    report = outcome["result"]

    club_league = str(comps.get(CLUB).api_football_id)
    assert [asked.get("league") for asked in results_asked(af_requests)] == [club_league]
    assert tsdb_requests.requests == []
    assert af.budget.used_today() == len(af_requests.requests) == 2, "the live poll and one results request"
    assert report["results_requests"] == 1

    club_row, national_row = state(db, club), state(db, national)
    assert club_row["last_outcome"] == RecoveryOutcome.FRESH_UNANSWERED.value and club_row["attempts"] == 1
    assert club_row["last_outcome_detail"].startswith(
        f"api_football answered for this competition on {DAY.isoformat()} with 0 row(s)")
    seen = archive(db, CLUB, DAY)
    assert seen["state"] == ArchiveState.EMPTY.value and seen["provider"] == "api_football"

    assert national_row["last_outcome"] == RecoveryOutcome.DEFERRED.value
    assert national_row.get("attempts", 0) == 0
    assert "not_served" in national_row["last_deferred_because"]
    assert archive(db, NATIONAL, DAY)["state"] == ArchiveState.UNKNOWN.value

    day = report["days"][DAY.isoformat()]
    assert day["calls"] == {CLUB: "answered", NATIONAL: "deferred"}
    assert day["call"] == "mixed"
    assert report["deferred"] == [f"{NATIONAL}@{DAY.isoformat()}"]
    assert set(report["archive"]) == {f"{CLUB}@{DAY.isoformat()}"}
    assert report["failed_calls"] == [] and outcome["ok"] is True


# ============================================================== 4. what was spent is what was sent
def test_a_provider_with_no_budget_is_charged_for_the_competitions_it_was_asked_about(db):
    """`cost_hint` stands in for a budget that cannot be read: one request per competition the
    call named. A call that named one of the two competitions it was handed cost one request."""
    provider = ClubOnly()
    stranded(db, NATIONAL, KICKOFF)
    stranded(db, CLUB, KICKOFF + timedelta(hours=3))
    service = MatchDataService(db, providers=[provider], cache=MatchCache(client=FakeRedis()),
                               now=PASS_AT, keys=[CLUB, NATIONAL])
    meta = SyncMeta()

    called = service._sync_results(DAY, meta)

    assert provider.results_asked == [(CLUB,)]
    assert meta.requests == 1
    assert called == "mixed"


def test_a_provider_that_can_be_asked_about_nothing_is_charged_nothing(db):
    provider = NoIds()
    match = stranded(db, NATIONAL, KICKOFF)
    service = MatchDataService(db, providers=[provider], cache=MatchCache(client=FakeRedis()),
                               now=PASS_AT, keys=[CLUB, NATIONAL])
    meta = SyncMeta()

    called = service._sync_results(DAY, meta)

    assert called == "deferred"
    assert provider.results_asked == [] and meta.requests == 0
    assert meta.not_sent == ["not_served"] and meta.request_failed is False
    row = state(db, match)
    assert row["last_outcome"] == RecoveryOutcome.DEFERRED.value and row.get("attempts", 0) == 0
    assert row["last_deferred_because"] == ["not_served"]
