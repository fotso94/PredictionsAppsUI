"""An expert's record is what they were standing behind at kickoff, and it survives them.

Everything here is about one abuse. Before this, deleting a prediction dropped it out of scoring
with no time limit at all: an expert could publish freely, wait for the result and remove whatever
went wrong, and the leaderboard would show only the winners. Superseding did the same thing more
quietly, and unpublishing did it while destroying the evidence outright (``published_at`` was set
to NULL, so nothing could show afterwards that the prediction had predated kickoff).

The rule these tests pin down: a prediction that was published before kickoff and still standing
when the match started is scored, whatever happens to it afterwards. Withdrawn before kickoff it
counts for nothing, because nobody was standing behind it. Losses are the interesting half - a fix
that only kept the wins would be worse than no fix.

The second half of the file covers how test data is told apart from a real record: an explicit
stored flag, set server-side under a configuration gate that is off by default, never a marker
typed into the reasoning text. The QA harness used to mark its rows by writing "[e2e-qa]" into
that text, which is free-form and user-controlled: the moment such a marker influenced scoring,
any expert could exclude their own losses by typing nine characters.

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
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    League, Match, MatchResult, MatchStatus, Prediction, PredictionOutcome, PredictionResult,
    PredictionSource, PredictionStatus, Team,
)
from app.models.users import AccountStatus, User, UserType
from app.schemas.predictions import ExpertPredictionCreate, ExpertPredictionOverride
from app.services import settlement as S
from app.services.expert_prediction import (
    ClassificationNotAllowed, ExpertPredictionService, ForeignExpertRecord, RecordClosed,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

#: Far from every other module's fixtures so nothing here collides, and far in the past so these
#: matches are unambiguously over.
KICKOFF = (datetime.now(timezone.utc) - timedelta(days=300)).replace(
    hour=15, minute=0, second=0, microsecond=0, tzinfo=None)

#: The literal the QA harness used to write into the reasoning field. It appears here only to prove
#: that the backend no longer cares what the reasoning says.
LEGACY_MARKER = "[e2e-qa]"


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
def _expert(db, name: str = "tipster") -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"{name}-{suffix}@test.local", username=f"{name}_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _match(db, kickoff: datetime = KICKOFF, status: MatchStatus = MatchStatus.FINISHED) -> Match:
    suffix = uuid.uuid4().hex[:8]
    league = League(id=uuid.uuid4(), name=f"History League {suffix}", display_name="History League",
                    country="England", is_active=True)
    home = Team(id=uuid.uuid4(), name=f"Home {suffix}", country="England")
    away = Team(id=uuid.uuid4(), name=f"Away {suffix}", country="England")
    db.add_all([league, home, away])
    db.flush()
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                  match_date=kickoff, status=status, external_api_id=f"ext-history-{suffix}",
                  external_api_source="sample", match_metadata={})
    db.add(match)
    db.flush()
    return match


def away_win(db, kickoff: datetime = KICKOFF) -> Match:
    """A finished match the home side lost 0-2.

    Every prediction below leans home, so scoring one of these fixtures produces a LOSS. That is
    deliberate: the abuse being closed is the removal of losses, so a test that only proved wins
    survive would prove nothing.
    """
    match = _match(db, kickoff)
    db.add(MatchResult(id=uuid.uuid4(), match_id=match.id, home_score=0, away_score=2, result="A",
                       result_metadata={"provider": "sample"}))
    db.flush()
    db.refresh(match)
    return match


def _prediction(db, match: Match, user: User, home=0.6, draw=0.25, away=0.15,
                published_at: Optional[datetime] = None, reasoning: str = "constructed for a test",
                source: PredictionSource = PredictionSource.EXPERT_MANUAL,
                status: PredictionStatus = PredictionStatus.PUBLISHED,
                is_test_data: Optional[bool] = None) -> Prediction:
    row = Prediction(
        id=uuid.uuid4(), match_id=match.id, source=source, created_by=user.id,
        home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(draw)),
        away_win_prob=Decimal(str(away)), confidence_score=Decimal("0.8"),
        status=status, priority_level=100, reasoning=reasoning, is_test_data=is_test_data,
        published_at=published_at or (match.match_date - timedelta(hours=6)))
    db.add(row)
    db.flush()
    return row


def settle(db):
    return S.SettlementService(db).settle_range(commit=False)


def score_of(db, prediction: Prediction) -> Optional[PredictionResult]:
    return (db.query(PredictionResult)
            .filter(PredictionResult.prediction_id == prediction.id).one_or_none())


def measured(db, user: User):
    """The performance payload's entry for one expert, or None when the source is absent."""
    payload = S.measurement(db, start=(KICKOFF - timedelta(days=1)).date(),
                            end=(KICKOFF + timedelta(days=1)).date())
    return next((s for s in payload["sources"] if s["source_id"] == str(user.id)), None)


# ------------------------------------------------- the record survives a post-kickoff withdrawal
def test_a_loss_deleted_after_kickoff_is_still_scored_and_still_reported(db):
    """The abuse, closed. This is the test the whole change exists for.

    An expert publishes, loses, and deletes the prediction once the result is in. The deletion is
    honoured for readers - it is their prediction to withdraw - but the measured record keeps it,
    loss and all.
    """
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)          # leans home; the home side lost 0-2
    prediction.deleted_at = match.match_date + timedelta(hours=3)
    db.flush()

    settle(db)

    row = score_of(db, prediction)
    assert row is not None, "a prediction deleted after kickoff must still be scored"
    assert row.outcome == PredictionOutcome.LOST
    assert row.actual_outcome == "away"
    assert float(row.probability_of_actual) == 0.15

    # and it reaches the published record, not just the table
    source = measured(db, user)
    assert source is not None and source["scored"] == 1
    market = next(m for m in source["markets"] if m["market"] == S.MARKET_MATCH_RESULT)
    assert market["scored"] == 1 and market["hits"] == 0, "the loss is counted as a loss"


def test_deleting_a_scored_loss_does_not_remove_it_from_the_published_record(db):
    """The realistic sequence: the scheduler scores it within minutes, then the expert deletes it.

    The score row was always left behind in prediction_results, but the performance read started
    from the candidate list, so a deleted prediction's score was simply never looked up again.
    """
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    settle(db)
    assert measured(db, user)["scored"] == 1

    prediction.deleted_at = datetime.utcnow()          # long after the match
    db.flush()

    source = measured(db, user)
    assert source is not None, "the expert must not vanish from the leaderboard by deleting a loss"
    assert source["scored"] == 1
    market = next(m for m in source["markets"] if m["market"] == S.MARKET_MATCH_RESULT)
    assert market["hits"] == 0


def test_a_prediction_withdrawn_before_kickoff_is_not_scored(db):
    """The other half of the rule. Nobody was standing behind this when the match started."""
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    prediction.deleted_at = match.match_date - timedelta(hours=1)
    db.flush()

    settle(db)

    assert score_of(db, prediction) is None
    assert measured(db, user) is None, "a withdrawn prediction is not a record of anything"


@pytest.mark.parametrize("offset,scored", [
    (timedelta(microseconds=-1), False),   # withdrawn a hair before kickoff: too late to count
    (timedelta(0), True),                  # withdrawn AT kickoff: too late to take back
    (timedelta(microseconds=1), True),
])
def test_the_withdrawal_boundary_is_the_kickoff_instant(db, offset, scored):
    """The exact instant belongs to the actor on both sides.

    Publishing AT kickoff is not prematch evidence (the existing ``published_at >= kickoff`` test),
    so withdrawing AT kickoff is symmetrically too late to take anything back. Getting this the
    other way round would leave a withdrawal timed exactly on the whistle able to delete a loss.
    """
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    prediction.deleted_at = match.match_date + offset
    db.flush()

    settle(db)

    assert (score_of(db, prediction) is not None) is scored


def test_the_boundary_compares_naive_utc_on_both_sides(db):
    """Both columns are naive UTC, and the comparison must stay a plain one.

    An aware datetime on either side would raise TypeError rather than mis-compare quietly, but
    only if nothing introduces a conversion; this pins the stored shape so a future writer that
    forgets to normalise is caught here rather than in a wrong score.
    """
    match = away_win(db)
    prediction = _prediction(db, match, _expert(db))
    prediction.deleted_at = match.match_date + timedelta(hours=2)
    db.flush()
    db.expire_all()

    stored = db.query(Prediction).filter(Prediction.id == prediction.id).one()
    kickoff = db.query(Match).filter(Match.id == match.id).one().match_date
    assert stored.published_at.tzinfo is None and stored.deleted_at.tzinfo is None
    assert kickoff.tzinfo is None
    assert S.stood_at_kickoff(stored, kickoff) is True


# ------------------------------------------------------------------------------- supersession
def test_a_supersession_after_kickoff_scores_the_version_that_stood_at_kickoff(db):
    """Superseding is the quietest way to erase a loss, so it gets the same rule as deleting.

    The replacement is published after kickoff, so it is not prematch evidence and can never be
    scored. Without this the fixture would contribute nothing at all: the original filtered out
    for being superseded, the replacement refused for being late.
    """
    match = away_win(db)
    user = _expert(db)
    original = _prediction(db, match, user, home=0.6, draw=0.25, away=0.15)
    replacement = _prediction(db, match, user, home=0.15, draw=0.25, away=0.6,
                              published_at=match.match_date + timedelta(hours=3))
    original.superseded_by = replacement.id
    db.flush()

    settle(db)

    row = score_of(db, original)
    assert row is not None, "the original is the only prematch version there is"
    assert row.outcome == PredictionOutcome.LOST
    assert float(row.probability_of_actual) == 0.15, "scored on what it said before kickoff"
    assert score_of(db, replacement) is None, "the later version is not prematch evidence"


def test_a_supersession_before_kickoff_hands_the_fixture_to_the_replacement(db):
    """An ordinary correction. The replacement is what readers had at kickoff, so it is scored."""
    match = away_win(db)
    user = _expert(db)
    original = _prediction(db, match, user, home=0.6, draw=0.25, away=0.15)
    replacement = _prediction(db, match, user, home=0.15, draw=0.25, away=0.6,
                              published_at=match.match_date - timedelta(hours=2))
    original.superseded_by = replacement.id
    db.flush()

    settle(db)

    assert score_of(db, original) is None
    row = score_of(db, replacement)
    assert row is not None and row.outcome == PredictionOutcome.WON


def test_an_expert_cannot_supersede_another_experts_record(db):
    """Overriding a model's prediction is the feature; overriding a colleague's is not."""
    match = _match(db, kickoff=datetime.utcnow() + timedelta(days=2), status=MatchStatus.SCHEDULED)
    author, intruder = _expert(db, "author"), _expert(db, "intruder")
    theirs = _prediction(db, match, author, published_at=datetime.utcnow())
    db.flush()

    with pytest.raises(ForeignExpertRecord):
        ExpertPredictionService(db).override_prediction(
            ExpertPredictionOverride(prediction_id=str(theirs.id), home_win_prob=0.2,
                                     draw_prob=0.2, away_win_prob=0.6, confidence_score=0.8,
                                     reasoning="I would rather this said something else"),
            intruder)

    db.expire_all()
    assert db.query(Prediction).filter(Prediction.id == theirs.id).one().superseded_by is None


def test_a_prediction_cannot_be_superseded_once_the_match_has_kicked_off(db):
    """After kickoff the record is closed: the original keeps standing for what it said."""
    match = away_win(db)
    user = _expert(db)
    mine = _prediction(db, match, user, source=PredictionSource.API_FOOTBALL_BASELINE)
    db.flush()

    with pytest.raises(RecordClosed):
        ExpertPredictionService(db).override_prediction(
            ExpertPredictionOverride(prediction_id=str(mine.id), home_win_prob=0.15,
                                     draw_prob=0.25, away_win_prob=0.6, confidence_score=0.8,
                                     reasoning="now that I have seen the result"),
            user)


# --------------------------------------------------------------------------- unpublish/archive
def test_unpublishing_after_kickoff_hides_the_prediction_but_keeps_the_score(db):
    """Archiving used to clear published_at, destroying the proof that it predated kickoff."""
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    published_at = prediction.published_at

    ExpertPredictionService(db).toggle_publish_status(str(prediction.id), user)
    db.flush()

    assert prediction.status == PredictionStatus.ARCHIVED
    assert prediction.published_at == published_at, "the publication time is a historical fact"
    assert prediction.unpublished_at is not None

    settle(db)
    row = score_of(db, prediction)
    assert row is not None and row.outcome == PredictionOutcome.LOST


def test_an_unpublish_republish_round_trip_does_not_restamp_the_publication_time(db):
    """The round trip used to make a prediction permanently unscoreable."""
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    published_at = prediction.published_at
    service = ExpertPredictionService(db)

    service.toggle_publish_status(str(prediction.id), user)
    service.toggle_publish_status(str(prediction.id), user)
    db.flush()

    assert prediction.status == PredictionStatus.PUBLISHED
    assert prediction.published_at == published_at
    assert prediction.unpublished_at is None

    settle(db)
    assert score_of(db, prediction) is not None


def test_republishing_after_the_result_does_not_resurrect_a_prematch_withdrawal(db):
    """The mirror abuse, and the profitable direction: withdraw in advance, restore the winners.

    A prediction taken off the public lists before kickoff was not standing when the ball was
    kicked, and no later toggle can change that. Clearing ``unpublished_at`` on a republish would
    have let an expert park every prediction before kickoff, watch the results and put back only
    the ones that came in - a record built out of hindsight, which is worse than the deletions
    this change closes because it invents wins rather than hiding losses.
    """
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user, home=0.15, draw=0.25, away=0.6)   # would WIN
    prediction.status = PredictionStatus.ARCHIVED
    prediction.unpublished_at = match.match_date - timedelta(hours=2)
    db.flush()

    settle(db)
    assert score_of(db, prediction) is None, "not standing at kickoff, so nothing to measure"

    ExpertPredictionService(db).toggle_publish_status(str(prediction.id), user)
    db.flush()

    assert prediction.status == PredictionStatus.PUBLISHED, "readers get it back; that is allowed"
    assert prediction.unpublished_at is not None, "the prematch withdrawal is a closed fact"
    assert prediction.unpublished_at < match.match_date

    settle(db)
    assert score_of(db, prediction) is None
    assert measured(db, user) is None, "a win nobody could read at kickoff is not a record"


def test_a_second_withdrawal_after_kickoff_cannot_overwrite_the_prematch_one(db):
    """The same erasure by a longer route: republish, then unpublish again, after the result.

    Restamping ``unpublished_at`` with a post-kickoff time would make the row look as though it
    had stood at kickoff and only come down afterwards.
    """
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user, home=0.15, draw=0.25, away=0.6)   # would WIN
    prediction.status = PredictionStatus.ARCHIVED
    withdrawn_at = match.match_date - timedelta(hours=2)
    prediction.unpublished_at = withdrawn_at
    db.flush()

    service = ExpertPredictionService(db)
    service.toggle_publish_status(str(prediction.id), user)   # back on the lists
    service.toggle_publish_status(str(prediction.id), user)   # and off again
    db.flush()

    assert prediction.unpublished_at == withdrawn_at

    settle(db)
    assert score_of(db, prediction) is None
    assert measured(db, user) is None


def test_a_withdrawal_after_kickoff_is_not_frozen_and_a_republish_clears_it(db):
    """The control. Only a PREMATCH withdrawal is a closed fact; a later one says nothing.

    A prediction that stood at kickoff stays scored throughout, so nothing here depends on the
    column - but the state must still be honest about whether the row is currently off the lists.
    """
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    service = ExpertPredictionService(db)

    service.toggle_publish_status(str(prediction.id), user)   # unpublished AFTER kickoff
    db.flush()
    assert prediction.unpublished_at is not None
    assert prediction.unpublished_at > match.match_date

    service.toggle_publish_status(str(prediction.id), user)   # and back on
    db.flush()
    assert prediction.unpublished_at is None, "a post-kickoff withdrawal carries no prematch fact"

    settle(db)
    row = score_of(db, prediction)
    assert row is not None and row.outcome == PredictionOutcome.LOST


def test_a_withdrawal_before_kickoff_can_still_be_undone_while_the_match_is_ahead(db):
    """The freeze must not reach back into a match that has not started.

    An expert who takes a prediction down and puts it back the same afternoon is doing ordinary
    editing, and the record that results is the one readers had at kickoff.
    """
    match = _match(db, kickoff=datetime.utcnow() + timedelta(days=2),
                   status=MatchStatus.SCHEDULED)
    user = _expert(db)
    prediction = _prediction(db, match, user, published_at=datetime.utcnow())
    service = ExpertPredictionService(db)

    service.toggle_publish_status(str(prediction.id), user)
    db.flush()
    assert prediction.unpublished_at is not None

    service.toggle_publish_status(str(prediction.id), user)
    db.flush()
    assert prediction.unpublished_at is None, "nothing is frozen before kickoff"
    assert S.stood_at_kickoff(prediction, match.match_date) is True


def test_a_prediction_unpublished_before_kickoff_is_not_scored(db):
    """Taken off the public lists before the match: nobody was reading it at kickoff."""
    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user, status=PredictionStatus.ARCHIVED)
    prediction.unpublished_at = match.match_date - timedelta(hours=2)
    db.flush()

    settle(db)
    assert score_of(db, prediction) is None


def test_a_draft_that_was_never_published_is_not_scored(db):
    """A row still awaiting review was never shown to anyone, so there is nothing to measure."""
    match = away_win(db)
    user = _expert(db)
    draft = _prediction(db, match, user, status=PredictionStatus.PENDING)
    db.flush()

    settle(db)
    assert score_of(db, draft) is None


# ------------------------------------------------------------------- explicit test classification
def test_a_record_classified_as_test_data_is_left_out_of_the_measured_record(db):
    match = away_win(db)
    user = _expert(db)
    flagged = _prediction(db, match, user, is_test_data=True)
    db.flush()

    settle(db)

    assert score_of(db, flagged) is None
    assert measured(db, user) is None


def test_an_identical_record_that_is_not_classified_is_measured(db):
    """The control for the test above: same rows, same author, one flag apart."""
    match = away_win(db)
    user = _expert(db)
    ordinary = _prediction(db, match, user, is_test_data=None)
    db.flush()

    settle(db)

    assert score_of(db, ordinary) is not None
    assert measured(db, user)["scored"] == 1


def test_the_exclusion_does_not_depend_on_the_reasoning_text(db):
    """A genuine expert who happens to type the old QA marker is still measured.

    This is the reason the classification is a column. While the marker was the rule, anyone could
    keep a loss off their record by typing nine characters into a free-text field.
    """
    match = away_win(db)
    user = _expert(db)
    honest = _prediction(db, match, user,
                         reasoning=f"{LEGACY_MARKER} I really do think the home side take this")
    db.flush()

    settle(db)

    row = score_of(db, honest)
    assert row is not None and row.outcome == PredictionOutcome.LOST
    assert measured(db, user)["scored"] == 1


def test_the_declared_default_for_the_classification_gate_is_off():
    """The invariant is the DECLARED default, not whatever this machine's .env happens to say.

    Asserting the live setting made this test pass or fail depending on the developer's own .env:
    a machine running the end-to-end suite turns the gate on, and the test that exists to prove the
    gate is off by default then failed. What must never drift is the default compiled into
    Settings, which is what every deployment gets when it says nothing.
    """
    from app.core.config import Settings
    assert Settings.model_fields["ALLOW_TEST_DATA_CLASSIFICATION"].default is False


def test_classification_is_refused_where_the_installation_does_not_allow_it(db, monkeypatch):
    """With the gate off, no user can classify their own record - whatever they ask for."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALLOW_TEST_DATA_CLASSIFICATION", False)

    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    db.flush()

    with pytest.raises(ClassificationNotAllowed):
        ExpertPredictionService(db).classify_as_test_data(str(prediction.id), user)

    db.expire_all()
    assert db.query(Prediction).filter(Prediction.id == prediction.id).one().is_test_data is None


def test_a_create_request_asking_for_classification_is_ignored_when_the_gate_is_off(db, monkeypatch):
    """Asking is not enough: the request is stored unclassified and the record stays measurable."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALLOW_TEST_DATA_CLASSIFICATION", False)
    from app.services.expert_prediction import test_data_classification
    assert test_data_classification(True) is None
    assert test_data_classification(False) is None
    assert test_data_classification(None) is None


def test_with_the_gate_on_the_harness_can_classify_its_own_record(db, monkeypatch):
    """The supported mechanism, exercised the way the end-to-end suite uses it."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALLOW_TEST_DATA_CLASSIFICATION", True)

    match = away_win(db)
    user = _expert(db)
    prediction = _prediction(db, match, user)
    db.flush()

    ExpertPredictionService(db).classify_as_test_data(str(prediction.id), user)
    db.flush()
    assert prediction.is_test_data is True

    settle(db)
    assert score_of(db, prediction) is None
    assert measured(db, user) is None


def test_the_gate_does_not_let_an_expert_classify_somebody_elses_record(db, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALLOW_TEST_DATA_CLASSIFICATION", True)

    match = away_win(db)
    author, intruder = _expert(db, "author"), _expert(db, "intruder")
    theirs = _prediction(db, match, author)
    db.flush()

    with pytest.raises(ValueError):
        ExpertPredictionService(db).classify_as_test_data(str(theirs.id), intruder)
    assert theirs.is_test_data is None


def test_a_created_prediction_carries_the_classification_when_the_gate_is_on(db, monkeypatch):
    """End to end through the create path, since that is how the harness marks its own rows."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALLOW_TEST_DATA_CLASSIFICATION", True)

    match = _match(db, kickoff=datetime.utcnow() + timedelta(days=2), status=MatchStatus.SCHEDULED)
    user = _expert(db)
    created = ExpertPredictionService(db).create_manual_prediction(
        ExpertPredictionCreate(match_id=str(match.id), home_win_prob=0.55, draw_prob=0.25,
                               away_win_prob=0.20, confidence_score=0.7,
                               reasoning="a record the suite created", is_test_data=True),
        user)
    assert created.is_test_data is True


# ------------------------------------------------------------------------ the placeholder delete
def test_a_placeholder_match_carrying_predictions_is_not_deleted(db):
    """Match.predictions cascades delete-orphan, so deleting the match deletes the record.

    It takes other experts' predictions, their scores and their preserved earlier versions with
    it, none of it soft-deleted and none of it recoverable. Latent today - nothing carries the
    "(TBD)" name - but it is the largest single erasure reachable from an expert action.
    """
    match = away_win(db)
    prediction = _prediction(db, match, _expert(db))
    db.flush()

    deleted = ExpertPredictionService(db)._delete_placeholder_match(match.id)

    assert deleted is False
    assert db.query(Match).filter(Match.id == match.id).count() == 1
    assert db.query(Prediction).filter(Prediction.id == prediction.id).count() == 1


# ------------------------------------------- the report states only what the record actually says
def test_a_row_with_no_publication_time_is_not_reported_as_published_late(db):
    """A missing publication time and a late one are different facts, and the report must say so.

    ``candidate_predictions`` stopped filtering on status, so a PUBLISHED row whose
    ``published_at`` is NULL now reaches the unscored branch of the performance read. It used to be
    told the reader as "published at or after kickoff", which the record does not support: nothing
    here says when the row went out, only that we do not know.
    """
    match = away_win(db)
    user = _expert(db)
    undated = _prediction(db, match, user)
    undated.published_at = None
    db.flush()

    settle(db)
    assert score_of(db, undated) is None

    source = measured(db, user)
    assert source["scored"] == 0 and source["not_scored"] == 1
    reason = source["not_scored_reasons"][0]["reason"]
    assert "after kickoff" not in reason, reason
    assert reason == S.NO_PUBLICATION_TIME_REASON


def test_a_row_published_after_kickoff_still_says_it_was_published_after_kickoff(db):
    """The control for the test above: the reason that was always right stays right."""
    match = away_win(db)
    user = _expert(db)
    late = _prediction(db, match, user, published_at=match.match_date + timedelta(minutes=5))
    db.flush()

    settle(db)
    assert score_of(db, late) is None

    source = measured(db, user)
    assert source["scored"] == 0 and source["not_scored"] == 1
    assert source["not_scored_reasons"][0]["reason"] == S.NOT_PREMATCH_EVIDENCE_REASON


def test_the_refusal_reason_answers_for_a_withdrawn_row_too(db):
    """The helper is total, so no future caller can be handed the wrong half of the story.

    ``candidate_predictions`` drops withdrawn and never-published rows before the performance read
    sees them, so this case does not arise there today. It is pinned anyway: the defect being
    closed is a reason that was correct for the rows that reached it and wrong for the rows that
    started reaching it later.
    """
    match = away_win(db)
    user = _expert(db)
    withdrawn = _prediction(db, match, user)
    withdrawn.unpublished_at = match.match_date - timedelta(hours=1)
    db.flush()

    assert S.not_prematch_reason(withdrawn, match.match_date) == S.NOT_STANDING_REASON


# ---------------------------------------------- a conviction nobody supplied is not a zero
#
# predictions.confidence_score was NOT NULL, and create, override and the override's audit row all
# coerced a missing conviction to Decimal("0.0"). A blank field and an expert's deliberate "I rate
# this at nothing" therefore became the same stored number, and every reader printed both as 0%.
# The column is nullable now and the coercions are gone, so the two are different records again.
#
# What these tests do NOT do is reinterpret the rows written before the fix. Those zeros are
# genuinely ambiguous and nothing stored can tell a coerced blank from a claimed zero; turning them
# into NULL would invent exactly the information the coercion destroyed. They stay as they are.

def _scheduled(db) -> Match:
    return _match(db, kickoff=datetime.utcnow() + timedelta(days=2), status=MatchStatus.SCHEDULED)


def test_a_prediction_created_with_no_conviction_stores_null(db):
    """The defect, closed at the point of writing. Was Decimal("0.0000")."""
    match, user = _scheduled(db), _expert(db)
    created = ExpertPredictionService(db).create_manual_prediction(
        ExpertPredictionCreate(match_id=str(match.id), home_win_prob=0.55, draw_prob=0.25,
                               away_win_prob=0.20, reasoning="no conviction offered"),
        user)

    db.expire_all()
    stored = db.query(Prediction).filter(Prediction.id == created.id).one()
    assert stored.confidence_score is None, (
        "a conviction the author never supplied was stored as a number")


def test_a_prediction_created_with_no_conviction_serialises_as_null(db):
    """And it reaches the reader as null, not as 0.0 - the enrichment used to call float() flat."""
    match, user = _scheduled(db), _expert(db)
    service = ExpertPredictionService(db)
    created = service.create_manual_prediction(
        ExpertPredictionCreate(match_id=str(match.id), home_win_prob=0.55, draw_prob=0.25,
                               away_win_prob=0.20, reasoning="no conviction offered"),
        user)

    payload = service.enrich_prediction_with_details(created)
    assert payload["confidence_score"] is None

    # And the response model can carry it. Declaring this field a required float was the last link
    # in the chain: the column and the service could both say "not given" and the API still could
    # not transmit it.
    from app.schemas.predictions import ExpertPredictionResponse
    assert ExpertPredictionResponse(**payload).confidence_score is None


def test_a_prediction_created_with_an_explicit_zero_stores_zero(db):
    """The other half, and the reason none of this may be written with truthiness.

    An expert who types 0 has claimed something. If this test and the two above ever agree, the
    fix has been undone by somebody reaching for `if data.confidence_score`.
    """
    match, user = _scheduled(db), _expert(db)
    service = ExpertPredictionService(db)
    created = service.create_manual_prediction(
        ExpertPredictionCreate(match_id=str(match.id), home_win_prob=0.55, draw_prob=0.25,
                               away_win_prob=0.20, confidence_score=0.0,
                               reasoning="I stand behind this one not at all"),
        user)

    db.expire_all()
    stored = db.query(Prediction).filter(Prediction.id == created.id).one()
    assert stored.confidence_score is not None, "a claimed zero was thrown away as an absence"
    assert float(stored.confidence_score) == 0.0
    assert service.enrich_prediction_with_details(stored)["confidence_score"] == 0.0


def test_an_override_with_no_conviction_does_not_silently_become_zero(db):
    """Three rows are written by an override and all three used to say zero.

    The replacement prediction, the audit row's ``new_confidence``, and the ``confidence_adjustment``
    computed from it - which reported a swing away from the original's conviction that the expert
    never made.
    """
    from app.models.predictions import PredictionOverride

    match, user = _scheduled(db), _expert(db)
    original = _prediction(db, match, user, source=PredictionSource.API_FOOTBALL_BASELINE,
                           published_at=datetime.utcnow())
    db.flush()
    assert float(original.confidence_score) == 0.8  # the original DID claim one

    replacement = ExpertPredictionService(db).override_prediction(
        ExpertPredictionOverride(prediction_id=str(original.id), home_win_prob=0.15,
                                 draw_prob=0.25, away_win_prob=0.60,
                                 reasoning="the away side has recovered its first choice keeper"),
        user)

    db.expire_all()
    stored = db.query(Prediction).filter(Prediction.id == replacement.id).one()
    assert stored.confidence_score is None

    audit = db.query(PredictionOverride).filter(
        PredictionOverride.prediction_id == replacement.id).one()
    assert audit.new_confidence is None, "the audit trail claimed a conviction of zero"
    assert audit.original_confidence is not None and float(audit.original_confidence) == 0.8
    assert audit.confidence_adjustment is None, (
        "a conviction change was computed against a conviction that was never given")


def test_an_override_that_does_claim_a_conviction_still_records_the_adjustment(db):
    """The control: with both sides present the audit row still measures the change."""
    from app.models.predictions import PredictionOverride

    match, user = _scheduled(db), _expert(db)
    original = _prediction(db, match, user, source=PredictionSource.API_FOOTBALL_BASELINE,
                           published_at=datetime.utcnow())
    db.flush()

    replacement = ExpertPredictionService(db).override_prediction(
        ExpertPredictionOverride(prediction_id=str(original.id), home_win_prob=0.15,
                                 draw_prob=0.25, away_win_prob=0.60, confidence_score=0.5,
                                 reasoning="the away side has recovered its first choice keeper"),
        user)

    db.expire_all()
    audit = db.query(PredictionOverride).filter(
        PredictionOverride.prediction_id == replacement.id).one()
    assert float(audit.new_confidence) == 0.5
    assert float(audit.confidence_adjustment) == -0.3


def test_a_revision_records_a_withheld_conviction_as_null_not_as_zero(db):
    """The preserved earlier version has to say the same thing the live row says.

    ``prediction_snapshot`` feeds both sides of every revision, so a conviction rendered as 0.0
    here would put a figure nobody claimed into the permanent record of what was published.
    """
    match, user = _scheduled(db), _expert(db)
    created = ExpertPredictionService(db).create_manual_prediction(
        ExpertPredictionCreate(match_id=str(match.id), home_win_prob=0.55, draw_prob=0.25,
                               away_win_prob=0.20, reasoning="no conviction offered"),
        user)
    db.flush()

    from app.services.expert_prediction import prediction_snapshot
    assert prediction_snapshot(created)["confidence_score"] is None
