"""
Database-backed tests for the personal favourites endpoints.

What these lock down:
* Following and unfollowing a team or a league, idempotently, against the existing preference columns.
* Saving a match with and without a note, and re-saving without destroying the note.
* A saved match is private: another user can neither see it nor delete it, and never sees the note.
* An id that points at nothing is refused with a 404, so a favourite cannot dangle.
* The upcoming / live / finished split.
* Listing saved matches issues **no** provider request: every provider entry point raises if touched.

Requires PostgreSQL. Set TEST_DATABASE_URL (default: the docker-compose test database
postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test); skipped when unreachable.
"""

from __future__ import annotations

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
from app.models.predictions import League, Match, MatchStatus, Team
from app.models.users import AccountStatus, SavedMatch, User, UserPreference, UserType
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers.http import ProviderHttpClient
from app.services.providers.sample import SampleDataProvider, SampleForecastProvider
from tests.providers.support import FakeRedis

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

# Far enough ahead that no other module's fixtures share the day.
DAY = (datetime.now(timezone.utc) + timedelta(days=55)).date()
KICKOFF = datetime.combine(DAY, datetime.min.time()) + timedelta(hours=18)


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
    """Session joined to an outer transaction; endpoint-level commit() only releases a savepoint."""
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
    """Every service gets the same in-memory cache; nothing reaches the real Redis."""
    redis = FakeRedis()
    monkeypatch.setattr("app.services.match_data_service.MatchCache", lambda client=None: MatchCache(client=redis))
    monkeypatch.setattr("app.services.forecast_service.MatchCache", lambda client=None: MatchCache(client=redis))
    return redis


@pytest.fixture(autouse=True)
def no_provider_calls(monkeypatch):
    """
    Every way out to a provider, closed.

    The autouse guard in tests/conftest.py forces the *sample* providers, which answer from local
    data and would hide a refresh that should never have happened. So the sample provider's own
    entry points fail here too, alongside the shared HTTP client: if any endpoint in this module
    tries to fetch anything, the test that called it fails.
    """
    def refuse(name):
        def _refuse(*args, **kwargs):
            raise AssertionError(f"a provider call was made ({name}); these endpoints read stored data only")
        return _refuse

    monkeypatch.setattr(ProviderHttpClient, "get_json", refuse("http get_json"))
    for method in ("get_fixtures", "get_live", "get_results", "get_standings", "list_competitions"):
        monkeypatch.setattr(SampleDataProvider, method, refuse(f"SampleDataProvider.{method}"))
    monkeypatch.setattr(SampleForecastProvider, "get_forecasts", refuse("SampleForecastProvider.get_forecasts"))


@pytest.fixture
def client(db):
    """Client with both get_db callables overridden. Authentication is added per test by `as_user`."""
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
    """Sign a given user in for the following requests (test-only; real authentication is untouched)."""
    def _as(user: User):
        app.dependency_overrides[get_current_active_user] = lambda: user
        return user
    yield _as
    app.dependency_overrides.pop(get_current_active_user, None)


# ----------------------------------------------------------------------------- helpers
def _user(db) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"fan-{suffix}@test.local", username=f"fan_{suffix}",
                password_hash="not-a-real-hash", user_type=UserType.REGULAR,
                account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


def _league(db) -> League:
    league = MatchRegistry(db).ensure_canonical_league("premier_league")
    db.flush()
    return league


def _team(db, name: str) -> Team:
    team = Team(id=uuid.uuid4(), name=name, country="England")
    db.add(team)
    db.flush()
    return team


def _match(db, league: League, label: str, kickoff: datetime = KICKOFF,
           status: MatchStatus = MatchStatus.SCHEDULED) -> Match:
    match = Match(id=uuid.uuid4(), league_id=league.id, home_team_id=_team(db, f"{label} Home").id,
                  away_team_id=_team(db, f"{label} Away").id, match_date=kickoff, status=status,
                  external_api_id=f"ext-fav-{label}-{uuid.uuid4().hex[:6]}", external_api_source="sample",
                  match_metadata={})
    db.add(match)
    db.flush()
    return match


# ----------------------------------------------------------------------------- follow / unfollow
def test_follow_and_unfollow_a_team(client, db, as_user):
    user, team = _user(db), _team(db, "Followed FC")
    as_user(user)

    followed = client.put(f"/api/v1/me/favourites/teams/{team.id}")
    assert followed.status_code == 200, followed.text
    assert followed.json()["following"] is True and followed.json()["changed"] is True
    assert followed.json()["ids"] == [str(team.id)]

    listed = client.get("/api/v1/me/favourites").json()
    assert [t["id"] for t in listed["teams"]] == [str(team.id)]
    assert listed["teams"][0]["name"] == "Followed FC"
    assert listed["unresolved"]["teams"] == []

    removed = client.delete(f"/api/v1/me/favourites/teams/{team.id}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["following"] is False and removed.json()["changed"] is True
    assert client.get("/api/v1/me/favourites").json()["teams"] == []


def test_following_the_same_team_twice_changes_nothing(client, db, as_user):
    user, team = _user(db), _team(db, "Twice FC")
    as_user(user)

    first = client.put(f"/api/v1/me/favourites/teams/{team.id}").json()
    second = client.put(f"/api/v1/me/favourites/teams/{team.id}").json()

    assert first["changed"] is True and second["changed"] is False
    assert second["following"] is True and second["ids"] == [str(team.id)]


def test_unfollowing_something_not_followed_is_not_an_error(client, db, as_user):
    user, team = _user(db), _team(db, "Never FC")
    as_user(user)

    response = client.delete(f"/api/v1/me/favourites/teams/{team.id}")

    assert response.status_code == 200, response.text
    assert response.json()["changed"] is False and response.json()["following"] is False


def test_following_an_unknown_team_is_a_404(client, db, as_user):
    as_user(_user(db))
    assert client.put(f"/api/v1/me/favourites/teams/{uuid.uuid4()}").status_code == 404
    assert client.put("/api/v1/me/favourites/teams/not-a-uuid").status_code == 404


def test_following_an_unknown_league_is_a_404(client, db, as_user):
    as_user(_user(db))
    assert client.put(f"/api/v1/me/favourites/leagues/{uuid.uuid4()}").status_code == 404
    assert client.put("/api/v1/me/favourites/leagues/no_such_competition").status_code == 404


def test_a_league_can_be_followed_by_its_canonical_key_and_is_stored_as_a_uuid(client, db, as_user):
    """The UI addresses a competition by key; one league must still have one spelling on disk."""
    user, league = _user(db), _league(db)
    as_user(user)

    response = client.put("/api/v1/me/favourites/leagues/premier_league")

    assert response.status_code == 200, response.text
    assert response.json()["ids"] == [str(league.id)]
    listed = client.get("/api/v1/me/favourites").json()
    assert [entry["id"] for entry in listed["leagues"]] == [str(league.id)]


def test_a_followed_id_that_no_longer_resolves_is_reported_not_dropped(client, db, as_user):
    """"We follow something we cannot show you" must not be silently rendered as "you follow nothing"."""
    user = _user(db)
    stale = str(uuid.uuid4())
    db.add(UserPreference(user_id=user.id, favorite_teams=[stale], favorite_leagues=[]))
    db.flush()
    as_user(user)

    listed = client.get("/api/v1/me/favourites").json()

    assert listed["teams"] == []
    assert listed["team_ids"] == [stale]
    assert listed["unresolved"]["teams"] == [stale]


def test_the_team_limit_is_enforced_and_matches_the_preferences_endpoint(client, db, as_user):
    """Both writers of favorite_teams must agree, or one stores a list the other refuses back."""
    user = _user(db)
    as_user(user)
    limit = client.get("/api/v1/me/favourites").json()["limits"]["teams"]
    for index in range(limit):
        team = _team(db, f"Limit {index}")
        assert client.put(f"/api/v1/me/favourites/teams/{team.id}").status_code == 200

    overflow = client.put(f"/api/v1/me/favourites/teams/{_team(db, 'One too many').id}")

    assert overflow.status_code == 400, overflow.text
    assert len(client.get("/api/v1/me/favourites").json()["team_ids"]) == limit


# ----------------------------------------------------------------------------- saving matches
def test_save_a_match_without_a_note(client, db, as_user):
    user, match = _user(db), _match(db, _league(db), "plain")
    as_user(user)

    response = client.put(f"/api/v1/me/saved-matches/{match.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] is True and body["note"] is None
    assert body["match_id"] == str(match.id)
    # The same payload the match endpoints return, not a second shape invented here.
    assert body["match"]["id"] == str(match.id)
    assert body["match"]["kickoff_utc"] == KICKOFF.isoformat() + "Z"
    assert body["match"]["home"]["name"] == "plain Home"
    assert body["match"]["forecast_state"] == "unavailable"
    assert body["saved_at"].endswith("Z")


def test_save_a_match_with_a_note_and_keep_it_on_a_plain_re_save(client, db, as_user):
    user, match = _user(db), _match(db, _league(db), "noted")
    as_user(user)

    created = client.put(f"/api/v1/me/saved-matches/{match.id}", json={"note": "  watch the keeper  "})
    assert created.status_code == 200, created.text
    assert created.json()["note"] == "watch the keeper"

    again = client.put(f"/api/v1/me/saved-matches/{match.id}")

    assert again.status_code == 200, again.text
    assert again.json()["created"] is False, "a repeat save must be idempotent, not an error"
    assert again.json()["note"] == "watch the keeper", "a plain re-save must not destroy the note"
    assert db.query(SavedMatch).filter(SavedMatch.user_id == user.id).count() == 1


def test_a_note_can_be_changed_and_cleared(client, db, as_user):
    user, match = _user(db), _match(db, _league(db), "editnote")
    as_user(user)

    client.put(f"/api/v1/me/saved-matches/{match.id}", json={"note": "first thought"})
    changed = client.put(f"/api/v1/me/saved-matches/{match.id}", json={"note": "second thought"})
    cleared = client.put(f"/api/v1/me/saved-matches/{match.id}", json={"note": "   "})

    assert changed.json()["note"] == "second thought"
    assert cleared.json()["note"] is None


def test_saving_an_unknown_match_is_a_404(client, db, as_user):
    as_user(_user(db))
    assert client.put(f"/api/v1/me/saved-matches/{uuid.uuid4()}").status_code == 404
    assert client.put("/api/v1/me/saved-matches/not-a-match").status_code == 404


def test_unsaving_a_match_that_was_not_saved_is_not_an_error(client, db, as_user):
    user, match = _user(db), _match(db, _league(db), "notsaved")
    as_user(user)

    response = client.delete(f"/api/v1/me/saved-matches/{match.id}")

    assert response.status_code == 200, response.text
    assert response.json()["removed"] is False


def test_unsave_removes_only_that_save(client, db, as_user):
    user, league = _user(db), _league(db)
    kept, dropped = _match(db, league, "kept"), _match(db, league, "dropped")
    as_user(user)
    client.put(f"/api/v1/me/saved-matches/{kept.id}")
    client.put(f"/api/v1/me/saved-matches/{dropped.id}")

    removed = client.delete(f"/api/v1/me/saved-matches/{dropped.id}")

    assert removed.json()["removed"] is True
    remaining = client.get("/api/v1/me/saved-matches").json()
    assert [entry["match_id"] for entry in remaining["upcoming"]] == [str(kept.id)]


# ----------------------------------------------------------------------------- listing
def test_saved_matches_are_split_into_upcoming_live_and_finished(client, db, as_user):
    user, league = _user(db), _league(db)
    later = _match(db, league, "later", KICKOFF + timedelta(hours=3))
    sooner = _match(db, league, "sooner", KICKOFF)
    playing = _match(db, league, "playing", KICKOFF - timedelta(days=1), MatchStatus.LIVE)
    played = _match(db, league, "played", KICKOFF - timedelta(days=2), MatchStatus.FINISHED)
    as_user(user)
    for match in (later, sooner, playing, played):
        assert client.put(f"/api/v1/me/saved-matches/{match.id}").status_code == 200

    body = client.get("/api/v1/me/saved-matches").json()

    # Upcoming runs earliest kickoff first, whatever order the saves were made in.
    assert [entry["match_id"] for entry in body["upcoming"]] == [str(sooner.id), str(later.id)]
    assert [entry["match_id"] for entry in body["live"]] == [str(playing.id)]
    assert [entry["match_id"] for entry in body["finished"]] == [str(played.id)]
    assert body["counts"] == {"upcoming": 2, "live": 1, "finished": 1, "total": 4}


def test_favourites_carries_the_same_saved_match_block(client, db, as_user):
    user, match = _user(db), _match(db, _league(db), "dashboard")
    as_user(user)
    client.put(f"/api/v1/me/saved-matches/{match.id}", json={"note": "one call for the dashboard"})

    favourites = client.get("/api/v1/me/favourites").json()

    assert favourites["saved_matches"] == client.get("/api/v1/me/saved-matches").json()
    assert favourites["saved_matches"]["upcoming"][0]["note"] == "one call for the dashboard"


def test_a_saved_match_whose_fixture_is_deleted_does_not_break_the_list(client, db, as_user):
    user, league = _user(db), _league(db)
    doomed, kept = _match(db, league, "doomed"), _match(db, league, "survivor")
    as_user(user)
    client.put(f"/api/v1/me/saved-matches/{doomed.id}")
    client.put(f"/api/v1/me/saved-matches/{kept.id}")

    db.delete(doomed)
    db.flush()

    response = client.get("/api/v1/me/saved-matches")
    assert response.status_code == 200, response.text
    assert [entry["match_id"] for entry in response.json()["upcoming"]] == [str(kept.id)]


def test_listing_saved_matches_makes_no_provider_call(client, db, as_user):
    """
    The `no_provider_calls` fixture turns every provider entry point into a failure, so this passing
    is the assertion: reading favourites spends nothing from any allowance.
    """
    user, match = _user(db), _match(db, _league(db), "nobudget")
    as_user(user)
    client.put(f"/api/v1/me/saved-matches/{match.id}")

    assert client.get("/api/v1/me/saved-matches").status_code == 200
    assert client.get("/api/v1/me/favourites").status_code == 200


# ----------------------------------------------------------------------------- isolation between users
def test_one_user_never_sees_another_users_saved_match_or_note(client, db, as_user):
    owner, other = _user(db), _user(db)
    match = _match(db, _league(db), "private")
    as_user(owner)
    client.put(f"/api/v1/me/saved-matches/{match.id}", json={"note": "my own reminder"})

    as_user(other)
    body = client.get("/api/v1/me/saved-matches").json()

    assert body["counts"]["total"] == 0
    assert "my own reminder" not in client.get("/api/v1/me/favourites").text


def test_one_user_cannot_delete_another_users_saved_match(client, db, as_user):
    owner, other = _user(db), _user(db)
    match = _match(db, _league(db), "notyours")
    as_user(owner)
    client.put(f"/api/v1/me/saved-matches/{match.id}", json={"note": "still mine"})

    as_user(other)
    attempt = client.delete(f"/api/v1/me/saved-matches/{match.id}")

    assert attempt.status_code == 200, attempt.text
    assert attempt.json()["removed"] is False, "nothing of this user's was deleted"
    as_user(owner)
    still_there = client.get("/api/v1/me/saved-matches").json()
    assert [entry["match_id"] for entry in still_there["upcoming"]] == [str(match.id)]
    assert still_there["upcoming"][0]["note"] == "still mine"


def test_one_users_follows_do_not_leak_into_anothers(client, db, as_user):
    owner, other = _user(db), _user(db)
    team = _team(db, "Shared name only")
    as_user(owner)
    client.put(f"/api/v1/me/favourites/teams/{team.id}")

    as_user(other)
    assert client.get("/api/v1/me/favourites").json()["team_ids"] == []


# ----------------------------------------------------------------------------- authentication
class TestAuthenticationIsStillEnforced:
    """The override above is test-only: the application itself accepts neither no token nor a fake one."""

    @pytest.fixture
    def unauthenticated_client(self, db):
        def override_get_db():
            yield db

        overrides = {deps_get_db: override_get_db, session_get_db: override_get_db}
        app.dependency_overrides.update(overrides)
        try:
            yield TestClient(app)
        finally:
            for dependency in overrides:
                app.dependency_overrides.pop(dependency, None)

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/v1/me/favourites"),
        ("get", "/api/v1/me/saved-matches"),
        ("put", "/api/v1/me/saved-matches/00000000-0000-0000-0000-000000000000"),
        ("delete", "/api/v1/me/saved-matches/00000000-0000-0000-0000-000000000000"),
        ("put", "/api/v1/me/favourites/teams/00000000-0000-0000-0000-000000000000"),
        ("delete", "/api/v1/me/favourites/leagues/00000000-0000-0000-0000-000000000000"),
    ])
    def test_missing_token_is_rejected(self, unauthenticated_client, method, path):
        response = getattr(unauthenticated_client, method)(path)
        assert response.status_code in (401, 403), response.text

    def test_mock_token_is_rejected(self, unauthenticated_client):
        response = unauthenticated_client.get("/api/v1/me/favourites",
                                              headers={"Authorization": "Bearer mock-token"})
        assert response.status_code == 401, response.text
