"""
A test body that reaches for every service a backend test can reach: the canary of the isolation
preflight's regression tests (test_target_guard.py).

It is NOT collected by an ordinary run - its name does not match `test_*.py` - and is only ever run
by path, in a subprocess, by those regression tests:

- behind network tripwires (every socket connect and name lookup, `psycopg2.connect` and the httpx
  transports are recorded and blocked), to show that a configuration the preflight refuses never
  reaches a test body: a refused run prints no CANARY line and records no attempt;
- without tripwires, against the throwaway PostgreSQL and Redis only, to show that an approved
  configuration really runs and really reaches them.

Every operation is a read (`SELECT current_database()`, Redis `INFO server`, one HTTP GET to a
port nothing listens on), and the outcome is printed as one JSON line with exception class names
only: a message can carry a URL.
"""

from __future__ import annotations

import json
import os


def _database(url: str) -> dict:
    from sqlalchemy import create_engine, text

    engine = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as connection:
            name, port = connection.execute(text("select current_database(), inet_server_port()")).one()
        return {"ok": True, "database": name, "port": int(port)}
    except Exception as exc:  # noqa: BLE001 - the class name is the whole report
        return {"ok": False, "error": type(exc).__name__}
    finally:
        engine.dispose()


def _redis(db) -> dict:
    from app.core.redis import get_redis_client

    try:
        client = get_redis_client(db)
        info = client.info("server")
        return {"ok": True, "port": int(info["tcp_port"]), "db": client.connection_pool.connection_kwargs.get("db")}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": type(exc).__name__}


def test_canary_reaches_every_service():
    from app.core.config import settings
    from tests.conftest import TEST_DATABASE_URL

    outcomes = {
        "test_database": _database(TEST_DATABASE_URL),
        "settings_database": _database(settings.DATABASE_URL),
        "redis_default": _redis(None),
    }
    for role in ("SESSIONS", "PREDICTIONS", "EXPERT_TOOLS", "ML_MODELS", "MATCH_DATA", "RATE_LIMIT"):
        outcomes[f"redis_{role.lower()}"] = _redis(getattr(settings, f"REDIS_DB_{role}"))
    http_url = os.environ.get("GUARD_CANARY_HTTP_URL")
    if http_url:
        import httpx

        try:
            httpx.get(http_url, timeout=2)
            outcomes["http"] = {"ok": True}
        except Exception as exc:  # noqa: BLE001
            outcomes["http"] = {"ok": False, "error": type(exc).__name__}
    print("CANARY " + json.dumps(outcomes, sort_keys=True), flush=True)
