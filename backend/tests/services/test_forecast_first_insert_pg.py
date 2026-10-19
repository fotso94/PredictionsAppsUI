"""
Two workers meeting a forecast that has no row yet - on a REAL, isolated PostgreSQL, each worker with
its own connection and its own session, so the database itself arbitrates.

`SELECT ... FOR UPDATE` locks a row that exists; it cannot lock one that does not. Two writers that
both find no row and both insert used to collide on `uq_provider_forecasts_match_provider`; the
second one's IntegrityError rolled back its transaction, newer forecast and all. The same held one
step earlier for the match's provider reference (`uq_provider_entity_refs_provider_external`). Both
are now claimed with INSERT ... ON CONFLICT DO NOTHING and then read back under FOR UPDATE.

The interleaving is forced at the database driver: a gate holds a named worker thread just before
it executes its INSERT into the table under test, until the test lets it go. Every wait is bounded.

Runs only when `RACE_TEST_DATABASE_URL` names an isolated server, for example a throwaway container:

    docker run -d --rm --pull never --name policy-round-race-test-postgres \\
        -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=forecast_race_test \\
        -p 127.0.0.1:5440:5440 --tmpfs /var/lib/postgresql/data postgres:15-alpine -c port=5440
    RACE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5440/forecast_race_test pytest ...

It refuses the application's databases and the application's server port, and it empties every
table of the database it is given after each test - acceptable only on a disposable one.
"""
from __future__ import annotations

import os
import re
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import Match
from app.models.provider_data import ProviderEntityRef, ProviderForecastRecord
from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.base import ProviderForecast
from tests.providers.support import FakeRedis
from tests.services.test_forecast_retention_db import KEY, KICKOFF, _event, _store_the_fixture
from tests.services.test_forecast_sync_concurrency import (  # noqa: F401 - shared fixtures
    WAIT_SECONDS, InThread, closed_network, wait,
)

URL = os.environ.get("RACE_TEST_DATABASE_URL")
APPLICATION_DATABASES = {"soccer_predictions", "soccer_predictions_e2e", "soccer_predictions_dev",
                         "soccer_predictions_qa", "soccer_predictions_test"}
APPLICATION_PORT = 5432
pytestmark = pytest.mark.skipif(
    not URL, reason="RACE_TEST_DATABASE_URL is not set: no isolated PostgreSQL for independent sessions")

PROVIDER = "stub"
NOW = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
OLDER, NEWER = NOW, NOW + timedelta(minutes=5)


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
    """The league, teams and match committed, so both workers' sessions see them."""
    Session = sessionmaker(bind=engine)
    setup = Session()
    registry = MatchRegistry(setup)
    match = _store_the_fixture(registry)
    league = registry.ensure_canonical_league(KEY)
    setup.commit()
    world = SimpleNamespace(Session=Session, match_id=match.id, league_id=league.id)
    setup.close()
    yield world
    with engine.begin() as conn:
        tables = ", ".join(f"{t.schema}.{t.name}" if t.schema else t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


class InsertGate:
    """Holds a named worker thread just before it executes an INSERT into predictions.<table>."""

    def __init__(self, engine, table: str, workers):
        self.engine = engine
        self.pattern = re.compile(rf"^\s*INSERT INTO predictions\.{table}\b(?!_)", re.IGNORECASE)
        self.arrived = {name: threading.Event() for name in workers}
        self.go = {name: threading.Event() for name in workers}
        event.listen(engine, "before_cursor_execute", self._before)

    def _before(self, conn, cursor, statement, parameters, context, executemany):
        name = threading.current_thread().name
        if name in self.arrived and not self.go[name].is_set() and self.pattern.match(statement):
            self.arrived[name].set()
            if not self.go[name].wait(WAIT_SECONDS):
                raise AssertionError(f"{name} was never let through to its insert")

    def close(self):
        event.remove(self.engine, "before_cursor_execute", self._before)


def forecast(retrieved: datetime, home_prob: float) -> ProviderForecast:
    return ProviderForecast(provider=PROVIDER, external_event_id="evt-27378", competition_key=KEY,
                            home_name="Rep. Of Ireland", away_name="Kosovo", kickoff_utc=KICKOFF,
                            home_prob=home_prob, draw_prob=0.30, away_prob=round(0.70 - home_prob, 2),
                            model_run_at=retrieved.replace(hour=6, minute=0), fetched_at=retrieved, raw=_event())


def run_worker(world, payload: ProviderForecast, step: str):
    """One worker: its own session, its own service, one write, one commit."""
    session = world.Session()
    try:
        svc = ForecastService(session, provider=None, cache=MatchCache(client=FakeRedis()), now=NOW,
                              keys=[KEY], sync_fixtures=False, use_default_provider=False)
        svc.registry = MatchRegistry(session)
        if step == "upsert":
            svc._upsert_record(session.get(Match, world.match_id), payload, "exact", "provider_id")
        else:
            outcome = svc.attach_forecast(payload, KEY, world.league_id)
            assert outcome["result"] == "attached", outcome
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def interleave(engine, world, table: str, first: ProviderForecast, second: ProviderForecast, step: str):
    """Both workers reach their INSERT into `table` before either runs it; the first then completes
    and commits; then the second goes on."""
    gate = InsertGate(engine, table, ["worker 1", "worker 2"])
    try:
        one = InThread(lambda: run_worker(world, first, step), "worker 1")
        wait(gate.arrived["worker 1"], "worker 1 at its insert")
        two = InThread(lambda: run_worker(world, second, step), "worker 2")
        wait(gate.arrived["worker 2"], "worker 2 at its insert")
        gate.go["worker 1"].set()
        one.join()
        gate.go["worker 2"].set()
        two.join()
    finally:
        gate.close()


ORDERS = {
    "older-first": ((OLDER, 0.38), (NEWER, 0.40)),
    "newer-first": ((NEWER, 0.40), (OLDER, 0.38)),
    "tied": ((NOW, 0.38), (NOW, 0.41)),
}


def what_was_stored(world):
    session = world.Session()
    try:
        rows = session.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == world.match_id).all()
        snapshots = ForecastService(session, provider=None, cache=MatchCache(client=FakeRedis()), now=NOW,
                                    keys=[KEY], sync_fixtures=False,
                                    use_default_provider=False).snapshots_for_match(world.match_id, PROVIDER)
        refs = session.query(ProviderEntityRef).filter(ProviderEntityRef.entity_type == "match",
                                                       ProviderEntityRef.provider == PROVIDER).all()
        return rows, snapshots, refs
    finally:
        session.close()


def utc(value):
    return value.replace(tzinfo=timezone.utc)


@pytest.mark.parametrize("order", list(ORDERS))
def test_two_workers_writing_the_first_forecast_row_both_succeed_and_the_newer_retrieval_stands(engine, world, order):
    (t1, p1), (t2, p2) = ORDERS[order]
    interleave(engine, world, "provider_forecasts", forecast(t1, p1), forecast(t2, p2), "upsert")

    rows, snapshots, _ = what_was_stored(world)
    assert len(rows) == 1, "one current row"
    [row] = rows
    if order == "tied":
        # The same retrieval read twice: the later writer, in the order the row lock serialised
        # them, is current - as SNAPSHOT_ORDER breaks the same tie by creation.
        assert utc(row.fetched_at) == NOW and float(row.home_win_prob) == p2
    else:
        assert utc(row.fetched_at) == NEWER and float(row.home_win_prob) == 0.40, "the newer retrieval stands"
    assert sorted(float(s.home_win_prob) for s in snapshots) == sorted([p1, p2]), "both retrievals in the history"
    for snap in snapshots:
        assert utc(snap.first_fetched_at) == utc(snap.last_fetched_at), "each retrieval keeps its own time"
    assert float(snapshots[-1].home_win_prob) == float(row.home_win_prob), "the history's latest is the current row"


@pytest.mark.parametrize("order", ["older-first", "newer-first"])
def test_two_workers_attaching_the_same_new_event_meet_at_its_provider_reference_and_both_succeed(engine, world, order):
    """The whole attachment: both workers find no reference for the new provider event and both
    would insert it. Neither may fail; one reference, one current row, the newer retrieval."""
    (t1, p1), (t2, p2) = ORDERS[order]
    interleave(engine, world, "provider_entity_refs", forecast(t1, p1), forecast(t2, p2), "attach")

    rows, snapshots, refs = what_was_stored(world)
    assert len(refs) == 1 and refs[0].entity_id == world.match_id
    assert len(rows) == 1 and utc(rows[0].fetched_at) == NEWER and float(rows[0].home_win_prob) == 0.40
    assert sorted(float(s.home_win_prob) for s in snapshots) == [0.38, 0.40]
