"""Database-backed tests for result scoring.

The local database holds no finished match at all - every stored fixture is still upcoming - so
every result in here is constructed. That is the point: these tests pin down what "was it right?"
means before there is any real data to argue about.

Covered: a home win, a draw and an away win; both-teams-to-score either way; over and under on both
lines; a postponed fixture voiding rather than losing; a market the source never published being
skipped rather than counted as a loss; a snapshot captured after kickoff (and one captured with the
kickoff unknown) being refused; an expert prediction edited after kickoff being scored on the
version that stood at kickoff; idempotent re-runs; and the minimum-sample refusal.

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
    Match, MatchResult, MatchStatus, Prediction, PredictionAudit, PredictionOutcome,
    PredictionResult, PredictionSource, PredictionStatus, Team,
)
from app.models.provider_data import ProviderForecastResult, ProviderForecastSnapshot
from app.models.users import AccountStatus, User, UserType
from app.services.expert_prediction import REVISION_ACTION
from app.services.match_registry import MatchRegistry
from app.services import settlement as S

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

# Well in the past and far from every other module's fixtures, so nothing here collides.
KICKOFF = (datetime.now(timezone.utc) - timedelta(days=200)).replace(
    hour=15, minute=0, second=0, microsecond=0, tzinfo=None)


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


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"tipster-{suffix}@test.local", username=f"tipster_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:6]}", country="England")
    db.add(team)
    db.flush()
    return team


def _match(db, status: MatchStatus = MatchStatus.FINISHED, kickoff: datetime = KICKOFF) -> Match:
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=_team(db, "Home").id,
                  away_team_id=_team(db, "Away").id, match_date=kickoff, status=status,
                  external_api_id=f"ext-settle-{uuid.uuid4().hex[:10]}", external_api_source="sample",
                  match_metadata={})
    db.add(match)
    db.flush()
    return match


def _result(db, match: Match, home: int, away: int, metadata: Optional[Dict[str, Any]] = None) -> MatchResult:
    outcome = "H" if home > away else "A" if away > home else "D"
    row = MatchResult(id=uuid.uuid4(), match_id=match.id, home_score=home, away_score=away,
                      result=outcome, result_metadata=metadata or {"provider": "sample"})
    db.add(row)
    db.flush()
    db.refresh(match)
    return row


def played(db, home: int, away: int, metadata: Optional[Dict[str, Any]] = None) -> Match:
    """A finished match with a stored score."""
    match = _match(db)
    _result(db, match, home, away, metadata)
    return match


def _prediction(db, match: Match, user: User, home=0.5, draw=0.3, away=0.2,
                published_at: Optional[datetime] = None, **markets) -> Prediction:
    row = Prediction(
        id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL, created_by=user.id,
        home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(draw)), away_win_prob=Decimal(str(away)),
        confidence_score=Decimal("0.8"), status=PredictionStatus.PUBLISHED, priority_level=100,
        published_at=published_at or (match.match_date - timedelta(hours=6)),
        reasoning="constructed for a settlement test",
        **{name: (Decimal(str(value)) if value is not None else None) for name, value in markets.items()})
    db.add(row)
    db.flush()
    return row


def _snapshot(db, match: Match, provider: str = "gameforecast", before_kickoff: Optional[bool] = True,
              **markets) -> ProviderForecastSnapshot:
    captured = match.match_date - timedelta(hours=3) if before_kickoff is not False \
        else match.match_date + timedelta(hours=1)
    row = ProviderForecastSnapshot(
        id=uuid.uuid4(), match_id=match.id, provider=provider,
        external_event_id=f"evt-{uuid.uuid4().hex[:8]}", match_confidence="exact",
        matched_by="provider_id", first_fetched_at=captured, last_fetched_at=captured,
        kickoff_at_capture=match.match_date, captured_before_kickoff=before_kickoff,
        **{name: (Decimal(str(value)) if isinstance(value, (int, float)) else value)
           for name, value in markets.items()})
    db.add(row)
    db.flush()
    return row


def market(row, name: str) -> Dict[str, Any]:
    """One market entry off a stored score row."""
    return next(entry for entry in row.market_results if entry["market"] == name)


def settle(db) -> Dict[str, Any]:
    return S.SettlementService(db).settle_range(commit=False)


def stored_prediction_result(db, prediction: Prediction) -> PredictionResult:
    return db.query(PredictionResult).filter(PredictionResult.prediction_id == prediction.id).one()


def stored_forecast_result(db, snapshot: ProviderForecastSnapshot) -> ProviderForecastResult:
    return db.query(ProviderForecastResult).filter(
        ProviderForecastResult.snapshot_id == snapshot.id).one()


# ----------------------------------------------------------------------------- 1X2
@pytest.mark.parametrize("home_goals,away_goals,expected", [(2, 0, "home"), (1, 1, "draw"), (0, 3, "away")])
def test_match_result_settles_on_the_regulation_scoreline(db, home_goals, away_goals, expected):
    match = played(db, home_goals, away_goals)
    user = _expert(db)
    # the expert's most likely outcome is always "home"; only one of the three parametrisations hits
    prediction = _prediction(db, match, user, home=0.6, draw=0.25, away=0.15)
    settle(db)

    row = stored_prediction_result(db, prediction)
    assert row.actual_outcome == expected
    assert row.outcome == (PredictionOutcome.WON if expected == "home" else PredictionOutcome.LOST)
    assert row.is_correct is (expected == "home")
    assert row.rules_version == S.RULES_VERSION
    assert row.match_result_id == match.result.id

    entry = market(row, S.MARKET_MATCH_RESULT)
    assert entry["predicted"] == "home" and entry["actual"] == expected
    # the probability stored is the one the expert published for what actually happened - not a
    # derived "closeness" number
    assert entry["probability_of_actual"] == {"home": 0.6, "draw": 0.25, "away": 0.15}[expected]
    assert "regulation-time score" in entry["rule"]


def test_brier_score_is_the_published_distribution_against_what_happened(db):
    match = played(db, 0, 1)          # away win
    prediction = _prediction(db, match, _expert(db), home=0.6, draw=0.25, away=0.15)
    settle(db)

    row = stored_prediction_result(db, prediction)
    # (0.6-0)^2 + (0.25-0)^2 + (0.15-1)^2 = 0.36 + 0.0625 + 0.7225
    assert float(row.brier_score) == pytest.approx(1.145, abs=1e-9)
    assert float(row.probability_of_actual) == 0.15


def test_probabilities_that_do_not_sum_to_one_are_not_renormalised(db):
    match = played(db, 2, 0)
    snapshot = _snapshot(db, match, home_win_prob=0.5, draw_prob=0.2, away_win_prob=0.1)
    settle(db)

    row = stored_forecast_result(db, snapshot)
    entry = market(row, S.MARKET_MATCH_RESULT)
    # the hit test only compares sizes, so it still applies ...
    assert row.outcome == PredictionOutcome.WON and entry["predicted"] == "home"
    # ... but a proper score would need numbers the source never published
    assert row.brier_score is None
    assert "renormalising" in entry["reason"]


def test_a_shared_highest_probability_is_a_push_not_a_guess(db):
    match = played(db, 2, 0)
    prediction = _prediction(db, match, _expert(db), home=0.4, draw=0.2, away=0.4)
    settle(db)

    row = stored_prediction_result(db, prediction)
    assert row.outcome == PredictionOutcome.PUSH
    assert row.is_correct is None
    assert "no single most likely outcome" in market(row, S.MARKET_MATCH_RESULT)["reason"]
    # the probabilistic score still applies: a push is not an absence of evidence
    assert row.brier_score is not None


# ----------------------------------------------------------------------------- BTTS and goal lines
@pytest.mark.parametrize("home_goals,away_goals,both_scored", [(2, 1, True), (2, 0, False)])
def test_both_teams_to_score_settles_on_regulation_goals(db, home_goals, away_goals, both_scored):
    match = played(db, home_goals, away_goals)
    prediction = _prediction(db, match, _expert(db), btts_yes_prob=0.65, btts_no_prob=0.35)
    settle(db)

    entry = market(stored_prediction_result(db, prediction), S.MARKET_BTTS)
    assert entry["actual"] == ("yes" if both_scored else "no")
    assert entry["predicted"] == "yes"
    assert entry["outcome"] == (S.WON if both_scored else S.LOST)
    assert entry["probability_of_actual"] == (0.65 if both_scored else 0.35)


@pytest.mark.parametrize("home_goals,away_goals,over_25,over_35", [
    (0, 0, False, False),   # 0 goals: under both lines
    (2, 0, False, False),   # 2 goals: under 2.5 and under 3.5
    (2, 1, True, False),    # 3 goals: over 2.5, under 3.5
    (3, 1, True, True),     # 4 goals: over both lines
])
def test_goal_lines_settle_on_the_regulation_total(db, home_goals, away_goals, over_25, over_35):
    match = played(db, home_goals, away_goals)
    prediction = _prediction(db, match, _expert(db),
                             total_goals_over_25_prob=0.55, total_goals_under_25_prob=0.45,
                             total_goals_over_35_prob=0.3, total_goals_under_35_prob=0.7)
    settle(db)

    row = stored_prediction_result(db, prediction)
    line_25 = market(row, S.MARKET_OVER_UNDER_25)
    line_35 = market(row, S.MARKET_OVER_UNDER_35)
    assert line_25["actual"] == ("over" if over_25 else "under")
    assert line_35["actual"] == ("over" if over_35 else "under")
    # the expert leans over on 2.5 and under on 3.5, so each line is a hit exactly when it matches
    assert line_25["outcome"] == (S.WON if over_25 else S.LOST)
    assert line_35["outcome"] == (S.LOST if over_35 else S.WON)


def test_a_market_the_source_never_published_is_skipped_not_lost(db):
    match = played(db, 2, 1)
    prediction = _prediction(db, match, _expert(db), home=0.6, draw=0.25, away=0.15)  # 1X2 only
    settle(db)

    row = stored_prediction_result(db, prediction)
    for name in (S.MARKET_BTTS, S.MARKET_OVER_UNDER_25, S.MARKET_OVER_UNDER_35):
        entry = market(row, name)
        assert entry["outcome"] == S.NOT_SCORED, name
        assert entry["outcome"] != S.LOST
        assert entry["probability_of_actual"] is None
        assert "no probability" in entry["reason"]
    # and it never becomes a zero in the aggregate either
    measured = S.measure_sources(db, KICKOFF - timedelta(days=1), KICKOFF + timedelta(days=1))
    btts = next(m for m in measured[0]["markets"] if m["market"] == S.MARKET_BTTS)
    assert btts["scored"] == 0 and btts["not_scored"] == 1 and btts["hits"] == 0
    assert btts["hit_rate"] is None


def test_one_published_side_of_a_two_way_market_is_not_enough(db):
    match = played(db, 2, 1)
    prediction = _prediction(db, match, _expert(db), total_goals_over_25_prob=0.55)
    settle(db)

    entry = market(stored_prediction_result(db, prediction), S.MARKET_OVER_UNDER_25)
    assert entry["outcome"] == S.NOT_SCORED
    assert "would have to be derived" in entry["reason"]


def test_correct_score_scores_only_the_scorelines_the_source_listed(db):
    match = played(db, 2, 1)
    listed = _snapshot(db, match, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                       exact_score={"2-1": 0.14, "1-0": 0.11}, exact_score_other_prob=Decimal("0.6"))
    unlisted_match = played(db, 4, 3)
    unlisted = _snapshot(db, unlisted_match, provider="gameforecast",
                         home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                         exact_score={"1-0": 0.2, "2-0": 0.1})
    settle(db)

    hit = market(stored_forecast_result(db, listed), S.MARKET_CORRECT_SCORE)
    assert hit["outcome"] == S.WON and hit["predicted"] == "2-1" and hit["probability_of_actual"] == 0.14

    miss = market(stored_forecast_result(db, unlisted), S.MARKET_CORRECT_SCORE)
    assert miss["outcome"] == S.LOST and miss["actual"] == "4-3"
    # the "other scorelines" remainder is never read as a prediction of 4-3
    assert miss["probability_of_actual"] is None
    assert "not among the ones the source listed" in miss["reason"]
    assert miss["brier_score"] is None


# ----------------------------------------------------------------------------- void
@pytest.mark.parametrize("status,phrase", [(MatchStatus.POSTPONED, "postponed"),
                                           (MatchStatus.CANCELLED, "cancelled or abandoned")])
def test_a_fixture_that_was_never_played_voids_every_market(db, status, phrase):
    match = _match(db, status=status)
    prediction = _prediction(db, match, _expert(db), home=0.6, draw=0.25, away=0.15,
                             btts_yes_prob=0.6, btts_no_prob=0.4)
    snapshot = _snapshot(db, match, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2)
    settle(db)

    row = stored_prediction_result(db, prediction)
    assert row.outcome == PredictionOutcome.VOID
    assert row.is_correct is None and row.actual_outcome is None
    assert row.match_result_id is None and row.brier_score is None
    assert phrase in row.void_reason
    assert {entry["outcome"] for entry in row.market_results} == {S.VOID}
    assert stored_forecast_result(db, snapshot).outcome == PredictionOutcome.VOID

    # a void never enters a hit rate
    measured = S.measure_sources(db, KICKOFF - timedelta(days=1), KICKOFF + timedelta(days=1))
    for source in measured:
        assert source["void"] == 1 and source["scored"] == 0
        assert source["measured"] is False
        assert "voided" in source["not_measured_reason"]


def test_a_result_that_went_beyond_regulation_time_is_refused_rather_than_scored(db):
    match = played(db, 2, 1, metadata={"provider": "sample", "period": "AET"})
    prediction = _prediction(db, match, _expert(db))
    report = settle(db)

    assert db.query(PredictionResult).filter(PredictionResult.prediction_id == prediction.id).count() == 0
    assert any("regulation time only" in skipped["reason"] for skipped in report["skipped_matches"])


def test_a_finished_match_with_no_stored_score_is_left_pending(db):
    match = _match(db, status=MatchStatus.FINISHED)      # no MatchResult row
    prediction = _prediction(db, match, _expert(db))
    report = settle(db)

    assert db.query(PredictionResult).filter(PredictionResult.prediction_id == prediction.id).count() == 0
    assert any("no score is stored" in skipped["reason"] for skipped in report["skipped_matches"])


# ----------------------------------------------------------------------------- prematch evidence only
def test_a_snapshot_captured_after_kickoff_is_never_scored(db):
    match = played(db, 2, 0)
    late = _snapshot(db, match, before_kickoff=False, home_win_prob=0.9, draw_prob=0.05, away_win_prob=0.05)
    report = settle(db)

    assert db.query(ProviderForecastResult).filter(
        ProviderForecastResult.snapshot_id == late.id).count() == 0
    assert report["provider_forecasts"]["settled"] == 0
    assert report["provider_forecasts"]["not_scored"] == 1
    assert "before kickoff" in report["not_scored"][0]["reason"]


def test_a_snapshot_whose_kickoff_was_unknown_is_not_treated_as_prematch(db):
    match = played(db, 2, 0)
    unknown = _snapshot(db, match, before_kickoff=None, home_win_prob=0.9, draw_prob=0.05, away_win_prob=0.05)
    settle(db)

    assert db.query(ProviderForecastResult).filter(
        ProviderForecastResult.snapshot_id == unknown.id).count() == 0


def test_the_last_prematch_snapshot_is_the_one_scored(db):
    match = played(db, 0, 2)
    early = _snapshot(db, match, home_win_prob=0.8, draw_prob=0.1, away_win_prob=0.1)
    early.first_fetched_at = match.match_date - timedelta(days=3)
    later = _snapshot(db, match, home_win_prob=0.2, draw_prob=0.2, away_win_prob=0.6)
    later.first_fetched_at = match.match_date - timedelta(hours=2)
    db.flush()
    settle(db)

    assert db.query(ProviderForecastResult).filter(
        ProviderForecastResult.snapshot_id == early.id).count() == 0
    row = stored_forecast_result(db, later)
    assert row.outcome == PredictionOutcome.WON and float(row.probability_of_actual) == 0.6
    assert row.snapshot_captured_at == later.first_fetched_at


def test_a_prediction_published_after_kickoff_is_never_scored(db):
    match = played(db, 2, 0)
    late = _prediction(db, match, _expert(db), published_at=match.match_date + timedelta(minutes=30))
    report = settle(db)

    assert db.query(PredictionResult).filter(PredictionResult.prediction_id == late.id).count() == 0
    assert report["expert_predictions"]["not_scored"] == 1
    assert report["not_scored"][0]["reason"] == "published at or after kickoff"


def test_a_prediction_edited_after_kickoff_is_scored_on_the_version_that_stood_at_kickoff(db):
    match = played(db, 2, 0)
    prediction = _prediction(db, match, _expert(db), home=0.2, draw=0.3, away=0.5)
    # the live row now says "home", but that is what the expert wrote AFTER the match started
    prediction.home_win_prob = Decimal("0.7")
    prediction.draw_prob, prediction.away_win_prob = Decimal("0.2"), Decimal("0.1")
    db.add(PredictionAudit(
        id=uuid.uuid4(), prediction_id=prediction.id, user_id=prediction.created_by,
        action=REVISION_ACTION, action_description="edited after kickoff",
        old_values={"home_win_prob": 0.2, "draw_prob": 0.3, "away_win_prob": 0.5},
        new_values={"home_win_prob": 0.7, "draw_prob": 0.2, "away_win_prob": 0.1},
        created_at=match.match_date + timedelta(minutes=20),
        updated_at=match.match_date + timedelta(minutes=20)))
    db.flush()
    settle(db)

    row = stored_prediction_result(db, prediction)
    entry = market(row, S.MARKET_MATCH_RESULT)
    assert entry["predicted"] == "away"                     # the prematch view, not the edited one
    assert row.outcome == PredictionOutcome.LOST
    assert float(row.probability_of_actual) == 0.2
    assert "restored from revision" in entry["evidence"]


def test_an_edit_before_kickoff_is_the_prematch_view(db):
    match = played(db, 2, 0)
    prediction = _prediction(db, match, _expert(db), home=0.7, draw=0.2, away=0.1)
    db.add(PredictionAudit(
        id=uuid.uuid4(), prediction_id=prediction.id, user_id=prediction.created_by,
        action=REVISION_ACTION, action_description="corrected before kickoff",
        old_values={"home_win_prob": 0.2, "draw_prob": 0.3, "away_win_prob": 0.5},
        new_values={"home_win_prob": 0.7, "draw_prob": 0.2, "away_win_prob": 0.1},
        created_at=match.match_date - timedelta(hours=2),
        updated_at=match.match_date - timedelta(hours=2)))
    db.flush()
    settle(db)

    row = stored_prediction_result(db, prediction)
    assert row.outcome == PredictionOutcome.WON
    assert market(row, S.MARKET_MATCH_RESULT)["evidence"] == "as published"


def test_withdrawn_and_unpublished_predictions_are_not_scored(db):
    match = played(db, 2, 0)
    user = _expert(db)
    draft = _prediction(db, match, user)
    draft.status = PredictionStatus.PENDING
    withdrawn = _prediction(db, match, user)
    withdrawn.deleted_at = datetime.utcnow()
    db.flush()
    settle(db)

    assert db.query(PredictionResult).filter(
        PredictionResult.prediction_id.in_([draft.id, withdrawn.id])).count() == 0


# ----------------------------------------------------------------------------- idempotency
def test_running_settlement_twice_changes_nothing(db):
    match = played(db, 2, 1)
    prediction = _prediction(db, match, _expert(db), btts_yes_prob=0.6, btts_no_prob=0.4)
    snapshot = _snapshot(db, match, home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2)

    first = settle(db)
    assert first["expert_predictions"]["settled"] == 1 and first["provider_forecasts"]["settled"] == 1
    settled_at = stored_prediction_result(db, prediction).settled_at

    # expire everything so the second pass compares against what PostgreSQL actually stored (the
    # JSONB round trip included) rather than against objects still warm in the identity map
    db.expire_all()
    second = settle(db)
    assert second["expert_predictions"] == {"settled": 0, "updated": 0, "unchanged": 1, "void": 0,
                                            "not_scored": 0}
    assert second["provider_forecasts"] == {"settled": 0, "updated": 0, "unchanged": 1, "void": 0,
                                            "not_scored": 0}
    # one row each, and the original settlement time untouched
    assert db.query(PredictionResult).filter(PredictionResult.prediction_id == prediction.id).count() == 1
    assert db.query(ProviderForecastResult).filter(
        ProviderForecastResult.snapshot_id == snapshot.id).count() == 1
    assert stored_prediction_result(db, prediction).settled_at == settled_at


def test_a_corrected_result_is_rescored_in_place(db):
    match = played(db, 2, 0)
    prediction = _prediction(db, match, _expert(db), home=0.6, draw=0.25, away=0.15)
    settle(db)
    assert stored_prediction_result(db, prediction).outcome == PredictionOutcome.WON

    match.result.home_score, match.result.away_score, match.result.result = 0, 2, "A"
    db.flush()
    report = settle(db)

    assert report["expert_predictions"]["updated"] == 1
    assert db.query(PredictionResult).filter(PredictionResult.prediction_id == prediction.id).count() == 1
    assert stored_prediction_result(db, prediction).outcome == PredictionOutcome.LOST


# ----------------------------------------------------------------------------- measurement
def _thirty_scored_predictions(db, user: User, hits: int) -> None:
    """`hits` home wins and the rest away wins, against a prediction that always leans home."""
    for index in range(30):
        home_win = index < hits
        match = played(db, 2, 0) if home_win else played(db, 0, 2)
        _prediction(db, match, user, home=0.6, draw=0.25, away=0.15)
    settle(db)


def test_an_accuracy_headline_is_refused_below_the_minimum_sample(db):
    user = _expert(db)
    for _ in range(4):
        _prediction(db, played(db, 2, 0), user, home=0.6, draw=0.25, away=0.15)
    settle(db)

    payload = S.measurement(db, start=(KICKOFF - timedelta(days=1)).date(),
                            end=(KICKOFF + timedelta(days=1)).date())
    source = next(s for s in payload["sources"] if s["source_id"] == str(user.id))
    assert source["scored"] == 4 and source["measured"] is True
    result = next(m for m in source["markets"] if m["market"] == S.MARKET_MATCH_RESULT)
    assert result["hits"] == 4 and result["scored"] == 4
    # four out of four is 100% and it is still not published
    assert result["hit_rate"] is None and result["hit_rate_available"] is False
    assert f"below the minimum of {S.MINIMUM_SCORED_SAMPLE}" in result["hit_rate_unavailable_reason"]
    assert result["brier_score"] is None and result["brier_available"] is False
    assert payload["minimum_sample"] == S.MINIMUM_SCORED_SAMPLE


def test_at_the_minimum_sample_the_rate_is_published_with_its_sample_and_definition(db):
    user = _expert(db)
    _thirty_scored_predictions(db, user, hits=18)

    payload = S.measurement(db, start=(KICKOFF - timedelta(days=1)).date(),
                            end=(KICKOFF + timedelta(days=1)).date())
    source = next(s for s in payload["sources"] if s["source_id"] == str(user.id))
    result = next(m for m in source["markets"] if m["market"] == S.MARKET_MATCH_RESULT)

    assert source["scored"] == 30 and source["measured"] is True
    assert result["hit_rate"] == 0.6 and result["hit_rate_sample"] == 30
    assert result["hit_rate_available"] is True and result["hit_rate_unavailable_reason"] is None
    assert "most likely" in result["hit_rate_definition"]
    # the proper score comes with it: 18 x (0.16+0.0625+0.0225) + 12 x (0.36+0.0625+0.7225)
    assert result["brier_available"] is True
    assert result["brier_score"] == pytest.approx((18 * 0.245 + 12 * 1.145) / 30, abs=1e-5)
    assert result["brier_baseline"] == 0.6667
    assert result["brier_sample"] == 30


def test_a_source_with_nothing_scored_says_so_instead_of_showing_a_zero(db):
    match = played(db, 2, 0)
    _snapshot(db, match, before_kickoff=False, home_win_prob=0.6, draw_prob=0.2, away_win_prob=0.2)

    payload = S.measurement(db, start=(KICKOFF - timedelta(days=1)).date(),
                            end=(KICKOFF + timedelta(days=1)).date())
    source = next(s for s in payload["sources"] if s["source_type"] == "model_provider")
    assert source["scored"] == 0 and source["not_scored"] == 1
    assert source["measured"] is False
    assert source["not_measured_reason"] is not None
    assert "hit_rate" not in source            # no accuracy key at all at the source level
    assert source["not_scored_reasons"][0]["reason"].startswith("no snapshot")


def test_the_window_excludes_matches_outside_it(db):
    user = _expert(db)
    _prediction(db, played(db, 2, 0), user)
    settle(db)

    far = (KICKOFF + timedelta(days=30)).date()
    payload = S.measurement(db, start=far, end=far)
    assert payload["sources"] == []
    assert "nothing to score" in payload["not_measured_reason"]


def test_the_published_rules_travel_with_every_figure(db):
    payload = S.measurement(db, start=KICKOFF.date(), end=KICKOFF.date())
    rules = payload["rules"]
    assert rules["version"] == S.RULES_VERSION
    assert "90 minutes plus stoppage" in rules["basis"]
    assert "never a loss" in rules["void"]
    assert "never counted as a loss" in rules["unsupplied_market"]
    assert set(rules["markets"]) == {S.MARKET_MATCH_RESULT, S.MARKET_BTTS, S.MARKET_OVER_UNDER_25,
                                     S.MARKET_OVER_UNDER_35, S.MARKET_CORRECT_SCORE}
    assert rules["minimum_sample"] == S.MINIMUM_SCORED_SAMPLE
