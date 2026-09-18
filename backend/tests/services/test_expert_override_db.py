"""
Overriding a prediction, exercised against a real database.

This path could never have worked: it built PredictionOverride with original_prediction_id,
override_prediction_id, overridden_by and override_metadata, none of which are columns on that model.
SQLAlchemy raised TypeError, the endpoint's own `except Exception` turned it into a 400 "Failed to
create override", and the API test mocks the service — so the suite stayed green over a feature that
failed on every call. These tests use the real model, which is the only way that stays caught.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    League, Match, MatchStatus, Prediction, PredictionOverride, PredictionSource, PredictionStatus, Team,
)
from app.models.users import AccountStatus, User, UserType
from app.schemas.predictions import ExpertPredictionOverride
from app.services.expert_prediction import ExpertPredictionService

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")
NOW = datetime.now(timezone.utc).replace(microsecond=0)


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
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


def _world(db):
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"override-{suffix}@test.local", username=f"override_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    league = League(id=uuid.uuid4(), name=f"League {suffix}", display_name="League", country="England",
                    is_active=True)
    home = Team(id=uuid.uuid4(), name=f"Home {suffix}", short_name="HOM", country="England")
    away = Team(id=uuid.uuid4(), name=f"Away {suffix}", short_name="AWY", country="England")
    db.add_all([user, league, home, away])
    db.flush()
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                  match_date=(NOW + timedelta(days=2)).replace(tzinfo=None), status=MatchStatus.SCHEDULED,
                  season="2026/27", external_api_id=f"sample:{suffix}", external_api_source="sample")
    db.add(match)
    db.flush()
    original = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.API_FOOTBALL_BASELINE,
                          created_by=user.id, home_win_prob=Decimal("0.50"), draw_prob=Decimal("0.30"),
                          away_win_prob=Decimal("0.20"), confidence_score=Decimal("0.60"),
                          status=PredictionStatus.PUBLISHED, published_at=datetime.utcnow(),
                          priority_level=50, reasoning="the original view")
    db.add(original)
    db.flush()
    return user, match, original


def _override(original_id: str) -> ExpertPredictionOverride:
    return ExpertPredictionOverride(
        prediction_id=str(original_id), home_win_prob=0.62, draw_prob=0.23, away_win_prob=0.15,
        confidence_score=0.8, reasoning="the home side's first-choice defence is back")


def test_overriding_a_prediction_actually_writes_a_record(db):
    """The regression: this raised TypeError before reaching the database."""
    user, match, original = _world(db)
    service = ExpertPredictionService(db)

    result = service.override_prediction(_override(original.id), user)
    db.flush()

    assert result.id != original.id
    assert float(result.home_win_prob) == 0.62
    record = db.query(PredictionOverride).filter(PredictionOverride.prediction_id == result.id).one()
    assert record.expert_user_id == user.id
    assert record.expert_profile_id is not None, "expert_profile_id is NOT NULL and must be filled"
    assert record.override_reason == "the home side's first-choice defence is back"


def test_the_override_record_keeps_both_sets_of_probabilities(db):
    """The point of the record is that you can see what changed and by how much."""
    user, match, original = _world(db)
    service = ExpertPredictionService(db)

    result = service.override_prediction(_override(original.id), user)
    db.flush()
    record = db.query(PredictionOverride).filter(PredictionOverride.prediction_id == result.id).one()

    assert record.original_probabilities["home_win"] == 0.5
    assert record.original_probabilities["prediction_id"] == str(original.id)
    assert record.new_probabilities["home_win"] == 0.62
    assert float(record.original_confidence) == 0.6
    assert float(record.new_confidence) == 0.8
    assert float(record.confidence_adjustment) == pytest.approx(0.2, abs=1e-6)


def test_the_original_prediction_survives_being_overridden(db):
    """An override supersedes; it must not delete or rewrite what was said before."""
    user, match, original = _world(db)
    service = ExpertPredictionService(db)

    result = service.override_prediction(_override(original.id), user)
    db.flush()

    kept = db.query(Prediction).filter(Prediction.id == original.id).one()
    assert float(kept.home_win_prob) == 0.5, "the original probabilities are untouched"
    assert kept.reasoning == "the original view"
    assert kept.superseded_by == result.id
    assert result.prediction_metadata["original_prediction_id"] == str(original.id)


def test_overriding_a_prediction_that_does_not_exist_is_refused(db):
    user, match, original = _world(db)
    service = ExpertPredictionService(db)
    with pytest.raises(ValueError):
        service.override_prediction(_override(uuid.uuid4()), user)


def test_the_model_columns_the_service_writes_all_exist(db):
    """Catches the exact class of defect: a kwarg that is not a column fails only at runtime."""
    columns = {c.name for c in PredictionOverride.__table__.columns}
    for written in ("prediction_id", "expert_user_id", "expert_profile_id", "original_probabilities",
                    "original_confidence", "new_probabilities", "new_confidence",
                    "confidence_adjustment", "override_reason", "key_insights"):
        assert written in columns, f"{written} is not a column on PredictionOverride"
