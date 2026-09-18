"""
Database-backed regression tests for the prediction and match endpoints.

Covers the bugs fixed in this change:
* ``GET /api/v1/predictions/published?date=`` returned 500 (``Session`` has no ``func``).
* Timestamps were serialised without a UTC marker, so the browser read them as local time.
* Today/tomorrow were bucketed by the UTC day, so a late kickoff moved to the wrong day for
  anyone whose local day does not line up with UTC (``tz_offset``).
* A published prediction could never be edited again, although experts publish directly.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
No provider is ever called: the match endpoints are queried with ``refresh=false``.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.predictions import (
    League,
    Match,
    MatchStatus,
    Prediction,
    PredictionSource,
    PredictionStatus,
    Team,
)
from app.models.users import AccountStatus, User, UserType
from app.schemas.predictions import ExpertPredictionUpdate
from app.services.expert_prediction import ExpertPredictionService
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

# A day far enough ahead that nothing else in the suite has fixtures there.
DAY = (datetime.now(timezone.utc) + timedelta(days=40)).date()
LATE_KICKOFF = datetime.combine(DAY, datetime.min.time()) + timedelta(hours=23, minutes=30)   # 23:30 UTC
EARLY_NEXT_DAY = datetime.combine(DAY, datetime.min.time()) + timedelta(days=1, hours=1)      # 01:00 UTC, D+1


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
    """Every service gets the same in-memory cache; nothing reaches the real Redis."""
    redis = FakeRedis()
    monkeypatch.setattr("app.services.match_data_service.MatchCache", lambda client=None: MatchCache(client=redis))
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))
    return redis


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"expert-{suffix}@test.local", username=f"expert_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT, account_status=AccountStatus.ACTIVE,
                email_verified=True)
    db.add(user)
    db.flush()
    return user


def _league(db) -> League:
    """One of the covered competitions, so the match endpoints return its fixtures."""
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    return league


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, country="England")
    db.add(team)
    db.flush()
    return team


def _match(db, league: League, kickoff_utc: datetime, label: str) -> Match:
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=_team(db, f"{label} Home").id,
                  away_team_id=_team(db, f"{label} Away").id, match_date=kickoff_utc,
                  status=MatchStatus.SCHEDULED, external_api_id=f"ext-{label}-{uuid.uuid4().hex[:6]}",
                  external_api_source="sample", match_metadata={})
    db.add(match)
    db.flush()
    return match


def _publish(db, match: Match, user: User, published_at: datetime) -> Prediction:
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=user.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.8"),
                            status=PredictionStatus.PUBLISHED, published_at=published_at, priority_level=100,
                            reasoning="expert view")
    db.add(prediction)
    db.flush()
    return prediction


def _kickoffs(body) -> set:
    return {m["kickoff_utc"] for m in body["matches"]}


# ----------------------------------------------------------------------------- published predictions
def test_published_predictions_can_be_filtered_by_date(client, db):
    """The date filter used to call `db.func`, which does not exist: every request was a 500."""
    expert, league = _expert(db), _league(db)
    on_day = _match(db, league, LATE_KICKOFF, "onday")
    next_day = _match(db, league, EARLY_NEXT_DAY, "nextday")
    wanted = _publish(db, on_day, expert, datetime.utcnow())
    _publish(db, next_day, expert, datetime.utcnow())

    response = client.get(f"/api/v1/predictions/published?date={DAY.isoformat()}")

    assert response.status_code == 200, response.text
    ids = [row["id"] for row in response.json()]
    assert ids == [str(wanted.id)]


def test_published_predictions_reject_an_unparseable_date(client, db):
    response = client.get("/api/v1/predictions/published?date=13-10-2025")
    assert response.status_code == 400, response.text


def test_published_prediction_timestamps_are_utc_with_z(client, db):
    """Without the Z the browser parses the kickoff as local time and can show the wrong day."""
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "utcz")
    _publish(db, match, expert, datetime.utcnow())

    response = client.get(f"/api/v1/predictions/published?date={DAY.isoformat()}")

    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["published_at"].endswith("Z")
    assert row["match_details"]["match_date"] == LATE_KICKOFF.isoformat() + "Z"


# ----------------------------------------------------------------------------- local day windows
def test_matches_default_to_the_utc_calendar_day(client, db):
    """Without tz_offset the behaviour is unchanged: the UTC calendar day."""
    league = _league(db)
    late = _match(db, league, LATE_KICKOFF, "utclate")
    _match(db, league, EARLY_NEXT_DAY, "utcnext")

    response = client.get(f"/api/v1/matches?date={DAY.isoformat()}&refresh=false")

    assert response.status_code == 200, response.text
    body = response.json()
    assert _kickoffs(body) == {late.match_date.isoformat() + "Z"}
    assert body["tz_offset"] is None


def test_matches_use_the_callers_local_day_when_tz_offset_is_sent(client, db):
    """UTC-5: both a 23:30 UTC kickoff and a 01:00 UTC one fall in the same local day."""
    league = _league(db)
    late = _match(db, league, LATE_KICKOFF, "wlate")
    early = _match(db, league, EARLY_NEXT_DAY, "wearly")

    response = client.get(f"/api/v1/matches?date={DAY.isoformat()}&refresh=false&tz_offset=-300")

    assert response.status_code == 200, response.text
    body = response.json()
    assert _kickoffs(body) == {late.match_date.isoformat() + "Z", early.match_date.isoformat() + "Z"}
    assert body["tz_offset"] == -300
    assert body["window_utc"]["start"] == (datetime.combine(DAY, datetime.min.time()) + timedelta(hours=5)
                                           ).isoformat() + "Z"


def test_a_late_kickoff_belongs_to_the_next_local_day_east_of_utc(client, db):
    """UTC+2: a 23:30 UTC kickoff is 01:30 local, so it belongs to the *next* local day."""
    league = _league(db)
    late = _match(db, league, LATE_KICKOFF, "eastlate")

    same_day = client.get(f"/api/v1/matches?date={DAY.isoformat()}&refresh=false&tz_offset=120")
    next_day = client.get(f"/api/v1/matches?date={(DAY + timedelta(days=1)).isoformat()}&refresh=false&tz_offset=120")

    assert same_day.status_code == 200 and next_day.status_code == 200, same_day.text
    assert _kickoffs(same_day.json()) == set()
    assert _kickoffs(next_day.json()) == {late.match_date.isoformat() + "Z"}


def test_tz_offset_outside_the_accepted_range_is_rejected(client, db):
    response = client.get(f"/api/v1/matches?date={DAY.isoformat()}&refresh=false&tz_offset=5000")
    assert response.status_code == 422, response.text


# ----------------------------------------------------------------------------- editing after publication
def test_expert_can_edit_a_published_prediction(db):
    """Experts publish directly, so their published predictions must stay editable."""
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "edit")
    published_at = datetime.utcnow() - timedelta(hours=3)
    prediction = _publish(db, match, expert, published_at)

    updated = ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1,
                               confidence_score=0.9, reasoning="team news changed"),
        expert,
    )

    assert float(updated.home_win_prob) == pytest.approx(0.7)
    assert updated.reasoning == "team news changed"
    # Still published, and the publication time is not restamped
    assert updated.status == PredictionStatus.PUBLISHED
    assert updated.published_at == published_at
    assert updated.updated_at > published_at


def test_expert_cannot_edit_a_rejected_prediction(db):
    """A moderation outcome is not a draft: REJECTED stays uneditable."""
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "rejected")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.status = PredictionStatus.REJECTED
    db.flush()

    with pytest.raises(ValueError):
        ExpertPredictionService(db).update_prediction(
            str(prediction.id),
            ExpertPredictionUpdate(home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1),
            expert,
        )


def test_expert_cannot_edit_someone_elses_prediction(db):
    expert, other, league = _expert(db), _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "notmine")
    prediction = _publish(db, match, expert, datetime.utcnow())

    with pytest.raises(ValueError):
        ExpertPredictionService(db).update_prediction(
            str(prediction.id),
            ExpertPredictionUpdate(home_win_prob=0.7, draw_prob=0.2, away_win_prob=0.1),
            other,
        )
