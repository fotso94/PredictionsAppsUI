"""
The recovery path, driven through the REAL Live Score provider with the provider's own payloads.

Every other recovery test hands the sweep ready-made `ProviderFixture` objects, so the part of the
path that turns a provider's reply into a stored result - the fixture id that finds the stored
row, `status: "FINISHED"` / `time: "FT"`, the `scores` periods parsed as "N - M", and every field
surviving the cache round trip `_call_chain` puts each answer through - was never exercised on
the way a stranded fixture is actually recovered. Here nothing between the HTTP reply and the
database is a double: `LiveScoreAPIProvider` over an `httpx.MockTransport`, the shipped
`MatchDataService`, `MatchRegistry`, `SyncScheduler` and `SettlementService`, and PostgreSQL.

THE REPLIES ARE THE EVIDENCE, NOT AN IMITATION OF IT.

* docs/evidence/livescore-history-2026-09-16-la-liga.json is served verbatim as the
  `matches/history.json` answer for La Liga on 2026-09-16: its three rows, every key they carry and
  nothing they do not.
* docs/evidence/livescore-world-cup-knockout-scores.json records the score periods of World Cup
  knockout ties as the provider sent them. Its rows are condensed (the team names as strings, no
  competition object), so the Australia v Egypt row is served in the full row shape of the La Liga
  capture - team objects, a competition object, `id`, `fixture_id`, `round` - with the knockout
  file's own values for everything it records: the date, the fixture id, the teams, `status`,
  `time: "AP"` and all five `scores` fields, including `et_score` and `ps_score`. The shape fields
  it does not record (the team ids, the match id, the round) are labelled below as test values.

Neither capture carries a `scheduled` kickoff time, so neither do these replies.

Requires PostgreSQL (the recovery bookkeeping is JSONB on real rows, and settlement reads real
tables). Set TEST_DATABASE_URL; skipped when unreachable. No network: the transport is a mock, and
the provider's competition ids come from the static registry rather than from a list request.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.predictions import Match, MatchResult, MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService, recovery_requests_today
from app.services.match_registry import MatchRegistry, RecoveryOutcome
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.settlement import OUTCOME_DRAW, OUTCOME_HOME
from app.services.sync_scheduler import TASK_RECOVER, TASK_SETTLE, SyncScheduler
from tests.providers.support import FakeRedis, json_response
from tests.services.test_scheduler_recovery import forecast_on, settled
from tests.services.test_sync_scheduler import Clock, LockingFakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

EVIDENCE = Path(__file__).resolve().parents[3] / "docs" / "evidence"
LA_LIGA_CAPTURE = json.loads((EVIDENCE / "livescore-history-2026-09-16-la-liga.json").read_text())
KNOCKOUT_CAPTURE = json.loads((EVIDENCE / "livescore-world-cup-knockout-scores.json").read_text())

LA_LIGA_DAY = date(2026, 9, 16)
#: The fixture the La Liga capture answers with first: Barcelona 7-2 Racing Santander.
BARCELONA_FIXTURE_ID = 1876618
#: The knockout tie: level after 90 minutes and after extra time, decided on penalties.
KNOCKOUT_FIXTURE_ID = 1853401

#: Test values for the shape fields the knockout capture does not record. They only need to agree
#: between the stored fixture and the reply, and they claim nothing about the provider's own ids.
KNOCKOUT_SHAPE = {"id": 900001, "round": "R16", "home_id": 900101, "away_id": 900102}
#: When the stored rows say these matches kicked off. Neither capture records a kickoff time, and
#: the recovery has no business moving whatever the row already holds; these are the stored
#: values it must leave alone, not claims about when either match started.
STORED_KICKOFF = {BARCELONA_FIXTURE_ID: "19:34:00", KNOCKOUT_FIXTURE_ID: "18:00:00"}


# ----------------------------------------------------------------------------- the replies
def la_liga_rows() -> List[Dict]:
    """The La Liga capture's rows, exactly as the provider sent them."""
    assert LA_LIGA_CAPTURE["query"] == {"competition_id": "3", "from": "2026-09-16", "to": "2026-09-16"}
    return copy.deepcopy(LA_LIGA_CAPTURE["rows"])


def knockout_row() -> Dict:
    """The Australia v Egypt row from the knockout capture, in the La Liga capture's row shape."""
    recorded = next(r for r in KNOCKOUT_CAPTURE["rows"] if r["fixture_id"] == KNOCKOUT_FIXTURE_ID)
    assert set(LA_LIGA_CAPTURE["rows"][0]) == {"away", "competition", "date", "fixture_id", "home", "id",
                                                "round", "scores", "status", "time"}
    return {
        "away": {"id": KNOCKOUT_SHAPE["away_id"], "name": recorded["away"]},
        "competition": {"id": int(KNOCKOUT_CAPTURE["query"]["competition_id"]), "name": "World Cup"},
        "date": recorded["date"],
        "fixture_id": recorded["fixture_id"],
        "home": {"id": KNOCKOUT_SHAPE["home_id"], "name": recorded["home"]},
        "id": KNOCKOUT_SHAPE["id"],
        "round": KNOCKOUT_SHAPE["round"],
        "scores": dict(recorded["scores"]),
        "status": recorded["status"],
        "time": recorded["time"],
    }


class LiveScoreReplies:
    """The HTTP side of Live Score: what each endpoint answers, and every request it was sent.

    `history[(competition_id, date)]` is what `matches/history.json` holds. `history_status` makes
    that endpoint answer with an HTTP error instead, which is how a request goes out and fails.
    `matches/live.json` answers with an empty feed: how long it keeps a finished match is not known,
    and nothing here depends on it.
    """

    def __init__(self):
        self.history: Dict[tuple, List[Dict]] = {}
        self.history_status: Optional[int] = None
        self.requests: List[httpx.Request] = []

    def history_requests(self) -> List[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith("matches/history.json")]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params = dict(request.url.params)
        assert params.get("key") == "test-key" and params.get("secret") == "test-secret"
        path = request.url.path
        if path.endswith("matches/live.json"):
            return json_response({"success": True, "data": {"match": []}})
        if path.endswith("matches/history.json"):
            if self.history_status is not None:
                return json_response({"success": False, "error": "Service Unavailable"},
                                     self.history_status)
            assert params["from"] == params["to"], "the sweep asks for one day at a time"
            rows = self.history.get((params["competition_id"], params["from"]), [])
            return json_response({"success": True, "data": {"match": rows, "next_page": False}})
        raise AssertionError(f"unexpected request to {path}")


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
def _no_throttle(monkeypatch):
    """The real client spaces calls a second apart; a test must not wait for that."""
    monkeypatch.setattr("app.services.providers.livescore_api.MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr("app.services.providers.livescore_api.BURST_RETRY_DELAY", 0.0)


@pytest.fixture(autouse=True)
def _covered(monkeypatch):
    monkeypatch.setattr(settings, "COVERED_COMPETITIONS", "la_liga")
    monkeypatch.setattr(settings, "COVERED_NATIONAL_TEAM_COMPETITIONS", "fifa_world_cup")
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 1)


KEYS = ["la_liga", "fifa_world_cup"]


def real_provider(replies: LiveScoreReplies, clock: Callable[[], datetime],
                  daily_limit: int = 1200) -> LiveScoreAPIProvider:
    return LiveScoreAPIProvider(
        api_key="test-key", api_secret="test-secret", transport=httpx.MockTransport(replies),
        budget=RequestBudget("livescore", daily_limit, client=FakeRedis(), now=clock),
        competition_overrides={}, store=MatchCache(client=FakeRedis()), use_default_ids=True)


def build(db, clock: Clock, provider: LiveScoreAPIProvider,
          tasks=(TASK_RECOVER, TASK_SETTLE)) -> SyncScheduler:
    cache = MatchCache(client=LockingFakeRedis(clock=clock))

    def match_factory(_db):
        return MatchDataService(_db, providers=[provider], cache=cache, now=clock(), keys=KEYS)

    scheduler = SyncScheduler(session_factory=lambda: db, cache=cache, now=clock,
                              match_service_factory=match_factory,
                              forecast_service_factory=lambda _db: None,
                              tasks=list(tasks), close_sessions=False)
    scheduler.test_cache = cache
    return scheduler


def stored_from_the_forward_list(db, provider: LiveScoreAPIProvider, row: Dict, key: str,
                                 kickoff_time: Optional[str] = None) -> Match:
    """The fixture as the fixtures task stored it before kickoff, then left reading "LIVE, HT".

    Stored through the real provider's `fixtures/list.json` mapping, so the fixture id, the team
    ids and the competition are linked exactly as they are on a real row; `status` and `minute`
    are then set the way the last live poll before the outage left them.
    """
    scheduled = {
        "id": str(row["fixture_id"]), "date": row["date"],
        "time": kickoff_time or STORED_KICKOFF[row["fixture_id"]],
        "home": row["home"], "away": row["away"], "competition": row["competition"],
        "round": row.get("round"),
    }
    fixture = provider._fixture_from_scheduled(scheduled, [key])
    fixture.competition = provider.list_competitions([key])[0]
    match = MatchRegistry(db).upsert_fixture(fixture)
    assert match is not None
    match.status = MatchStatus.LIVE
    meta = dict(match.match_metadata or {})
    meta.update({"minute": "HT", "provider_status": "halftime"})
    match.match_metadata = meta
    db.commit()
    return match


def recovery_of(report: Dict) -> Dict:
    entry = report["tasks"][TASK_RECOVER]
    assert entry.get("ran") is True, f"the recover task did not run: {entry}"
    return entry["result"]


# ============================================= 1. a league result, from the provider's own reply
def test_a_league_fixture_is_recovered_from_the_archive_s_own_reply(db):
    """
    Barcelona v Racing Santander, stored LIVE at half time, two days behind: the recovery pass asks
    `matches/history.json` for La Liga on 2026-09-16 and is handed the capture verbatim.

    The fixture id finds the stored row; FINISHED/FT settles it; `ft_score` "7 - 2" is the
    regulation score and `et_score`/`ps_score` "" say no extra time was played; the kickoff the
    row already held is left where it was, since the reply carries no kickoff time; and the
    forecast is scored as a home win.
    """
    clock = Clock(start=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc))
    replies = LiveScoreReplies()
    replies.history[("3", "2026-09-16")] = la_liga_rows()
    provider = real_provider(replies, clock)
    barcelona = next(r for r in la_liga_rows() if r["fixture_id"] == BARCELONA_FIXTURE_ID)
    match = stored_from_the_forward_list(db, provider, barcelona, "la_liga")
    kickoff = match.match_date
    prediction = forecast_on(db, match)
    scheduler = build(db, clock, provider)

    report = scheduler.run_once()
    recovered = recovery_of(report)

    db.refresh(match)
    assert [r.url.params["competition_id"] for r in replies.history_requests()] == ["3"]
    assert recovered["outcomes"][RecoveryOutcome.RECOVERED.value] == 1
    assert match.status == MatchStatus.FINISHED
    assert match.match_date == kickoff, "a reply with no kickoff time does not move the kickoff"
    result = db.query(MatchResult).filter(MatchResult.match_id == match.id).one()
    assert (result.home_score, result.away_score) == (7, 2)
    assert (result.home_score_ft, result.away_score_ft) == (7, 2)
    assert (result.home_score_ht, result.away_score_ht) == (4, 1)
    assert result.home_score_et is None and result.home_score_pens is None
    assert result.result_metadata["beyond_regulation"] is False, (
        "an empty et_score/ps_score from this provider means none was played")
    assert result.result_metadata["period_marker"] == "FT"
    assert settled(db, prediction).actual_outcome == OUTCOME_HOME
    assert recovered["results_requests"] == 1 and recovered["live_requests"] == 1


# =================================== 2. a knockout tie settles on regulation time, not penalties
def test_a_knockout_tie_recovered_from_the_archive_settles_on_regulation_time(db):
    """
    Australia v Egypt: 1-1 after 90 minutes, 1-1 after extra time, Egypt through 4-2 on penalties.

    The shoot-out decides the tie and settles nothing. The markets settle on the 90-minute score,
    so the recovered result must carry `ft_score` all the way into `home_score_ft` - through the
    reply, the provider mapping and the cache round trip - and a forecast is scored as the DRAW the
    90 minutes were, not the away win the shoot-out was.
    """
    clock = Clock(start=datetime(2026, 7, 5, 12, 0, tzinfo=timezone.utc))
    replies = LiveScoreReplies()
    row = knockout_row()
    replies.history[("362", row["date"])] = [row]
    provider = real_provider(replies, clock)
    match = stored_from_the_forward_list(db, provider, row, "fifa_world_cup")
    kickoff = match.match_date
    prediction = forecast_on(db, match)
    scheduler = build(db, clock, provider)

    recovered = recovery_of(scheduler.run_once())

    db.refresh(match)
    assert recovered["outcomes"][RecoveryOutcome.RECOVERED.value] == 1
    assert match.status == MatchStatus.FINISHED
    assert match.match_date == kickoff
    result = db.query(MatchResult).filter(MatchResult.match_id == match.id).one()
    assert (result.home_score_ft, result.away_score_ft) == (1, 1), "the 90-minute score survived"
    assert (result.home_score_et, result.away_score_et) == (1, 1)
    assert (result.home_score_pens, result.away_score_pens) == (2, 4)
    assert (result.home_score, result.away_score) == (1, 1)
    assert result.result_metadata["beyond_regulation"] is True
    assert result.result_metadata["period_marker"] == "AP"
    assert result.result_metadata["scoreline"] == "1-1 (2-4 pens)"
    outcome = settled(db, prediction)
    assert outcome is not None, "settled, not withheld for want of a regulation score"
    assert outcome.actual_outcome == OUTCOME_DRAW, "penalties settle nothing"


# ========================== 3. a request that went out and failed is spent: the day's cap binds
def test_a_day_of_http_503_from_the_archive_stops_at_the_recovery_ceiling(db, monkeypatch):
    """
    Five stranded fixtures on five days behind the lookback, and `matches/history.json` answering
    HTTP 503 all day while the live feed answers. Before this was fixed, a request that went out and
    failed was charged nothing, so the day's recovery ceiling never bound: 45 history requests were
    made against a ceiling of 40.

    Every pass, the first history request goes out and fails, the cool-down it sets holds the rest
    of that pass's asks back (deferred, not sent), and the one request that went out is charged.
    Over a whole UTC day of half-hourly passes the archive is sent exactly the ceiling's worth.
    """
    monkeypatch.setattr(settings, "SYNC_RECOVERY_MAX_REQUESTS_PER_DAY", 40)
    clock = Clock(start=datetime(2026, 9, 25, 0, 0, 30, tzinfo=timezone.utc))
    replies = LiveScoreReplies()
    replies.history_status = 503
    provider = real_provider(replies, clock)
    rows = la_liga_rows()
    stranded = []
    for offset, days_back in enumerate((2, 3, 4, 5, 6)):
        row = dict(rows[offset % len(rows)])
        row["fixture_id"] = 7000000 + offset          # test values: five distinct fixtures
        row["date"] = (clock().date() - timedelta(days=days_back)).isoformat()
        stranded.append(stored_from_the_forward_list(db, provider, row, "la_liga",
                                                     kickoff_time="19:00:00"))
    scheduler = build(db, clock, provider, tasks=(TASK_RECOVER,))

    passes = 0
    while clock().date() == date(2026, 9, 25):
        entry = scheduler.run_once()["tasks"][TASK_RECOVER]
        assert entry["ran"] is True
        passes += 1
        clock.tick(settings.SYNC_RECOVERY_INTERVAL_SECONDS)

    assert passes == 48
    assert len(replies.history_requests()) == 40, "every request that went out was charged"
    assert recovery_requests_today(scheduler.test_cache, datetime(2026, 9, 25, 23, 59,
                                                                   tzinfo=timezone.utc)) == 40
    assert provider.budget.granted == 40 + passes, "40 history requests and one live poll a pass"
    for match in stranded:
        db.refresh(match)
        row = MatchRegistry.recovery_state(match)
        assert match.status == MatchStatus.LIVE and not row.get("attempts")
        assert not row.get("gave_up_at"), "an outage retires nothing"
    assert sum(MatchRegistry.recovery_state(m).get("provider_errors") or 0 for m in stranded) == 40
    assert all(MatchRegistry.recovery_state(m).get("deferrals") for m in stranded), (
        "the asks the ceiling and the cool-down held back were deferred, not filed as outages")


# ========================= 4. our own ceiling refusing a call is not a provider that is down
def test_our_own_daily_ceiling_refusing_the_call_is_deferred_and_nothing_is_sent(db):
    """
    One request is left in the daily budget - the ceiling WE configured - and the recovery pass's
    live poll takes it. The results request is then refused before it leaves.

    No results request reaches the provider, so nothing was unreachable: the fixture is DEFERRED
    with the ceiling's own words, no failure is noted against the archive, the pass is not a
    failure, and a reader is never told the provider could not be reached.
    """
    clock = Clock(start=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc))
    replies = LiveScoreReplies()
    replies.history[("3", "2026-09-16")] = la_liga_rows()
    provider = real_provider(replies, clock, daily_limit=5)
    barcelona = next(r for r in la_liga_rows() if r["fixture_id"] == BARCELONA_FIXTURE_ID)
    match = stored_from_the_forward_list(db, provider, barcelona, "la_liga")
    for _ in range(4):
        provider.budget.consume(1, reason="fetch")      # the day's other spending
    scheduler = build(db, clock, provider)

    entry = scheduler.run_once()["tasks"][TASK_RECOVER]
    report = entry["result"]

    assert [r.url.path.rsplit("/", 1)[-1] for r in replies.requests] == ["live.json"]
    assert replies.history_requests() == [], "the results request was refused before it left"
    assert entry["ok"] is True, "a spent allowance is a budget decision, not an outage"
    assert report["failed_calls"] == []
    assert report["outcomes"][RecoveryOutcome.DEFERRED.value] == 1
    assert report["outcomes"][RecoveryOutcome.PROVIDER_ERROR.value] == 0
    assert report["results_requests"] == 0 and report["live_requests"] == 1
    db.refresh(match)
    assert match.status == MatchStatus.LIVE
    row = MatchRegistry.recovery_state(match)
    assert row["last_outcome"] == "deferred" and not row.get("provider_errors")
    assert row.get("attempts", 0) == 0
    assert "refused by the daily ceiling we configured" in row["last_outcome_detail"]
    assert row["last_deferred_because"] == ["our_allowance"], "our limit, and said to be ours"
    assert MatchRegistry(db).archive_observation("la_liga", LA_LIGA_DAY).get("last_failed_at") is None


def test_the_provider_s_own_reported_window_refusing_the_call_is_deferred_as_theirs(db):
    """
    The provider's last response said its own window has nothing left, while our daily counter
    still shows room. Both of the pass's calls are refused before they leave - the refusal is the
    provider's accounting, not our ceiling - so nothing is sent, the fixture is DEFERRED, and the
    row says whose limit it was: the provider's, never "our own request allowance".
    """
    from app.services.providers.http import RateLimitReading

    clock = Clock(start=datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc))
    replies = LiveScoreReplies()
    replies.history[("3", "2026-09-16")] = la_liga_rows()
    provider = real_provider(replies, clock)
    barcelona = next(r for r in la_liga_rows() if r["fixture_id"] == BARCELONA_FIXTURE_ID)
    match = stored_from_the_forward_list(db, provider, barcelona, "la_liga")
    provider.budget.rate_limit.record(RateLimitReading(
        provider="livescore", limit=1200, remaining=0, reset_seconds=3 * 3600,
        observed_at=clock(), status_code=200))
    scheduler = build(db, clock, provider)
    scheduler._budget_block = lambda services, name: None   # our counter has room; theirs does not

    entry = scheduler.run_once()["tasks"][TASK_RECOVER]
    report = entry["result"]

    assert replies.requests == [], "nothing was sent"
    assert entry["ok"] is True and report["failed_calls"] == []
    assert report["outcomes"][RecoveryOutcome.DEFERRED.value] == 1
    assert "no request was sent" in report["live_note"]
    db.refresh(match)
    row = MatchRegistry.recovery_state(match)
    assert row["last_outcome"] == "deferred" and not row.get("provider_errors")
    assert row["last_deferred_because"] == ["provider_allowance"]
