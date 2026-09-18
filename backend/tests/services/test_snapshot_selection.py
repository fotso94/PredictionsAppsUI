"""Which forecast snapshot is "the" forecast, when several of them claim the same moment.

A match usually carries more than one prematch snapshot with the SAME ``first_fetched_at``. That is
not corruption: the migration that backfilled this table stamped its one row per forecast with the
record's retrieval time, and ``scripts/repair_forecasts.py`` appends its corrected re-reading of the
same payload under the same retrieval time on purpose, because a repair retrieves nothing from the
provider and must not move the clock forward.

While the ordering was ``first_fetched_at`` alone, "the last row" was whatever the database felt
like returning last, and that answer moves - an UPDATE rewrites a tuple elsewhere in the heap, so a
later scan sees a different order. Settlement scored one twin and the performance read then looked
up the other, found no score against it and reported it as still pending: four scored forecasts
surfaced as "scored 2, pending 2".

Everything here is constructed, and every snapshot in it shares a retrieval time with its twins, so
these tests fail against any ordering that is not total.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import (
    Match, MatchResult, MatchStatus, Prediction, PredictionSource, PredictionStatus, Team,
)
from app.models.provider_data import ProviderForecastResult, ProviderForecastSnapshot
from app.models.users import AccountStatus, User, UserType
from app.services import settlement as S
from app.services.forecast_service import choose_snapshots, order_snapshots
from app.services.match_registry import MatchRegistry

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

# Well in the past and away from the other modules' fixtures, so nothing here collides.
KICKOFF = (datetime.now(timezone.utc) - timedelta(days=210)).replace(
    hour=15, minute=0, second=0, microsecond=0, tzinfo=None)
WINDOW = (KICKOFF - timedelta(days=1), KICKOFF + timedelta(days=1))

#: Every twin in a group carries this one retrieval time. The whole point of the module.
RETRIEVED = KICKOFF - timedelta(hours=3)


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
def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:6]}", country="England")
    db.add(team)
    db.flush()
    return team


def played(db, home: int, away: int) -> Match:
    """A finished match with a stored regulation-time score."""
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=_team(db, "Home").id,
                  away_team_id=_team(db, "Away").id, match_date=KICKOFF, status=MatchStatus.FINISHED,
                  external_api_id=f"ext-tie-{uuid.uuid4().hex[:10]}", external_api_source="sample",
                  match_metadata={})
    db.add(match)
    db.flush()
    db.add(MatchResult(id=uuid.uuid4(), match_id=match.id, home_score=home, away_score=away,
                       result="H" if home > away else "A" if away > home else "D",
                       result_metadata={"provider": "sample"}))
    db.flush()
    db.refresh(match)
    return match


def _provider_name() -> str:
    """A source name of this test's own, so a window read cannot pick up anybody else's rows."""
    return f"twin-{uuid.uuid4().hex[:8]}"


def _snapshot(db, match: Match, provider: str, written_at: datetime, home: float,
              retrieved: Optional[datetime] = None,
              before_kickoff: Optional[bool] = True) -> ProviderForecastSnapshot:
    """One snapshot, with its write time (``created_at``) and retrieval time stated explicitly.

    ``home`` doubles as the row's fingerprint: the score that comes out names the twin it was
    computed from, so "the right one was scored" is checked on the numbers, not on an id alone.
    """
    captured = retrieved if retrieved is not None else RETRIEVED
    row = ProviderForecastSnapshot(
        id=uuid.uuid4(), match_id=match.id, provider=provider,
        external_event_id=f"evt-{uuid.uuid4().hex[:8]}", match_confidence="exact",
        matched_by="provider_id", created_at=written_at,
        home_win_prob=Decimal(str(home)), draw_prob=Decimal(str(round(1 - home - 0.1, 4))),
        away_win_prob=Decimal("0.1"),
        first_fetched_at=captured, last_fetched_at=captured,
        kickoff_at_capture=match.match_date, captured_before_kickoff=before_kickoff)
    db.add(row)
    db.flush()
    return row


def twins(db, match: Match, provider: str, homes=(0.50, 0.60, 0.70)) -> List[ProviderForecastSnapshot]:
    """Snapshots sharing one retrieval time, written newest-first so insert order is not the answer.

    The rows go in back to front on purpose. A reader that just takes what the database hands back
    last will take the row written FIRST, which is the stale one; the corrected re-reading is the
    row written LAST, and it is the one every caller has to agree on.
    """
    written = [KICKOFF - timedelta(hours=2) + timedelta(minutes=10 * index)
               for index in range(len(homes))]
    rows = [_snapshot(db, match, provider, written[index], homes[index])
            for index in reversed(range(len(homes)))]
    rows.reverse()                      # oldest write first, matching `homes`
    return rows


def chosen_snapshot(db, match: Match, provider: str) -> ProviderForecastSnapshot:
    return S.prematch_snapshots(db, [match.id])[(match.id, provider)]


def source_counts(db, provider: str):
    """What /performance/sources publishes for one source, over this module's window."""
    measured = S.measure_sources(db, *WINDOW)
    source = next(s for s in measured if s["source_id"] == provider)
    return {key: source[key] for key in ("eligible", "scored", "pending", "void", "not_scored")}


# ------------------------------------------------- the pick is total, and it is the same every time
def test_the_chosen_snapshot_is_the_last_one_written_for_that_retrieval(db):
    """Not merely a consistent arbitrary row: the corrected re-reading, by name."""
    match = played(db, 2, 0)
    provider = _provider_name()
    stale, middle, corrected = twins(db, match, provider)

    picked = chosen_snapshot(db, match, provider)
    assert picked.id == corrected.id
    assert picked.id not in (stale.id, middle.id)
    assert float(picked.home_win_prob) == 0.70
    # all three describe one retrieval, which is why first_fetched_at cannot settle it alone
    assert stale.first_fetched_at == middle.first_fetched_at == corrected.first_fetched_at


def test_the_same_row_comes_back_however_often_it_is_asked_and_however_the_rows_move(db):
    """An UPDATE rewrites a tuple elsewhere in the heap - the physical order is not the answer."""
    match = played(db, 2, 0)
    provider = _provider_name()
    stale, middle, corrected = twins(db, match, provider)

    seen = {chosen_snapshot(db, match, provider).id for _ in range(25)}

    # a resync that sees unchanged content moves last_fetched_at: a real write, and the one that
    # shuffled the physical order in production
    for row in (stale, middle, corrected, stale):
        db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.id == row.id).update(
            {"last_fetched_at": RETRIEVED + timedelta(minutes=5)})
        db.flush()
        db.expire_all()
        seen.add(chosen_snapshot(db, match, provider).id)

    assert seen == {corrected.id}


def test_a_later_retrieval_still_outranks_a_later_write(db):
    """The tiebreak breaks ties only. first_fetched_at remains the primary key of the decision."""
    match = played(db, 2, 0)
    provider = _provider_name()
    # written last, but retrieved earlier: it is not the provider's final prematch word
    _snapshot(db, match, provider, written_at=KICKOFF - timedelta(minutes=5), home=0.50,
              retrieved=RETRIEVED - timedelta(hours=1))
    latest_retrieval = _snapshot(db, match, provider, written_at=KICKOFF - timedelta(hours=2),
                                 home=0.70, retrieved=RETRIEVED)

    assert chosen_snapshot(db, match, provider).id == latest_retrieval.id


def test_the_ordering_is_total_so_no_two_rows_can_tie(db):
    """created_at can repeat to the microsecond; the row id is what closes the order."""
    match = played(db, 2, 0)
    provider = _provider_name()
    written = KICKOFF - timedelta(hours=2)
    rows = [_snapshot(db, match, provider, written_at=written, home=home)
            for home in (0.50, 0.60, 0.70)]
    assert len({row.created_at for row in rows}) == 1        # a genuine tie on both timestamps

    expected = max(rows, key=lambda row: row.id)             # the documented last resort
    assert {chosen_snapshot(db, match, provider).id for _ in range(25)} == {expected.id}


def test_every_reader_of_the_history_ends_on_the_chosen_row(db):
    """The forecast history a reader scrolls and the row settlement scores are the same row."""
    match = played(db, 2, 0)
    provider = _provider_name()
    twins(db, match, provider)

    history = order_snapshots(
        db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.match_id == match.id)).all()
    assert history[-1].id == chosen_snapshot(db, match, provider).id
    # and the resync's "what is the newest snapshot?" question lands there too
    newest = choose_snapshots(
        db.query(ProviderForecastSnapshot)
        .filter(ProviderForecastSnapshot.match_id == match.id,
                ProviderForecastSnapshot.provider == provider))[(match.id, provider)]
    assert newest.id == history[-1].id


# ------------------------------------------------------- scoring and reporting cannot disagree
def test_scoring_then_reporting_counts_every_scored_forecast(db):
    """The production shape: four finished matches, twinned snapshots, one source.

    Between the scoring and the read the stale twins are touched, the way a resync touches a
    snapshot whose content has not changed. That write is what moved the rows in the heap and made
    the two paths disagree; here the answer has to survive it.
    """
    provider = _provider_name()
    matches = [played(db, 2, 0), played(db, 1, 1), played(db, 0, 3), played(db, 3, 1)]
    stale = []
    for index, match in enumerate(matches):
        group = twins(db, match, provider, homes=(0.50, 0.60, 0.70) if index % 2 else (0.55, 0.75))
        stale.extend(group[:-1])

    S.SettlementService(db).settle_range(*WINDOW, commit=False)

    for row in stale:                    # one at a time, so the rewritten rows land in this order
        db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.id == row.id).update(
            {"last_fetched_at": RETRIEVED + timedelta(minutes=5)}, synchronize_session=False)
        db.flush()
    db.expire_all()

    assert source_counts(db, provider) == {"eligible": 4, "scored": 4, "pending": 0,
                                           "void": 0, "not_scored": 0}
    for match in matches:
        picked = chosen_snapshot(db, match, provider)
        stored = db.query(ProviderForecastResult).filter(
            ProviderForecastResult.match_id == match.id).one()
        assert stored.snapshot_id == picked.id
        assert stored.snapshot_captured_at == picked.first_fetched_at
        # the score is the corrected re-reading's numbers, not the stale twin's
        published = {"H": picked.home_win_prob, "D": picked.draw_prob,
                     "A": picked.away_win_prob}[match.result.result]
        assert float(stored.probability_of_actual) == pytest.approx(float(published))


def test_the_scored_row_is_the_row_the_performance_read_looks_up(db):
    """The exact split that produced "scored 2, pending 2": one twin scored, the other reported."""
    match = played(db, 2, 0)
    provider = _provider_name()
    _, _, corrected = twins(db, match, provider)
    S.SettlementService(db).settle_range(*WINDOW, commit=False)

    stored = db.query(ProviderForecastResult).one()
    assert stored.snapshot_id == corrected.id
    assert source_counts(db, provider)["scored"] == 1

    # and a score already attached to the chosen row is left exactly as it is on a re-run
    settled_at, rules = stored.settled_at, stored.rules_version
    report = S.SettlementService(db).settle_range(*WINDOW, commit=False)
    db.refresh(stored)
    assert report["provider_forecasts"]["settled"] == 0
    assert db.query(ProviderForecastResult).count() == 1
    assert (stored.settled_at, stored.rules_version) == (settled_at, rules)


def test_a_twin_captured_after_kickoff_is_not_promoted_by_the_tiebreak(db):
    """The tiebreak orders prematch evidence; it never lets post-kickoff evidence in."""
    match = played(db, 2, 0)
    provider = _provider_name()
    prematch = _snapshot(db, match, provider, written_at=KICKOFF - timedelta(hours=2), home=0.70)
    _snapshot(db, match, provider, written_at=KICKOFF + timedelta(hours=3), home=0.95,
              retrieved=KICKOFF + timedelta(hours=1), before_kickoff=False)
    _snapshot(db, match, provider, written_at=KICKOFF + timedelta(hours=4), home=0.99,
              retrieved=RETRIEVED, before_kickoff=None)

    assert chosen_snapshot(db, match, provider).id == prematch.id
    S.SettlementService(db).settle_range(*WINDOW, commit=False)
    assert db.query(ProviderForecastResult).one().snapshot_id == prematch.id


# ------------------------------------------------------------------- the same question for experts
def test_two_expert_predictions_published_at_the_same_moment_are_both_scored(db):
    """No pick-one step exists on the expert side, so an equal timestamp cannot hide a score.

    Every live published prediction is scored on its own row, keyed by prediction_id. Two versions
    sharing a publication time are two predictions, both counted - not two candidates for one slot,
    which is the shape that lost a forecast.
    """
    match = played(db, 2, 0)
    user = User(id=uuid.uuid4(), email=f"tipster-{uuid.uuid4().hex[:8]}@test.local",
                username=f"tipster_{uuid.uuid4().hex[:8]}", password_hash="not-a-real-hash",
                user_type=UserType.EXPERT, account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()

    published = KICKOFF - timedelta(hours=6)
    for _ in range(2):
        db.add(Prediction(
            id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
            created_by=user.id, home_win_prob=Decimal("0.6"), draw_prob=Decimal("0.25"),
            away_win_prob=Decimal("0.15"), confidence_score=Decimal("0.8"),
            status=PredictionStatus.PUBLISHED, priority_level=100, published_at=published,
            created_at=published, reasoning="constructed for a tie test"))
    db.flush()

    S.SettlementService(db).settle_range(*WINDOW, commit=False)
    counts = source_counts(db, str(user.id))
    assert counts["scored"] == 2 and counts["pending"] == 0 and counts["eligible"] == 2
