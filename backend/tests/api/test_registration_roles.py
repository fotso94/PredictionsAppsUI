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


# ------------------------------------------------------------------ approval is not self-service
def test_approval_and_rejection_are_administrator_only():
    """A review the author can perform on their own work is not a review.

    These endpoints used to accept any expert, with a TODO asking for admin-only "once the admin
    system is in place". Nothing changes while EXPERT_DIRECT_PUBLISH is on, because predictions are
    published on creation; it matters when the flag is off, which is exactly when somebody expects a
    real review step.
    """
    from app.api.v1.endpoints import expert
    from app.core.deps import get_current_admin_user

    for name in ("approve_prediction", "reject_prediction"):
        handler = getattr(expert, name)
        dependencies = [
            default.dependency
            for default in handler.__defaults__ or ()
            if hasattr(default, "dependency")
        ]
        assert get_current_admin_user in dependencies, f"{name} must require an administrator"


def test_publishing_itself_is_still_direct_for_experts():
    """The admin-only approval must not have reintroduced a gate in front of publishing."""
    from app.api.v1.endpoints import expert
    from app.core.deps import get_current_admin_user

    dependencies = [
        default.dependency
        for default in expert.create_manual_prediction.__defaults__ or ()
        if hasattr(default, "dependency")
    ]
    assert get_current_admin_user not in dependencies
