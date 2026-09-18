"""
Explicit, quota-safe data refresh.

Everything the app shows is read from stored data. Without this module nothing is ever refreshed
unless a visitor happens to load a page with `refresh=true`, which makes "last updated" a function
of who browsed the site rather than of any process the owner controls.

Four tasks, because the four kinds of data do not go stale at the same rate:

  fixtures   the day's matches and the next few days      - hours
  live       scores, ONLY while a covered match is in its live window - minutes
  results    finished matches, so settlement has something to score   - half hours
  forecasts  third-party model forecasts, rotated by ForecastService  - hours

Nothing here fetches anything itself. Each task calls the service that already knows how to talk to
a provider (`MatchDataService`, `ForecastService`), so the provider chain, the Redis caches, the
cool-downs after a failure, the forecast sync lock and - above all - `RequestBudget` still apply
exactly as they do on the request path.

The failure this design is actually built against is not a missed refresh, it is a runaway loop on a
trial plan. Five separate things stop that:

  1. every provider call still goes through RequestBudget, unchanged;
  2. a hard ceiling checked BEFORE the task runs: when the day's allowance is spent (minus a reserve
     kept for interactive page loads) the task is skipped and says so. `remaining()` only reads the
     counter, so a skip never produces a refused reservation;
  3. a task that fails backs off exponentially instead of retrying on the next tick;
  4. a Redis lock per task, so a second worker - or `scripts/sync_once.py` run by hand - cannot run
     the same task at the same time;
  5. due-times live in Redis, not in memory, so restarting the backend does not re-trigger a pass.
     A startup grace period covers the first-ever start and the case where Redis is unavailable.

No new dependency: FastAPI's lifespan owns one asyncio task, and because the provider calls are
blocking they run in a single-threaded executor rather than on the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService, SyncMeta

logger = logging.getLogger(__name__)

TASK_FIXTURES = "fixtures"
TASK_LIVE = "live"
TASK_RESULTS = "results"
TASK_FORECASTS = "forecasts"
TASK_SETTLE = "settle"
#: Order matters: `settle` runs after `results`, so a result ingested this pass is scored in it
#: rather than half an hour later.
TASK_NAMES: Tuple[str, ...] = (TASK_FIXTURES, TASK_LIVE, TASK_RESULTS, TASK_FORECASTS, TASK_SETTLE)

#: What one forecast competition's turn is assumed to cost when its provider will not price it:
#: a league-id discovery and then the fetch, which is the expensive case. The dry run is an upper
#: bound, so where it cannot know it rounds UP - a number that under-reports what a trial plan is
#: about to spend is worse than no number at all.
UNPRICED_TURN_COST = 2

STATE_KEY = "sync:task:{name}"
LOCK_KEY = "sync:lock:{name}"
#: Task state outlives any plausible outage, so "last succeeded" stays honest after a long stop.
STATE_TTL_SECONDS = 14 * 24 * 3600
#: Longer than any single pass, short enough that a killed worker does not wedge a task for an hour.
LOCK_TTL_SECONDS = 15 * 60

#: A failing task never retries sooner than this, whatever its normal interval is.
BACKOFF_MIN_SECONDS = 300
BACKOFF_MAX_SECONDS = 6 * 3600

#: Keep the stored summary small: it is read by the status endpoint on every call.
MAX_STORED_ERRORS = 10
MAX_ERROR_CHARS = 300


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):  # a hand-edited or corrupted state entry must not wedge the loop
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _clip(errors: Sequence[str]) -> List[str]:
    return [str(e)[:MAX_ERROR_CHARS] for e in list(errors)[:MAX_STORED_ERRORS]]


def _next_budget_reset(now: datetime) -> datetime:
    """Both providers count per UTC day, so their allowances come back at UTC midnight.

    A minute of slack keeps a clock a hair ahead of the provider's from asking before the reset.
    """
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(minutes=1)


class _Services:
    """The two services a pass needs, built at most once per pass and only when actually used.

    Building `MatchDataService.providers` constructs the provider chain (no network), and building it
    four times per pass would re-read the competition-id store four times for nothing.
    """

    def __init__(self, scheduler: "SyncScheduler", db):
        self._scheduler = scheduler
        self._db = db
        self._match: Optional[MatchDataService] = None
        self._forecast: Optional[ForecastService] = None

    @property
    def match(self) -> MatchDataService:
        if self._match is None:
            factory = self._scheduler._match_factory
            self._match = (factory(self._db) if factory
                           else MatchDataService(self._db, cache=self._scheduler.cache,
                                                 now=self._scheduler.fixed_now))
        return self._match

    @property
    def forecast(self) -> ForecastService:
        if self._forecast is None:
            factory = self._scheduler._forecast_factory
            self._forecast = (factory(self._db) if factory
                              else ForecastService(self._db, cache=self._scheduler.cache,
                                                   now=self._scheduler.fixed_now))
        return self._forecast


class SyncScheduler:
    """Decides what is due, runs it safely, and records what happened."""

    def __init__(self, session_factory: Optional[Callable[[], Any]] = None,
                 cache: Optional[MatchCache] = None,
                 now: Optional[Any] = None,
                 match_service_factory: Optional[Callable[[Any], MatchDataService]] = None,
                 forecast_service_factory: Optional[Callable[[Any], ForecastService]] = None,
                 tasks: Optional[Iterable[str]] = None,
                 close_sessions: bool = True):
        self._session_factory = session_factory
        self.cache = cache or MatchCache()
        #: A datetime or a zero-argument callable; None means "real clock". Tests pass a fake clock.
        self._now = now
        self._match_factory = match_service_factory
        self._forecast_factory = forecast_service_factory
        self._tasks = list(tasks) if tasks is not None else None
        self._close_sessions = close_sessions
        self._token = uuid.uuid4().hex
        self._executor: Optional[ThreadPoolExecutor] = None

    # ------------------------------------------------------------------ clock / config
    @property
    def now(self) -> datetime:
        if self._now is None:
            return datetime.now(timezone.utc)
        return self._now() if callable(self._now) else self._now

    @property
    def fixed_now(self) -> Optional[datetime]:
        """The pinned instant to hand to the data services, or None to let them use the real clock."""
        return None if self._now is None else self.now

    def enabled_tasks(self) -> List[str]:
        """Tasks the background loop is allowed to run, in a stable order."""
        if self._tasks is not None:
            wanted = {n.strip().lower() for n in self._tasks}
        else:
            wanted = {n.strip().lower() for n in settings.SYNC_SCHEDULER_TASKS.split(",") if n.strip()}
        unknown = wanted - set(TASK_NAMES)
        if unknown:
            logger.warning("Unknown sync task(s) in SYNC_SCHEDULER_TASKS: %s", ", ".join(sorted(unknown)))
        return [name for name in TASK_NAMES if name in wanted]

    def interval(self, name: str) -> int:
        seconds = {
            TASK_FIXTURES: settings.SYNC_FIXTURES_INTERVAL_SECONDS,
            TASK_LIVE: settings.SYNC_LIVE_INTERVAL_SECONDS,
            TASK_RESULTS: settings.SYNC_RESULTS_INTERVAL_SECONDS,
            TASK_FORECASTS: settings.SYNC_FORECASTS_INTERVAL_SECONDS,
            TASK_SETTLE: settings.SYNC_SETTLE_INTERVAL_SECONDS,
        }[name]
        # A misconfigured 0 would turn the loop into a hot loop against the provider.
        return max(int(seconds), 30)

    # ------------------------------------------------------------------ state
    def state(self, name: str) -> Dict[str, Any]:
        stored = self.cache.get(STATE_KEY.format(name=name))
        return dict(stored) if isinstance(stored, dict) else {}

    def _save_state(self, name: str, state: Dict[str, Any]) -> None:
        self.cache.set(STATE_KEY.format(name=name), state, ttl=STATE_TTL_SECONDS, stale_ttl=STATE_TTL_SECONDS)

    def due(self, name: str) -> Tuple[bool, Optional[str]]:
        """(due now, why not). A task that has never run on this installation is due."""
        next_due = _parse(self.state(name).get("next_due_at"))
        if next_due is None:
            return True, None
        now = self.now
        if now >= next_due:
            return True, None
        return False, f"next due at {next_due.isoformat()}"

    def _backoff_seconds(self, name: str, consecutive_failures: int) -> int:
        base = max(self.interval(name), BACKOFF_MIN_SECONDS)
        return int(min(base * (2 ** max(consecutive_failures - 1, 0)), BACKOFF_MAX_SECONDS))

    def _record(self, name: str, *, result: Optional[Dict[str, Any]], ok: bool,
                error: Optional[str], started: datetime) -> Dict[str, Any]:
        now = self.now
        state = self.state(name)
        state["last_run_at"] = now.isoformat()
        state["last_duration_ms"] = int(max((now - started).total_seconds(), 0) * 1000)
        state["runs"] = int(state.get("runs") or 0) + 1
        state["last_result"] = result
        state["last_skip_reason"] = None
        if ok:
            state["last_success_at"] = now.isoformat()
            state["consecutive_failures"] = 0
            state["last_error"] = None
            state["backoff_seconds"] = None
            state["next_due_at"] = (now + timedelta(seconds=self.interval(name))).isoformat()
        else:
            failures = int(state.get("consecutive_failures") or 0) + 1
            backoff = self._backoff_seconds(name, failures)
            state["failures"] = int(state.get("failures") or 0) + 1
            state["consecutive_failures"] = failures
            state["last_error_at"] = now.isoformat()
            state["last_error"] = (error or "task reported no usable data")[:MAX_ERROR_CHARS]
            state["backoff_seconds"] = backoff
            # Back off rather than retrying on the next tick: whatever broke is unlikely to be fixed
            # in sixty seconds, and each retry is a provider request nobody asked for.
            #
            # But never past the next budget reset. The commonest way a task fails here is the
            # allowance running out mid-pass (a spent provider is reported as a failure, not a
            # skip), and a 6 h backoff taken at 22:30 would park the task until 04:30 - hours of a
            # fresh day's allowance spent waiting for a quota that came back at midnight. `min`
            # only ever pulls the retry earlier, so a short backoff is untouched, and
            # `backoff_seconds` above still records the real penalty.
            state["next_due_at"] = min(now + timedelta(seconds=backoff),
                                       _next_budget_reset(now)).isoformat()
        self._save_state(name, state)
        return state

    def _record_skip(self, name: str, reason: str, advance: bool) -> None:
        now = self.now
        state = self.state(name)
        state["last_skipped_at"] = now.isoformat()
        state["last_skip_reason"] = reason[:MAX_ERROR_CHARS]
        if advance:
            # Re-asking every minute is free but pointless, and it floods the log. Wait a normal
            # interval - but never past the next budget reset: a task blocked late in the evening
            # should resume when the allowance comes back, not hours into the new day.
            state["next_due_at"] = min(now + timedelta(seconds=self.interval(name)),
                                       _next_budget_reset(now)).isoformat()
        self._save_state(name, state)

    # ------------------------------------------------------------------ locking
    def _client(self):
        return getattr(self.cache, "_redis", lambda: None)()

    def _acquire_lock(self, name: str) -> bool:
        """One instance of a task at a time, across workers and across the one-shot script.

        Best effort: without Redis there is nothing to coordinate through, and refusing to sync at
        all would be a worse failure than a duplicated pass on a single-process install.
        """
        client = self._client()
        if client is None:
            return True
        try:
            return bool(client.set(LOCK_KEY.format(name=name), self._token, nx=True, ex=LOCK_TTL_SECONDS))
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.debug("Sync lock unavailable for %s (%s); proceeding without it", name, exc)
            return True

    def _release_lock(self, name: str) -> None:
        client = self._client()
        if client is None:
            return
        key = LOCK_KEY.format(name=name)
        try:
            # compare-and-delete, so a lock that already expired and was retaken is not released here
            if client.get(key) in (self._token, self._token.encode("utf-8")):
                client.delete(key)
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ budget ceiling
    @staticmethod
    def _providers_for(services: _Services, name: str) -> List[Any]:
        """Every provider this task could call, in the order the chain would try them."""
        if name == TASK_SETTLE:
            # Scoring reads stored results and stored predictions. It calls nobody, so no budget can
            # block it — which is the point: a spent allowance must never stop us scoring what we
            # already hold.
            return []
        if name == TASK_FORECASTS:
            provider = services.forecast.provider
            return [provider] if provider is not None else []
        return [p for p in services.match.providers if p is not None]

    def _budget_of(self, services: _Services, name: str):
        """The budget of the provider this task would reach for first (for reporting)."""
        providers = self._providers_for(services, name)
        return getattr(providers[0], "budget", None) if providers else None

    def _budget_block(self, services: _Services, name: str) -> Optional[str]:
        """Why this task must not call any of its providers right now, or None.

        Only reads the counters. Reserving here and being refused would inflate the refused counter
        with requests nobody ever intended to send, which is exactly the noise that counter exists to
        expose. A fallback provider with allowance left is reason enough to run: the ceiling stops a
        task only when every provider it could reach is out.
        """
        spent = []
        for provider in self._providers_for(services, name):
            budget = getattr(provider, "budget", None)
            try:
                limit = int(getattr(budget, "daily_limit", 0) or 0)
                if budget is None or not limit:
                    return None  # unmetered provider: nothing here can say it is out of allowance
                remaining, used = budget.remaining(), budget.used_today()
                # Never let the reserve swallow a small plan: a 10/day allowance keeps 1 back, not 50.
                reserve = min(max(int(settings.SYNC_SCHEDULER_BUDGET_RESERVE), 0), limit // 10)
            except Exception as exc:  # pragma: no cover - the ceiling is best effort, never a blocker
                logger.debug("Budget check failed for %s: %s", name, exc)
                return None
            if remaining - reserve >= 1:
                return None
            spent.append(f"{budget.provider} ({used}/{limit} used; {reserve} held back for page loads)")
        if not spent:
            return None
        return "daily request budget is spent for " + " and ".join(spent)

    # ------------------------------------------------------------------ the tasks
    def _run_fixtures(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        service = services.match
        days = max(int(settings.SYNC_FIXTURES_DAYS_AHEAD), 1)
        today = service.now.date()
        out: Dict[str, Any] = {"days": {}, "errors": []}
        got_data = False
        for offset in range(days):
            day = today + timedelta(days=offset)
            meta = service.sync_day(day)
            out["days"][day.isoformat()] = meta.to_dict()
            out["errors"].extend(meta.errors)
            if meta.source != "database":
                got_data = True
        out["errors"] = _clip(out["errors"])
        out["days_requested"] = days
        error = None if got_data else "; ".join(out["errors"]) or "no fixture data could be obtained"
        return out, got_data, error

    def _run_results(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        service = services.match
        lookback = max(int(settings.SYNC_RESULTS_LOOKBACK_DAYS), 0)
        today = service.now.date()
        out: Dict[str, Any] = {"days": {}, "errors": [], "polled": False}
        for offset in range(lookback + 1):
            day = today - timedelta(days=offset)
            meta = SyncMeta()
            # Gated inside `_sync_results`: a day with nothing left to settle costs no request.
            service._sync_results(day, meta)
            out["days"][day.isoformat()] = meta.to_dict()
            out["errors"].extend(meta.errors)
            out["polled"] = out["polled"] or meta.results_polled
        out["errors"] = _clip(out["errors"])
        ok = not out["errors"]
        return out, ok, "; ".join(out["errors"]) or None

    def _run_live(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        service = services.match
        if not service._live_window_open():
            # The single most expensive mistake available here is polling live scores all night.
            return ({"live_window_open": False, "live_polled": False,
                     "note": "no covered match is in its live window; no provider request made"},
                    True, None)
        meta = SyncMeta()
        service._sync_live(meta)
        out = {"live_window_open": True, **meta.to_dict()}
        out["errors"] = _clip(out["errors"])
        ok = not out["errors"]
        return out, ok, "; ".join(out["errors"]) or None

    def _run_forecasts(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        # ForecastService already rotates least-recently-synced first, holds its own lock, enforces
        # its own per-competition interval and stops before reserving when its allowance is gone.
        report = services.forecast.ensure_synced()
        error = report.get("error")
        return report, not error, error

    def _run_settle(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        """Score the prematch evidence for matches that have finished. Makes no provider request.

        Without this the results task ingests final scores and nothing ever reads them: the table
        `prediction_results` sat empty for exactly that reason before the scheduler existed.
        """
        from app.services.settlement import SettlementService

        now = services.match.now
        lookback = max(int(settings.SYNC_SETTLE_LOOKBACK_DAYS), 1)
        service = SettlementService(self._db_of(services))
        report = service.settle_range(start=now - timedelta(days=lookback), end=now)
        errors = _clip(list(report.get("errors") or []))
        report["errors"] = errors
        return report, not errors, "; ".join(errors) or None

    @staticmethod
    def _db_of(services: _Services):
        return services._db

    def _execute(self, name: str, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        return {
            TASK_FIXTURES: self._run_fixtures,
            TASK_LIVE: self._run_live,
            TASK_RESULTS: self._run_results,
            TASK_FORECASTS: self._run_forecasts,
            TASK_SETTLE: self._run_settle,
        }[name](services)

    # ------------------------------------------------------------------ one pass
    def run_once(self, only: Optional[Iterable[str]] = None, force: bool = False) -> Dict[str, Any]:
        """Run every due task once and return what happened. Blocking; never raises for a task failure."""
        names = self._selected(only)
        report: Dict[str, Any] = {"started_at": self.now.isoformat(), "tasks": {}}
        if not names:
            report["note"] = "no sync task is enabled"
            report["finished_at"] = self.now.isoformat()
            return report
        # Whether a task is due is answered from Redis alone. Deciding first means the common tick -
        # the one where nothing is due - does not open a database connection every minute.
        verdicts = {name: ((True, None) if force else self.due(name)) for name in names}
        db = self._open_session() if any(is_due for is_due, _ in verdicts.values()) else None
        services = _Services(self, db) if db is not None else None
        try:
            for name in names:
                is_due, why = verdicts[name]
                if not is_due:
                    report["tasks"][name] = {"ran": False, "skipped": "not_due", "reason": why}
                    continue
                report["tasks"][name] = self._maybe_run(name, services)
        finally:
            if db is not None:
                self._close_session(db)
        report["finished_at"] = self.now.isoformat()
        return report

    def _selected(self, only: Optional[Iterable[str]]) -> List[str]:
        if only is None:
            return self.enabled_tasks()
        requested = [n.strip().lower() for n in only if str(n).strip()]
        unknown = [n for n in requested if n not in TASK_NAMES]
        if unknown:
            raise ValueError(f"Unknown sync task(s): {', '.join(unknown)}. "
                             f"Valid tasks: {', '.join(TASK_NAMES)}")
        # An explicit request wins over SYNC_SCHEDULER_TASKS: naming a task by hand is a deliberate act.
        return [name for name in TASK_NAMES if name in requested]

    def _maybe_run(self, name: str, services: _Services) -> Dict[str, Any]:
        """Run one task that has already been decided to be due. Never raises."""
        blocked = self._budget_block(services, name)
        if blocked:
            logger.info("Sync task %s skipped: %s", name, blocked)
            self._record_skip(name, blocked, advance=True)
            return {"ran": False, "skipped": "budget_spent", "reason": blocked}
        if not self._acquire_lock(name):
            # Another worker (or scripts/sync_once.py) is already paying for this task.
            return {"ran": False, "skipped": "locked",
                    "reason": f"another {name} sync is already running"}
        started = self.now
        try:
            try:
                result, ok, error = self._execute(name, services)
            except Exception as exc:  # a broken task must not stop the other three, or the loop
                logger.exception("Sync task %s failed", name)
                state = self._record(name, result=None, ok=False, error=str(exc), started=started)
                return {"ran": True, "ok": False, "error": str(exc),
                        "next_due_at": state.get("next_due_at"),
                        "consecutive_failures": state.get("consecutive_failures")}
            state = self._record(name, result=result, ok=ok, error=error, started=started)
            outcome: Dict[str, Any] = {"ran": True, "ok": ok, "result": result,
                                       "duration_ms": state.get("last_duration_ms"),
                                       "next_due_at": state.get("next_due_at")}
            if not ok:
                outcome["error"] = state.get("last_error")
                outcome["consecutive_failures"] = state.get("consecutive_failures")
            return outcome
        finally:
            self._release_lock(name)

    def _open_session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from app.db.session import SessionLocal
        return SessionLocal()

    def _close_session(self, db) -> None:
        if not self._close_sessions:
            return
        try:
            db.close()
        except Exception:  # pragma: no cover
            logger.debug("Closing the sync session failed", exc_info=True)

    # ------------------------------------------------------------------ dry run
    def estimate(self, only: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """What a pass would do and what it would cost. Makes no provider request."""
        names = self._selected(only)
        report: Dict[str, Any] = {"estimated_at": self.now.isoformat(), "tasks": {}, "total_requests": 0}
        if not names:
            report["note"] = "no sync task is enabled"
            return report
        db = self._open_session()
        services = _Services(self, db)
        try:
            for name in names:
                entry = self._estimate_task(name, services)
                report["tasks"][name] = entry
                if entry.get("would_run"):
                    report["total_requests"] += int(entry.get("estimated_requests") or 0)
        finally:
            self._close_session(db)
        return report

    def _estimate_task(self, name: str, services: _Services) -> Dict[str, Any]:
        is_due, why = self.due(name)
        budget = self._budget_of(services, name)
        entry: Dict[str, Any] = {
            "due_now": is_due,
            "reason_not_due": why,
            "interval_seconds": self.interval(name),
            "provider": getattr(budget, "provider", None),
            "budget_remaining": budget.remaining() if budget is not None else None,
        }
        blocked = self._budget_block(services, name)
        entry["blocked"] = blocked
        entry["would_run"] = bool(is_due and not blocked)
        try:
            requests, basis = self._estimate_cost(name, services)
        except Exception as exc:  # an estimate must never be the thing that breaks
            entry["estimated_requests"] = None
            entry["basis"] = f"could not be estimated: {exc}"
            return entry
        entry["estimated_requests"] = requests
        entry["basis"] = basis
        return entry

    @staticmethod
    def _forecast_pass_cost(provider: Any, due_keys: Sequence[str]) -> Tuple[int, str]:
        """(what these competitions' turns are expected to cost, and what that assumed).

        The bound holds for ONE page of events per fetch, which is what every covered competition
        has returned so far. A competition with more pages pays one more request per extra page
        (up to the provider's page cap), and those are not priced here: charging every fetch the
        cap would report four times the real cost of the only plan that has to be read exactly,
        and would hold back a pass that fits comfortably. The assumption is stated in the basis
        string that travels with the number, so a reader is never handed the figure alone.

        Each competition is priced by the provider itself, through the same `request_cost` seam
        `ForecastService` uses to decide whether it can afford to START a turn - so the estimate
        and the gate cannot disagree. A competition whose provider league id is already recorded
        costs one /events fetch; one that still has to be discovered pays a /leagues lookup first
        and costs two; one already marked unresolvable costs nothing, because its turn is
        short-circuited before any HTTP call.

        Dropping the discovery request is what made a six-competition pass estimate 6 and spend 7
        (champions_league is the one covered competition with no configured GameForecast id).
        Charging every competition two, the way this did before that, over-reported the cost of
        the one plan that has to be read exactly.

        A provider that will not price a turn is charged the expensive case: an estimate that
        cannot know rounds UP, because under-reporting a trial plan is how a pass overruns it.

        Prices are read from the provider's caches (Redis and in-memory). No request is made and
        nothing is written.
        """
        price = getattr(provider, "request_cost", None)
        costs: List[int] = []
        unpriced = 0
        for key in due_keys:
            cost = None
            if callable(price):
                try:
                    cost = max(int(price(key)), 0)
                except Exception as exc:  # pragma: no cover - pricing must never break an estimate
                    logger.debug("Could not price the %s turn for %s: %s",
                                 getattr(provider, "name", "provider"), key, exc)
            if cost is None:
                cost, unpriced = UNPRICED_TURN_COST, unpriced + 1
            costs.append(cost)

        wording = {
            0: "costing nothing (a remembered discovery failure short-circuits the turn)",
            1: "costing 1 request (the provider league id is already recorded)",
            2: "costing 2 (a league-id discovery, then the fetch)",
        }
        parts = []
        for cost in sorted(set(costs), reverse=True):
            count = costs.count(cost)
            parts.append(f"{count} {wording.get(cost) or f'costing {cost} request(s)'}")
        if unpriced:
            parts.append(f"{unpriced} of them not priced by "
                         f"{getattr(provider, 'name', 'the provider')!r}, so charged the "
                         f"expensive case rather than assumed cheap")
        return sum(costs), "; ".join(parts) or "nothing is due"

    def _estimate_cost(self, name: str, services: _Services) -> Tuple[int, str]:
        """What this task is expected to spend, before caching. Reads the database, never a provider.

        An estimate, not a guarantee: see `_forecast_pass_cost` for the one assumption it makes
        (a single page of events per competition) and why pricing the page cap instead would be
        worse. The basis string returned beside the number says what was assumed.
        """
        if name == TASK_FORECASTS:
            forecast = services.forecast
            if forecast.provider is None:
                return 0, "no prediction provider is configured"
            interval = timedelta(hours=settings.GAMEFORECAST_SYNC_INTERVAL_HOURS)
            now = forecast.now
            due_keys = [k for k in forecast.sync_order()
                        if not forecast._last_sync(k) or now - forecast._last_sync(k) >= interval]
            cost, assumed = self._forecast_pass_cost(forecast.provider, due_keys)
            budget = getattr(forecast.provider, "budget", None)
            capped = min(cost, budget.remaining()) if budget is not None and budget.daily_limit else cost
            # Count only what this task bills to the FORECAST allowance. Each competition also
            # triggers a fixture sync, but that goes through MatchDataService and is charged to the
            # match-data providers' budgets; adding it here doubled the apparent cost of the small
            # forecast plan, which is the one figure that has to be read exactly.
            return (capped,
                    f"{len(due_keys)} competition(s) past their {settings.GAMEFORECAST_SYNC_INTERVAL_HOURS}h "
                    f"interval ({assumed}): {cost} request(s), capped at {capped} by the remaining "
                    f"{getattr(budget, 'provider', 'forecast')} allowance. Assumes one page of "
                    f"events per fetch; a competition with more than one page pays one more "
                    f"request per extra page. Each one also syncs fixtures, billed to the "
                    f"match-data providers, not to this allowance")
        if name == TASK_SETTLE:
            # Scoring reads stored results and stored predictions; it contacts nobody.
            return 0, "no provider request: scoring reads only what is already stored"
        service = services.match
        keys = len(service.keys)
        if name == TASK_FIXTURES:
            days = max(int(settings.SYNC_FIXTURES_DAYS_AHEAD), 1)
            return keys * days, f"1 request per competition per day: {keys} competition(s) x {days} day(s)"
        if name == TASK_LIVE:
            if not service._live_window_open():
                return 0, "no covered match is in its live window"
            return 1, "1 request (matches/live.json covers every competition at once)"
        lookback = max(int(settings.SYNC_RESULTS_LOOKBACK_DAYS), 0)
        today = service.now.date()
        pending = [today - timedelta(days=offset) for offset in range(lookback + 1)
                   if service._pending_results_exist(today - timedelta(days=offset))]
        return (keys * len(pending),
                f"1 request per competition for each day with an unsettled match: "
                f"{keys} competition(s) x {len(pending)} day(s)")

    # ------------------------------------------------------------------ status
    def status(self) -> Dict[str, Any]:
        enabled = self.enabled_tasks()
        payload: Dict[str, Any] = {
            "enabled": bool(settings.SYNC_SCHEDULER_ENABLED),
            "running": is_running(),
            "tick_seconds": max(int(settings.SYNC_SCHEDULER_TICK_SECONDS), 5),
            "startup_delay_seconds": max(int(settings.SYNC_SCHEDULER_STARTUP_DELAY_SECONDS), 0),
            "budget_reserve": int(settings.SYNC_SCHEDULER_BUDGET_RESERVE),
            "enabled_tasks": enabled,
            # Due-times and history live in Redis. Without it the scheduler still runs, but it cannot
            # remember when a task last ran, so freshness here would be a guess. Say so.
            "state_store_available": self.cache.available,
            "tasks": {},
        }
        for name in TASK_NAMES:
            state = self.state(name)
            is_due, why = self.due(name)
            never_run = not state.get("last_run_at")
            payload["tasks"][name] = {
                "enabled": name in enabled,
                "interval_seconds": self.interval(name),
                "never_run": never_run,
                "last_run_at": state.get("last_run_at"),
                "last_success_at": state.get("last_success_at"),
                "last_error_at": state.get("last_error_at"),
                "last_error": state.get("last_error"),
                "last_duration_ms": state.get("last_duration_ms"),
                "last_result": state.get("last_result"),
                "last_skipped_at": state.get("last_skipped_at"),
                "last_skip_reason": state.get("last_skip_reason"),
                "runs": int(state.get("runs") or 0),
                "failures": int(state.get("failures") or 0),
                "consecutive_failures": int(state.get("consecutive_failures") or 0),
                "backoff_seconds": state.get("backoff_seconds"),
                "next_due_at": state.get("next_due_at"),
                "due_now": is_due,
                "reason_not_due": why,
            }
        return payload

    # ------------------------------------------------------------------ background loop
    @property
    def executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            # One worker: a pass can never overlap itself inside this process, whatever the tick is.
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sync-scheduler")
        return self._executor

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None

    async def run_forever(self) -> None:
        """Tick until cancelled. The blocking work runs in a thread, never on the event loop."""
        delay = max(int(settings.SYNC_SCHEDULER_STARTUP_DELAY_SECONDS), 0)
        logger.info("Background sync scheduler started (tasks: %s); first tick in %ds",
                    ", ".join(self.enabled_tasks()) or "none", delay)
        try:
            # Development restarts the backend constantly. Waiting here means a restart loop cannot
            # turn into a request storm, even before the persisted due-times are consulted.
            await asyncio.sleep(delay)
            while True:
                try:
                    loop = asyncio.get_running_loop()
                    report = await loop.run_in_executor(self.executor, self.run_once)
                    ran = [n for n, r in report.get("tasks", {}).items() if r.get("ran")]
                    if ran:
                        logger.info("Background sync pass ran: %s", ", ".join(ran))
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - the loop must outlive any single failure
                    logger.exception("Background sync pass failed")
                await asyncio.sleep(max(int(settings.SYNC_SCHEDULER_TICK_SECONDS), 5))
        except asyncio.CancelledError:
            logger.info("Background sync scheduler stopped")
            raise
        finally:
            self.shutdown()


# ---------------------------------------------------------------------- process-wide handle
#: Set by the FastAPI lifespan so the status endpoint can say whether the loop is actually alive
#: rather than only whether it is configured to be.
_RUNNING_TASK: Optional["asyncio.Task"] = None


def is_running() -> bool:
    return _RUNNING_TASK is not None and not _RUNNING_TASK.done()


def start_background_scheduler() -> Optional["asyncio.Task"]:
    """Start the loop if enabled. Returns the task so the lifespan can stop it again."""
    global _RUNNING_TASK
    if not settings.SYNC_SCHEDULER_ENABLED:
        logger.info("Background sync scheduler disabled (SYNC_SCHEDULER_ENABLED=false)")
        return None
    scheduler = SyncScheduler()
    if not scheduler.enabled_tasks():
        logger.info("Background sync scheduler not started: SYNC_SCHEDULER_TASKS is empty")
        return None
    _RUNNING_TASK = asyncio.ensure_future(scheduler.run_forever())
    return _RUNNING_TASK


async def stop_background_scheduler(task: Optional["asyncio.Task"]) -> None:
    global _RUNNING_TASK
    _RUNNING_TASK = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:  # pragma: no cover
        logger.exception("Background sync scheduler stopped with an error")


def scheduler_status(cache: Optional[MatchCache] = None) -> Dict[str, Any]:
    """Scheduler state for the status endpoint. Touches Redis only; no database, no provider."""
    return SyncScheduler(cache=cache).status()
