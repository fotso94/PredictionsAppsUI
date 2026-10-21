"""
The signed-in user's own profile and password: PUT /api/v1/users/me and PUT /api/v1/users/me/password.

What was wrong before this change:

* The profile form sends every field. An account whose first or last name was never supplied (the
  columns are nullable) sent '' for it, and ``min_length=1`` refused the whole request with 422, so
  such a user could not change even their username or avatar.
* A name could not be cleared at all: '' was refused, and an explicit null was read as "not sent"
  (``if value is not None``), so the stored name silently stayed.
* Nothing was stripped. Three spaces passed ``min_length=3`` and became a username; " taken " slipped
  past the duplicate check because it is not "taken".
* The password change answered "You have been logged out from all devices." That is not what
  happens: access tokens stay valid until they expire, and /auth/refresh does not consult the
  refresh-token keys the change deletes. The message now says only what is true. Making the claim
  true (token hardening) is a separate piece of work and is not attempted here.

The contract these tests pin: an omitted field is unchanged; '' or null clears a nullable field
(first_name, last_name, avatar_url); strings are stripped; a username can never be blanked (422 with
a message saying so) and a taken one is still 409.

Requires PostgreSQL (TEST_DATABASE_URL, default the docker-compose test database); skipped when
unreachable. Redis is never reached: the user-cache invalidation and the refresh-token revocation are
replaced by recorders.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import List, Optional

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_current_active_user
from app.core.deps import get_db as deps_get_db
from app.core.security import get_password_hash, verify_password
from app.db.base import Base
from app.db.session import get_db as session_get_db
from app.main import app
from app.models.users import AccountStatus, User, UserType
from app.schemas.users import UserUpdateRequest

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

OLD_PASSWORD = "old-password-1"
NEW_PASSWORD = "new-password-2"


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


class Recorder:
    """Stands in for a Redis-backed side effect and remembers every call."""

    def __init__(self):
        self.calls: List[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args + tuple(kwargs.values()))
        return 0


@pytest.fixture(autouse=True)
def revoked(monkeypatch) -> Recorder:
    """The refresh-token revocation and the user-cache invalidation, recorded instead of sent to Redis."""
    recorder = Recorder()
    monkeypatch.setattr("app.api.v1.endpoints.users.revoke_user_refresh_tokens", recorder)

    class _Cache:
        delete_user_cache = Recorder()

    monkeypatch.setattr("app.api.v1.endpoints.users.cache_service", _Cache())
    return recorder


@pytest.fixture
def client(db):
    """Both get_db callables overridden; never entered as a context manager, so no app lifespan."""
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
STAMPED = datetime(2026, 1, 2, 3, 4, 5)


def _user(db, first_name: Optional[str] = "Ada", last_name: Optional[str] = "Lovelace",
          avatar_url: Optional[str] = "https://example.invalid/ada.png",
          password_hash: str = "not-a-real-hash", username: Optional[str] = None) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(id=uuid.uuid4(), email=f"me-{suffix}@test.local", username=username or f"me_{suffix}",
                first_name=first_name, last_name=last_name, avatar_url=avatar_url,
                password_hash=password_hash, user_type=UserType.REGULAR,
                account_status=AccountStatus.ACTIVE, email_verified=True,
                created_at=STAMPED, updated_at=STAMPED)
    db.add(user)
    db.flush()
    return user


def _reread(db, user: User) -> User:
    db.expire_all()
    return db.query(User).filter(User.id == user.id).one()


def _put(client, body: dict):
    return client.put("/api/v1/users/me", json=body)


# ----------------------------------------------------------------------------- the schema contract
def test_a_blank_name_is_read_as_a_clear_and_is_still_counted_as_sent():
    body = UserUpdateRequest(first_name="", last_name="   ", avatar_url=" ")
    assert body.first_name is None and body.last_name is None and body.avatar_url is None
    assert body.model_fields_set == {"first_name", "last_name", "avatar_url"}


def test_an_empty_body_sends_nothing():
    assert UserUpdateRequest().model_fields_set == set()


@pytest.mark.parametrize("username", ["", "   ", None])
def test_a_username_cannot_be_blanked_in_the_schema(username):
    with pytest.raises(ValidationError) as caught:
        UserUpdateRequest(username=username)
    assert "username cannot be blank" in str(caught.value)


def test_strings_are_stripped():
    body = UserUpdateRequest(username="  spaced_name  ", first_name="  Grace ")
    assert body.username == "spaced_name" and body.first_name == "Grace"


# ----------------------------------------------------------------------------- PUT /users/me
def test_a_user_with_no_names_can_change_their_username_from_the_full_form(client, db, as_user):
    """The defect the QA hit: the form sends '' for a name that was never supplied. Was 422."""
    user = as_user(_user(db, first_name=None, last_name=None, avatar_url=None))
    new_username = f"renamed_{uuid.uuid4().hex[:8]}"

    response = _put(client, {"username": new_username, "first_name": "", "last_name": "",
                             "avatar_url": ""})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == new_username
    assert body["first_name"] is None and body["last_name"] is None and body["avatar_url"] is None
    stored = _reread(db, user)
    assert stored.username == new_username
    assert stored.first_name is None and stored.last_name is None and stored.avatar_url is None


def test_a_user_with_no_names_can_change_only_their_avatar(client, db, as_user):
    user = as_user(_user(db, first_name=None, last_name=None, avatar_url=None))

    response = _put(client, {"avatar_url": "https://example.invalid/new.png"})

    assert response.status_code == 200, response.text
    assert _reread(db, user).avatar_url == "https://example.invalid/new.png"


def test_an_explicit_null_clears_a_name_and_leaves_the_other_fields_alone(client, db, as_user):
    """Was a silent no-op: null was read as "not sent", so the stored name stayed."""
    user = as_user(_user(db))
    username = user.username

    response = _put(client, {"first_name": None})

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert stored.first_name is None
    assert stored.last_name == "Lovelace"
    assert stored.avatar_url == "https://example.invalid/ada.png"
    assert stored.username == username


def test_an_explicit_null_or_blank_clears_the_avatar_and_the_last_name(client, db, as_user):
    user = as_user(_user(db))

    response = _put(client, {"avatar_url": None, "last_name": "   "})

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert stored.avatar_url is None and stored.last_name is None
    assert stored.first_name == "Ada"


def test_an_empty_body_changes_nothing(client, db, as_user):
    user = as_user(_user(db))
    before = (user.username, user.first_name, user.last_name, user.avatar_url)

    response = _put(client, {})

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert (stored.username, stored.first_name, stored.last_name, stored.avatar_url) == before
    # Nothing changed, so nothing claims a change either.
    assert stored.updated_at == STAMPED


def test_a_real_change_moves_updated_at(client, db, as_user):
    user = as_user(_user(db))

    response = _put(client, {"first_name": "Grace"})

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert stored.first_name == "Grace"
    assert stored.updated_at > STAMPED


def test_values_are_stored_stripped(client, db, as_user):
    user = as_user(_user(db))
    new_username = f"strip_{uuid.uuid4().hex[:8]}"

    response = _put(client, {"username": f"  {new_username}  ", "first_name": "  Grace  "})

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert stored.username == new_username and stored.first_name == "Grace"


@pytest.mark.parametrize("username", ["", "   ", None])
def test_a_username_cannot_be_blanked(client, db, as_user, username):
    """'   ' used to pass min_length=3 and was stored; null was a silent no-op. Both are refused now."""
    user = as_user(_user(db))
    original = user.username

    response = _put(client, {"username": username})

    assert response.status_code == 422, response.text
    assert "username cannot be blank" in response.text
    assert _reread(db, user).username == original


@pytest.mark.parametrize("spelling", ["{taken}", "  {taken}  "])
def test_a_taken_username_is_still_a_conflict(client, db, as_user, spelling):
    """Padded with spaces, the taken name used to slip past the duplicate check and be stored."""
    other = _user(db)
    user = as_user(_user(db))
    original = user.username

    response = _put(client, {"username": spelling.format(taken=other.username)})

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Username already taken"
    assert _reread(db, user).username == original


def test_sending_ones_own_username_back_is_not_a_conflict(client, db, as_user):
    user = as_user(_user(db))

    response = _put(client, {"username": user.username, "first_name": "Ada"})

    assert response.status_code == 200, response.text


def _padded_username(padding: str = " ") -> str:
    """A username stored with whitespace around it, as registration still allows.

    Written at creation: changing it afterwards would move updated_at (the column's onupdate) in
    the test's own setup.
    """
    return f"padded_{uuid.uuid4().hex[:8]}{padding}"


def test_a_padded_stored_username_sent_back_trimmed_is_unchanged_not_a_conflict(client, db, as_user):
    """The profile form always resends the username, trimmed by the schema.

    For an account stored as 'name ' while another account owns 'name', the unchanged username
    compared unequal to the stored one, went to the duplicate check, found the other account and
    refused EVERY save with 409 - a save that changed only the last name included.
    """
    other = _user(db)
    # The same name with a trailing space: the unique index allows both.
    user = as_user(_user(db, username=f"{other.username} "))
    stored_username = user.username

    response = _put(client, {"username": other.username, "last_name": "Byron"})

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert stored.last_name == "Byron"
    assert stored.username == stored_username, "an unchanged username is not rewritten"
    assert _reread(db, other).username == other.username


@pytest.mark.parametrize("padding", [" ", "  ", "\t"])
def test_a_padded_stored_username_sent_back_alone_changes_nothing(client, db, as_user, padding):
    """No conflict to trip over, and still nothing to change: no write, no new updated_at."""
    user = as_user(_user(db, username=_padded_username(padding)))
    stored_username = user.username

    response = _put(client, {"username": stored_username.strip()})

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert stored.username == stored_username
    assert stored.updated_at == STAMPED, "a request that changes nothing claims no change"


def test_a_padded_stored_username_can_still_be_changed_and_is_stored_trimmed(client, db, as_user):
    user = as_user(_user(db, username=_padded_username()))
    new_username = f"fresh_{uuid.uuid4().hex[:8]}"

    response = _put(client, {"username": f" {new_username} "})

    assert response.status_code == 200, response.text
    assert _reread(db, user).username == new_username


# ----------------------------------------------------------------------------- PUT /users/me/password
def _password_user(db, as_user) -> User:
    return as_user(_user(db, password_hash=get_password_hash(OLD_PASSWORD)))


def _change(client, current: str, new: str, confirm: str):
    return client.put("/api/v1/users/me/password",
                      json={"current_password": current, "new_password": new, "confirm_password": confirm})


def test_a_wrong_current_password_is_refused_and_changes_nothing(client, db, as_user, revoked):
    user = _password_user(db, as_user)

    response = _change(client, "not-the-password", NEW_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "Incorrect current password"
    assert verify_password(OLD_PASSWORD, _reread(db, user).password_hash)
    assert revoked.calls == []


def test_mismatched_new_passwords_are_refused_and_change_nothing(client, db, as_user, revoked):
    user = _password_user(db, as_user)

    response = _change(client, OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD + "x")

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == "New passwords do not match"
    assert verify_password(OLD_PASSWORD, _reread(db, user).password_hash)
    assert revoked.calls == []


def test_a_password_change_stores_the_new_hash_revokes_refresh_tokens_and_claims_nothing_more(
        client, db, as_user, revoked):
    user = _password_user(db, as_user)

    response = _change(client, OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

    assert response.status_code == 200, response.text
    stored = _reread(db, user)
    assert verify_password(NEW_PASSWORD, stored.password_hash)
    assert not verify_password(OLD_PASSWORD, stored.password_hash)
    assert revoked.calls == [(str(user.id),)]
    message = response.json()["message"]
    # Other devices are NOT signed out (access tokens stay valid until they expire), so the
    # message must not say they are.
    assert "all devices" not in message and "logged out" not in message
    assert message == "Password changed successfully. Sign in again with your new password."
