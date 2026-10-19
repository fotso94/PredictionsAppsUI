"""
What becomes of a forecast nobody could place, against the REAL registry.

A forecast the provider gave us whose fixture could not be identified is kept, and its retrieval
time travels with it. These tests pin the two halves the retention policy keeps apart: whether a
forecast is PREMATCH EVIDENCE - decided by when it was retrieved against the kick-off, never by
when it was finally bound - and whether it is still RETAINED for a later binding, which the
service never gives up on by itself (`PENDING_RETRY_DAYS` of automatic retries, then an explicit
retention record that an operator can still attach). Settlement and suggestions are asserted
directly, because they are where prematch eligibility is enforced.

The provider is a real GameForecastProvider over a transport that raises on contact, with a real
RequestBudget: re-attaching costs nothing because it cannot cost anything, and the counters say so.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.provider_data import ProviderForecastRecord
from app.services import match_matching
from app.services.forecast_markets import envelopes_for_matches
from app.services.forecast_service import (
    PENDING_RETRY_DAYS, ForecastService, _forecast_to_dict,
)
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.base import (
    ProviderCompetition, ProviderFixture, ProviderForecast, ProviderTeam,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.gameforecast import GameForecastProvider
from app.services.settlement import prematch_snapshots
from app.services.suggestions import suggest
from tests.providers.support import FakeRedis, make_transport

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc)
#: Six hours before kick-off: the forecast is prematch evidence whenever it is bound.
RETRIEVED_BEFORE = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
#: Half an hour after kick-off: never prematch evidence, however soon it is bound.
RETRIEVED_AFTER = KICKOFF + timedelta(minutes=30)
MODEL_RUN = datetime(2026, 9, 25, 6, 0, tzinfo=timezone.utc)
KEY = "uefa_nations_league"


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


@pytest.fixture(autouse=True)
def closed_cache(monkeypatch):
    """Every ForecastService built inside the code under test (suggestions builds its own) reads an
    in-memory cache: nothing here may reach a real Redis."""
    redis = FakeRedis()
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))


def _provider_that_cannot_be_reached(redis):
    """A real GameForecastProvider whose transport raises on contact. Any request is a failure."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"a request left for the provider: {request.method} {request.url}")

    transport, recorder = make_transport(handler)
    budget = RequestBudget("gameforecast", 8, client=redis)
    provider = GameForecastProvider(api_key="rapid-key", api_host="gf.test", base_url="https://gf.test",
                                    transport=transport, budget=budget, league_overrides={},
                                    store=MatchCache(client=redis))
    return provider, recorder, budget


@pytest.fixture
def h(db):
    redis = FakeRedis()
    provider, recorder, budget = _provider_that_cannot_be_reached(redis)
    service = ForecastService(db, provider=provider, cache=MatchCache(client=redis), now=NOW,
                              keys=[KEY], sync_fixtures=False)
    service.registry = MatchRegistry(db)
    return SimpleNamespace(db=db, service=service, registry=service.registry, provider=provider,
                           recorder=recorder, budget=budget,
                           league=service.registry.ensure_canonical_league(KEY))


def _event() -> dict:
    """A real provider event, so the stored payload carries the markets the match page rebuilds."""
    with open(os.path.join(FIXTURES, "gameforecast_event_armenia_latvia.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _forecast(retrieved_at: datetime, *, home="Rep. Of Ireland", away="Kosovo",
              kickoff: datetime = KICKOFF, event="evt-27378") -> ProviderForecast:
    return ProviderForecast(
        provider="gameforecast", external_event_id=event, competition_key=KEY,
        home_name=home, away_name=away, kickoff_utc=kickoff,
        home_prob=0.38, draw_prob=0.32, away_prob=0.30, model_run_at=MODEL_RUN, fetched_at=retrieved_at,
        raw=_event())


def _store_the_fixture(registry, kickoff: datetime = KICKOFF):
    """The fixture as the match provider spells it, which is not how the forecast provider spells it."""
    return registry.upsert_fixture(ProviderFixture(
        provider="livescore", external_id=f"ls-{int(kickoff.timestamp())}",
        competition=ProviderCompetition(provider="livescore", external_id="350",
                                        name="UEFA Nations League", key=KEY),
        home=ProviderTeam(provider="livescore", external_id="ls-roi", name="Republic of Ireland"),
        away=ProviderTeam(provider="livescore", external_id="ls-kos", name="Kosovo"),
        kickoff_utc=kickoff, status="scheduled"))


def _keep(h, forecast: ProviderForecast, now: datetime) -> None:
    """The state a real unmatched forecast is left in: paid for, refused, held pending."""
    h.service._now = now
    outcome = h.service.attach_forecast(forecast, KEY, h.league.id)
    assert outcome["result"] == "unmatched", outcome
    h.service._store_pending(KEY, [_forecast_to_dict(forecast)], replace=True)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _nothing_was_spent(h) -> None:
    assert h.recorder.requests == [], "a request reached the transport"
    assert h.budget.used_today() == 0 and h.budget.granted == 0, "the budget let a request out"


def _records(db, match_id):
    return db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == match_id).all()


# ------------------------------------------------------------------ retrieved before kick-off: evidence
def test_a_forecast_retrieved_before_kickoff_binds_to_a_fixture_that_arrives_days_after_the_match(h):
    _keep(h, _forecast(RETRIEVED_BEFORE), now=RETRIEVED_BEFORE)

    # Three days after the match - far beyond the 150 minutes of the live window - the fixture
    # finally arrives from the match provider.
    h.service._now = KICKOFF + timedelta(days=3)
    match = _store_the_fixture(h.registry)
    h.db.flush()

    report = h.service.reattach_pending(KEY)

    assert (report["attached"], report["still_pending"], report["retained"]) == (1, 0, 0), report
    [snapshot] = h.service.snapshots_for_match(match.id, "gameforecast")
    assert snapshot.captured_before_kickoff is True
    assert _aware(snapshot.first_fetched_at) == RETRIEVED_BEFORE, "the retrieval time, not the binding time"
    assert _aware(snapshot.last_fetched_at) == RETRIEVED_BEFORE
    assert _aware(snapshot.model_run_at) == MODEL_RUN
    [record] = _records(h.db, match.id)
    assert _aware(record.fetched_at) == RETRIEVED_BEFORE
    # Settlement scores it: it is the last snapshot captured before kick-off.
    chosen = prematch_snapshots(h.db, [match.id])
    assert {k: v.id for k, v in chosen.items()} == {(match.id, "gameforecast"): snapshot.id}
    assert not (h.service.cache.get(h.service._pending_key(KEY)) or [])
    _nothing_was_spent(h)


def test_an_alias_correction_binds_a_kept_forecast_long_after_kickoff(h, monkeypatch):
    """The provider's spelling and the fixture's share no alias, so the forecast waits; the alias
    is added weeks later, and the kept forecast binds for nothing - still prematch evidence."""
    match = _store_the_fixture(h.registry)
    h.db.flush()
    assert not match_matching.team_names_match("Hibernia", "Republic of Ireland"), "precondition"
    _keep(h, _forecast(RETRIEVED_BEFORE, home="Hibernia"), now=RETRIEVED_BEFORE)

    h.service._now = KICKOFF + timedelta(days=5)
    before = h.service.reattach_pending(KEY)
    assert (before["attached"], before["still_pending"]) == (0, 1), before

    monkeypatch.setitem(match_matching._ALIASES, match_matching.normalize_team_name("Hibernia"),
                        match_matching.normalize_team_name("Republic of Ireland"))
    assert match_matching.team_names_match("Hibernia", "Republic of Ireland")

    after = h.service.reattach_pending(KEY)

    assert (after["attached"], after["still_pending"]) == (1, 0), after
    [snapshot] = h.service.snapshots_for_match(match.id, "gameforecast")
    assert snapshot.captured_before_kickoff is True
    assert _aware(snapshot.first_fetched_at) == RETRIEVED_BEFORE
    _nothing_was_spent(h)


def test_repeated_attachment_of_the_same_payload_creates_no_duplicate_snapshot(h):
    _keep(h, _forecast(RETRIEVED_BEFORE), now=RETRIEVED_BEFORE)
    h.service._now = KICKOFF + timedelta(days=3)
    match = _store_the_fixture(h.registry)
    h.db.flush()

    first = h.service.reattach_pending(KEY)
    second = h.service.reattach_pending(KEY)
    again = h.service.attach_forecast(_forecast(RETRIEVED_BEFORE), KEY, h.league.id)
    h.db.flush()

    assert first["attached"] == 1 and second["attached"] == 0 and again["result"] == "attached"
    assert len(h.service.snapshots_for_match(match.id, "gameforecast")) == 1
    assert len(_records(h.db, match.id)) == 1
    [snapshot] = h.service.snapshots_for_match(match.id, "gameforecast")
    assert _aware(snapshot.last_fetched_at) == RETRIEVED_BEFORE, "seen again, and still the one retrieval"
    _nothing_was_spent(h)


# ------------------------------------------------------------------ retrieved after kick-off: never evidence
def test_a_forecast_retrieved_after_kickoff_never_becomes_prematch_evidence(h):
    match = _store_the_fixture(h.registry)
    h.db.flush()
    h.service._now = RETRIEVED_AFTER + timedelta(minutes=5)

    outcome = h.service.attach_forecast(_forecast(RETRIEVED_AFTER), KEY, h.league.id)
    h.db.flush()

    assert outcome["result"] == "attached", "a late forecast is still kept, for reference"
    [snapshot] = h.service.snapshots_for_match(match.id, "gameforecast")
    assert snapshot.captured_before_kickoff is False
    # Scoring: `prematch_snapshots` is the filter settlement scores through, and it refuses it.
    assert prematch_snapshots(h.db, [match.id]) == {}
    # The match page says what it is.
    envelope = envelopes_for_matches(h.db, [match], h.service, now=h.service.now)[match.id]
    assert envelope["forecast"]["captured_before_kickoff"] is False
    # Suggestions never consider a fixture that has kicked off, and a forecast retrieved after
    # kick-off has no moment before it at which it existed.
    result = suggest(h.db, now=h.service.now, competition_ids=[h.league.id])
    assert result["pool"]["fixtures_in_window"] == 0 and result["combinations"] == []
    _nothing_was_spent(h)


# ------------------------------------------------------------------ past the retry window: retained
def test_a_forecast_past_the_retry_window_is_retained_with_its_payload_intact_and_still_attachable(h):
    old_kickoff = NOW - timedelta(days=PENDING_RETRY_DAYS + 10)
    retrieved = old_kickoff - timedelta(hours=6)
    forecast = _forecast(retrieved, kickoff=old_kickoff, event="evt-old")
    _keep(h, forecast, now=retrieved)
    h.service._now = NOW

    report = h.service.reattach_pending(KEY)

    assert (report["attached"], report["still_pending"], report["retained"]) == (0, 0, 1), report
    assert not (h.service.cache.get(h.service._pending_key(KEY)) or []), "no longer retried on its own"
    [kept] = h.service.retained(KEY)
    assert kept["forecast"] == _forecast_to_dict(forecast), "payload, retrieval time and run time untouched"
    assert kept["retention"]["retry"] is False
    assert f"{PENDING_RETRY_DAYS} days" in kept["retention"]["reason"]
    assert kept["retention"]["last_result"] == "unmatched"
    assert h.service.reattach_pending(KEY) == {"competitions": {}, "attached": 0, "still_pending": 0, "retained": 0}

    # The fixture's identity is sorted out at the end of the season: the explicit attempt binds it,
    # for nothing, and it is still prematch evidence.
    match = _store_the_fixture(h.registry, kickoff=old_kickoff)
    h.db.flush()
    explicit = h.service.reattach_pending(KEY, include_retained=True)

    assert (explicit["attached"], explicit["retained_attached"], explicit["retained_kept"]) == (1, 1, 0), explicit
    assert h.service.retained(KEY) == []
    [snapshot] = h.service.snapshots_for_match(match.id, "gameforecast")
    assert snapshot.captured_before_kickoff is True
    assert _aware(snapshot.first_fetched_at) == retrieved
    assert {k: v.id for k, v in prematch_snapshots(h.db, [match.id]).items()} == {(match.id, "gameforecast"): snapshot.id}
    _nothing_was_spent(h)
