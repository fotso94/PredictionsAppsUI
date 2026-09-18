"""Database-backed tests for the scoring state published by /data-providers/coverage.

The bug these lock down: the coverage payload carried two constants,

    "accuracy_available": False,
    "accuracy_unavailable_reason": "no settled results have been scored yet",

which were true the day they were written and stayed "true" once settlement began writing scores,
because a constant cannot notice the database. The home page and the dashboard read those two keys,
so both told visitors nothing had been scored while four scored forecasts sat in the table.

What is asserted here:
* the three states are kept apart - nothing scored, scored but below the minimum sample, and a
  figure exists - and each is reached from the data alone;
* the reason string is measured, not a constant: it changes as rows are added, and the old sentence
  never comes back;
* the counts are published in every state and a percentage is published in none of them: the rate
  belongs to /performance/sources, which publishes it with its sample and its definition;
* coverage and /performance/sources count the same forecasts, including the equal-timestamp
  snapshot twins that made settlement and the performance read disagree in the first place.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
No provider is ever called: every provider entry point raises if touched.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints.data_providers import (
    ACCURACY_AVAILABLE, ACCURACY_BELOW_MINIMUM_SAMPLE, ACCURACY_NOTHING_SCORED,
)
from app.core.deps import get_db as deps_get_db
from app.db.base import Base
from app.db.session import get_db as session_get_db
from app.main import app
from app.models.predictions import (
    Match, MatchResult, MatchStatus, Prediction, PredictionSource, PredictionStatus, Team,
)
from app.models.provider_data import ProviderForecastSnapshot
from app.models.users import AccountStatus, User, UserType
from app.services import settlement as S
from app.services.match_registry import MatchRegistry
from app.services.providers.http import ProviderHttpClient
from app.services.providers.sample import SampleDataProvider, SampleForecastProvider

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

COVERAGE = "/api/v1/data-providers/coverage"
SOURCES = "/api/v1/performance/sources"

# Inside the default measurement window (90 days back), and far enough from the fixtures of the
# other modules that nothing shares a kickoff with them.
KICKOFF = (datetime.now(timezone.utc) - timedelta(days=10)).replace(
    hour=19, minute=0, second=0, microsecond=0, tzinfo=None)

# The sentence the payload used to return whatever the database held. It must never come back.
OLD_CONSTANT = "no settled results have been scored yet"


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
    """Session joined to an outer transaction; endpoint-level commit() only releases a savepoint."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection,
                           join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def no_provider_calls(monkeypatch):
    """Coverage reads stored rows only; every way out to a provider is closed."""
    def refuse(name):
        def _refuse(*args, **kwargs):
            raise AssertionError(f"a provider call was made ({name}); this endpoint reads stored data only")
        return _refuse

    monkeypatch.setattr(ProviderHttpClient, "get_json", refuse("http get_json"))
    for method in ("get_fixtures", "get_live", "get_results", "get_standings", "list_competitions"):
        monkeypatch.setattr(SampleDataProvider, method, refuse(f"SampleDataProvider.{method}"))
    monkeypatch.setattr(SampleForecastProvider, "get_forecasts", refuse("SampleForecastProvider.get_forecasts"))


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    overrides = {deps_get_db: override_get_db, session_get_db: override_get_db}
    app.dependency_overrides.update(overrides)
    try:
        yield TestClient(app)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"tipster-{suffix}@test.local", username=f"tipster_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _match(db, status: MatchStatus = MatchStatus.FINISHED) -> Match:
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()

    def team(label):
        row = Team(id=uuid.uuid4(), name=f"{label} {uuid.uuid4().hex[:6]}", country="England")
        db.add(row)
        db.flush()
        return row

    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=team("Home").id,
                  away_team_id=team("Away").id, match_date=KICKOFF, status=status,
                  external_api_id=f"ext-cov-{uuid.uuid4().hex[:10]}", external_api_source="sample",
                  match_metadata={})
    db.add(match)
    db.flush()
    return match


def played(db, home: int, away: int) -> Match:
    match = _match(db)
    db.add(MatchResult(id=uuid.uuid4(), match_id=match.id, home_score=home, away_score=away,
                       result="H" if home > away else "A" if away > home else "D",
                       result_metadata={"provider": "sample"}))
    db.flush()
    db.refresh(match)
    return match


def _prediction(db, match: Match, user: User, home=0.6, draw=0.25, away=0.15) -> Prediction:
    row = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                     created_by=user.id, home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(draw)),
                     away_win_prob=Decimal(str(away)), confidence_score=Decimal("0.8"),
                     status=PredictionStatus.PUBLISHED, priority_level=100,
                     published_at=match.match_date - timedelta(hours=5), reasoning="test view")
    db.add(row)
    db.flush()
    return row


def _snapshot(db, match: Match, provider="gameforecast", captured: Optional[datetime] = None,
              home=0.5, draw=0.3, away=0.2) -> ProviderForecastSnapshot:
    """One stored prematch forecast. `captured` is shared between twins on purpose in one test."""
    fetched = captured or (match.match_date - timedelta(hours=2))
    row = ProviderForecastSnapshot(
        id=uuid.uuid4(), match_id=match.id, provider=provider,
        external_event_id=f"evt-{uuid.uuid4().hex[:8]}", match_confidence="exact",
        matched_by="provider_id", first_fetched_at=fetched, last_fetched_at=fetched,
        kickoff_at_capture=match.match_date, captured_before_kickoff=True,
        home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(draw)), away_win_prob=Decimal(str(away)))
    db.add(row)
    db.flush()
    return row


def _settle(db) -> None:
    S.SettlementService(db).settle_range(commit=False)


def _coverage(client) -> dict:
    response = client.get(COVERAGE)
    assert response.status_code == 200, response.text
    return response.json()


def _reason(body: dict) -> str:
    return body["accuracy_unavailable_reason"]


# ----------------------------------------------------------------------------- nothing scored
def test_an_installation_with_nothing_to_score_says_so(client):
    """No terminal match in the window: the state is "nothing scored", with the measured reason."""
    body = _coverage(client)

    assert body["accuracy_state"] == ACCURACY_NOTHING_SCORED
    assert body["accuracy_available"] is False
    assert body["scoring"]["eligible"] == 0 and body["scoring"]["scored"] == 0
    assert body["scoring"]["sources"] == 0
    assert "has been scored yet" in _reason(body)
    # the settlement service's own explanation of an empty window, not a sentence invented here
    assert "terminal status" in _reason(body)
    assert OLD_CONSTANT not in _reason(body)


def test_a_result_nobody_has_scored_yet_is_counted_as_pending_not_as_scored(client, db):
    """A played match with an unsettled prediction: still "nothing scored", but the counts show why."""
    expert = _expert(db)
    _prediction(db, played(db, 2, 0), expert)     # eligible, but settlement has not run

    body = _coverage(client)

    assert body["accuracy_state"] == ACCURACY_NOTHING_SCORED
    assert body["accuracy_available"] is False
    scoring = body["scoring"]
    assert scoring["eligible"] == 1 and scoring["scored"] == 0 and scoring["pending"] == 1
    assert scoring["published_figures"] == 0 and scoring["sources_measured"] == 0
    assert "1 eligible prediction(s)" in _reason(body) and "1 pending" in _reason(body)


# ----------------------------------------------------------------------------- below the minimum
def test_below_the_minimum_sample_the_counts_are_published_and_the_rate_is_not(client, db):
    """Three scored predictions: a different state from nothing scored, and still no percentage."""
    expert = _expert(db)
    for _ in range(3):
        _prediction(db, played(db, 2, 0), expert)     # three home wins, three home calls
    _settle(db)

    response = client.get(COVERAGE)
    body = response.json()

    assert body["accuracy_state"] == ACCURACY_BELOW_MINIMUM_SAMPLE
    assert body["accuracy_available"] is False
    scoring = body["scoring"]
    assert scoring["eligible"] == 3 and scoring["scored"] == 3 and scoring["pending"] == 0
    assert scoring["sources"] == 1 and scoring["sources_measured"] == 1
    assert scoring["published_figures"] == 0
    assert scoring["minimum_sample"] == S.MINIMUM_SCORED_SAMPLE
    # the reason names the measured counts and the rule, so it cannot be a constant
    assert "3 of 3 eligible prediction(s)" in _reason(body)
    assert str(S.MINIMUM_SCORED_SAMPLE) in _reason(body)
    assert OLD_CONSTANT not in _reason(body)
    # a perfect three-from-three is exactly the run a rate would flatter: none is published here
    assert "hit_rate" not in response.text and "brier" not in response.text


def test_the_window_the_counts_were_taken_over_is_published_with_them(client, db):
    """A count without its window is not interpretable, so coverage carries the window too."""
    expert = _expert(db)
    _prediction(db, played(db, 2, 0), expert)
    _settle(db)

    body = _coverage(client)
    window = body["scoring"]["window"]

    assert window == client.get(SOURCES).json()["window"]     # the same window as the detail page
    assert window["start"] in _reason(body) and window["end"] in _reason(body)
    assert body["scoring"]["detail"] == SOURCES


# ----------------------------------------------------------------------------- a figure exists
def test_at_the_minimum_sample_coverage_reports_that_a_figure_exists(client, db):
    """Thirty scored predictions: the performance module publishes a rate, so coverage says so."""
    expert = _expert(db)
    for index in range(S.MINIMUM_SCORED_SAMPLE):
        _prediction(db, played(db, 2, 0) if index < 21 else played(db, 0, 2), expert)
    _settle(db)

    response = client.get(COVERAGE)
    body = response.json()

    assert body["accuracy_state"] == ACCURACY_AVAILABLE
    assert body["accuracy_available"] is True
    assert body["accuracy_unavailable_reason"] is None
    scoring = body["scoring"]
    assert scoring["scored"] == S.MINIMUM_SCORED_SAMPLE and scoring["sources_measured"] == 1
    assert scoring["published_figures"] >= 1
    # the figure itself still lives on the performance page, with its sample and its definition
    assert "hit_rate" not in response.text
    market = next(m for m in client.get(SOURCES).json()["sources"][0]["markets"]
                  if m["market"] == S.MARKET_MATCH_RESULT)
    assert market["hit_rate_available"] is True and market["hit_rate_sample"] == S.MINIMUM_SCORED_SAMPLE


# ----------------------------------------------------------------------------- not a constant
def test_the_reason_is_measured_and_moves_with_the_database(client, db):
    """The regression proper: the same endpoint, three states, three different sentences."""
    expert = _expert(db)

    empty = _coverage(client)
    _prediction(db, played(db, 2, 0), expert)
    _settle(db)
    one_scored = _coverage(client)
    for _ in range(2):
        _prediction(db, played(db, 1, 0), expert)
    _settle(db)
    three_scored = _coverage(client)

    assert empty["accuracy_state"] == ACCURACY_NOTHING_SCORED
    assert one_scored["accuracy_state"] == ACCURACY_BELOW_MINIMUM_SAMPLE
    assert three_scored["accuracy_state"] == ACCURACY_BELOW_MINIMUM_SAMPLE
    # the counts moved with the rows
    assert [empty["scoring"]["scored"], one_scored["scoring"]["scored"],
            three_scored["scoring"]["scored"]] == [0, 1, 3]
    # and so did the explanation: three readings, three distinct strings, none of them the constant
    reasons = [_reason(empty), _reason(one_scored), _reason(three_scored)]
    assert len(set(reasons)) == 3, reasons
    assert all(OLD_CONSTANT not in reason for reason in reasons)


def test_the_keys_the_home_page_and_dashboard_already_read_still_answer(client, db):
    """Backward compatibility: the two original keys keep their names, types and meaning."""
    expert = _expert(db)
    _prediction(db, played(db, 2, 0), expert)
    _settle(db)

    body = _coverage(client)

    assert isinstance(body["accuracy_available"], bool)
    assert isinstance(body["accuracy_unavailable_reason"], str)
    for key in ("competitions_covered", "upcoming_matches", "matches_stored", "model_forecasts",
                "upcoming_matches_with_forecast", "forecast_snapshots",
                "expert_predictions_published", "measured_at"):
        assert key in body, key


# ----------------------------------------------------------------------------- one count, not two
def test_coverage_and_the_performance_page_count_the_same_forecasts(client, db):
    """Coverage must not grow a second way of counting; it reuses the settlement service's own.

    The two snapshots of the second match share a ``first_fetched_at`` to the microsecond, which is
    the shape the live table is in: the migration backfilled one snapshot per forecast stamped with
    the record's retrieval time, and the repair script appended its corrected re-reading with that
    same time, deliberately, because a repair retrieves nothing. Both endpoints must land on the
    same snapshot of that forecast and report the same counts.
    """
    first, second = played(db, 2, 0), played(db, 0, 1)
    _snapshot(db, first)
    twin_time = second.match_date - timedelta(hours=3)
    _snapshot(db, second, captured=twin_time)
    _snapshot(db, second, captured=twin_time)     # same forecast, same timestamp, second version
    _settle(db)

    coverage_body = _coverage(client)
    sources = client.get(SOURCES).json()["sources"]

    assert coverage_body["scoring"]["scored"] == sum(s["scored"] for s in sources)
    assert coverage_body["scoring"]["pending"] == sum(s["pending"] for s in sources)
    assert coverage_body["scoring"]["eligible"] == sum(s["eligible"] for s in sources)
    assert coverage_body["scoring"]["sources_measured"] == len([s for s in sources if s["measured"]])
    # one forecast per match, both scored: the twin must not be reported as a second, pending one
    assert coverage_body["scoring"]["eligible"] == 2
    assert coverage_body["scoring"]["scored"] == 2 and coverage_body["scoring"]["pending"] == 0
    assert coverage_body["accuracy_state"] == ACCURACY_BELOW_MINIMUM_SAMPLE
