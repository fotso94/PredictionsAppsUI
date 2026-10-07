"""
The match-data block on /data-providers/status and on its own at /data-providers/match-data.

What these lock down:
* /status carries `match_data`, and /match-data serves that same block on its own - the same state,
  sources and counts, a kilobyte rather than the whole status payload;
* on the chain as it stood on 2026-10-07 (three refusals, failing passes) the block reads BLOCKED,
  with `since` the newest provider write in the database and the waiting forecasts counted;
* a row stored again from a cached copy after the refusal - the registry stamps the store, not the
  answer - does not move `since` on either endpoint: it stays at the provider's last answer;
* NEITHER ENDPOINT SENDS A PROVIDER REQUEST OR SPENDS ALLOWANCE. The real Live Score, API-Football
  and TheSportsDB classes are configured (with test values) so that a regression would have
  something to call; every HTTP request and every budget reservation raises if touched, and the
  day's budget counters are read back unmoved.

Requires PostgreSQL (TEST_DATABASE_URL; skipped when unreachable). Redis is an in-memory double,
so nothing here reads or writes the real cache or the real budget counters.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.deps import get_db as deps_get_db
from app.db.base import Base
from app.db.session import get_db as session_get_db
from app.main import app
from app.models.predictions import Match, MatchStatus, Team
from app.services import match_data_health as H
from app.services.forecast_service import STATUS_KEY as FORECAST_STATUS_KEY
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.budget import RequestBudget
from app.services.providers.http import ProviderHttpClient
from app.services.providers.sample import SampleDataProvider, SampleForecastProvider
from app.services.sync_scheduler import STATE_KEY
from tests.providers.support import FakeRedis

from tests.conftest import TEST_DATABASE_URL  # noqa: E402 - one place for the default

STATUS = "/api/v1/data-providers/status"
MATCH_DATA = "/api/v1/data-providers/match-data"
CHAIN = ("livescore", "api_football", "thesportsdb")

NOW = datetime.now(timezone.utc).replace(microsecond=0)
# In the future, so no row another module leaves behind can be newer than it. The provider records
# are dated around it - the last answer a second before the write, every refusal after it - because
# a stamp is checked against its own provider's record, and one its record cannot account for
# does not count as a write.
WRITTEN = NOW + timedelta(days=30)
ANSWERED = WRITTEN - timedelta(seconds=1)
REFUSED = WRITTEN + timedelta(minutes=5)

REFUSALS = {
    "livescore": ("livescore: authentication rejected (HTTP 401): This API key and secret do not have access "
                  "to our data enabled"),
    "api_football": ("API-Football errors: {'plan': 'Free plans do not have access to this season, try from "
                     "2022 to 2024.'}"),
    "thesportsdb": ('thesportsdb: request rejected (HTTP 400): {"Message":"Invalid Premium API key: Signup '
                    'here: https:\\/\\/www.thesportsdb.com\\/pricing"}'),
}


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
    H.forget_stored_counts()
    yield session
    H.forget_stored_counts()
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def stores(monkeypatch):
    """One in-memory cache and one in-memory budget store, in place of both real Redis databases."""
    cache, budgets = FakeRedis(), FakeRedis()
    for module in ("app.services.match_data_service", "app.services.forecast_service",
                   "app.services.sync_scheduler", "app.services.providers.livescore_api"):
        monkeypatch.setattr(f"{module}.MatchCache", lambda client=None: MatchCache(client=cache))
    monkeypatch.setattr("app.services.providers.budget._redis", lambda: budgets)
    return cache, budgets


@pytest.fixture
def real_chain(monkeypatch):
    """The production chain's classes, configured with test values so a regression has something to call."""
    monkeypatch.setattr(settings, "DATA_PROVIDER", "livescore")
    monkeypatch.setattr(settings, "DATA_PROVIDER_FALLBACKS", "api_football,thesportsdb")
    monkeypatch.setattr(settings, "LIVESCORE_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LIVESCORE_API_SECRET", "test-secret")
    monkeypatch.setattr(settings, "API_FOOTBALL_KEY", "test-key")
    monkeypatch.setattr(settings, "THESPORTSDB_KEY", "test-key")


@pytest.fixture(autouse=True)
def no_provider_calls(monkeypatch):
    """Every way out to a provider, and every way of spending an allowance, fails the test."""
    def refuse(name):
        def _refuse(*args, **kwargs):
            raise AssertionError(f"{name} was called; the match-data block reads recorded state only")
        return _refuse

    monkeypatch.setattr(ProviderHttpClient, "get_json", refuse("a provider HTTP request"))
    monkeypatch.setattr(RequestBudget, "consume", refuse("RequestBudget.consume"))
    for method in ("get_fixtures", "get_live", "get_results", "get_standings", "list_competitions"):
        monkeypatch.setattr(SampleDataProvider, method, refuse(f"SampleDataProvider.{method}"))
    monkeypatch.setattr(SampleForecastProvider, "get_forecasts", refuse("SampleForecastProvider.get_forecasts"))


@pytest.fixture
def client(db, stores, real_chain):
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
def _seed_todays_state(cache: FakeRedis) -> None:
    """The recorded state of 2026-10-07: three refusals, failing fetches, recover and settle 'fine'."""
    store = MatchCache(client=cache)
    for name, error in REFUSALS.items():
        store.set(f"provider:status:{name}", {
            "last_success_at": ANSWERED.isoformat(), "last_error_at": REFUSED.isoformat(), "last_error": error,
        }, ttl=3600)
    tasks = {
        "fixtures": {"last_run_at": (NOW - timedelta(minutes=30)).isoformat(), "consecutive_failures": 15,
                     "last_success_at": (NOW - timedelta(days=4)).isoformat(),
                     "next_due_at": (NOW + timedelta(hours=5)).isoformat()},
        "results": {"last_run_at": (NOW - timedelta(minutes=30)).isoformat(), "consecutive_failures": 19,
                    "last_success_at": (NOW - timedelta(days=4)).isoformat(),
                    "next_due_at": (NOW + timedelta(hours=5)).isoformat()},
        "recover": {"last_run_at": (NOW - timedelta(minutes=5)).isoformat(), "consecutive_failures": 0,
                    "last_success_at": (NOW - timedelta(minutes=5)).isoformat(),
                    "next_due_at": (NOW + timedelta(minutes=25)).isoformat()},
        "settle": {"last_run_at": (NOW - timedelta(minutes=5)).isoformat(), "consecutive_failures": 0,
                   "last_success_at": (NOW - timedelta(minutes=5)).isoformat(),
                   "next_due_at": (NOW + timedelta(hours=2)).isoformat()},
    }
    for name, state in tasks.items():
        store.set(STATE_KEY.format(name=name), state, ttl=3600)
    store.set(FORECAST_STATUS_KEY.format(provider=SampleForecastProvider.name), {
        "synced_at": (NOW - timedelta(minutes=30)).isoformat(),
        "retried": {"premier_league": {"pending": 10, "attached": 0}, "la_liga": {"pending": 9, "attached": 1}},
    }, ttl=3600)


def _stored_match(db, synced: datetime = WRITTEN) -> Match:
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    teams = [Team(id=uuid.uuid4(), name=f"{side} {uuid.uuid4().hex[:6]}", country="England") for side in ("Home", "Away")]
    db.add_all(teams)
    db.flush()
    row = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=teams[0].id, away_team_id=teams[1].id,
                match_date=(NOW + timedelta(days=2)).replace(tzinfo=None), status=MatchStatus.SCHEDULED,
                external_api_id=f"ls-md-{uuid.uuid4().hex[:8]}", external_api_source="livescore",
                match_metadata={"provider": "livescore", "last_synced_at": synced.isoformat()})
    db.add(row)
    db.flush()
    return row


def _spent(budgets: FakeRedis) -> dict:
    """Every provider's counters for today, read from the in-memory budget store."""
    return {name: (RequestBudget(name, 100, client=budgets).used_today(),
                   RequestBudget(name, 100, client=budgets).refused_today())
            for name in (*CHAIN, SampleForecastProvider.name)}


# ----------------------------------------------------------------------------- the tests
def test_status_and_the_lean_endpoint_carry_the_same_blocked_block_without_spending_anything(client, db, stores):
    cache, budgets = stores
    _seed_todays_state(cache)
    _stored_match(db)
    before = _spent(budgets)

    status = client.get(STATUS)
    assert status.status_code == 200, status.text
    block = status.json()["match_data"]
    assert block["state"] == "blocked"
    assert block["since"] == WRITTEN.isoformat() and block["since_basis"] == "last_provider_write"
    assert [(s["name"], s["role"], s["answer"], s["kind"]) for s in block["sources"]] == [
        ("livescore", "primary", "refused", "access"),
        ("api_football", "fallback", "refused", "plan"),
        ("thesportsdb", "fallback", "refused", "access"),
    ]
    assert block["forecasts_waiting_for_fixtures"] == 18
    assert block["upcoming_stored"] >= 1
    assert block["next_check_at"] == (NOW + timedelta(minutes=25)).isoformat()

    lean = client.get(MATCH_DATA)
    assert lean.status_code == 200, lean.text
    alone = lean.json()
    assert set(alone) == set(block), "the lean endpoint serves the match-data block and nothing else"
    assert {k: v for k, v in alone.items() if k != "checked_at"} == {k: v for k, v in block.items() if k != "checked_at"}
    assert len(lean.content) < 4096, "a kilobyte or two, not the whole status payload"
    assert len(lean.content) * 3 < len(status.content)

    assert _spent(budgets) == before == {name: (0, 0) for name in before}, "no allowance moved"


def test_a_healthy_chain_reads_ok_and_still_sends_nothing(client, db, stores):
    cache, budgets = stores
    store = MatchCache(client=cache)
    for name in CHAIN:
        store.set(f"provider:status:{name}", {"last_success_at": NOW.isoformat()}, ttl=3600)
    for name in ("fixtures", "live", "results"):
        store.set(STATE_KEY.format(name=name), {"last_run_at": NOW.isoformat(), "last_success_at": NOW.isoformat(),
                                                "consecutive_failures": 0}, ttl=3600)
    _stored_match(db)

    block = client.get(MATCH_DATA).json()
    assert block["state"] == "ok"
    assert block["affects"] == []
    assert client.get(STATUS).json()["match_data"]["state"] == "ok"
    assert _spent(budgets) == {name: (0, 0) for name in (*CHAIN, SampleForecastProvider.name)}


def test_a_row_stored_again_from_a_cached_copy_after_the_refusal_moves_since_on_neither_endpoint(client, db, stores):
    # `MatchRegistry` stamps `last_synced_at` when it stores a row, and a results pass stores the
    # 24-hour stale copy again once every provider has failed. That row is stamped after Live
    # Score's refusal, which no answer of Live Score's can account for.
    cache, budgets = stores
    _seed_todays_state(cache)
    _stored_match(db)
    _stored_match(db, synced=REFUSED + timedelta(minutes=30))

    for block in (client.get(STATUS).json()["match_data"], client.get(MATCH_DATA).json()):
        assert block["state"] == "blocked"
        assert block["since"] == ANSWERED.isoformat(), "bounded by Live Score's last answer, not the re-store"
        assert block["since_basis"] == "last_provider_answer"
    assert _spent(budgets) == {name: (0, 0) for name in (*CHAIN, SampleForecastProvider.name)}
