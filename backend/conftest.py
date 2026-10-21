"""
The backend test suite's isolation preflight: the first thing pytest loads.

This is the rootdir conftest (the directory of pyproject.toml, which holds the pytest settings).
pytest loads conftest files outermost first, so this one is imported before tests/conftest.py
imports the application, before tests/__init__.py and before any test module. Its first statement
is the check (app/core/target_guard.py): every database and Redis database the run will use,
resolved exactly as the application and the tests resolve them, against the committed allowlist
(app/core/isolation_targets.json). A refused run ends right here with exit 78 and an explanation
that names keys and host:port/database and never a credential - before any database, Redis, HTTP
or provider operation.

It does not depend on how the shell expanded anything, on addopts (the canonical command passes
-o addopts="") or on a plugin being installed. The same check runs again at session start and
after collection, when every test module has read its URLs from the environment, and refuses if
anything governed changed in between. For a run that skips this file, tests/conftest.py runs it as
its first statement and app/core/config.py runs it under pytest when the settings are built, so a
run that loads no conftest at all, or a test file outside tests/, is refused as well.
"""

from app.core.target_guard import enforce

_APPROVED = enforce(role="backend-tests", layer="backend/conftest.py")


def pytest_sessionstart(session):
    enforce(role="backend-tests", layer="pytest_sessionstart")


def pytest_collection_finish(session):
    enforce(role="backend-tests", layer="pytest_collection_finish")


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(_APPROVED.summary_line())
