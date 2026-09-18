"""
Public registration must not hand out administrator accounts.

The endpoint is unauthenticated and its response includes a signed token, so accepting `role`
verbatim meant anyone who could reach the API could mint an administrator and be logged in as one in
the same request. Reproduced against the running local backend before the fix: HTTP 201 with an
access token whose `role` claim was "admin".

Experts stay self-selectable on purpose: Phase 1 has experts publish directly. That grants
permission to publish, not reviewed credentials.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.auth import register
from app.core.deps import get_db
from app.main import app


@pytest.fixture
def client():
    """A client whose database is a stub: registration must be refused before any row is written."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    app.dependency_overrides[get_db] = lambda: db
    from app.db.session import get_db as session_get_db
    app.dependency_overrides[session_get_db] = lambda: db
    with TestClient(app) as test_client:
        test_client.db = db
        yield test_client
    app.dependency_overrides.clear()


def _payload(role: str) -> dict:
    return {
        "email": f"role-probe-{role}@example.com",
        "username": f"role_probe_{role}",
        "password": "NotARealPassword!2026",
        "first_name": "Role",
        "last_name": "Probe",
        "role": role,
    }


@pytest.mark.parametrize("role", ["admin", "ADMIN", "Admin", "superuser", "owner", ""])
def test_a_stranger_cannot_sign_themselves_up_as_an_administrator(client, role):
    response = client.post("/api/v1/auth/register", json=_payload(role))
    assert response.status_code == 400, response.text
    assert "administrator" in response.text.lower() or "role must be one of" in response.text.lower()
    # nothing may be written for a refused role
    client.db.add.assert_not_called()
    client.db.commit.assert_not_called()


def test_the_refusal_says_how_an_administrator_is_actually_granted(client):
    response = client.post("/api/v1/auth/register", json=_payload("admin"))
    detail = response.json()["detail"].lower()
    assert "regular" in detail and "expert" in detail
    assert "existing administrator" in detail


def test_the_self_selectable_roles_are_exactly_regular_and_expert():
    """Pinned as a list so widening it is a deliberate, reviewable edit rather than a slip."""
    import inspect
    source = inspect.getsource(register)
    assert 'SELF_SELECTABLE_ROLES = ["regular", "expert"]' in source
    assert '"admin"' not in source.split("SELF_SELECTABLE_ROLES")[1].split("]")[0]
