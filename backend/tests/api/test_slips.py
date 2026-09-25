"""
Database-backed tests for the personal selection slips: /api/v1/me/slips.

What these lock down:
* building a slip from selections the markets endpoint serves, with the probability, snapshot and
  forecast times copied at the moment of adding;
* one selection per fixture (a duplicate or a contradicting leg on the same fixture is refused);
* nothing on a fixture that has kicked off, and a selection the forecast does not carry is refused;
* a forecast revised after the leg was added changes the CURRENT figure beside the leg, never the
  stored one;
* a recorded slip is immutable, and its history is not rewritten by editing a duplicate;
* settlement on read against stored results: won, lost, void (draw-no-bet on a draw; a postponed
  fixture), unresolved (no half-time score), and a still-pending overdue fixture;
* a slip is private to its owner: another account can neither read nor change it;
* money: an XAF stake takes no decimals, a EUR one takes two, and the potential return is a gross
  figure and a net one from a price that was actually given - never from a probability;
* NO provider request on any of these paths (every provider entry point raises if touched).

Requires PostgreSQL (docker-compose test database; see tests/api/test_favourites.py). Skipped when
unreachable.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_current_active_user
from app.core.deps import get_db as deps_get_db
from app.db.base import Base
from app.db.session import get_db as session_get_db
from app.main import app
from app.models.predictions import League, Match, MatchResult, MatchStatus, Team
from app.models.provider_data import ProviderForecastRecord, ProviderForecastSnapshot
from app.models.slips import SelectionSlip
from app.models.users import AccountStatus, User, UserType
from app.services.forecast_service import content_hash
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.gameforecast import parse_event
from app.services.providers.http import ProviderHttpClient
from app.services.providers.sample import SampleDataProvider, SampleForecastProvider
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")

NOW = datetime.now(timezone.utc).replace(microsecond=0)
KICKOFF_AHEAD = (NOW + timedelta(days=3)).replace(tzinfo=None)
KICKOFF_PASSED = (NOW - timedelta(hours=3)).replace(tzinfo=None)


def load(name: str) -> dict:
    with open(os.path.join(FIXTURES, f"gameforecast_event_{name}.json"), encoding="utf-8") as handle:
        return json.load(handle)


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
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def in_memory_cache(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr("app.services.match_data_service.MatchCache", lambda client=None: MatchCache(client=redis))
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))
    return redis


@pytest.fixture(autouse=True)
def no_provider_calls(monkeypatch):
    def refuse(name):
        def _refuse(*args, **kwargs):
            raise AssertionError(f"a provider call was made ({name}); slips read stored data only")
        return _refuse
    monkeypatch.setattr(ProviderHttpClient, "get_json", refuse("http get_json"))
    for method in ("get_fixtures", "get_live", "get_results", "get_standings", "list_competitions"):
        monkeypatch.setattr(SampleDataProvider, method, refuse(f"SampleDataProvider.{method}"))
    monkeypatch.setattr(SampleForecastProvider, "get_forecasts", refuse("SampleForecastProvider.get_forecasts"))


@pytest.fixture
def client(db):
    def override_get_db():
        yield db
    overrides = {deps_get_db: override_get_db, session_get_db: override_get_db}
    app.dependency_overrides.update(overrides)
    try:
        yield TestClient(app)
    finally:
        for dependency in overrides:
            app.dependency_overrides.pop(dependency, None)
        app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def as_user():
    def _as(user: User):
        app.dependency_overrides[get_current_active_user] = lambda: user
        return user
    yield _as
    app.dependency_overrides.pop(get_current_active_user, None)


# ----------------------------------------------------------------------------- helpers
def _user(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"slip-{suffix}@test.local", username=f"slip_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.REGULAR,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _league(db) -> League:
    league = MatchRegistry(db).ensure_canonical_league("uefa_nations_league")
    db.flush()
    return league


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, short_name=name[:3].upper(), country=None, is_active=True)
    db.add(team)
    db.flush()
    return team


def _match(db, league: League, home: str, away: str, kickoff: datetime, status=MatchStatus.SCHEDULED) -> Match:
    row = Match(id=uuid.uuid4(), home_team_id=_team(db, home).id, away_team_id=_team(db, away).id, league_id=league.id,
                match_date=kickoff, status=status, external_api_id=f"ls-{uuid.uuid4().hex[:8]}",
                external_api_source="livescore", match_metadata={})
    db.add(row)
    db.flush()
    return row


def _forecast(db, match: Match, payload: dict, fetched_at: datetime = None) -> ProviderForecastRecord:
    fetched = fetched_at or (NOW - timedelta(hours=2)).replace(tzinfo=None)
    parsed = parse_event(payload)
    record = ProviderForecastRecord(
        id=uuid.uuid4(), match_id=match.id, provider="gameforecast", external_event_id=str(payload["id"]),
        home_win_prob=parsed.home_prob, draw_prob=parsed.draw_prob, away_win_prob=parsed.away_prob,
        btts_yes_prob=parsed.btts_yes_prob, btts_no_prob=parsed.btts_no_prob,
        total_goals_over_25_prob=parsed.over_25_prob, total_goals_under_25_prob=parsed.under_25_prob,
        total_goals_over_35_prob=parsed.over_35_prob, total_goals_under_35_prob=parsed.under_35_prob,
        exact_score=parsed.exact_score, exact_score_other_prob=parsed.exact_score_other_prob,
        recommended_bets=parsed.recommended_bets, match_confidence="exact", matched_by="provider_id",
        model_run_at=(parsed.model_run_at.replace(tzinfo=None) if parsed.model_run_at else None),
        fetched_at=fetched, raw_payload=payload)
    snapshot = ProviderForecastSnapshot(
        id=uuid.uuid4(), match_id=match.id, provider="gameforecast", external_event_id=str(payload["id"]),
        content_hash=content_hash(parsed), home_win_prob=parsed.home_prob, draw_prob=parsed.draw_prob,
        away_win_prob=parsed.away_prob, match_confidence="exact", matched_by="provider_id",
        first_fetched_at=fetched, last_fetched_at=fetched, kickoff_at_capture=match.match_date,
        captured_before_kickoff=match.match_date > fetched, raw_payload=payload)
    db.add_all([record, snapshot])
    db.flush()
    return record


def _result(db, match: Match, home: int, away: int, ht=None, beyond=False):
    result = MatchResult(id=uuid.uuid4(), match_id=match.id, home_score=home, away_score=away,
                         home_score_ht=ht[0] if ht else None, away_score_ht=ht[1] if ht else None,
                         home_score_ft=None if beyond else home, away_score_ft=None if beyond else away,
                         home_score_et=home if beyond else None, away_score_et=away if beyond else None,
                         result="H" if home > away else "A" if away > home else "D",
                         result_metadata={"provider": "livescore"})
    db.add(result)
    match.status = MatchStatus.FINISHED
    db.flush()
    return result


def leg_body(match: Match, selection_id: str, odds=None) -> dict:
    body = {"match_id": str(match.id), "selection_id": selection_id}
    if odds is not None:
        body["odds"] = odds
    return body


# ----------------------------------------------------------------------------- building
def test_a_slip_copies_the_selection_it_was_taken_from_and_reads_it_back(client, db, as_user):
    user = as_user(_user(db))
    league = _league(db)
    match = _match(db, league, "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    _forecast(db, match, load("bulgaria_luxembourg"))

    markets = client.get(f"/api/v1/matches/{match.id}/markets").json()
    assert markets["forecast"]["snapshot_id"] is not None
    served = {s["selection_id"]: s for g in markets["groups"] for m in g["markets"] for s in m["selections"]}
    assert served["total_goals:under@2.5"]["probability"] == pytest.approx(0.55)

    created = client.post("/api/v1/me/slips", json={"name": None, "legs": [leg_body(match, "total_goals:under@2.5")]})
    assert created.status_code == 201, created.text
    slip = created.json()
    assert slip["status"] == "draft" and slip["state"] == "pending"
    (leg,) = slip["legs"]
    assert leg["selection"] == {"selection_id": "total_goals:under@2.5", "market_id": "total_goals", "outcome": "under",
                                "line": 2.5, "period": "regulation"}
    assert leg["probability"] == pytest.approx(0.55)
    assert leg["probability_source"] == "provider"
    assert leg["snapshot_id"] == markets["forecast"]["snapshot_id"]
    assert leg["model_run_at"] == markets["forecast"]["model_run_at"]
    assert leg["forecast_fetched_at"] == markets["forecast"]["retrieved_at"]
    assert leg["normalisation_version"] == "markets.v1"
    assert leg["odds"] is None, "no price was given for this selection and none is invented"
    assert leg["started"] is False
    assert leg["current"] == {"probability": pytest.approx(0.55), "available": True, "forecast_changed": False, "state": "available"}
    assert leg["match"]["home"]["name"] == "Bulgaria"
    assert slip["price"] is None and slip["price_missing_legs"] == 1
    assert slip["potential"] is None

    listed = client.get("/api/v1/me/slips").json()["slips"]
    assert [s["id"] for s in listed] == [slip["id"]]


def test_one_selection_per_fixture_so_a_contradicting_leg_is_refused(client, db, as_user):
    as_user(_user(db))
    match = _match(db, _league(db), "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    _forecast(db, match, load("bulgaria_luxembourg"))
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(match, "match_result:home")]}).json()

    again = client.post(f"/api/v1/me/slips/{slip['id']}/legs", json=leg_body(match, "match_result:home"))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "one_per_match"
    contradiction = client.post(f"/api/v1/me/slips/{slip['id']}/legs", json=leg_body(match, "match_result:away"))
    assert contradiction.status_code == 409 and contradiction.json()["detail"]["code"] == "one_per_match"
    same_game = client.post(f"/api/v1/me/slips/{slip['id']}/legs", json=leg_body(match, "total_goals:over@2.5"))
    assert same_game.status_code == 409, "a same-game combination is outside this release"
    assert len(client.get(f"/api/v1/me/slips/{slip['id']}").json()["legs"]) == 1


def test_a_fixture_that_has_kicked_off_and_a_selection_the_forecast_lacks_are_refused(client, db, as_user):
    as_user(_user(db))
    league = _league(db)
    started = _match(db, league, "Georgia", "N.Ireland", KICKOFF_PASSED, status=MatchStatus.LIVE)
    _forecast(db, started, load("georgia_northern_ireland"))
    ahead = _match(db, league, "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    payload = json.loads(json.dumps(load("bulgaria_luxembourg")))
    del payload["predictions"][0]["first_half_winner"]
    _forecast(db, ahead, payload)
    no_forecast = _match(db, league, "Armenia", "Latvia", KICKOFF_AHEAD)

    late = client.post("/api/v1/me/slips", json={"legs": [leg_body(started, "match_result:home")]})
    assert late.status_code == 409 and late.json()["detail"]["code"] == "kickoff_passed"
    missing = client.post("/api/v1/me/slips", json={"legs": [leg_body(ahead, "first_half_result:home")]})
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "selection_unavailable"
    unknown = client.post("/api/v1/me/slips", json={"legs": [leg_body(ahead, "corners:over@9.5")]})
    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "selection_unknown"
    none = client.post("/api/v1/me/slips", json={"legs": [leg_body(no_forecast, "match_result:home")]})
    assert none.status_code == 422 and none.json()["detail"]["code"] == "selection_unknown"
    assert db.query(SelectionSlip).count() == 0, "a refused leg creates no slip"


def test_a_revised_forecast_changes_the_current_figure_beside_the_leg_never_the_stored_one(client, db, as_user):
    as_user(_user(db))
    match = _match(db, _league(db), "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    record = _forecast(db, match, load("bulgaria_luxembourg"))
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(match, "match_result:home")]}).json()
    assert slip["legs"][0]["probability"] == pytest.approx(0.45)

    revised = json.loads(json.dumps(load("bulgaria_luxembourg")))
    revised["predictions"][0]["match_result"] = {"home": 60, "draw": 25, "away": 15}
    record.raw_payload = revised
    record.home_win_prob = 0.60
    db.flush()

    leg = client.get(f"/api/v1/me/slips/{slip['id']}").json()["legs"][0]
    assert leg["probability"] == pytest.approx(0.45), "what the reader chose is what the reader chose"
    assert leg["current"]["probability"] == pytest.approx(0.60)
    assert leg["current"]["forecast_changed"] is True


# ----------------------------------------------------------------------------- saving, recording, duplicating
def test_saving_needs_a_name_and_recording_makes_the_slip_immutable(client, db, as_user):
    as_user(_user(db))
    league = _league(db)
    first = _match(db, league, "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    second = _match(db, league, "Armenia", "Latvia", KICKOFF_AHEAD + timedelta(hours=2))
    _forecast(db, first, load("bulgaria_luxembourg"))
    _forecast(db, second, load("armenia_latvia"))
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(first, "match_result:home", 2.3),
                                                          leg_body(second, "total_goals:under@2.5", 1.8)]}).json()
    assert slip["price"] == pytest.approx(4.14) and slip["price_source"] == "user"

    nameless = client.patch(f"/api/v1/me/slips/{slip['id']}", json={"status": "saved"})
    assert nameless.status_code == 422 and nameless.json()["detail"]["code"] == "name_required"
    saved = client.patch(f"/api/v1/me/slips/{slip['id']}", json={"name": "Weekend double", "status": "saved",
                                                               "currency": "EUR", "stake": "10.00"}).json()
    assert saved["status"] == "saved" and saved["name"] == "Weekend double"
    assert saved["potential"] == {"currency": "EUR", "stake": "10.00", "gross_return": "41.40", "net_profit": "31.40",
                                  "rounding": "half-up to the currency's minor unit",
                                  "note": "a quoted figure from the price given; not money held or promised by this application"}

    recorded = client.post(f"/api/v1/me/slips/{slip['id']}/record", json={"reference": "ticket 42", "price": 4.10}).json()
    assert recorded["status"] == "recorded" and recorded["recorded_reference"] == "ticket 42"
    assert recorded["price"] == pytest.approx(4.10) and recorded["price_source"] == "user"
    assert recorded["recorded_at"] is not None
    assert "own statement" in recorded["recorded_note"]

    for attempt in (
        client.post(f"/api/v1/me/slips/{slip['id']}/legs", json=leg_body(second, "match_result:home")),
        client.delete(f"/api/v1/me/slips/{slip['id']}/legs/{recorded['legs'][0]['id']}"),
        client.patch(f"/api/v1/me/slips/{slip['id']}/legs/{recorded['legs'][0]['id']}", json={"odds": 9.0}),
        client.patch(f"/api/v1/me/slips/{slip['id']}", json={"stake": "99"}),
        client.delete(f"/api/v1/me/slips/{slip['id']}"),
    ):
        assert attempt.status_code == 409 and attempt.json()["detail"]["code"] == "recorded_immutable", attempt.text

    renamed = client.patch(f"/api/v1/me/slips/{slip['id']}", json={"note": "placed at lunchtime"})
    assert renamed.status_code == 200 and renamed.json()["note"] == "placed at lunchtime"

    copy = client.post(f"/api/v1/me/slips/{slip['id']}/duplicate").json()
    assert copy["status"] == "draft" and copy["id"] != slip["id"]
    assert [l["selection"]["selection_id"] for l in copy["legs"]] == ["match_result:home", "total_goals:under@2.5"]
    edited = client.delete(f"/api/v1/me/slips/{copy['id']}/legs/{copy['legs'][0]['id']}").json()
    assert len(edited["legs"]) == 1
    original = client.get(f"/api/v1/me/slips/{slip['id']}").json()
    assert len(original["legs"]) == 2 and original["price"] == pytest.approx(4.10), "the recorded history is untouched"


def test_an_xaf_stake_takes_no_decimals_and_a_missing_price_invents_no_return(client, db, as_user):
    as_user(_user(db))
    match = _match(db, _league(db), "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    _forecast(db, match, load("bulgaria_luxembourg"))
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(match, "double_chance:1x")]}).json()

    fine = client.patch(f"/api/v1/me/slips/{slip['id']}", json={"currency": "XAF", "stake": "5050.50"})
    assert fine.status_code == 422 and fine.json()["detail"]["code"] == "stake_precision"
    ok = client.patch(f"/api/v1/me/slips/{slip['id']}", json={"currency": "XAF", "stake": "5050"}).json()
    assert ok["stake"] == "5050" and ok["currency"] == "XAF"
    assert ok["potential"] is None and ok["price"] is None, "a probability is not a price"
    priced = client.patch(f"/api/v1/me/slips/{slip['id']}/legs/{ok['legs'][0]['id']}", json={"odds": 1.33}).json()
    assert priced["potential"] == {"currency": "XAF", "stake": "5050", "gross_return": "6717", "net_profit": "1667",
                                   "rounding": "half-up to the currency's minor unit",
                                   "note": "a quoted figure from the price given; not money held or promised by this application"}
    unknown = client.patch(f"/api/v1/me/slips/{slip['id']}", json={"currency": "ZZZ", "stake": "1"})
    assert unknown.status_code == 422 and unknown.json()["detail"]["code"] == "unknown_currency"


# ----------------------------------------------------------------------------- privacy
def test_a_slip_is_private_to_its_owner(client, db, as_user):
    owner = _user(db)
    other = _user(db)
    match = _match(db, _league(db), "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    _forecast(db, match, load("bulgaria_luxembourg"))
    as_user(owner)
    slip = client.post("/api/v1/me/slips", json={"name": "mine", "legs": [leg_body(match, "match_result:home")]}).json()

    as_user(other)
    assert client.get("/api/v1/me/slips").json()["slips"] == []
    assert client.get(f"/api/v1/me/slips/{slip['id']}").status_code == 404
    assert client.patch(f"/api/v1/me/slips/{slip['id']}", json={"name": "stolen"}).status_code == 404
    assert client.delete(f"/api/v1/me/slips/{slip['id']}").status_code == 404
    assert client.post(f"/api/v1/me/slips/{slip['id']}/legs", json=leg_body(match, "match_result:away")).status_code == 404
    as_user(owner)
    assert client.get(f"/api/v1/me/slips/{slip['id']}").json()["name"] == "mine"


def test_reading_slips_signed_out_is_refused(client, db):
    assert client.get("/api/v1/me/slips").status_code in (401, 403)


# ----------------------------------------------------------------------------- settlement on read
def test_settlement_on_read_against_stored_results(client, db, as_user):
    as_user(_user(db))
    league = _league(db)
    georgia = _match(db, league, "Georgia", "N.Ireland", KICKOFF_AHEAD)
    armenia = _match(db, league, "Armenia", "Latvia", KICKOFF_AHEAD)
    dnb = _match(db, league, "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    overdue = _match(db, league, "Serbia", "Greece", KICKOFF_AHEAD)
    called_off = _match(db, league, "Austria", "Israel", KICKOFF_AHEAD)
    for match, name in ((georgia, "georgia_northern_ireland"), (armenia, "armenia_latvia"), (dnb, "bulgaria_luxembourg"),
                        (overdue, "bulgaria_luxembourg"), (called_off, "armenia_latvia")):
        payload = json.loads(json.dumps(load(name)))
        payload["id"] = f"{payload['id']}-{name}-{uuid.uuid4().hex[:4]}"
        _forecast(db, match, payload)

    won = client.post("/api/v1/me/slips", json={"name": "won", "legs": [
        leg_body(georgia, "match_result:away", 3.4), leg_body(armenia, "first_half_result:home", 2.0)]}).json()
    lost = client.post("/api/v1/me/slips", json={"name": "lost", "legs": [
        leg_body(georgia, "both_teams_score:yes"), leg_body(armenia, "total_goals:under@2.5")]}).json()
    voided = client.post("/api/v1/me/slips", json={"name": "void", "legs": [
        leg_body(dnb, "draw_no_bet:home", 1.5), leg_body(called_off, "match_result:home", 1.2), leg_body(armenia, "match_result:home", 1.6)]}).json()
    unresolved = client.post("/api/v1/me/slips", json={"name": "unresolved", "legs": [
        leg_body(georgia, "team_to_score_first:away"), leg_body(overdue, "match_result:home")]}).json()
    for slip in (won, lost, voided, unresolved):
        assert slip["state"] == "pending"

    # The results arrive (as stored on 2026-09-25), one fixture is postponed, one never gets a result.
    _result(db, georgia, 0, 1, ht=(0, 0))
    _result(db, armenia, 2, 0, ht=(1, 0))
    _result(db, dnb, 1, 1)
    called_off.status = MatchStatus.POSTPONED
    overdue.status = MatchStatus.LIVE
    overdue.match_date = KICKOFF_PASSED
    db.flush()

    listed = {s["name"]: s for s in client.get("/api/v1/me/slips").json()["slips"]}
    assert listed["won"]["state"] == "won"
    assert [l["state"] for l in listed["won"]["legs"]] == ["won", "won"]
    assert listed["won"]["legs"][1]["settlement"]["basis"] == "half_time"
    assert listed["won"]["settled_at"] is not None
    assert listed["lost"]["state"] == "lost"
    assert [l["state"] for l in listed["lost"]["legs"]] == ["lost", "won"]
    void_states = {l["match"]["home"]["name"]: l["state"] for l in listed["voided"]["legs"]} if "voided" in listed else \
        {l["match"]["home"]["name"]: l["state"] for l in listed["void"]["legs"]}
    assert void_states == {"Bulgaria": "void", "Austria": "void", "Armenia": "won"}
    assert listed["void"]["state"] == "won", "void legs drop out; the remaining leg won"
    assert listed["void"]["price"] == pytest.approx(1.5 * 1.2 * 1.6), "the original price is history"
    assert listed["void"]["effective_price"] == pytest.approx(1.6), "what the combination pays on: the void legs' prices drop out"
    assert listed["unresolved"]["state"] == "pending", "an overdue fixture with no result keeps the slip pending"
    unresolved_leg = {l["match"]["home"]["name"]: l for l in listed["unresolved"]["legs"]}
    assert unresolved_leg["Georgia"]["state"] == "unresolved"
    assert "order of goals" in unresolved_leg["Georgia"]["settlement"]["rule"]
    assert unresolved_leg["Serbia"]["state"] == "pending" and unresolved_leg["Serbia"]["started"] is True

    # Settlement is idempotent and final states are never reopened.
    again = {s["name"]: s for s in client.get("/api/v1/me/slips").json()["slips"]}
    assert again["won"]["settled_at"] == listed["won"]["settled_at"]
    assert client.get("/api/v1/me/slips?status=recorded").json()["slips"] == []


def test_a_recorded_bet_cannot_be_placed_on_a_fixture_already_played(client, db, as_user):
    as_user(_user(db))
    league = _league(db)
    match = _match(db, league, "Georgia", "N.Ireland", KICKOFF_AHEAD)
    _forecast(db, match, load("georgia_northern_ireland"))
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(match, "match_result:away")]}).json()
    _result(db, match, 0, 1, ht=(0, 0))
    refused = client.post(f"/api/v1/me/slips/{slip['id']}/record", json={})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "fixture_finished"


# ----------------------------------------------------------------------------- the review's defects
def test_replacing_a_selection_is_atomic_so_a_refused_replacement_leaves_the_original(client, db, as_user):
    as_user(_user(db))
    match = _match(db, _league(db), "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    payload = json.loads(json.dumps(load("bulgaria_luxembourg")))
    del payload["predictions"][0]["first_half_winner"]
    _forecast(db, match, payload)
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(match, "match_result:home", 2.3)]}).json()
    leg_id = slip["legs"][0]["id"]

    refused = client.put(f"/api/v1/me/slips/{slip['id']}/legs/{leg_id}", json={"selection_id": "first_half_result:home"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "selection_unavailable"
    kept = client.get(f"/api/v1/me/slips/{slip['id']}").json()
    assert [l["id"] for l in kept["legs"]] == [leg_id], "the original leg is untouched by a refused replacement"
    assert kept["legs"][0]["selection"]["selection_id"] == "match_result:home"

    swapped = client.put(f"/api/v1/me/slips/{slip['id']}/legs/{leg_id}", json={"selection_id": "total_goals:under@2.5", "odds": 1.8}).json()
    assert [l["selection"]["selection_id"] for l in swapped["legs"]] == ["total_goals:under@2.5"]
    assert swapped["legs"][0]["id"] != leg_id and swapped["legs"][0]["position"] == 0
    assert swapped["legs"][0]["odds"]["value"] == pytest.approx(1.8)
    assert swapped["price"] == pytest.approx(1.8)


def test_a_void_leg_adjusts_the_return_and_never_inflates_it(client, db, as_user):
    """Defect: a recorded 2.00 x 3.00 with 1,000 XAF staked still showed 6,000 after the first leg voided."""
    as_user(_user(db))
    league = _league(db)
    first = _match(db, league, "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    second = _match(db, league, "Armenia", "Latvia", KICKOFF_AHEAD + timedelta(hours=2))
    _forecast(db, first, load("bulgaria_luxembourg"))
    _forecast(db, second, load("armenia_latvia"))
    slip = client.post("/api/v1/me/slips", json={"name": "double", "legs": [leg_body(first, "match_result:home", 2.0),
                                                                            leg_body(second, "match_result:home", 3.0)]}).json()
    recorded = client.post(f"/api/v1/me/slips/{slip['id']}/record", json={"currency": "XAF", "stake": "1000"}).json()
    assert recorded["price"] == pytest.approx(6.0) and recorded["effective_price"] == pytest.approx(6.0)
    assert recorded["potential"]["gross_return"] == "6000" and recorded["potential"]["net_profit"] == "5000"

    first.status = MatchStatus.POSTPONED
    db.flush()
    after = client.get(f"/api/v1/me/slips/{slip['id']}").json()
    assert after["counts"]["void"] == 1
    assert after["price"] == pytest.approx(6.0), "the recorded price is history and stays"
    assert after["effective_price"] == pytest.approx(3.0), "what the combination now pays on"
    assert after["potential"]["gross_return"] == "3000" and after["potential"]["net_profit"] == "2000"
    assert "dropped out" in after["effective_price_note"]
    assert after["potential_withheld_reason"] is None


def test_a_void_leg_under_a_typed_combined_price_withholds_the_adjusted_return(client, db, as_user):
    as_user(_user(db))
    league = _league(db)
    first = _match(db, league, "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    second = _match(db, league, "Armenia", "Latvia", KICKOFF_AHEAD + timedelta(hours=2))
    _forecast(db, first, load("bulgaria_luxembourg"))
    _forecast(db, second, load("armenia_latvia"))
    # Two legs without their own prices; the reader records the bookmaker's combined 6.50.
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(first, "both_teams_score:no"), leg_body(second, "both_teams_score:no")]}).json()
    recorded = client.post(f"/api/v1/me/slips/{slip['id']}/record", json={"currency": "XAF", "stake": "1000", "price": 6.5}).json()
    assert recorded["potential"]["gross_return"] == "6500"

    second.status = MatchStatus.CANCELLED
    db.flush()
    after = client.get(f"/api/v1/me/slips/{slip['id']}").json()
    assert after["price"] == pytest.approx(6.5) and after["price_source"] == "user"
    assert after["effective_price"] is None
    assert after["potential"] is None, "6,500 XAF would be an invention once a leg is void"
    assert "cannot be computed" in after["potential_withheld_reason"]


def test_a_leg_is_attributed_only_to_a_snapshot_holding_the_numbers_it_was_taken_from(client, db, as_user):
    """Defect: a re-fetch that changed only a newly served block reused the old snapshot id."""
    as_user(_user(db))
    match = _match(db, _league(db), "Bulgaria", "Luxembourg", KICKOFF_AHEAD)
    record = _forecast(db, match, load("bulgaria_luxembourg"))
    old_snapshot = client.get(f"/api/v1/matches/{match.id}/markets").json()["forecast"]["snapshot_id"]
    assert old_snapshot

    # The provider revises only the first-half block; the current row is updated, no snapshot yet.
    revised = json.loads(json.dumps(load("bulgaria_luxembourg")))
    revised["predictions"][0]["first_half_winner"] = {"home": 40, "draw": 40, "away": 20}
    record.raw_payload = revised
    db.flush()
    envelope = client.get(f"/api/v1/matches/{match.id}/markets").json()
    assert envelope["forecast"]["snapshot_id"] is None, "no stored snapshot holds these numbers"
    slip = client.post("/api/v1/me/slips", json={"legs": [leg_body(match, "first_half_result:home")]}).json()
    assert slip["legs"][0]["probability"] == pytest.approx(0.40)
    assert slip["legs"][0]["snapshot_id"] is None, "no evidence is better than the wrong evidence"

    # The sync writes the new snapshot; from then on the leg's numbers are attributable.
    parsed = parse_event(revised)
    db.add(ProviderForecastSnapshot(
        id=uuid.uuid4(), match_id=match.id, provider="gameforecast", external_event_id=str(revised["id"]),
        content_hash=content_hash(parsed), home_win_prob=parsed.home_prob, draw_prob=parsed.draw_prob, away_win_prob=parsed.away_prob,
        match_confidence="exact", matched_by="provider_id", first_fetched_at=(NOW - timedelta(hours=1)).replace(tzinfo=None),
        last_fetched_at=(NOW - timedelta(hours=1)).replace(tzinfo=None), kickoff_at_capture=match.match_date,
        captured_before_kickoff=True, raw_payload=revised))
    db.flush()
    again = client.get(f"/api/v1/matches/{match.id}/markets").json()
    assert again["forecast"]["snapshot_id"] not in (None, old_snapshot)
    slip2 = client.post("/api/v1/me/slips", json={"legs": [leg_body(match, "first_half_result:home")]}).json()
    assert slip2["legs"][0]["snapshot_id"] == again["forecast"]["snapshot_id"]
