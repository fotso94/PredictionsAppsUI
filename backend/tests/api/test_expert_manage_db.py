"""
Managing one's own predictions, against a real database: deleting, the rows a deletion freezes,
and the counts the dashboard and the list are built from.

What was wrong before this change:

* DELETE was not idempotent. Every call rewrote ``deleted_at`` with a fresh time and wrote another
  audit entry, each stamped with yet another fresh time, so a retry sent after kickoff moved a
  prematch withdrawal past kickoff and put the prediction back into the measured record.
* A deleted prediction could still be edited and publish-toggled, so its withdrawal evidence
  (status, ``unpublished_at``) kept moving after the expert had taken it down.
* The dashboard counted in Python over at most 1000 loaded rows, and its "not published" figure
  was PENDING alone, so an archived prediction was counted nowhere and Written did not equal
  Published + Not published.
* My Predictions returned no total, so the page could not know whether another page existed.

Requires PostgreSQL (TEST_DATABASE_URL, default the docker-compose test database); skipped when
unreachable. No provider is called, and the app's lifespan is never entered (no `with TestClient`).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, insert, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.deps import get_current_expert_user
from app.core.deps import get_db as deps_get_db
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.audit import AuditAction, AuditLog
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
from app.services.expert_prediction import ExpertPredictionService

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

#: Far enough ahead that no other module in the suite has fixtures there.
KICKOFF = (datetime.now(timezone.utc) + timedelta(days=52)).replace(
    hour=19, minute=0, second=0, microsecond=0, tzinfo=None)


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


@pytest.fixture
def client(db):
    """The expert endpoints depend on app.core.deps.get_db and the public ones on
    app.db.session.get_db - two distinct callables. Both are overridden so every request sees the
    test's own uncommitted rows."""
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps_get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(deps_get_db, None)
        app.dependency_overrides.pop(get_current_expert_user, None)


def signed_in(user: User) -> None:
    """Make `user` the caller of the expert endpoints for the rest of the test."""
    app.dependency_overrides[get_current_expert_user] = lambda: user


# ----------------------------------------------------------------------------- helpers
def _expert(db, name: str = "manager") -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"{name}-{suffix}@test.local", username=f"{name}_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _match(db, kickoff: datetime = KICKOFF) -> Match:
    suffix = uuid.uuid4().hex[:8]
    league = League(id=uuid.uuid4(), name=f"Manage League {suffix}", display_name="Manage League",
                    country="England", is_active=True)
    home = Team(id=uuid.uuid4(), name=f"Home {suffix}", country="England")
    away = Team(id=uuid.uuid4(), name=f"Away {suffix}", country="England")
    db.add_all([league, home, away])
    db.flush()
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                  match_date=kickoff, status=MatchStatus.SCHEDULED,
                  external_api_id=f"ext-manage-{suffix}", external_api_source="sample",
                  match_metadata={})
    db.add(match)
    db.flush()
    return match


def _prediction(db, match: Match, user: User, status: PredictionStatus = PredictionStatus.PUBLISHED,
                confidence: Optional[str] = "0.8", deleted_at: Optional[datetime] = None,
                created_at: Optional[datetime] = None) -> Prediction:
    row = Prediction(
        id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
        created_by=user.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
        away_win_prob=Decimal("0.2"),
        confidence_score=Decimal(confidence) if confidence is not None else None,
        status=status, priority_level=100, reasoning="constructed for a management test",
        published_at=(match.match_date - timedelta(days=1)
                      if status in (PredictionStatus.PUBLISHED, PredictionStatus.ARCHIVED) else None),
        deleted_at=deleted_at, created_at=created_at or datetime.utcnow())
    db.add(row)
    db.flush()
    return row


def _reread(db, prediction: Prediction) -> Prediction:
    db.expire_all()
    return db.query(Prediction).filter(Prediction.id == prediction.id).one()


def _deletion_audit_rows(db, prediction: Prediction):
    return db.query(AuditLog).filter(
        AuditLog.resource_type == "prediction",
        AuditLog.resource_id == prediction.id,
        AuditLog.action == AuditAction.DELETE,
    ).all()


# ----------------------------------------------------------------------------- deleting twice
def test_deleting_twice_answers_200_both_times_with_the_first_deletion_time(client, db):
    """A retry is a success (the frontend and the QA cleanup both count on 2xx), and it says
    truthfully that the prediction was already gone, and since when."""
    expert = _expert(db)
    prediction = _prediction(db, _match(db), expert)
    signed_in(expert)

    first = client.delete(f"/api/v1/expert/predictions/{prediction.id}")
    second = client.delete(f"/api/v1/expert/predictions/{prediction.id}")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    one, two = first.json(), second.json()
    assert one["message"] == two["message"] == "Prediction deleted successfully"
    assert one["prediction_id"] == two["prediction_id"] == str(prediction.id)

    stored = _reread(db, prediction).deleted_at
    assert one["deleted_at"] == two["deleted_at"], "the retry reported a different deletion time"
    assert one["deleted_at"] == stored.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    assert one["already_deleted"] is False
    assert two["already_deleted"] is True


def test_a_repeated_delete_writes_one_audit_entry_carrying_the_stored_time(client, db):
    """Every call used to append a DELETE audit entry with a fresh time of its own, so the trail
    showed withdrawals that never happened. One deletion, one entry, the time actually stored."""
    expert = _expert(db)
    prediction = _prediction(db, _match(db), expert)
    signed_in(expert)

    for _ in range(3):
        assert client.delete(f"/api/v1/expert/predictions/{prediction.id}").status_code == 200

    rows = _deletion_audit_rows(db, prediction)
    assert len(rows) == 1, f"{len(rows)} deletion entries for one deletion"
    stored = _reread(db, prediction).deleted_at
    assert rows[0].audit_metadata["deleted_at"] == stored.isoformat()
    assert rows[0].user_id == expert.id


def test_deleting_a_missing_prediction_is_a_404(client, db):
    signed_in(_expert(db))

    response = client.delete(f"/api/v1/expert/predictions/{uuid.uuid4()}")

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"]


def test_another_expert_cannot_delete_a_prediction_and_nothing_is_written(client, db):
    author, intruder = _expert(db, "author"), _expert(db, "intruder")
    prediction = _prediction(db, _match(db), author)
    signed_in(intruder)

    response = client.delete(f"/api/v1/expert/predictions/{prediction.id}")

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "You can only delete your own predictions"
    assert _reread(db, prediction).deleted_at is None
    assert _deletion_audit_rows(db, prediction) == []


def test_a_lost_compare_and_set_reports_the_other_deletion_and_overwrites_nothing(engine, db):
    """Defence in depth behind the row lock: the write is UPDATE ... WHERE deleted_at IS NULL.

    A deletion that lands between the read and the write (here forced in, on the same transaction,
    just before the service's UPDATE runs) wins; this call then writes nothing and reports the
    stored time as already deleted. Added with the fix: it exercises a branch of the new code
    rather than a defect of the old one, which had no such branch.
    """
    expert = _expert(db)
    prediction = _prediction(db, _match(db), expert)
    theirs = datetime(2026, 1, 2, 3, 4, 5)
    mine = datetime(2026, 1, 2, 9, 0, 0)

    def land_another_deletion_first(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("UPDATE predictions.predictions") and "deleted_at IS NULL" in statement:
            cursor.execute("UPDATE predictions.predictions SET deleted_at = %(t)s WHERE id = %(id)s",
                           {"t": theirs, "id": str(prediction.id)})

    event.listen(engine, "before_cursor_execute", land_another_deletion_first)
    try:
        outcome = ExpertPredictionService(db, clock=lambda: mine).delete_prediction(
            str(prediction.id), expert)
    finally:
        event.remove(engine, "before_cursor_execute", land_another_deletion_first)

    assert outcome.already_deleted is True
    assert outcome.deleted_at == theirs
    assert _reread(db, prediction).deleted_at == theirs


# ----------------------------------------------------------------------- a deleted row stays put
def test_a_deleted_prediction_cannot_be_edited(client, db):
    """Editing a deleted row rewrote the values it was withdrawn with and appended a revision to a
    prediction nobody could see. It is refused as a missing one is, and nothing changes."""
    expert = _expert(db)
    prediction = _prediction(db, _match(db), expert)
    signed_in(expert)
    assert client.delete(f"/api/v1/expert/predictions/{prediction.id}").status_code == 200
    before = _reread(db, prediction)
    values = (before.home_win_prob, before.reasoning, before.updated_at, before.deleted_at)

    response = client.put(f"/api/v1/expert/predictions/{prediction.id}",
                          json={"home_win_prob": 0.7, "draw_prob": 0.2, "away_win_prob": 0.1,
                                "reasoning": "rewritten after it was deleted"})

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"]
    after = _reread(db, prediction)
    assert (after.home_win_prob, after.reasoning, after.updated_at, after.deleted_at) == values
    assert db.query(PredictionAudit).filter(PredictionAudit.prediction_id == prediction.id).count() == 0


@pytest.mark.parametrize("status", [PredictionStatus.PUBLISHED, PredictionStatus.ARCHIVED])
def test_a_deleted_prediction_cannot_be_publish_toggled(client, db, status):
    """Toggling a deleted row moved its status and its unpublished_at - the withdrawal evidence
    settlement reads - after the expert had already taken it down."""
    expert = _expert(db)
    prediction = _prediction(db, _match(db), expert, status=status)
    signed_in(expert)
    assert client.delete(f"/api/v1/expert/predictions/{prediction.id}").status_code == 200
    before = _reread(db, prediction)
    evidence = (before.status, before.published_at, before.unpublished_at, before.updated_at,
                before.deleted_at)

    response = client.post(f"/api/v1/expert/predictions/{prediction.id}/toggle-publish")

    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"]
    after = _reread(db, prediction)
    assert (after.status, after.published_at, after.unpublished_at, after.updated_at,
            after.deleted_at) == evidence
    assert db.query(PredictionAudit).filter(PredictionAudit.prediction_id == prediction.id).count() == 0


def test_editing_or_toggling_a_missing_prediction_is_a_404_too(client, db):
    """The same answer as for a deleted one: the caller cannot tell the two apart, and need not."""
    signed_in(_expert(db))
    missing = uuid.uuid4()

    edit = client.put(f"/api/v1/expert/predictions/{missing}",
                      json={"home_win_prob": 0.7, "draw_prob": 0.2, "away_win_prob": 0.1})
    toggle = client.post(f"/api/v1/expert/predictions/{missing}/toggle-publish")

    assert edit.status_code == 404, edit.text
    assert toggle.status_code == 404, toggle.text


def test_a_live_prediction_is_still_edited_and_toggled_as_before(client, db):
    """The control: only a deleted row is refused."""
    expert = _expert(db)
    prediction = _prediction(db, _match(db), expert)
    signed_in(expert)

    edit = client.put(f"/api/v1/expert/predictions/{prediction.id}",
                      json={"home_win_prob": 0.7, "draw_prob": 0.2, "away_win_prob": 0.1})
    toggle = client.post(f"/api/v1/expert/predictions/{prediction.id}/toggle-publish")

    assert edit.status_code == 200, edit.text
    assert toggle.status_code == 200, toggle.text
    assert toggle.json()["status"] == "archived"


# ----------------------------------------------------------------------------- the counts
def _one_of_each(db):
    """One expert with a row in each status they can hold, plus two rows that must not count."""
    expert, other = _expert(db), _expert(db, "other")
    match = _match(db)
    _prediction(db, match, expert, PredictionStatus.PUBLISHED, confidence="0.9")
    _prediction(db, match, expert, PredictionStatus.ARCHIVED, confidence="0.5")
    _prediction(db, match, expert, PredictionStatus.PENDING, confidence=None)
    _prediction(db, match, expert, PredictionStatus.REJECTED, confidence="0.7")
    _prediction(db, match, expert, PredictionStatus.PUBLISHED, confidence="0.1",
                deleted_at=datetime.utcnow())                                  # soft-deleted
    _prediction(db, match, other, PredictionStatus.ARCHIVED, confidence="0.2")   # someone else's
    return expert


def test_the_counts_by_status_leave_out_deleted_and_foreign_rows(db):
    expert = _one_of_each(db)

    counts = ExpertPredictionService(db).count_expert_predictions_by_status(expert)

    assert counts == {PredictionStatus.PUBLISHED: 1, PredictionStatus.ARCHIVED: 1,
                      PredictionStatus.PENDING: 1, PredictionStatus.REJECTED: 1}


def test_the_dashboard_counts_add_up(client, db):
    """Written = Published + Not published, whatever the statuses. Before, "not published" was
    PENDING alone: an unpublished (ARCHIVED) or REJECTED row was counted nowhere."""
    expert = _one_of_each(db)
    signed_in(expert)

    response = client.get("/api/v1/expert/analytics/performance")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_predictions"] == 4
    assert data["published_predictions"] == 1
    assert data["pending_predictions"] == 1, "the old field keeps its old meaning"
    assert data["archived_predictions"] == 1
    assert data["not_published_predictions"] == 3
    assert data["total_predictions"] == data["published_predictions"] + data["not_published_predictions"]
    # The mean of the convictions that exist, on the same rows: (0.9 + 0.5 + 0.7) / 3.
    assert data["average_confidence"] == pytest.approx(0.7)
    assert len(data["recent_predictions"]) == 4


def test_the_dashboard_counts_are_not_capped_at_a_thousand_rows(client, db):
    """The counts were len() of a list fetched with limit=1000."""
    expert = _expert(db)
    match = _match(db)
    start = datetime.utcnow() - timedelta(days=5)
    db.execute(insert(Prediction), [
        dict(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
             created_by=expert.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
             away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.6"),
             status=PredictionStatus.PUBLISHED, priority_level=100,
             published_at=start, created_at=start + timedelta(seconds=n),
             updated_at=start + timedelta(seconds=n))
        for n in range(1001)])
    _prediction(db, match, expert, PredictionStatus.ARCHIVED, created_at=start - timedelta(days=1))
    db.flush()
    signed_in(expert)

    data = client.get("/api/v1/expert/analytics/performance").json()

    assert data["total_predictions"] == 1002
    assert data["published_predictions"] == 1001
    assert data["archived_predictions"] == 1, "the oldest row fell outside the first thousand"
    assert data["not_published_predictions"] == 1
    assert len(data["recent_predictions"]) == 10


# ----------------------------------------------------------------------------- the list total
def test_my_predictions_carries_the_total_in_x_total_count(client, db):
    """The body stays a bare list (the QA cleanup and the composer suite read it as one); the total
    for the same filter travels in a header, so the page can tell whether another page exists."""
    expert = _one_of_each(db)
    signed_in(expert)

    page = client.get("/api/v1/expert/predictions/my-predictions?limit=2&offset=0")
    archived = client.get("/api/v1/expert/predictions/my-predictions?status=archived")
    beyond = client.get("/api/v1/expert/predictions/my-predictions?limit=2&offset=10")

    assert page.status_code == 200, page.text
    assert isinstance(page.json(), list) and len(page.json()) == 2
    assert page.headers["x-total-count"] == "4"
    assert archived.headers["x-total-count"] == "1" and len(archived.json()) == 1
    assert beyond.json() == [] and beyond.headers["x-total-count"] == "4"


def test_the_total_count_header_is_exposed_to_the_browser(client, db):
    """A cross-origin page can read a response header only if CORS exposes it."""
    signed_in(_expert(db))
    origin = settings.BACKEND_CORS_ORIGINS[0]

    response = client.get("/api/v1/expert/predictions/my-predictions", headers={"Origin": origin})

    assert response.status_code == 200, response.text
    assert response.headers["x-total-count"] == "0"
    assert response.headers["access-control-allow-origin"] == origin
    exposed = [h.strip().lower() for h in response.headers["access-control-expose-headers"].split(",")]
    assert "x-total-count" in exposed
