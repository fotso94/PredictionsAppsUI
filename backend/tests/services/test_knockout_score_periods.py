"""
A knockout tie settles on the 90 minutes, not on the score it finished with.

API-Football's `goals` is the score of the football played -- extra time included -- while
`score.fulltime` is the score after 90 minutes. Reading `goals` as the full-time score made a tie
that stood 1-1 at 90 and finished 2-1 in extra time settle as a 2-1 home win, on markets whose
published rule is regulation time only. Everyone who had the draw was marked wrong and everyone
who had the home win was marked right, off a scoreline the markets do not pay out on.

These tests drive API-Football knockout payloads the whole way -- provider mapping, the registry
row, then settlement -- and pin the three cases apart: a tie decided in extra time, a tie decided
on penalties, and an ordinary 90-minute win that must keep settling exactly as it did. The last
test covers the provider that supplies no breakdown at all, where the honest answer is to withhold
rather than to settle on a score that may cover more football than the market does.

The payloads are API-Football's real response shape; the ties in them are constructed.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    Match, MatchResult, MatchStatus, Prediction, PredictionResult, PredictionSource,
    PredictionStatus,
)
from app.models.users import AccountStatus, User, UserType
from app.services import settlement as S
from app.services.match_registry import MatchRegistry
from app.services.providers.api_football_provider import _fixture_from_payload
from app.services.providers.base import STATUS_FINISHED

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

KICKOFF = (datetime.now(timezone.utc) - timedelta(days=240)).replace(
    hour=20, minute=0, second=0, microsecond=0)


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
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ----------------------------------------------------------------------------- the payload
def knockout_payload(goals: Dict[str, Any], fulltime: Dict[str, Any],
                     extratime: Dict[str, Any], penalty: Dict[str, Any],
                     status_short: str, halftime: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One /fixtures row in API-Football's response shape."""
    suffix = uuid.uuid4().hex[:8]
    return {
        "fixture": {
            "id": f"108{suffix}",
            "referee": "C. Turpin, France",
            "timezone": "UTC",
            "date": KICKOFF.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "timestamp": int(KICKOFF.timestamp()),
            "periods": {"first": int(KICKOFF.timestamp()), "second": int(KICKOFF.timestamp()) + 3600},
            "venue": {"id": 550, "name": "Signal Iduna Park", "city": "Dortmund"},
            "status": {"long": "Match Finished", "short": status_short, "elapsed": 120},
        },
        "league": {"id": 2, "name": "UEFA Champions League", "country": "World",
                   "logo": "https://media.api-sports.io/football/leagues/2.png", "flag": None,
                   "season": 2024, "round": "Round of 16"},
        "teams": {
            "home": {"id": 165, "name": f"Hausen SV {suffix}",
                     "logo": "https://media.api-sports.io/football/teams/165.png", "winner": True},
            "away": {"id": 530, "name": f"Fortuna CF {suffix}",
                     "logo": "https://media.api-sports.io/football/teams/530.png", "winner": False},
        },
        "goals": goals,
        "score": {
            "halftime": halftime if halftime is not None else {"home": 0, "away": 1},
            "fulltime": fulltime,
            "extratime": extratime,
            "penalty": penalty,
        },
    }


#: 1-1 after 90, 2-1 after extra time. `goals` carries the 2-1; `score.fulltime` the 1-1.
AET_TIE = dict(goals={"home": 2, "away": 1}, fulltime={"home": 1, "away": 1},
               extratime={"home": 2, "away": 1}, penalty={"home": None, "away": None},
               status_short="AET")

#: 1-1 after 120 minutes, won 4-3 on penalties. A shootout is never a goal.
SHOOTOUT_TIE = dict(goals={"home": 1, "away": 1}, fulltime={"home": 1, "away": 1},
                    extratime={"home": 1, "away": 1}, penalty={"home": 4, "away": 3},
                    status_short="PEN")

#: An ordinary tie settled inside 90 minutes; nothing about it may change.
NINETY_MINUTES = dict(goals={"home": 2, "away": 1}, fulltime={"home": 2, "away": 1},
                      extratime={"home": None, "away": None}, penalty={"home": None, "away": None},
                      status_short="FT")


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"knockout-{suffix}@test.local", username=f"knockout_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def ingest(db, **payload_kwargs) -> Match:
    """The payload, through the real provider mapping and the real registry, to a stored match."""
    fixture = _fixture_from_payload(knockout_payload(**payload_kwargs), "champions_league")
    match = MatchRegistry(db).upsert_fixture(fixture)
    assert match is not None, "the registry refused a fixture these tests depend on"
    db.flush()
    db.refresh(match)
    return match


def predict(db, match: Match, home=0.5, draw=0.3, away=0.2) -> Prediction:
    row = Prediction(
        id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
        created_by=_expert(db).id, home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(draw)),
        away_win_prob=Decimal(str(away)), confidence_score=Decimal("0.8"),
        status=PredictionStatus.PUBLISHED, priority_level=100,
        published_at=match.match_date - timedelta(hours=6),
        reasoning="published before a knockout tie that went long")
    db.add(row)
    db.flush()
    return row


def settle(db) -> Dict[str, Any]:
    return S.SettlementService(db).settle_range(commit=False)


def stored_result(db, match: Match) -> MatchResult:
    return db.query(MatchResult).filter(MatchResult.match_id == match.id).one()


def scored(db, prediction: Prediction) -> PredictionResult:
    return db.query(PredictionResult).filter(PredictionResult.prediction_id == prediction.id).one()


# ----------------------------------------------------------------------------- the mapping
def test_goals_is_the_football_played_and_fulltime_is_the_ninety_minutes():
    fixture = _fixture_from_payload(knockout_payload(**AET_TIE), "champions_league")

    # The score of the football played: extra time counted in.
    assert (fixture.home_score, fixture.away_score) == (2, 1)
    # The score the markets settle on: the 90 minutes, which was a draw.
    assert (fixture.ft_home_score, fixture.ft_away_score) == (1, 1)
    assert (fixture.et_home_score, fixture.et_away_score) == (2, 1)
    assert (fixture.ps_home_score, fixture.ps_away_score) == (None, None)
    assert fixture.went_beyond_regulation is True
    assert fixture.status == STATUS_FINISHED


def test_a_shootout_is_never_counted_as_a_goal():
    fixture = _fixture_from_payload(knockout_payload(**SHOOTOUT_TIE), "champions_league")

    assert (fixture.home_score, fixture.away_score) == (1, 1)
    assert (fixture.ft_home_score, fixture.ft_away_score) == (1, 1)
    assert (fixture.ps_home_score, fixture.ps_away_score) == (4, 3)
    assert fixture.went_beyond_regulation is True


def test_a_match_that_ended_at_ninety_reports_no_extra_periods():
    fixture = _fixture_from_payload(knockout_payload(**NINETY_MINUTES), "champions_league")

    assert (fixture.home_score, fixture.away_score) == (2, 1)
    assert (fixture.ft_home_score, fixture.ft_away_score) == (2, 1)
    assert (fixture.et_home_score, fixture.et_away_score) == (None, None)
    assert fixture.went_beyond_regulation is False


# ----------------------------------------------------------------------------- the stored row
def test_the_registry_stores_the_periods_beside_the_final_score(db):
    match = ingest(db, **AET_TIE)
    result = stored_result(db, match)

    assert (result.home_score, result.away_score) == (2, 1)      # the match really finished 2-1
    assert (result.home_score_ft, result.away_score_ft) == (1, 1)
    assert (result.home_score_et, result.away_score_et) == (2, 1)
    assert (result.home_score_pens, result.away_score_pens) == (None, None)
    assert result.result_metadata.get("went_beyond_regulation") is True


def test_the_registry_stores_a_shootout_without_adding_it_to_the_goals(db):
    result = stored_result(db, ingest(db, **SHOOTOUT_TIE))

    assert (result.home_score, result.away_score) == (1, 1)
    assert (result.home_score_pens, result.away_score_pens) == (4, 3)


# ----------------------------------------------------------------------------- settlement
def test_a_tie_won_in_extra_time_settles_as_the_draw_it_was_at_ninety(db):
    match = ingest(db, **AET_TIE)
    backed_the_draw = predict(db, match, home=0.2, draw=0.6, away=0.2)
    backed_the_home_win = predict(db, match, home=0.7, draw=0.2, away=0.1)

    settle(db)

    # The bug settled this as a home win off `goals`. Regulation was 1-1.
    assert scored(db, backed_the_draw).actual_outcome == "draw"
    assert scored(db, backed_the_draw).is_correct is True
    assert scored(db, backed_the_home_win).is_correct is False


def test_a_tie_won_on_penalties_settles_on_the_goals_not_the_shootout(db):
    match = ingest(db, **SHOOTOUT_TIE)
    prediction = predict(db, match, home=0.2, draw=0.6, away=0.2)

    settle(db)

    row = scored(db, prediction)
    assert row.actual_outcome == "draw"      # 4-3 on penalties is not a 4-3 win
    assert row.is_correct is True


def test_an_ordinary_ninety_minute_win_still_settles_on_its_score(db):
    match = ingest(db, **NINETY_MINUTES)
    prediction = predict(db, match, home=0.7, draw=0.2, away=0.1)

    settle(db)

    row = scored(db, prediction)
    assert row.actual_outcome == "home"
    assert row.is_correct is True


def test_a_tie_known_to_have_gone_long_with_no_regulation_score_is_withheld(db):
    """
    The provider that records a knockout tie but no period breakdown.

    There is one score and it covers more football than the market pays out on, so there is
    nothing safe to settle. Withholding leaves the prediction pending for a provider that can
    supply the 90 minutes; settling it would mark people wrong off the wrong scoreline.
    """
    match = ingest(db, **AET_TIE)
    result = stored_result(db, match)
    result.home_score_ft, result.away_score_ft = None, None      # breakdown never supplied
    result.home_score_et, result.away_score_et = None, None
    db.flush()
    prediction = predict(db, match)

    report = settle(db)

    assert db.query(PredictionResult).filter(
        PredictionResult.prediction_id == prediction.id).count() == 0
    assert any("regulation time only" in skipped["reason"]
               for skipped in report["skipped_matches"])
