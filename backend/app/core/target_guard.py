"""
The isolation preflight: what a test run may connect to, decided before anything can connect.

WHY. On 2026-10-20 two backend runs lost their test settings to an unquoted shell variable (zsh
does not split `env $VARS cmd`: the first variable got the whole string and the rest were never
set), and resolved Redis to the live server from backend/.env - which, in a worktree, is a link
to the main checkout's live configuration. The only check then was that the database NAME
contained "test", and the unsplit value ('soccer_predictions_test POSTGRES_DB=... REDIS_HOST=...')
still does. So this module decides from the fully resolved targets instead, by exact comparison
with a committed allowlist, and refuses anything else.

WHAT IT JUDGES. Everything a run will connect to, resolved by the same code the application and
the tests use - the real `app.core.config.settings` object (environment, then `.env`, then class
defaults, exactly as pydantic-settings resolves them), `app.core.redis_urls.redis_url_for` (the URL
`get_redis_client` connects with for each database), redis-py's `parse_url`, and SQLAlchemy's own
`create_connect_args` for PostgreSQL (so a query string that redirects host, port or database is
seen for what it does):
- the application's database, and for the test role TEST_DATABASE_URL and RACE_TEST_DATABASE_URL;
- every Redis database the application opens: the default client and the six REDIS_DB_* roles,
  and for the test role LEASE_TEST_REDIS_URL's three;
- the scheduler and email switches.
Missing isolation settings, live or unapproved targets, and conflicting overrides are all refused,
and every reason is collected before any is reported. The policy is isolation_targets.json beside
this file; frontend/e2e/support/target-policy.ts reads the same file.

WHAT IT NEVER DOES. It opens no connection, sends no request, resolves no host name and writes
nothing: every comparison is between strings and numbers already in memory (exact host names
from a short loopback list; no DNS). Its report names keys and host:port/database, never a value
that could hold a credential. Importing this module loads nothing outside the standard library.

WHERE IT RUNS (role `backend-tests`; every layer calls `enforce`, which is idempotent):
1. backend/conftest.py - the rootdir conftest, which pytest loads before every other conftest and
   before any test module. Its first statement is the check; a refusal ends the process there
   with exit 78, before backend/tests/conftest.py imports the application.
2. The same file re-checks at session start and after collection, when every test module has
   read its URLs from the environment, and refuses if anything governed changed since.
3. backend/tests/conftest.py, whose first statement is the same check: pytest executes a conftest
   it loads whatever the import mode, rootdir or confcutdir, so a run that cuts off the rootdir
   conftest (--confcutdir=tests, another --rootdir) still meets it.
4. app/core/config.py, under pytest: the settings judge themselves the moment they are built
   (enforce_on_settings), so a run that loads no conftest at all (--noconftest), or a test file
   outside tests/, is refused before any module can connect with them - every module that can
   connect reads these settings first. This is the layer that does not depend on where a file is.
5. backend/tests/__init__.py, when the package really is imported. It is not relied on: under
   --import-mode=importlib with another rootdir, pytest hands back an empty placeholder module
   for the package and its __init__ never runs (2026-10-21 review), which layers 3 and 4 cover.
6. `python -m app.core.target_guard --role backend-tests [--json]` (exit 0 or 78), which
   scripts/test_evidence.py runs with the exact environment it will give the suite, and
   scripts/local-servers.sh and .claude/launch.json's backend-isolated entry run with role
   `isolated-backend` before starting the isolated backend.

GET /health names the database with driver_database() below, so the browser preflight hears where
the driver really connects - or nothing, when the URL redirects or cannot be read.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlsplit

EXIT_REFUSED = 78
POLICY_PATH = Path(__file__).with_name("isolation_targets.json")
POLICY_FORMAT = "isolation-targets/1"

REDIS_ROLE_KEYS = ("REDIS_DB_SESSIONS", "REDIS_DB_PREDICTIONS", "REDIS_DB_EXPERT_TOOLS", "REDIS_DB_ML_MODELS",
                   "REDIS_DB_MATCH_DATA", "REDIS_DB_RATE_LIMIT")
PROVIDER_KEYS = ("LIVESCORE_API_KEY", "LIVESCORE_API_SECRET", "GAMEFORECAST_API_KEY", "API_FOOTBALL_KEY",
                 "THESPORTSDB_KEY")
INT_KEYS = ("POSTGRES_PORT", "REDIS_PORT", "REDIS_DB") + REDIS_ROLE_KEYS
BOOL_KEYS = ("SYNC_SCHEDULER_ENABLED", "EMAIL_ENABLED")
STR_KEYS = ("DATABASE_URL", "POSTGRES_SERVER", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
            "REDIS_URL", "REDIS_HOST", "REDIS_PASSWORD") + PROVIDER_KEYS
SETTINGS_KEYS = STR_KEYS + INT_KEYS + BOOL_KEYS
TEST_KEYS = ("TEST_DATABASE_URL", "RACE_TEST_DATABASE_URL", "LEASE_TEST_REDIS_URL")
#: libpq reads these whatever the URL says; PGHOSTADDR redirects a connection even with a host given.
PG_ENV_KEYS = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGSERVICE", "PGSERVICEFILE")
GOVERNED = SETTINGS_KEYS + TEST_KEYS + PG_ENV_KEYS
#: Values that can carry a credential: never shown, and not tested for a NAME= prefix.
SECRET_KEYS = frozenset(("POSTGRES_PASSWORD", "REDIS_PASSWORD") + PROVIDER_KEYS)
#: What a PostgreSQL URL may carry beyond host, port and database without being able to redirect it.
PG_PARAMETERS = frozenset(("host", "port", "dbname", "user", "password", "connect_timeout", "sslmode",
                           "application_name"))
#: The one REDIS_URL shape whose database get_redis_client really serves: scheme, optional
#: credentials, an explicit host and port, and a numeric database - no query string (redis-py lets
#: ?db= override the path), no unix socket, nothing after the database.
REDIS_URL_FORM = re.compile(r"^rediss?://(?:[^@/?#\s]*@)?(?:\[[0-9A-Fa-f:.]+\]|[^:/?#@\s\[\]]+):\d+/\d+$")
#: A value an unsplit shell variable produces: whitespace inside it, or one that starts NAME=.
UNSPLIT_SPACE = re.compile(r"\s")
UNSPLIT_ASSIGNMENT = re.compile(r"^[A-Z][A-Z0-9_]{2,}=")

TRUE_WORDS = frozenset(("1", "true", "t", "yes", "y", "on"))
FALSE_WORDS = frozenset(("0", "false", "f", "no", "n", "off"))

CANONICAL_COMMAND = (
    "cd backend && TEST_DATABASE_URL=postgresql://postgres:<password>@localhost:5432/soccer_predictions_test "
    "POSTGRES_DB=soccer_predictions_test REDIS_HOST=127.0.0.1 REDIS_PORT=6390 SYNC_SCHEDULER_ENABLED=false "
    "EMAIL_ENABLED=false ./venv311/bin/python -m pytest -o addopts=\"\" -q")
FIX_HINTS = {
    "backend-tests": [
        "Write every target on the command line, with the throwaway Redis started (backend/README.md, \"Testing\"):",
        "  " + CANONICAL_COMMAND,
        "  (add LEASE_TEST_REDIS_URL=redis://127.0.0.1:6390/9 and RACE_TEST_DATABASE_URL="
        "postgresql://postgres@127.0.0.1:5440/forecast_race_test to run the real-Redis and race tests)",
    ],
    "isolated-backend": [
        "Start the isolated backend with scripts/local-servers.sh start isolated, which sets every one of "
        "these explicitly (ISOLATED_ENV).",
    ],
}


class PolicyError(Exception):
    """The committed policy is missing, unreadable or not the expected format."""


# ================================================================================ the policy
def load_policy(path: Path = POLICY_PATH) -> Dict[str, Any]:
    """The committed policy, fail-closed. Its sha256 is kept under `_sha256`."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise PolicyError(f"the isolation policy {Path(path).name} cannot be read ({type(exc).__name__})") from None
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PolicyError(f"the isolation policy {Path(path).name} is not JSON") from None
    if not isinstance(document, dict) or document.get("format") != POLICY_FORMAT:
        raise PolicyError(f"the isolation policy {Path(path).name} is not format {POLICY_FORMAT}")
    document["_sha256"] = hashlib.sha256(raw).hexdigest()
    return document


def _is_port(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value < 65536


def _is_db(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 15


def _dbs(entry: Mapping[str, Any]) -> List[int]:
    return list(range(16)) if entry.get("databases") == "all" else list(entry.get("databases") or [])


def policy_problems(policy: Mapping[str, Any]) -> List[str]:
    """Why a policy cannot be trusted; empty when it can. A policy that approves, for any role, a
    protected target that role may not use is itself refused: deny must win by construction."""
    problems: List[str] = []
    if policy.get("format") != POLICY_FORMAT:
        problems.append(f"format is not {POLICY_FORMAT}")
    hosts = policy.get("loopback_hosts")
    if not isinstance(hosts, list) or not hosts or not all(isinstance(h, str) and h for h in hosts):
        problems.append("loopback_hosts is empty or malformed")
    protected = policy.get("protected") or {}
    pg_marks = protected.get("postgres_databases")
    redis_marks = protected.get("redis")
    if not isinstance(pg_marks, list) or not pg_marks or not all(
            isinstance(m, dict) and isinstance(m.get("database"), str) and m.get("class") for m in pg_marks):
        problems.append("protected.postgres_databases is empty or malformed")
        pg_marks = []
    if not isinstance(redis_marks, list) or not redis_marks or not all(
            isinstance(m, dict) and _is_port(m.get("port")) and m.get("class")
            and isinstance(m.get("databases"), list) and m["databases"] and all(_is_db(d) for d in m["databases"])
            for m in redis_marks):
        problems.append("protected.redis is empty or malformed")
        redis_marks = []
    roles = policy.get("roles")
    if not isinstance(roles, dict) or not roles:
        return problems + ["roles is empty or malformed"]
    for name, role in roles.items():
        if not isinstance(role, dict):
            problems.append(f"role {name} is malformed")
            continue
        may_use = role.get("may_use", [])
        if not isinstance(may_use, list) or "live" in may_use:
            problems.append(f"role {name}: may_use is malformed or lists the live class")
            may_use = []
        for kind in ("postgres", "redis"):
            slots = role.get(kind)
            if not isinstance(slots, dict) or not slots:
                problems.append(f"role {name}: {kind} is empty or malformed")
                continue
            for slot, entries in slots.items():
                if not isinstance(entries, list) or not entries:
                    problems.append(f"role {name}: {kind}.{slot} is empty")
                    continue
                for entry in entries:
                    if not isinstance(entry, dict) or entry.get("host") != "loopback" or not _is_port(entry.get("port")):
                        problems.append(f"role {name}: {kind}.{slot} has an entry that is not loopback:<port>")
                        continue
                    if kind == "postgres":
                        if not isinstance(entry.get("database"), str) or not entry["database"]:
                            problems.append(f"role {name}: postgres.{slot} has an entry with no database")
                            continue
                        for mark in pg_marks:
                            if mark["database"] == entry["database"] and mark["class"] not in may_use:
                                problems.append(f"role {name}: postgres.{slot} approves the protected database "
                                                f"{entry['database']} ({mark['class']})")
                    else:
                        databases = entry.get("databases")
                        if databases != "all" and not (isinstance(databases, list) and databases
                                                       and all(_is_db(d) for d in databases)):
                            problems.append(f"role {name}: redis.{slot} has an entry with malformed databases")
                            continue
                        for mark in redis_marks:
                            if mark["port"] == entry["port"] and set(_dbs(entry)) & set(mark["databases"]) \
                                    and mark["class"] not in may_use:
                                problems.append(f"role {name}: redis.{slot} approves protected Redis databases on "
                                                f":{entry['port']} ({mark['class']})")
    browser = policy.get("browser") or {}
    sides = {side: browser.get(side) or {} for side in ("live", "isolated")}
    for side, ports in sides.items():
        for key in ("frontend_ports", "backend_ports"):
            values = ports.get(key)
            if not isinstance(values, list) or not values or not all(_is_port(p) for p in values):
                problems.append(f"browser.{side}.{key} is empty or malformed")
    live_ports = set(sides["live"].get("frontend_ports") or []) | set(sides["live"].get("backend_ports") or [])
    isolated_ports = set(sides["isolated"].get("frontend_ports") or []) | set(sides["isolated"].get("backend_ports") or [])
    if live_ports & isolated_ports:
        problems.append("browser: the live and isolated ports overlap")
    if sides["isolated"].get("role") not in roles:
        problems.append("browser.isolated.role names no role")
    return problems


# ================================================================================ targets
@dataclass
class Target:
    """One place a run will connect to. `host`, `port` and `database` are what the driver will use;
    `problem` is set when it cannot be told safely (and the target is then not judged further)."""
    label: str
    kind: str                       # "postgres" | "redis"
    source: str
    host: Optional[str] = None
    port: Optional[int] = None
    database: Any = None            # a name for PostgreSQL, a number (or numbers) for Redis
    problem: Optional[str] = None   # cannot be told safely: refused, and not judged further
    conflict: Optional[str] = None  # can be told, and is judged, but was redirected: refused as well

    def describe(self) -> str:
        if self.problem:
            return "(unreadable)"
        host = f"[{self.host}]" if self.host and ":" in self.host else self.host
        if self.kind == "redis":
            dbs = self.database if isinstance(self.database, (list, tuple)) else [self.database]
            return f"{host}:{self.port}/{','.join(str(d) for d in dbs)}"
        return f"{host}:{self.port}/{self.database}"

    def identity(self) -> Tuple[Any, ...]:
        return (self.kind, self.host, self.port, tuple(self.database) if isinstance(self.database, list) else self.database)


@dataclass
class Refusal:
    code: str
    message: str


@dataclass
class Verdict:
    role: str
    refusals: List[Refusal] = field(default_factory=list)
    targets: Dict[str, str] = field(default_factory=dict)
    sources: Dict[str, str] = field(default_factory=dict)
    approved: List[str] = field(default_factory=list)
    policy_sha256: Optional[str] = None
    snapshot: Tuple[Any, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.refusals

    @property
    def codes(self) -> set:
        return {refusal.code for refusal in self.refusals}

    def summary_line(self) -> str:
        if not self.ok:
            return f"target guard: {self.role} REFUSED ({len(self.refusals)} problem(s): {', '.join(sorted(self.codes))})"
        shown = "; ".join(f"{label} {target}" for label, target in self.targets.items())
        return f"target guard: {self.role} approved - {shown} (policy sha256 {str(self.policy_sha256)[:12]})"

    def report(self, layer: str = "") -> str:
        where = f", at {layer}" if layer else ""
        lines = [f"REFUSED: the isolation preflight (role {self.role}{where}) found {len(self.refusals)} problem(s).",
                 "Nothing has connected to any database, Redis server or HTTP service: this check runs before "
                 "anything that can.", ""]
        for index, refusal in enumerate(self.refusals, 1):
            lines.append(f"  {index}. [{refusal.code}] {refusal.message}")
        if self.targets:
            lines += ["", "Resolved targets (credentials are never shown):"]
            width = max(len(label) for label in self.targets)
            for label, target in self.targets.items():
                lines.append(f"  {label.ljust(width)}  {target}   <- {self.sources.get(label, '')}")
        if self.approved:
            lines += ["", f"Approved for {self.role} (backend/app/core/isolation_targets.json, sha256 "
                          f"{str(self.policy_sha256)[:12]}):"] + [f"  {line}" for line in self.approved]
        lines += [""] + FIX_HINTS.get(self.role, [])
        lines.append(f"Exit {EXIT_REFUSED}.")
        return "\n".join(lines)

    def as_json(self) -> Dict[str, Any]:
        return {"ok": self.ok, "role": self.role, "codes": sorted(self.codes),
                "refusals": [{"code": r.code, "message": r.message} for r in self.refusals],
                "targets": dict(self.targets), "policy_sha256": self.policy_sha256}


def _host_of(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value[1:-1] if value.startswith("[") and value.endswith("]") else value


def _postgres_target(label: str, source: str, url: str) -> Target:
    """Where psycopg2 will really connect: SQLAlchemy's own create_connect_args, so a URL query string
    that overrides host, port or dbname is seen for what it does."""
    from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
    from sqlalchemy.engine import make_url

    target = Target(label=label, kind="postgres", source=source)
    try:
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql":
            target.problem = f"{label} is not a PostgreSQL URL"
            return target
        args, params = PGDialect_psycopg2().create_connect_args(parsed)
    except Exception as exc:  # noqa: BLE001 - only the class name is kept: a message can quote the URL
        target.problem = f"{label} cannot be parsed as a PostgreSQL URL ({type(exc).__name__})"
        return target
    unexpected = sorted(set(params) - PG_PARAMETERS)
    host, port, database = params.get("host"), params.get("port"), params.get("dbname")
    if args or unexpected:
        target.problem = (f"{label} carries the connection parameter(s) {', '.join(unexpected) or 'positional'}, "
                          "which can redirect it; only host, port, dbname, user, password, connect_timeout, "
                          "sslmode and application_name are accepted")
    elif not host or not port or not database:
        missing = [name for name, value in (("host", host), ("port", port), ("database", database)) if not value]
        target.problem = (f"{label} does not name its {', '.join(missing)}; libpq would fill it in from "
                          "its own defaults or PG* variables")
    elif "," in str(host) or str(host).startswith("/"):
        target.problem = f"{label} names several hosts or a socket directory, not one host"
    if target.problem:
        return target
    try:
        target.port = int(port)
    except (TypeError, ValueError):
        target.problem = f"{label} has a port that is not a number"
        return target
    target.host, target.database = str(host), str(database)
    # Parameters that override the URL's own host, port or database are a conflict in themselves; the
    # target is still judged where it really goes.
    query = set((parsed.query or {}).keys()) & {"host", "port", "dbname"}
    if query:
        target.conflict = (f"{label} has the URL parameter(s) {', '.join(sorted(query))}, which override the "
                           f"host, port or database in the URL itself (it really goes to {target.describe()})")
    return target


def _redis_target(label: str, source: str, url: str) -> Target:
    from redis.connection import parse_url

    target = Target(label=label, kind="redis", source=source)
    try:
        parsed = parse_url(url)
    except Exception as exc:  # noqa: BLE001
        target.problem = f"{label} cannot be parsed as a Redis URL ({type(exc).__name__})"
        return target
    if parsed.get("path"):
        target.problem = f"{label} is a unix socket, not a host and port"
        return target
    target.host = parsed.get("host") or "localhost"
    target.port = int(parsed.get("port") or 6379)
    target.database = int(parsed.get("db") or 0)
    return target


def _lease_target(source: str, url: str) -> Target:
    """LEASE_TEST_REDIS_URL as tests/services/test_sync_lease_redis.py reads it: urlparse's host,
    port and path, and the three databases d, d+1 and d+2 (mod 16) that the tests flush."""
    target = Target(label="lease redis", kind="redis", source=source)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        target.problem = "LEASE_TEST_REDIS_URL cannot be parsed"
        return target
    if parts.query or parts.fragment or not parts.hostname or not port or parts.scheme not in ("redis", "rediss"):
        target.problem = "LEASE_TEST_REDIS_URL must be redis://host:port/<database> with nothing after the database"
        return target
    path = (parts.path or "/0").lstrip("/") or "0"
    if not path.isdigit():
        target.problem = "LEASE_TEST_REDIS_URL's database is not a number"
        return target
    first = int(path)
    target.host, target.port = parts.hostname, port
    target.database = [(first + offset) % 16 for offset in (0, 1, 2)]
    return target


def _bool_word(value: str) -> Optional[bool]:
    word = value.strip().lower()
    return True if word in TRUE_WORDS else False if word in FALSE_WORDS else None


def _assembled_database_url(settings: Any) -> str:
    """What Settings.assemble_db_connection builds from the parts: equal to DATABASE_URL unless a
    DATABASE_URL was supplied (by the environment or by a .env file)."""
    return (f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}@"
            f"{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")


def _assembled_redis_url(settings: Any) -> str:
    password = settings.REDIS_PASSWORD
    credentials = f":{password}@" if password else ""
    return f"redis://{credentials}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"


def _application_settings() -> Any:
    from app.core import config

    return config.settings


class _Judge:
    """One evaluation: collects every refusal, then hands back a Verdict."""

    def __init__(self, role: str, environ: Mapping[str, str], policy: Mapping[str, Any]):
        self.role_name = role
        self.role = policy["roles"][role]
        self.environ = environ
        self.policy = policy
        self.loopback = set(policy["loopback_hosts"])
        self.refusals: List[Refusal] = []
        self.targets: List[Tuple[str, Target]] = []      # (slot, target)

    def refuse(self, code: str, message: str) -> None:
        if not any(r.code == code and r.message == message for r in self.refusals):
            self.refusals.append(Refusal(code, message))

    def explicit(self, key: str) -> bool:
        """Set in the process environment, under exactly this name, to something that is not blank.
        A value from a .env file, a class default or a module's literal default is never explicit."""
        value = self.environ.get(key)
        return value is not None and value.strip() != ""

    def source(self, *keys: str) -> str:
        given = [key for key in keys if self.explicit(key)]
        if given:
            return "environment " + "/".join(given)
        return "not exported: " + "/".join(keys) + " from .env or the class default"

    # ------------------------------------------------------------------------- judging a target
    def judge(self, slot: str, target: Target) -> None:
        self.targets.append((slot, target))
        code = "conflict:redis-url-form" if target.kind == "redis" else "conflict:postgres-url"
        if target.problem:
            self.refuse(code, target.problem)
            return
        if target.conflict:
            self.refuse(code, target.conflict)
        host = _host_of(target.host)
        loopback = host in self.loopback
        kind = target.kind
        if kind == "postgres":
            mark = next((m for m in self.policy["protected"]["postgres_databases"]
                         if m["database"] == target.database), None)
            if mark and mark["class"] not in self.role.get("may_use", []):
                code = "live-database" if mark["class"] == "live" else f"{mark['class']}-database"
                rule = ("It is refused on any host and port." if mark["class"] == "live"
                        else f"Role {self.role_name} may not use it.")
                self.refuse(code, f"{target.label} ({target.describe()}) is {mark['why']}. {rule}")
                return
            entries = self.role["postgres"].get(slot, [])
            if loopback and any(e["port"] == target.port and e["database"] == target.database for e in entries):
                return
            self.refuse("unapproved-database", self._unapproved(target, loopback, [
                f"loopback:{e['port']}/{e['database']}" for e in entries]))
            return
        databases = target.database if isinstance(target.database, list) else [target.database]
        for db in databases:
            mark = next((m for m in self.policy["protected"]["redis"]
                         if m["port"] == target.port and db in m["databases"]), None)
            if mark and mark["class"] not in self.role.get("may_use", []):
                code = "live-redis" if mark["class"] == "live" else f"{mark['class']}-redis"
                rule = ("The live Redis is refused on any host." if mark["class"] == "live"
                        else f"Role {self.role_name} may not use them.")
                self.refuse(code, f"{target.label} is {target.host}:{target.port} database {db}: {mark['why']}. {rule}")
                continue
            entries = self.role["redis"].get(slot, [])
            if loopback and any(e["port"] == target.port and db in _dbs(e) for e in entries):
                continue
            self.refuse("unapproved-redis", self._unapproved(
                target, loopback, [f"loopback:{e['port']}/{'any' if e['databases'] == 'all' else _span(e['databases'])}"
                                   for e in entries], db))

    def _unapproved(self, target: Target, loopback: bool, approved: Sequence[str], db: Any = None) -> str:
        what = target.describe() if db is None else f"{target.host}:{target.port} database {db}"
        why = ("" if loopback else
               f" Only {', '.join(sorted(self.loopback))} are recognised as this machine, by exact name and without a lookup.")
        return (f"{target.label} ({what}) is not an approved target for {self.role_name}; approved: "
                f"{', '.join(approved) or 'none'}.{why}")


def _span(databases: Sequence[int]) -> str:
    values = sorted(databases)
    if values and values == list(range(values[0], values[-1] + 1)) and len(values) > 2:
        return f"{values[0]}-{values[-1]}"
    return ",".join(str(v) for v in values)


#: How many evaluations are running in this thread's call stack. The first evaluation in a process
#: imports app.core.config, whose own check (enforce_on_settings) would otherwise evaluate again
#: from inside it: the outer evaluation is already judging those very settings.
_EVALUATING = 0


def evaluate(role: str = "backend-tests", environ: Optional[Mapping[str, str]] = None,
             settings_factory: Optional[Callable[[], Any]] = None,
             policy: Optional[Mapping[str, Any]] = None) -> Verdict:
    """Every reason to refuse `role`'s targets, or none. Pure: no connection, lookup or write."""
    global _EVALUATING
    _EVALUATING += 1
    try:
        return _evaluate(role, environ, settings_factory, policy)
    finally:
        _EVALUATING -= 1


def _evaluate(role: str, environ: Optional[Mapping[str, str]], settings_factory: Optional[Callable[[], Any]],
              policy: Optional[Mapping[str, Any]]) -> Verdict:
    environ = dict(os.environ if environ is None else environ)
    try:
        policy = load_policy() if policy is None else policy
    except PolicyError as exc:
        return Verdict(role=role, refusals=[Refusal("policy:invalid", str(exc))])
    sha = policy.get("_sha256")
    problems = policy_problems(policy)
    if role not in (policy.get("roles") or {}):
        problems.append(f"there is no role {role!r}")
    if problems:
        return Verdict(role=role, policy_sha256=sha,
                       refusals=[Refusal("policy:invalid", "the isolation policy cannot be trusted: " + "; ".join(problems))])
    judge = _Judge(role, environ, policy)
    tests_role = "test" in policy["roles"][role]["postgres"]

    # ---------------------------------------------------------------- the environment itself
    unsplit = set()
    for key in GOVERNED:
        value = environ.get(key)
        if value is None:
            continue
        if UNSPLIT_SPACE.search(value) or (key not in SECRET_KEYS and UNSPLIT_ASSIGNMENT.search(value)):
            unsplit.add(key)
            judge.refuse("conflict:unsplit-value",
                         f"{key} contains whitespace or begins with a NAME= assignment - what an unsplit shell "
                         "variable produces (zsh does not split `env $VARS cmd`): one variable gets the whole "
                         "string and the others are never set. Write each variable on the command line.")
    for key in environ:
        if key not in GOVERNED and key.upper() in GOVERNED:
            judge.refuse("conflict:case-variant",
                         f"{key} is set but is not {key.upper()}: the settings are case-sensitive and ignore it, "
                         "while a reader of the environment may not")
    for key in PG_ENV_KEYS:
        if key in environ:
            judge.refuse("conflict:pg-environment",
                         f"{key} is set; libpq honours it whatever the URL says (PGHOSTADDR even with a host given). "
                         "Unset it.")

    # ---------------------------------------------------------------- missing
    if tests_role and not judge.explicit("TEST_DATABASE_URL"):
        judge.refuse("missing:TEST_DATABASE_URL",
                     "TEST_DATABASE_URL is not set: 29 test modules would fall back to their literal default, "
                     "and nothing would say which database the run really uses")
    if not (judge.explicit("DATABASE_URL") or judge.explicit("POSTGRES_DB")):
        judge.refuse("missing:database",
                     "neither DATABASE_URL nor POSTGRES_DB is set, so the application's database comes from .env "
                     "or the class default - the live database in every checkout")
    if not (judge.explicit("REDIS_URL") or (judge.explicit("REDIS_HOST") and judge.explicit("REDIS_PORT"))):
        missing = [k for k in ("REDIS_HOST", "REDIS_PORT") if not judge.explicit(k)]
        judge.refuse("missing:redis",
                     f"neither REDIS_URL nor both REDIS_HOST and REDIS_PORT are set ({', '.join(missing)} missing), so "
                     "the Redis server comes from .env or the class default - the live one")
    for key in BOOL_KEYS:
        if not judge.explicit(key):
            judge.refuse(f"missing:{key}",
                         f"{key} is not set; .env and the class default leave it on"
                         + (" (the TestClient lifespan starts the scheduler)" if key.startswith("SYNC") else ""))
    if not tests_role:
        unset = [key for key in PROVIDER_KEYS if environ.get(key) is None or environ[key].strip() != ""]
        if unset:
            judge.refuse("missing:provider-blank",
                         f"{', '.join(unset)} must be set and blank: the isolated backend has every provider door closed")

    # ---------------------------------------------------------------- the settings, as the application resolves them
    try:
        settings = (settings_factory or _application_settings)()
    except Exception as exc:  # noqa: BLE001
        errors = getattr(exc, "errors", None)
        detail = ""
        if callable(errors):
            try:
                detail = "; ".join(f"{'.'.join(str(p) for p in e.get('loc', ()))}: {e.get('type')}" for e in errors())
            except Exception:  # noqa: BLE001
                detail = ""
        judge.refuse("malformed:settings",
                     f"the application settings cannot be built ({type(exc).__name__}{': ' + detail if detail else ''})")
        return _verdict(judge, role, sha, environ)

    for key in SETTINGS_KEYS:
        if key in unsplit or not judge.explicit(key):
            continue
        value, held = environ[key], getattr(settings, key, None)
        if key in INT_KEYS:
            try:
                same = int(value.strip()) == held
            except ValueError:
                same = False
        elif key in BOOL_KEYS:
            same = _bool_word(value) is not None and _bool_word(value) == held
        else:
            same = value == held
        if not same:
            judge.refuse("conflict:settings-differ",
                         f"{key} in the environment is not what the application settings hold: the settings were "
                         "built from other values than the ones every module will read")
    for key in BOOL_KEYS:
        if getattr(settings, key, True):
            judge.refuse(f"flag:{key}", f"{key} resolves to true; it must be false for {role}")

    # ---------------------------------------------------------------- PostgreSQL
    app_slot = "test" if tests_role else "application"
    if "DATABASE_URL" in unsplit:
        app_db = Target(label="settings database", kind="postgres", source="environment DATABASE_URL",
                        problem="DATABASE_URL is unreadable (see the whitespace problem)")
        judge.targets.append((app_slot, app_db))
    else:
        db_source = judge.source("DATABASE_URL", "POSTGRES_SERVER", "POSTGRES_PORT", "POSTGRES_DB")
        assembled = _assembled_database_url(settings)
        from_dotenv = not judge.explicit("DATABASE_URL") and settings.DATABASE_URL != assembled
        if from_dotenv:
            db_source = "DATABASE_URL from .env"
            if any(judge.explicit(k) for k in ("POSTGRES_SERVER", "POSTGRES_PORT", "POSTGRES_DB")):
                judge.refuse("conflict:dotenv-database-url",
                             "DATABASE_URL comes from a .env file and silently overrides POSTGRES_SERVER/POSTGRES_PORT/"
                             "POSTGRES_DB from the environment")
        app_db = _postgres_target("settings database", db_source, settings.DATABASE_URL)
        judge.judge(app_slot, app_db)
        if judge.explicit("DATABASE_URL") and any(judge.explicit(k) for k in ("POSTGRES_SERVER", "POSTGRES_PORT", "POSTGRES_DB")):
            parts = _postgres_target("POSTGRES_* parts", "environment", assembled)
            if not parts.problem and not app_db.problem and parts.identity()[1:] != app_db.identity()[1:] \
                    and not (_host_of(parts.host) in judge.loopback and _host_of(app_db.host) in judge.loopback
                             and parts.identity()[2:] == app_db.identity()[2:]):
                judge.refuse("conflict:database-url-vs-postgres",
                             f"DATABASE_URL ({app_db.describe()}) and POSTGRES_* ({parts.describe()}) are both set and "
                             "name different databases; DATABASE_URL silently wins")
    test_db = None
    if tests_role:
        if "TEST_DATABASE_URL" in unsplit:
            judge.targets.append(("test", Target(label="test database", kind="postgres",
                                                 source="environment TEST_DATABASE_URL",
                                                 problem="TEST_DATABASE_URL is unreadable (see the whitespace problem)")))
        elif judge.explicit("TEST_DATABASE_URL"):
            test_db = _postgres_target("test database", "environment TEST_DATABASE_URL", environ["TEST_DATABASE_URL"])
            judge.judge("test", test_db)
            if not test_db.problem and not app_db.problem and not _same_target(judge, test_db, app_db):
                judge.refuse("conflict:test-vs-settings-database",
                             f"TEST_DATABASE_URL ({test_db.describe()}) is not the database the application settings "
                             f"resolve to ({app_db.describe()}): the TestClient lifespan, deps.SessionLocal and the "
                             "scheduler connect with the settings, not with TEST_DATABASE_URL")
        if judge.explicit("RACE_TEST_DATABASE_URL") and "RACE_TEST_DATABASE_URL" not in unsplit:
            race = _postgres_target("race database", "environment RACE_TEST_DATABASE_URL", environ["RACE_TEST_DATABASE_URL"])
            judge.judge("race", race)
            if not race.problem and any(other is not None and not other.problem and _same_target(judge, race, other)
                                        for other in (test_db, app_db)):
                judge.refuse("conflict:race-same-as-test",
                             f"RACE_TEST_DATABASE_URL ({race.describe()}) is the test database; the race tests "
                             "TRUNCATE ... CASCADE every table, so they need a database of their own")

    # ---------------------------------------------------------------- Redis: every database the application opens
    from app.core.redis_urls import redis_url_for

    redis_source = judge.source("REDIS_URL", "REDIS_HOST", "REDIS_PORT", "REDIS_DB")
    redis_url = settings.REDIS_URL
    if "REDIS_URL" in unsplit:
        judge.targets.append(("application", Target(label="redis default (REDIS_DB)", kind="redis",
                                                    source="environment REDIS_URL",
                                                    problem="REDIS_URL is unreadable (see the whitespace problem)")))
        app_redis: List[Target] = []
    else:
        if not judge.explicit("REDIS_URL") and redis_url != _assembled_redis_url(settings):
            redis_source = "REDIS_URL from .env"
            if any(judge.explicit(k) for k in ("REDIS_HOST", "REDIS_PORT", "REDIS_DB")):
                judge.refuse("conflict:dotenv-redis-url",
                             "REDIS_URL comes from a .env file and silently overrides REDIS_HOST/REDIS_PORT/REDIS_DB "
                             "from the environment")
        if not REDIS_URL_FORM.match(redis_url or ""):
            judge.refuse("conflict:redis-url-form",
                         "REDIS_URL is not of the form redis://[credentials@]host:port/<database> with nothing after "
                         "the database: a ?db= query wins over the path in redis-py, a URL with no database makes "
                         "get_redis_client build another server's address, and a missing host falls back to localhost")
        app_redis = []
        default = _redis_target("redis default (REDIS_DB)", redis_source, redis_url_for(None, config=settings))
        app_redis.append(default)
        if not default.problem and REDIS_URL_FORM.match(redis_url or "") and default.database != settings.REDIS_DB:
            judge.refuse("conflict:redis-url-form",
                         f"REDIS_URL names database {default.database} but REDIS_DB is {settings.REDIS_DB}: "
                         "get_redis_client(REDIS_DB) would serve the URL's database")
        for key in REDIS_ROLE_KEYS:
            app_redis.append(_redis_target(f"redis {key}", f"the default's server; {judge.source(key)}",
                                           redis_url_for(getattr(settings, key), config=settings)))
        if judge.explicit("REDIS_URL") and any(judge.explicit(k) for k in ("REDIS_HOST", "REDIS_PORT", "REDIS_DB")):
            parts = _redis_target("REDIS_* parts", "environment", _assembled_redis_url(settings))
            if not parts.problem and not default.problem and (parts.host, parts.port, parts.database) != \
                    (default.host, default.port, default.database):
                judge.refuse("conflict:redis-url-vs-parts",
                             f"REDIS_URL ({default.describe()}) and REDIS_HOST/REDIS_PORT/REDIS_DB ({parts.describe()}) "
                             "are both set and disagree; REDIS_URL silently wins")
        for target in app_redis:
            judge.judge("application", target)
    values = {"REDIS_DB": settings.REDIS_DB, **{key: getattr(settings, key) for key in REDIS_ROLE_KEYS}}
    out_of_range = [key for key, value in values.items() if not _is_db(value)]
    if out_of_range:
        judge.refuse("conflict:redis-db-range", f"{', '.join(out_of_range)} is outside 0-15")
    roles = [values[key] for key in REDIS_ROLE_KEYS]
    if len(set(roles)) != len(roles):
        clashes = sorted({key for key in REDIS_ROLE_KEYS if roles.count(values[key]) > 1})
        judge.refuse("conflict:redis-db-collision",
                     f"{', '.join(clashes)} share a database; every role has one of its own")
    entries = policy["roles"][role]["redis"].get("application", [])
    per_database = any(
        not t.problem and _host_of(t.host) in judge.loopback
        and any(e["port"] == t.port and e["databases"] != "all" for e in entries)
        for t in app_redis)
    if per_database:
        unset = [key for key in ("REDIS_DB",) + REDIS_ROLE_KEYS if not judge.explicit(key)]
        if unset:
            judge.refuse("missing:redis-db",
                         f"{', '.join(unset)} not set: on a server that is approved database by database rather than "
                         "whole, every database the application opens must be written down (REDIS_DB is the default "
                         "client's, which /api/v1/health/detailed and every role equal to it use)")

    if tests_role and judge.explicit("LEASE_TEST_REDIS_URL") and "LEASE_TEST_REDIS_URL" not in unsplit:
        lease = _lease_target("environment LEASE_TEST_REDIS_URL", environ["LEASE_TEST_REDIS_URL"])
        if lease.problem:
            judge.targets.append(("lease", lease))
            judge.refuse("conflict:lease-url-form", lease.problem)
        else:
            judge.judge("lease", lease)
            used = {t.database for t in app_redis if not t.problem and _same_server(judge, t, lease)}
            overlap = sorted(set(lease.database) & used)
            if overlap:
                judge.refuse("conflict:lease-overlaps-application",
                             f"LEASE_TEST_REDIS_URL's databases {_span(lease.database)} include {_span(overlap)}, which "
                             "the application uses on the same server; the lease tests flush them")
    return _verdict(judge, role, sha, environ)


def _same_target(judge: _Judge, a: Target, b: Target) -> bool:
    return (_host_of(a.host) in judge.loopback) == (_host_of(b.host) in judge.loopback) and \
        (_host_of(a.host) in judge.loopback or a.host == b.host) and a.port == b.port and a.database == b.database


def _same_server(judge: _Judge, a: Target, b: Target) -> bool:
    both_local = _host_of(a.host) in judge.loopback and _host_of(b.host) in judge.loopback
    return a.port == b.port and (both_local or a.host == b.host)


def _approved_lines(policy: Mapping[str, Any], role: str) -> List[str]:
    spec = policy["roles"][role]
    lines = []
    for slot, entries in spec["postgres"].items():
        lines.append(f"postgres {slot}: " + ", ".join(f"loopback:{e['port']}/{e['database']}" for e in entries))
    for slot, entries in spec["redis"].items():
        lines.append(f"redis {slot}: " + ", ".join(
            f"loopback:{e['port']} ({'every database' if e['databases'] == 'all' else 'databases ' + _span(e['databases'])})"
            for e in entries))
    return lines


def _verdict(judge: _Judge, role: str, sha: Optional[str], environ: Mapping[str, str]) -> Verdict:
    targets: Dict[str, str] = {}
    sources: Dict[str, str] = {}
    for _, target in judge.targets:
        targets[target.label] = target.describe()
        sources[target.label] = target.source
    governed = sorted((key, hashlib.sha256(value.encode("utf-8", "replace")).hexdigest())
                      for key, value in environ.items() if key.upper() in GOVERNED)
    return Verdict(role=role, refusals=list(judge.refusals), targets=targets, sources=sources,
                   approved=_approved_lines(judge.policy, role), policy_sha256=sha,
                   snapshot=(tuple(governed), tuple(sorted(targets.items()))))


# ================================================================================ enforcing
_APPROVED: Dict[str, Tuple[Verdict, str]] = {}


def _release_pytest_capture() -> None:
    """A refusal must reach the terminal. Under pytest, output is captured at the file-descriptor
    level (and os._exit would discard it), so pytest's capture is suspended first if it is active."""
    if "_pytest.capture" not in sys.modules:
        return
    capture = sys.modules["_pytest.capture"]
    manager = getattr(capture, "CaptureManager", None)
    if manager is None:
        return
    for candidate in gc.get_objects():
        if isinstance(candidate, manager):
            try:
                candidate.suspend_global_capture(in_=True)
            except Exception:  # noqa: BLE001 - the report is written whatever happens here
                pass


def _refuse(verdict: Verdict, layer: str) -> None:
    _release_pytest_capture()
    try:
        sys.stderr.write("\n" + verdict.report(layer) + "\n")
        sys.stderr.flush()
    finally:
        # Not SystemExit: pytest turns an exception raised while importing a conftest or a test module
        # into a report and carries on (or exits 2 or 4). Nothing has been opened, so nothing is lost.
        os._exit(EXIT_REFUSED)


def enforce(role: str = "backend-tests", layer: str = "unspecified") -> Verdict:
    """Refuse the process (exit 78) unless `role`'s targets are approved and nothing governed has
    changed since the first layer approved them. Returns the approving verdict."""
    verdict = evaluate(role=role)
    first = _APPROVED.get(role)
    if verdict.ok and first is not None and first[0].snapshot != verdict.snapshot:
        before_env, before_targets = first[0].snapshot
        now_env, now_targets = verdict.snapshot
        keys = sorted({k for k, _ in set(before_env) ^ set(now_env)})
        labels = sorted({label for label, _ in set(before_targets) ^ set(now_targets)})
        verdict.refusals.append(Refusal(
            "conflict:changed",
            f"governed settings changed after {first[1]} approved them ({', '.join(keys + labels) or 'targets'}): "
            "the modules that already read them and the ones that read them now would use different targets"))
    if not verdict.ok:
        _refuse(verdict, layer)
    if first is None:
        _APPROVED[role] = (verdict, layer)
    return verdict


def enforce_on_settings(layer: str = "app/core/config.py") -> Optional[Verdict]:
    """app/core/config.py's own check, called under pytest as soon as `settings` exists: whatever
    conftest files pytest loaded or skipped, a refused run ends here, before any module that reads
    the settings has opened anything. Skipped when an evaluation is what imported the settings
    module (it is judging them already). Returns the approving verdict, or None when skipped."""
    if _EVALUATING:
        return None
    return enforce(role="backend-tests", layer=layer)


def driver_database(url: str) -> Optional[str]:
    """The name of the database psycopg2 will really connect to for `url`, read the way the
    driver reads it (SQLAlchemy's create_connect_args); None when the URL cannot be read, names no
    single host and database, or carries a parameter that overrides its own host, port or database.
    GET /health publishes this: urlsplit stops at an unencoded '#' or '?' in a password and ignores
    ?dbname=, so it named a database the driver did not use (2026-10-21 review)."""
    target = _postgres_target("database", "settings", url or "")
    if target.problem or target.conflict:
        return None
    return target.database


# ================================================================================ command line
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.core.target_guard",
        description="Judge this environment's database, Redis and switch settings against the isolation policy, "
                    "without connecting to anything. Exit 0 when approved, 78 when refused.")
    parser.add_argument("--role", default="backend-tests", help="backend-tests (default) or isolated-backend")
    parser.add_argument("--json", action="store_true", help="print the verdict as one JSON object on stdout")
    args = parser.parse_args(argv)
    verdict = evaluate(role=args.role)
    if args.json:
        print(json.dumps(verdict.as_json(), sort_keys=True))
    elif verdict.ok:
        print(verdict.summary_line())
    else:
        print(verdict.report("command line"), file=sys.stderr)
    return 0 if verdict.ok else EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
