#!/usr/bin/env python
"""
How far has each fixture come along fixture -> forecast -> suggestion -> stored result ->
settlement? A read-only proof, on the data this installation really holds.

WHY THIS EXISTS
    Match data stopped arriving after 2026-10-02 14:53 UTC: Live Score answers HTTP 401 and
    neither fallback can serve the current season. Forecasts kept arriving, so a page showing
    forecasts looks alive while the half of the chain that needs match data - new fixtures, stored
    results, settlement - stands still. "It works again" has to be shown fixture by fixture once
    access returns, and shown exactly the way the outage is shown now, so the two runs can be laid
    side by side. This tool is that instrument; each run is kept under docs/evidence/journey-proof/.

WHAT IT NEVER DOES
    It writes nothing and sends no provider request. Each of those is enforced, not promised:

    * The database is read-only twice over. The connection is opened with
      `default_transaction_read_only=on` (what PGOPTIONS in the run line also sets, applied here
      rather than trusted to whoever runs it), the transaction is then declared READ ONLY and
      checked with SHOW before the first query, and it is rolled back in `finally`. Slips and legs
      are read from their tables, never through GET /api/v1/me/slips, which settles and commits.
    * Redis is read through `ReadOnlyRedis`, which refuses every command that is not a read.
    * HTTP goes through `GuardedClient`: GET only, only /health, /api/v1/data-providers/status,
      /api/v1/suggestions, /api/v1/matches/{uuid} and /api/v1/matches/{uuid}/markets, and never
      with `refresh=` in the query. Everything else is refused before it leaves: GET
      /api/v1/matches defaults to refresh=true (a provider request), /api/v1/matches/live polls the
      provider, /api/v1/me/* settles slips and commits.
    * The spend check reads every provider's counters before and after the run. Anything that moved
      which the scheduler's own ledger does not account for was spent by something other than the
      scheduler, and the run says so (and exits 2).

    The only file it ever writes is the one --out names, and it refuses to overwrite one.

WHAT IT REPORTS
    `match_data_access` is returned | partial | blocked, from three signals that must all hold:
    (a) the primary provider succeeded after --access-since, its last transmission was answered
    HTTP 200 and it is not cooling down; (b) the fixtures or results task's last pass succeeded
    after it, sent the primary at least one request and - for fixtures - had at least one day
    answered by a provider in that pass rather than by a cache; (c) a fixture sync or a result was
    stored after it. Five signals that look like recovery and are not are read, printed and
    ignored: the recovery task's success (it records one having sent nothing), a fixtures or
    results success that asked nobody (a results pass with nothing due, a fixtures pass served
    from the stale copy), a fallback's HTTP 200 (API-Football answers 200 with a plan error in the
    body), a fallback's `last_success_at`, and `matches.updated_at` (recovery bookkeeping bumps
    it).

    For every fixture, five stages, each {verdict, at, evidence}:
      fixture_stored     the row exists; proven_current when created or synced after --access-since
      forecast_attached  a forecast snapshot taken before kickoff
      suggestion         before kickoff: in GET /api/v1/suggestions or a single-fixture probe of it;
                         after kickoff: proven_earlier (an earlier run, --previous) or
                         selection_evidence (a slip leg read from a prematch snapshot)
      stored_result      a match_results row on a FINISHED fixture; otherwise why there is none
      settlement         every slip leg on the fixture beside a dry run of the settlement rule
                         (slip_settlement.settle_selection, which is pure; never settle_leg), and
                         the forecast-scoring row
    and the chain verdict: the first stage that does not pass.

    Slips settle only when their OWNER reads them: GET /api/v1/me/slips settles and commits, and
    the scheduler's settle task scores forecasts and never touches a slip. A leg whose dry run is
    final while the stored leg is still pending therefore reads `pending: owner read`, not `failed`.

    The output is written for a public repository: no email, user id, recorded reference, note,
    token, key or secret, every configured credential value is scrubbed from every string, and an
    owner appears only as `owner_is_qa`. A slip's name is kept only for the QA account.

RUN
    cd backend
    PGOPTIONS='-c default_transaction_read_only=on' ./venv311/bin/python scripts/prove_journey.py --recorded-slips
    PGOPTIONS='-c default_transaction_read_only=on' ./venv311/bin/python scripts/prove_journey.py \\
        --recorded-slips --window 2026-10-02T00:00:00Z 2026-10-07T02:00:00Z \\
        --previous ../docs/evidence/journey-proof/*.json --json --out ../docs/evidence/journey-proof/

    An --out that names a directory gets <UTC yyyy-mm-ddTHHMMZ>.json inside it. The selectors
    (--match, --slip, --window, --recorded-slips) combine: every fixture any of them names is
    proved once. docs/evidence/journey-proof/README.md says how to read a run and when to run the
    next one.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import create_engine, func, or_, text
from sqlalchemy.orm import Session, aliased, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.predictions import League, Match, MatchResult, MatchStatus, Team
from app.models.provider_data import ProviderForecastRecord, ProviderForecastResult, ProviderForecastSnapshot
from app.models.slips import (
    SLIP_STATUS_RECORDED, STATE_LOST, STATE_UNRESOLVED, STATE_VOID, STATE_WON, SelectionSlip, SelectionSlipLeg,
)
from app.models.users import User
from app.schemas.matches import result_expected_by
from app.services.forecast_service import COOLDOWN_KEY as FORECAST_COOLDOWN_KEY
from app.services.match_data_service import COOLDOWN_KEY as PROVIDER_COOLDOWN_KEY
from app.services.match_data_service import STATUS_KEY as PROVIDER_STATUS_KEY
from app.services.match_registry import RELISTED_KEY, RETRY_HORIZON, MatchRegistry, recovery_state_of
from app.services.providers.budget import (
    SCHEDULER_SENT_KEY, TRANSMISSION_OUTCOMES, _ledger_by_provider, budget_key, read_transmitted, transmitted_key,
)
from app.services.slip_settlement import settle_selection, slip_state
from app.services.sync_scheduler import STATE_KEY as TASK_STATE_KEY

#: Every key above is imported from the code that writes it rather than re-spelled here: a reader
#: looking under a key nobody writes reports "nothing recorded" for ever, which looks exactly like
#: an honest answer.

#: v2: signal (b) counts a task's success only on a pass that asked the primary and was answered
#: (`scheduler_pass_counts`); v1 counted any success. A v1 file's (b) is read by the older rule.
SCHEMA_VERSION = "journey-proof.v2"
TOOL = "backend/scripts/prove_journey.py"
DEFAULT_API = "http://127.0.0.1:8000"
#: The first whole second after Live Score's last success before it began refusing
#: (2026-10-02T14:53:28.028159Z, GET /api/v1/data-providers/status at 2026-10-07 01:06 UTC). A
#: match-data signal counts as "returned" only when it is later than this. Rounding DOWN to
#: 14:53:28 let that last success itself, and the results pass that finished 0.3 s after it, read
#: as later than the outage they preceded.
DEFAULT_ACCESS_SINCE = "2026-10-02T14:53:29Z"
#: The account the live browser suite records its journey slips with
#: (frontend/e2e/support/qa-account.ts). Compared inside the database; never read out, never printed.
QA_EMAIL_DEFAULT = "qa.expert@predictions-local.dev"

STAGES = ("fixture_stored", "forecast_attached", "suggestion", "stored_result", "settlement")
#: The one verdict that lets the chain past its stage without being a `proven*`. After kickoff the
#: suggestion service no longer considers a fixture, and a slip leg read from a prematch snapshot
#: shows markets -> slip in its place. The chain names every stage it stood in for, so it is never
#: mistaken for a suggestion.
SUBSTITUTES = ("selection_evidence",)
FINAL_STATES = (STATE_WON, STATE_LOST, STATE_VOID)
SCHEDULER_TASKS = ("fixtures", "results", "live", "recover", "forecasts", "settle")
DETAIL_CHARS = 300

#: How bad a settlement verdict is, worst first. A fixture with several legs reads as its worst.
_SETTLEMENT_ORDER = ("failed", "unresolved", "pending: owner read", "pending", "proven")


# ======================================================================================= time
_FRACTION = re.compile(r"\.(\d+)")


def _instant(value: Any) -> Optional[datetime]:
    """Any timestamp this tool reads, as an aware UTC datetime; None when absent or unreadable.

    Columns are naive UTC; JSON the backend wrote carries +00:00 or Z. Python 3.9 reads neither a
    "Z" nor a fraction that is not 3 or 6 digits, so both are normalised first: the same stored
    value must place the same way on both interpreters this repository runs. Unreadable is None,
    never a guess, and every caller treats None as "cannot be placed in time".
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    raw = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], raw, count=1)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _iso(value: Any) -> Optional[str]:
    instant = _instant(value)
    return instant.isoformat().replace("+00:00", "Z") if instant else None


def _after(value: Any, since: Optional[datetime]) -> bool:
    instant = _instant(value)
    return bool(instant and since and instant > since)


def _naive(instant: datetime) -> datetime:
    """For a filter on a naive UTC column."""
    return instant.astimezone(timezone.utc).replace(tzinfo=None)


def _clip(value: Any, limit: int = DETAIL_CHARS) -> Optional[str]:
    if value is None:
        return None
    rendered = str(value)
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


def _status(value: Any) -> Optional[str]:
    """A match status as its lower-case value, whether it came from the ORM or from JSON."""
    if value is None:
        return None
    return str(getattr(value, "value", value)).lower()


def _number(value: Any) -> Any:
    """Decimals as floats, so the output is plain JSON."""
    if value is None or isinstance(value, (int, float, bool)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _json(raw: Any) -> Optional[Dict[str, Any]]:
    """A MatchCache entry (JSON text) as a dict; None when absent or unreadable."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw)
    except (TypeError, ValueError):
        return None


# ===================================================================================== guards
class RefusedRequest(RuntimeError):
    """An HTTP request this tool will not send. Raised before anything leaves the machine."""


class RefusedWrite(RuntimeError):
    """A Redis command that is not a read."""


_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

#: The only paths a request may name, matched against the WHOLE path. Each was read for what it
#: does: the status, suggestions, detail and markets handlers read what is stored and make no
#: provider request. A match id has to be a UUID, which is what keeps /matches/live and
#: /matches/upcoming out of the detail pattern.
ALLOWED_PATHS = (
    re.compile(r"/health"),
    re.compile(r"/api/v1/data-providers/status"),
    re.compile(r"/api/v1/suggestions"),
    re.compile(rf"/api/v1/matches/{_UUID}"),
    re.compile(rf"/api/v1/matches/{_UUID}/markets"),
)

#: Why the nearest neighbours of the allowlist are refused, for the error a refusal raises.
_WHY_REFUSED = (
    ("/api/v1/me/", "it settles the owner's slips and commits"),
    ("/api/v1/matches/live", "it polls the provider (_sync_live)"),
    ("/api/v1/matches", "it defaults to refresh=true, which is a provider request"),
)


def check_request(method: str, url: httpx.URL) -> None:
    """Refuse anything but an allowlisted GET with no `refresh` in its query."""
    if method.upper() != "GET":
        raise RefusedRequest(f"{method.upper()} {url.path} refused: this tool sends GET only")
    path = url.path
    query = url.query.decode("utf-8", "replace") if isinstance(url.query, bytes) else str(url.query)
    if "refresh" in (name.lower() for name in url.params.keys()) or "refresh=" in query.lower():
        raise RefusedRequest(f"GET {path}?{query} refused: a refresh asks the provider")
    if not any(pattern.fullmatch(path) for pattern in ALLOWED_PATHS):
        why = next((reason for prefix, reason in _WHY_REFUSED if path.startswith(prefix)), "it is not on the allowlist")
        raise RefusedRequest(f"GET {path} refused: {why}")


#: Hosts a GuardedClient may be pointed at: this machine's loopback names.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _origin(url: httpx.URL) -> Tuple[str, str, int]:
    """(scheme, host, port) with the scheme's default port filled in, for an exact comparison."""
    port = url.port or (443 if url.scheme == "https" else 80)
    return (url.scheme, (url.host or "").lower(), port)


def _path_template(path: str) -> str:
    return re.sub(_UUID, "{id}", path)


class GuardedClient:
    """The only way this tool speaks HTTP: an allowlist checked twice.

    Once when a request is built, so a refused one never reaches the client, and again in the
    client's own request hook, which runs on the request actually about to be sent - so even a
    call made around `request()` straight on the underlying client cannot get past it. Redirects
    are not followed: a redirect is a new request this tool did not choose.
    """

    def __init__(self, base_url: str, transport: Optional[httpx.BaseTransport] = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._origin = _origin(httpx.URL(self.base_url))
        if self._origin[1] not in LOOPBACK_HOSTS:
            # The allowlist names this application's paths; on any other host the same paths could
            # belong to anything, a provider included. This tool reads the local backend only.
            raise RefusedRequest(f"{self.base_url} refused: this tool reads a backend on this machine only")
        self.sent: List[Dict[str, Any]] = []
        self.refused: List[str] = []
        self._client = httpx.Client(base_url=self.base_url, transport=transport, timeout=timeout,
                                    follow_redirects=False, event_hooks={"request": [self._last_check]})

    def _check(self, request: httpx.Request) -> None:
        if _origin(request.url) != self._origin:
            raise RefusedRequest(f"{request.method} {request.url} refused: not the backend this run was given")
        check_request(request.method, request.url)

    def _last_check(self, request: httpx.Request) -> None:
        self._check(request)

    def request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send one allowlisted request. Returns {ok, status, body, error}; refusals raise."""
        request = self._client.build_request(method, path, params=params)
        try:
            self._check(request)
        except RefusedRequest as exc:
            self.refused.append(str(exc))
            raise
        entry = {"method": request.method, "path": _path_template(request.url.path), "status": None}
        self.sent.append(entry)
        try:
            response = self._client.send(request)
        except httpx.HTTPError as exc:
            return {"ok": False, "status": None, "body": None, "error": f"{type(exc).__name__}: {_clip(exc, 200)}"}
        entry["status"] = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = None
        return {"ok": response.is_success, "status": response.status_code, "body": body,
                "error": None if response.is_success else _clip(response.text, 200)}

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.request("GET", path, params=params)

    def summary(self) -> Dict[str, Any]:
        counts = Counter(f"{e['method']} {e['path']} -> {e['status']}" for e in self.sent)
        return {"base": self.base_url, "sent": dict(sorted(counts.items())), "refused": list(self.refused)}

    def close(self) -> None:
        self._client.close()


class ReadOnlyRedis:
    """A Redis client that can only read. Any other command raises before it reaches the store."""

    READS = frozenset({"get", "mget", "hget", "hgetall", "hmget", "exists", "type", "ttl", "pttl", "scan_iter", "ping"})
    #: What `read_together` may queue inside its MULTI/EXEC.
    READS_IN_TRANSACTION = frozenset({"get", "hgetall"})

    def __init__(self, client: Any):
        self._client = client
        self.refused: List[str] = []

    def __getattr__(self, name: str) -> Any:
        if name in ReadOnlyRedis.READS:
            return getattr(self._client, name)
        self.refused.append(name)
        raise RefusedWrite(f"Redis {name!r} refused: this tool reads Redis and never writes it")

    def read_together(self, reads: Sequence[Tuple[str, str]]) -> List[Any]:
        """Several reads as one MULTI/EXEC, so they describe a single instant of the store.

        It is what lets the usage counter and the scheduler's ledger be subtracted from each other:
        read apart, a grant landing between the two reads shows on one side and not the other.
        Only reads are queued. A client without pipelines (the test fakes) is read in order.
        """
        for command, _ in reads:
            if command not in ReadOnlyRedis.READS_IN_TRANSACTION:
                self.refused.append(command)
                raise RefusedWrite(f"Redis {command!r} refused inside a read transaction")
        pipeline = getattr(self._client, "pipeline", None)
        if callable(pipeline):
            pipe = pipeline(transaction=True)
            for command, key in reads:
                getattr(pipe, command)(key)
            return list(pipe.execute())
        return [getattr(self._client, command)(key) for command, key in reads]


def read_only_engine(database_url: str):
    """An engine whose every connection starts read-only: the PGOPTIONS setting, applied here."""
    return create_engine(database_url, poolclass=NullPool, echo=False,
                         connect_args={"options": "-c default_transaction_read_only=on"})


@contextmanager
def read_only_session(factory: Callable[[], Session]) -> Iterator[Session]:
    """A session in a READ ONLY transaction, checked before the first query, rolled back after.

    The SHOW is the point: a declaration nobody checked is a promise. If the database does not
    report the transaction as read-only, nothing is read at all.
    """
    session = factory()
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        mode = session.execute(text("SHOW transaction_read_only")).scalar()
        if str(mode).lower() != "on":
            raise RuntimeError(f"the transaction reports transaction_read_only={mode!r}; refusing to read")
        yield session
    finally:
        session.rollback()
        session.close()


def _redis_client(db: int) -> Optional[Any]:
    """A decoded client on one Redis database, or None when unreachable (recorded, not fatal)."""
    try:
        import redis

        base = (settings.REDIS_URL or "redis://localhost:6379/0").rsplit("/", 1)[0]
        client = redis.from_url(f"{base}/{db}", decode_responses=True, socket_connect_timeout=5, socket_timeout=5)
        client.ping()
        return client
    except Exception:  # pragma: no cover - environment dependent
        return None


# ============================================================================ provider status
def _provider_view(name: str, status: Dict[str, Any], budget: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "last_success_at": status.get("last_success_at"),
        "last_error": _clip(status.get("last_error")),
        "last_error_at": status.get("last_error_at"),
        "cooling_down": _clip(status.get("cooling_down")),
        "transmitted_today": budget.get("transmitted_today"),
        "used_today": budget.get("used_today"),
    }


def _task_view(task: Dict[str, Any]) -> Dict[str, Any]:
    last = task.get("last_result") if isinstance(task.get("last_result"), dict) else {}
    days = last.get("days") if isinstance(last.get("days"), dict) else {}
    sent = task.get("last_requests_sent")
    return {
        "last_run_at": task.get("last_run_at"),
        "last_success_at": task.get("last_success_at"),
        "last_error_at": task.get("last_error_at"),
        "last_error": _clip(task.get("last_error")),
        "consecutive_failures": task.get("consecutive_failures"),
        "next_due_at": task.get("next_due_at"),
        "last_requests": last.get("requests"),
        # Per provider, what the task's last pass was granted (`SyncScheduler._record`), or None
        # when the backend did not record it. This, not `last_requests`, says who was asked: the
        # results task's `requests` counts the competitions it put to the chain, a cool-down skip
        # and a cache hit included (its 01:04 pass reads 2 having sent nothing).
        "last_requests_sent": ({str(k): _int(v) or 0 for k, v in sent.items()} if isinstance(sent, dict) else None),
        # The fixtures task's own day counts, and the days whose forward list a provider answered
        # in the pass itself: `days_answered` also counts a cache hit up to MATCH_CACHE_TTL_FIXTURES
        # old, which this pass did not ask for.
        "days_from_provider": sum(1 for day in days.values()
                                  if isinstance(day, dict) and day.get("forward_source") == "provider"),
        "days_answered": last.get("days_answered"),
        "days_from_stale_cache": last.get("days_from_stale_cache"),
        "days_unanswered": last.get("days_unanswered"),
    }


def status_view_from_api(status: Dict[str, Any]) -> Dict[str, Any]:
    """The parts of GET /api/v1/data-providers/status the verdicts read, in one shape."""
    forecasts = status.get("forecasts") or {}
    budget = forecasts.get("budget") or {}
    remaining = budget.get("effective_remaining_today")
    return {
        "source": "api",
        "checked_at": status.get("checked_at"),
        "primary": status.get("active_provider"),
        "chain": [_provider_view(p.get("name"), p, p.get("budget") or {}) for p in status.get("chain") or []],
        "forecasts": {
            "provider": forecasts.get("active_provider") or budget.get("provider"),
            "cooling_down": _clip(forecasts.get("cooling_down")),
            "remaining_today": remaining if remaining is not None else budget.get("remaining_today"),
            "used_today": budget.get("used_today"),
            "daily_limit": budget.get("daily_limit"),
            "transmitted_today": budget.get("transmitted_today"),
        },
        "tasks": {name: _task_view(task or {}) for name, task in
                  ((status.get("scheduler") or {}).get("tasks") or {}).items()},
        # What the backend itself tells readers about match data, where it says so. Kept to be
        # checked against the verdict, never to make it.
        "app_match_data": ({"state": status["match_data"].get("state")}
                           if isinstance(status.get("match_data"), dict) else None),
    }


def status_view_from_redis(store: Optional[ReadOnlyRedis], budget_store: Optional[ReadOnlyRedis], now: datetime,
                           primary: str, fallbacks: Sequence[str], forecast_provider: str) -> Dict[str, Any]:
    """The same view read straight from the keys the backend writes, for when the API is down.

    Thinner than the API's: the configured ceilings live in the backend's settings and the
    provider's own rate-limit window is not re-derived, so `remaining_today` is left unknown.
    """
    def cached(key: str) -> Dict[str, Any]:
        return (_json(store.get(key)) or {}) if store is not None else {}

    chain = []
    for name in [primary] + [f for f in fallbacks if f and f != primary]:
        status = dict(cached(PROVIDER_STATUS_KEY.format(name=name)))
        status["cooling_down"] = cached(PROVIDER_COOLDOWN_KEY.format(name=name)).get("reason")
        budget = {"transmitted_today": read_transmitted(name, budget_store, now) if budget_store is not None else None,
                  "used_today": _int(budget_store.get(budget_key(name, now))) if budget_store is not None else None}
        chain.append(_provider_view(name, status, budget))
    return {
        "source": "redis",
        "checked_at": _iso(now),
        "primary": primary,
        "chain": chain,
        "forecasts": {
            "provider": forecast_provider,
            "cooling_down": _clip(cached(FORECAST_COOLDOWN_KEY.format(provider=forecast_provider)).get("reason")),
            "remaining_today": None,
            "used_today": (_int(budget_store.get(budget_key(forecast_provider, now)))
                           if budget_store is not None else None),
            "daily_limit": None,
            "transmitted_today": (read_transmitted(forecast_provider, budget_store, now)
                                  if budget_store is not None else None),
        },
        "tasks": {name: _task_view(cached(TASK_STATE_KEY.format(name=name))) for name in SCHEDULER_TASKS},
    }


# ============================================================================ stored signals
def stored_signals(db: Session, since: datetime) -> Dict[str, Any]:
    """What the database itself says arrived last, and what first arrived after `since`.

    `last_synced_at` is written by the registry when a provider's answer is stored, and a result
    row only when a provider reported the fixture finished with both scores. `matches.updated_at`
    is read too, and only to be shown as the false signal it is: recovery bookkeeping rewrites the
    row's metadata and moves it with no provider having said anything.
    """
    synced = db.execute(text(
        "with synced as ("
        "  select (match_metadata->>'last_synced_at')::timestamptz as ts from predictions.matches"
        "  where match_metadata->>'last_synced_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T'"
        ") select max(ts), min(ts) filter (where ts > :since) from synced"), {"since": since}).one()
    newest_result, newest_result_update = db.query(func.max(MatchResult.created_at), func.max(MatchResult.updated_at)).one()
    first_result = (db.query(func.min(MatchResult.created_at))
                    .filter(MatchResult.created_at > _naive(since)).scalar())
    newest_match_created, newest_match_updated = db.query(func.max(Match.created_at), func.max(Match.updated_at)).one()
    return {
        "newest_last_synced_at": _iso(synced[0]),
        "first_last_synced_after_since": _iso(synced[1]),
        "newest_result_created_at": _iso(newest_result),
        "first_result_created_after_since": _iso(first_result),
        "newest_result_updated_at": _iso(newest_result_update),
        "newest_match_created_at": _iso(newest_match_created),
        "newest_match_updated_at": _iso(newest_match_updated),
    }


# ========================================================================= access detector
MATCH_DATA_TASKS = ("fixtures", "results")


def _sent_label(sent: Dict[str, int]) -> str:
    return ", ".join(f"{name} {count}" for name, count in sorted(sent.items()) if count) or "nothing"


def scheduler_pass_counts(name: str, task: Dict[str, Any], primary: str, since: datetime) -> Tuple[bool, Optional[str]]:
    """(does the fixtures or results task's last pass show match data reachable, and if not, why).

    `SyncScheduler._record` writes a success for every pass that reports ok, and two kinds of pass
    report ok having heard from nobody. A results pass with no competition due makes no call and
    records no error: on 2026-10-09, when the only stored fixtures kick off at 18:30-19:00 and a
    fixture is pending only 150 minutes after kickoff, every results pass until about 21:00 UTC is
    one. A fixtures pass counts a day served from the 24-hour stale copy as data (`got_data` is any
    source but the database), after the primary was asked and refused. So a success counts only
    when that pass asked the primary - `last_requests_sent`, what each provider was granted - and,
    for fixtures, a provider answered at least one day's forward list in the pass itself.

    For results that is enough: the pass succeeds only with no error recorded, and a request to
    the primary that went out and got no answer records one, so a success that asked the primary
    was answered by it. For fixtures it is not: the pass succeeds on any day's data, so the answer
    may be a fallback's after the primary refused. Signal (a) says whether the primary itself
    answers, and `returned` needs both.
    """
    if not _after(task.get("last_success_at"), since):
        return False, f"no success after {_iso(since)}"
    failures = int(task.get("consecutive_failures") or 0)
    if failures:
        return False, f"{failures} failed pass(es) since its last success"
    # From here the last pass IS the successful one (`_record` zeroes the streak on a success and
    # raises it on every failure), so what it sent and answered describe that success.
    sent = task.get("last_requests_sent")
    if sent is None:
        return False, (f"its last pass did not record what it sent, so it cannot be shown to have asked {primary}: "
                       "a pass that sent nothing records a success all the same")
    if (sent.get(primary) or 0) < 1:
        return False, (f"its last successful pass sent {primary} no request (sent: {_sent_label(sent)}); a pass with "
                       "nothing due, or answered from a cache or by a fallback, records a success all the same")
    if name == "fixtures" and not task.get("days_from_provider"):
        # With no day from a provider, every day `days_answered` counts was a cache hit.
        return False, (f"no day of its last successful pass was answered by a provider in the pass "
                       f"({task.get('days_answered') or 0} from the cache, "
                       f"{task.get('days_from_stale_cache') or 0} from the stale copy, "
                       f"{task.get('days_unanswered') or 0} unanswered); a day served from the stale copy "
                       "alone makes a fixtures pass succeed")
    return True, None


def _scheduler_evidence(name: str, task: Dict[str, Any], judged: Tuple[bool, Optional[str]]) -> Dict[str, Any]:
    evidence = {"last_success_at": task.get("last_success_at"),
                "consecutive_failures": task.get("consecutive_failures"),
                "last_error": task.get("last_error"),
                "last_requests_sent": task.get("last_requests_sent"),
                "counts": judged[0], "why_not": judged[1]}
    if name == "fixtures":
        evidence.update({key: task.get(key) for key in
                         ("days_from_provider", "days_answered", "days_from_stale_cache", "days_unanswered")})
    return evidence


def detect_match_data_access(view: Optional[Dict[str, Any]], stored: Dict[str, Any], since: datetime) -> Dict[str, Any]:
    """returned | partial | blocked, from three signals that each have to hold, and the five that
    look like recovery and are ignored.

    Why three: each one alone has been seen to lie. Live Score itself can answer HTTP 200 with
    `success: false` in the body, so (a) needs (b); a task can record a success on a pass that
    stored nothing, so (b) needs (c); and stored rows say nothing about whether the scheduler can
    still reach anyone, so (c) needs (a). And (b) is read only off a pass that asked the primary
    and was answered (`scheduler_pass_counts`): a success that asked nobody is no signal at all.
    """
    view = view or {}
    since_label = _iso(since)
    chain = view.get("chain") or []
    primary_name = view.get("primary") or (chain[0]["name"] if chain else "livescore")
    by_name = {p.get("name"): p for p in chain}
    primary = by_name.get(primary_name) or {}
    transmitted = primary.get("transmitted_today") or {}
    a_holds = bool(_after(primary.get("last_success_at"), since) and transmitted.get("last_status") == 200
                   and not primary.get("cooling_down"))
    tasks = view.get("tasks") or {}
    judged = {name: scheduler_pass_counts(name, tasks.get(name) or {}, primary_name, since)
              for name in MATCH_DATA_TASKS}
    tasks_ok = [name for name in MATCH_DATA_TASKS if judged[name][0]]
    c_holds = (_after(stored.get("newest_last_synced_at"), since)
               or _after(stored.get("newest_result_created_at"), since))
    signals = [
        {"signal": "primary_provider_answering", "holds": a_holds,
         "evidence": {"provider": primary_name, "last_success_at": primary.get("last_success_at"),
                      "transmitted_last_status": transmitted.get("last_status"),
                      "cooling_down": primary.get("cooling_down")}},
        {"signal": "scheduler_fixtures_or_results_succeeding", "holds": bool(tasks_ok),
         "evidence": {name: _scheduler_evidence(name, tasks.get(name) or {}, judged[name])
                      for name in MATCH_DATA_TASKS}},
        {"signal": "stored_match_data_advancing", "holds": bool(c_holds),
         "evidence": {"newest_last_synced_at": stored.get("newest_last_synced_at"),
                      "newest_result_created_at": stored.get("newest_result_created_at")}},
    ]
    held = [s for s in signals if s["holds"]]
    verdict = "returned" if len(held) == len(signals) else ("blocked" if not held else "partial")

    # The earliest stored row after the outage is an upper bound on when access came back: it
    # cannot have returned later than the first thing it delivered. An ask recorded on a fixture
    # after this instant was certainly put to a source that could answer.
    firsts = [_instant(stored.get(k)) for k in ("first_last_synced_after_since", "first_result_created_after_since")]
    firsts = [f for f in firsts if f is not None]
    returned_by = min(firsts) if verdict == "returned" and firsts else None

    recover = tasks.get("recover") or {}
    ignored: List[Dict[str, Any]] = [
        {"signal": "scheduler.tasks.recover.last_success_at", "value": recover.get("last_success_at"),
         "last_requests": recover.get("last_requests"),
         "why_ignored": "the recovery task records a success whenever no call failed outright, whether or not "
                        "any provider answered - including passes that sent no request at all"},
        {"signal": "matches.updated_at", "value": stored.get("newest_match_updated_at"),
         "why_ignored": "recovery bookkeeping rewrites match_metadata.recovery and moves it; no provider spoke"},
    ]
    for name in MATCH_DATA_TASKS:
        task = tasks.get(name) or {}
        # Listed only while the task reads as succeeding - a success after `since` with no failure
        # behind it - and that success was rejected: the one that looks like recovery and is not.
        # A success followed by failures does not look like recovery to anyone.
        if (not judged[name][0] and _after(task.get("last_success_at"), since)
                and not int(task.get("consecutive_failures") or 0)):
            ignored.append({"signal": f"scheduler.tasks.{name}.last_success_at", "value": task.get("last_success_at"),
                            "last_requests_sent": task.get("last_requests_sent"),
                            "why_ignored": judged[name][1]})
    for fallback in chain:
        if fallback.get("name") == primary_name:
            continue
        status = (fallback.get("transmitted_today") or {}).get("last_status")
        ignored.append({
            "signal": f"{fallback.get('name')}: last transmission status and last_success_at",
            "value": {"transmitted_last_status": status, "last_success_at": fallback.get("last_success_at")},
            "last_error": fallback.get("last_error"),
            "why_ignored": ("a fallback's HTTP 200 can carry a plan error in its body (API-Football: free plans "
                            "cannot read the current season), and its last_success_at has moved with no "
                            "fixture synced"),
        })
    return {
        "verdict": verdict,
        "access_since": since_label,
        "source": view.get("source"),
        "checked_at": view.get("checked_at"),
        "signals": signals,
        "missing": [s["signal"] for s in signals if not s["holds"]],
        "returned_no_later_than": _iso(returned_by),
        "providers": [{"name": p.get("name"), "role": "primary" if p.get("name") == primary_name else "fallback",
                       "last_success_at": p.get("last_success_at"), "last_error": p.get("last_error"),
                       "last_error_at": p.get("last_error_at"), "cooling_down": p.get("cooling_down"),
                       "transmitted_last_status": (p.get("transmitted_today") or {}).get("last_status")}
                      for p in chain],
        "stored": stored,
        "ignored_signals": ignored,
        # The backend's own reader-facing state (GET /api/v1/data-providers/status `match_data`),
        # when the running build publishes one: recorded beside the verdict, which it never decides,
        # so a banner that disagrees with the evidence shows up here.
        "app_reports": view.get("app_match_data"),
    }


# ============================================================================ stage helpers
def _stage(verdict: str, at: Any = None, **evidence: Any) -> Dict[str, Any]:
    return {"verdict": verdict, "at": _iso(at), "evidence": evidence}


def passes(verdict: Optional[str]) -> bool:
    return bool(verdict) and (verdict.startswith("proven") or verdict in SUBSTITUTES)


def _kickoff(match: Any) -> Optional[datetime]:
    return _instant(getattr(match, "match_date", None))


def _prematch(snapshot: Any, kickoff: Optional[datetime]) -> bool:
    """Captured before kickoff, as the snapshot recorded it; from its first retrieval only when it
    recorded nothing (rows written before the column existed)."""
    if snapshot.captured_before_kickoff is not None:
        return bool(snapshot.captured_before_kickoff)
    first = _instant(snapshot.first_fetched_at)
    return bool(first and kickoff and first < kickoff)


def _selection_id(market_id: str, outcome: str, line: Any) -> str:
    return f"{market_id}:{outcome}" + (f"@{float(line):g}" if line is not None else "")


def _snapshot_view(snapshot: Any) -> Dict[str, Any]:
    return {"id": str(snapshot.id), "provider": snapshot.provider,
            "first_fetched_at": _iso(snapshot.first_fetched_at), "last_fetched_at": _iso(snapshot.last_fetched_at),
            "captured_before_kickoff": snapshot.captured_before_kickoff,
            "kickoff_at_capture": _iso(getattr(snapshot, "kickoff_at_capture", None)),
            "model_run_at": _iso(snapshot.model_run_at)}


def _record_view(record: Any) -> Dict[str, Any]:
    return {"provider": record.provider, "fetched_at": _iso(record.fetched_at), "model_run_at": _iso(record.model_run_at),
            "match_confidence": record.match_confidence, "matched_by": record.matched_by}


def _result_view(result: Any) -> Dict[str, Any]:
    meta = getattr(result, "result_metadata", None) or {}
    return {
        "created_at": _iso(getattr(result, "created_at", None)), "updated_at": _iso(getattr(result, "updated_at", None)),
        "provider": meta.get("provider"),
        "score": [result.home_score, result.away_score],
        "regulation": [result.home_score_ft, result.away_score_ft],
        "half_time": [result.home_score_ht, result.away_score_ht],
        "extra_time": [getattr(result, "home_score_et", None), getattr(result, "away_score_et", None)],
        "penalties": [getattr(result, "home_score_pens", None), getattr(result, "away_score_pens", None)],
        "beyond_regulation": meta.get("beyond_regulation"),
        "period_marker": meta.get("period_marker"),
    }


#: The recovery fields a reader of the proof needs. `last_outcome_detail` is the sentence the sweep
#: wrote, clipped; everything else is a count, a time or a short label.
_RECOVERY_FIELDS = ("last_outcome", "last_outcome_at", "deferrals", "last_deferred_because", "next_ask_after",
                    "attempts", "first_attempt_at", "last_attempt_at", "attempts_quality", "attempts_at_correction",
                    "attempts_quality_as_of", "provider_errors", "gave_up_at", "stopped_by", "recovered_at",
                    "recovered_as")


def _recovery_view(recovery: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not recovery:
        return None
    view = {field: recovery.get(field) for field in _RECOVERY_FIELDS if recovery.get(field) is not None}
    if recovery.get("last_outcome_detail"):
        view["last_outcome_detail"] = _clip(recovery.get("last_outcome_detail"))
    return view


def attempt_counts_unreliable(recovery: Dict[str, Any], since: datetime) -> Optional[Dict[str, Any]]:
    """Why this fixture's attempt count cannot be taken at face value, or None when it can.

    Until 201442e, whenever Live Score was out of the chain a fallback that could not name a
    national-team competition returned an empty list for it unasked, and that was counted as an
    answered attempt (docs/known-limitations.md). Live Score has been out since `since`.

    A row `scripts/repair_not_answers.py` has sorted out carries its own account - `attempts_quality`
    "exact", or "upper_bound"/"unverified" with how many attempts the bound covers and as of when -
    and that mark decides: it was written by something that read the attempts, which a clock
    comparison did not. A row with no mark is unreliable when any attempt was counted after `since`,
    because that attempt may be one of the false ones. That errs towards flagging: once access
    returns, a genuine ask also trips it until the row is repaired, because the count it adds to may
    still hold the false ones.
    """
    quality = recovery.get("attempts_quality")
    if quality:
        if quality == "exact":
            return None
        reasons = [f"the stored record marks its own count as {quality!r}"]
    elif _after(recovery.get("last_attempt_at"), since):
        reasons = [f"an attempt was counted after {_iso(since)}, while every national-team results call a "
                   "fallback could not make was recorded as answered"]
    else:
        return None
    return {"attempts": recovery.get("attempts"), "first_attempt_at": recovery.get("first_attempt_at"),
            "last_attempt_at": recovery.get("last_attempt_at"), "attempts_quality": quality,
            "attempts_at_correction": recovery.get("attempts_at_correction"),
            "attempts_quality_as_of": recovery.get("attempts_quality_as_of"), "why": reasons}


# ============================================================================ the five stages
def classify_fixture_stored(match: Any, since: datetime) -> Dict[str, Any]:
    """Stage 1. `proven_current` only when the row was created or synced after the outage began:
    a row from before it proves the pipeline once worked, not that it works now."""
    if match is None:
        return _stage("not_found", None, detail="no fixture row with this id")
    meta = match.match_metadata or {}
    synced = meta.get("last_synced_at")
    current = _after(match.created_at, since) or _after(synced, since)
    return _stage("proven_current" if current else "proven", _instant(synced) or match.created_at,
                  match_id=str(match.id), external_api_source=match.external_api_source,
                  external_api_id=match.external_api_id, created_at=_iso(match.created_at),
                  last_synced_at=_iso(synced), provider=meta.get("provider"),
                  provider_status=meta.get("provider_status"), status=_status(match.status),
                  kickoff=_iso(match.match_date), relisted_as=meta.get(RELISTED_KEY))


def classify_forecast(match: Any, snapshots: Sequence[Any], records: Sequence[Any], now: datetime,
                      forecasts: Optional[Dict[str, Any]] = None, forecast_task: Optional[Dict[str, Any]] = None,
                      markets: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Stage 2: a forecast held from BEFORE kickoff. One retrieved afterwards is reference, not a
    prediction, and is never counted as this stage passing."""
    kickoff = _kickoff(match)
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    ordered = sorted(snapshots, key=lambda s: _instant(s.last_fetched_at) or oldest)
    prematch = [s for s in ordered if _prematch(s, kickoff)]
    newest = prematch[-1] if prematch else (ordered[-1] if ordered else None)
    evidence = {"snapshots": len(snapshots), "prematch_snapshots": len(prematch),
                "snapshot": _snapshot_view(newest) if newest is not None else None,
                "records": [_record_view(r) for r in records], "markets": markets}
    if prematch:
        first = min((_instant(s.first_fetched_at) for s in prematch if _instant(s.first_fetched_at)), default=None)
        return _stage("proven", first, **evidence)
    if snapshots:
        first = min((_instant(s.first_fetched_at) for s in snapshots if _instant(s.first_fetched_at)), default=None)
        return _stage("failed", first, detail="the only forecast held arrived after kickoff", **evidence)
    next_due = (forecast_task or {}).get("next_due_at")
    if kickoff is not None and kickoff > now:
        forecasts = forecasts or {}
        if forecasts.get("cooling_down") or forecasts.get("remaining_today") == 0:
            return _stage("blocked: forecast provider", None,
                          detail="no forecast yet, and the forecast provider is cooling down or today's allowance is spent",
                          cooling_down=forecasts.get("cooling_down"), remaining_today=forecasts.get("remaining_today"),
                          next_due_at=next_due, **evidence)
        return _stage("pending", None, detail="kickoff is ahead and no forecast is held yet", next_due_at=next_due, **evidence)
    return _stage("absent", None, detail="no forecast was stored for this fixture before it kicked off", **evidence)


def _combination_hit(body: Dict[str, Any], match_id: str) -> Optional[Dict[str, Any]]:
    for combination in body.get("combinations") or []:
        for leg in combination.get("legs") or []:
            if str((leg.get("match") or {}).get("id")) != match_id:
                continue
            selection = leg.get("selection") or {}
            why = leg.get("why") or {}
            return {"generated_at": body.get("generated_at"), "combination": combination.get("index"),
                    "rank": why.get("rank"), "selection_id": selection.get("selection_id"),
                    "probability": selection.get("probability"),
                    "snapshot_id": (why.get("forecast") or {}).get("snapshot_id")}
    return None


def _pool_view(body: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not body:
        return None
    pool = body.get("pool") or {}
    return {"generated_at": body.get("generated_at"), "fixtures_in_window": pool.get("fixtures_in_window"),
            "qualifying": pool.get("qualifying"),
            "excluded": {k: v for k, v in (pool.get("excluded") or {}).items() if v},
            "combinations": len(body.get("combinations") or []), "shortfall": _clip(body.get("shortfall"))}


def classify_suggestion(match: Any, now: datetime, default: Optional[Dict[str, Any]] = None,
                        probe: Optional[Dict[str, Any]] = None, previous_hits: Sequence[Dict[str, Any]] = (),
                        legs: Sequence[Any] = ()) -> Dict[str, Any]:
    """Stage 3. Suggestions consider only SCHEDULED fixtures that have not kicked off
    (suggestions.py clamps the window's start to now), so this stage can be OBSERVED only before
    kickoff, and after it only remembered: from an earlier run, or from a slip leg."""
    kickoff = _kickoff(match)
    match_id = str(match.id)
    if kickoff is not None and kickoff > now and _status(match.status) == "scheduled":
        answered = [(name, resp) for name, resp in (("default", default), ("probe", probe)) if resp and resp.get("ok")]
        calls = {name: (_pool_view(resp.get("body")) if resp and resp.get("ok") else
                        ({"status": resp.get("status"), "error": resp.get("error")} if resp else None))
                 for name, resp in (("default", default), ("probe", probe))}
        if not answered:
            return _stage("not_observed", None, detail="GET /api/v1/suggestions was not answered", calls=calls)
        for name, resp in answered:
            hit = _combination_hit(resp.get("body") or {}, match_id)
            if hit:
                return _stage("proven", hit["generated_at"], call=name, basis="combination", calls=calls, **hit)
        pool = _pool_view((probe or {}).get("body")) if probe and probe.get("ok") else None
        if pool and pool["fixtures_in_window"] == 1:
            if pool["qualifying"] == 1:
                # The service answers a window with too few qualifying fixtures with a combination
                # shorter than asked, so the probe normally shows the fixture in one (above). Should
                # it not, a qualifying fixture alone in the window is shown by the pool count.
                return _stage("proven", pool["generated_at"], call="probe", basis="pool",
                              detail="the only fixture in the probe window qualified for a suggestion",
                              generated_at=pool["generated_at"], calls=calls)
            if len(pool["excluded"]) == 1:
                reason = next(iter(pool["excluded"]))
                return _stage(f"excluded:{reason}", pool["generated_at"], generated_at=pool["generated_at"], calls=calls)
        return _stage("not_observed", None, calls=calls,
                      detail="not in any combination, and the probe window did not isolate this fixture")
    earlier = sorted((h for h in previous_hits if kickoff and _instant(h.get("generated_at"))
                      and _instant(h.get("generated_at")) < kickoff), key=lambda h: _instant(h["generated_at"]))
    if earlier:
        first = earlier[0]
        return _stage("proven_earlier", first["generated_at"], file=first.get("file"),
                      generated_at=first.get("generated_at"), observed=first.get("evidence"))
    selections = sorted((leg for leg in legs if leg.probability_source == "provider" and leg.snapshot_id
                         and kickoff and _instant(leg.created_at) and _instant(leg.created_at) < kickoff),
                        key=lambda leg: _instant(leg.created_at))
    if selections:
        return _stage("selection_evidence", selections[0].created_at,
                      detail=("a slip leg was read from a forecast snapshot before kickoff: this shows "
                              "markets -> slip, not the suggestion service"),
                      legs=[{"leg_id": str(leg.id), "selection_id": _selection_id(leg.market_id, leg.outcome, leg.line),
                             "snapshot_id": str(leg.snapshot_id), "created_at": _iso(leg.created_at)} for leg in selections])
    return _stage("not_observed", None,
                  detail=("suggestions only consider scheduled fixtures that have not kicked off, and no earlier "
                          "observation of this one was supplied (--previous)"))


def classify_stored_result(match: Any, result: Any, now: datetime, access: Dict[str, Any],
                           since: datetime) -> Dict[str, Any]:
    """Stage 4: a result row on a FINISHED fixture, or why there is none - in the order the
    reasons apply. A fixture with no result while match data cannot be fetched is `blocked`, never
    `failed`: nothing about the fixture failed, nobody could be asked."""
    kickoff = _kickoff(match)
    expected_by = _instant(result_expected_by(match)) if getattr(match, "match_date", None) else None
    status = _status(match.status)
    recovery = recovery_state_of(match)
    evidence: Dict[str, Any] = {"status": status, "result_expected_by": _iso(expected_by),
                                "result": _result_view(result) if result is not None else None,
                                "recovery": _recovery_view(recovery)}
    unreliable = attempt_counts_unreliable(recovery, since)
    if unreliable:
        evidence["attempt_counts_unreliable"] = unreliable
    if status in ("cancelled", "postponed"):
        return _stage("proven", (match.match_metadata or {}).get("last_synced_at"), basis="fixture_status",
                      detail=f"the fixture is {status}: no score is expected and every selection on it is void",
                      **evidence)
    if result is not None:
        if status == "finished":
            return _stage("proven_current" if _after(result.created_at, since) else "proven", result.created_at, **evidence)
        return _stage("unresolved: result stored on an unfinished fixture", result.created_at, **evidence)
    if status == "finished":
        return _stage("unresolved: finished without a stored result", None, **evidence)
    if kickoff is not None and now < kickoff:
        return _stage("pending: waiting for kickoff", None, **evidence)
    if expected_by is not None and now < expected_by:
        return _stage("pending: inside result window", None, **evidence)
    if status == "live":
        # A row that still reads LIVE long after its result was due is the absence of a report,
        # not a match in play.
        evidence["status_stale"] = True
    verdict = access.get("verdict")
    if verdict != "returned":
        label = ("blocked: no match-data source answering" if verdict == "blocked"
                 else "blocked: match-data access partial")
        return _stage(label, None, access=verdict, missing=access.get("missing"), **evidence)
    returned_by = _instant(access.get("returned_no_later_than"))
    last_ask = _instant(recovery.get("last_attempt_at"))
    stopped = _instant(recovery.get("gave_up_at"))
    past_horizon = kickoff is not None and now > kickoff + RETRY_HORIZON
    asked_since_return = bool(last_ask and returned_by and last_ask >= returned_by)
    if (stopped or past_horizon) and asked_since_return:
        return _stage("failed", stopped or last_ask,
                      detail="asked after access returned, and no result was stored by the end of the retry schedule",
                      **evidence)
    if stopped:
        return _stage("unresolved: stopped before access returned", stopped,
                      detail=("the retry budget stopped on asks recorded before access returned, which may include "
                              "asks never made; the stored record needs the documented repair"), **evidence)
    return _stage("pending: recovery queue", None, next_ask_after=recovery.get("next_ask_after"), **evidence)


def dry_run_leg(leg: Any, match: Any, result: Any) -> Dict[str, Any]:
    """The settlement rule applied to one leg, in memory. `settle_selection` is pure: it reads the
    status and the result and returns a verdict. `settle_leg` would write onto the leg."""
    line = float(leg.line) if leg.line is not None else None
    status = match.status if isinstance(match.status, MatchStatus) else MatchStatus(_status(match.status))
    return settle_selection(leg.market_id, leg.outcome, line, status, result)


def leg_verdict(stored_state: str, dry: Dict[str, Any]) -> str:
    state = dry.get("state")
    if stored_state in FINAL_STATES:
        # Final states are never reopened, so a final stored state that the rule no longer agrees
        # with is a real disagreement.
        return "proven" if stored_state == state else "failed"
    if state in FINAL_STATES:
        return "pending: owner read"
    if state == STATE_UNRESOLVED:
        return f"unresolved:{dry.get('basis') or 'unknown'}"
    return "pending"


def _worst(verdicts: Iterable[str]) -> str:
    def rank(verdict: str) -> int:
        for index, prefix in enumerate(_SETTLEMENT_ORDER):
            if verdict == prefix or verdict.startswith(prefix + ":"):
                return index
        return 0
    return min(verdicts, key=rank)


def classify_settlement(match: Any, result: Any, legs: Sequence[Any], scores: Sequence[Any],
                        has_prematch_forecast: bool) -> Dict[str, Any]:
    """Stage 5: what settled, against what the rule says now.

    Slip legs are judged first, because they are what a reader recorded. A fixture nobody put in a
    slip is judged by its forecast-scoring row instead, which the scheduler's settle task writes.
    """
    entries = []
    for leg in legs:
        dry = dry_run_leg(leg, match, result)
        entries.append({
            "leg_id": str(leg.id), "slip_id": str(leg.slip_id),
            "slip_status": getattr(leg, "slip_status", None), "owner_is_qa": getattr(leg, "owner_is_qa", None),
            "selection_id": _selection_id(leg.market_id, leg.outcome, leg.line),
            "stored_state": leg.state, "settled_at": _iso(leg.settled_at), "stored_settlement": leg.settlement,
            "dry_run": dry, "verdict": leg_verdict(leg.state, dry),
        })
    scoring = [{"snapshot_id": str(score.snapshot_id), "settled_at": _iso(score.settled_at),
                "outcome": _status(score.outcome), "is_correct": score.is_correct,
                "rules_version": score.rules_version, "void_reason": score.void_reason} for score in scores]
    evidence = {"legs": entries, "forecast_scoring": scoring}
    if entries:
        verdict = _worst(e["verdict"] for e in entries)
        settled = [_instant(leg.settled_at) for leg in legs if _instant(leg.settled_at)]
        return _stage(verdict, max(settled) if verdict == "proven" and settled else None, basis="slip_legs", **evidence)
    if scoring:
        return _stage("proven", max((_instant(s.settled_at) for s in scores), default=None),
                      basis="forecast_scoring", **evidence)
    if result is None and _status(match.status) not in ("cancelled", "postponed"):
        return _stage("pending", None, detail="nothing can settle before a result is stored", **evidence)
    if has_prematch_forecast:
        return _stage("pending: forecast scoring", None,
                      detail="a result and a prematch forecast are stored and no score row exists yet",
                      **evidence)
    return _stage("not_applicable", None, detail="no slip leg and no prematch forecast on this fixture: nothing to settle",
                  **evidence)


def chain_verdict(stages: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """The first stage that does not pass, naming every stage a substitute stood in for.

    `later` lists the stages after it that do not pass either. Without it a fixture that kicked
    off before anyone observed its suggestion reads only "suggestion: not_observed", and the
    stage that actually holds it up - no result can be fetched - drops out of sight.
    """
    substitutes = []
    for index, name in enumerate(STAGES):
        verdict = stages[name]["verdict"]
        if verdict in SUBSTITUTES:
            substitutes.append(f"{name}: {verdict}")
        if not passes(verdict):
            later = [f"{after}: {stages[after]['verdict']}" for after in STAGES[index + 1:]
                     if not passes(stages[after]["verdict"])]
            return {"verdict": verdict, "stage": name, "passed_with": substitutes, "later": later}
    return {"verdict": "proven", "stage": None, "passed_with": substitutes, "later": []}


def classify_slip(slip: Any, legs: Sequence[Any], matches: Dict[Any, Any], results: Dict[Any, Any],
                  owner_is_qa: bool, labels: Optional[Dict[Any, str]] = None) -> Dict[str, Any]:
    """A slip as stored, beside what its legs' dry runs make of it (`slip_state`)."""
    labels = labels or {}
    entries, dry_states = [], []
    for leg in legs:
        match = matches.get(leg.match_id)
        dry = dry_run_leg(leg, match, results.get(leg.match_id)) if match is not None else None
        if dry is not None:
            dry_states.append(dry["state"])
        entries.append({
            "leg_id": str(leg.id), "position": leg.position, "match_id": str(leg.match_id),
            "fixture": labels.get(leg.match_id), "selection_id": _selection_id(leg.market_id, leg.outcome, leg.line),
            "probability": _number(leg.probability), "probability_source": leg.probability_source,
            "snapshot_id": str(leg.snapshot_id) if leg.snapshot_id else None,
            "created_at": _iso(leg.created_at), "stored_state": leg.state, "settled_at": _iso(leg.settled_at),
            "dry_run_state": dry["state"] if dry else None,
            "verdict": leg_verdict(leg.state, dry) if dry else "unresolved:fixture_not_found",
        })
    dry_state = slip_state(dry_states) if len(dry_states) == len(legs) else STATE_UNRESOLVED
    stored = slip.state
    if stored in FINAL_STATES:
        verdict = "proven" if stored == dry_state else "failed"
    elif dry_state in FINAL_STATES:
        verdict = "pending: owner read"
    elif dry_state == STATE_UNRESOLVED:
        verdict = "unresolved"
    else:
        verdict = "pending"
    return {
        "id": str(slip.id),
        # A slip's name is the owner's own words; kept only for the QA account, whose names are
        # the suite's ("Journey <minute>").
        "name": slip.name if owner_is_qa else None,
        "owner_is_qa": bool(owner_is_qa), "status": slip.status, "state": stored,
        "settled_at": _iso(slip.settled_at), "created_at": _iso(slip.created_at),
        "recorded_at": _iso(slip.recorded_at), "price_recorded": slip.price is not None,
        "legs": entries, "dry_run_state": dry_state, "verdict": verdict,
    }


# ================================================================================== loading
def _owner_is_qa(qa_email: str):
    """Compared in SQL, so the address never reaches this process."""
    return (func.lower(User.email) == (qa_email or "").lower()).label("owner_is_qa")


def _slips(db: Session, slip_ids: Sequence[uuid.UUID], recorded: bool, qa_email: str) -> List[Tuple[Any, bool]]:
    conditions = []
    if slip_ids:
        conditions.append(SelectionSlip.id.in_(list(slip_ids)))
    if recorded:
        conditions.append(SelectionSlip.status == SLIP_STATUS_RECORDED)
    if not conditions:
        return []
    return (db.query(SelectionSlip, _owner_is_qa(qa_email)).join(User, User.id == SelectionSlip.user_id)
            .filter(or_(*conditions)).order_by(SelectionSlip.created_at.asc()).all())


def _legs_on(db: Session, match_ids: Sequence[Any], qa_email: str) -> Dict[Any, List[Any]]:
    """Every slip leg on these fixtures, whoever owns it, carrying only what the proof prints."""
    if not match_ids:
        return {}
    rows = (db.query(SelectionSlipLeg, SelectionSlip.status, _owner_is_qa(qa_email))
            .join(SelectionSlip, SelectionSlip.id == SelectionSlipLeg.slip_id)
            .join(User, User.id == SelectionSlip.user_id)
            .filter(SelectionSlipLeg.match_id.in_(list(match_ids)))
            .order_by(SelectionSlipLeg.created_at.asc()).all())
    grouped: Dict[Any, List[Any]] = {}
    for leg, slip_status, owner_is_qa in rows:
        grouped.setdefault(leg.match_id, []).append(SimpleNamespace(
            id=leg.id, slip_id=leg.slip_id, match_id=leg.match_id, market_id=leg.market_id, outcome=leg.outcome,
            line=leg.line, probability_source=leg.probability_source, snapshot_id=leg.snapshot_id,
            created_at=leg.created_at, state=leg.state, settled_at=leg.settled_at, settlement=leg.settlement,
            slip_status=slip_status, owner_is_qa=bool(owner_is_qa)))
    return grouped


def _grouped(rows: Iterable[Any]) -> Dict[Any, List[Any]]:
    grouped: Dict[Any, List[Any]] = {}
    for row in rows:
        grouped.setdefault(row.match_id, []).append(row)
    return grouped


def probe_params(match: Any) -> Dict[str, Any]:
    """GET /api/v1/suggestions narrowed to this fixture's competition and kickoff second, with every
    probability let through, so the pool says whether this one fixture qualifies and why not."""
    kickoff = _kickoff(match)
    return {"legs": 2, "min_probability": 0, "max_probability": 1, "competitions": str(match.league_id),
            "from": _iso(kickoff - timedelta(seconds=1)), "to": _iso(kickoff + timedelta(seconds=1)),
            "max_combinations": 10}


def _detail_view(response: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if response is None:
        return None
    if not response.get("ok"):
        return {"status": response.get("status"), "error": response.get("error")}
    body = response.get("body") or {}
    return {"status": response.get("status"), "match_status": body.get("status"),
            "result_expected_by": body.get("result_expected_by"), "forecast_state": body.get("forecast_state"),
            "last_synced_at": body.get("last_synced_at"), "score": body.get("score")}


def _markets_view(response: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if response is None:
        return None
    if not response.get("ok"):
        return {"status": response.get("status"), "error": response.get("error")}
    body = response.get("body") or {}
    forecast = body.get("forecast") or {}
    return {"status": response.get("status"), "forecast_state": forecast.get("state"),
            "snapshot_id": forecast.get("snapshot_id"), "captured_before_kickoff": forecast.get("captured_before_kickoff"),
            "retrieved_at": forecast.get("retrieved_at"), "reason": _clip(body.get("reason"))}


def prove_fixture(match: Any, *, label: str, competition: Any, now: datetime, since: datetime,
                  access: Dict[str, Any], view: Optional[Dict[str, Any]] = None, result: Any = None,
                  snapshots: Sequence[Any] = (), records: Sequence[Any] = (), scores: Sequence[Any] = (),
                  legs: Sequence[Any] = (), default: Optional[Dict[str, Any]] = None,
                  probe: Optional[Dict[str, Any]] = None, previous_hits: Sequence[Dict[str, Any]] = (),
                  detail: Optional[Dict[str, Any]] = None, markets: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One fixture through the five stages, from rows already read. Touches nothing."""
    view = view or {}
    tasks = view.get("tasks") or {}
    stages = {
        "fixture_stored": classify_fixture_stored(match, since),
        "forecast_attached": classify_forecast(match, snapshots, records, now, view.get("forecasts"),
                                               tasks.get("forecasts"), _markets_view(markets)),
        "suggestion": classify_suggestion(match, now, default, probe, previous_hits, legs),
        "stored_result": classify_stored_result(match, result, now, access, since),
    }
    stages["settlement"] = classify_settlement(match, result, legs, scores,
                                               stages["forecast_attached"]["verdict"] == "proven")
    chain = chain_verdict(stages)
    chain["current"] = stages["fixture_stored"]["verdict"] == "proven_current"
    flags = {}
    if stages["stored_result"]["evidence"].get("attempt_counts_unreliable"):
        flags["attempt_counts_unreliable"] = True
    if stages["stored_result"]["evidence"].get("status_stale"):
        flags["status_stale_live"] = True
    if (match.match_metadata or {}).get(RELISTED_KEY):
        flags["relisted"] = True
    return {
        "match_id": str(match.id), "fixture": label, "competition": getattr(competition, "name", None),
        "competition_id": str(getattr(competition, "id", "")) or None, "kickoff": _iso(match.match_date),
        "status": _status(match.status), "stages": stages, "chain": chain, "flags": flags,
        "api_detail": _detail_view(detail),
    }


def prove(db: Session, *, now: datetime, since: datetime, access: Dict[str, Any], view: Optional[Dict[str, Any]],
          api: Optional[GuardedClient], selection: Dict[str, Any], previous_hits: Dict[str, List[Dict[str, Any]]],
          qa_email: str) -> Dict[str, Any]:
    """Every selected fixture through the five stages, and every selected slip."""
    registry = MatchRegistry(db)
    match_ids: List[Any] = []
    not_found: List[Dict[str, str]] = []
    for raw in selection.get("matches") or []:
        resolved = registry.resolve_match_id(raw)
        if resolved is None:
            not_found.append({"input": str(raw), "kind": "match"})
        else:
            match_ids.append(resolved)
    slip_ids = []
    for raw in selection.get("slips") or []:
        try:
            slip_ids.append(uuid.UUID(str(raw)))
        except ValueError:
            not_found.append({"input": str(raw), "kind": "slip"})
    slip_rows = _slips(db, slip_ids, bool(selection.get("recorded_slips")), qa_email)
    found_slips = {slip.id for slip, _ in slip_rows}
    not_found.extend({"input": str(s), "kind": "slip"} for s in slip_ids if s not in found_slips)
    for slip, _ in slip_rows:
        match_ids.extend(leg.match_id for leg in slip.legs)
    window = selection.get("window")
    if window:
        match_ids.extend(row.id for row in db.query(Match.id)
                         .filter(Match.match_date >= _naive(window[0]), Match.match_date < _naive(window[1]))
                         .order_by(Match.match_date.asc(), Match.id.asc()).all())
    ids = list(dict.fromkeys(match_ids))

    home, away = aliased(Team), aliased(Team)
    rows = (db.query(Match, League, home, away)
            .join(League, League.id == Match.league_id)
            .join(home, home.id == Match.home_team_id)
            .join(away, away.id == Match.away_team_id)
            .filter(Match.id.in_(ids)).order_by(Match.match_date.asc(), Match.id.asc()).all()) if ids else []
    results = {r.match_id: r for r in db.query(MatchResult).filter(MatchResult.match_id.in_(ids)).all()} if ids else {}
    snapshots = _grouped(db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.match_id.in_(ids)).all()) if ids else {}
    records = _grouped(db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id.in_(ids)).all()) if ids else {}
    scores = _grouped(db.query(ProviderForecastResult).filter(ProviderForecastResult.match_id.in_(ids)).all()) if ids else {}
    legs = _legs_on(db, ids, qa_email)

    upcoming = [m for m, *_ in rows if (_kickoff(m) or now) > now and _status(m.status) == "scheduled"]
    default = api.get("/api/v1/suggestions") if api is not None and upcoming else None

    fixtures, labels, matches = [], {}, {}
    for match, league, home_team, away_team in rows:
        label = f"{home_team.name} v {away_team.name}"
        labels[match.id], matches[match.id] = label, match
        detail = markets = probe = None
        if api is not None:
            detail = api.get(f"/api/v1/matches/{match.id}")
            markets = api.get(f"/api/v1/matches/{match.id}/markets")
            if match in upcoming:
                probe = api.get("/api/v1/suggestions", params=probe_params(match))
        fixtures.append(prove_fixture(
            match, label=label, competition=league, now=now, since=since, access=access, view=view,
            result=results.get(match.id), snapshots=snapshots.get(match.id, []), records=records.get(match.id, []),
            scores=scores.get(match.id, []), legs=legs.get(match.id, []), default=default, probe=probe,
            previous_hits=previous_hits.get(str(match.id), ()), detail=detail, markets=markets))

    slips = [classify_slip(slip, list(slip.legs), matches, results, bool(owner_is_qa), labels)
             for slip, owner_is_qa in slip_rows]
    return {"fixtures": fixtures, "slips": slips, "not_found": not_found,
            "suggestions_default": _pool_view(default.get("body")) if default and default.get("ok") else
            (_detail_view(default) if default else None)}


def summarise(fixtures: Sequence[Dict[str, Any]], slips: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "fixtures": len(fixtures),
        "stages": {name: dict(sorted(Counter(f["stages"][name]["verdict"] for f in fixtures).items())) for name in STAGES},
        "chain": dict(sorted(Counter((f"{f['chain']['stage']}: {f['chain']['verdict']}" if f["chain"]["stage"]
                                      else "proven") for f in fixtures).items())),
        "current_chains_proven": sum(1 for f in fixtures if f["chain"]["current"] and not f["chain"]["stage"]),
        "attempt_counts_unreliable": sum(1 for f in fixtures if f["flags"].get("attempt_counts_unreliable")),
        "status_stale_live": sum(1 for f in fixtures if f["flags"].get("status_stale_live")),
        "slips": dict(sorted(Counter(s["verdict"] for s in slips).items())),
    }


# ============================================================================== spend check
def _transmitted_total(record: Optional[Dict[str, Any]]) -> Optional[int]:
    if record is None:
        return None
    return sum(_int(record.get(outcome)) or 0 for outcome in TRANSMISSION_OUTCOMES)


def spend_from_status(status: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """One reading per budgeted provider from the status payload, which reads each usage counter
    and the scheduler's ledger in one transaction (budget.py) - the exact method of
    frontend/e2e/support/provider-spend.ts."""
    blocks = [(p.get("name"), p.get("budget")) for p in status.get("chain") or []]
    forecast_budget = (status.get("forecasts") or {}).get("budget")
    blocks.append(((forecast_budget or {}).get("provider") or "forecasts", forecast_budget))
    reading = {}
    for name, budget in blocks:
        if not budget:
            continue
        reading[name] = {"used_today": budget.get("used_today"),
                         "scheduler_sent": (budget.get("scheduler_sent") or {}).get("total"),
                         "transmitted": _transmitted_total(budget.get("transmitted_today"))}
    return reading


def spend_from_redis(budget_store: ReadOnlyRedis, names: Sequence[str], now: datetime) -> Dict[str, Dict[str, Any]]:
    """The same reading straight from the counters, every key in one read-only MULTI/EXEC."""
    reads: List[Tuple[str, str]] = [("hgetall", SCHEDULER_SENT_KEY)]
    for name in names:
        reads += [("get", budget_key(name, now)), ("hgetall", transmitted_key(name, now))]
    values = budget_store.read_together(reads)
    ledger = _ledger_by_provider(values[0])
    reading = {}
    for index, name in enumerate(names):
        counted, transmitted = values[1 + 2 * index], values[2 + 2 * index] or {}
        reading[name] = {"used_today": _int(counted) or 0,
                         "scheduler_sent": sum(ledger.get(name, {}).values()),
                         "transmitted": sum(_int(transmitted.get(outcome)) or 0 for outcome in TRANSMISSION_OUTCOMES)}
    return reading


def compare_spend(before: Optional[Dict[str, Dict[str, Any]]], after: Optional[Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """Per provider, what moved `used_today` that the scheduler's ledger does not account for.

    `transmitted_in_run` is shown beside it and does not decide anything: a scheduler request
    granted before the first reading and answered after it shows there and is not a leak.
    """
    if before is None or after is None:
        return {"verdict": "unknown", "providers": {}, "problems": ["a reading could not be taken"]}
    providers, problems = {}, []
    for name in sorted(set(before) | set(after)):
        was, now = before.get(name), after.get(name)
        if not was or not now:
            problems.append(f"{name} is in only one of the two readings")
            continue
        if any(v is None for v in (was["used_today"], now["used_today"], was["scheduler_sent"], now["scheduler_sent"])):
            problems.append(f"{name}: the usage counter or the scheduler ledger could not be read")
            continue
        if now["used_today"] < was["used_today"]:
            problems.append(f"{name}: used_today went down; the UTC day turned over inside the run")
            continue
        scheduler = now["scheduler_sent"] - was["scheduler_sent"]
        transmitted = (now["transmitted"] - was["transmitted"]
                       if was.get("transmitted") is not None and now.get("transmitted") is not None else None)
        providers[name] = {"used_today": [was["used_today"], now["used_today"]], "scheduler_sent_in_run": scheduler,
                           "spent_besides_scheduler": (now["used_today"] - was["used_today"]) - scheduler,
                           "transmitted_in_run": transmitted}
    spent = [name for name, entry in providers.items() if entry["spent_besides_scheduler"] > 0]
    verdict = "failed" if spent else ("unknown" if problems or not providers else "passed")
    return {"verdict": verdict, "providers": providers, "problems": problems}


def _overall_spend(api_check: Dict[str, Any], redis_check: Dict[str, Any]) -> str:
    verdicts = [api_check["verdict"], redis_check["verdict"]]
    if "failed" in verdicts:
        return "failed"
    return "passed" if "passed" in verdicts else "unknown"


# ============================================================================ run metadata
def _command(args: Sequence[str], cwd: Optional[str] = None) -> Optional[str]:
    try:
        done = subprocess.run(list(args), capture_output=True, text=True, timeout=15, cwd=cwd,
                              env={**os.environ, "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.SubprocessError):
        return None
    # Trailing whitespace only: a porcelain status line starts with a meaningful space (" M path").
    return done.stdout.rstrip() if done.returncode == 0 else None


def repo_state(root: str) -> Dict[str, Any]:
    """HEAD, when it got here, and which application files differ from it. Read-only git:
    `--no-optional-locks` keeps `status` from refreshing the index other sessions share."""
    head = _command(["git", "rev-parse", "HEAD"], cwd=root)
    moved = _command(["git", "log", "-g", "-1", "--date=iso-strict", "--format=%gd"], cwd=root) or ""
    found = re.search(r"\{(.+)\}", moved)
    dirty = _command(["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=all", "--",
                      "backend/app"], cwd=root)
    # "XY path", or "XY old -> new" for a rename: the path that exists now is the last one.
    changed = None if dirty is None else sorted(line[3:].split(" -> ")[-1].strip('"')
                                                 for line in dirty.splitlines() if line.strip())
    return {"head": head, "committed_at": _iso(_command(["git", "show", "-s", "--format=%cI", "HEAD"], cwd=root)),
            "head_moved_at": _iso(found.group(1)) if found else None, "app_tree_changes": changed}


def backend_process(port: int, root: str) -> Dict[str, Any]:
    """The process listening on the API port, and when it started: the backend runs without
    --reload, so what it serves is the tree as it was at that moment, not as it is now."""
    pids = (_command(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"]) or "").split()
    if not pids:
        return {"found": False}
    pid = pids[0]
    started_raw = _command(["ps", "-o", "lstart=", "-p", pid]) or ""
    try:
        started = datetime.strptime(" ".join(started_raw.split()), "%a %b %d %H:%M:%S %Y").astimezone(timezone.utc)
    except ValueError:
        started = None
    command = (_command(["ps", "-o", "command=", "-p", pid]) or "").split()
    # The command line is printed from the uvicorn executable on: what precedes it is a path on this
    # machine, which the evidence has no business publishing.
    start = next((i for i, part in enumerate(command) if os.path.basename(part) == "uvicorn"), None)
    shown = " ".join([os.path.basename(command[start])] + command[start + 1:]) if start is not None else None
    cwd = (_command(["lsof", "-a", "-p", pid, "-d", "cwd", "-Fn"]) or "").splitlines()
    cwd_path = next((line[1:] for line in cwd if line.startswith("n")), None)
    changed_after = []
    app_dir = os.path.join(root, "backend", "app")
    if started is not None:
        for folder, folders, files in os.walk(app_dir):
            folders[:] = [f for f in folders if f != "__pycache__"]
            for name in files:
                path = os.path.join(folder, name)
                try:
                    modified = os.path.getmtime(path)
                except OSError:  # removed while being walked; other sessions share this tree
                    continue
                if modified > started.timestamp():
                    changed_after.append(os.path.relpath(path, root))
    return {"found": True, "pid": int(pid), "started_at": _iso(started), "command": shown,
            "reload": "--reload" in command,
            "cwd_is_this_backend": bool(cwd_path) and os.path.realpath(cwd_path) == os.path.realpath(os.path.join(root, "backend")),
            "app_files_modified_after_start": sorted(changed_after)}


def running_code(repo: Dict[str, Any], process: Dict[str, Any]) -> Dict[str, Any]:
    """Whether the process serves HEAD. Inferred, and said to be: no endpoint names its commit.

    The backend runs without --reload, so it serves the tree as it stood when it started. Other
    sessions edit this tree while it runs; an application file that differs from HEAD only because
    it was changed AFTER the start was not what the process loaded. Modification times cannot show
    an earlier edit to a file that was changed again later, and the answer says so.
    """
    started, moved = _instant(process.get("started_at")), _instant(repo.get("head_moved_at"))
    changed = repo.get("app_tree_changes")
    later = set(process.get("app_files_modified_after_start") or [])
    if not (started and moved) or changed is None:
        return {"includes_head": None, "basis": "unknown",
                "detail": "the process start, the moment HEAD arrived or the tree's state could not be read"}
    if started <= moved:
        if not changed and not later:
            # HEAD arrived later, but no application file has changed since the start and the tree
            # matches HEAD: the commit recorded files already on disk when the process loaded them
            # (a checkout or merge that changed one would have moved its modification time).
            return {"includes_head": True, "basis": "inferred",
                    "detail": (f"HEAD reached this tree at {_iso(moved)}, after the process started at "
                               f"{_iso(started)}, but no application file has changed since the start and the "
                               "application tree matches HEAD, so what it loaded is HEAD's code (a file deleted "
                               "since, or an edit made and undone before the start, cannot be seen from "
                               "modification times)")}
        return {"includes_head": False, "basis": "inferred",
                "detail": f"the process started at {_iso(started)}, before HEAD reached this tree at {_iso(moved)}"}
    if not changed:
        return {"includes_head": True, "basis": "inferred",
                "detail": "the process started after HEAD reached this tree, and the application tree matches HEAD"}
    earlier = [path for path in changed if path not in later]
    if not earlier:
        return {"includes_head": True, "basis": "inferred",
                "detail": (f"the process started after HEAD reached this tree; the {len(changed)} application "
                           "file(s) that differ from HEAD were all last changed after it started, so none is what "
                           "it loaded (an earlier edit to one of the same files cannot be ruled out from "
                           "modification times)")}
    return {"includes_head": None, "basis": "unknown",
            "detail": f"application file(s) changed before the process started and differ from HEAD: {', '.join(earlier[:5])}"}


# ================================================================================ redaction
#: Keys that never appear in the output, whatever they hold.
FORBIDDEN_KEYS = frozenset({"email", "user_id", "recorded_reference", "note", "notes", "token", "key", "secret",
                            "password", "stake_minor", "currency"})
#: Fragments that make a key forbidden wherever they appear in its name.
FORBIDDEN_KEY_PARTS = ("email", "token", "secret", "password", "api_key", "apikey")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CREDENTIAL_PARAM = re.compile(r"(?i)\b(api[_-]?key|apikey|key|secret|token|password)=([^&\s\"']+)")


def credential_values() -> List[str]:
    """Every configured credential value, so it can be scrubbed from any string that quotes it.

    Collected from the settings by name (KEY, SECRET, TOKEN, PASSWORD) and from the password part
    of every configured URL. Never printed: they exist here only to be removed.
    """
    values = set()
    try:
        fields = settings.model_dump()
    except Exception:  # pragma: no cover - older pydantic
        fields = dict(vars(settings))
    for name, value in fields.items():
        if hasattr(value, "get_secret_value"):
            value = value.get_secret_value()
        if not isinstance(value, str) or not value:
            continue
        if re.search(r"KEY|SECRET|TOKEN|PASSWORD", name.upper()) and len(value) >= 6:
            values.add(value)
        if name.upper().endswith("_URL"):
            try:
                password = urlsplit(value).password
            except ValueError:
                password = None
            if password and len(password) >= 4:
                values.add(password)
    return sorted(values, key=len, reverse=True)


def _forbidden(name: Any) -> bool:
    lowered = str(name).lower()
    return lowered in FORBIDDEN_KEYS or any(part in lowered for part in FORBIDDEN_KEY_PARTS)


def redact(value: Any, secrets: Sequence[str] = ()) -> Any:
    """The output made fit for a public repository: forbidden keys dropped, emails, credential
    parameters and configured credential values scrubbed from every string, and the home
    directory replaced by "~"."""
    if isinstance(value, dict):
        return {k: redact(v, secrets) for k, v in value.items() if not _forbidden(k)}
    if isinstance(value, (list, tuple)):
        return [redact(v, secrets) for v in value]
    if isinstance(value, str):
        scrubbed = value
        for secret in secrets:
            if secret and secret in scrubbed:
                scrubbed = scrubbed.replace(secret, "[redacted]")
        home = os.path.expanduser("~")
        if home and home != "/" and home in scrubbed:
            scrubbed = scrubbed.replace(home, "~")
        scrubbed = _EMAIL.sub("[redacted-email]", scrubbed)
        return _CREDENTIAL_PARAM.sub(lambda m: f"{m.group(1)}=[redacted]", scrubbed)
    return value


# ======================================================================================= run
def load_previous(paths: Sequence[str]) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]]]:
    """Suggestion observations from earlier runs: the fixtures a run saw suggested, and when."""
    names, hits = [], {}
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
        names.append(os.path.basename(path))
        for fixture in document.get("fixtures") or []:
            stage = (fixture.get("stages") or {}).get("suggestion") or {}
            if stage.get("verdict") != "proven":
                continue
            evidence = stage.get("evidence") or {}
            hits.setdefault(str(fixture.get("match_id")), []).append({
                "file": os.path.basename(path), "generated_at": evidence.get("generated_at") or stage.get("at"),
                "evidence": {k: evidence.get(k) for k in ("call", "basis", "selection_id", "probability", "snapshot_id", "rank")},
            })
    return names, hits


def run(session_factory: Callable[[], Session], *, api: Optional[GuardedClient], store: Optional[ReadOnlyRedis],
        budget_store: Optional[ReadOnlyRedis], selection: Dict[str, Any], since: datetime,
        previous_paths: Sequence[str] = (), qa_email: str = QA_EMAIL_DEFAULT, primary: Optional[str] = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), repo_root: Optional[str] = None,
        process_check: bool = True, database_name: Optional[str] = None) -> Dict[str, Any]:
    """The whole proof, bracketed by the spend check, redacted for publication.

    `clock` is read once at the start (the instant every verdict is judged at) and once for the
    closing spend reading, whose Redis keys are the UTC day of THAT moment: a run that crosses
    midnight is then caught as one, not compared against the wrong day's counters.
    """
    now = clock()
    previous_names, previous_hits = load_previous(previous_paths)

    health = api.get("/health") if api is not None else None
    status_before = api.get("/api/v1/data-providers/status") if api is not None else None
    status_body = status_before.get("body") if status_before and status_before.get("ok") else None
    fallbacks = [n.strip() for n in (settings.DATA_PROVIDER_FALLBACKS or "").split(",") if n.strip()]
    if status_body:
        names = [p.get("name") for p in status_body.get("chain") or []]
        names.append(((status_body.get("forecasts") or {}).get("budget") or {}).get("provider") or settings.PREDICTION_PROVIDER)
    else:
        names = [settings.DATA_PROVIDER] + fallbacks + [settings.PREDICTION_PROVIDER]
    names = list(dict.fromkeys(n for n in names if n))
    redis_before = spend_from_redis(budget_store, names, now) if budget_store is not None else None

    if status_body:
        view = status_view_from_api(status_body)
    else:
        view = status_view_from_redis(store, budget_store, now, settings.DATA_PROVIDER, fallbacks,
                                      settings.PREDICTION_PROVIDER)
    if primary:
        view["primary"] = primary

    with read_only_session(session_factory) as db:
        database = {"name": database_name,
                    "transaction_read_only": db.execute(text("SHOW transaction_read_only")).scalar(),
                    "default_transaction_read_only": db.execute(text("SHOW default_transaction_read_only")).scalar()}
        stored = stored_signals(db, since)
        access = detect_match_data_access(view, stored, since)
        body = prove(db, now=now, since=since, access=access, view=view, api=api, selection=selection,
                     previous_hits=previous_hits, qa_email=qa_email)

    status_after = api.get("/api/v1/data-providers/status") if api is not None else None
    redis_after = spend_from_redis(budget_store, names, clock()) if budget_store is not None else None
    api_check = compare_spend(spend_from_status(status_body) if status_body else None,
                              spend_from_status(status_after["body"]) if status_after and status_after.get("ok") else None)
    redis_check = compare_spend(redis_before, redis_after)
    spend = {"verdict": _overall_spend(api_check, redis_check),
             "method": ("used_today minus the scheduler's own ledger, before and after the run: from the status "
                        "endpoint (one transaction per provider) and from the Redis counters (one MULTI/EXEC)"),
             "api": api_check, "redis": redis_check}

    repo = repo_state(repo_root) if repo_root else None
    process = None
    if process_check and api is not None:
        port = urlsplit(api.base_url).port or 80
        process = backend_process(port, repo_root or os.getcwd())
    result = {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL,
        "generated_at": _iso(now),
        "run": {"access_since": _iso(since), "selection": {
            "matches": [str(m) for m in selection.get("matches") or []],
            "slips": [str(s) for s in selection.get("slips") or []],
            "window": [_iso(w) for w in selection["window"]] if selection.get("window") else None,
            "recorded_slips": bool(selection.get("recorded_slips"))}},
        "previous": previous_names,
        "repo": repo,
        "backend": {"api": api.base_url if api is not None else None,
                    "health": (health.get("body") if health and health.get("ok") else _detail_view(health)),
                    "process": process,
                    "running_code": running_code(repo or {}, process or {}) if repo and process else None},
        "database": database,
        "guards": {"http": api.summary() if api is not None else None,
                   "redis_refused": (store.refused if store is not None else []) +
                                    (budget_store.refused if budget_store is not None else [])},
        "match_data_access": access,
        "forecasts": view.get("forecasts"),
        "spend_check": spend,
        "summary": summarise(body["fixtures"], body["slips"]),
        "not_found": body["not_found"],
        "suggestions_default": body["suggestions_default"],
        "fixtures": body["fixtures"],
        "slips": body["slips"],
    }
    return redact(result, credential_values())


# ================================================================================= rendering
def render(result: Dict[str, Any]) -> str:
    access = result["match_data_access"]
    out = [f"Journey proof at {result['generated_at']} (access since {access['access_since']})",
           f"match_data_access: {access['verdict']}"
           + (f"  missing: {', '.join(access['missing'])}" if access.get("missing") else "")]
    for provider in access["providers"]:
        out.append(f"  {provider['name']:<13} {provider['role']:<8} last success {provider['last_success_at'] or 'never'}"
                   f"; last error: {provider['last_error'] or '-'}")
    spend = result["spend_check"]
    out.append(f"spend_check: {spend['verdict']}")
    for name, entry in spend["api"]["providers"].items():
        out.append(f"  {name:<13} spent besides the scheduler {entry['spent_besides_scheduler']}, "
                   f"scheduler {entry['scheduler_sent_in_run']}")
    backend = result["backend"]
    if backend.get("process"):
        out.append(f"backend: pid {backend['process'].get('pid')} started {backend['process'].get('started_at')}; "
                   f"repo HEAD {((result.get('repo') or {}).get('head') or '?')[:7]}; "
                   f"running code includes HEAD: {(backend.get('running_code') or {}).get('includes_head')}")
    out.append("")
    out.append(f"{len(result['fixtures'])} fixture(s)")
    for fixture in result["fixtures"]:
        chain = fixture["chain"]
        where = f" at {chain['stage']}" if chain["stage"] else ""
        flags = f"  [{', '.join(sorted(fixture['flags']))}]" if fixture["flags"] else ""
        then = f"; then {'; '.join(chain['later'])}" if chain.get("later") else ""
        out.append(f"  {(fixture['kickoff'] or '')[:16]}  {fixture['fixture'][:38]:<38}  {chain['verdict']}{where}{then}{flags}")
    if result["slips"]:
        out.append("")
        out.append(f"{len(result['slips'])} slip(s)")
        for slip in result["slips"]:
            out.append(f"  {slip['id']}  {slip['status']}/{slip['state']}  dry run {slip['dry_run_state']}  -> {slip['verdict']}")
            for leg in slip["legs"]:
                out.append(f"     {leg['fixture'] or leg['match_id']}: {leg['selection_id']}  stored {leg['stored_state']}, "
                           f"dry run {leg['dry_run_state']} -> {leg['verdict']}")
    out.append("")
    for name, counts in result["summary"]["stages"].items():
        out.append(f"  {name:<18} " + ", ".join(f"{verdict} {count}" for verdict, count in counts.items()))
    return "\n".join(out)


def _out_path(path: str, generated_at: str) -> str:
    """A directory gets `<UTC yyyy-mm-ddTHHMMZ>.json`; a file name is used as given."""
    if path.endswith(os.sep) or os.path.isdir(path):
        stamp = _instant(generated_at).strftime("%Y-%m-%dT%H%MZ")
        path = os.path.join(path, f"{stamp}.json")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--match", action="append", default=[], metavar="ID",
                        help="a fixture: internal UUID or provider id (repeatable)")
    parser.add_argument("--slip", action="append", default=[], metavar="UUID", help="a slip (repeatable)")
    parser.add_argument("--window", nargs=2, metavar=("FROM", "TO"), help="every fixture kicking off in [FROM, TO)")
    parser.add_argument("--recorded-slips", action="store_true", help="every recorded slip and its fixtures")
    parser.add_argument("--api", default=DEFAULT_API, help=f"the backend to read (default {DEFAULT_API})")
    parser.add_argument("--access-since", default=DEFAULT_ACCESS_SINCE,
                        help=f"a match-data signal counts only when later than this (default {DEFAULT_ACCESS_SINCE})")
    parser.add_argument("--primary", default=None, help="the primary match-data provider (default: the status endpoint's)")
    parser.add_argument("--previous", nargs="*", default=[], help="earlier evidence files, for the suggestion stage after kickoff")
    parser.add_argument("--json", action="store_true", help="print the JSON instead of the summary")
    parser.add_argument("--out", default=None, help="write the JSON here (a directory gets a UTC-stamped name); never overwrites")
    parser.add_argument("--database-url", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not (args.match or args.slip or args.window or args.recorded_slips):
        parser.error("name what to prove: --match, --slip, --window or --recorded-slips")
    since = _instant(args.access_since)
    if since is None:
        parser.error(f"--access-since is not an ISO-8601 instant: {args.access_since}")
    window = None
    if args.window:
        window = (_instant(args.window[0]), _instant(args.window[1]))
        if None in window or window[0] >= window[1]:
            parser.error("--window needs two ISO-8601 instants, FROM before TO")
    # This is a report: the engine's statement echo (on when the backend runs with DEBUG) and the
    # HTTP client's request log would bury it.
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    database_url = args.database_url or settings.DATABASE_URL
    engine = read_only_engine(database_url)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    api = GuardedClient(args.api)
    match_client, budget_client = _redis_client(settings.REDIS_DB_MATCH_DATA), _redis_client(settings.REDIS_DB_RATE_LIMIT)
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        result = run(factory, api=api, store=ReadOnlyRedis(match_client) if match_client else None,
                     budget_store=ReadOnlyRedis(budget_client) if budget_client else None,
                     selection={"matches": args.match, "slips": args.slip, "window": window,
                                "recorded_slips": args.recorded_slips},
                     since=since, previous_paths=args.previous,
                     qa_email=os.environ.get("E2E_QA_EMAIL") or QA_EMAIL_DEFAULT, primary=args.primary,
                     repo_root=repo_root, database_name=urlsplit(database_url).path.lstrip("/") or None)
    finally:
        api.close()
        engine.dispose()

    payload = json.dumps(result, indent=2, sort_keys=False, default=str)
    if args.out:
        path = _out_path(args.out, result["generated_at"])
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # "x": one file per run, never overwritten. A second run in the same minute fails loudly
        # rather than replacing the evidence the first one wrote.
        with open(path, "x", encoding="utf-8") as handle:
            handle.write(payload + "\n")
        print(f"wrote {redact(os.path.abspath(path))}", file=sys.stderr)
    print(payload if args.json else render(result))
    return 2 if result["spend_check"]["verdict"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
