"""
The password-reset emails: who they greet, and what they claim happened.

What was wrong before this change:

* PUT /users/me can now clear a first or last name (it stores NULL). The forgot-password and
  reset-password endpoints built the greeting as ``f"{user.first_name} {user.last_name}"``, so a
  cleared name became the literal word 'None' ('None Smith', or 'None None'), and because that is
  not blank the username fallback was never reached. Every other name in auth.py already guarded
  against None; all of them now go through one helper.
* The reset email promised "You'll be logged out of all devices" and the confirmation "You've been
  logged out of all devices". The reset deletes the user's refresh-token keys, which /auth/refresh
  never consults, and access tokens stay valid until they expire - the same reason the
  change-password copy was corrected this round. The templates now say what is true: devices that
  are already signed in are not signed out automatically. Making the claim true (token hardening)
  is separate work and is not attempted here.

No email is ever sent: the email service is replaced by a recorder, and the refresh-token
revocation (Redis) by a no-op. Requires PostgreSQL (TEST_DATABASE_URL, default the docker-compose
test database); skipped when unreachable.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.deps import get_db as deps_get_db
from app.db.base import Base
from app.db.session import get_db as session_get_db
from app.main import app
from app.models.users import AccountStatus, User, UserType
from app.services.email_service import EmailService

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres123@localhost:5432/soccer_predictions_test")

TEMPLATES = Path(__file__).resolve().parents[2] / "app" / "templates" / "emails"
RESET_TEMPLATES = ("password_reset.txt", "password_reset.html",
                   "password_reset_confirmation.txt", "password_reset_confirmation.html")
NEW_PASSWORD = "reset-password-3"


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


class EmailRecorder:
    """Stands in for the email service: remembers what each email would have been sent with."""

    def __init__(self):
        self.resets: List[Dict[str, Any]] = []
        self.confirmations: List[Dict[str, Any]] = []

    async def send_password_reset_email(self, **kwargs) -> bool:
        self.resets.append(kwargs)
        return True

    async def send_password_reset_confirmation_email(self, **kwargs) -> bool:
        self.confirmations.append(kwargs)
        return True


@pytest.fixture
def emails(monkeypatch) -> EmailRecorder:
    recorder = EmailRecorder()
    monkeypatch.setattr("app.api.v1.endpoints.auth.email_service", recorder)
    monkeypatch.setattr("app.api.v1.endpoints.auth.revoke_user_refresh_tokens", lambda **_: 0)
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


def _user(db, first_name: Optional[str], last_name: Optional[str]) -> User:
    suffix = uuid.uuid4().hex[:8]
    # example.com, not test.local: the reset request validates the address, and refuses
    # special-use domains.
    user = User(id=uuid.uuid4(), email=f"reset-{suffix}@example.com", username=f"reset_{suffix}",
                first_name=first_name, last_name=last_name, password_hash="not-a-real-hash",
                user_type=UserType.REGULAR, account_status=AccountStatus.ACTIVE, email_verified=True)
    db.add(user)
    db.flush()
    return user


# ----------------------------------------------------------------------------- the greeting
NAMES = [
    # (first_name, last_name, expected greeting; None means "the username")
    ("Ada", "Lovelace", "Ada Lovelace"),
    (None, "Lovelace", "Lovelace"),
    ("Ada", None, "Ada"),
    (None, None, None),
]


@pytest.mark.parametrize("first_name,last_name,expected", NAMES)
def test_both_reset_emails_greet_by_name_and_never_say_none(client, db, emails, first_name, last_name, expected):
    user = _user(db, first_name, last_name)
    greeting = expected if expected is not None else user.username

    requested = client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert requested.status_code == 200, requested.text
    assert len(emails.resets) == 1
    assert emails.resets[0]["user_name"] == greeting
    assert "None" not in emails.resets[0]["user_name"]

    reset = client.post("/api/v1/auth/reset-password",
                        json={"token": emails.resets[0]["reset_token"], "new_password": NEW_PASSWORD})
    assert reset.status_code == 200, reset.text
    assert len(emails.confirmations) == 1
    assert emails.confirmations[0]["user_name"] == greeting
    assert "None" not in emails.confirmations[0]["user_name"]


# ----------------------------------------------------------------------------- what the emails claim
def _templates() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))


CONTEXT = {"user_name": "Ada", "reset_url": "https://example.invalid/reset-password?token=x",
           "reset_token": "x", "login_url": "https://example.invalid/login",
           "platform_name": "Soccer Predictions Platform", "support_email": "support@example.invalid",
           "year": "2025"}


@pytest.mark.parametrize("name", RESET_TEMPLATES)
def test_the_reset_templates_do_not_claim_a_logout_everywhere(name):
    """A reset signs no other device out: /auth/refresh never reads the keys it deletes."""
    rendered = _templates().get_template(name).render(**CONTEXT)
    lowered = rendered.lower()
    assert "all devices" not in lowered, f"{name} still claims a logout on every device"
    assert "logged out of" not in lowered
    assert re.search(r"\bnot (be )?signed out automatically", lowered), f"{name} does not say what happens"


@pytest.mark.asyncio
async def test_what_the_service_actually_sends_claims_no_logout_everywhere(monkeypatch):
    """Whichever content the service ends up using (template or built-in fallback), checked as sent."""
    service = EmailService()
    sent: List[Dict[str, str]] = []

    async def capture(**kwargs) -> bool:
        sent.append(kwargs)
        return True

    monkeypatch.setattr(service, "send_email", capture)
    assert await service.send_password_reset_email(to_email="a@example.com", user_name="Ada", reset_token="x")
    assert await service.send_password_reset_confirmation_email(to_email="a@example.com", user_name="Ada")

    assert len(sent) == 2
    for message in sent:
        for part in (message["html_content"], message["text_content"]):
            assert "all devices" not in part.lower()
