#!/usr/bin/env python3
"""
Run every test suite once and keep reports that someone else can check, total by total.

WHY THIS EXISTS
    The totals reported for an earlier round (966 mocked browser tests, 57 live ones, 1,415 backend
    tests) could not be checked by anyone afterwards, because no raw output survived. Playwright
    empties its output directory at the start of every run, the HTML report had been overwritten,
    and a total read off a console through a pipe carries the pipe's exit code, not the runner's.
    Nobody can recompute such a count, so it is only a claim. This script writes the reports first
    and states the totals from them.

WHAT `run` DOES
    1. Preflight. Every reason to refuse is collected and printed together, and any one of them
       stops the run before a suite starts:
       - the working tree has uncommitted changes. --allow-dirty allows them and records the
         changed path names and the SHA-256 of `git diff HEAD`, never the diff itself;
       - another test run is active anywhere on this machine. Worktrees share :3100, :8000, the
         QA account, the backend test database and Redis;
       - another evidence run holds the lock;
       - a server under test is missing or serves another commit. For the live project, the
         backend is also refused when its process started before the newest change to its
         app/**/*.py, because it is then running older code;
       - for the backend suite, the test database or Redis does not answer. The database-backed
         modules would then skip, and the run would still exit green.
    2. A watcher samples every 15 seconds. Another test runner, a server restart, a new HEAD or a
       change to the working tree marks the whole run CONTAMINATED.
    3. The suites run one after another, each with its own exit code taken from the child process.
       The backend suite (pytest) runs first. Then the Playwright projects mocked-desktop,
       mocked-mobile, mocked-mobile-360 and live run in that order, one invocation each. Raw output
       goes to .test-runs/<run-id>/, which is gitignored.
    4. Post-checks. The reporter's own human summary, the JSON report and the JUnit report must
       agree bucket by bucket, and every requested project must be present. A backend skip that
       says "not reachable" disqualifies the run.
    5. Scrub and publish to docs/evidence/test-reports/<run-id>/. The published set is
       summary.md, summary.json, one JUnit file and one console tail per suite, and SHA256SUMS.
       Traces, screenshots and the full JSON stay in .test-runs/, because traces hold the QA
       password and bearer tokens. Nothing is staged or committed; the script only prints the
       paths.

WHAT `verify` DOES
    It checks every file against SHA256SUMS and recomputes every total from the committed XML,
    comparing them with summary.json. It reads each reporter's own summary back from the committed
    console tail, and makes every post-check again, including the agreement between the exit code
    and the results. It works out from the suites listed, their commands and the run id whether the
    run was partial. Then it re-derives each verdict and re-renders summary.md from summary.json.
    It needs only a Python 3.9+ interpreter and the published directory.

EXIT CODES
    run     0 PASS, 1 FAIL, 2 NOT EVIDENCE or CONTAMINATED, 3 refused before any suite ran,
            4 the scrub or the deny-list scan stopped the publish (the raw run is kept)
    verify  0 every check holds, 1 otherwise

USAGE
    backend/venv311/bin/python scripts/test_evidence.py run
    backend/venv311/bin/python scripts/test_evidence.py run --dry-run
    backend/venv311/bin/python scripts/test_evidence.py run --suites backend --allow-dirty
    python3 scripts/test_evidence.py verify docs/evidence/test-reports/<run-id>

This file uses the standard library only, so `verify` runs on any Python 3.9 or later.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"
VENV_PYTHON = BACKEND / "venv311" / "bin" / "python"
PLAYWRIGHT_BIN = FRONTEND / "node_modules" / ".bin" / "playwright"
CONFTEST = BACKEND / "tests" / "conftest.py"
QA_ACCOUNT = FRONTEND / "e2e" / "support" / "qa-account.ts"
RAW_ROOT = REPO / ".test-runs"
PUBLISH_ROOT = REPO / "docs" / "evidence" / "test-reports"
#: Untracked files under this prefix are this script's own output. They are not inputs to any test,
#: so an uncommitted report from an earlier run does not make the next run "dirty".
EVIDENCE_PREFIX = "docs/evidence/test-reports/"

FORMAT = "predictionsappsui-test-evidence/1"
PLAYWRIGHT_PROJECTS = ("mocked-desktop", "mocked-mobile", "mocked-mobile-360", "live")
ALL_SUITES = ("backend",) + PLAYWRIGHT_PROJECTS
DEFAULT_BASE_URL = "http://localhost:3100"
DEFAULT_API_URL = "http://127.0.0.1:8000"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
POSTGRES_CONTAINER = "soccer_predictions_postgres"
REDIS_CONTAINER = "soccer_predictions_redis"

#: The concurrency guard's patterns, matched by `pgrep -f` (extended regex) against full command
#: lines. A plain "playwright" would match every @playwright/mcp server on the machine (26 of them
#: when this was written) and refuse forever; these match a test runner, a Playwright worker and
#: pytest, and none of them matches its own text.
GUARD_PATTERNS = {
    "playwright runner": r"(/\.bin/playwright|@playwright/test/cli\.js|/playwright/cli\.js|playwright) test( |$)",
    "playwright worker": r"playwright/lib/worker/workerProcessEntry\.js",
    "pytest": r"(-m pytest|bin/pytest|py\.test)( |$)",
}
WATCH_INTERVAL_SECONDS = 15
BACKEND_TAIL_LINES = 80
PLAYWRIGHT_TAIL_LINES = 40
SIZE_WARNING_BYTES = 2 * 1024 * 1024

#: Every git call here is read-only and must stay invisible to sibling sessions committing in the
#: same checkout. Without GIT_OPTIONAL_LOCKS=0, `git status` refreshes the index and can briefly
#: hold index.lock, which makes a concurrent `git add` or `git commit` fail.
GIT_ENV = {"GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}

#: Reporter settings inherited from the caller's shell would redirect or duplicate the reports this
#: script reads, so a child never sees them. PYTEST_ADDOPTS could filter the backend suite.
INHERITED_ENV_DROPPED_PREFIXES = ("PLAYWRIGHT_JSON_", "PLAYWRIGHT_JUNIT_", "PLAYWRIGHT_HTML_",
                                  "PLAYWRIGHT_LIST_", "PLAYWRIGHT_BLOB_", "PLAYWRIGHT_LINE_",
                                  "PLAYWRIGHT_DOT_")
INHERITED_ENV_DROPPED = ("PW_TEST_REPORTER", "PYTEST_ADDOPTS")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(moment: Optional[datetime]) -> Optional[str]:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def say(line: str = "") -> None:
    print(line, flush=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def run_bytes(argv: Sequence[str], cwd: Optional[Path] = None, env_extra: Optional[Dict[str, str]] = None,
              timeout: float = 60, base_env: Optional[Dict[str, str]] = None) -> Tuple[int, bytes]:
    """Run a short command and return (exit code, stdout). A program that cannot start reads as 127."""
    env = dict(os.environ if base_env is None else base_env)
    env.update(env_extra or {})
    try:
        proc = subprocess.run(list(argv), cwd=str(cwd) if cwd else None, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return 127, b""
    return proc.returncode, proc.stdout


def run_text(argv: Sequence[str], cwd: Optional[Path] = None, env_extra: Optional[Dict[str, str]] = None,
             timeout: float = 60, base_env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    code, out = run_bytes(argv, cwd, env_extra, timeout, base_env)
    return code, out.decode("utf-8", "replace")


def git_out(args: Sequence[str], cwd: Path = REPO) -> Optional[str]:
    code, out = run_text(["git", *args], cwd=cwd, env_extra=GIT_ENV)
    return out.strip() if code == 0 else None


# ----------------------------------------------------------------------------- repository state
def parse_porcelain(raw: bytes) -> List[str]:
    """`git status --porcelain=v1 -z` as "XY path" entries. Rename and copy sources are dropped."""
    entries = raw.decode("utf-8", "replace").split("\0")
    paths: List[str] = []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if status[0] in "RC":
            index += 1   # the next entry is the path it was renamed or copied from
        paths.append(f"{status} {path}")
    return paths


def is_evidence_output(entry: str) -> bool:
    return entry.startswith("?? ") and entry[3:].startswith(EVIDENCE_PREFIX)


def dirty_paths(checkout: Path, pathspec: Optional[str] = None) -> Optional[List[str]]:
    """Changed and untracked paths (names only), or None when git could not say."""
    argv = ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"]
    if pathspec:
        argv += ["--", pathspec]
    code, raw = run_bytes(argv, cwd=checkout, env_extra=GIT_ENV)
    if code != 0:
        return None
    return [entry for entry in parse_porcelain(raw) if not is_evidence_output(entry)]


def untracked_sha256(checkout: Path, entries: Sequence[str]) -> str:
    """One digest over every untracked file's path and content. `git diff HEAD` does not see them."""
    digest = hashlib.sha256()
    for entry in sorted(entries):
        if not entry.startswith("?? "):
            continue
        relative = entry[3:]
        digest.update(relative.encode("utf-8", "replace") + b"\0")
        try:
            stat = (checkout / relative).stat()
            if stat.st_size > 64 * 1024 * 1024:
                digest.update(f"size:{stat.st_size}:{stat.st_mtime_ns}".encode())
            else:
                digest.update(sha256_file(checkout / relative).encode())
        except OSError:
            digest.update(b"unreadable")
    return digest.hexdigest()


def git_common_dir(checkout: Path) -> Optional[Path]:
    out = git_out(["rev-parse", "--git-common-dir"], checkout)
    if not out:
        return None
    path = Path(out)
    return path if path.is_absolute() else (checkout / path).resolve()


def repo_state(checkout: Path = REPO) -> Dict[str, Any]:
    paths = dirty_paths(checkout)
    code, diff = run_bytes(["git", "diff", "HEAD", "--binary"], cwd=checkout, env_extra=GIT_ENV)
    return {
        "head": git_out(["rev-parse", "HEAD"], checkout),
        "branch": git_out(["rev-parse", "--abbrev-ref", "HEAD"], checkout),
        "dirty": paths is None or bool(paths),
        "dirty_paths": paths if paths is not None else ["(git status failed)"],
        "diff_sha256": sha256_bytes(diff) if code == 0 else None,
        "untracked_sha256": untracked_sha256(checkout, paths or []),
    }


def origin_main(checkout: Path = REPO) -> Dict[str, Any]:
    """origin/main as this checkout last fetched it. Nothing is fetched here."""
    common = git_common_dir(checkout)
    fetch_head = common / "FETCH_HEAD" if common else None
    fetched = None
    if fetch_head and fetch_head.exists():
        fetched = iso(datetime.fromtimestamp(fetch_head.stat().st_mtime, timezone.utc))
    return {"origin_main": git_out(["rev-parse", "--verify", "-q", "origin/main"], checkout),
            "last_fetch_at": fetched}


def tree_fingerprint(state: Dict[str, Any]) -> Tuple[Any, ...]:
    return (state.get("head"), tuple(state.get("dirty_paths") or ()), state.get("diff_sha256"),
            state.get("untracked_sha256"))


def make_run_id(now: datetime, head: Optional[str], dirty: bool, partial: bool) -> str:
    run_id = f"{now.astimezone(timezone.utc):%Y-%m-%dT%H%MZ}-{(head or 'nohead')[:7]}"
    if dirty:
        run_id += "-dirty"
    if partial:
        run_id += "-partial"
    return run_id


#: A partial run's id, with the "-2", "-3" unique_dir adds when two runs start in the same minute.
PARTIAL_RUN_ID = re.compile(r"-partial(?:-\d+)?$")


def partial_reasons_for(suites: Sequence[str], filtered: bool) -> List[str]:
    """Why a run is PARTIAL - NOT EVIDENCE. `run` states it from its options, and `verify` works it
    out again from the suites a summary lists and the commands they ran."""
    reasons = []
    if list(suites) != list(ALL_SUITES):
        reasons.append(f"only {', '.join(suites)} requested")
    if filtered:
        reasons.append("tests filtered with --grep")
    return reasons


# ----------------------------------------------------------------------------- processes and servers
class GuardError(RuntimeError):
    """The concurrency guard could not look. That must never read as "nothing is running"."""


def parse_lstart(text: str) -> Optional[datetime]:
    """`ps -o lstart=` ("Tue Oct  6 21:02:46 2026", local time, C locale) as a UTC moment."""
    words = " ".join(text.split())
    if not words:
        return None
    try:
        stamp = time.mktime(time.strptime(words, "%a %b %d %H:%M:%S %Y"))
    except (ValueError, OverflowError):
        return None
    return datetime.fromtimestamp(stamp, timezone.utc)


def process_started(pid: int) -> Optional[datetime]:
    code, out = run_text(["ps", "-o", "lstart=", "-p", str(pid)], env_extra={"LC_ALL": "C"})
    return parse_lstart(out) if code == 0 else None


def process_table() -> Dict[int, Tuple[int, str]]:
    """pid -> (parent pid, command line) for every process."""
    _, out = run_text(["ps", "-axo", "pid=,ppid=,command="], env_extra={"LC_ALL": "C"})
    table: Dict[int, Tuple[int, str]] = {}
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2] if len(parts) > 2 else "")
    return table


def own_family(pid: int, table: Dict[int, Tuple[int, str]]) -> set:
    """`pid`, its ancestors and its descendants. Siblings are not family: a test run started
    beside this one from the same shell is still a foreign runner."""
    family = {pid}
    cursor = table.get(pid, (0, ""))[0]
    while cursor > 1 and cursor not in family:
        family.add(cursor)
        cursor = table.get(cursor, (0, ""))[0]
    children: Dict[int, List[int]] = {}
    for child, (parent, _) in table.items():
        children.setdefault(parent, []).append(child)
    frontier = [pid]
    while frontier:
        for child in children.get(frontier.pop(), []):
            if child not in family:
                family.add(child)
                frontier.append(child)
    return family


def program_name(command: str) -> str:
    first = command.split(" ", 1)[0] if command else ""
    return os.path.basename(first) or "?"


def find_foreign_runners(own_pid: Optional[int] = None) -> List[Dict[str, Any]]:
    """Every test runner on this machine outside this script's own process tree.

    The check is machine-wide on purpose: a run in another worktree uses the same servers, QA
    account, test database and Redis. Only the program name and the matched words are kept, never
    the whole command line, because shells often carry a database URL in front of the command.
    """
    own_pid = own_pid or os.getpid()
    matched: Dict[int, str] = {}
    for label, pattern in GUARD_PATTERNS.items():
        code, out = run_text(["pgrep", "-f", "--", pattern])
        if code not in (0, 1):   # 1 is "nothing matched"; anything else means pgrep did not look
            raise GuardError(f"pgrep could not run the '{label}' check (exit {code})")
        for token in out.split():
            if token.isdigit():
                matched.setdefault(int(token), label)
    if not matched:
        return []
    table = process_table()   # read after pgrep, so a runner that just started is in it
    family = own_family(own_pid, table)
    found = []
    for pid, label in sorted(matched.items()):
        if pid in family or pid not in table:
            continue
        command = table[pid][1]
        hit = re.search(GUARD_PATTERNS[label], command)
        found.append({"pid": pid, "check": label, "program": program_name(command),
                      "matched": hit.group(0).strip() if hit else "", "started_at": iso(process_started(pid))})
    return found


def guard_refusals(runners: Sequence[Dict[str, Any]]) -> List[str]:
    return [f"another test run is active: pid {r['pid']} ({r['check']}: {r['program']} '{r['matched']}', "
            f"started {r['started_at'] or 'unknown'}). Wait for it to finish; runs share the servers, "
            "the QA account, the test database and Redis." for r in runners]


def process_cwd(pid: int) -> Optional[str]:
    code, out = run_text(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"])
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return None


def listening_pids(port: int) -> List[int]:
    _, out = run_text(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    return sorted({int(token) for token in out.split() if token.isdigit()})


def checkout_of(directory: str) -> Dict[str, Any]:
    """The git checkout a server's working directory belongs to, and what is uncommitted under it."""
    top = git_out(["rev-parse", "--show-toplevel"], Path(directory))
    if not top:
        return {"toplevel": None, "head": None, "dirty_paths": None}
    relative = os.path.relpath(os.path.realpath(directory), os.path.realpath(top))
    return {"toplevel": top, "head": git_out(["rev-parse", "HEAD"], Path(directory)),
            "dirty_paths": dirty_paths(Path(top), None if relative == "." else relative)}


def listener(port: int) -> Dict[str, Any]:
    pids = listening_pids(port)
    record: Dict[str, Any] = {"port": port, "listening": bool(pids), "pids": pids}
    if not pids:
        return record
    pid = pids[0]
    _, command = run_text(["ps", "-o", "command=", "-p", str(pid)])
    cwd = process_cwd(pid)
    record.update({"pid": pid, "started_at": iso(process_started(pid)), "command": command.strip()[:240],
                   "cwd": cwd, "checkout": checkout_of(cwd) if cwd else None})
    return record


def listener_identity(port: int) -> Tuple[Tuple[int, ...], Optional[str]]:
    pids = listening_pids(port)
    return tuple(pids), iso(process_started(pids[0])) if pids else None


def newest_source_change(app_dir: Path) -> Optional[datetime]:
    """The newest modification time of any .py file under app_dir."""
    newest = None
    for root, dirs, files in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                try:
                    moment = os.stat(os.path.join(root, name)).st_mtime
                except OSError:
                    continue
                newest = moment if newest is None or moment > newest else newest
    return datetime.fromtimestamp(newest, timezone.utc) if newest is not None else None


def started_after(started_at: Optional[str], changed: Optional[datetime]) -> Optional[bool]:
    """Whether a process started after a file change. Process start times have one-second
    resolution, so a start in the same second as the change counts as not after it."""
    if not started_at or not changed:
        return None
    started = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return started.timestamp() > int(changed.timestamp())


def url_port(url: str) -> Tuple[Optional[str], Optional[int]]:
    parts = urllib.parse.urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.hostname, port


# ----------------------------------------------------------------------------- HTTP (GET only)
def http_get_json(url: str, timeout: float = 5.0) -> Tuple[Optional[int], Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with opener.open(request, timeout=timeout) as resp:
            status, body = resp.status, resp.read(4 * 1024 * 1024)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return None, None
    try:
        return status, json.loads(body.decode("utf-8"))
    except ValueError:
        return status, None


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:80]


def error_kind(text: Any) -> Optional[str]:
    """A provider or task error reduced to its kind. The text is never kept: it can quote a request
    URL, and Live Score takes its key and secret as query parameters."""
    if not text:
        return None
    text = str(text)
    status = re.search(r"\bHTTP (\d{3})\b", text) or re.search(r"\bstatus(?: code)?[ :=]+(\d{3})\b", text, re.I)
    if status:
        return f"http_{status.group(1)}"
    lowered = text.lower()
    for kind, needles in (("timeout", ("timed out", "timeout")),
                          ("local_permission", ("operation not permitted", "permissionerror", "permission denied")),
                          ("connection", ("connection", "refused", "unreachable", "nodename", "errno")),
                          ("allowance", ("allowance", "quota", "rate limit", "budget", "ceiling"))):
        if any(needle in lowered for needle in needles):
            return kind
    return "other"


def provider_snapshot(status: Any) -> Optional[Dict[str, Any]]:
    """The few fields of /api/v1/data-providers/status that explain a live skip, and nothing else:
    per provider its integration status, last success, last error time and error kind."""
    if not isinstance(status, dict):
        return None
    providers = []
    for entry in status.get("chain") or []:
        if isinstance(entry, dict):
            providers.append({
                "role": "match data", "name": _scalar(entry.get("name")),
                "integration_status": _scalar(entry.get("integration_status")),
                "configured": _scalar(entry.get("configured")),
                "last_success_at": _scalar(entry.get("last_success_at")),
                "last_error_at": _scalar(entry.get("last_error_at")),
                "error_kind": error_kind(entry.get("last_error")),
                "cooling_down": bool(entry.get("cooling_down")),
            })
    forecasts = status.get("forecasts")
    if isinstance(forecasts, dict):
        last_sync = forecasts.get("last_sync") if isinstance(forecasts.get("last_sync"), dict) else {}
        providers.append({
            "role": "forecasts", "name": _scalar(forecasts.get("active_provider")),
            "integration_status": _scalar(forecasts.get("integration_status")),
            "configured": _scalar(forecasts.get("configured")),
            "last_success_at": _scalar(last_sync.get("synced_at")),
            "last_error_at": None, "error_kind": None,
            "cooling_down": bool(forecasts.get("cooling_down")),
        })
    tasks = {}
    scheduler = status.get("scheduler") if isinstance(status.get("scheduler"), dict) else {}
    for name, task in sorted((scheduler.get("tasks") or {}).items()):
        if isinstance(task, dict):
            tasks[str(name)] = {"last_success_at": _scalar(task.get("last_success_at")),
                                "last_error_at": _scalar(task.get("last_error_at")),
                                "error_kind": error_kind(task.get("last_error"))}
    return {"checked_at": _scalar(status.get("checked_at")), "providers": providers, "scheduler_tasks": tasks}


def health_snapshot(api_url: str) -> Dict[str, Any]:
    code, body = http_get_json(api_url.rstrip("/") + "/health")
    record: Dict[str, Any] = {"http_status": code}
    if isinstance(body, dict):
        record.update({key: _scalar(body.get(key)) for key in ("status", "environment", "version")})
    return record


# ----------------------------------------------------------------------------- backend suite inputs
def conftest_database_default(conftest: Path = CONFTEST) -> Tuple[Optional[str], bool]:
    """(the URL backend/tests/conftest.py uses, whether it reads TEST_DATABASE_URL first).

    The URL is read from that file rather than copied here, so this script never holds a
    credential. If conftest ignores the variable, its session fixture keeps creating and dropping
    tables in its own database whatever this script sets.
    """
    try:
        tree = ast.parse(conftest.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return None, False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "TEST_DATABASE_URL" for t in node.targets)):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value, False
        if (isinstance(value, ast.Call) and len(value.args) == 2
                and all(isinstance(arg, ast.Constant) for arg in value.args)
                and value.args[0].value == "TEST_DATABASE_URL"):
            return value.args[1].value, True
    return None, False


def describe_database_url(url: Optional[str]) -> Dict[str, Any]:
    """Scheme, host, port and database name only, never the user or the password."""
    if not url:
        return {"scheme": None, "host": None, "port": None, "database": None}
    parts = urllib.parse.urlsplit(url)
    return {"scheme": parts.scheme, "host": parts.hostname, "port": parts.port,
            "database": parts.path.lstrip("/") or None}


#: Run in the backend's own interpreter, so the database and Redis are reached exactly as the tests
#: reach them. Only exception class names come back: a message can carry the URL.
BACKEND_PROBE = r'''
import json, os
result = {}
try:
    from sqlalchemy import create_engine, text
    engine = create_engine(os.environ["TEST_DATABASE_URL"], connect_args={"connect_timeout": 3})
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    result["postgres"] = "ok"
except Exception as exc:
    result["postgres"] = type(exc).__name__
try:
    from app.core.redis import get_redis_client
    get_redis_client().ping()
    result["redis"] = "ok"
except Exception as exc:
    result["redis"] = type(exc).__name__
print("PROBE " + json.dumps(result))
'''


def probe_backend_services(database_url: str) -> Dict[str, str]:
    code, out = run_text([str(VENV_PYTHON), "-c", BACKEND_PROBE], cwd=BACKEND,
                         env_extra={"TEST_DATABASE_URL": database_url}, timeout=60)
    for line in out.splitlines():
        if line.startswith("PROBE "):
            try:
                return {key: str(value) for key, value in json.loads(line[6:]).items()}
            except ValueError:
                break
    return {"postgres": f"probe failed (exit {code})", "redis": f"probe failed (exit {code})"}


VERSIONS_PROBE = r'''
import json, sys
from importlib import metadata
out = {"python": sys.version.split()[0]}
for name in ("pytest", "pytest-cov", "pytest-asyncio"):
    try:
        out[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        out[name] = None
print(json.dumps(out))
'''


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def tool_versions() -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for name, argv in (("node", ["node", "-v"]), ("npm", ["npm", "-v"]), ("macos", ["sw_vers", "-productVersion"])):
        code, out = run_text(argv, cwd=FRONTEND)
        versions[name] = out.strip().splitlines()[0] if code == 0 and out.strip() else None
    package = _read_json(FRONTEND / "node_modules" / "@playwright" / "test" / "package.json") or {}
    versions["playwright"] = package.get("version")
    browsers = _read_json(FRONTEND / "node_modules" / "playwright-core" / "browsers.json") or {}
    chromium = next((b for b in browsers.get("browsers") or [] if b.get("name") == "chromium"), None)
    versions["chromium"] = (f"{chromium.get('browserVersion')} (revision {chromium.get('revision')})"
                            if chromium else None)
    code, out = run_text([str(VENV_PYTHON), "-c", VERSIONS_PROBE])
    try:
        backend = json.loads(out.strip().splitlines()[-1]) if code == 0 else {}
    except (ValueError, IndexError):
        backend = {}
    versions["backend python (venv311)"] = backend.get("python")
    for name in ("pytest", "pytest-cov", "pytest-asyncio"):
        versions[name] = backend.get(name)
    for label, container in (("postgres image", POSTGRES_CONTAINER), ("redis image", REDIS_CONTAINER)):
        code, out = run_text(["docker", "inspect", "-f", "{{.Config.Image}}", container], timeout=20)
        versions[label] = out.strip() if code == 0 and out.strip() else None
    return versions


# ----------------------------------------------------------------------------- lock
class Refused(Exception):
    """A reason not to start, worded for the person reading the console."""


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def default_lock_path() -> Path:
    """Inside the git common directory, which every worktree of this repository shares. $TMPDIR is
    not shared: sandboxed sessions each get their own."""
    common = git_common_dir(REPO) or (REPO / ".git")
    return common / "predictionsappsui-test-evidence.lock"


class RunLock:
    """An atomic lock (mkdir) so that two evidence runs cannot race past the guard together."""

    def __init__(self, path: Path):
        self.path = path
        self.held = False
        self.cleared_stale: Optional[Dict[str, Any]] = None
        self.acquired_at: Optional[str] = None

    def _owner(self) -> Optional[Dict[str, Any]]:
        owner = _read_json(self.path / "owner.json")
        return owner if isinstance(owner, dict) else None

    def acquire(self, run_id: str) -> None:
        for attempt in (1, 2):
            try:
                os.mkdir(self.path)
                break
            except FileExistsError:
                owner = self._owner()
                pid = owner.get("pid") if owner else None
                try:
                    young = time.time() - self.path.stat().st_mtime < 60
                except OSError:
                    young = False
                if attempt == 2 or (isinstance(pid, int) and pid_alive(pid)) or (owner is None and young):
                    run = owner.get("run_id") if owner else "unknown"
                    raise Refused(f"another evidence run holds the lock {self.path} "
                                  f"(pid {pid if pid else 'unknown'}, run {run})")
                # The owner is gone, so the lock is stale. Keep who it was for the record and take it.
                self.cleared_stale = {key: (owner or {}).get(key) for key in ("pid", "run_id", "acquired_at")}
                shutil.rmtree(self.path, ignore_errors=True)
        self.acquired_at = iso(utc_now())
        (self.path / "owner.json").write_text(
            json.dumps({"pid": os.getpid(), "run_id": run_id, "acquired_at": self.acquired_at}), encoding="utf-8")
        self.held = True

    def release(self) -> None:
        if self.held:
            owner = self._owner()
            if owner is None or owner.get("pid") == os.getpid():
                shutil.rmtree(self.path, ignore_errors=True)
            self.held = False

    def record(self) -> Dict[str, Any]:
        return {"path": str(self.path), "acquired_at": self.acquired_at, "stale_lock_cleared": self.cleared_stale}


# ----------------------------------------------------------------------------- watcher
class Watcher(threading.Thread):
    """Samples the machine while the suites run. Anything it sees contaminates the run."""

    def __init__(self, baseline_repo: Dict[str, Any], baseline_servers: Dict[str, Dict[str, Any]],
                 interval: float = WATCH_INTERVAL_SECONDS):
        super().__init__(name="test-evidence-watcher", daemon=True)
        self.interval = interval
        self.baseline_repo = baseline_repo
        self.baseline_servers = {role: (tuple(rec.get("pids") or ()), rec.get("started_at"), rec.get("port"))
                                 for role, rec in baseline_servers.items()}
        self.samples = 0
        self.current_suite: Optional[str] = None
        self.anomalies: Dict[str, Dict[str, Any]] = {}
        self._stopping = threading.Event()
        self._mutex = threading.Lock()

    def run(self) -> None:
        while not self._stopping.wait(self.interval):
            self.sample()

    def stop(self) -> None:
        self._stopping.set()

    def _note(self, key: str, kind: str, detail: str, now: str) -> None:
        entry = self.anomalies.get(key)
        if entry:
            entry.update(last_seen=now, samples=entry["samples"] + 1, detail=detail)
        else:
            self.anomalies[key] = {"kind": kind, "detail": detail, "first_seen": now, "last_seen": now,
                                   "samples": 1, "during": self.current_suite}

    def sample(self) -> None:
        with self._mutex:
            self.samples += 1
            now = iso(utc_now()) or ""
            try:
                runners = find_foreign_runners()
            except GuardError as exc:
                self._note("guard", "watch_failed", str(exc), now)
                runners = []
            for runner in runners:
                self._note(f"runner-{runner['pid']}", "foreign_runner",
                           f"pid {runner['pid']} ({runner['check']}: {runner['program']} '{runner['matched']}')", now)
            for role, (pids, started, port) in self.baseline_servers.items():
                current = listener_identity(port)
                if current != (pids, started):
                    kind = "server_down" if not current[0] else "server_restart"
                    self._note(f"server-{role}-{current}", kind,
                               f"{role} on :{port} was pid {','.join(map(str, pids)) or 'none'} started {started}; "
                               f"now pid {','.join(map(str, current[0])) or 'none'} started {current[1]}", now)
            state = repo_state()
            before_head, head = self.baseline_repo.get("head") or "?", state.get("head") or "?"
            if head != before_head:
                self._note(f"head-{head}", "head_changed", f"HEAD moved from {before_head[:12]} to {head[:12]}", now)
            if tree_fingerprint(state)[1:] != tree_fingerprint(self.baseline_repo)[1:]:
                before, after = set(self.baseline_repo.get("dirty_paths") or ()), set(state.get("dirty_paths") or ())
                changed = sorted(before ^ after) or ["(same paths, different content)"]
                self._note("tree", "tree_changed", "working tree changed: " + "; ".join(changed[:10])
                           + (f" and {len(changed) - 10} more" if len(changed) > 10 else ""), now)

    def record(self) -> Dict[str, Any]:
        return {"interval_seconds": self.interval, "samples": self.samples,
                "anomalies": sorted(self.anomalies.values(), key=lambda a: (a["first_seen"], a["kind"]))}


# ----------------------------------------------------------------------------- running a suite
_CURRENT_CHILD: Optional[subprocess.Popen] = None
_STOP_REQUESTED = threading.Event()


def _on_sigterm(signum: int, frame: Any) -> None:
    """Stop after the current suite, and ask the child to stop the way Ctrl-C would, so pytest and
    Playwright still write their reports. A terminal Ctrl-C reaches the child by itself."""
    _STOP_REQUESTED.set()
    child = _CURRENT_CHILD
    if child is not None and child.poll() is None:
        try:
            child.send_signal(signal.SIGINT)
        except OSError:
            pass


def child_env(extra: Dict[str, str]) -> Dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(INHERITED_ENV_DROPPED_PREFIXES) and key not in INHERITED_ENV_DROPPED}
    env.update(extra)
    return env


def run_child(argv: Sequence[str], cwd: Path, env: Dict[str, str], console: Path,
              echo: bool = True) -> Dict[str, Any]:
    """Run one suite, copying its output line by line to the console log and the terminal. The exit
    code is the child's own, from wait(), never a pipe's."""
    global _CURRENT_CHILD
    started = utc_now()
    interrupts = 0
    with open(console, "wb") as log:
        proc = subprocess.Popen(list(argv), cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        _CURRENT_CHILD = proc
        try:
            assert proc.stdout is not None
            while True:
                try:
                    chunk = proc.stdout.readline()
                    if not chunk:
                        break
                    log.write(chunk)
                    log.flush()
                    if echo:
                        sys.stdout.write(chunk.decode("utf-8", "replace"))
                        sys.stdout.flush()
                except KeyboardInterrupt:
                    # The child got the same Ctrl-C and is writing its interrupted summary: keep
                    # reading. A second Ctrl-C terminates it and a third kills it.
                    interrupts += 1
                    _STOP_REQUESTED.set()
                    if interrupts == 2:
                        proc.terminate()
                    elif interrupts >= 3:
                        proc.kill()
            while True:
                try:
                    code = proc.wait()
                    break
                except KeyboardInterrupt:
                    interrupts += 1
                    _STOP_REQUESTED.set()
                    proc.kill()
        finally:
            _CURRENT_CHILD = None
    finished = utc_now()
    return {"exit_code": code, "started_at": iso(started), "finished_at": iso(finished),
            "duration_seconds": round((finished - started).total_seconds(), 1),
            "interrupted": interrupts > 0 or _STOP_REQUESTED.is_set()}


def backend_command(raw: Path, grep: Optional[str] = None) -> List[str]:
    argv = [str(VENV_PYTHON), "-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-q", "-rfEs",
            f"--junitxml={raw / 'backend.junit.xml'}", "-o", "junit_suite_name=backend",
            "-o", "junit_family=xunit2", "-o", "junit_logging=no"]
    return argv + (["-k", grep] if grep else [])


def playwright_command(project: str, raw: Path, grep: Optional[str] = None) -> List[str]:
    # The binary directly, not `npx`: one process layer fewer between the runner and its exit code.
    argv = [str(PLAYWRIGHT_BIN), "test", f"--project={project}", "--forbid-only", "--retries=0",
            f"--output={raw / ('artifacts-' + project)}", "--reporter=list,json,junit"]
    return argv + (["--grep", grep] if grep else [])


def suite_kind(name: Any) -> str:
    return "pytest" if name == "backend" else "playwright"


#: The option each kind of suite takes its filter in, as backend_command and playwright_command add it.
FILTER_OPTION = {"pytest": "-k", "playwright": "--grep"}
#: Options whose value is a path into the raw directory. Paths are scrubbed differently depending on
#: where the raw directory was, so only the file name is compared.
PATH_OPTIONS = ("--junitxml=", "--output=")


def command_shape(argv: Sequence[str]) -> List[str]:
    """A command without what depends on the machine: the program's directory and the raw directory."""
    shape = [os.path.basename(str(argv[0]))] if argv else []
    for arg in list(argv)[1:]:
        arg = str(arg)
        prefix = next((p for p in PATH_OPTIONS if arg.startswith(p)), None)
        shape.append(prefix + os.path.basename(arg[len(prefix):]) if prefix else arg)
    return shape


def recorded_filter(name: str, argv: Sequence[str]) -> Tuple[bool, Optional[str]]:
    """(the command is exactly the one the runner builds for this suite, the filter it carries).

    `verify` uses this to work out whether a run was filtered from the command itself, not from the
    partial flag beside it. A command the runner never builds (a -x, a file argument, another
    project) fails the first value, because nothing in the totals would show it.
    """
    argv = [str(arg) for arg in argv]
    option = FILTER_OPTION[suite_kind(name)]
    grep = argv[argv.index(option) + 1] if option in argv[:-1] else None
    raw = Path("raw")
    expected = backend_command(raw, grep) if name == "backend" else playwright_command(name, raw, grep)
    return command_shape(argv) == command_shape(expected), grep


def playwright_env(project: str, raw: Path, base_url: str, api_url: str) -> Dict[str, str]:
    # Both output files must be set: a JSON or JUnit reporter without one prints its whole report
    # into the console log.
    return {
        "PLAYWRIGHT_JSON_OUTPUT_FILE": str(raw / f"playwright-{project}.json"),
        "PLAYWRIGHT_JUNIT_OUTPUT_FILE": str(raw / f"playwright-{project}.junit.xml"),
        "PLAYWRIGHT_JUNIT_SUITE_NAME": f"playwright-{project}",
        "PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME": "1",
        "PLAYWRIGHT_JUNIT_STRIP_ANSI": "1",
        "FORCE_COLOR": "0",
        "E2E_BASE_URL": base_url,
        "E2E_API_URL": api_url,
    }


# ----------------------------------------------------------------------------- reading the reports
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
PW_RUNNING = re.compile(r"^Running (\d+) tests? using (\d+) workers?")
#: Exactly two spaces: the failure headers listed under a bucket are indented by four, and a list
#: line has its status mark and index before the title.
PW_BUCKET = re.compile(r"^  (\d+) (failed|interrupted|flaky|skipped|did not run|passed)(?: \(.*\))?$")
PW_FATAL = re.compile(r"^  (?:(\d+) errors were|1 error was) not a part of any test")
PW_EPILOGUE_EXTRA = re.compile(r"^(    \S.*|  Slow test file: .*|  Consider running tests from slow files.*)$")
PYTEST_FINAL = re.compile(r"^(?:=+ )?((?:\d+ [a-z]+(?:, )?)+|no tests ran) in ([\d.]+)s(?: \([\d:.]+\))?(?: =+)?$")
PYTEST_COUNT = re.compile(r"(\d+) ([a-z]+)")
PLAYWRIGHT_BUCKETS = ("passed", "failed", "flaky", "skipped", "did_not_run", "interrupted")
PYTEST_COUNTS = ("passed", "failed", "skipped", "xfailed", "xpassed", "errors", "warnings", "deselected")


def strip_ansi(text: str) -> str:
    return ANSI.sub("", text)


def console_lines(text: str) -> List[str]:
    """A console's lines with colour codes removed line by line, so that line numbers stay those of
    the raw text and a tail cut by line number holds what the parsers read."""
    return [strip_ansi(line) for line in text.splitlines()]


def playwright_epilogue(lines: Sequence[str]) -> Tuple[int, int]:
    """(first, end) of the list reporter's final summary in `lines`; first == end when there is none.

    The epilogue is read backwards from the last line and stops at the first line that cannot
    belong to it, so a test that prints "  3 passed" in the middle of the run is not counted.
    """
    end = len(lines)
    while end and not lines[end - 1].strip():
        end -= 1
    first = end
    while first and (PW_BUCKET.match(lines[first - 1]) or PW_FATAL.match(lines[first - 1])
                     or PW_EPILOGUE_EXTRA.match(lines[first - 1])):
        first -= 1
    return first, end


def pytest_final_index(lines: Sequence[str]) -> Optional[int]:
    """The index of pytest's final "N passed in Xs" line, the last one when several match."""
    for index in range(len(lines) - 1, -1, -1):
        if PYTEST_FINAL.match(lines[index].strip()):
            return index
    return None


def console_tail(text: str, kind: str, count: int) -> str:
    """The last `count` lines of a console, extended upwards when the reporter's final summary starts
    earlier. With many failures Playwright names each one under "N failed", and a fixed tail would
    start in the middle of the summary; `verify` reads the summary back from this tail."""
    lines = text.splitlines()
    stripped = console_lines(text)
    first = max(0, len(lines) - count)
    if kind == "pytest":
        final = pytest_final_index(stripped)
        first = first if final is None else min(first, final)
    else:
        start, end = playwright_epilogue(stripped)
        first = first if start == end else min(first, start)
    return "\n".join(lines[first:]) + "\n"


def parse_playwright_console(text: str) -> Dict[str, Any]:
    """The list reporter's own summary: "Running N tests" and the bucket lines at the very end."""
    lines = console_lines(text)
    planned = workers = None
    for line in lines:
        running = PW_RUNNING.match(line)
        if running:
            planned, workers = int(running.group(1)), int(running.group(2))
    first, end = playwright_epilogue(lines)
    block = lines[first:end]
    buckets: Optional[Dict[str, int]] = None
    fatal = 0
    for line in block:
        bucket = PW_BUCKET.match(line)
        if bucket:
            buckets = buckets or {name: 0 for name in PLAYWRIGHT_BUCKETS}
            buckets[bucket.group(2).replace(" ", "_")] = int(bucket.group(1))
        error = PW_FATAL.match(line)
        if error:
            fatal = int(error.group(1) or 1)
    # With many failures the names listed under "N failed" would push the totals out of the quote.
    quoted = block if len(block) <= 60 else [line for line in block if PW_BUCKET.match(line) or PW_FATAL.match(line)]
    return {"planned": planned, "workers": workers, "buckets": buckets, "fatal_errors": fatal, "lines": quoted}


def outcome_of(test: Dict[str, Any]) -> str:
    """Playwright's computeTestCaseOutcome, recomputed from the results in the JSON report."""
    expected_status = test.get("expectedStatus")
    counts = {"skipped": 0, "did_not_run": 0, "expected": 0, "interrupted": 0, "unexpected": 0}
    for result in test.get("results") or []:
        status = result.get("status")
        if status == "interrupted":
            counts["interrupted"] += 1
        elif status == "skipped" and expected_status == "skipped":
            counts["skipped"] += 1
        elif status == "skipped":
            counts["did_not_run"] += 1
        elif status == expected_status:
            counts["expected"] += 1
        else:
            counts["unexpected"] += 1
    if counts["expected"] == 0 and counts["unexpected"] == 0:
        return "skipped"
    if counts["unexpected"] == 0:
        return "expected"
    if counts["expected"] == 0 and counts["skipped"] == 0:
        return "unexpected"
    return "flaky"


def human_bucket(test: Dict[str, Any]) -> str:
    """The bucket Playwright's own summary puts a test in. JSON stats and JUnit count interrupted
    and did-not-run tests as skipped, so an interrupted run would otherwise read as "2 skipped"."""
    outcome = outcome_of(test)
    if outcome == "skipped":
        results = test.get("results") or []
        if any(r.get("status") == "interrupted" for r in results):
            return "interrupted"
        if not results or test.get("expectedStatus") != "skipped":
            return "did_not_run"
        return "skipped"
    return {"expected": "passed", "unexpected": "failed", "flaky": "flaky"}[outcome]


def iter_json_tests(suites: Any, titles: Optional[Tuple[str, ...]] = None
                    ) -> Iterator[Tuple[Dict[str, Any], Dict[str, Any], Tuple[str, ...]]]:
    """(spec, test, describe titles + test title) for every test in a JSON report."""
    for suite in suites or []:
        # The top level is the file, whose title the location already shows.
        path = () if titles is None else titles + (suite.get("title") or "",)
        for spec in suite.get("specs") or []:
            for test in spec.get("tests") or []:
                yield spec, test, tuple(t for t in path if t) + (spec.get("title") or "",)
        yield from iter_json_tests(suite.get("suites"), path)


def first_line(text: Any) -> str:
    for line in strip_ansi(str(text or "")).splitlines():
        if line.strip():
            return line.strip()[:300]
    return ""


def annotation_reasons(test: Dict[str, Any]) -> str:
    seen: List[str] = []
    sources = list(test.get("annotations") or [])
    for result in test.get("results") or []:
        sources += list(result.get("annotations") or [])
    for annotation in sources:
        if annotation.get("type") in ("skip", "fixme") and annotation.get("description"):
            if annotation["description"] not in seen:
                seen.append(annotation["description"])
    return "; ".join(seen)


def analyse_playwright_json(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"present": False}
    buckets = {name: 0 for name in PLAYWRIGHT_BUCKETS}
    projects = set()
    disagreements = 0
    skipped_tests: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for spec, test, titles in iter_json_tests(data.get("suites")):
        bucket = human_bucket(test)
        buckets[bucket] += 1
        projects.add(test.get("projectName"))
        if test.get("status") != outcome_of(test):
            disagreements += 1
        location = f"{spec.get('file')}:{spec.get('line')}"
        title = " > ".join(titles)
        if bucket in ("skipped", "did_not_run", "interrupted"):
            skipped_tests.append({"project": test.get("projectName"), "location": location, "title": title,
                                  "bucket": bucket, "reason": annotation_reasons(test)})
        if bucket in ("failed", "interrupted", "flaky"):
            message = ""
            for result in reversed(test.get("results") or []):
                errors = result.get("errors") or []
                error = errors[0] if errors else (result.get("error") or {})
                message = first_line(error.get("message"))
                if message:
                    break
            if message or bucket == "failed":
                failures.append({"project": test.get("projectName"), "location": location, "title": title,
                                 "bucket": bucket, "error": message})
    stats = data.get("stats") or {}
    return {
        "present": True,
        "total": sum(buckets.values()),
        "buckets": buckets,
        "projects": sorted(p for p in projects if p),
        "stats": {key: stats.get(key) for key in ("expected", "unexpected", "flaky", "skipped")},
        "status_disagreements": disagreements,
        "fatal_errors": len(data.get("errors") or []),
        "playwright_version": (data.get("config") or {}).get("version"),
        "skipped_tests": skipped_tests,
        "failures": failures,
    }


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _root_and_suites(text: str) -> Tuple[ET.Element, List[ET.Element]]:
    root = ET.fromstring(text)
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return root, suites


def analyse_playwright_junit(text: str) -> Dict[str, Any]:
    """Totals recomputed from the testcases themselves, beside the totals the file states."""
    root, suites = _root_and_suites(text)
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    stated = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    projects = set()
    for suite in suites:
        projects.add(suite.get("hostname"))
        for key in stated:
            stated[key] += _int(suite.get(key)) or 0
        for case in suite.findall("testcase"):
            totals["tests"] += 1
            if case.find("failure") is not None:
                totals["failures"] += 1
            elif case.find("error") is not None:
                totals["errors"] += 1
            elif case.find("skipped") is not None:
                totals["skipped"] += 1
    root_stated = {key: _int(root.get(key)) for key in stated} if root.tag == "testsuites" else dict(stated)
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    return {**totals, "projects": sorted(p for p in projects if p),
            "consistent": stated == {k: totals[k] for k in stated} and root_stated == stated}


def analyse_pytest_junit(text: str) -> Dict[str, Any]:
    """pytest's JUnit (xunit2), counted the way pytest's own summary line counts.

    A test that fails and then errors in teardown is written as two testcase elements with the
    same name, and a test that passes and then errors in teardown has only an <error>. So outcomes
    are decided per test name, and errors are counted per <error> element, as pytest does.
    """
    _, suites = _root_and_suites(text)
    cases: Dict[Tuple[str, str], List[ET.Element]] = {}
    stated = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    elements = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in stated:
            stated[key] += _int(suite.get(key)) or 0
        for case in suite.findall("testcase"):
            elements["tests"] += 1
            cases.setdefault((case.get("classname") or "", case.get("name") or ""), []).append(case)
    counts = {"passed_or_xpassed": 0, "failed": 0, "errors": 0, "skipped": 0, "xfailed": 0}
    skips: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    for (classname, name), group in cases.items():
        children = [child for case in group for child in case if child.tag in ("failure", "error", "skipped")]
        for child in children:
            elements[{"failure": "failures", "error": "errors", "skipped": "skipped"}[child.tag]] += 1
        test = f"{classname}::{name}" if classname else name
        errors = [c for c in children if c.tag == "error"]
        counts["errors"] += len(errors)
        for error in errors:
            failures.append({"test": test, "kind": "error", "message": first_line(error.get("message"))})
        failed = [c for c in children if c.tag == "failure"]
        skipped = [c for c in children if c.tag == "skipped"]
        strict_xpass = [c for c in skipped
                        if c.get("type") is None and "passes unexpectedly" in (c.get("message") or "")]
        if failed or strict_xpass:
            counts["failed"] += 1
            for failure in failed + strict_xpass:
                failures.append({"test": test, "kind": "failure", "message": first_line(failure.get("message"))})
        elif any(c.get("type") == "pytest.xfail" for c in skipped):
            counts["xfailed"] += 1
        elif skipped:
            counts["skipped"] += 1
            for skip in skipped:
                location = (skip.text or "").split(": ", 1)[0] if skip.text else ""
                skips.append({"test": test, "location": location, "reason": first_line(skip.get("message"))})
        elif any((e.get("message") or "").startswith("failed on setup") or e.get("message") == "collection failure"
                 for e in errors):
            pass   # never ran: pytest counts only the error
        else:
            counts["passed_or_xpassed"] += 1
    return {"testcases": elements["tests"], **counts, "skips": skips, "failed_tests": failures,
            "consistent": stated == elements}


def parse_pytest_console(text: str) -> Optional[Dict[str, Any]]:
    """pytest's final line, e.g. "2 failed, 1400 passed, 14 skipped in 312.4s", with -q or without."""
    lines = console_lines(text)
    index = pytest_final_index(lines)
    if index is None:
        return None
    line = lines[index].strip()
    final = PYTEST_FINAL.match(line)
    assert final is not None
    counts = {name: 0 for name in PYTEST_COUNTS}
    for number, word in PYTEST_COUNT.findall(final.group(1)):
        word = {"error": "errors", "warning": "warnings"}.get(word, word)
        if word in counts:
            counts[word] = int(number)
    return {"line": line, "counts": counts, "seconds": float(final.group(2))}


def check(name: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def playwright_junit_checks(junit: Dict[str, Any], buckets: Dict[str, int],
                            planned: Optional[int]) -> List[Dict[str, Any]]:
    """What the committed JUnit must agree with. `verify` reruns exactly these."""
    b = buckets
    skipped_like = b["skipped"] + b["did_not_run"] + b["interrupted"]
    return [
        check("JUnit totals match its own testcases", junit.get("consistent"), ""),
        check("JUnit tests = planned", junit.get("tests") == planned,
              f"JUnit {junit.get('tests')} / planned {planned}"),
        check("JUnit failures + errors = failed", junit.get("failures", 0) + junit.get("errors", 0) == b["failed"],
              f"JUnit {junit.get('failures', 0) + junit.get('errors', 0)} / failed {b['failed']}"),
        check("JUnit skipped = skipped + did not run + interrupted", junit.get("skipped") == skipped_like,
              f"JUnit {junit.get('skipped')} / {skipped_like}"),
        check("JUnit passed = passed + flaky", junit.get("passed") == b["passed"] + b["flaky"],
              f"JUnit {junit.get('passed')} / {b['passed'] + b['flaky']}"),
    ]


def pytest_junit_checks(junit: Dict[str, Any], counts: Dict[str, int]) -> List[Dict[str, Any]]:
    """What the committed backend JUnit must agree with. `verify` reruns exactly these."""
    passed = counts["passed"] + counts["xpassed"]
    unreachable = sum("not reachable" in (s.get("reason") or "").lower() for s in junit.get("skips") or [])
    return [
        check("JUnit totals match its own testcases", junit.get("consistent"), ""),
        check("JUnit failed = pytest failed", junit.get("failed") == counts["failed"],
              f"JUnit {junit.get('failed')} / pytest {counts['failed']}"),
        check("JUnit errors = pytest errors", junit.get("errors") == counts["errors"],
              f"JUnit {junit.get('errors')} / pytest {counts['errors']}"),
        check("JUnit skipped = pytest skipped", junit.get("skipped") == counts["skipped"],
              f"JUnit {junit.get('skipped')} / pytest {counts['skipped']}"),
        check("JUnit xfailed = pytest xfailed", junit.get("xfailed") == counts["xfailed"],
              f"JUnit {junit.get('xfailed')} / pytest {counts['xfailed']}"),
        check("JUnit passed = pytest passed + xpassed", junit.get("passed_or_xpassed") == passed,
              f"JUnit {junit.get('passed_or_xpassed')} / pytest {passed}"),
        check("no skip says the test database or Redis is not reachable", unreachable == 0,
              f"{unreachable} such skip(s)"),
    ]


def read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def playwright_checks(project: str, human: Dict[str, Any], json_report: Dict[str, Any],
                      junit: Optional[Dict[str, Any]], exit_code: Optional[int], interrupted: bool
                      ) -> List[Dict[str, Any]]:
    """Every post-check of one Playwright project, from the reporter's human summary, the analysis
    of the JSON report, the analysis of the JUnit file and the exit code. `run` records these and
    `verify` makes them again from summary.json and the published files, so that no recorded
    outcome, the exit code's included, is taken on trust."""
    planned = human.get("planned")
    checks = [check("human summary present", human.get("buckets") is not None and planned is not None,
                    "the list reporter's 'Running N tests' line and its final bucket lines")]
    hb = human.get("buckets") or {name: 0 for name in PLAYWRIGHT_BUCKETS}
    checks.append(check("planned = sum of the human buckets", planned == sum(hb.values()),
                        f"planned {planned} / buckets {sum(hb.values())}"))
    checks.append(check("JSON report present", json_report.get("present")))
    jb = json_report.get("buckets") or {name: 0 for name in PLAYWRIGHT_BUCKETS}
    if json_report.get("present"):
        for name in PLAYWRIGHT_BUCKETS:
            checks.append(check(f"human {name.replace('_', ' ')} = JSON", hb.get(name) == jb.get(name),
                                f"human {hb.get(name)} / JSON {jb.get(name)}"))
        stats = json_report.get("stats") or {}
        skipped_like = sum(jb.get(name) or 0 for name in ("skipped", "did_not_run", "interrupted"))
        checks.append(check("JSON stats agree with the recomputed buckets",
                            stats.get("expected") == jb.get("passed") and stats.get("unexpected") == jb.get("failed")
                            and stats.get("flaky") == jb.get("flaky") and stats.get("skipped") == skipped_like,
                            f"stats {stats}"))
        checks.append(check("JSON outcomes match their results", json_report.get("status_disagreements") == 0,
                            f"{json_report.get('status_disagreements')} disagreement(s)"))
        checks.append(check("JSON holds exactly the requested project", json_report.get("projects") == [project],
                            f"{json_report.get('projects')}"))
    checks.append(check("JUnit report present and parseable", junit is not None))
    if junit is not None:
        checks += playwright_junit_checks(junit, hb, planned)
        checks.append(check("JUnit holds exactly the requested project", junit.get("projects") == [project],
                            f"{junit.get('projects')}"))
    fatal = max(human.get("fatal_errors") or 0, json_report.get("fatal_errors") or 0)
    green = hb.get("failed") == 0 and hb.get("interrupted") == 0 and fatal == 0 and (planned or 0) > 0
    checks.append(check("exit code agrees with the results", (exit_code == 0) == green,
                        f"exit {exit_code}, failed {hb.get('failed')}, interrupted {hb.get('interrupted')}, "
                        f"errors outside tests {fatal}"))
    checks.append(check("not interrupted", not interrupted))
    return checks


def pytest_checks(human: Optional[Dict[str, Any]], junit: Optional[Dict[str, Any]], exit_code: Optional[int],
                  interrupted: bool, partial: bool) -> List[Dict[str, Any]]:
    """Every post-check of the backend suite, from pytest's final line (parsed), the analysis of the
    JUnit file and the exit code. Like playwright_checks, `verify` makes these again."""
    counts = human["counts"] if human else {name: 0 for name in PYTEST_COUNTS}
    checks = [check("pytest summary line present", human is not None)]
    checks.append(check("JUnit report present and parseable", junit is not None))
    if junit is not None:
        checks += pytest_junit_checks(junit, counts)
    if not partial:
        checks.append(check("nothing deselected", counts["deselected"] == 0, f"{counts['deselected']} deselected"))
    tests = counts["passed"] + counts["failed"] + counts["skipped"] + counts["xfailed"] + counts["xpassed"]
    # pytest exits 5 when it collected nothing, and every other check agrees with an empty report.
    checks.append(check("at least one test ran", tests > 0, f"{tests} test(s)"))
    green = counts["failed"] == 0 and counts["errors"] == 0 and tests > 0
    checks.append(check("exit code agrees with the results", (exit_code == 0) == green,
                        f"exit {exit_code}, failed {counts['failed']}, errors {counts['errors']}, tests {tests}"))
    checks.append(check("not interrupted", not interrupted))
    return checks


def analyse_playwright(project: str, raw: Path, ran: Dict[str, Any], partial: bool) -> Dict[str, Any]:
    console = read_text(raw / f"playwright-{project}.console.log") or ""
    human = parse_playwright_console(console)
    json_report = analyse_playwright_json(_read_json(raw / f"playwright-{project}.json"))
    junit_text = read_text(raw / f"playwright-{project}.junit.xml")
    try:
        junit = analyse_playwright_junit(junit_text) if junit_text else None
    except ET.ParseError:
        junit = None
    checks = playwright_checks(project, human, json_report, junit, ran["exit_code"], bool(ran.get("interrupted")))
    hb = human["buckets"] or {name: 0 for name in PLAYWRIGHT_BUCKETS}
    junit_public = {k: v for k, v in (junit or {}).items()} if junit else None
    return {
        "planned": human["planned"],
        "buckets": hb,
        "human": {"planned": human["planned"], "workers": human["workers"], "buckets": human["buckets"],
                  "fatal_errors": human["fatal_errors"], "lines": human["lines"]},
        "json": {k: v for k, v in json_report.items() if k not in ("skipped_tests", "failures")},
        "junit": junit_public,
        "checks": checks,
        "skipped_tests": json_report.get("skipped_tests") or [],
        "failures": json_report.get("failures") or [],
    }


def analyse_backend(raw: Path, ran: Dict[str, Any], partial: bool) -> Dict[str, Any]:
    console = read_text(raw / "backend.console.log") or ""
    human = parse_pytest_console(console)
    junit_text = read_text(raw / "backend.junit.xml")
    try:
        junit = analyse_pytest_junit(junit_text) if junit_text else None
    except ET.ParseError:
        junit = None
    counts = human["counts"] if human else {name: 0 for name in PYTEST_COUNTS}
    checks = pytest_checks(human, junit, ran["exit_code"], bool(ran.get("interrupted")), partial)
    junit_public = {k: v for k, v in junit.items() if k not in ("skips", "failed_tests")} if junit else None
    if junit_public is not None:
        junit_public["skips"] = junit["skips"]
    return {
        "planned": None,
        "buckets": counts,
        "human": {"line": human["line"] if human else None, "seconds": human["seconds"] if human else None},
        "junit": junit_public,
        "checks": checks,
        "skipped_tests": [{"project": "backend", "location": s["location"], "title": s["test"],
                           "bucket": "skipped", "reason": s["reason"]} for s in (junit or {}).get("skips", [])],
        "failures": [{"project": "backend", "location": "", "title": f["test"], "bucket": f["kind"],
                      "error": f["message"]} for f in (junit or {}).get("failed_tests", [])],
    }


# ----------------------------------------------------------------------------- verdicts
def suite_verdict(suite: Dict[str, Any]) -> str:
    if suite.get("status") != "ran":
        return "NOT RUN"
    if not all(c.get("ok") for c in suite.get("checks") or []):
        return "NOT EVIDENCE"
    return "PASS" if suite.get("exit_code") == 0 else "FAIL"


def overall_verdict(summary: Dict[str, Any]) -> str:
    if (summary.get("watcher") or {}).get("anomalies"):
        return "CONTAMINATED"
    verdicts = [suite_verdict(s) for s in summary.get("suites") or []]
    incomplete = not verdicts or any(v in ("NOT EVIDENCE", "NOT RUN") for v in verdicts)
    if summary.get("partial") or summary.get("interrupted") or incomplete:
        return "NOT EVIDENCE"
    if "FAIL" in verdicts:
        return "FAIL"
    return "PASS"


VERDICT_EXIT = {"PASS": 0, "FAIL": 1, "NOT EVIDENCE": 2, "CONTAMINATED": 2}


# ----------------------------------------------------------------------------- scrubbing
class ScrubAbort(Exception):
    """Something in a file to be published that no rule may silently rewrite. Messages name the file,
    line and rule, never the value."""


JWT = re.compile(r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}")
#: A token already replaced, in plain text or in XML, is not replaced again.
REDACTED = r"(?!<redacted>|&lt;redacted&gt;)"
BEARER = re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?bearer\s+)" + REDACTED + r"[A-Za-z0-9._~+/=-]+")
URL_CREDENTIALS = re.compile(r"(?i)\b((?:postgres(?:ql)?(?:\+\w+)?|rediss?)://)([^:/@\s\"'<>]*):"
                             + REDACTED + r"([^@/\s\"'<>]+)@")
#: In XML a second query parameter follows "&amp;", not "&".
QUERY_SECRET = re.compile(r"(?i)((?:[?&]|&amp;)(?:key|secret|api_key|apikey|token|access_token)=)"
                          + REDACTED + r"[^&\s\"'<>#]+")
PYTEST_HOSTNAME = re.compile(r"(<testsuite\b[^>]*?\shostname=\")([^\"]*)(\")")
#: File names such as icon@2x.png look like addresses; those endings are not mail domains.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+([A-Za-z]{2,}))\b")
NOT_MAIL_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "js", "mjs", "ts", "tsx", "css", "json", "map", "html"}
ALLOWED_EMAIL_DOMAINS = ("example.com", "predictions-local.dev")
SCRUB_RULES = ("ansi", "repo-root", "home", "pytest-hostname", "bearer-header", "jwt", "url-credentials",
               "query-secret")


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def foreign_emails(text: str) -> List[Tuple[int, str]]:
    found = []
    for match in EMAIL.finditer(text):
        domain, tld = match.group(1).lower(), match.group(2).lower()
        if tld in NOT_MAIL_TLDS or domain in ALLOWED_EMAIL_DOMAINS:
            continue
        found.append((line_of(text, match.start()), domain))
    return found


class Scrubber:
    """Deterministic rewrites applied to every published file, each counted per file.

    Replacements are tokens such as <repo> and <jwt>. In XML they are written escaped, so the parsed
    text reads <repo> and the file stays well-formed.
    """

    def __init__(self, roots: Iterable[str], home: Optional[str]):
        variants = set()
        for root in roots:
            if root:
                variants.update({root.rstrip("/"), os.path.realpath(root).rstrip("/")})
        self.roots = sorted((v for v in variants if v and v != "/"), key=len, reverse=True)
        homes = {h.rstrip("/") for h in (home, os.path.realpath(home) if home else None) if h}
        self.homes = sorted(homes, key=len, reverse=True)
        self.counts: Dict[str, Dict[str, int]] = {}

    def scrub(self, text: str, target: str, xml: bool = False, pytest_junit: bool = False) -> str:
        counts = self.counts.setdefault(target, {})

        def token(name: str) -> str:
            return xml_escape(f"<{name}>") if xml else f"<{name}>"

        def count(rule: str, n: int) -> None:
            if n:
                counts[rule] = counts.get(rule, 0) + n

        text, n = ANSI.subn("", text)
        count("ansi", n)
        for root in self.roots:
            count("repo-root", text.count(root))
            text = text.replace(root, token("repo"))
        for home in self.homes:
            count("home", text.count(home))
            text = text.replace(home, "~")
        if pytest_junit:
            text, n = PYTEST_HOSTNAME.subn(lambda m: m.group(1) + token("redacted") + m.group(3), text)
            count("pytest-hostname", n)
        text, n = BEARER.subn(lambda m: m.group(1) + token("redacted"), text)
        count("bearer-header", n)
        text, n = JWT.subn(token("jwt"), text)
        count("jwt", n)
        text, n = URL_CREDENTIALS.subn(lambda m: f"{m.group(1)}{m.group(2)}:{token('redacted')}@", text)
        count("url-credentials", n)
        text, n = QUERY_SECRET.subn(lambda m: m.group(1) + token("redacted"), text)
        count("query-secret", n)
        if "/Users/" in text:
            raise ScrubAbort(f"{target}: line {line_of(text, text.index('/Users/'))}: an absolute /Users/ path "
                             "outside the repository and home directory survived the scrub")
        emails = foreign_emails(text)
        if emails:
            line, domain = emails[0]
            raise ScrubAbort(f"{target}: line {line}: an email address at {domain}, which is not one of "
                             f"{', '.join(ALLOWED_EMAIL_DOMAINS)}")
        return text

    def scrub_tree(self, value: Any, target: str) -> Any:
        """Scrub every string inside a JSON-like value."""
        if isinstance(value, str):
            return self.scrub(value, target)
        if isinstance(value, list):
            return [self.scrub_tree(item, target) for item in value]
        if isinstance(value, dict):
            return {key: self.scrub_tree(item, target) for key, item in value.items()}
        return value


# ----------------------------------------------------------------------------- deny-list
#: Names whose values must never appear in a published file, besides every *_KEY, *_SECRET,
#: *_PASSWORD and *_TOKEN.
DENY_NAMES = ("SECRET_KEY", "POSTGRES_PASSWORD", "SMTP_USER", "SMTP_PASSWORD", "FIRST_SUPERUSER_EMAIL",
              "FIRST_SUPERUSER_PASSWORD", "EMAILS_FROM_EMAIL", "E2E_QA_PASSWORD", "E2E_QA_EMAIL")
DENY_SUFFIXES = ("_KEY", "_SECRET", "_PASSWORD", "_TOKEN")
#: A shorter value would match ordinary words and numbers and stop every publish. Such names are
#: listed in summary.json as not scanned, so the gap is visible.
MIN_DENY_LENGTH = 6
ENV_FILES = ("backend/.env", "frontend/.env", ".env", "docker/.env", "backend/.env.local", "frontend/.env.local")


def parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name[7:].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, 1)[0].strip()
        values[name] = value
    return values


def wanted_in_deny_list(name: str) -> bool:
    return name in DENY_NAMES or name.endswith(DENY_SUFFIXES)


def load_deny_list(env_paths: Iterable[Tuple[str, Path]], environ: Dict[str, str],
                   extra: Dict[str, Optional[str]]) -> Tuple[Dict[str, str], List[str]]:
    """{label: value} to scan for, and the labels too short to scan. Values stay in memory only."""
    deny: Dict[str, str] = {}
    too_short: List[str] = []

    def add(label: str, value: Optional[str]) -> None:
        if not value:
            return
        if len(value) < MIN_DENY_LENGTH:
            too_short.append(label)
        else:
            deny[label] = value

    for display, path in env_paths:
        for name, value in parse_env_file(path).items():
            if wanted_in_deny_list(name):
                add(f"{name} ({display})", value)
    for name in ("E2E_QA_PASSWORD", "E2E_QA_EMAIL"):
        add(f"{name} (environment)", environ.get(name))
    for label, value in extra.items():
        add(label, value)
    return deny, sorted(set(too_short))


def committed_qa_password() -> Optional[str]:
    """The QA account's committed fallback password. It is public already, but if it ever shows up in
    a report then step values or traces have leaked into it."""
    text = read_text(QA_ACCOUNT) or ""
    match = re.search(r"password:\s*process\.env\.E2E_QA_PASSWORD\s*\|\|\s*'([^']+)'", text)
    return match.group(1) if match else None


def default_deny_list() -> Tuple[Dict[str, str], List[str]]:
    paths = []
    checkouts = [REPO]
    main = git_common_dir(REPO)
    if main and main.name == ".git" and main.parent != REPO:
        checkouts.append(main.parent)   # .env files live in the main checkout, not in worktrees
    for checkout in checkouts:
        for relative in ENV_FILES:
            if (checkout / relative).exists():
                paths.append((relative if checkout == REPO else f"main checkout {relative}", checkout / relative))
    return load_deny_list(paths, dict(os.environ), {
        "git user.email": git_out(["config", "user.email"]),
        "hostname": platform.node(),
        "E2E_QA_PASSWORD (committed fallback)": committed_qa_password(),
    })


def value_forms(value: str) -> List[str]:
    forms = {value, xml_escape(value, {'"': "&quot;", "'": "&apos;"}), urllib.parse.quote(value, safe=""),
             json.dumps(value)[1:-1]}
    return sorted(f for f in forms if f)


def leak_scan(text: str, name: str, deny: Dict[str, str]) -> List[str]:
    """A read-only last look at a file about to be written. Findings name the file, line and rule,
    or the variable whose value appeared, and never the value."""
    findings = []
    if "/Users/" in text:
        findings.append(f"{name}: line {line_of(text, text.index('/Users/'))}: an absolute /Users/ path")
    for label, pattern in (("a JWT", JWT), ("a bearer token", BEARER),
                           ("credentials in a database URL", URL_CREDENTIALS),
                           ("a secret query parameter", QUERY_SECRET)):
        match = pattern.search(text)
        if match:
            findings.append(f"{name}: line {line_of(text, match.start())}: {label}")
    for line, domain in foreign_emails(text)[:1]:
        findings.append(f"{name}: line {line}: an email address at {domain}")
    for label, value in sorted(deny.items()):
        for form in value_forms(value):
            index = text.find(form)
            if index >= 0:
                findings.append(f"{name}: line {line_of(text, index)}: the value of {label}")
                break
    return findings


class PublishAbort(Exception):
    def __init__(self, findings: Sequence[str]):
        super().__init__("; ".join(findings))
        self.findings = list(findings)


# ----------------------------------------------------------------------------- summary.md
def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> List[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return lines


def _pick(item: Dict[str, Any], keys: Sequence[str]) -> List[Any]:
    return [item.get(key) for key in keys]


def render_summary_md(summary: Dict[str, Any]) -> str:
    """summary.md is rendered from summary.json alone, so `verify` can render it again and compare."""
    suites = summary.get("suites") or []
    out = _render_headline(summary, suites)
    out += _render_results(suites)
    out += _render_tests(suites)
    out += _render_environment(summary, suites)
    out += _render_integrity(summary)
    out += ["## How to verify", "", "```", summary.get("verify_command") or "", "```", ""]
    return "\n".join(out)


def _render_headline(summary: Dict[str, Any], suites: List[Dict[str, Any]]) -> List[str]:
    verdict = summary.get("verdict")
    dirty = (summary.get("repository") or {}).get("dirty")
    out = [f"# Test evidence {summary.get('run_id')}", ""]
    if summary.get("partial"):
        out += ["**PARTIAL - NOT EVIDENCE**: " + "; ".join(summary.get("partial_reasons") or []), ""]
    out += [f"**{verdict}**" + (" (dirty working tree, recorded below)" if dirty else ""), ""]
    out += [f"- {s.get('name')}: exit {_cell(s.get('exit_code'))}, {s.get('verdict')}" for s in suites] + [""]
    if verdict == "NOT EVIDENCE":
        failing = [f"{s.get('name')}: {c.get('name')} ({c.get('detail')})"
                   for s in suites for c in s.get("checks") or [] if not c.get("ok")]
        if failing:
            out += ["Failed checks:"] + [f"- {_cell(item)}" for item in failing] + [""]
    anomalies = (summary.get("watcher") or {}).get("anomalies") or []
    if anomalies:
        out.append("Contamination:")
        out += [f"- {a.get('first_seen')} during {a.get('during') or 'no suite'}: {a.get('kind')}, "
                f"{_cell(a.get('detail'))}" for a in anomalies]
        out.append("")
    out += ["## Run", "", f"- Run id: `{summary.get('run_id')}`",
            f"- Started {summary.get('started_at')}, finished {summary.get('finished_at')} (UTC)", ""]
    out += _table(["Suite", "Started (UTC)", "Finished (UTC)", "Duration (s)", "Exit code"],
                  [_pick(s, ("name", "started_at", "finished_at", "duration_seconds", "exit_code")) for s in suites])
    return out + [""]


def _render_results(suites: List[Dict[str, Any]]) -> List[str]:
    out = ["## Results", ""]
    rows = []
    for s in suites:
        b = s.get("buckets") or {}
        head = _pick(s, ("name", "exit_code", "verdict"))
        if s.get("kind") == "pytest":
            rows.append(head + ["-"] + _pick(b, ("passed", "failed")) + ["-", b.get("skipped"), "-", "-"]
                        + _pick(b, ("errors", "xfailed", "xpassed")))
        else:
            rows.append(head + [s.get("planned")]
                        + _pick(b, ("passed", "failed", "flaky", "skipped", "did_not_run", "interrupted"))
                        + ["-", "-", "-"])
    out += _table(["Suite", "Exit", "Verdict", "Planned", "Passed", "Failed", "Flaky", "Skipped", "Did not run",
                   "Interrupted", "Errors", "xfailed", "xpassed"], rows)
    out.append("")
    for s in suites:
        if s.get("status") != "ran":
            continue
        human = s.get("human") or {}
        quoted = human.get("lines") if s.get("kind") == "playwright" else [human.get("line")]
        quoted = [line for line in (quoted or []) if line]
        out += [f"### {s.get('name')}", "", "The reporter's own final lines, verbatim:", ""]
        out += ["```"] + (quoted or ["(none found)"]) + ["```", ""]
        j = s.get("junit") or {}
        if s.get("kind") == "pytest":
            out.append(f"JUnit: {j.get('testcases')} testcases; passed or xpassed {j.get('passed_or_xpassed')}, "
                       f"failed {j.get('failed')}, errors {j.get('errors')}, skipped {j.get('skipped')}, "
                       f"xfailed {j.get('xfailed')}.")
        else:
            js = s.get("json") or {}
            out.append(f"JUnit: tests {j.get('tests')}, passed {j.get('passed')}, failures {j.get('failures')}, "
                       f"errors {j.get('errors')}, skipped {j.get('skipped')}. "
                       f"JSON (kept locally): {js.get('total')} tests, buckets {js.get('buckets')}.")
        out.append("")
        out += _table(["Check", "Result", "Detail"],
                      [[c.get("name"), "ok" if c.get("ok") else "FAILED", c.get("detail")]
                       for c in s.get("checks") or []])
        out.append("")
    return out


def _render_tests(suites: List[Dict[str, Any]]) -> List[str]:
    out = ["## Skipped tests", ""]
    skipped = [t for s in suites for t in s.get("skipped_tests") or []]
    out += _table(["Project", "Location", "Test", "Bucket", "Reason"],
                  [_pick(t, ("project", "location", "title", "bucket", "reason")) for t in skipped]) \
        if skipped else ["None."]
    out += ["", "## Failures", ""]
    failures = [t for s in suites for t in s.get("failures") or []]
    out += _table(["Project", "Location", "Test", "Kind", "First line of the error"],
                  [_pick(t, ("project", "location", "title", "bucket", "error")) for t in failures]) \
        if failures else ["None."]
    return out + [""]


def _render_environment(summary: Dict[str, Any], suites: List[Dict[str, Any]]) -> List[str]:
    repo = summary.get("repository") or {}
    out = ["## Repository", "",
           f"- HEAD at start: `{repo.get('head_at_start')}`",
           f"- HEAD at end: `{repo.get('head_at_end')}`",
           f"- Branch: `{repo.get('branch')}`",
           f"- origin/main: `{repo.get('origin_main')}` as of the last fetch, {repo.get('last_fetch_at')}"]
    if repo.get("dirty"):
        out.append(f"- Working tree: DIRTY, allowed with --allow-dirty. {len(repo.get('dirty_paths') or [])} "
                   f"path(s); `git diff HEAD` sha256 `{repo.get('diff_sha256')}`; "
                   f"untracked files sha256 `{repo.get('untracked_sha256')}`")
        out += [f"  - `{p}`" for p in repo.get("dirty_paths") or []]
    else:
        out.append("- Working tree: clean")
    out += [f"- Working tree unchanged at the end: {'yes' if repo.get('unchanged_at_end') else 'NO'}", ""]

    out += ["## Servers under test", ""]
    for role, server in (summary.get("servers") or {}).items():
        out += [f"### {role}: {server.get('url')}", ""]
        if not server.get("listening"):
            out += ["Nothing was listening.", ""]
            continue
        checkout = server.get("checkout") or {}
        out.append(f"- PID {server.get('pid')}, started {server.get('started_at')}, "
                   f"working directory `{server.get('cwd')}`")
        out.append(f"- Command: `{server.get('command')}`")
        out.append(f"- Checkout `{checkout.get('toplevel')}` at `{checkout.get('head')}`, "
                   f"{len(checkout.get('dirty_paths') or [])} uncommitted path(s) under its directory")
        if "newest_source_change" in server:
            newer = {True: "yes", False: "NO", None: "unknown"}[server.get("process_newer_than_code")]
            out.append(f"- Newest app/**/*.py change {server.get('newest_source_change')}; "
                       f"process newer than the code: {newer}")
        if "health" in server:
            out.append(f"- /health: {server.get('health')}")
        out.append(f"- Same process at the end: {'yes' if server.get('unchanged_at_end') else 'NO'}")
        snapshot = server.get("provider_status")
        if snapshot:
            out += ["", f"Provider status at {snapshot.get('checked_at')} "
                        "(fields kept: status, times, error kind):", ""]
            out += _table(["Role", "Provider", "Integration", "Configured", "Last success", "Last error",
                           "Error kind", "Cooling down"],
                          [_pick(p, ("role", "name", "integration_status", "configured", "last_success_at",
                                     "last_error_at", "error_kind", "cooling_down"))
                           for p in snapshot.get("providers") or []])
            tasks = snapshot.get("scheduler_tasks") or {}
            if tasks:
                out += [""] + _table(["Scheduler task", "Last success", "Last error", "Error kind"],
                                     [[name] + _pick(t, ("last_success_at", "last_error_at", "error_kind"))
                                      for name, t in tasks.items()])
        out.append("")
    database = summary.get("test_database")
    if database:
        reads = "yes" if database.get("conftest_reads_env") else "no"
        out += ["## Backend test database", "",
                f"- {database.get('scheme')}://{database.get('host')}:{database.get('port')}/"
                f"{database.get('database')} (from {database.get('source')}); "
                f"conftest.py reads TEST_DATABASE_URL: {reads}",
                f"- PostgreSQL: {database.get('postgres')}; Redis: {database.get('redis')}", ""]
    out += ["## Tools", ""] + _table(["Tool", "Version"], list((summary.get("tools") or {}).items())) + [""]
    out += ["## Commands", ""]
    for s in suites:
        command = s.get("command") or {}
        names = ", ".join(command.get("env") or []) or "no extra variables"
        out += [f"{s.get('name')}, in `{command.get('cwd')}`, with {names} set:", "",
                "```", " ".join(command.get("argv") or []), "```", ""]
    return out


def _render_integrity(summary: Dict[str, Any]) -> List[str]:
    integrity = summary.get("integrity") or {}
    watcher = summary.get("watcher") or {}
    guard = integrity.get("guard_at_start") or []
    lock = integrity.get("lock") or {}
    deny = integrity.get("deny_list") or {}
    runner = summary.get("runner") or {}
    out = ["## Integrity", "",
           f"- Runner: `{runner.get('path')}`, SHA-256 `{runner.get('sha256')}`",
           f"- Concurrency guard at start: {'no other test run' if not guard else str(len(guard)) + ' found'}",
           f"- Lock acquired {lock.get('acquired_at')}; stale lock cleared: {lock.get('stale_lock_cleared') or 'no'}",
           f"- Watcher: {watcher.get('samples')} sample(s) every {watcher.get('interval_seconds')} s; "
           f"anomalies: {len(watcher.get('anomalies') or []) or 'none'}",
           f"- Deny-list: {len(deny.get('scanned') or [])} value(s) scanned, none found. Not scanned (shorter "
           f"than {deny.get('min_length')} characters): {', '.join(deny.get('too_short') or []) or 'none'}",
           f"- Published size: {integrity.get('published_bytes')} bytes"
           + (" (over the 2 MB warning line)" if integrity.get("size_warning") else ""),
           "", "Scrub substitutions per file:", ""]
    out += _table(["File"] + list(SCRUB_RULES),
                  [[name] + [counts.get(rule, 0) for rule in SCRUB_RULES]
                   for name, counts in sorted((integrity.get("scrub_counts") or {}).items())])
    out += ["", "Raw files kept locally, with their SHA-256 before scrubbing:", ""]
    out += _table(["Published", "Raw file", "Raw SHA-256"],
                  [[name] + _pick(r, ("raw", "sha256"))
                   for name, r in sorted((integrity.get("raw_files") or {}).items())])
    return out + [""]


# ----------------------------------------------------------------------------- publishing
def scrubber_for_repo() -> Scrubber:
    roots = [str(REPO)]
    listing = git_out(["worktree", "list", "--porcelain"]) or ""
    roots += [line[len("worktree "):] for line in listing.splitlines() if line.startswith("worktree ")]
    return Scrubber(roots, os.path.expanduser("~"))


def totals_of(junit: Dict[str, Any]) -> Dict[str, Any]:
    """A JUnit analysis without its free text, which scrubbing is allowed to change."""
    return {key: value for key, value in junit.items() if key not in ("skips", "failed_tests")}


def publish(summary: Dict[str, Any], raw: Path, out_dir: Path, scrubber: Scrubber,
            deny: Dict[str, str], too_short: Sequence[str]) -> Dict[str, Any]:
    """Scrub everything in memory, scan it, and write only if the scan is clean.

    The JUnit totals in summary.json are recomputed from the scrubbed XML that is committed, so that
    `verify` gets exactly the same figures from the same file. Scrubbing only rewrites text, so a
    total that changes means a rule damaged the XML, and the publish stops.
    """
    files: Dict[str, str] = {}
    raw_files: Dict[str, Dict[str, str]] = {}
    rescored: Dict[str, Dict[str, Any]] = {}
    inside = os.path.realpath(raw).startswith(os.path.realpath(REPO) + os.sep)
    raw_label = os.path.relpath(raw, REPO) if inside else scrubber.scrub(str(raw), "summary")
    for suite in summary["suites"]:
        if suite.get("status") != "ran":
            continue
        name, kind = suite["name"], suite["kind"]
        stem = "backend" if kind == "pytest" else f"playwright-{name}"
        junit_raw = raw / f"{stem}.junit.xml"
        if junit_raw.exists() and suite.get("junit") is not None:
            scrubbed = scrubber.scrub(junit_raw.read_text(encoding="utf-8", errors="replace"),
                                      f"{stem}.junit.xml", xml=True, pytest_junit=kind == "pytest")
            try:
                analysed = analyse_pytest_junit(scrubbed) if kind == "pytest" else analyse_playwright_junit(scrubbed)
            except ET.ParseError:
                raise PublishAbort([f"{stem}.junit.xml: no longer parses after scrubbing"])
            analysed.pop("failed_tests", None)
            if totals_of(analysed) != totals_of(suite["junit"]):
                raise PublishAbort([f"{stem}.junit.xml: scrubbing changed its totals"])
            rescored[name] = analysed
            files[f"{stem}.junit.xml"] = scrubbed
            raw_files[f"{stem}.junit.xml"] = {"raw": f"{raw_label}/{junit_raw.name}", "sha256": sha256_file(junit_raw)}
            suite["files"]["junit"] = f"{stem}.junit.xml"
        console_raw = raw / f"{stem}.console.log"
        if console_raw.exists():
            lines = BACKEND_TAIL_LINES if kind == "pytest" else PLAYWRIGHT_TAIL_LINES
            tail = console_tail(console_raw.read_text(encoding="utf-8", errors="replace"), kind, lines)
            files[f"{stem}.console-tail.txt"] = scrubber.scrub(tail, f"{stem}.console-tail.txt")
            raw_files[f"{stem}.console-tail.txt"] = {"raw": f"{raw_label}/{console_raw.name}",
                                                     "sha256": sha256_file(console_raw)}
            suite["files"]["console_tail"] = f"{stem}.console-tail.txt"
    public = scrubber.scrub_tree(summary, "summary")
    for suite in public["suites"]:
        if suite["name"] in rescored:
            suite["junit"] = rescored[suite["name"]]
    integrity = public["integrity"]
    integrity["raw_files"] = raw_files
    integrity["published_sha256"] = {name: sha256_bytes(text.encode("utf-8")) for name, text in sorted(files.items())}
    integrity["deny_list"] = {"scanned": sorted(deny), "too_short": list(too_short), "min_length": MIN_DENY_LENGTH}
    size = sum(len(text.encode("utf-8")) for text in files.values())
    integrity["published_bytes"] = size
    integrity["size_warning"] = size > SIZE_WARNING_BYTES
    integrity["scrub_counts"] = {name: dict(sorted(counts.items())) for name, counts in sorted(scrubber.counts.items())}
    files["summary.json"] = json.dumps(public, indent=2, ensure_ascii=False) + "\n"
    files["summary.md"] = render_summary_md(public)
    findings = [finding for name, text in sorted(files.items()) for finding in leak_scan(text, name, deny)]
    if findings:
        raise PublishAbort(findings)
    out_dir.mkdir(parents=True, exist_ok=False)
    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
    write_sha256sums(out_dir)
    return public


def published_files(directory: Path) -> List[str]:
    """The files a published directory holds besides SHA256SUMS. Dot files (.DS_Store) are not part of it."""
    return sorted(p.name for p in directory.iterdir()
                  if p.is_file() and p.name != "SHA256SUMS" and not p.name.startswith("."))


def write_sha256sums(directory: Path) -> None:
    """The format `shasum -a 256 -c SHA256SUMS` reads."""
    lines = "".join(f"{sha256_file(directory / name)}  {name}\n" for name in published_files(directory))
    (directory / "SHA256SUMS").write_text(lines, encoding="utf-8")


# ----------------------------------------------------------------------------- verify
#: What a summary.json can hold that this verify cannot read. A malformed field must fail a check,
#: never stop `verify` with a traceback.
MALFORMED = (KeyError, TypeError, ValueError, AttributeError, IndexError)


def verify_dir(directory: Path, emit=say) -> bool:
    """Every check a reviewer needs, from the published files alone.

    Nothing that can be worked out again is taken from summary.json on trust. The JUnit totals come
    from the committed XML and the reporters' own summaries from the committed console tails. Every
    post-check, the agreement between the exit code and the results included, is made again from
    those and the recorded exit code. Whether the run was partial follows from the suites it lists,
    the commands they ran and the run id. What only the run itself could see stays a record: the
    exit codes, the watcher's samples, the servers and the full JSON report.
    """
    problems: List[str] = []

    def expect(ok: bool, label: str, detail: str = "") -> None:
        label += f" ({detail})" if detail and not ok else ""
        emit(("ok    " if ok else "FAIL  ") + label)
        if not ok:
            problems.append(label)

    sums_path = directory / "SHA256SUMS"
    listed: Dict[str, str] = {}
    if not sums_path.exists():
        expect(False, "SHA256SUMS exists")
    else:
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            parts = line.split("  ", 1)
            if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
                listed[parts[1]] = parts[0]
            elif line.strip():
                expect(False, f"SHA256SUMS line is well-formed: {line[:80]!r}")
        for name, digest in sorted(listed.items()):
            path = directory / name
            expect(path.is_file() and sha256_file(path) == digest, f"{name} matches SHA256SUMS")
        present = set(published_files(directory))
        unlisted, missing = sorted(present - set(listed)), sorted(set(listed) - present)
        expect(not unlisted and not missing, "every file is listed in SHA256SUMS and every listed file exists"
               + (f" (unlisted: {unlisted}, missing: {missing})" if unlisted or missing else ""))
    summary = _read_json(directory / "summary.json")
    if not isinstance(summary, dict):
        expect(False, "summary.json is readable")
        return False
    expect(summary.get("format") == FORMAT, f"summary.json format is {FORMAT}")
    runner = summary.get("runner") or {}
    if isinstance(runner, dict) and runner.get("sha256") not in (None, sha256_file(Path(__file__).resolve())):
        emit("note  this is not the runner that made the run. If a check fails on an honest run, verify with that "
             "runner: git show <head_at_start>:scripts/test_evidence.py")
    try:
        suites = summary.get("suites") or []
        if not all(isinstance(suite, dict) for suite in suites):
            expect(False, "summary.json lists each suite as an object")
            suites = [suite for suite in suites if isinstance(suite, dict)]
        partial = _verify_run_shape(summary, suites, expect)
        for suite in suites:
            try:
                _verify_suite(directory, suite, partial, expect)
            except MALFORMED as exc:
                expect(False, f"{suite.get('name')}: summary.json has the shape this verify reads",
                       f"{type(exc).__name__}: {str(exc)[:80]}")
        expect(overall_verdict(summary) == summary.get("verdict"),
               f"overall verdict {summary.get('verdict')} follows from the suites and the watcher")
        reports = sorted(set(published_files(directory)) - {"summary.json", "summary.md"})
        named = sorted(str(f) for suite in suites for f in (suite.get("files") or {}).values() if f)
        expect(named == reports, "every published report belongs to a suite listed in summary.json",
               f"named {named}, published {reports}")
        published = (summary.get("integrity") or {}).get("published_sha256") or {}
        expect(sorted(published) == reports, "summary.json records the SHA-256 of every published report")
        for name, digest in sorted(published.items()):
            path = directory / name
            expect(path.is_file() and sha256_file(path) == digest, f"{name} matches summary.json")
    except MALFORMED as exc:
        expect(False, "summary.json has the shape this verify reads", f"{type(exc).__name__}: {str(exc)[:80]}")
    md = read_text(directory / "summary.md")
    try:
        rendered: Optional[str] = render_summary_md(summary)
    except MALFORMED:
        rendered = None
    expect(md is not None and md == rendered, "summary.md is exactly what summary.json renders to")
    emit("")
    emit("VERIFIED" if not problems else f"NOT VERIFIED: {len(problems)} check(s) failed")
    return not problems


def _verify_run_shape(summary: Dict[str, Any], suites: List[Dict[str, Any]], expect) -> bool:
    """Whether the run was partial, worked out again from the suites listed, the commands they ran
    and the run id, and checked against what summary.json says. Returns the worked-out answer."""
    names = [suite.get("name") for suite in suites]
    canonical = [name for name in ALL_SUITES if name in names]
    expect(names == canonical, "the suites are known, listed once each, in the order they run",
           ", ".join(str(name) for name in names))
    filtered = []
    stopped = []
    for suite in suites:
        name = suite.get("name")
        if name not in ALL_SUITES:
            continue
        expect(suite.get("kind") == suite_kind(name), f"{name}: kind {suite.get('kind')} is the kind of that suite")
        built, grep = recorded_filter(name, (suite.get("command") or {}).get("argv") or [])
        expect(built, f"{name}: the command is the one the runner builds for it")
        if grep is not None:
            filtered.append(name)
        if suite.get("status") != "ran" or suite.get("interrupted"):
            stopped.append(name)
    reasons = partial_reasons_for(canonical, bool(filtered))
    partial = bool(reasons) or names != canonical
    expect(summary.get("partial") is partial and (summary.get("partial_reasons") or []) == reasons,
           f"the run is {'partial' if partial else 'not partial'}, as recorded",
           "; ".join(reasons) or "every suite, unfiltered")
    expect(bool(PARTIAL_RUN_ID.search(str(summary.get("run_id") or ""))) == partial,
           "the run id ends in -partial exactly when the run is partial")
    # A suite is cut short or skipped only once a stop was requested, and that stop marks the run.
    expect(not stopped or summary.get("interrupted") is True,
           "a suite that was interrupted or never started means the run was interrupted", ", ".join(stopped))
    return partial


def _verify_suite(directory: Path, suite: Dict[str, Any], partial: bool, expect) -> None:
    name = suite.get("name")
    kind = suite_kind(name)
    status = suite.get("status")
    expect(status in ("ran", "not run"), f"{name}: status {status!r} is 'ran' or 'not run'")
    expect(suite_verdict(suite) == suite.get("verdict"),
           f"{name}: verdict {suite.get('verdict')} follows from its checks")
    if status != "ran":
        expect(not suite.get("files") and not suite.get("checks"),
               f"{name}: never started, so no reports and no checks")
        return
    stem = "backend" if kind == "pytest" else f"playwright-{name}"
    files = suite.get("files") or {}
    expect(files.get("junit") in (None, f"{stem}.junit.xml")
           and files.get("console_tail") == f"{stem}.console-tail.txt",
           f"{name}: its reports are {stem}.junit.xml and {stem}.console-tail.txt", f"{files}")

    junit: Optional[Dict[str, Any]] = None
    if files.get("junit"):
        text = read_text(directory / files["junit"])
        if text is None:
            expect(False, f"{name}: JUnit file present")
            return
        try:
            junit = analyse_pytest_junit(text) if kind == "pytest" else analyse_playwright_junit(text)
        except ET.ParseError:
            expect(False, f"{name}: {files['junit']} parses")
            return
        recorded = suite.get("junit") or {}
        for key, value in junit.items():
            if key == "failed_tests":
                continue
            shown = f"{len(value)} item(s)" if isinstance(value, list) and key == "skips" else repr(value)
            expect(recorded.get(key) == value, f"{name}: JUnit {key} recomputed = summary.json ({shown})")
    else:
        # The run had no readable JUnit for this suite; the recomputed checks below then say so.
        expect(suite.get("junit") is None, f"{name}: no JUnit file published, and summary.json records none")

    # The reporter's own summary: as summary.json quotes it, and as the published console tail shows it.
    tail = read_text(directory / files["console_tail"]) if files.get("console_tail") else None
    expect(tail is not None, f"{name}: console tail present")
    human = suite.get("human") or {}
    if kind == "pytest":
        line = human.get("line")
        parsed = parse_pytest_console(line) if isinstance(line, str) else None
        counts = parsed["counts"] if parsed else {count: 0 for count in PYTEST_COUNTS}
        expect(suite.get("buckets") == counts, f"{name}: the buckets are the counts in pytest's own summary line",
               f"line {line!r}")
        if tail is not None:
            from_tail = parse_pytest_console(tail)
            tail_line = from_tail["line"] if from_tail else None
            expect(tail_line == (parsed["line"] if parsed else None),
                   f"{name}: the published console tail holds the same summary", f"tail {tail_line!r}")
        made = pytest_checks(parsed, junit, suite.get("exit_code"), bool(suite.get("interrupted")), partial)
    else:
        buckets = human.get("buckets")
        quoted = parse_playwright_console("\n".join(str(item) for item in human.get("lines") or []))
        expect(quoted["buckets"] == buckets and quoted["fatal_errors"] == human.get("fatal_errors"),
               f"{name}: the summary lines quoted in summary.json give its buckets")
        expect(suite.get("buckets") == (buckets or {bucket: 0 for bucket in PLAYWRIGHT_BUCKETS})
               and suite.get("planned") == human.get("planned"),
               f"{name}: the buckets and the planned count are the reporter's own")
        if tail is not None:
            from_tail = parse_playwright_console(tail)
            same = (from_tail["buckets"] == buckets and from_tail["fatal_errors"] == human.get("fatal_errors")
                    and from_tail["planned"] in (None, human.get("planned")))
            expect(same, f"{name}: the published console tail holds the same summary",
                   f"tail {from_tail['buckets']}, planned {from_tail['planned']}")
        made = playwright_checks(name, human, suite.get("json") or {}, junit, suite.get("exit_code"),
                                 bool(suite.get("interrupted")))

    recorded_checks = [(c.get("name"), c.get("ok")) for c in suite.get("checks") or []]
    recorded_ok = dict(recorded_checks)
    for made_check in made:
        ok = made_check["ok"]
        expect(recorded_ok.get(made_check["name"]) is ok,
               f"{name}: '{made_check['name']}' recomputes as {'ok' if ok else 'FAILED'}, as recorded")
    made_names = [c["name"] for c in made]
    recorded_names = [check_name for check_name, _ in recorded_checks]
    expect(recorded_names == made_names, f"{name}: the recorded checks are the ones the run makes",
           f"missing {[n for n in made_names if n not in recorded_names]}, "
           f"extra {[n for n in recorded_names if n not in made_names]}")


# ----------------------------------------------------------------------------- preflight
class Options:
    def __init__(self, args: argparse.Namespace):
        requested = [s.strip() for s in (args.suites or ",".join(ALL_SUITES)).split(",") if s.strip()]
        unknown = [s for s in requested if s not in ALL_SUITES]
        if unknown:
            raise SystemExit(f"unknown suite(s): {', '.join(unknown)}; choose from {', '.join(ALL_SUITES)}")
        self.suites = [s for s in ALL_SUITES if s in requested]   # always the canonical order
        self.allow_dirty = args.allow_dirty
        self.base_url = args.base_url or os.environ.get("E2E_BASE_URL") or DEFAULT_BASE_URL
        self.api_url = args.api_url or os.environ.get("E2E_API_URL") or DEFAULT_API_URL
        self.grep = args.grep
        self.test_database_url = args.test_database_url
        self.dry_run = args.dry_run
        self.no_publish = args.no_publish
        self.raw_root = Path(args.raw_root).resolve() if args.raw_root else RAW_ROOT
        self.partial_reasons = partial_reasons_for(self.suites, bool(self.grep))


def preflight(opts: Options) -> Tuple[Dict[str, Any], List[str], Optional[str]]:
    """(the record, every reason to refuse, the test database URL). The URL is returned separately
    because it may hold a password and must not reach the record."""
    refusals: List[str] = []
    record: Dict[str, Any] = {"checked_at": iso(utc_now())}
    repo = repo_state()
    repo.update(origin_main())
    record["repository"] = repo
    if repo["dirty"] and not opts.allow_dirty:
        refusals.append(f"the working tree has {len(repo['dirty_paths'])} uncommitted path(s): "
                        + ", ".join(repo["dirty_paths"][:8]) + (" ..." if len(repo["dirty_paths"]) > 8 else "")
                        + ". Commit them, or rerun with --allow-dirty to record them.")
    try:
        runners = find_foreign_runners()
    except GuardError as exc:
        runners = []
        refusals.append(f"the concurrency guard could not run: {exc}")
    record["guard_at_start"] = runners
    refusals += guard_refusals(runners)

    playwright_selected = [s for s in opts.suites if s in PLAYWRIGHT_PROJECTS]
    servers: Dict[str, Dict[str, Any]] = {}
    for role, url, needed in (("frontend", opts.base_url, bool(playwright_selected)),
                              ("backend", opts.api_url, "live" in opts.suites)):
        host, port = url_port(url)
        server: Dict[str, Any] = {"url": url}
        if host not in LOCAL_HOSTS or port is None:
            server["listening"] = False
            if needed:
                refusals.append(f"{role} {url} is not on this machine, "
                                "so the process serving it cannot be identified")
            servers[role] = server
            continue
        server.update(listener(port))
        if role == "backend" and server.get("cwd"):
            changed = newest_source_change(Path(server["cwd"]) / "app")
            server["newest_source_change"] = iso(changed)
            server["process_newer_than_code"] = started_after(server.get("started_at"), changed)
        if role == "backend" and server.get("listening"):
            server["health"] = health_snapshot(url)
            _, status = http_get_json(url.rstrip("/") + "/api/v1/data-providers/status")
            server["provider_status"] = provider_snapshot(status)
        servers[role] = server
        if needed:
            refusals += server_refusals(role, server, repo, opts.allow_dirty)
    record["servers"] = servers

    database_url = None
    if "backend" in opts.suites:
        if not VENV_PYTHON.exists():
            refusals.append(f"the backend interpreter {VENV_PYTHON} does not exist")
        default, reads_env = conftest_database_default()
        source = ("--test-database-url" if opts.test_database_url else
                  "TEST_DATABASE_URL" if os.environ.get("TEST_DATABASE_URL") else "conftest.py default")
        database_url = opts.test_database_url or os.environ.get("TEST_DATABASE_URL") or default
        database = describe_database_url(database_url)
        database.update(source=source, conftest_reads_env=reads_env)
        refusals += database_refusals(database_url, default, reads_env)
        if database_url and VENV_PYTHON.exists():
            database.update(probe_backend_services(database_url))
            for service in ("postgres", "redis"):
                if database.get(service) != "ok":
                    refusals.append(f"{service} does not answer for the backend suite ({database.get(service)}); "
                                    "its database-backed modules would skip and the run would still exit green")
        record["test_database"] = database
    if playwright_selected and not PLAYWRIGHT_BIN.exists():
        refusals.append(f"{PLAYWRIGHT_BIN} does not exist; run npm ci in frontend/")
    record["tools"] = tool_versions()
    return record, refusals, database_url


def database_refusals(url: Optional[str], conftest_default: Optional[str], conftest_reads_env: bool) -> List[str]:
    """The backend suite's session fixture drops every table it created when it ends, so the
    database it is pointed at must be a test database, and conftest.py must really use it."""
    if not url:
        return ["no backend test database: set TEST_DATABASE_URL"]
    name = describe_database_url(url).get("database") or ""
    if "test" not in name.lower():
        return [f"the backend suite drops every table it creates when it ends; refusing database '{name}', "
                "whose name does not say it is a test database"]
    if not conftest_reads_env and conftest_default and url != conftest_default:
        return ["backend/tests/conftest.py ignores TEST_DATABASE_URL, so its session fixture would still create "
                f"and drop tables in '{describe_database_url(conftest_default).get('database')}'"]
    return []


def server_refusals(role: str, server: Dict[str, Any], repo: Dict[str, Any], allow_dirty: bool) -> List[str]:
    if not server.get("listening"):
        return [f"nothing is listening for the {role} at {server['url']}"]
    refusals = []
    checkout = server.get("checkout") or {}
    if not checkout.get("head"):
        return [f"the {role} process (pid {server.get('pid')}) runs outside a git checkout this script can read"]
    if checkout["head"] != repo.get("head"):
        refusals.append(f"the {role} at {server['url']} serves {checkout.get('toplevel')} "
                        f"at {checkout['head'][:12]}, "
                        f"not HEAD {(repo.get('head') or '?')[:12]} of the checkout under test")
    same_checkout = os.path.realpath(checkout.get("toplevel") or "") == os.path.realpath(str(REPO))
    if not same_checkout and checkout.get("dirty_paths") and not allow_dirty:
        refusals.append(f"the {role} serves another checkout with {len(checkout['dirty_paths'])} uncommitted path(s) "
                        "under its directory; rerun with --allow-dirty to record them")
    if role == "backend":
        if server.get("process_newer_than_code") is not True:
            refusals.append(f"the backend process (pid {server.get('pid')}, started {server.get('started_at')}) "
                            "did not start after the newest change to its app/**/*.py "
                            f"({server.get('newest_source_change')}); it has no --reload, so it may be running "
                            "older code. Restart it first.")
        status = (server.get("health") or {}).get("http_status")
        if status != 200:
            refusals.append(f"GET {server['url'].rstrip('/')}/health did not answer 200 ({status})")
    return refusals


def print_preflight(record: Dict[str, Any], refusals: Sequence[str], opts: Options) -> None:
    repo = record["repository"]
    say(f"repository  {repo.get('head')} on {repo.get('branch')}, "
        + (f"DIRTY ({len(repo['dirty_paths'])} path(s))" if repo.get("dirty") else "clean"))
    for role, server in record["servers"].items():
        if server.get("listening"):
            checkout = server.get("checkout") or {}
            say(f"{role:<11} {server['url']}: pid {server.get('pid')} started {server.get('started_at')}, "
                f"checkout at {(checkout.get('head') or '?')[:12]}"
                + (f", process newer than code: {server.get('process_newer_than_code')}" if role == "backend" else ""))
        else:
            say(f"{role:<11} {server['url']}: not listening")
    database = record.get("test_database")
    if database:
        say(f"test db     {database.get('host')}:{database.get('port')}/{database.get('database')} "
            f"({database.get('source')}): postgres {database.get('postgres')}, redis {database.get('redis')}")
    say(f"guard       {len(record['guard_at_start'])} other test run(s) found")
    partial = f"  [PARTIAL: {'; '.join(opts.partial_reasons)}]" if opts.partial_reasons else ""
    say(f"suites      {', '.join(opts.suites)}{partial}")
    for name, version in record["tools"].items():
        say(f"  {name:<26} {version}")
    for reason in refusals:
        say(f"REFUSE      {reason}")


# ----------------------------------------------------------------------------- commands
def unique_dir(parent: Path, name: str) -> Tuple[Path, str]:
    candidate, suffix = name, 1
    while (parent / candidate).exists() or (PUBLISH_ROOT / candidate).exists():
        suffix += 1
        candidate = f"{name}-{suffix}"
    return parent / candidate, candidate


def cmd_dry_run(opts: Options, record: Dict[str, Any], refusals: Sequence[str], database_url: Optional[str]) -> int:
    """Preflight in report-only form, then the planned counts, without running a test."""
    repo = record["repository"]
    run_id = make_run_id(utc_now(), repo.get("head"), repo.get("dirty"), bool(opts.partial_reasons))
    raw, run_id = unique_dir(opts.raw_root, run_id + "-dry-run")
    raw.mkdir(parents=True)
    plan: Dict[str, Any] = {"run_id": run_id, "would_refuse": list(refusals), "suites": {}}
    for suite in opts.suites:
        if suite == "backend":
            argv = [str(VENV_PYTHON), "-m", "pytest", "--collect-only", "-q", "-o", "addopts=",
                    "-p", "no:cacheprovider"]
            argv += ["-k", opts.grep] if opts.grep else []
            env = child_env({"TEST_DATABASE_URL": database_url} if database_url else {})
            code, out = run_text(argv, cwd=BACKEND, timeout=600, base_env=env)
            match = re.search(r"(\d+)(?:/(\d+))? tests? collected(?:.*?(\d+) errors?)?", out)
            planned = int(match.group(1)) if match else None
            errors = int(match.group(3)) if match and match.group(3) else 0
        else:
            # --reporter=list alone: in list mode the configured HTML reporter would otherwise
            # rewrite the shared e2e/.report.
            argv = [str(PLAYWRIGHT_BIN), "test", "--list", f"--project={suite}", "--reporter=list"]
            argv += ["--grep", opts.grep] if opts.grep else []
            code, out = run_text(argv, cwd=FRONTEND, timeout=600, base_env=child_env({"FORCE_COLOR": "0"}))
            match = re.search(r"^Total: (\d+) tests? in (\d+) files?", out, re.M)
            planned, errors = (int(match.group(1)) if match else None), 0
        (raw / f"{suite}.plan.txt").write_text(out, encoding="utf-8")
        plan["suites"][suite] = {"exit_code": code, "planned": planned, "collection_errors": errors}
        say(f"plan        {suite}: {planned if planned is not None else '?'} test(s), exit {code}"
            + (f", {errors} collection error(s)" if errors else ""))
    (raw / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    (raw / "preflight.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    say(f"dry run     nothing was run; plan and preflight kept in {raw}")
    outcome = f"a real run would be REFUSED ({len(refusals)} reason(s) above)" if refusals else "a real run would start"
    say(f"dry run     {outcome}")
    return 0 if not refusals else 3


def assemble_summary(*, run_id: str, partial_reasons: Sequence[str], interrupted: bool, started_at: datetime,
                     finished_at: datetime, record: Dict[str, Any], end: Dict[str, Any], allow_dirty: bool,
                     suites: List[Dict[str, Any]], watcher: Dict[str, Any], lock: Dict[str, Any]) -> Dict[str, Any]:
    """The unscrubbed summary of a finished run, verdicts included."""
    repo = record["repository"]
    summary: Dict[str, Any] = {
        "format": FORMAT,
        "run_id": run_id,
        "partial": bool(partial_reasons),
        "partial_reasons": list(partial_reasons),
        "interrupted": interrupted,
        "started_at": iso(started_at),
        "finished_at": iso(finished_at),
        "repository": {
            "head_at_start": repo.get("head"), "head_at_end": end.get("head"), "branch": repo.get("branch"),
            "origin_main": repo.get("origin_main"), "last_fetch_at": repo.get("last_fetch_at"),
            "dirty": repo.get("dirty"), "allow_dirty": allow_dirty, "dirty_paths": repo.get("dirty_paths"),
            "diff_sha256": repo.get("diff_sha256"), "untracked_sha256": repo.get("untracked_sha256"),
            "unchanged_at_end": tree_fingerprint(end) == tree_fingerprint(repo),
        },
        "servers": record["servers"],
        "test_database": record.get("test_database"),
        "tools": record["tools"],
        "suites": suites,
        "watcher": watcher,
        "integrity": {"guard_at_start": record["guard_at_start"], "lock": lock},
        # `verify` makes every check again with its own code, so a reviewer needs to know which
        # version of this file made the run when the checks have changed since.
        "runner": {"path": "scripts/test_evidence.py", "sha256": sha256_file(Path(__file__).resolve())},
        "verify_command": f"python3 scripts/test_evidence.py verify docs/evidence/test-reports/{run_id}",
    }
    for suite in suites:
        suite["verdict"] = suite_verdict(suite)
    summary["verdict"] = overall_verdict(summary)
    return summary


def cmd_run(opts: Options) -> int:
    record, refusals, database_url = preflight(opts)
    print_preflight(record, refusals, opts)
    if opts.dry_run:
        return cmd_dry_run(opts, record, refusals, database_url)
    if refusals:
        say(f"\nREFUSED: {len(refusals)} reason(s) above. Nothing was run.")
        return 3
    repo = record["repository"]
    started_at = utc_now()
    run_id = make_run_id(started_at, repo.get("head"), repo.get("dirty"), bool(opts.partial_reasons))
    raw, run_id = unique_dir(opts.raw_root, run_id)
    lock = RunLock(default_lock_path())
    try:
        lock.acquire(run_id)
    except Refused as exc:
        say(f"\nREFUSED: {exc}. Nothing was run.")
        return 3
    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        raw.mkdir(parents=True)
        (raw / "preflight.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        watched = {}
        if any(s in PLAYWRIGHT_PROJECTS for s in opts.suites):
            watched["frontend"] = record["servers"]["frontend"]
        if "live" in opts.suites:
            watched["backend"] = record["servers"]["backend"]
        watcher = Watcher(repo, watched)
        watcher.start()
        suites: List[Dict[str, Any]] = []
        for name in opts.suites:
            kind = "pytest" if name == "backend" else "playwright"
            entry: Dict[str, Any] = {"name": name, "kind": kind, "files": {}}
            if name == "backend":
                argv, cwd = backend_command(raw, opts.grep), BACKEND
                # Preflight refused a run without a test database URL, so this is never empty.
                extra = {"TEST_DATABASE_URL": database_url or "", "PYTHONUNBUFFERED": "1"}
                console = raw / "backend.console.log"
            else:
                argv, cwd = playwright_command(name, raw, opts.grep), FRONTEND
                extra = playwright_env(name, raw, opts.base_url, opts.api_url)
                console = raw / f"playwright-{name}.console.log"
            entry["command"] = {"cwd": str(cwd), "argv": argv, "env": sorted(extra)}
            if _STOP_REQUESTED.is_set():
                entry.update(status="not run", exit_code=None, checks=[], buckets={})
                suites.append(entry)
                continue
            say(f"\n===== {name} ({' '.join(argv[:3])} ...) =====")
            watcher.current_suite = name
            ran = run_child(argv, cwd, child_env(extra), console)
            watcher.current_suite = None
            entry.update(status="ran", **ran)
            if kind == "pytest":
                entry.update(analyse_backend(raw, ran, bool(opts.partial_reasons)))
            else:
                entry.update(analyse_playwright(name, raw, ran, bool(opts.partial_reasons)))
            say(f"===== {name}: exit {ran['exit_code']} =====")
            suites.append(entry)
        watcher.stop()
        watcher.join(timeout=60)
        watcher.sample()   # the end-of-run re-check of HEAD, the tree, the servers and other runners
        finished_at = utc_now()
        end = repo_state()
        for role, server in record["servers"].items():
            if server.get("listening"):
                server["unchanged_at_end"] = (listener_identity(server["port"])
                                              == (tuple(server.get("pids") or ()), server.get("started_at")))
        summary = assemble_summary(run_id=run_id, partial_reasons=opts.partial_reasons,
                                   interrupted=_STOP_REQUESTED.is_set(), started_at=started_at,
                                   finished_at=finished_at, record=record, end=end, allow_dirty=opts.allow_dirty,
                                   suites=suites, watcher=watcher.record(), lock=lock.record())
        (raw / "summary.local.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        say(f"\nverdict     {summary['verdict']}")
        for suite in suites:
            say(f"  {suite['name']:<18} exit {suite.get('exit_code')}  {suite['verdict']}")
        say(f"raw         {raw}")
        if opts.no_publish:
            say("publish     skipped (--no-publish)")
            return VERDICT_EXIT[summary["verdict"]]
        deny, too_short = default_deny_list()
        out_dir = PUBLISH_ROOT / run_id
        try:
            public = publish(summary, raw, out_dir, scrubber_for_repo(), deny, too_short)
        except (ScrubAbort, PublishAbort) as exc:
            say("\nPUBLISH ABORTED. Nothing was written to docs/; the raw run is kept locally.")
            for finding in getattr(exc, "findings", [str(exc)]):
                say(f"  {finding}")
            return 4
        if public["integrity"]["size_warning"]:
            say(f"warning     the published files are {public['integrity']['published_bytes']} bytes, over 2 MB")
        say(f"published   {out_dir}")
        for path in sorted(out_dir.iterdir()):
            say(f"  {path.relative_to(REPO)}")
        say(f"verify with {summary['verify_command']}")
        say("Nothing was staged or committed.")
        return VERDICT_EXIT[summary["verdict"]]
    finally:
        lock.release()


def cmd_verify(directory: str) -> int:
    path = Path(directory)
    if not path.is_dir():
        say(f"{directory} is not a directory")
        return 1
    return 0 if verify_dir(path) else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the suites and publish the scrubbed reports")
    run.add_argument("--suites", help=f"comma-separated subset of {','.join(ALL_SUITES)} "
                                      "(a subset is PARTIAL - NOT EVIDENCE)")
    run.add_argument("--allow-dirty", action="store_true", help="run on a dirty working tree and record it")
    run.add_argument("--base-url", help=f"frontend under test (default $E2E_BASE_URL or {DEFAULT_BASE_URL})")
    run.add_argument("--api-url", help=f"backend under test (default $E2E_API_URL or {DEFAULT_API_URL})")
    run.add_argument("--grep", help="filter tests (pytest -k / playwright --grep); "
                                    "marks the run PARTIAL - NOT EVIDENCE")
    run.add_argument("--test-database-url",
                     help="backend test database (default $TEST_DATABASE_URL, then conftest.py's)")
    run.add_argument("--dry-run", action="store_true", help="preflight and planned counts only; runs no test")
    run.add_argument("--no-publish", action="store_true", help="keep everything in .test-runs/ only")
    run.add_argument("--raw-root", help=argparse.SUPPRESS)
    verify = sub.add_parser("verify", help="check a published report directory")
    verify.add_argument("directory")
    args = parser.parse_args(argv)
    if args.command == "verify":
        return cmd_verify(args.directory)
    return cmd_run(Options(args))


if __name__ == "__main__":
    raise SystemExit(main())
