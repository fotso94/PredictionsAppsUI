"""Re-attaching a forecast we already paid for, against the REAL registry.

The mock-based tests in test_forecast_service.py can prove that `reattach_pending` does not call
the provider, but not that it BINDS: they mock the registry, so a green attachment there is the
mock agreeing with itself. This module runs the real `MatchRegistry` against PostgreSQL so the
identification is the one production performs.

The provider here is not a stub that records calls and is checked afterwards - it RAISES on every
method. A test that merely counts calls passes if the counter is read wrong; a provider that
cannot be used at all fails the moment anything reaches for it, which is the guarantee being made:
this path spends nothing because it cannot.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.provider_data import ProviderForecastRecord
from app.services.forecast_service import ForecastService, _forecast_to_dict
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.base import (
    ProviderCompetition, ProviderFixture, ProviderForecast, ProviderTeam,
)

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc)
#: Deliberately hours before `NOW`: the record must keep the moment the forecast was RETRIEVED,
#: not the moment it was finally bound to a fixture.
RETRIEVED_AT = datetime(2026, 9, 24, 6, 30, tzinfo=timezone.utc)
KEY = "uefa_nations_league"


class ProviderThatMustNotBeCalled:
    """Any use is a test failure, which is a stronger statement than a call counter."""

    name = "must-not-be-called"
    integration_status = "test"

    def is_configured(self):
        return True

    def get_forecasts(self, *args, **kwargs):
        raise AssertionError("reattach_pending reached the provider; it must spend nothing")

    def resolve_league(self, *args, **kwargs):
        raise AssertionError("reattach_pending resolved a league through the provider")

    def league_id_is_known(self, *args, **kwargs):
        raise AssertionError("reattach_pending asked the provider about a league id")

    def request_cost(self, *args, **kwargs):
        raise AssertionError("reattach_pending priced a provider request")


class FakeRedis:
    """Enough of Redis for the pending store, with no TTL behaviour to get in the way."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False, **kwargs):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    def delete(self, *keys):
        for key in keys:
            self.store.pop(key, None)
        return True

    def exists(self, key):
        return key in self.store

    def ttl(self, key):
        return 3600 if key in self.store else -2


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
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def service(db):
    svc = ForecastService(db, provider=ProviderThatMustNotBeCalled(),
                          cache=MatchCache(client=FakeRedis()), now=NOW,
                          keys=[KEY], sync_fixtures=False)
    return svc


def _forecast():
    return ProviderForecast(
        provider="gameforecast", external_event_id="evt-27378", competition_key=KEY,
        home_name="Rep. Of Ireland", away_name="Kosovo", kickoff_utc=KICKOFF,
        home_prob=0.38, draw_prob=0.32, away_prob=0.30, fetched_at=RETRIEVED_AT)


def _store_the_fixture(registry):
    """The fixture as Live Score spells it, which is not how the forecast provider spells it."""
    return registry.upsert_fixture(ProviderFixture(
        provider="livescore", external_id="ls-27378",
        competition=ProviderCompetition(provider="livescore", external_id="350",
                                        name="UEFA Nations League", key=KEY),
        home=ProviderTeam(provider="livescore", external_id="ls-roi", name="Republic of Ireland"),
        away=ProviderTeam(provider="livescore", external_id="ls-kos", name="Kosovo"),
        kickoff_utc=KICKOFF, status="scheduled"))


def _records(db, match_id):
    return db.query(ProviderForecastRecord).filter(
        ProviderForecastRecord.match_id == match_id).all()


def test_a_kept_forecast_binds_to_its_fixture_for_free(db, service):
    registry = MatchRegistry(db)
    service.registry = registry

    # 1. The forecast arrives before its fixture is stored, so nothing can identify it and it is
    #    kept. This is the state a real unmatched forecast is left in.
    outcome = service.attach_forecast(_forecast(), KEY, registry.ensure_canonical_league(KEY).id)
    assert outcome["result"] == "unmatched", outcome
    service._store_pending(KEY, [_forecast_to_dict(_forecast())], replace=True)
    assert service.cache.get(service._pending_key(KEY)), "the forecast was not kept"

    # 2. The fixture is stored, spelled the way the match provider spells it.
    match = _store_the_fixture(registry)
    db.flush()

    # 3. Re-attaching binds it, and the provider is never reached - any call raises.
    report = service.reattach_pending(KEY)
    assert report["attached"] == 1, report
    assert report["still_pending"] == 0, report

    rows = _records(db, match.id)
    assert len(rows) == 1, f"expected one forecast row, found {len(rows)}"

    # 4. The retrieval time is the provider's, not the moment we finally bound it. A forecast is
    #    evidence about a moment before kickoff, and re-stamping it would make a snapshot look
    #    newer than the reading it carries.
    stored = rows[0].fetched_at
    stored = stored.replace(tzinfo=timezone.utc) if stored.tzinfo is None else stored
    assert stored == RETRIEVED_AT, f"retrieval time was rewritten: {stored} != {RETRIEVED_AT}"

    # 5. It is out of the pending set, so a later pass does not reconsider it.
    assert not (service.cache.get(service._pending_key(KEY)) or []), "it is still pending"


def test_reattaching_twice_binds_once(db, service):
    """Idempotent: the second call has nothing to do and must not write a second row."""
    registry = MatchRegistry(db)
    service.registry = registry
    service.attach_forecast(_forecast(), KEY, registry.ensure_canonical_league(KEY).id)
    service._store_pending(KEY, [_forecast_to_dict(_forecast())], replace=True)
    match = _store_the_fixture(registry)
    db.flush()

    first = service.reattach_pending(KEY)
    second = service.reattach_pending(KEY)

    assert first["attached"] == 1, first
    assert second["attached"] == 0, second
    assert len(_records(db, match.id)) == 1, "re-attaching twice stored the forecast twice"
