"""
Two DELETEs of the same prediction at the same moment - on a REAL, isolated PostgreSQL, each request
with its own connection and its own session, so the database itself arbitrates.

The deletion used to be a plain read followed by an unconditional write. Under READ COMMITTED both
requests read ``deleted_at`` as NULL, both wrote their own time, the later commit won, and both
appended a DELETE audit entry. A deletion is now taken under the row lock (SELECT ... FOR UPDATE,
re-read with populate_existing so an object the session already holds cannot hide the other
request's write) and written as a compare-and-set (UPDATE ... WHERE deleted_at IS NULL). Exactly
one request deletes; the other waits for it and then reports that the prediction was already gone.

The interleaving is forced at the database driver: a gate holds worker 1 just before it executes
its UPDATE of predictions.predictions - after its read, so on the fixed code with the row lock
taken - until the test has seen worker 2 either wait on that lock or run to completion. Every wait
is bounded. The workers run the endpoint function itself, so the audit trail is part of the proof.

Runs only when `RACE_TEST_DATABASE_URL` names an isolated server, for example a throwaway container:

    docker run -d --rm --pull never --name expert-fixes-race-pg \\
        -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=forecast_race_test \\
        -p 127.0.0.1:5440:5440 --tmpfs /var/lib/postgresql/data postgres:15-alpine -c port=5440
    RACE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5440/forecast_race_test pytest ...

It refuses the application's databases and the application's server port, and it empties every
table of the database it is given after each test - acceptable only on a disposable one.
"""
from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.endpoints.expert import delete_prediction as delete_endpoint
from app.db.base import Base
from app.models.audit import AuditAction, AuditLog
from app.models.predictions import (
    League, Match, MatchStatus, Prediction, PredictionSource, PredictionStatus, Team,
)
from app.models.users import AccountStatus, User, UserType
from tests.services.test_forecast_sync_concurrency import (  # noqa: F401 - shared fixtures
    WAIT_SECONDS, InThread, closed_network, wait,
)

URL = os.environ.get("RACE_TEST_DATABASE_URL")
APPLICATION_DATABASES = {"soccer_predictions", "soccer_predictions_e2e", "soccer_predictions_dev",
                         "soccer_predictions_qa", "soccer_predictions_test"}
APPLICATION_PORT = 5432
pytestmark = pytest.mark.skipif(
    not URL, reason="RACE_TEST_DATABASE_URL is not set: no isolated PostgreSQL for independent sessions")

KICKOFF = datetime(2026, 11, 7, 15, 0)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(URL, pool_size=6, connect_args={"connect_timeout": 3})
    with eng.connect() as conn:
        name, port = conn.execute(text("select current_database(), inet_server_port()")).one()
        if name in APPLICATION_DATABASES or port == APPLICATION_PORT:
            pytest.fail(f"refusing {name} on port {port}: these tests run only on an isolated PostgreSQL")
        for schema in ("users", "predictions", "ml_models", "analytics", "audit"):
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        conn.commit()
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture
def world(engine):
    """An expert and one published prediction of theirs, committed, so both workers see them."""
    Session = sessionmaker(bind=engine)
    setup = Session()
    suffix = uuid.uuid4().hex[:8]
    expert = User(id=uuid.uuid4(), email=f"race-{suffix}@test.local", username=f"race_{suffix}",
                  password_hash="not-a-real-hash", user_type=UserType.EXPERT,
                  account_status=AccountStatus.ACTIVE, email_verified=True)
    league = League(id=uuid.uuid4(), name=f"Race League {suffix}", display_name="Race League",
                    country="England", is_active=True)
    home = Team(id=uuid.uuid4(), name=f"Home {suffix}", country="England")
    away = Team(id=uuid.uuid4(), name=f"Away {suffix}", country="England")
    setup.add_all([expert, league, home, away])
    setup.flush()
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=home.id, away_team_id=away.id,
                  match_date=KICKOFF, status=MatchStatus.SCHEDULED,
                  external_api_id=f"ext-race-{suffix}", external_api_source="sample", match_metadata={})
    setup.add(match)
    setup.flush()
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL,
                            created_by=expert.id, home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"),
                            away_win_prob=Decimal("0.2"), confidence_score=Decimal("0.8"),
                            status=PredictionStatus.PUBLISHED, priority_level=100,
                            published_at=KICKOFF - timedelta(days=1), reasoning="raced")
    setup.add(prediction)
    setup.commit()
    world = SimpleNamespace(Session=Session, expert_id=expert.id, prediction_id=prediction.id)
    setup.close()
    yield world
    with engine.begin() as conn:
        tables = ", ".join(f"{t.schema}.{t.name}" if t.schema else t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


class DeletionGate:
    """Records every UPDATE of predictions.predictions that writes deleted_at, by worker, and holds
    worker 1 just before its own until the test lets it go."""

    PATTERN = re.compile(r"^\s*UPDATE predictions\.predictions\b(?!_)", re.IGNORECASE)

    def __init__(self, engine):
        self.engine = engine
        self.updates = []
        self.arrived = threading.Event()
        self.go = threading.Event()
        event.listen(engine, "before_cursor_execute", self._before)

    def _before(self, conn, cursor, statement, parameters, context, executemany):
        if not (self.PATTERN.match(statement) and "deleted_at" in statement):
            return
        name = threading.current_thread().name
        self.updates.append(name)
        if name == "worker 1":
            self.arrived.set()
            if not self.go.wait(WAIT_SECONDS):
                raise AssertionError("worker 1 was never let through to its update")

    def close(self):
        event.remove(self.engine, "before_cursor_execute", self._before)


def run_delete(world):
    """One request: its own session, the endpoint function itself, as FastAPI would call it."""
    session = world.Session()
    try:
        user = session.get(User, world.expert_id)
        return asyncio.run(delete_endpoint(prediction_id=str(world.prediction_id), db=session,
                                           current_user=user))
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def waiting_on_a_lock(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text(
            "select count(*) from pg_stat_activity "
            "where datname = current_database() and wait_event_type = 'Lock'")).scalar()


def test_two_simultaneous_deletes_write_once_and_the_loser_reports_already_deleted(engine, world):
    gate = DeletionGate(engine)
    try:
        one = InThread(lambda: run_delete(world), "worker 1")
        wait(gate.arrived, "worker 1 at its update")
        two = InThread(lambda: run_delete(world), "worker 2")

        # Worker 2 must now be parked on worker 1's row lock. On the old code it never was: it read
        # deleted_at as NULL without a lock and ran straight through to its own write.
        blocked = False
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline and two.thread.is_alive():
            if waiting_on_a_lock(engine) > 0:
                blocked = True
                break
            time.sleep(0.05)

        gate.go.set()
        first = one.join()
        second = two.join()
    finally:
        gate.close()

    session = world.Session()
    try:
        stored = session.get(Prediction, world.prediction_id).deleted_at
        audit = session.query(AuditLog).filter(AuditLog.resource_type == "prediction",
                                               AuditLog.resource_id == world.prediction_id,
                                               AuditLog.action == AuditAction.DELETE).all()
    finally:
        session.close()

    assert gate.updates == ["worker 1"], f"deleted_at was written by {gate.updates}"
    assert len(audit) == 1, f"{len(audit)} deletion entries for one deletion"
    assert first["already_deleted"] is False, first
    assert second["already_deleted"] is True, second
    assert first["deleted_at"] == second["deleted_at"]
    assert first["deleted_at"] == stored.isoformat() + "Z", "the stored time is the winner's"
    assert audit[0].audit_metadata["deleted_at"] == stored.isoformat()
    assert blocked, "worker 2 was never made to wait for worker 1's row lock"
