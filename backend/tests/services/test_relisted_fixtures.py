"""
One match its provider listed twice, the other way round: closed where it stands, never merged.

THE INCIDENT, AS THE STORED ROWS RECORD IT. Live Score listed the AFCON qualifier Senegal v
Mozambique for 2026-09-25 19:00 UTC at the Stade Léopold Sédar Senghor (fixture 1899816). From
06:18 that morning it listed Mozambique v Senegal, 13:00 UTC at the Estádio Nacional do Zimpeto
(1902057), and stopped listing 1899816: every other qualifier of the day kept being re-synced and
that one never was. 1902057 finished 1-1. The sync stored both rows, so the old one read
"scheduled" from then on, and by 2026-10-05 the recovery sweep had asked a results provider about
it 31 times. No team plays twice in a day.

THE REPLIES ARE LIVE SCORE'S SHAPES CARRYING THE STORED VALUES. A `fixtures/list.json` row has the
keys `LiveScoreAPIProvider._fixture_from_scheduled` reads; a `matches/history.json` row has exactly
the keys of the captured archive row in docs/evidence/livescore-history-2026-09-16-la-liga.json.
Every value in them - fixture, team and competition ids, names, kickoffs, venues, round, scores - is
the one predictions.matches, match_results and provider_entity_refs hold for these fixtures. The
archive's own match id (`id` on a history row) was never stored, and is a labelled test value. Sudan
v Ethiopia, the group's other fixture that matchday, rides along as a fixture the rule must leave
alone.

Requires PostgreSQL. Set TEST_DATABASE_URL; skipped when unreachable. No network: the transport is
a mock and the competition id comes from the static registry.
"""

from __future__ import annotations

import copy
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.predictions import (
    Match, MatchResult, MatchStatus, Prediction, PredictionOutcome, PredictionResult,
    PredictionSource, PredictionStatus,
)
from app.models.users import AccountStatus, User, UserType
from app.schemas.matches import serialize_match
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.match_registry import RELISTED_KEY, UNSETTLED_GRACE, MatchRegistry
from app.services.providers.budget import RequestBudget
from app.services.providers.livescore_api import LiveScoreAPIProvider
from app.services.settlement import RELISTED_VOID_REASON, SettlementService
from tests.providers.support import FakeRedis, json_response

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

AFCON_Q = "africa_cup_of_nations_qualification"
MATCHDAY = date(2026, 9, 25)
COMPETITION = {"id": 228, "name": "Africa Cup of Nations Qualifications"}
SENEGAL, MOZAMBIQUE = {"id": 1460, "name": "Senegal"}, {"id": 2771, "name": "Mozambique"}
SUDAN, ETHIOPIA = {"id": 1519, "name": "Sudan"}, {"id": 1597, "name": "Ethiopia"}

#: The stale listing's kickoff, and the moment the live poll's window around it closes.
STALE_KICKOFF = datetime(2026, 9, 25, 19, 0, tzinfo=timezone.utc)
WINDOW_CLOSED = STALE_KICKOFF + UNSETTLED_GRACE


def listed(fixture_id: int, home: Dict, away: Dict, kickoff: str, venue: str, day: str = "2026-09-25") -> Dict:
    """A `fixtures/list.json` row."""
    return {"id": fixture_id, "date": day, "time": kickoff, "round": "1", "location": venue,
            "home": dict(home), "away": dict(away), "competition": dict(COMPETITION)}


def played(fixture_id: int, home: Dict, away: Dict, ht: str, ft: str, archive_id: int) -> Dict:
    """A `matches/history.json` row, in the captured archive row's keys exactly."""
    return {"away": dict(away), "competition": dict(COMPETITION), "date": "2026-09-25",
            "fixture_id": fixture_id, "home": dict(home), "id": archive_id, "round": "1",
            "scores": {"et_score": "", "ft_score": ft, "ht_score": ht, "ps_score": "", "score": ft},
            "status": "FINISHED", "time": "FT"}


FIRST_LISTING = listed(1899816, SENEGAL, MOZAMBIQUE, "19:00:00", "Stade Léopold Sédar Senghor")
RELISTING = listed(1902057, MOZAMBIQUE, SENEGAL, "13:00:00", "Estádio Nacional do Zimpeto")
BYSTANDER = listed(1899808, SUDAN, ETHIOPIA, "13:00:00", "Al-Merreikh Stadium")
#: 900201 and 900202 are test values: the archive's own match ids were never stored.
RELISTING_PLAYED = played(1902057, MOZAMBIQUE, SENEGAL, "1 - 1", "1 - 1", archive_id=900201)
BYSTANDER_PLAYED = played(1899808, SUDAN, ETHIOPIA, "0 - 0", "1 - 0", archive_id=900202)


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
    monkeypatch.setattr(settings, "SYNC_RESULTS_LOOKBACK_DAYS", 1)


# ----------------------------------------------------------------------------- the provider
class Replies:
    """What Live Score answers for the matchday, and every request it was sent."""

    def __init__(self):
        self.fixtures: List[Dict] = []
        self.history: List[Dict] = []
        self.requests: List[httpx.Request] = []

    def asked(self, endpoint: str) -> int:
        return sum(1 for r in self.requests if r.url.path.endswith(endpoint))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        params, path = dict(request.url.params), request.url.path
        if path.endswith("fixtures/list.json"):
            assert params["competition_id"] == "228"
            rows = [r for r in self.fixtures if r["date"] == params["date"]]
            return json_response({"success": True, "data": {"fixtures": copy.deepcopy(rows), "next_page": False}})
        if path.endswith("matches/history.json"):
            assert params["competition_id"] == "228" and params["from"] == params["to"] == MATCHDAY.isoformat()
            return json_response({"success": True, "data": {"match": copy.deepcopy(self.history),
                                                            "next_page": False}})
        if path.endswith("matches/live.json"):
            return json_response({"success": True, "data": {"match": []}})
        raise AssertionError(f"unexpected request to {path}")


def provider_for(replies: Replies, at: datetime) -> LiveScoreAPIProvider:
    return LiveScoreAPIProvider(
        api_key="test-key", api_secret="test-secret", transport=httpx.MockTransport(replies),
        budget=RequestBudget("livescore", 1200, client=FakeRedis(), now=at),
        competition_overrides={}, store=MatchCache(client=FakeRedis()), use_default_ids=True)


def service_at(db, replies: Replies, at: datetime) -> MatchDataService:
    """A pass at `at`: its own cache, so every answer it uses is one it asked for."""
    return MatchDataService(db, providers=[provider_for(replies, at)], cache=MatchCache(client=FakeRedis()),
                            now=at, keys=[AFCON_Q])


def store(db, row: Dict, at: datetime) -> Match:
    """One `fixtures/list.json` row through the real mapping and the registry, as a sync at `at` would."""
    provider = provider_for(Replies(), at)
    fixture = provider._fixture_from_scheduled(copy.deepcopy(row), [AFCON_Q])
    fixture.competition = provider.list_competitions([AFCON_Q])[0]
    match = MatchRegistry(db, now=at).upsert_fixture(fixture)
    assert match is not None
    return match


def store_played(db, row: Dict, at: datetime) -> Match:
    """One `matches/history.json` row the same way."""
    provider = provider_for(Replies(), at)
    fixture = provider._fixture_from_match(copy.deepcopy(row), [AFCON_Q])
    fixture.competition = provider.list_competitions([AFCON_Q])[0]
    match = MatchRegistry(db, now=at).upsert_fixture(fixture)
    assert match is not None
    return match


def by_fixture_id(db, fixture_id: int) -> Match:
    match = MatchRegistry(db).match_by_ref("livescore", str(fixture_id))
    assert match is not None
    return match


def score(db, match: Match) -> Optional[tuple]:
    row = db.query(MatchResult).filter(MatchResult.match_id == match.id).first()
    return None if row is None else (row.home_score, row.away_score)


def the_pair(db, at: datetime = WINDOW_CLOSED + timedelta(minutes=1)):
    """Both listings stored in the order Live Score sent them, and the re-listing played."""
    stale = store(db, FIRST_LISTING, datetime(2026, 9, 24, 6, 13, tzinfo=timezone.utc))
    real = store(db, RELISTING, datetime(2026, 9, 25, 6, 18, tzinfo=timezone.utc))
    store_played(db, RELISTING_PLAYED, datetime(2026, 9, 25, 15, 31, tzinfo=timezone.utc))
    db.refresh(real)
    assert real.id != stale.id and real.status == MatchStatus.FINISHED
    return stale, real, at


def expert_view_on(db, match: Match, published_at: datetime) -> Prediction:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"relisting-{suffix}@test.local", username=f"relisting_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    row = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                     created_by=user.id, home_win_prob=Decimal("0.55"), draw_prob=Decimal("0.25"),
                     away_win_prob=Decimal("0.20"), confidence_score=Decimal("0.7"),
                     status=PredictionStatus.PUBLISHED, published_at=published_at.replace(tzinfo=None),
                     priority_level=100, reasoning="Senegal at home")
    db.add(row)
    db.flush()
    return row


# ============================================================ the incident, end to end
def test_the_relisted_qualifier_is_closed_once_its_own_kickoff_has_passed_and_nothing_crosses(db):
    replies = Replies()

    # 2026-09-24 06:13 UTC: the matchday as first published.
    replies.fixtures = [FIRST_LISTING, BYSTANDER]
    service_at(db, replies, datetime(2026, 9, 24, 6, 13, tzinfo=timezone.utc)).sync_day(MATCHDAY)
    stale = by_fixture_id(db, 1899816)
    view = expert_view_on(db, stale, published_at=datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc))

    # 06:18 the next morning: Mozambique v Senegal in its place, and 1899816 no longer listed.
    replies.fixtures = [RELISTING, BYSTANDER]
    service_at(db, replies, datetime(2026, 9, 25, 6, 18, tzinfo=timezone.utc)).sync_day(MATCHDAY)
    real = by_fixture_id(db, 1902057)
    assert real.id != stale.id, "a provider's own other fixture is never joined to a new id"
    assert (real.home_team_id, real.away_team_id) == (stale.away_team_id, stale.home_team_id)
    assert stale.status == real.status == MatchStatus.SCHEDULED

    # 15:31: both 13:00 kickoffs are past the live window, and the archive has them.
    replies.history = [RELISTING_PLAYED, BYSTANDER_PLAYED]
    service_at(db, replies, datetime(2026, 9, 25, 15, 31, tzinfo=timezone.utc))._sync_results(MATCHDAY, SyncMeta())
    for row in (stale, real):
        db.refresh(row)
    assert real.status == MatchStatus.FINISHED and score(db, real) == (1, 1)
    assert stale.status == MatchStatus.SCHEDULED and RELISTED_KEY not in (stale.match_metadata or {}), \
        "the listing's own kickoff has not passed yet, and nothing is decided before it has"

    # 21:31: 19:00 plus the live poll's whole window, and nobody reported the listing started.
    history_asks = replies.asked("matches/history.json")
    service_at(db, replies, WINDOW_CLOSED + timedelta(minutes=1)).sync_day(MATCHDAY)
    db.refresh(stale)
    assert replies.asked("matches/history.json") == history_asks, \
        "no archive request is spent on a listing the stored rows already account for"
    assert stale.status == MatchStatus.POSTPONED
    note = stale.match_metadata[RELISTED_KEY]
    assert note["match_id"] == str(real.id)
    assert (note["home"], note["away"], note["scoreline"]) == ("Mozambique", "Senegal", "1-1")
    assert note["provider_ids"] == {"livescore": "1902057"}
    assert note["this_listing_ids"] == {"livescore": "1899816"}
    assert note["status_before"] == "scheduled"
    assert "6 h 00 min" in note["reason"] and "a prediction stays on the fixture it was made for" in note["reason"]

    # Nothing invented, nothing moved.
    assert score(db, stale) is None, "no result is written onto the listing that was not played"
    assert score(db, real) == (1, 1)
    db.refresh(view)
    assert view.match_id == stale.id, "the expert's view stays on the fixture they saw"
    registry = MatchRegistry(db)
    assert registry.resolve_match_id("livescore:1899816") == stale.id, "the provider's id still names its listing"
    assert {r.external_id for r in registry.refs_for("match", real.id)} == {"1902057"}

    bystander = by_fixture_id(db, 1899808)
    assert bystander.status == MatchStatus.FINISHED and score(db, bystander) == (1, 0)
    assert RELISTED_KEY not in (bystander.match_metadata or {})
    assert RELISTED_KEY not in (real.match_metadata or {})


def test_a_listing_the_sweep_has_been_chasing_is_closed_by_the_recovery_pass_for_nothing(db):
    """The row as production held it: asked about thirty times, its next ask already due."""
    stale, real, _ = the_pair(db)
    meta = dict(stale.match_metadata or {})
    meta["recovery"] = {"attempts": 30, "last_outcome": "fresh_unanswered",
                        "last_attempt_at": "2026-10-02T08:12:01.544620+00:00",
                        "next_ask_after": "2026-10-03T08:12:01.544620+00:00"}
    stale.match_metadata = meta
    db.commit()
    replies = Replies()
    service = service_at(db, replies, datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc))

    plan = service.recovery_plan()
    assert [m.id for m in plan["relisted"]] == [stale.id]
    assert stale.id not in {m.id for m in plan["stranded"]} | {m.id for m in plan["due"]}
    assert plan["results_requests"] == 0 and plan["days"] == [], "the plan prices what the pass will do"

    report = service.recover_stranded()

    db.refresh(stale)
    assert report["relisted"] == [{"match_id": str(stale.id), "relisted_as": str(real.id)}]
    assert report["results_requests"] == 0 and report["live_requests"] == 0
    assert replies.requests == [], "closing a second listing asks no provider anything"
    assert stale.status == MatchStatus.POSTPONED
    state = stale.match_metadata["recovery"]
    assert state["attempts"] == 30, "what was spent on it stays on record"
    assert "next_ask_after" not in state, "and no further ask is advertised"


# ============================================================ what the rule does not touch
def test_nothing_is_decided_inside_the_listing_s_own_live_window(db):
    stale, real, _ = the_pair(db)
    registry = MatchRegistry(db)
    assert registry.relisting_of(stale, WINDOW_CLOSED - timedelta(minutes=1)) is None
    assert registry.relisting_of(stale, WINDOW_CLOSED).id == real.id


def test_the_same_clubs_the_same_way_round_are_left_to_the_duplicate_repair(db):
    """Same way round, both rows say the same thing, and folding them is the right repair."""
    stale = store(db, FIRST_LISTING, datetime(2026, 9, 24, 6, 13, tzinfo=timezone.utc))
    same_way = listed(1902058, SENEGAL, MOZAMBIQUE, "13:00:00", "Stade Léopold Sédar Senghor")  # test id
    store(db, same_way, datetime(2026, 9, 25, 6, 18, tzinfo=timezone.utc))
    store_played(db, played(1902058, SENEGAL, MOZAMBIQUE, "1 - 1", "1 - 1", archive_id=900203),
                 datetime(2026, 9, 25, 15, 31, tzinfo=timezone.utc))

    assert MatchRegistry(db).retire_relisted(WINDOW_CLOSED + timedelta(days=1)) == []
    db.refresh(stale)
    assert stale.status == MatchStatus.SCHEDULED


def test_the_return_leg_days_later_is_a_different_match(db):
    _stale, real, _ = the_pair(db)
    return_leg = store(db, listed(1903000, SENEGAL, MOZAMBIQUE, "19:00:00", "Stade Léopold Sédar Senghor",
                                  day="2026-09-29"),  # test id and date: a second leg four days on
                       datetime(2026, 9, 26, 6, 0, tzinfo=timezone.utc))
    later = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    assert MatchRegistry(db).relisting_of(return_leg, later) is None
    assert return_leg.id not in {m.id for m in MatchRegistry(db).retire_relisted(later)}
    assert return_leg.status == MatchStatus.SCHEDULED and real.status == MatchStatus.FINISHED


def test_a_played_row_without_a_stored_score_is_not_evidence(db):
    stale = store(db, FIRST_LISTING, datetime(2026, 9, 24, 6, 13, tzinfo=timezone.utc))
    real = store(db, RELISTING, datetime(2026, 9, 25, 6, 18, tzinfo=timezone.utc))
    real.status = MatchStatus.FINISHED  # a status with no result row behind it
    db.flush()
    assert MatchRegistry(db).relisting_of(stale, WINDOW_CLOSED + timedelta(days=1)) is None


def test_a_listing_reported_in_play_is_not_closed(db):
    stale, _real, at = the_pair(db)
    stale.status = MatchStatus.LIVE
    db.flush()
    assert MatchRegistry(db).relisting_of(stale, at) is None


# ============================================================ when the provider speaks again
def test_a_stale_listing_sent_again_unchanged_stays_closed(db):
    stale, real, at = the_pair(db)
    MatchRegistry(db).retire_relisted(at)

    again = store(db, FIRST_LISTING, at + timedelta(hours=1))

    assert again.id == stale.id
    assert again.status == MatchStatus.POSTPONED, "a re-send never puts it back on the calendar"
    assert again.match_metadata[RELISTED_KEY]["match_id"] == str(real.id)


def test_a_listing_brought_back_on_another_date_loses_the_note(db):
    stale, real, at = the_pair(db)
    MatchRegistry(db).retire_relisted(at)

    back = store(db, listed(1899816, SENEGAL, MOZAMBIQUE, "19:00:00", "Stade Léopold Sédar Senghor",
                            day="2026-11-14"),  # test date: the provider re-dates its own fixture
                 at + timedelta(days=1))

    assert back.id == stale.id
    assert back.status == MatchStatus.SCHEDULED
    assert back.match_date == datetime(2026, 11, 14, 19, 0)
    assert RELISTED_KEY not in back.match_metadata
    assert back.match_metadata["relisting_lifted"]["match_id"] == str(real.id)


# ============================================================ what a reader is told
def test_the_payload_says_where_the_match_was_played(db):
    stale, real, at = the_pair(db)
    registry = MatchRegistry(db)
    registry.retire_relisted(at)

    payload = serialize_match(stale, registry.team_names([stale]), registry.leagues_by_id([stale]))
    other = serialize_match(real, registry.team_names([real]), registry.leagues_by_id([real]))

    assert payload["status"] == "postponed"
    assert payload["relisted_as"]["match_id"] == str(real.id)
    assert payload["relisted_as"]["kickoff_utc"] == "2026-09-25T13:00:00Z"
    assert payload["relisted_as"]["scoreline"] == "1-1"
    assert other["relisted_as"] is None


def test_a_prematch_view_on_the_stale_listing_is_voided_there_with_the_true_reason(db):
    stale, real, at = the_pair(db)
    view = expert_view_on(db, stale, published_at=datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc))
    MatchRegistry(db).retire_relisted(at)

    report = SettlementService(db).settle_match(stale)
    db.flush()

    assert report["expert_predictions"]["void"] == 1
    settled = db.query(PredictionResult).filter(PredictionResult.prediction_id == view.id).one()
    assert settled.outcome == PredictionOutcome.VOID
    assert settled.void_reason == RELISTED_VOID_REASON
    assert db.query(Prediction).filter(Prediction.match_id == real.id).count() == 0
