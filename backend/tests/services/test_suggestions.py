"""
Suggested combinations: deterministic, honest about shortfalls, and never a provider call.

Requires PostgreSQL (docker-compose test database); skipped when unreachable. Every provider entry
point is closed for the whole module, so a suggestion that reached for a provider fails the test.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.predictions import League, Match, MatchStatus, Team
from app.models.provider_data import ProviderForecastRecord
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.http import ProviderHttpClient
from app.services.providers.sample import SampleDataProvider, SampleForecastProvider
from app.services.suggestions import suggest
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def load(name: str) -> dict:
    with open(os.path.join(FIXTURES, f"gameforecast_event_{name}.json"), encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def engine():
    try:
        eng = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
        with eng.connect() as conn:
            for schema in ("users", "predictions", "ml_models", "analytics", "audit"):
                conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
            conn.commit()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL test database not reachable: {exc}")
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection, join_transaction_mode="create_savepoint")()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def closed_providers(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))

    def refuse(name):
        def _refuse(*args, **kwargs):
            raise AssertionError(f"a provider call was made ({name}); suggestions read stored forecasts only")
        return _refuse
    monkeypatch.setattr(ProviderHttpClient, "get_json", refuse("http get_json"))
    monkeypatch.setattr(SampleForecastProvider, "get_forecasts", refuse("SampleForecastProvider.get_forecasts"))
    for method in ("get_fixtures", "get_live", "get_results"):
        monkeypatch.setattr(SampleDataProvider, method, refuse(f"SampleDataProvider.{method}"))


def _league(db, key="uefa_nations_league") -> League:
    league = MatchRegistry(db).ensure_canonical_league(key)
    db.flush()
    return league


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, short_name=name[:3].upper(), country=None, is_active=True)
    db.add(team)
    db.flush()
    return team


def _fixture(db, league: League, home: str, away: str, kickoff: datetime, payload: dict = None,
             status=MatchStatus.SCHEDULED, fetched_at: datetime = None, home_draw_away=None) -> Match:
    match = Match(id=uuid.uuid4(), home_team_id=_team(db, home).id, away_team_id=_team(db, away).id, league_id=league.id,
                  match_date=kickoff.replace(tzinfo=None), status=status, external_api_id=f"ls-{uuid.uuid4().hex[:8]}",
                  external_api_source="livescore", match_metadata={})
    db.add(match)
    db.flush()
    if payload is not None:
        payload = json.loads(json.dumps(payload))
        payload["id"] = f"{payload['id']}-{uuid.uuid4().hex[:6]}"
        if home_draw_away:
            payload["predictions"][0]["match_result"] = dict(zip(("home", "draw", "away"), home_draw_away))
        fetched = (fetched_at or NOW - timedelta(hours=3)).replace(tzinfo=None)
        db.add(ProviderForecastRecord(id=uuid.uuid4(), match_id=match.id, provider="gameforecast",
                                      external_event_id=payload["id"], match_confidence="exact", matched_by="provider_id",
                                      model_run_at=fetched, fetched_at=fetched, raw_payload=payload))
        db.flush()
    return match


def test_suggestions_are_deterministic_disjoint_and_explained(db):
    league = _league(db)
    base = load("bulgaria_luxembourg")
    # Eight fixtures whose best selection is the 1X2 favourite at known probabilities
    for index, home_pct in enumerate((90, 85, 80, 75, 70, 65, 62, 61)):
        _fixture(db, league, f"Home{index}", f"Away{index}", NOW + timedelta(days=1, hours=index), base,
                 home_draw_away=(home_pct, (100 - home_pct) // 2, 100 - home_pct - (100 - home_pct) // 2))

    first = suggest(db, now=NOW, legs=3, min_probability=0.6, markets=["match_result"])
    second = suggest(db, now=NOW, legs=3, min_probability=0.6, markets=["match_result"])
    assert first == second, "the same stored data and arguments produce the same suggestions"
    assert first["pool"]["qualifying"] == 8
    assert len(first["combinations"]) == 2
    top = first["combinations"][0]
    assert [leg["why"]["probability"] for leg in top["legs"]] == [pytest.approx(0.90), pytest.approx(0.85), pytest.approx(0.80)]
    assert [leg["why"]["rank"] for leg in top["legs"]] == [1, 2, 3]
    assert top["combined_probability"]["value"] == pytest.approx(0.90 * 0.85 * 0.80, abs=1e-6)
    assert "assuming the matches are independent" in top["combined_probability"]["basis"]
    assert "not a calibrated prediction" in top["combined_probability"]["basis"]
    ids_first = {leg["match"]["id"] for leg in top["legs"]}
    ids_second = {leg["match"]["id"] for leg in first["combinations"][1]["legs"]}
    assert not ids_first & ids_second, "alternatives share no fixture"
    assert first["shortfall"] is not None and "2 further qualifying" in first["shortfall"]
    leg = top["legs"][0]
    assert leg["why"]["forecast"]["age_hours"] == pytest.approx(3.0)
    assert leg["why"]["settlement"]["capable"] is True
    assert leg["why"]["provider_odds"]["value"] == 2.3
    assert top["combined_odds"]["value"] == pytest.approx(2.3 ** 3, abs=1e-3)
    assert first["rules"]["source"].startswith("stored provider forecasts only")
    for word in ("safe", "guaranteed", "sure"):
        assert word not in json.dumps(first).lower()


def test_too_few_candidates_returns_fewer_legs_and_says_why(db):
    league = _league(db)
    base = load("bulgaria_luxembourg")
    _fixture(db, league, "A", "B", NOW + timedelta(days=1), base, home_draw_away=(80, 10, 10))
    _fixture(db, league, "C", "D", NOW + timedelta(days=1), base, home_draw_away=(70, 15, 15))
    _fixture(db, league, "E", "F", NOW + timedelta(days=1), base, home_draw_away=(40, 30, 30))
    _fixture(db, league, "G", "H", NOW + timedelta(days=1), base, home_draw_away=(98, 1, 1))

    out = suggest(db, now=NOW, legs=4, min_probability=0.6, markets=["match_result"])
    assert out["pool"]["qualifying"] == 2
    assert out["pool"]["excluded"]["below_threshold"] == 1
    assert out["pool"]["excluded"]["above_ceiling"] == 1, "a 98% favourite tells a combination nothing and is left out"
    raised = suggest(db, now=NOW, legs=4, min_probability=0.6, max_probability=1.0, markets=["match_result"])
    assert raised["pool"]["qualifying"] == 3
    assert len(out["combinations"]) == 1 and len(out["combinations"][0]["legs"]) == 2
    assert "only 2 fixtures qualify for 4 legs" in out["shortfall"]

    nothing = suggest(db, now=NOW, legs=2, min_probability=0.95, markets=["match_result"])
    assert nothing["combinations"] == []
    assert "no fixture in the window" in nothing["shortfall"]


def test_started_stale_and_unforecast_fixtures_are_excluded_and_counted(db):
    league = _league(db)
    base = load("bulgaria_luxembourg")
    _fixture(db, league, "Started", "X", NOW - timedelta(hours=1), base, home_draw_away=(90, 5, 5))
    _fixture(db, league, "Stale", "Y", NOW + timedelta(days=1), base, home_draw_away=(90, 5, 5),
             fetched_at=NOW - timedelta(hours=100))
    _fixture(db, league, "Bare", "Z", NOW + timedelta(days=1))
    _fixture(db, league, "Fine", "W", NOW + timedelta(days=1), base, home_draw_away=(90, 5, 5))
    _fixture(db, league, "Far", "V", NOW + timedelta(days=20), base, home_draw_away=(90, 5, 5))

    out = suggest(db, now=NOW, legs=2, min_probability=0.6, markets=["match_result"])
    names = [leg["match"]["home"]["name"] for c in out["combinations"] for leg in c["legs"]]
    assert names == ["Fine"]
    assert out["pool"]["excluded"]["stale"] == 1
    assert out["pool"]["excluded"]["no_forecast"] == 1
    assert out["pool"]["fixtures_in_window"] == 3, "the started fixture is outside the window; the far one is beyond 7 days"

    with_stale = suggest(db, now=NOW, legs=2, min_probability=0.6, markets=["match_result"], include_stale=True)
    assert {leg["match"]["home"]["name"] for c in with_stale["combinations"] for leg in c["legs"]} == {"Fine", "Stale"}
    assert any(leg["why"]["forecast"]["state"] == "stale" for c in with_stale["combinations"] for leg in c["legs"])


def test_market_competition_window_and_odds_filters(db):
    nations = _league(db, "uefa_nations_league")
    friendlies = _league(db, "national_teams_friendlies")
    base = load("bulgaria_luxembourg")
    nl = _fixture(db, nations, "NL", "A", NOW + timedelta(days=1), base, home_draw_away=(45, 30, 25))
    _fixture(db, friendlies, "FR", "B", NOW + timedelta(days=3), base, home_draw_away=(45, 30, 25))

    totals_only = suggest(db, now=NOW, legs=2, min_probability=0.5, markets=["total_goals"])
    picks = {leg["selection"]["selection_id"] for c in totals_only["combinations"] for leg in c["legs"]}
    assert picks == {"total_goals:over@0.5"}, "the 0.5 line is the best-supported totals selection in this payload"

    competition = suggest(db, now=NOW, legs=2, min_probability=0.5, competition_ids=[nl.league_id])
    assert {leg["match"]["home"]["name"] for c in competition["combinations"] for leg in c["legs"]} == {"NL"}

    window = suggest(db, now=NOW, legs=2, min_probability=0.5, kickoff_from=NOW + timedelta(days=2))
    assert {leg["match"]["home"]["name"] for c in window["combinations"] for leg in c["legs"]} == {"FR"}

    # The draw is priced 3.0 and the away win 3.4: a range that starts above 3.0 leaves only the away win.
    priced = suggest(db, now=NOW, legs=2, min_probability=0.2, markets=["match_result"], odds_min=3.2, odds_max=3.5)
    picks = {leg["selection"]["selection_id"] for c in priced["combinations"] for leg in c["legs"]}
    assert picks == {"match_result:away"}, "only the provider's 1X2 prices exist, so an odds range selects among them"
    assert all(leg["why"]["provider_odds"]["value"] == 3.4 for c in priced["combinations"] for leg in c["legs"])

    too_narrow = suggest(db, now=NOW, legs=2, min_probability=0.2, markets=["match_result"], odds_min=50.0)
    assert too_narrow["pool"]["excluded"]["odds_filter"] == 2


def test_untrackable_markets_are_not_suggested_unless_asked_for(db):
    league = _league(db)
    payload = json.loads(json.dumps(load("bulgaria_luxembourg")))
    # Make "team to score first: home" the single highest probability in the payload
    payload["predictions"][0]["team_to_score_first"] = {"home": 92, "away": 6, "neither": 2}
    _fixture(db, league, "A", "B", NOW + timedelta(days=1), payload)
    default = suggest(db, now=NOW, legs=2, min_probability=0.5)
    picks = {leg["selection"]["market_id"] for c in default["combinations"] for leg in c["legs"]}
    assert "team_to_score_first" not in picks
    asked = suggest(db, now=NOW, legs=2, min_probability=0.5, markets=["team_to_score_first"], settleable_only=False)
    picks = {leg["selection"]["market_id"] for c in asked["combinations"] for leg in c["legs"]}
    assert picks == {"team_to_score_first"}
    assert all(leg["why"]["settlement"]["capable"] is False for c in asked["combinations"] for leg in c["legs"])
