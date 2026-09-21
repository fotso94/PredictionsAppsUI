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

import pydantic
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
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
from app.schemas.predictions import ExpertPredictionCreate, ExpertPredictionUpdate
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


def test_coverage_does_not_count_a_deleted_prediction_as_published(client, db):
    """An expert who removes a prediction must not keep being credited with it on the home page.

    Deletion is a soft delete, so a count that only filters on status keeps reporting removed
    predictions - which is how the home page came to claim 27 published while none were live.
    """
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "coverage-count")
    prediction = _publish(db, match, expert, datetime.utcnow())

    with_prediction = client.get("/api/v1/data-providers/coverage").json()["expert_predictions_published"]
    prediction.deleted_at = datetime.utcnow()
    db.flush()
    after_removal = client.get("/api/v1/data-providers/coverage").json()["expert_predictions_published"]

    assert after_removal == with_prediction - 1


# ----------------------------------------------------------------------------- withdrawing a value
def test_an_explicit_null_withdraws_a_stored_conviction(db):
    """An expert who clears the conviction box must end up with no conviction stored.

    This pins the distinction `model_fields_set` carries and `is not None` cannot: by the time
    Pydantic is done, "the edit never mentioned this field" and "the edit deleted what was in it"
    are the same None. Resolve both as leave-it-alone and a cleared box saves, the page reloads,
    and the old percentage is back. The body below names the key and sets it null, which is the
    JSON the browser sends for a box the expert emptied.
    """
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "withdraw")
    prediction = _publish(db, match, expert, datetime.utcnow())
    assert prediction.confidence_score == Decimal("0.8")

    updated = ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               confidence_score=None),
        expert,
    )

    assert updated.confidence_score is None, (
        f"the withdrawn conviction came back as {updated.confidence_score!r}")


def test_an_omitted_conviction_leaves_the_stored_one_alone(db):
    """The other half of the rule, and the reason it cannot be "always write what is on the model".

    An edit that says nothing about a field is not a request to delete it. This body changes only
    the probabilities; the conviction the expert published earlier has to survive it untouched.
    """
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "omitted")
    prediction = _publish(db, match, expert, datetime.utcnow())

    updated = ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2),
        expert,
    )

    assert updated.confidence_score == Decimal("0.8")


def test_a_conviction_of_zero_can_be_stored_by_an_edit(db):
    """0 is a claim, so an edit that sets it must store it rather than skip it as falsy."""
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "editzero")
    prediction = _publish(db, match, expert, datetime.utcnow())

    updated = ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               confidence_score=0.0),
        expert,
    )

    assert updated.confidence_score == Decimal("0.0000")
    assert updated.confidence_score is not None


def test_the_withdrawal_rule_is_uniform_across_every_optional_field(db):
    """Conviction is not a special case: every optional value is withdrawn the same way.

    The fix would be worth very little if it applied to confidence_score alone - the next person
    to add an optional market would have no rule to follow, and the same bug would come back one
    field at a time. This edit clears a BTTS pair, both goal lines and the reasoning note in one
    body, and leaves the match-result conviction out of the body entirely.

    Both sides of each pair are named, because that is now the only way to withdraw one, and each
    market's conviction is named with it, because that is now the only way to take a market down;
    the tests below this one are the proof that half of either is refused.
    """
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "uniform")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.btts_yes_prob = Decimal("0.6000")
    prediction.btts_no_prob = Decimal("0.4000")
    prediction.total_goals_over_25_prob = Decimal("0.5500")
    prediction.total_goals_under_25_prob = Decimal("0.4500")
    prediction.total_goals_confidence = Decimal("0.7000")
    db.flush()

    updated = ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_yes_prob=None, btts_no_prob=None, btts_confidence=None,
                               total_goals_over_25_prob=None, total_goals_under_25_prob=None,
                               total_goals_over_35_prob=None, total_goals_under_35_prob=None,
                               total_goals_confidence=None,
                               reasoning=None),
        expert,
    )

    assert updated.btts_yes_prob is None and updated.btts_no_prob is None
    assert updated.total_goals_over_25_prob is None and updated.total_goals_under_25_prob is None
    assert updated.reasoning is None
    # The conviction went down with the market it was about.
    assert updated.total_goals_confidence is None
    # Never mentioned by the edit, and its market - the match result - is still published, so it
    # stands. That is the other half of the rule: an absent key changes nothing.
    assert updated.confidence_score == Decimal("0.8")


# ------------------------------------------------------------- a pair is withdrawn whole or not at all
#
# An explicit null CLEARS a stored value, and that rule applied one field at a time is what makes
# this one necessary: without it an expert could take down one side of a two-way market and leave
# the other standing. PUT {"btts_yes_prob": null} against a row holding 0.60/0.40 would commit yes
# NULL beside no 0.4000. Nothing downstream can describe that row honestly - match_brief reports
# the market at 40% and names the other side unpublished in the same sentence - and nothing below
# the request stops it: predictions.ck_predictions_btts_prob_sum evaluates to NULL when one side
# is NULL, and a Postgres CHECK only fails on FALSE, so the row would commit silently. The
# total-goals pairs have no sum constraint at all.
@pytest.mark.parametrize("cleared,other", [
    ("btts_yes_prob", "btts_no_prob"),
    ("btts_no_prob", "btts_yes_prob"),
    ("total_goals_over_25_prob", "total_goals_under_25_prob"),
    ("total_goals_under_25_prob", "total_goals_over_25_prob"),
    ("total_goals_over_35_prob", "total_goals_under_35_prob"),
    ("total_goals_under_35_prob", "total_goals_over_35_prob"),
])
def test_clearing_one_side_of_a_complementary_pair_is_refused(cleared, other):
    """The refusal, and it names the half that is missing rather than a constraint.

    No database is needed: the body can never be built, so the incoherent row cannot be reached
    from this endpoint however the service behaves afterwards.
    """
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               **{cleared: None})

    assert other in str(refused.value), (
        f"clearing {cleared} was refused without telling the caller {other} is the other half")


def test_revaluing_one_side_of_a_complementary_pair_is_refused():
    """The same rule catches the quieter version: one side moved, the other left where it was.

    0.70 sent on its own against a stored 0.60/0.40 would leave the pair summing to 1.10. The
    BTTS constraint would have caught that one - both sides are present, so the arithmetic is
    actually evaluated - but only as a 500-shaped IntegrityError named after the constraint, and
    the total-goals pairs have no such constraint to catch anything.
    """
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_yes_prob=0.7)

    assert "btts_no_prob" in str(refused.value)


def test_a_pair_cleared_on_one_side_and_kept_on_the_other_is_refused():
    """Both keys present, one null: the pair stated as though its halves were separate markets."""
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_yes_prob=None, btts_no_prob=0.4)

    assert "btts_yes_prob" in str(refused.value) and "btts_no_prob" in str(refused.value)


def test_a_pair_withdrawn_on_both_sides_still_goes_through(db):
    """The control. The rule must forbid the incoherent edit and permit the coherent one.

    A rule that also blocked withdrawing a market whole would leave an expert with no way to take
    one down, and an editor whose cleared fields cannot reach the database is the defect this
    whole group of tests exists to keep closed.
    """
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "pairwhole")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.btts_yes_prob = Decimal("0.6000")
    prediction.btts_no_prob = Decimal("0.4000")
    prediction.btts_confidence = Decimal("0.9000")
    db.flush()

    updated = ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_yes_prob=None, btts_no_prob=None, btts_confidence=None),
        expert,
    )

    assert updated.btts_yes_prob is None and updated.btts_no_prob is None
    assert updated.btts_confidence is None


# --------------------------------------------- a conviction does not outlive the market it is in
#
# The pair rule makes a market's two sides move as one and says nothing about the expert's stated
# conviction IN that market, which leaves one body able to do both at once: PUT {btts_yes_prob:
# null, btts_no_prob: null, btts_confidence: 0.9} withdraws the BTTS market whole and raises the
# conviction in it to 90% in the same request. Nothing downstream catches it - the service writes
# what the body says, and the table's CHECK on btts_confidence is a 0-1 range that 0.9 satisfies -
# so the row commits with a conviction attached to nothing. It has to be refused on the request.
@pytest.mark.parametrize("conviction,market", [
    ("btts_confidence", {"btts_yes_prob": None, "btts_no_prob": None}),
    ("total_goals_confidence", {"total_goals_over_25_prob": None, "total_goals_under_25_prob": None,
                                "total_goals_over_35_prob": None, "total_goals_under_35_prob": None}),
])
def test_withdrawing_a_market_while_raising_its_conviction_is_refused(conviction, market):
    """The refusal, for both markets that have a conviction of their own."""
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               **market, **{conviction: 0.9})

    assert conviction in str(refused.value)


@pytest.mark.parametrize("conviction,market", [
    ("btts_confidence", {"btts_yes_prob": None, "btts_no_prob": None}),
    ("total_goals_confidence", {"total_goals_over_25_prob": None, "total_goals_under_25_prob": None,
                                "total_goals_over_35_prob": None, "total_goals_under_35_prob": None}),
])
def test_withdrawing_a_market_without_mentioning_its_conviction_is_refused(conviction, market):
    """The quieter version, and the one an expert would actually hit.

    Leaving the conviction key out is not neutrality: the service reads an absent key as "the
    stored value stands", so a body that only takes the probabilities away leaves yesterday's
    conviction in a market that no longer has outcomes. Saying nothing has to be refused as
    firmly as saying 90%.
    """
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2, **market)

    assert conviction in str(refused.value)


def test_a_conviction_can_be_withdrawn_from_a_market_that_stays_published():
    """The control on the other side, and a thing experts legitimately do.

    The editor locks a published market's toggle but not its conviction box, so withdrawing the
    figure while the market stands is a supported edit. A rule that forbade it would be reading
    "a conviction needs a market" as "a market needs a conviction", which is not the same claim.
    """
    edit = ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                                  btts_yes_prob=0.6, btts_no_prob=0.4, btts_confidence=None)

    assert edit.btts_confidence is None
    assert "btts_confidence" in edit.model_fields_set


def test_a_conviction_in_an_unpublished_market_cannot_be_created_either():
    """A create writes the whole row, so the same shape is one POST away if only the edit is closed."""
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionCreate(match_id=str(uuid.uuid4()),
                               home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_confidence=0.9)

    assert "btts_confidence" in str(refused.value)


def test_one_goal_line_keeps_the_shared_conviction_alive():
    """total_goals_confidence covers both goal lines, so one published line is enough for it.

    Treating the 2.5 line's withdrawal as the end of the conviction would delete a figure the
    expert still stands behind on the 3.5 line.
    """
    edit = ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                                  total_goals_over_25_prob=None, total_goals_under_25_prob=None,
                                  total_goals_over_35_prob=0.3, total_goals_under_35_prob=0.7,
                                  total_goals_confidence=0.8)

    assert edit.total_goals_confidence == 0.8


def test_a_half_published_pair_cannot_be_created_either(db):
    """A create writes the same row, so it is held to the same rule.

    Closing only the edit path would have left the identical incoherent row one POST away.
    """
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionCreate(match_id=str(uuid.uuid4()),
                               home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_yes_prob=0.6)

    assert "btts_no_prob" in str(refused.value)


# ------------------------------------- the validator and the table mean the same thing by "sums to 1"
#
# ck_predictions_prob_sum is exact equality, and the request validators measure the same thing at
# the same scale. A strip of values the request accepts and the insert refuses is not leniency -
# it is a correctable mistake turned into a failed write, and the expert cannot be told which
# numbers to change: by the time the row reaches the table the reply can only say that the
# database refused it, because the endpoint cannot identify the constraint without parsing the
# driver's message and may not put that message in front of a caller.
#
# The request holds the tighter rule rather than the constraint holding a looser one,
# deliberately: all 250 rows stored sum to exactly 1, the reader renders each probability as a
# percentage without rescaling, and widening the CHECK would make 34% + 33% + 34% a storable
# prediction. Counted read-only against this installation on 2026-09-21.
def test_a_triple_the_table_refuses_is_refused_by_the_schema_first():
    """34 / 33 / 34: inside a 0.99-1.01 tolerance, outside ck_predictions_prob_sum."""
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionCreate(match_id=str(uuid.uuid4()),
                               home_win_prob=0.34, draw_prob=0.33, away_win_prob=0.34)

    assert "sum to exactly 1" in str(refused.value)
    # The numbers as the columns would hold them, so the expert can see where the 0.01 came from.
    assert "1.0100" in str(refused.value)

    with pytest.raises(pydantic.ValidationError):
        ExpertPredictionUpdate(home_win_prob=0.34, draw_prob=0.33, away_win_prob=0.34)


def test_the_table_agrees_with_the_schema_about_34_33_34(db):
    """The other half of the claim: the table refuses the triple the schema refuses.

    Without this the test above only says what the schema does. Storing the triple proves the two
    draw the line in the same place, which is the whole point of the rule.
    """
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "exactsum")
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id,
                            source=PredictionSource.EXPERT_MANUAL, created_by=expert.id,
                            priority_level=100, status=PredictionStatus.PUBLISHED,
                            home_win_prob=Decimal("0.34"), draw_prob=Decimal("0.33"),
                            away_win_prob=Decimal("0.34"))
    db.add(prediction)

    with pytest.raises(IntegrityError) as refused:
        db.flush()

    assert "ck_predictions_prob_sum" in str(refused.value)
    db.rollback()


def test_rounding_to_the_stored_scale_is_where_the_sum_is_judged(db):
    """Exactness is measured at NUMERIC(5, 4), because that is where the constraint measures it.

    Comparing the floats as sent would get both of these wrong in opposite directions.
    """
    # 0.1 + 0.2 + 0.7 is 1.0000000000000002 in binary floating point and exactly 1.0000 in the
    # columns. The table takes it, so the request must too.
    accepted = ExpertPredictionUpdate(home_win_prob=0.1, draw_prob=0.2, away_win_prob=0.7)
    assert accepted.away_win_prob == 0.7

    # 0.333333 three times is 0.999999 as a float - inside a 0.99-1.01 tolerance - and 0.9999 in
    # the columns, which the table refuses. It has to be refused here instead.
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionUpdate(home_win_prob=0.333333, draw_prob=0.333333, away_win_prob=0.333334)
    assert "0.9999" in str(refused.value)

    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "scale")
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id,
                            source=PredictionSource.EXPERT_MANUAL, created_by=expert.id,
                            priority_level=100, status=PredictionStatus.PUBLISHED,
                            home_win_prob=Decimal(str(accepted.home_win_prob)),
                            draw_prob=Decimal(str(accepted.draw_prob)),
                            away_win_prob=Decimal(str(accepted.away_win_prob)))
    db.add(prediction)
    db.flush()  # the table agrees: no CheckViolation

    assert prediction.home_win_prob == Decimal("0.1")


# ------------------------------------------- and the same scale decides a complementary pair
#
# ck_predictions_btts_prob_sum is BETWEEN 0.99 AND 1.01 over the two STORED values, so the pair
# rule on the request has to be measured there too. Adding the request's doubles instead opens a
# strip where the request says yes and the insert says no, and it opens at the fourth decimal,
# where nobody reading the two numbers would see it.
#
# The over/under pairs have no constraint of their own, so for them the request is the only place
# the arithmetic is checked. They are held to the same rule and measured the same way, because a
# rule that applies to one of three complementary markets is not a rule.
def test_a_pair_the_table_refuses_is_refused_by_the_schema_first(db):
    """0.98995 with 0.02005: exactly 1.01 as doubles, 1.0101 as the columns hold it."""
    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionCreate(match_id=str(uuid.uuid4()),
                               home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               btts_yes_prob=0.98995, btts_no_prob=0.02005)

    # The numbers as the columns would hold them, so the expert can see where the excess is.
    assert "0.9900" in str(refused.value) and "0.0201" in str(refused.value)
    assert "1.0101" in str(refused.value)

    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "pairscale")
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id,
                            source=PredictionSource.EXPERT_MANUAL, created_by=expert.id,
                            priority_level=100, status=PredictionStatus.PUBLISHED,
                            home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"),
                            btts_yes_prob=Decimal("0.98995"), btts_no_prob=Decimal("0.02005"))
    db.add(prediction)

    with pytest.raises(IntegrityError) as violated:
        db.flush()

    assert "ck_predictions_btts_prob_sum" in str(violated.value)
    db.rollback()


@pytest.mark.parametrize("first,second", [
    ("btts_yes_prob", "btts_no_prob"),
    ("total_goals_over_25_prob", "total_goals_under_25_prob"),
    ("total_goals_over_35_prob", "total_goals_under_35_prob"),
])
def test_every_complementary_pair_is_judged_at_the_stored_scale(first, second):
    """All three markets, one rule. Each conviction is sent too, so nothing else can refuse it."""
    body = {"home_win_prob": 0.5, "draw_prob": 0.3, "away_win_prob": 0.2,
            first: 0.98995, second: 0.02005}
    if first.startswith("btts"):
        body["btts_confidence"] = 0.7
    else:
        body["total_goals_confidence"] = 0.7

    with pytest.raises(pydantic.ValidationError) as refused:
        ExpertPredictionUpdate(**body)

    assert "1.0101" in str(refused.value), (
        f"{first} + {second} was judged on the floats, which sum to exactly 1.01")


def test_a_pair_the_table_accepts_is_not_refused_by_the_schema(db):
    """The other direction, which matters just as much: 0.6 and 0.41 store as 1.0100 and stand.

    A request rule stricter than the CHECK refuses rows the table would take. The two sides are
    measured at the same scale precisely so that neither can happen, and a test that only pinned
    the refusals would be satisfied by a validator that refused everything.
    """
    accepted = ExpertPredictionCreate(match_id=str(uuid.uuid4()),
                                      home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                                      btts_yes_prob=0.6, btts_no_prob=0.41)

    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "pairedge")
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id,
                            source=PredictionSource.EXPERT_MANUAL, created_by=expert.id,
                            priority_level=100, status=PredictionStatus.PUBLISHED,
                            home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"),
                            btts_yes_prob=Decimal(str(accepted.btts_yes_prob)),
                            btts_no_prob=Decimal(str(accepted.btts_no_prob)))
    db.add(prediction)
    db.flush()  # the table agrees: 0.6000 + 0.4100 is inside BETWEEN 0.99 AND 1.01

    assert prediction.btts_no_prob == Decimal("0.41")


def test_key_factors_are_removed_from_the_metadata_rather_than_stored_as_null(db):
    """Withdrawing key_factors has to delete the key: a stored null claims an empty set of factors."""
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "factors")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.prediction_metadata = {"key_factors": {"injuries": "two defenders out"},
                                      "origin": "keep me"}
    db.flush()

    updated = ExpertPredictionService(db).update_prediction(
        str(prediction.id),
        ExpertPredictionUpdate(home_win_prob=0.5, draw_prob=0.3, away_win_prob=0.2,
                               key_factors=None),
        expert,
    )
    db.refresh(updated)

    assert "key_factors" not in (updated.prediction_metadata or {})
    assert updated.prediction_metadata["origin"] == "keep me", "the rest of the metadata is not ours to drop"


# ----------------------------------------------------------------------------- zero on the public API
def test_the_published_list_serves_a_conviction_of_zero_as_zero(client, db):
    """`if prediction.confidence_score else None` turned a real 0% into "nobody said".

    Decimal("0.0") is falsy, so this endpoint reported a deliberate zero and an unsupplied
    conviction identically - the very distinction the nullable column was introduced to make.
    The sibling markets in the same dict were already going through `_optional_float`, which is
    how we know it was an oversight and not a decision.
    """
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "zerolist")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.confidence_score = Decimal("0.0000")
    db.flush()

    response = client.get(f"/api/v1/predictions/published?match_id={match.id}")

    assert response.status_code == 200, response.text
    row = next(r for r in response.json() if r["id"] == str(prediction.id))
    assert row["confidence_score"] == 0.0, (
        f"a claimed zero was served as {row['confidence_score']!r}")


def test_the_published_list_serves_an_unsupplied_conviction_as_null(client, db):
    """The control: the two cases must reach the browser as different values."""
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "nulllist")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.confidence_score = None
    db.flush()

    response = client.get(f"/api/v1/predictions/published?match_id={match.id}")

    assert response.status_code == 200, response.text
    row = next(r for r in response.json() if r["id"] == str(prediction.id))
    assert row["confidence_score"] is None


def test_the_by_match_endpoint_serves_a_conviction_of_zero_as_zero(client, db):
    """The same falsy test stood in the by-match endpoint, one dict away from the one above."""
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "zerobymatch")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.confidence_score = Decimal("0.0000")
    db.flush()

    response = client.get(f"/api/v1/predictions/published/by-match/{match.external_api_id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body is not None and body["id"] == str(prediction.id)
    assert body["confidence_score"] == 0.0


def test_the_by_match_endpoint_serves_an_unsupplied_conviction_as_null(client, db):
    expert, league = _expert(db), _league(db)
    match = _match(db, league, LATE_KICKOFF, "nullbymatch")
    prediction = _publish(db, match, expert, datetime.utcnow())
    prediction.confidence_score = None
    db.flush()

    response = client.get(f"/api/v1/predictions/published/by-match/{match.external_api_id}")

    assert response.status_code == 200, response.text
    assert response.json()["confidence_score"] is None
