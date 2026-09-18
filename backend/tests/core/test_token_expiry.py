"""
Token expiry is compared in UTC on both sides.

`exp` is seconds since the Unix epoch, an absolute instant. Reading it with a naive
`datetime.fromtimestamp` gives the machine's LOCAL time; comparing that against `utcnow()` shifts
every expiry by the machine's UTC offset. West of Greenwich a freshly issued token is rejected; east
of it an expired one is honoured. Either way the machine's timezone decides who can sign in.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.security import (
    create_access_token, create_refresh_token, decode_token, verify_access_token, verify_refresh_token,
)


def _refresh(**kwargs):
    created = create_refresh_token(subject="user-1", **kwargs)
    return created[0] if isinstance(created, tuple) else created


@pytest.mark.parametrize("tz_name", ["America/New_York", "Pacific/Auckland", "UTC"])
def test_a_freshly_issued_token_is_valid_whatever_the_machine_timezone(monkeypatch, tz_name):
    import os, time
    monkeypatch.setitem(os.environ, "TZ", tz_name)
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        token = create_access_token(subject="user-1", role="expert", expires_delta=timedelta(minutes=30))
        assert verify_access_token(token) is not None
        assert verify_refresh_token(_refresh(expires_delta=timedelta(days=7))) is not None
    finally:
        os.environ.pop("TZ", None)
        if hasattr(time, "tzset"):
            time.tzset()


def test_an_expired_token_is_rejected():
    token = create_access_token(subject="user-1", role="expert", expires_delta=timedelta(seconds=-5))
    assert verify_access_token(token) is None


def test_a_short_lived_token_survives_its_whole_lifetime():
    """A 30-minute token used to be rejected on issue in EDT, four hours before it expired."""
    token = create_access_token(subject="user-1", role="expert", expires_delta=timedelta(minutes=30))
    exp = decode_token(token)["exp"]
    remaining = datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(timezone.utc)
    assert timedelta(minutes=29) < remaining <= timedelta(minutes=30)
    assert verify_access_token(token) is not None


def test_a_token_without_an_expiry_is_refused():
    from app.core.security import _is_expired
    assert _is_expired(None) is True
