"""
A test body that reaches for the application's database and every Redis database through the
application alone - it imports nothing from the `tests` package - for the isolation preflight's
regression tests (test_target_guard.py).

guard_canary.py reads TEST_DATABASE_URL from tests.conftest, so importing it runs
tests/__init__.py, which is itself one of the guard's layers. Most test modules never import
`tests.*` (38 of 79 on 2026-10-21), and a run that cuts off the conftest files and the package
__init__ (--noconftest or --confcutdir, under --import-mode=importlib with another rootdir, or a
test file outside tests/ altogether) reaches such a module with no layer of the guard in between
- unless the application's settings judge themselves when they are built. This canary is that
kind of module: if it prints its CANARY line, nothing stopped the run.

It is NOT collected by an ordinary run (its name does not match `test_*.py`); the regression tests
run it by path, in a subprocess, behind tripwires that record and block every connection attempt,
with an environment whose every target is a port nothing listens on. They also copy it outside
tests/ to stand for a collectable file there. Every operation is a read, and the outcome is printed
with exception class names only: a message can carry a URL.
"""

from __future__ import annotations

import json


def test_canary_reaches_the_application_services():
    # app.core.redis before app.core.config, on purpose: the settings are then first built from
    # inside a half-imported app.core.redis, the order tests/test_cache_services.py meets them in,
    # and the preflight must still judge them (and refuse with exit 78, not fail to import).
    from app.core.redis import get_redis_client
    from sqlalchemy import create_engine, text

    from app.core.config import settings

    outcomes = {}
    engine = create_engine(settings.DATABASE_URL, connect_args={"connect_timeout": 2})
    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
        outcomes["settings_database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - the class name is the whole report
        outcomes["settings_database"] = type(exc).__name__
    finally:
        engine.dispose()
    for db in (None, settings.REDIS_DB_SESSIONS):
        try:
            get_redis_client(db).ping()
            outcomes[f"redis_{db}"] = "ok"
        except Exception as exc:  # noqa: BLE001
            outcomes[f"redis_{db}"] = type(exc).__name__
    print("CANARY " + json.dumps(outcomes, sort_keys=True), flush=True)
