"""
Preserved expert records: an edit must append, never rewrite.

What was happening before this change: `ExpertPredictionService.update_prediction` overwrote the
live `predictions.predictions` row in place. `predictions.prediction_audit` - the table built to
hold old_values/new_values - had never received a single row from anywhere in the application, and
the endpoint's only audit entry passed the *already updated* prediction as both the original and
the override, so it recorded the new probabilities as the old ones. The version readers had seen
before a correction was therefore gone, and a correction made after kickoff could quietly replace
the prematch view with a different one.

These tests hold the fixed behaviour: the replaced version is written to prediction_audit before the
row is touched, it stays retrievable with its own timestamp, a second correction appends a second
revision rather than rewriting the first, and an edit made after kickoff cannot remove the original.

Requires PostgreSQL (TEST_DATABASE_URL, default the docker-compose test database); skipped when
unreachable. No provider is ever called: match reads use refresh=false.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_db as deps_get_db
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.predictions import (
    League,
    Match,
    MatchStatus,
    Prediction,
    PredictionAudit,
    PredictionSource,
    PredictionStatus,
    Team,
)
from app.models.users import AccountStatus, User, UserType
from app.schemas.predictions import ExpertPredictionUpdate
from app.services.expert_prediction import REVISION_ACTION, ExpertPredictionService
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

# Far enough ahead that no other module in the suite has fixtures there.
FUTURE_KICKOFF = datetime.utcnow() + timedelta(days=45)
PAST_KICKOFF = datetime.utcnow() - timedelta(hours=5)


# ----------------------------------------------------------------------------- fixtures
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
    """Session joined to an outer transaction; service-level commit() only releases a savepoint."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def in_memory_cache(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("app.services.match_data_service.MatchCache", lambda client=None: MatchCache(client=redis))
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))
    return redis


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    # The match endpoints depend on app.db.session.get_db and the expert endpoints on
    # app.core.deps.get_db - two distinct callables. Both are overridden so one test session sees
    # the writes the other made.
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps_get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(deps_get_db, None)


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"rev-{suffix}@test.local", username=f"rev_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, country="England")
    db.add(team)
    db.flush()
    return team


def _league(db) -> League:
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    return league


def _match(db, kickoff: datetime, label: str, status: MatchStatus = MatchStatus.SCHEDULED) -> Match:
    league = _league(db)
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=_team(db, f"{label} Home").id,
                  away_team_id=_team(db, f"{label} Away").id, match_date=kickoff, status=status,
                  external_api_id=f"ext-{label}-{uuid.uuid4().hex[:6]}", external_api_source="sample",
                  match_metadata={})
    db.add(match)
    db.flush()
    return match


def _publish(db, match: Match, user: User, published_at: datetime, **values) -> Prediction:
    fields = dict(home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"), away_win_prob=Decimal("0.2"),
                  confidence_score=Decimal("0.8"))
    fields.update({name: Decimal(str(value)) for name, value in values.items()})
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=user.id, status=PredictionStatus.PUBLISHED,
                            published_at=published_at, priority_level=100,
                            reasoning="first view: home side rested", **fields)
    db.add(prediction)
    db.flush()
    return prediction


def _edit(db, prediction: Prediction, expert: User, **fields) -> Prediction:
    payload = dict(home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1)
    payload.update(fields)
    return ExpertPredictionService(db).update_prediction(
        str(prediction.id), ExpertPredictionUpdate(**payload), expert)


def _revision_rows(db, prediction: Prediction):
    return db.query(PredictionAudit).filter(
        PredictionAudit.prediction_id == prediction.id,
        PredictionAudit.action == REVISION_ACTION,
    ).order_by(PredictionAudit.created_at.asc()).all()


def _detail(client, match: Match) -> dict:
    response = client.get(f"/api/v1/matches/{match.id}")
    assert response.status_code == 200, response.text
    return response.json()


# ----------------------------------------------------------------------------- the audit row itself
def test_editing_a_published_prediction_writes_old_and_new_values_to_prediction_audit(db):
    """prediction_audit existed and had never been written to. It is now the preservation mechanism."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "audit")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=3))

    assert _revision_rows(db, prediction) == []

    _edit(db, prediction, expert, reasoning="second view: key defender fit again")

    rows = _revision_rows(db, prediction)
    assert len(rows) == 1
    assert rows[0].old_values["home_win_prob"] == pytest.approx(0.5)
    assert rows[0].new_values["home_win_prob"] == pytest.approx(0.7)
    assert rows[0].old_values["reasoning"] == "first view: home side rested"
    assert rows[0].user_id == expert.id
    assert "home_win_prob 0.5 -> 0.7" in rows[0].changes_summary


def test_the_edit_still_behaves_as_before_for_the_live_row(db):
    """Preserving the previous version must not change what an edit does to the current one."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "live")
    published_at = datetime.utcnow() - timedelta(hours=3)
    prediction = _publish(db, match, expert, published_at)

    updated = _edit(db, prediction, expert, confidence_score=0.9)

    assert float(updated.home_win_prob) == pytest.approx(0.7)
    assert updated.status == PredictionStatus.PUBLISHED
    assert updated.published_at == published_at  # publication time is not restamped


# ----------------------------------------------------------------------------- exposed on the match
def test_the_match_payload_exposes_the_original_version_with_its_timestamp(client, db):
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "exposed")
    published_at = (datetime.utcnow() - timedelta(hours=6)).replace(microsecond=0)
    prediction = _publish(db, match, expert, published_at)

    _edit(db, prediction, expert, reasoning="second view")

    payload = _detail(client, match)
    revisions = payload["expert_prediction_revisions"]
    assert len(revisions) == 1
    original = revisions[0]
    assert original["revision"] == 1
    assert original["prediction_id"] == str(prediction.id)
    assert original["values"]["home_win_prob"] == pytest.approx(0.5)
    assert original["values"]["away_win_prob"] == pytest.approx(0.2)
    # The version that was live carries the time it was published, and the time it was replaced.
    assert original["published_at"] == published_at.isoformat() + "Z"
    assert original["replaced_at"].endswith("Z")
    assert original["edited_after_kickoff"] is False
    # ...alongside the current prediction, which shows the corrected numbers.
    assert payload["expert_prediction"]["home_win_prob"] == pytest.approx(0.7)


def test_an_unedited_prediction_has_no_revisions(client, db):
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "unedited")
    _publish(db, match, expert, datetime.utcnow())

    assert _detail(client, match)["expert_prediction_revisions"] == []


def test_a_correction_appends_rather_than_rewriting(client, db):
    """Two corrections leave two revisions, and the first is still the original."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "append")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=8))

    _edit(db, prediction, expert, home_win_prob=0.6, draw_prob=0.25, away_win_prob=0.15)
    _edit(db, prediction, expert, home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1)

    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert [row["revision"] for row in revisions] == [1, 2]
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)   # the original
    assert revisions[1]["values"]["home_win_prob"] == pytest.approx(0.6)   # the first correction
    assert revisions[0]["replaced_at"] <= revisions[1]["replaced_at"]


# ----------------------------------------------------------------------------- after kickoff
def test_a_post_kickoff_edit_cannot_make_the_original_disappear(client, db):
    """The prematch view is the whole point of the record: it must survive an edit made afterwards."""
    expert = _expert(db)
    match = _match(db, PAST_KICKOFF, "postkick", status=MatchStatus.LIVE)
    published_at = (datetime.utcnow() - timedelta(hours=9)).replace(microsecond=0)
    prediction = _publish(db, match, expert, published_at)

    _edit(db, prediction, expert, home_win_prob=0.95, draw_prob=0.03, away_win_prob=0.02,
          reasoning="rewritten after the match started")

    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)
    assert revisions[0]["published_at"] == published_at.isoformat() + "Z"
    # Flagged, so a reader can see the correction was made after the match had begun.
    assert revisions[0]["edited_after_kickoff"] is True


def test_a_post_kickoff_edit_after_an_earlier_one_still_keeps_the_original(client, db):
    expert = _expert(db)
    match = _match(db, PAST_KICKOFF, "twoedits", status=MatchStatus.LIVE)
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=10))

    _edit(db, prediction, expert, home_win_prob=0.6, draw_prob=0.25, away_win_prob=0.15)
    _edit(db, prediction, expert, home_win_prob=0.99, draw_prob=0.005, away_win_prob=0.005)

    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert len(revisions) == 2
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)


# ----------------------------------------------------------------------------- endpoint round trip
def test_the_update_endpoint_preserves_the_previous_version_too(client, db, monkeypatch):
    """The service is where preservation happens, but the HTTP path must reach it."""
    from app.core.deps import get_current_expert_user

    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "http")
    prediction = _publish(db, match, expert, datetime.utcnow() - timedelta(hours=2))
    app.dependency_overrides[get_current_expert_user] = lambda: expert
    try:
        response = client.put(
            f"/api/v1/expert/predictions/{prediction.id}",
            json={"home_win_prob": 0.7, "draw_prob": 0.2, "away_win_prob": 0.1,
                  "reasoning": "corrected over HTTP"},
        )
    finally:
        app.dependency_overrides.pop(get_current_expert_user, None)

    assert response.status_code == 200, response.text
    assert response.json()["home_win_prob"] == pytest.approx(0.7)
    revisions = _detail(client, match)["expert_prediction_revisions"]
    assert len(revisions) == 1
    assert revisions[0]["values"]["home_win_prob"] == pytest.approx(0.5)


# ----------------------------------------------------------------------------- brief on the payloads
def test_the_detail_payload_carries_the_full_brief_and_the_list_carries_the_compact_one(client, db):
    """B1: the brief rides on the detail endpoint; the list gets the compact form, which is built
    from values the list loop already holds and so costs no query per match."""
    expert = _expert(db)
    match = _match(db, FUTURE_KICKOFF, "brief")
    _publish(db, match, expert, datetime.utcnow())

    detail = _detail(client, match)
    day = FUTURE_KICKOFF.date().isoformat()
    listing = client.get(f"/api/v1/matches?date={day}&refresh=false")

    assert listing.status_code == 200, listing.text
    assert detail["brief"]["markets"][0]["key"] == "match_result"
    assert detail["brief_compact"]["headline"] == detail["brief"]["headline"]
    rows = [row for row in listing.json()["matches"] if row["id"] == str(match.id)]
    assert rows and "brief_compact" in rows[0]
    assert "brief" not in rows[0], "the list payload must stay compact"


def test_the_list_payload_costs_no_extra_query_per_match(client, db):
    """Measured, as B1 asks: adding matches must not add queries proportionally."""
    expert = _expert(db)
    day = (FUTURE_KICKOFF + timedelta(days=1)).date().isoformat()
    kickoff = FUTURE_KICKOFF + timedelta(days=1)
    first = _match(db, kickoff, "count1")
    _publish(db, first, expert, datetime.utcnow())
    db.commit()

    from sqlalchemy import event

    def count_queries(url: str) -> int:
        counter = {"n": 0}

        def before(conn, cursor, statement, parameters, context, executemany):
            counter["n"] += 1

        event.listen(db.get_bind(), "before_cursor_execute", before)
        try:
            assert client.get(url).status_code == 200
        finally:
            event.remove(db.get_bind(), "before_cursor_execute", before)
        return counter["n"]

    one_match = count_queries(f"/api/v1/matches?date={day}&refresh=false")
    second = _match(db, kickoff + timedelta(hours=1), "count2")
    _publish(db, second, expert, datetime.utcnow())
    db.commit()
    two_matches = count_queries(f"/api/v1/matches?date={day}&refresh=false")

    # One more match adds only its own forecast lookup, which existed before the brief did.
    assert two_matches - one_match <= 1, f"{one_match} -> {two_matches} queries"
