"""
Database-backed tests for the Phase 1 provider layer.

Covers: provider switching without losing expert predictions, identical ids across providers,
rescheduling, ambiguous fixtures (never attach a forecast), forecast sync + freshness, and the public
endpoints end to end with the sample provider.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.predictions import Match, Prediction, PredictionSource, PredictionStatus
from app.models.provider_data import ProviderForecastRecord
from app.models.users import AccountStatus, User, UserType
from app.schemas.predictions import ExpertPredictionCreate
from app.services.expert_prediction import ExpertPredictionService
from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService
from app.services.match_registry import MatchRegistry
from app.services.providers.base import ProviderForecast
from app.services.providers.sample import SampleDataProvider, SampleForecastProvider
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")
NOW = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
DAY = NOW.date() + timedelta(days=2)
KEYS = ["premier_league"]


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
def redis():
    return FakeRedis()


@pytest.fixture
def sample_settings(monkeypatch, redis):
    monkeypatch.setattr(settings, "DATA_PROVIDER", "sample")
    monkeypatch.setattr(settings, "DATA_PROVIDER_FALLBACKS", "")
    monkeypatch.setattr(settings, "PREDICTION_PROVIDER", "sample")
    monkeypatch.setattr(settings, "COVERED_COMPETITIONS", "premier_league,la_liga")
    # Coverage is two settings, so pinning one of them pins half the answer. The national-team
    # setting ships as `active`, which adds 29 competitions to everything `covered_keys` returns;
    # these tests are about a provider switch over a known two-competition set, so both halves are
    # named here rather than one being left to the shipped default.
    monkeypatch.setattr(settings, "COVERED_NATIONAL_TEAM_COMPETITIONS", "")
    # every service gets the same in-memory cache; nothing leaks between tests or into the real Redis
    monkeypatch.setattr("app.services.match_data_service.MatchCache", lambda client=None: MatchCache(client=redis))
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))
    return redis


@pytest.fixture
def client(db, sample_settings):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ----------------------------------------------------------------------------- helpers
def _expert(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"expert-{suffix}@test.local", username=f"expert_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.EXPERT, account_status=AccountStatus.ACTIVE,
                email_verified=True)
    db.add(user)
    db.flush()
    return user


def _publish(db, match: Match, user: User) -> Prediction:
    prediction = Prediction(id=uuid.uuid4(), match_id=match.id, source=PredictionSource.EXPERT_MANUAL, created_by=user.id,
                            home_win_prob=Decimal("0.5"), draw_prob=Decimal("0.3"), away_win_prob=Decimal("0.2"),
                            confidence_score=Decimal("0.8"), status=PredictionStatus.PUBLISHED,
                            published_at=datetime.utcnow(), priority_level=100, reasoning="expert view")
    db.add(prediction)
    db.flush()
    return prediction


def other_provider(fixture, ext_id, **changes):
    """The same real-world fixture as seen by a different provider (different ids everywhere)."""
    fields = dict(
        provider="other", external_id=ext_id,
        competition=replace(fixture.competition, provider="other", external_id="other-pl"),
        home=replace(fixture.home, provider="other", external_id=f"other-{fixture.home.external_id}"),
        away=replace(fixture.away, provider="other", external_id=f"other-{fixture.away.external_id}"),
    )
    fields.update(changes)
    return replace(fixture, **fields)


def forecast(fixture, event_id="E1", **changes):
    base = dict(provider="gameforecast", external_event_id=event_id, home_name=fixture.home.name, away_name=fixture.away.name,
                kickoff_utc=fixture.kickoff_utc, competition_name="Premier League", competition_key="premier_league",
                home_prob=0.5, draw_prob=0.3, away_prob=0.2)
    base.update(changes)
    return ProviderForecast(**base)


def sample_day(db, keys=KEYS):
    registry = MatchRegistry(db)
    fixtures = SampleDataProvider(now=NOW).get_fixtures(DAY, keys)
    matches = [registry.upsert_fixture(f) for f in fixtures]
    db.flush()
    return registry, fixtures, matches


# ----------------------------------------------------------------------------- registry / switching
def test_switching_provider_keeps_expert_prediction_on_the_same_match(db):
    registry, fixtures, matches = sample_day(db)
    user = _expert(db)
    prediction = _publish(db, matches[0], user)

    same_fixture_other_provider = other_provider(fixtures[0], "B-1")
    assert registry.upsert_fixture(same_fixture_other_provider).id == matches[0].id

    league_id = matches[0].league_id
    assert db.query(Match).filter(Match.league_id == league_id).count() == len(fixtures)
    assert registry.resolve_match_id("B-1") == matches[0].id
    assert registry.resolve_match_id("other:B-1") == matches[0].id
    assert registry.resolve_match_id(fixtures[0].external_id) == matches[0].id
    assert registry.resolve_match_id(str(matches[0].id)) == matches[0].id
    assert registry.resolve_match_id("does-not-exist") is None
    assert db.query(Prediction).filter(Prediction.match_id == matches[0].id).one().id == prediction.id
    refs = {r.provider: r.external_id for r in registry.refs_for("match", matches[0].id)}
    assert refs == {"sample": fixtures[0].external_id, "other": "B-1"}


def test_identical_id_at_another_provider_is_a_different_fixture(db, monkeypatch):
    registry, fixtures, matches = sample_day(db)
    foreign = other_provider(fixtures[1], fixtures[0].external_id,
                             home=replace(fixtures[1].home, provider="other", external_id="x1", name="Brentford"),
                             away=replace(fixtures[1].away, provider="other", external_id="x2", name="Fulham"))
    created = registry.upsert_fixture(foreign)
    assert created.id not in {m.id for m in matches}
    # a bare id that exists at two providers for two different fixtures is only resolved for the active provider
    monkeypatch.setattr(settings, "DATA_PROVIDER", "sample")
    assert registry.resolve_match_id(fixtures[0].external_id) == matches[0].id
    monkeypatch.setattr(settings, "DATA_PROVIDER", "other")
    assert registry.resolve_match_id(fixtures[0].external_id) == created.id
    monkeypatch.setattr(settings, "DATA_PROVIDER", "livescore")
    assert registry.resolve_match_id(fixtures[0].external_id) is None
    assert registry.resolve_match_id(f"sample:{fixtures[0].external_id}") == matches[0].id


def test_rescheduled_fixture_follows_the_provider_ref(db):
    registry, fixtures, matches = sample_day(db)
    moved = replace(fixtures[0], kickoff_utc=fixtures[0].kickoff_utc + timedelta(hours=26))
    assert registry.upsert_fixture(moved).id == matches[0].id
    db.flush()
    assert db.query(Match).get(matches[0].id).match_date == moved.kickoff_utc.replace(tzinfo=None)


def test_forecast_is_never_attached_to_an_uncertain_match(db):
    registry, fixtures, matches = sample_day(db)
    league = registry.ensure_canonical_league("premier_league")
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()), now=NOW, keys=KEYS)

    # kickoff 26 h away from the stored fixture -> "rescheduled?" -> ambiguous, nothing stored
    off = forecast(fixtures[0], kickoff_utc=fixtures[0].kickoff_utc + timedelta(hours=26))
    assert service.attach_forecast(off, "premier_league", league.id)["result"] == "ambiguous"
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == matches[0].id).count() == 0

    # home/away swapped -> ambiguous
    swapped = forecast(fixtures[0], home_name=fixtures[0].away.name, away_name=fixtures[0].home.name)
    assert service.attach_forecast(swapped, "premier_league", league.id)["result"] == "ambiguous"

    # unknown teams -> unmatched
    unknown = forecast(fixtures[0], home_name="Nowhere FC", away_name="Elsewhere United")
    assert service.attach_forecast(unknown, "premier_league", league.id)["result"] == "unmatched"

    # no markets at all -> ignored
    empty = forecast(fixtures[0], home_prob=None, draw_prob=None, away_prob=None)
    assert service.attach_forecast(empty, "premier_league", league.id)["result"] == "without_markets"

    # exact kickoff -> attached with the provider event id recorded
    out = service.attach_forecast(forecast(fixtures[0]), "premier_league", league.id)
    assert out["result"] == "attached" and out["match_id"] == str(matches[0].id)
    record = service.forecast_for_match(matches[0], provider_name="gameforecast")
    assert record.match_confidence == "exact" and record.matched_by == "name_kickoff"

    # afterwards the provider event id identifies the match even when the kickoff moves again
    later = forecast(fixtures[0], kickoff_utc=fixtures[0].kickoff_utc + timedelta(hours=30), home_prob=0.6, draw_prob=0.2, away_prob=0.2)
    assert service.attach_forecast(later, "premier_league", league.id)["result"] == "attached"
    db.flush()
    record = service.forecast_for_match(matches[0], provider_name="gameforecast")
    assert float(record.home_win_prob) == 0.6 and record.matched_by == "provider_id"
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == matches[0].id).count() == 1


def test_two_candidate_matches_make_a_forecast_ambiguous(db):
    registry, fixtures, matches = sample_day(db)
    league = registry.ensure_canonical_league("premier_league")
    # a second match with the same teams 40 h later (outside every window) -> new record ...
    twin = replace(fixtures[0], external_id="twin", kickoff_utc=fixtures[0].kickoff_utc + timedelta(hours=40))
    twin_match = registry.upsert_fixture(twin)
    assert twin_match.id != matches[0].id
    # ... which its provider then moves to one hour after the original: two candidates in the window
    registry.upsert_fixture(replace(twin, kickoff_utc=fixtures[0].kickoff_utc + timedelta(hours=1)))
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()), now=NOW, keys=KEYS)
    out = service.attach_forecast(forecast(fixtures[0]), "premier_league", league.id)
    assert out["result"] == "ambiguous" and set(out["candidates"]) == {str(matches[0].id), str(twin_match.id)}


def test_sync_and_forecast_freshness_with_sample_provider(db):
    cache = MatchCache(client=FakeRedis())
    data = MatchDataService(db, providers=[SampleDataProvider(now=NOW)], cache=cache, now=NOW, keys=KEYS)
    matches, meta = data.matches_for_day(DAY)
    assert meta.provider == "sample" and meta.source == "provider" and len(matches) == 2
    _, meta = data.matches_for_day(DAY)
    assert meta.source == "cache"

    # fixture-first sync is covered by test_ensure_synced_loads_fixtures_before_attaching; here only DAY's fixtures exist
    forecasts = ForecastService(db, provider=SampleForecastProvider(), cache=cache, now=NOW, keys=KEYS, sync_fixtures=False)
    report = forecasts.ensure_synced(days_ahead=3)
    stats = report["competitions"]["premier_league"]
    # Both of DAY's fixtures get their forecast. What happens to the rest of the window is the
    # point of the two assertions below, and it depends on the calendar: the sample provider
    # rotates a small set of teams on a three-day cycle, so on some dates the SAME pairing appears
    # again inside the days_ahead window. Those repeats are refused - "teams match but kickoff is
    # 43 h away" - rather than attached to DAY's match, which is the rule this whole codebase turns
    # on: refuse, never guess. An earlier version asserted ambiguous == 0, which quietly encoded
    # "today is not one of those dates" and failed the moment the clock rolled onto one.
    assert stats["attached"] == 2
    assert stats["fetched"] == (stats["attached"] + stats["ambiguous"]
                                + stats["unmatched"] + stats["without_markets"]), \
        "every fetched forecast is accounted for in exactly one bucket"
    for entry in stats["details"]:
        assert entry["result"] != "attached", "the details list only ever holds non-attachments"
        if entry["result"] == "ambiguous":
            # Refused for the right reason: a name match at the wrong kickoff, never a silent grab.
            assert "kickoff" in entry["reason"]
    for match in matches:
        record = forecasts.forecast_for_match(match)
        assert record is not None and record.provider == "sample"
        assert forecasts.freshness(record, match)["state"] == "available"
    assert forecasts.ensure_synced(days_ahead=3)["skipped"] == ["premier_league"]
    assert forecasts.ensure_synced(days_ahead=3, force=True)["competitions"]["premier_league"]["attached"] == 2


def test_forecasts_fetched_before_fixtures_are_attached_later_without_new_requests(db):
    class CountingForecastProvider(SampleForecastProvider):
        calls = 0

        def get_forecasts(self, key, date_from, date_to):
            CountingForecastProvider.calls += 1
            return super().get_forecasts(key, date_from, date_to)

    cache = MatchCache(client=FakeRedis())
    provider = CountingForecastProvider()
    # 1. forecasts arrive while no fixture rows exist (fixture sync disabled to simulate the race)
    service = ForecastService(db, provider=provider, cache=cache, now=NOW, keys=KEYS, sync_fixtures=False)
    first = service.ensure_synced(days_ahead=3)
    stats = first["competitions"]["premier_league"]
    assert stats["attached"] == 0 and stats["unmatched"] == stats["fetched"] > 0
    # 2. fixtures appear afterwards; the next (interval-gated) call attaches the pending forecasts for free
    data = MatchDataService(db, providers=[SampleDataProvider(now=NOW)], cache=cache, now=NOW, keys=KEYS)
    matches, _ = data.matches_for_day(DAY)
    second = service.ensure_synced(days_ahead=3)
    assert second["skipped"] == ["premier_league"]
    assert second["retried"]["premier_league"]["attached"] == 2
    assert CountingForecastProvider.calls == 1
    for match in matches:
        assert service.forecast_for_match(match) is not None


def test_pending_forecasts_are_retried_while_the_provider_is_paused(db):
    cache = MatchCache(client=FakeRedis())
    service = ForecastService(db, provider=SampleForecastProvider(), cache=cache, now=NOW, keys=KEYS, sync_fixtures=False)
    first = service.ensure_synced(days_ahead=3)
    assert first["competitions"]["premier_league"]["unmatched"] > 0  # no fixtures yet
    cache.set("forecast:cooldown:sample", {"reason": "quota"}, ttl=3600, stale_ttl=3600)
    data = MatchDataService(db, providers=[SampleDataProvider(now=NOW)], cache=cache, now=NOW, keys=KEYS)
    matches, _ = data.matches_for_day(DAY)
    paused = service.ensure_synced(days_ahead=3)
    assert paused["error"].startswith("skipped (recent failure") and paused["retried"]["premier_league"]["attached"] == 2
    assert all(service.forecast_for_match(m) is not None for m in matches)


def test_ensure_synced_loads_fixtures_before_attaching(db):
    cache = MatchCache(client=FakeRedis())
    fixtures = MatchDataService(db, providers=[SampleDataProvider(now=NOW)], cache=cache, now=NOW, keys=KEYS)
    service = ForecastService(db, provider=SampleForecastProvider(), cache=cache, now=NOW, keys=KEYS, fixtures=fixtures)
    report = service.ensure_synced(days_ahead=3)
    stats = report["competitions"]["premier_league"]
    assert stats["unmatched"] == 0 and stats["attached"] == stats["fetched"] > 0
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    assert db.query(Match).filter(Match.league_id == league.id).count() >= stats["attached"]


def test_expert_manual_prediction_resolves_provider_fixture_id(db, monkeypatch):
    monkeypatch.setattr(settings, "DATA_PROVIDER", "sample")
    registry, fixtures, matches = sample_day(db)
    user = _expert(db)
    payload = ExpertPredictionCreate(match_id=fixtures[1].external_id, home_win_prob=0.4, draw_prob=0.3, away_win_prob=0.3,
                                     confidence_score=0.7, reasoning="Resolved through the registry")
    prediction = ExpertPredictionService(db).create_manual_prediction(payload, user)
    assert prediction.match_id == matches[1].id
    assert prediction.status == PredictionStatus.PUBLISHED and prediction.published_at is not None  # experts publish directly
    monkeypatch.setattr(settings, "EXPERT_DIRECT_PUBLISH", False)
    pending = ExpertPredictionService(db).create_manual_prediction(payload, user)
    assert pending.status == PredictionStatus.PENDING and pending.published_at is None
    assert db.query(Match).filter(Match.league_id == matches[0].league_id).count() == len(fixtures)  # no placeholder row


def test_expert_without_profile_can_publish_directly(db, monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from app.core.deps import get_current_verified_expert_user
    from app.models.users import ExpertProfile

    user = _expert(db)
    assert db.query(ExpertProfile).filter(ExpertProfile.user_id == user.id).first() is None
    monkeypatch.setattr(settings, "EXPERT_DIRECT_PUBLISH", True)
    assert asyncio.run(get_current_verified_expert_user(current_user=user, db=db)) is user
    profile = db.query(ExpertProfile).filter(ExpertProfile.user_id == user.id).one()
    assert profile.is_verified is True

    # review workflow restored: an unverified profile is blocked again
    monkeypatch.setattr(settings, "EXPERT_DIRECT_PUBLISH", False)
    profile.is_verified = False
    db.flush()
    db.refresh(user)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_verified_expert_user(current_user=user, db=db))
    assert exc.value.status_code == 403


# ----------------------------------------------------------------------------- endpoints
def test_matches_endpoint_serves_sample_provider_with_forecasts_and_expert_predictions(client, db):
    response = client.get(f"/api/v1/matches?date={DAY.isoformat()}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "sample" and body["source"] == "provider" and body["stale"] is False
    assert len(body["matches"]) == 4  # two competitions x two fixtures
    first = body["matches"][0]
    assert first["home"]["name"] and first["kickoff_utc"].endswith("Z") and first["status"] == "scheduled"
    assert first["competition"]["key"] in ("premier_league", "la_liga")
    assert first["expert_prediction"] is None
    assert first["forecast"]["provider"] == "sample" and first["forecast_state"] == "available"
    assert first["forecast"]["markets_available"] == {"match_result": True, "btts": True, "over_under_25": True,
                                                      "over_under_35": False, "exact_score": False}
    assert first["forecast"]["total_goals_over_35_prob"] is None and first["forecast"]["confidence"] is None

    user = _expert(db)
    match = db.query(Match).get(uuid.UUID(first["id"]))
    _publish(db, match, user)
    again = client.get(f"/api/v1/matches?date={DAY.isoformat()}").json()
    expert = next(m for m in again["matches"] if m["id"] == first["id"])["expert_prediction"]
    assert expert["source"] == "expert_manual" and expert["home_win_prob"] == 0.5

    detail = client.get(f"/api/v1/matches/{first['id']}").json()
    assert detail["id"] == first["id"] and detail["expert_predictions"][0]["source"] == "expert_manual"
    assert {r["provider"] for r in detail["provider_refs"]} == {"sample"}
    by_provider_id = client.get(f"/api/v1/matches/{first['external_id'].split(':', 1)[1]}").json()
    assert by_provider_id["id"] == first["id"]
    assert client.get("/api/v1/matches/does-not-exist").status_code == 404
    assert client.get("/api/v1/matches?date=20-09-2026").status_code == 422

    legacy = client.get(f"/api/v1/predictions/published/by-match/{first['external_id'].split(':', 1)[1]}")
    assert legacy.status_code == 200 and legacy.json()["home_win_prob"] == 0.5

    live = client.get("/api/v1/matches/live")
    assert live.status_code == 200 and all(m["status"] in ("live", "halftime") for m in live.json()["matches"])


def test_league_team_and_status_endpoints(client):
    leagues = client.get("/api/v1/leagues").json()
    assert leagues["provider"] == "sample" and [c["key"] for c in leagues["competitions"]] == ["premier_league", "la_liga"]
    league_id = leagues["competitions"][0]["id"]
    assert client.get(f"/api/v1/leagues/{league_id}").json()["key"] == "premier_league"
    standings = client.get(f"/api/v1/leagues/{league_id}/standings").json()
    assert len(standings["standings"]) == 6 and standings["standings"][0]["position"] == 1
    calendar = client.get(f"/api/v1/leagues/{league_id}/matches?days_ahead=3&days_back=0").json()
    assert calendar["provider"] == "sample" and len(calendar["matches"]) >= 2
    team = calendar["matches"][0]["home"]
    search = client.get(f"/api/v1/teams/search?q={team['name'][:5]}").json()
    assert any(t["id"] == team["id"] for t in search["teams"])
    team_page = client.get(f"/api/v1/teams/{team['id']}").json()
    assert team_page["team"]["name"] == team["name"] and team_page["upcoming"]
    assert client.get("/api/v1/teams/not-a-uuid").status_code == 404
    status = client.get("/api/v1/data-providers/status").json()
    assert status["active_provider"] == "sample" and status["chain"][0]["name"] == "sample"
    assert status["forecasts"]["active_provider"] == "sample" and status["covered_competitions"] == ["premier_league", "la_liga"]
    # what each scheduler task sent, per pass and in total, is published beside its other state
    for task in status["scheduler"]["tasks"].values():
        assert {"last_requests_sent", "requests_sent_total"} <= set(task)


def test_unconfigured_primary_without_fallback_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "DATA_PROVIDER", "livescore")
    monkeypatch.setattr(settings, "LIVESCORE_API_KEY", "")
    monkeypatch.setattr(settings, "LIVESCORE_API_SECRET", "")
    response = client.get(f"/api/v1/matches?date={(DAY + timedelta(days=20)).isoformat()}")
    assert response.status_code == 503
    assert "no match-data provider is configured" in str(response.json()["detail"]).lower()


# ----------------------------------------------------------------------------- forecast evidence
def test_a_changed_forecast_leaves_both_readings_in_the_history(db):
    """Updating the current row must never be the only record of what the model said before kickoff."""
    registry, fixtures, matches = sample_day(db)
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()),
                              now=NOW, keys=KEYS, sync_fixtures=False)
    league_id = matches[0].league_id

    first = forecast(fixtures[0], home_prob=0.50, draw_prob=0.30, away_prob=0.20)
    assert service.attach_forecast(first, "premier_league", league_id)["result"] == "attached"
    db.flush()

    revised = forecast(fixtures[0], home_prob=0.62, draw_prob=0.24, away_prob=0.14,
                       model_run_at=NOW + timedelta(hours=3))
    assert service.attach_forecast(revised, "premier_league", league_id)["result"] == "attached"
    db.flush()

    # one current row, two pieces of evidence
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == matches[0].id).count() == 1
    history = service.snapshots_for_match(matches[0].id, "gameforecast")
    assert [float(s.home_win_prob) for s in history] == [0.5, 0.62]
    assert float(service.forecast_for_match(matches[0], "gameforecast").home_win_prob) == 0.62


def test_refetching_an_unchanged_forecast_adds_no_new_evidence(db):
    registry, fixtures, matches = sample_day(db)
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()),
                              now=NOW, keys=KEYS, sync_fixtures=False)
    league_id = matches[0].league_id
    same = forecast(fixtures[0])

    for _ in range(3):
        service.attach_forecast(same, "premier_league", league_id)
    db.flush()
    assert len(service.snapshots_for_match(matches[0].id, "gameforecast")) == 1


def test_a_prematch_snapshot_is_marked_as_such(db):
    registry, fixtures, matches = sample_day(db)
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()),
                              now=NOW, keys=KEYS, sync_fixtures=False)
    service.attach_forecast(forecast(fixtures[0]), "premier_league", matches[0].league_id)
    db.flush()
    snapshot = service.snapshots_for_match(matches[0].id, "gameforecast")[0]
    # DAY is two days out, so this really is a prematch forecast
    assert snapshot.captured_before_kickoff is True
    assert snapshot.kickoff_at_capture == fixtures[0].kickoff_utc.replace(tzinfo=None)


def test_a_recycled_provider_event_id_does_not_move_a_forecast_to_the_wrong_match(db):
    """Provider event ids are small integers and get reused between seasons."""
    registry, fixtures, matches = sample_day(db)
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()),
                              now=NOW, keys=KEYS, sync_fixtures=False)
    league_id = matches[0].league_id
    service.attach_forecast(forecast(fixtures[0], event_id="777"), "premier_league", league_id)
    db.flush()

    # the same event id comes back naming a completely different pair of teams
    recycled = forecast(fixtures[0], event_id="777", home_name="Sporting CP", away_name="Benfica")
    outcome = service.attach_forecast(recycled, "premier_league", league_id)
    assert outcome["result"] == "ambiguous"
    assert "no longer names the same teams" in outcome["reason"]


def test_expert_predictions_survive_a_forecast_provider_change(db):
    registry, fixtures, matches = sample_day(db)
    user = _expert(db)
    prediction = _publish(db, matches[0], user)
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()),
                              now=NOW, keys=KEYS, sync_fixtures=False)
    league_id = matches[0].league_id

    service.attach_forecast(forecast(fixtures[0], event_id="G1"), "premier_league", league_id)
    other = forecast(fixtures[0], event_id="A1", home_prob=0.4, draw_prob=0.35, away_prob=0.25)
    other.provider = "api_football"
    service.attach_forecast(other, "premier_league", league_id)
    db.flush()

    # two providers, two current rows, one untouched expert prediction
    assert db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == matches[0].id).count() == 2
    kept = db.query(Prediction).filter(Prediction.match_id == matches[0].id).one()
    assert kept.id == prediction.id and kept.status == PredictionStatus.PUBLISHED
    assert float(service.forecast_for_match(matches[0], "gameforecast").home_win_prob) == 0.5
    assert float(service.forecast_for_match(matches[0], "api_football").home_win_prob) == 0.4


# ----------------------------------------------------------------------------- orientation and identity
def test_a_forecast_listed_the_other_way_round_is_refused_not_flipped(db):
    """Every probability is orientation-bound, and a reverse leg is a different match.

    Attaching a forecast listed away-first would put the away side's win probability on the home
    side, which is worse than having no forecast at all.
    """
    registry, fixtures, matches = sample_day(db)
    service = ForecastService(db, provider=SampleForecastProvider(), cache=MatchCache(client=FakeRedis()),
                              now=NOW, keys=KEYS, sync_fixtures=False)
    league_id = matches[0].league_id
    assert service.attach_forecast(forecast(fixtures[0], event_id="R1"), "premier_league", league_id)["result"] == "attached"
    db.flush()

    reversed_listing = forecast(fixtures[0], event_id="R1",
                                home_name=fixtures[0].away.name, away_name=fixtures[0].home.name,
                                home_prob=0.8, draw_prob=0.1, away_prob=0.1)
    outcome = service.attach_forecast(reversed_listing, "premier_league", league_id)
    assert outcome["result"] == "ambiguous"
    # the forecast already stored is untouched, and 0.8 never lands on the wrong side
    assert float(service.forecast_for_match(matches[0], "gameforecast").home_win_prob) == 0.5


def test_a_recycled_fixture_id_cannot_repurpose_an_existing_match(db):
    """Provider fixture ids get reused between seasons; the teams decide, not the id."""
    registry, fixtures, matches = sample_day(db)
    user = _expert(db)
    prediction = _publish(db, matches[0], user)
    original_home, original_away = matches[0].home_team_id, matches[0].away_team_id

    recycled = replace(
        fixtures[0],
        home=replace(fixtures[0].home, external_id="zz1", name="Sporting CP"),
        away=replace(fixtures[0].away, external_id="zz2", name="Benfica"),
    )
    assert registry.upsert_fixture(recycled) is None
    db.flush()

    refreshed = db.query(Match).filter(Match.id == matches[0].id).one()
    assert (refreshed.home_team_id, refreshed.away_team_id) == (original_home, original_away)
    assert db.query(Prediction).filter(Prediction.match_id == matches[0].id).one().id == prediction.id
    assert any("no longer names the same teams" in r["reason"] for r in registry.refusals)


def test_a_fixture_sent_the_other_way_round_does_not_swap_the_stored_teams(db):
    registry, fixtures, matches = sample_day(db)
    original_home, original_away = matches[0].home_team_id, matches[0].away_team_id
    flipped = replace(fixtures[0], home=fixtures[0].away, away=fixtures[0].home)

    assert registry.upsert_fixture(flipped) is None
    db.flush()
    refreshed = db.query(Match).filter(Match.id == matches[0].id).one()
    assert (refreshed.home_team_id, refreshed.away_team_id) == (original_home, original_away)
