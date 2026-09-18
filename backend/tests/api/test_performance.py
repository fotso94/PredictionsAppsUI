"""Database-backed tests for the measured-performance endpoints.

What these lock down:
* /performance/rules publishes the ruleset every score was computed with.
* /performance/sources counts from stored score rows only, and never invents a figure: a source with
  nothing scored says why, and an accuracy headline is withheld below the minimum sample even when
  the source is on a perfect run.
* Every accuracy number that IS published arrives with its sample size and its definition.
* A void is reported as a void, never as a loss.
* /performance/settle is admin-only and idempotent.
* None of these endpoints issues a provider request: every provider entry point raises if touched.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
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

from app.core.deps import get_current_admin_user
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

# Far enough back that no other module's fixtures share the window.
KICKOFF = (datetime.now(timezone.utc) - timedelta(days=120)).replace(
    hour=19, minute=0, second=0, microsecond=0, tzinfo=None)
WINDOW = {"start": (KICKOFF - timedelta(days=1)).date().isoformat(),
          "end": (KICKOFF + timedelta(days=1)).date().isoformat()}


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
    """Every way out to a provider, closed: these endpoints read stored data only."""
    def refuse(name):
        def _refuse(*args, **kwargs):
            raise AssertionError(f"a provider call was made ({name}); these endpoints read stored data only")
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
        app.dependency_overrides.pop(get_current_admin_user, None)


@pytest.fixture
def as_admin(db):
    """Sign an admin in for the following requests (test-only; real authentication is untouched)."""
    def _as() -> User:
        suffix = uuid.uuid4().hex[:8]
        admin = User(id=uuid.uuid4(), email=f"admin-{suffix}@test.local", username=f"admin_{suffix}",
                     password_hash="not-a-real-hash", user_type=UserType.ADMIN,
                     account_status=AccountStatus.ACTIVE, email_verified=True)
        db.add(admin)
        db.flush()
        app.dependency_overrides[get_current_admin_user] = lambda: admin
        return admin
    yield _as
    app.dependency_overrides.pop(get_current_admin_user, None)


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"pundit-{suffix}@test.local", username=f"pundit_{suffix}",
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
                  external_api_id=f"ext-perf-{uuid.uuid4().hex[:10]}", external_api_source="sample",
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


def _snapshot(db, match: Match, provider="gameforecast", before_kickoff: Optional[bool] = True,
              home=0.5, draw=0.3, away=0.2) -> ProviderForecastSnapshot:
    captured = match.match_date - timedelta(hours=2) if before_kickoff is not False \
        else match.match_date + timedelta(hours=1)
    row = ProviderForecastSnapshot(
        id=uuid.uuid4(), match_id=match.id, provider=provider,
        external_event_id=f"evt-{uuid.uuid4().hex[:8]}", match_confidence="exact",
        matched_by="provider_id", first_fetched_at=captured, last_fetched_at=captured,
        kickoff_at_capture=match.match_date, captured_before_kickoff=before_kickoff,
        home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(draw)), away_win_prob=Decimal(str(away)))
    db.add(row)
    db.flush()
    return row


def _settle(db) -> None:
    S.SettlementService(db).settle_range(commit=False)


def _source(payload, source_id: str):
    return next(s for s in payload["sources"] if s["source_id"] == source_id)


def _market(source, name: str = S.MARKET_MATCH_RESULT):
    return next(m for m in source["markets"] if m["market"] == name)


# ----------------------------------------------------------------------------- rules
def test_rules_are_published_on_their_own(client):
    response = client.get("/api/v1/performance/rules")
    assert response.status_code == 200, response.text
    rules = response.json()
    assert rules["version"] == S.RULES_VERSION
    assert "90 minutes plus stoppage" in rules["basis"]
    assert "never a loss" in rules["void"]
    assert rules["minimum_sample"] == S.MINIMUM_SCORED_SAMPLE
    assert rules["minimum_sample_rationale"]
    assert S.MARKET_MATCH_RESULT in rules["markets"]


# ----------------------------------------------------------------------------- sources
def test_an_empty_window_says_there_is_nothing_to_score(client):
    response = client.get("/api/v1/performance/sources", params=WINDOW)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sources"] == [] and payload["sources_measured"] == 0
    assert "nothing to score" in payload["not_measured_reason"]
    assert payload["window"] == {"start": WINDOW["start"], "end": WINDOW["end"],
                                 "basis": "kickoff date in UTC, both ends included"}


def test_a_perfect_run_below_the_minimum_sample_publishes_no_accuracy(client, db):
    expert = _expert(db)
    for _ in range(5):
        _prediction(db, played(db, 3, 0), expert)     # five home wins, five home calls
    _settle(db)

    payload = client.get("/api/v1/performance/sources", params=WINDOW).json()
    source = _source(payload, str(expert.id))
    assert source["eligible"] == 5 and source["scored"] == 5 and source["pending"] == 0
    assert source["source_type"] == "expert" and source["source_label"] == expert.username

    result = _market(source)
    assert result["hits"] == 5 and result["scored"] == 5
    assert result["hit_rate"] is None and result["hit_rate_available"] is False
    assert str(S.MINIMUM_SCORED_SAMPLE) in result["hit_rate_unavailable_reason"]
    assert result["brier_score"] is None and result["brier_available"] is False
    # the counts behind the withheld figure are still published, as is the rule that produced them
    assert result["hit_rate_sample"] == 5
    assert "most likely" in result["hit_rate_definition"]
    assert "regulation-time score" in result["rule"]


def test_at_the_minimum_sample_the_figure_arrives_with_its_sample_and_definition(client, db):
    expert = _expert(db)
    for index in range(S.MINIMUM_SCORED_SAMPLE):
        match = played(db, 2, 0) if index < 21 else played(db, 0, 2)
        _prediction(db, match, expert)
    _settle(db)

    payload = client.get("/api/v1/performance/sources", params=WINDOW).json()
    source = _source(payload, str(expert.id))
    result = _market(source)
    assert source["measured"] is True and source["not_measured_reason"] is None
    assert result["hit_rate"] == 0.7
    assert result["hit_rate_sample"] == S.MINIMUM_SCORED_SAMPLE
    assert result["hit_rate_available"] is True
    assert result["hit_rate_definition"]
    assert result["brier_available"] is True and result["brier_sample"] == S.MINIMUM_SCORED_SAMPLE
    assert result["brier_baseline"] == 0.6667
    assert payload["rules"]["version"] == S.RULES_VERSION
    assert payload["sources_measured"] == 1


def test_a_provider_with_no_prematch_snapshot_is_not_measured_and_not_zeroed(client, db):
    match = played(db, 2, 0)
    _snapshot(db, match, before_kickoff=False, home=0.9, draw=0.05, away=0.05)
    _settle(db)

    payload = client.get("/api/v1/performance/sources", params=WINDOW).json()
    source = _source(payload, "gameforecast")
    assert source["source_type"] == "model_provider"
    assert source["scored"] == 0 and source["not_scored"] == 1 and source["markets"] == []
    assert source["measured"] is False
    assert source["not_measured_reason"]
    assert source["not_scored_reasons"][0]["count"] == 1
    assert "before kickoff" in source["not_scored_reasons"][0]["reason"]


def test_a_void_is_reported_as_a_void_not_a_loss(client, db):
    expert = _expert(db)
    _prediction(db, _match(db, status=MatchStatus.POSTPONED), expert)
    _settle(db)

    source = _source(client.get("/api/v1/performance/sources", params=WINDOW).json(), str(expert.id))
    assert source["void"] == 1 and source["scored"] == 0
    result = _market(source)
    assert result["voids"] == 1 and result["hits"] == 0 and result["scored"] == 0


def test_an_unsettled_match_is_pending_rather_than_missing(client, db):
    expert = _expert(db)
    _prediction(db, played(db, 1, 1), expert)     # no settlement run

    source = _source(client.get("/api/v1/performance/sources", params=WINDOW).json(), str(expert.id))
    assert source["eligible"] == 1 and source["pending"] == 1 and source["scored"] == 0
    assert source["measured"] is False


def test_the_window_is_validated_before_any_work_is_done(client):
    swapped = client.get("/api/v1/performance/sources",
                         params={"start": WINDOW["end"], "end": WINDOW["start"]})
    assert swapped.status_code == 400
    assert "start must not be after end" in swapped.json()["detail"]

    too_long = client.get("/api/v1/performance/sources", params={"start": "2020-01-01", "end": "2026-01-01"})
    assert too_long.status_code == 400
    assert str(S.MAX_WINDOW_DAYS) in too_long.json()["detail"]


# ----------------------------------------------------------------------------- settle
def test_settlement_requires_an_administrator(client, db):
    _prediction(db, played(db, 2, 0), _expert(db))
    refused = client.post("/api/v1/performance/settle", params=WINDOW)
    assert refused.status_code in (401, 403)


def test_an_admin_can_settle_and_re_running_changes_nothing(client, db, as_admin):
    admin = as_admin()
    expert = _expert(db)
    match = played(db, 2, 0)
    _prediction(db, match, expert)
    _snapshot(db, match)

    first = client.post("/api/v1/performance/settle", params=WINDOW)
    assert first.status_code == 200, first.text
    report = first.json()
    assert report["expert_predictions"]["settled"] == 1
    assert report["provider_forecasts"]["settled"] == 1
    assert report["rules_version"] == S.RULES_VERSION
    assert report["settled_by"] == str(admin.id)

    second = client.post("/api/v1/performance/settle", params=WINDOW).json()
    assert second["expert_predictions"]["settled"] == 0
    assert second["expert_predictions"]["unchanged"] == 1
    assert second["provider_forecasts"]["unchanged"] == 1

    # and the measurement afterwards counts each source exactly once
    payload = client.get("/api/v1/performance/sources", params=WINDOW).json()
    assert _source(payload, str(expert.id))["scored"] == 1
    assert _source(payload, "gameforecast")["scored"] == 1
