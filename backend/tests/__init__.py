"""
Tests package
Unit and integration tests for the API

Importing this package under pytest runs the isolation preflight (app.core.target_guard) - the
check the rootdir conftest (backend/conftest.py) runs first - so a run that bypasses that conftest
(--noconftest, another rootdir or confcutdir) is refused here, before any module of the package
is imported. Outside pytest the package is a library of fakes that opens nothing
(scripts/replay_forecast_week.py imports some), and is not judged.

This layer is not the one relied on: under --import-mode=importlib with another rootdir (or
-c /dev/null), pytest names the modules from that rootdir and hands back an empty placeholder for
this package, so this file never runs. tests/conftest.py and app/core/config.py run the same check
whatever the import mode (see target_guard's WHERE IT RUNS).
"""

import sys

if "_pytest" in sys.modules:
    from app.core.target_guard import enforce

    enforce(role="backend-tests", layer="tests/__init__.py")
