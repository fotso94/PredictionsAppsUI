"""
The isolation preflight (app.core.target_guard): what a backend test run may connect to, decided
before anything can connect.

WHY. Two backend runs on 2026-10-20 lost their test settings to an unquoted shell variable - zsh
does not split `env $VARS cmd` - and resolved Redis to the live server from backend/.env, which in
this worktree is a link to the main checkout's live configuration. Nothing stopped them: the only
check was a word in a database name, and that word survives the same slip (the unsplit value
'soccer_predictions_test POSTGRES_DB=... REDIS_HOST=...' still contains "test").

WHAT IS PINNED HERE.
- The decision itself, in-process, over simulated settings: a live `.env` is simulated by a temp
  file with the same keys and fake secrets; the real one is never read by these tests. Every
  unit test runs behind a tripwire that fails it on any socket connect, `psycopg2.connect`, Redis
  connect or httpx request, so the decision is shown to be pure.
- The ORDER, in subprocesses behind tripwires installed before pytest starts: a refused run exits
  78, records no connection attempt of any kind, never imports the application or the inner
  conftest, and never reaches a test body (tests/core/guard_canary.py, whose only job is to reach
  for every service). The unsafe targets are simulated on ports nothing listens on and on
  TEST-NET-1 (192.0.2.1), so that even a tripwire that failed could reach nothing live.
- A real run against the throwaway services (guard-test-redis :6390, guard-race-pg :5440) when
  they are given (LEASE_TEST_REDIS_URL and RACE_TEST_DATABASE_URL), without tripwires.

The guard module is imported inside each test, not at the top, so that a run on code without it
reports each test's own failure rather than one collection error.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

BACKEND = Path(__file__).resolve().parents[2]
TESTS = BACKEND / "tests"
CANARY = "tests/core/guard_canary.py"
EXIT_REFUSED = 78

SETTINGS_KEYS = (
    "DATABASE_URL", "POSTGRES_SERVER", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
    "REDIS_URL", "REDIS_HOST", "REDIS_PORT", "REDIS_DB", "REDIS_PASSWORD",
    "REDIS_DB_SESSIONS", "REDIS_DB_PREDICTIONS", "REDIS_DB_EXPERT_TOOLS", "REDIS_DB_ML_MODELS",
    "REDIS_DB_MATCH_DATA", "REDIS_DB_RATE_LIMIT", "SYNC_SCHEDULER_ENABLED", "EMAIL_ENABLED",
    "LIVESCORE_API_KEY", "LIVESCORE_API_SECRET", "GAMEFORECAST_API_KEY", "API_FOOTBALL_KEY", "THESPORTSDB_KEY",
)
TEST_KEYS = ("TEST_DATABASE_URL", "RACE_TEST_DATABASE_URL", "LEASE_TEST_REDIS_URL")
PG_KEYS = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGSERVICE", "PGSERVICEFILE")
GOVERNED = SETTINGS_KEYS + TEST_KEYS + PG_KEYS
ROLE_KEYS = ("REDIS_DB_SESSIONS", "REDIS_DB_PREDICTIONS", "REDIS_DB_EXPERT_TOOLS", "REDIS_DB_ML_MODELS",
             "REDIS_DB_MATCH_DATA", "REDIS_DB_RATE_LIMIT")

#: The shape of backend/.env in this worktree (a link to the main checkout's live configuration):
#: the same keys, the live targets, and secrets that are made up here.
LIVE_DOTENV = (
    'POSTGRES_SERVER="localhost"\nPOSTGRES_PORT=5432\nPOSTGRES_USER="postgres"\n'
    'POSTGRES_PASSWORD="dotenv-password-not-real"\nPOSTGRES_DB="soccer_predictions"\n'
    'REDIS_HOST="localhost"\nREDIS_PORT=6379\nREDIS_DB=0\nEMAIL_ENABLED=true\n'
    'LIVESCORE_API_KEY="dotenv-key-not-real"\n'
)
SECRETS = ("dotenv-password-not-real", "dotenv-key-not-real", "url-password-not-real")

TEST_URL = "postgresql://postgres:url-password-not-real@localhost:5432/soccer_predictions_test"
#: The canonical backend command's settings (backend/README.md, "Testing").
APPROVED = {
    "TEST_DATABASE_URL": TEST_URL, "POSTGRES_DB": "soccer_predictions_test",
    "REDIS_HOST": "127.0.0.1", "REDIS_PORT": "6390",
    "SYNC_SCHEDULER_ENABLED": "false", "EMAIL_ENABLED": "false",
}
THROWAWAY = {
    "LEASE_TEST_REDIS_URL": "redis://127.0.0.1:6390/9",
    "RACE_TEST_DATABASE_URL": "postgresql://postgres@127.0.0.1:5440/forecast_race_test",
}
#: scripts/local-servers.sh ISOLATED_ENV, as the isolated backend (:8001) is started.
ISOLATED = {
    "POSTGRES_DB": "soccer_predictions_e2e", "SYNC_SCHEDULER_ENABLED": "false", "EMAIL_ENABLED": "false",
    "LIVESCORE_API_KEY": "", "LIVESCORE_API_SECRET": "", "GAMEFORECAST_API_KEY": "", "API_FOOTBALL_KEY": "",
    "THESPORTSDB_KEY": "", "REDIS_HOST": "localhost", "REDIS_PORT": "6379", "REDIS_DB": "10",
    **{key: str(10 + index) for index, key in enumerate(ROLE_KEYS)},
}


def guard():
    return importlib.import_module("app.core.target_guard")


# ================================================================================ tripwires
class Tripped(AssertionError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any connection attempt from these tests is a failure, whatever it is aimed at."""
    attempts = []

    def trip(kind):
        def tripped(*args, **kwargs):
            attempts.append(kind)
            raise Tripped(f"{kind} attempted from a target-guard test")
        return tripped

    monkeypatch.setattr(socket.socket, "connect", trip("socket.connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", trip("socket.connect_ex"))
    monkeypatch.setattr(socket, "create_connection", trip("socket.create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", trip("socket.getaddrinfo"))
    import httpx
    import psycopg2
    import redis.connection

    monkeypatch.setattr(psycopg2, "connect", trip("psycopg2.connect"))
    monkeypatch.setattr(redis.connection.Connection, "connect", trip("redis connect"))
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", trip("httpx"))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", trip("httpx async"))
    yield attempts
    assert attempts == [], f"connection attempts: {attempts}"


@pytest.fixture
def judge(monkeypatch, tmp_path):
    """evaluate() over a clean environment plus the given keys, with the simulated live .env."""
    from app.core.config import Settings

    dotenv = tmp_path / "simulated-live.env"
    dotenv.write_text(LIVE_DOTENV, encoding="utf-8")
    for key in list(os.environ):
        if key.upper() in GOVERNED:
            monkeypatch.delenv(key)

    def run(role="backend-tests", dotenv_text=None, **env):
        if dotenv_text is not None:
            dotenv.write_text(dotenv_text, encoding="utf-8")
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return guard().evaluate(role=role, environ=dict(os.environ),
                                settings_factory=lambda: Settings(_env_file=str(dotenv)))

    return run


def without(mapping, *keys):
    return {key: value for key, value in mapping.items() if key not in keys}


def assert_clean_report(verdict):
    report = verdict.report()
    for secret in SECRETS:
        assert secret not in report
    return report


# ================================================================================ approved
def test_the_canonical_backend_command_passes(judge):
    verdict = judge(**APPROVED)
    assert verdict.ok, verdict.report()
    assert verdict.targets["test database"] == "localhost:5432/soccer_predictions_test"
    assert verdict.targets["settings database"] == "localhost:5432/soccer_predictions_test"
    assert verdict.targets["redis default (REDIS_DB)"] == "127.0.0.1:6390/0"
    assert verdict.targets["redis REDIS_DB_RATE_LIMIT"] == "127.0.0.1:6390/5"
    line = verdict.summary_line()
    assert "approved" in line and "soccer_predictions_test" in line and "url-password-not-real" not in line


def test_the_throwaway_services_pass_beside_it(judge):
    verdict = judge(**APPROVED, **THROWAWAY)
    assert verdict.ok, verdict.report()
    assert verdict.targets["race database"] == "127.0.0.1:5440/forecast_race_test"
    assert verdict.targets["lease redis"] == "127.0.0.1:6390/9,10,11"


def test_the_throwaway_postgres_alone_passes(judge):
    url = "postgresql://postgres@127.0.0.1:5440/forecast_race_test"
    verdict = judge(TEST_DATABASE_URL=url, POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT="5440",
                    POSTGRES_DB="forecast_race_test", REDIS_HOST="localhost", REDIS_PORT="6390",
                    SYNC_SCHEDULER_ENABLED="0", EMAIL_ENABLED="no")
    assert verdict.ok, verdict.report()


def test_the_isolated_backend_as_started_passes_its_own_role(judge):
    verdict = judge(role="isolated-backend", **ISOLATED)
    assert verdict.ok, verdict.report()
    assert verdict.targets["settings database"] == "localhost:5432/soccer_predictions_e2e"
    assert verdict.targets["redis default (REDIS_DB)"] == "localhost:6379/10"
    assert {verdict.targets[f"redis {key}"] for key in ROLE_KEYS} == {f"localhost:6379/{db}" for db in range(10, 16)}


# ================================================================================ missing
def test_nothing_exported_is_refused_naming_everything_missing(judge):
    """The state the unsplit variable left behind: every setting from the live .env."""
    verdict = judge()
    assert not verdict.ok
    assert {"missing:TEST_DATABASE_URL", "missing:database", "missing:redis",
            "missing:SYNC_SCHEDULER_ENABLED", "missing:EMAIL_ENABLED"} <= verdict.codes
    assert {"live-database", "live-redis"} <= verdict.codes
    report = assert_clean_report(verdict)
    assert "Nothing has connected" in report


@pytest.mark.parametrize("dropped, code", [
    ("TEST_DATABASE_URL", "missing:TEST_DATABASE_URL"),
    ("POSTGRES_DB", "missing:database"),
    ("REDIS_HOST", "missing:redis"),
    ("REDIS_PORT", "missing:redis"),
    ("SYNC_SCHEDULER_ENABLED", "missing:SYNC_SCHEDULER_ENABLED"),
    ("EMAIL_ENABLED", "missing:EMAIL_ENABLED"),
])
def test_each_missing_override_is_refused(judge, dropped, code):
    verdict = judge(**without(APPROVED, dropped))
    assert code in verdict.codes, verdict.report()
    assert dropped in assert_clean_report(verdict)


def test_an_empty_value_counts_as_missing(judge):
    """REDIS_HOST="" would make redis-py fall back to localhost: present is not enough."""
    verdict = judge(**{**APPROVED, "REDIS_HOST": ""})
    assert "missing:redis" in verdict.codes


def test_a_lowercase_spelling_is_not_the_setting(judge):
    """Settings are case-sensitive, so redis_port=6390 is ignored and REDIS_PORT comes from .env."""
    verdict = judge(**without(APPROVED, "REDIS_PORT"), redis_port="6390")
    assert {"missing:redis", "conflict:case-variant", "live-redis"} <= verdict.codes


def test_the_isolated_backend_needs_every_redis_database_written_down(judge):
    """Without REDIS_DB the default client keeps .env's 0 - the live sessions database - which is
    how the isolated backend was started until this guard existed."""
    verdict = judge(role="isolated-backend", **without(ISOLATED, "REDIS_DB"))
    assert "missing:redis-db" in verdict.codes
    assert "live-redis" in verdict.codes
    assert "REDIS_DB" in verdict.report()


def test_the_isolated_backend_needs_blank_provider_keys(judge):
    verdict = judge(role="isolated-backend", **without(ISOLATED, "LIVESCORE_API_KEY"))
    assert "missing:provider-blank" in verdict.codes
    assert "dotenv-key-not-real" not in verdict.report()


# ================================================================================ live databases
@pytest.mark.parametrize("name", ["soccer_predictions", "soccer_predictions_dev", "soccer_predictions_qa"])
@pytest.mark.parametrize("where", ["TEST_DATABASE_URL", "POSTGRES_DB", "DATABASE_URL"])
def test_a_live_database_is_refused_on_any_host_and_port(judge, name, where):
    url = f"postgresql://postgres@127.0.0.1:5999/{name}"
    env = dict(APPROVED)
    if where == "TEST_DATABASE_URL":
        env.update(TEST_DATABASE_URL=url, POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT="5999", POSTGRES_DB=name)
    elif where == "POSTGRES_DB":
        env.update(POSTGRES_DB=name)
    else:
        env = without(env, "POSTGRES_DB")
        env.update(DATABASE_URL=url)
    verdict = judge(**env)
    assert "live-database" in verdict.codes, verdict.report()
    assert name in assert_clean_report(verdict)


def test_the_isolated_pairs_database_is_not_for_backend_tests(judge):
    verdict = judge(**{**APPROVED, "POSTGRES_DB": "soccer_predictions_e2e",
                       "TEST_DATABASE_URL": "postgresql://postgres@localhost:5432/soccer_predictions_e2e"})
    assert "isolated-pair-database" in verdict.codes


@pytest.mark.parametrize("name", ["soccer_predictions_test_mine", "my_test", "soccer_predictions_20251008_backup"])
def test_a_name_that_merely_says_test_is_not_approved(judge, name):
    verdict = judge(**{**APPROVED, "POSTGRES_DB": name,
                       "TEST_DATABASE_URL": f"postgresql://postgres@localhost:5432/{name}"})
    assert "unapproved-database" in verdict.codes


@pytest.mark.parametrize("host", ["postgres", "test-db.internal", "192.0.2.1", "0.0.0.0"])
def test_only_a_loopback_host_is_approved(judge, host):
    verdict = judge(**{**APPROVED, "POSTGRES_SERVER": host,
                       "TEST_DATABASE_URL": f"postgresql://postgres@{host}:5432/soccer_predictions_test"})
    assert "unapproved-database" in verdict.codes


# ================================================================================ live Redis
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "192.0.2.1"])
def test_the_live_redis_server_is_refused_on_any_host(judge, host):
    verdict = judge(**{**APPROVED, "REDIS_HOST": host, "REDIS_PORT": "6379"})
    assert "live-redis" in verdict.codes, verdict.report()


def test_a_bare_ipv6_redis_host_is_refused_as_unreadable(judge):
    """Settings build redis://::1:6379/0 from it, which names no port redis-py can read."""
    verdict = judge(**{**APPROVED, "REDIS_HOST": "::1", "REDIS_PORT": "6379"})
    assert "conflict:redis-url-form" in verdict.codes


@pytest.mark.parametrize("db", ["0", "3", "5"])
def test_a_live_redis_database_named_by_url_is_refused(judge, db):
    verdict = judge(**without(APPROVED, "REDIS_HOST", "REDIS_PORT"), REDIS_URL=f"redis://127.0.0.1:6379/{db}")
    assert "live-redis" in verdict.codes


def test_the_isolated_pairs_redis_databases_are_not_for_backend_tests(judge):
    env = {**APPROVED, "REDIS_PORT": "6379", "REDIS_DB": "10", **{key: str(10 + i) for i, key in enumerate(ROLE_KEYS)}}
    verdict = judge(**env)
    assert "isolated-pair-redis" in verdict.codes


def test_every_redis_database_the_application_uses_is_judged(judge):
    """One role on a live database is enough to refuse, and the report names that role."""
    verdict = judge(role="isolated-backend", **{**ISOLATED, "REDIS_DB_RATE_LIMIT": "5"})
    assert "live-redis" in verdict.codes
    assert "REDIS_DB_RATE_LIMIT" in verdict.report()


def test_the_lease_tests_may_not_use_the_live_server(judge):
    verdict = judge(**APPROVED, LEASE_TEST_REDIS_URL="redis://127.0.0.1:6379/9")
    assert "isolated-pair-redis" in verdict.codes or "unapproved-redis" in verdict.codes


# ================================================================================ conflicts
def test_a_database_url_from_dotenv_silently_overriding_postgres_db_is_refused(judge):
    verdict = judge(dotenv_text=LIVE_DOTENV + 'DATABASE_URL="postgresql://postgres:x@localhost:5432/soccer_predictions"\n',
                    **APPROVED)
    assert "conflict:dotenv-database-url" in verdict.codes
    assert "live-database" in verdict.codes


def test_database_url_and_postgres_parts_that_disagree_are_refused(judge):
    verdict = judge(**APPROVED, DATABASE_URL="postgresql://postgres@127.0.0.1:5440/forecast_race_test")
    assert "conflict:database-url-vs-postgres" in verdict.codes


def test_a_redis_url_from_dotenv_overriding_the_parts_is_refused(judge):
    verdict = judge(dotenv_text=LIVE_DOTENV + 'REDIS_URL="redis://localhost:6379/0"\n', **APPROVED)
    assert "conflict:dotenv-redis-url" in verdict.codes
    assert "live-redis" in verdict.codes


def test_redis_url_and_parts_that_disagree_are_refused(judge):
    verdict = judge(**APPROVED, REDIS_URL="redis://127.0.0.1:6391/0")
    assert "conflict:redis-url-vs-parts" in verdict.codes


@pytest.mark.parametrize("url", [
    "redis://127.0.0.1:6390/3?db=0",     # redis-py lets ?db= win over the path
    "redis://127.0.0.1:6390",            # no path: get_redis_client's rsplit makes "redis://127.0.0.1:6390/N" of
                                         # it today, but "redis://12" of "redis://127.0.0.1:6390" minus a slash
    "redis://:6390/0",                   # no host: falls back to localhost
    "unix:///tmp/redis.sock?db=0",
])
def test_a_redis_url_not_of_the_one_exact_form_is_refused(judge, url):
    verdict = judge(**without(APPROVED, "REDIS_HOST", "REDIS_PORT"), REDIS_URL=url)
    assert "conflict:redis-url-form" in verdict.codes


def test_the_tests_and_the_application_must_use_one_database(judge):
    """The TestClient lifespan connects with settings.DATABASE_URL, not TEST_DATABASE_URL."""
    verdict = judge(**{**APPROVED, "POSTGRES_DB": "forecast_race_test"})
    assert "conflict:test-vs-settings-database" in verdict.codes


def test_two_redis_roles_on_one_database_are_refused(judge):
    verdict = judge(**APPROVED, REDIS_DB_SESSIONS="3", REDIS_DB_PREDICTIONS="3")
    assert "conflict:redis-db-collision" in verdict.codes


def test_a_redis_database_out_of_range_is_refused(judge):
    verdict = judge(**APPROVED, REDIS_DB_ML_MODELS="16")
    assert "conflict:redis-db-range" in verdict.codes


def test_the_race_database_may_not_be_the_test_database(judge):
    """The race tests TRUNCATE ... CASCADE every table."""
    verdict = judge(**APPROVED, RACE_TEST_DATABASE_URL=TEST_URL)
    assert "conflict:race-same-as-test" in verdict.codes


def test_the_lease_databases_may_not_overlap_the_applications(judge):
    """The lease tests flush databases d, d+1 and d+2."""
    verdict = judge(**APPROVED, LEASE_TEST_REDIS_URL="redis://127.0.0.1:6390/4")
    assert "conflict:lease-overlaps-application" in verdict.codes


def test_the_unsplit_shell_variable_is_refused_without_echoing_it(judge):
    """zsh's `env $V cmd` sets ONE variable to the whole string and leaves the rest unset."""
    joined = (TEST_URL + " POSTGRES_DB=soccer_predictions_test REDIS_HOST=127.0.0.2 REDIS_PORT=6390 "
              "SYNC_SCHEDULER_ENABLED=false EMAIL_ENABLED=false")
    verdict = judge(TEST_DATABASE_URL=joined)
    assert "conflict:unsplit-value" in verdict.codes
    report = assert_clean_report(verdict)
    # The key is named; nothing of the value is (127.0.0.2 appears only inside it).
    assert "TEST_DATABASE_URL" in report and "127.0.0.2" not in report


@pytest.mark.parametrize("url", [
    "postgresql://postgres@127.0.0.1:5440/forecast_race_test?host=localhost&port=5432&dbname=soccer_predictions",
    "postgresql://postgres@127.0.0.1/forecast_race_test",
    "postgresql://postgres@127.0.0.1:5440/forecast_race_test?service=live",
])
def test_a_postgres_url_whose_parameters_redirect_it_is_refused(judge, url):
    verdict = judge(**{**APPROVED, "TEST_DATABASE_URL": url})
    assert "conflict:postgres-url" in verdict.codes


def test_the_redirect_is_judged_where_it_really_goes(judge):
    url = "postgresql://postgres@127.0.0.1:5440/forecast_race_test?host=localhost&port=5432&dbname=soccer_predictions"
    verdict = judge(**{**APPROVED, "TEST_DATABASE_URL": url})
    assert "live-database" in verdict.codes


@pytest.mark.parametrize("key", PG_KEYS)
def test_libpq_environment_overrides_are_refused(judge, key):
    verdict = judge(**APPROVED, **{key: "localhost"})
    assert "conflict:pg-environment" in verdict.codes


def test_settings_resolved_before_the_environment_changed_are_refused(judge, monkeypatch, tmp_path):
    """A settings object built from other values than the ones every module will read."""
    from app.core.config import Settings

    stale_env = tmp_path / "stale.env"
    stale_env.write_text(LIVE_DOTENV, encoding="utf-8")
    for key, value in APPROVED.items():
        monkeypatch.setenv(key, value)
    stale = Settings(_env_file=str(stale_env))
    monkeypatch.setenv("REDIS_PORT", "6391")
    verdict = guard().evaluate(role="backend-tests", environ=dict(os.environ), settings_factory=lambda: stale)
    assert "conflict:settings-differ" in verdict.codes


@pytest.mark.parametrize("key", ["SYNC_SCHEDULER_ENABLED", "EMAIL_ENABLED"])
def test_the_scheduler_and_email_must_be_off(judge, key):
    verdict = judge(**{**APPROVED, key: "true"})
    assert f"flag:{key}" in verdict.codes


def test_unparseable_settings_are_refused_without_their_values(judge):
    verdict = judge(**{**APPROVED, "REDIS_PORT": "six-three-nine-zero"})
    assert "malformed:settings" in verdict.codes
    assert "six-three-nine-zero" not in verdict.report()


# ================================================================================ the policy
def test_the_committed_policy_is_self_consistent():
    policy = guard().load_policy()
    assert policy["format"] == "isolation-targets/1"
    assert guard().policy_problems(policy) == []


def test_a_policy_approving_a_live_target_is_itself_refused(judge):
    policy = json.loads(json.dumps(guard().load_policy()))
    policy["roles"]["backend-tests"]["postgres"]["test"].append(
        {"host": "loopback", "port": 5432, "database": "soccer_predictions"})
    assert guard().policy_problems(policy)
    from app.core.config import Settings
    verdict = guard().evaluate(role="backend-tests", environ={}, policy=policy,
                               settings_factory=lambda: Settings(_env_file=None))
    assert verdict.codes == {"policy:invalid"}


def test_a_missing_policy_file_refuses(tmp_path):
    with pytest.raises(guard().PolicyError):
        guard().load_policy(tmp_path / "nowhere.json")


def test_an_unknown_role_is_refused(judge):
    assert "policy:invalid" in judge(role="anything-goes", **APPROVED).codes


# ================================================================================ purity
def test_importing_the_guard_loads_no_driver_and_no_application():
    code = ("import sys, app.core.target_guard; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('psycopg2', 'redis', 'httpx', 'fastapi', 'sqlalchemy', 'app')))")
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=60,
                         env=minimal_env())
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.replace("'", '"')) == ["app", "app.core", "app.core.target_guard"]


def test_the_redis_url_helper_is_the_one_get_redis_client_uses():
    from redis.connection import parse_url

    from app.core.config import settings
    from app.core.redis import get_redis_client, redis_url_for

    for db in (None, settings.REDIS_DB, 3, 15):
        kwargs = get_redis_client(db).connection_pool.connection_kwargs
        parsed = parse_url(redis_url_for(db))
        assert (kwargs.get("host"), kwargs.get("port"), kwargs.get("db")) == \
               (parsed.get("host"), parsed.get("port"), parsed.get("db"))


def test_every_test_directory_is_a_package():
    """tests/__init__.py runs the guard; a directory without __init__.py imports its modules as
    top-level names and would skip it."""
    bare = sorted(str(path.relative_to(BACKEND)) for path in TESTS.rglob("*")
                  if path.is_dir() and path.name != "__pycache__" and any(path.glob("test_*.py"))
                  and not (path / "__init__.py").exists())
    assert bare == []


# ================================================================================ the order, in subprocesses
#: Installed before pytest starts. Everything it sees is recorded as one JSON line and blocked.
BOOT = r'''
import json, os, sys
LOG = os.environ["GUARD_TRIPWIRE_LOG"]
def note(kind, target):
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": kind, "target": str(target)}) + "\n")
def audit(event, args):
    if event == "socket.connect":
        address = args[1]
        note("socket.connect", f"{address[0]}:{address[1]}" if isinstance(address, tuple) else address)
        raise ConnectionRefusedError("tripwire: socket.connect blocked")
    if event == "socket.getaddrinfo":
        note("socket.getaddrinfo", f"{args[0]}:{args[1]}")
        raise OSError("tripwire: getaddrinfo blocked")
    if event == "import" and args[0] in ("app.main", "tests.conftest", "app.db.session"):
        note("import", args[0])
sys.addaudithook(audit)
import psycopg2
def connect(*args, **kwargs):
    note("psycopg2.connect", f"{kwargs.get('host')}:{kwargs.get('port')}/{kwargs.get('dbname')}")
    raise psycopg2.OperationalError("tripwire: psycopg2.connect blocked")
psycopg2.connect = connect
import httpx
def handle(self, request):
    note("httpx", f"{request.url.host}:{request.url.port}")
    raise httpx.ConnectError("tripwire: httpx blocked")
async def handle_async(self, request):
    note("httpx", f"{request.url.host}:{request.url.port}")
    raise httpx.ConnectError("tripwire: httpx blocked")
httpx.HTTPTransport.handle_request = handle
httpx.AsyncHTTPTransport.handle_async_request = handle_async
mode, args = sys.argv[1], sys.argv[2:]
if mode == "cli":
    import runpy
    sys.argv = ["app.core.target_guard", *args]
    runpy.run_module("app.core.target_guard", run_name="__main__")
    raise SystemExit(0)
plugins = []
if os.environ.get("GUARD_TAMPER_AFTER_START"):
    class Tamper:
        def pytest_collectstart(self, collector):
            os.environ["POSTGRES_DB"] = os.environ["GUARD_TAMPER_AFTER_START"]
    plugins.append(Tamper())
import pytest
raise SystemExit(pytest.main(args, plugins=plugins))
'''

#: -rP shows a passing test's captured output, so the CANARY line is visible without -s (capture stays on,
#: as in every real run).
PYTEST_ARGS = ["-q", "-rP", "-p", "no:cacheprovider", "-o", "addopts=", CANARY]


def minimal_env(**env):
    base = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR") if key in os.environ}
    base.update(PYTHONDONTWRITEBYTECODE="1", **env)
    return base


def free_port() -> int:
    """A port nothing listens on (bind, never connect: the tripwire is on connect)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def tripwired(tmp_path, env, mode="pytest", args=PYTEST_ARGS):
    log = tmp_path / "tripwire.jsonl"
    log.touch()
    out = subprocess.run([sys.executable, "-c", BOOT, mode, *args], cwd=BACKEND, capture_output=True, text=True,
                         timeout=180, env=minimal_env(GUARD_TRIPWIRE_LOG=str(log), **env))
    entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    return out.returncode, out.stdout + out.stderr, entries


SUBPROCESS_PASSWORD = "subprocess-password-not-real"


def approved_subprocess_env(dead: int):
    """Approved targets: the throwaway PostgreSQL and Redis. Behind the tripwires nothing reaches them."""
    return dict(TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:5440/forecast_race_test",
                POSTGRES_SERVER="127.0.0.1", POSTGRES_PORT="5440", POSTGRES_DB="forecast_race_test",
                POSTGRES_USER="postgres", POSTGRES_PASSWORD=SUBPROCESS_PASSWORD, REDIS_HOST="127.0.0.1",
                REDIS_PORT="6390", SYNC_SCHEDULER_ENABLED="false", EMAIL_ENABLED="false",
                GUARD_CANARY_HTTP_URL=f"http://127.0.0.1:{dead}/")


def unsafe_scenarios(dead: int):
    """(name, how the approved environment is changed, words the refusal must contain). Every
    unsafe target is on a port nothing listens on or on TEST-NET-1, never on a live service."""
    on_6379 = {"REDIS_HOST": "192.0.2.1", "REDIS_PORT": "6379"}
    return [
        ("missing TEST_DATABASE_URL", {"TEST_DATABASE_URL": None}, "TEST_DATABASE_URL is not set"),
        ("missing scheduler switch", {"SYNC_SCHEDULER_ENABLED": None}, "SYNC_SCHEDULER_ENABLED is not set"),
        ("live database by name",
         {"TEST_DATABASE_URL": f"postgresql://postgres@127.0.0.1:{dead}/soccer_predictions",
          "POSTGRES_PORT": str(dead), "POSTGRES_DB": "soccer_predictions"}, "live database"),
        ("live Redis server", on_6379, "live Redis"),
        ("the isolated pair's Redis databases",
         {**on_6379, "REDIS_DB": "10", **{key: str(10 + i) for i, key in enumerate(ROLE_KEYS)}}, "isolated pair"),
        ("conflicting REDIS_URL", {"REDIS_URL": "redis://127.0.0.1:6390/3?db=0"}, "REDIS_URL"),
        ("conflicting URL parameters",
         {"TEST_DATABASE_URL": "postgresql://postgres@127.0.0.1:5440/forecast_race_test"
                               f"?host=127.0.0.1&port={dead}&dbname=soccer_predictions"}, "parameter"),
        ("conflicting test and settings databases", {"POSTGRES_PORT": str(dead)}, "not the database"),
        ("an unsplit shell variable",
         {"TEST_DATABASE_URL": "postgresql://postgres@127.0.0.1:5440/forecast_race_test "
                               "POSTGRES_DB=forecast_race_test REDIS_HOST=127.0.0.1"}, "whitespace"),
    ]


def apply(env, changes):
    env = dict(env)
    for key, value in changes.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


SCENARIO_NAMES = [name for name, _, _ in unsafe_scenarios(1)]


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_a_refused_run_stops_before_any_connection_import_or_test(tmp_path, name):
    dead = free_port()
    _, changes, words = next(s for s in unsafe_scenarios(dead) if s[0] == name)
    code, output, entries = tripwired(tmp_path, apply(approved_subprocess_env(dead), changes))
    assert entries == [], f"attempted before the refusal: {entries}\n{output[-3000:]}"
    assert code == EXIT_REFUSED, output[-3000:]
    assert "CANARY" not in output
    assert "REFUSED" in output and words in output, output[-3000:]
    assert "Nothing has connected" in output
    assert "url-password-not-real" not in output and SUBPROCESS_PASSWORD not in output


def test_the_tests_package_refuses_when_the_rootdir_conftest_is_bypassed(tmp_path):
    dead = free_port()
    env = apply(approved_subprocess_env(dead), {"POSTGRES_DB": "soccer_predictions", "POSTGRES_PORT": str(dead),
                                               "TEST_DATABASE_URL": f"postgresql://postgres@127.0.0.1:{dead}/soccer_predictions"})
    code, output, entries = tripwired(tmp_path, env, args=["--noconftest", *PYTEST_ARGS])
    assert entries == [], entries
    assert code == EXIT_REFUSED, output[-3000:]
    assert "tests/__init__.py" in output and "CANARY" not in output


def test_a_change_after_the_check_is_refused_before_any_test(tmp_path):
    """The environment is changed after the rootdir conftest approved it, before collection ends."""
    dead = free_port()
    env = approved_subprocess_env(dead)
    code, output, entries = tripwired(tmp_path, {**env, "GUARD_TAMPER_AFTER_START": "soccer_predictions"})
    assert [e for e in entries if e["kind"] != "import"] == [], entries
    assert code == EXIT_REFUSED, output[-3000:]
    assert "CANARY" not in output and "REFUSED" in output


def test_the_command_line_check_refuses_and_approves_without_connecting(tmp_path):
    dead = free_port()
    unsafe = apply(approved_subprocess_env(dead), {"REDIS_HOST": "192.0.2.1", "REDIS_PORT": "6379"})
    code, output, entries = tripwired(tmp_path, unsafe, mode="cli", args=["--role", "backend-tests", "--json"])
    assert entries == [] and code == EXIT_REFUSED, output[-2000:]
    verdict = json.loads(output[output.index("{"):output.rindex("}") + 1])
    assert verdict["ok"] is False and "live-redis" in verdict["codes"]
    (tmp_path / "tripwire.jsonl").unlink()
    code, output, entries = tripwired(tmp_path, approved_subprocess_env(dead), mode="cli",
                                      args=["--role", "backend-tests", "--json"])
    assert entries == [] and code == 0, output[-2000:]
    assert json.loads(output[output.index("{"):output.rindex("}") + 1])["ok"] is True


def test_an_approved_run_reaches_the_test_body_and_only_approved_targets(tmp_path):
    dead = free_port()
    code, output, entries = tripwired(tmp_path, approved_subprocess_env(dead))
    assert code == 0, output[-3000:]
    assert "CANARY" in output
    attempted = {(e["kind"], e["target"]) for e in entries if e["kind"] != "import"}
    assert attempted, "the canary reached for nothing"
    allowed = {"127.0.0.1:5440/forecast_race_test", "127.0.0.1:6390", f"127.0.0.1:{dead}"}
    assert {target for _, target in attempted} <= allowed, attempted
    # The tripwires really sit in front of the database driver, Redis and HTTP: each was caught.
    assert {"psycopg2.connect", "socket.getaddrinfo", "httpx"} <= {kind for kind, _ in attempted}, attempted


# ================================================================================ real throwaway services
REAL_RACE = os.environ.get("RACE_TEST_DATABASE_URL")
REAL_LEASE = os.environ.get("LEASE_TEST_REDIS_URL")


@pytest.mark.skipif(not (REAL_RACE and REAL_LEASE),
                    reason="RACE_TEST_DATABASE_URL and LEASE_TEST_REDIS_URL are not set: no throwaway services")
def test_an_approved_run_really_reaches_the_throwaway_services(tmp_path):
    database, cache = urlparse(REAL_RACE), urlparse(REAL_LEASE)
    env = minimal_env(
        TEST_DATABASE_URL=REAL_RACE, POSTGRES_SERVER=database.hostname, POSTGRES_PORT=str(database.port),
        POSTGRES_DB=database.path.lstrip("/"), POSTGRES_USER=database.username or "postgres",
        POSTGRES_PASSWORD=database.password or "unused", REDIS_HOST=cache.hostname, REDIS_PORT=str(cache.port),
        SYNC_SCHEDULER_ENABLED="false", EMAIL_ENABLED="false")
    out = subprocess.run([sys.executable, "-m", "pytest", *PYTEST_ARGS], cwd=BACKEND, capture_output=True,
                         text=True, timeout=180, env=env)
    output = out.stdout + out.stderr
    assert out.returncode == 0, output[-3000:]
    canary = json.loads(next(line for line in output.splitlines() if line.startswith("CANARY "))[7:])
    for label in ("test_database", "settings_database"):
        assert canary[label] == {"ok": True, "database": database.path.lstrip("/"), "port": database.port}, canary
    for label, outcome in canary.items():
        if label.startswith("redis_"):
            assert outcome["ok"] and outcome["port"] == cache.port, canary
    assert "target guard: backend-tests approved" in output


# ================================================================================ the bypasses of 2026-10-21
# Three reviewers ran pytest in ways that skip every file the guard used to live in: the rootdir
# conftest and tests/__init__.py. Each case below runs behind the same tripwires as the order tests
# above, with an environment the guard refuses whose every target is a port nothing listens on, and
# demands exit 78 with no connection attempt and no test body reached.
APP_CANARY = "tests/core/guard_canary_app.py"


def refused_env(dead: int):
    """The approved subprocess environment, pointed at the live database's NAME and at a Redis
    server, both on a port nothing listens on: refused by the guard, and harmless without it."""
    return apply(approved_subprocess_env(dead), {
        "POSTGRES_DB": "soccer_predictions", "POSTGRES_PORT": str(dead), "REDIS_PORT": str(dead),
        "TEST_DATABASE_URL": f"postgresql://postgres@127.0.0.1:{dead}/soccer_predictions"})


def assert_refused_before_anything(code, output, entries, layer):
    assert [e for e in entries if e["kind"] != "import"] == [], f"attempted before the refusal: {entries}\n{output[-3000:]}"
    assert code == EXIT_REFUSED, output[-3000:]
    assert "CANARY" not in output, output[-3000:]
    assert "REFUSED" in output and layer in output, output[-3000:]
    assert SUBPROCESS_PASSWORD not in output


def _python_files_outside_tests():
    for root, dirs, files in os.walk(BACKEND):
        here = Path(root)
        dirs[:] = [d for d in dirs if not (d.startswith(("venv", ".venv", ".")) or d in ("__pycache__", "node_modules")
                                           or here / d == TESTS)]
        yield from (here / name for name in files if name.endswith(".py"))


def test_no_file_outside_the_tests_package_is_collectable():
    """scripts/test_connections.py was collected by `pytest --noconftest scripts/test_connections.py`
    (or --confcutdir=scripts): neither guard file runs for a module outside tests/, and its settings
    came from backend/.env - the live database and live Redis databases 0-5, which it writes test
    keys into. The root-level test_*.py files called the live API on :8000 or a real SMTP server.
    They are check_*.py now, run with python as before. Two rules, because pytest collects a file
    named on its command line whatever its name: no file outside tests/ is named like a test module
    (pyproject's python_files, and pytest's own default when -c points elsewhere), and no module
    outside tests/ and app/ defines a test function or class. (A module under app/ that can connect
    reads app.core.config, whose settings judge themselves under pytest.)"""
    named = sorted(str(path.relative_to(BACKEND)) for path in _python_files_outside_tests()
                   if path.name.startswith("test_") or path.name.endswith("_test.py"))
    assert named == []
    definitions = re.compile(r"^(?:async\s+def\s+|def\s+)(test\w*)\s*\(|^class\s+(Test\w*)", re.M)
    defined = sorted(f"{path.relative_to(BACKEND)}::{a or b}" for path in _python_files_outside_tests()
                     if path.relative_to(BACKEND).parts[0] != "app"
                     for a, b in definitions.findall(path.read_text(encoding="utf-8", errors="replace")))
    assert defined == []


@pytest.mark.parametrize("flags", [[], ["--noconftest"], ["--confcutdir=scripts"]],
                         ids=["outside-rootdir", "noconftest", "confcutdir-scripts"])
def test_a_test_file_outside_the_tests_package_is_refused_before_it_connects(tmp_path, flags):
    """A collectable file outside tests/ (copied there: the canary imports only the application) is
    judged when the application's settings are built, whatever conftest files pytest skipped."""
    dead = free_port()
    outside = tmp_path / "outside"
    outside.mkdir()
    canary = outside / "test_outside_canary.py"
    canary.write_text((BACKEND / APP_CANARY).read_text(encoding="utf-8"), encoding="utf-8")
    args = ["-q", "-rP", "-p", "no:cacheprovider", "-o", "addopts=", *flags, str(canary)]
    code, output, entries = tripwired(tmp_path, refused_env(dead), args=args)
    assert_refused_before_anything(code, output, entries, "app/core/config.py")


@pytest.mark.parametrize("flags", [
    ["--import-mode=importlib", "--confcutdir=tests", "--rootdir=.."],
    ["--noconftest", "--import-mode=importlib", "-c", "/dev/null"],
], ids=["importlib-confcutdir-rootdir", "importlib-noconftest-inifile"])
def test_importlib_mode_with_the_rootdir_conftest_cut_off_is_refused(tmp_path, flags):
    """Under --import-mode=importlib with another rootdir (or -c /dev/null) pytest names the modules
    from that rootdir (backend.tests.*, Users.*), puts an empty placeholder in sys.modules for the
    parent packages, and hands the placeholder back for tests/__init__.py, which therefore never
    runs; --confcutdir=tests or --noconftest cuts off backend/conftest.py as well."""
    dead = free_port()
    code, output, entries = tripwired(tmp_path, refused_env(dead),
                                      args=["-q", "-rP", "-p", "no:cacheprovider", "-o", "addopts=", *flags, APP_CANARY])
    assert_refused_before_anything(code, output, entries,
                                   "tests/conftest.py" if "--confcutdir=tests" in flags else "app/core/config.py")


#: The connections script under whatever name it has: scripts/test_connections.py until 2026-10-21.
CONNECTIONS_SCRIPT = next((p for p in ("scripts/check_connections.py", "scripts/test_connections.py")
                           if (BACKEND / p).exists()), "scripts/check_connections.py")


@pytest.mark.parametrize("args, layer", [
    (["--import-mode=importlib", "--confcutdir=tests", "--rootdir=..", "tests/test_cache_services.py",
      "tests/test_health.py", "tests/test_auth.py"], "tests/conftest.py"),
    (["--noconftest", "--import-mode=importlib", "-c", "/dev/null", "tests/test_cache_services.py"], "app/core/config.py"),
    (["--noconftest", CONNECTIONS_SCRIPT], "app/core/config.py"),
    (["--confcutdir=scripts", CONNECTIONS_SCRIPT], "app/core/config.py"),
], ids=["importlib-confcutdir-rootdir", "importlib-noconftest-inifile", "noconftest-script", "confcutdir-script"])
def test_the_reviewers_own_commands_are_refused_at_collection(tmp_path, args, layer):
    """The commands the reviewers ran (collect-only, so even a run with no guard executes no test
    body), with an environment the guard refuses: each collected its modules and exited 0 with no
    refusal. Each must now end at collection with exit 78 - not collect, and not stop on an
    ImportError either (the settings first built inside a half-imported app.core.redis, as
    tests/test_cache_services.py imports them, once made the preflight fail to import)."""
    dead = free_port()
    code, output, entries = tripwired(tmp_path, refused_env(dead),
                                      args=["-q", "--co", "-p", "no:cacheprovider", "-o", "addopts=", *args])
    assert_refused_before_anything(code, output, entries, layer)
    assert "ImportError" not in output and "tests collected" not in output


def test_the_isolated_backend_launch_entry_runs_the_guard_before_uvicorn(tmp_path):
    """.claude/launch.json's backend-isolated entry started uvicorn directly, so a DATABASE_URL in
    backend/.env (or the environment) that redirects the database - an unencoded '#' or '?' in its
    password, a ?dbname= parameter - put the isolated backend on the live database with nothing to
    refuse it. scripts/local-servers.sh already ran the guard first; the entry now does the same."""
    launch = json.loads((BACKEND.parent / ".claude" / "launch.json").read_text(encoding="utf-8"))
    entry = next(c for c in launch["configurations"] if c["name"] == "backend-isolated")
    assert entry["runtimeExecutable"] == "sh" and entry["runtimeArgs"][0] == "-c", entry
    guard_command, joiner, server = entry["runtimeArgs"][1].partition(" && exec ")
    assert joiner and guard_command == "./venv311/bin/python -m app.core.target_guard --role isolated-backend"
    assert server.split()[:2] == ["./venv311/bin/uvicorn", "app.main:app"] and "--port 8001" in server
    dead = free_port()
    for url in (f"postgresql://postgres:p#w@127.0.0.1:{dead}/soccer_predictions",
                f"postgresql://postgres:pw@127.0.0.1:{dead}/soccer_predictions_e2e?dbname=soccer_predictions"):
        (tmp_path / "tripwire.jsonl").unlink(missing_ok=True)
        code, output, entries = tripwired(tmp_path, {**entry["env"], "DATABASE_URL": url}, mode="cli",
                                          args=guard_command.split()[3:] + ["--json"])
        assert entries == [] and code == EXIT_REFUSED, output[-2000:]
        verdict = json.loads(output[output.index("{"):output.rindex("}") + 1])
        assert "live-database" in verdict["codes"], verdict
        assert "p#w" not in output and ":pw@" not in output
