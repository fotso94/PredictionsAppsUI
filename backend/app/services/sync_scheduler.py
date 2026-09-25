"""
Explicit, quota-safe data refresh.

Everything the app shows is read from stored data. Without this module nothing is ever refreshed
unless a visitor happens to load a page with `refresh=true`, which makes "last updated" a function
of who browsed the site rather than of any process the owner controls.

Four tasks, because the four kinds of data do not go stale at the same rate:

  fixtures   the day's matches and the next few days      - hours
  live       scores, ONLY while a covered match is in its live window - minutes
  results    finished matches, so settlement has something to score   - half hours
  recover    fixtures no refresh reaches any more, asked on a thinning retry schedule - half hours
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
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    COVERAGE_CALENDAR_KEY, MatchDataService, SyncMeta, live_polls_today, note_live_poll,
    recovery_requests_left_today, recovery_requests_today,
)
from app.services.providers import budget as request_budget
from app.services.providers import competitions as comps

logger = logging.getLogger(__name__)

#: "The caller did not say which budget store to read", kept apart from None, which means "none".
_REAL_BUDGET_STORE = object()

TASK_FIXTURES = "fixtures"
TASK_LIVE = "live"
TASK_RESULTS = "results"
TASK_RECOVER = "recover"
TASK_FORECASTS = "forecasts"
TASK_SETTLE = "settle"
#: Order matters: `settle` runs after `results` AND after `recover`, so a result ingested this
#: pass is scored in it rather than half an hour later - which is the difference between a
#: recovered final score reaching the reader's forecast now and reaching it on the next tick.
TASK_NAMES: Tuple[str, ...] = (TASK_FIXTURES, TASK_LIVE, TASK_RESULTS, TASK_RECOVER,
                               TASK_FORECASTS, TASK_SETTLE)

#: Tasks whose failure is recorded but never penalised with an exponential wait. Only the repair
#: qualifies: for a REFRESH a retry is a provider request nobody asked for, so backing off is
#: right, but the repair exists precisely to be running at the moment connectivity returns.
NO_BACKOFF_TASKS: FrozenSet[str] = frozenset({TASK_RECOVER})

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

#: Live polls made so far in one UTC day, so `SYNC_LIVE_MAX_REQUESTS_PER_DAY` can bound them.
#:
#: The live poll is the one task whose cost does not grow with the covered set - one
#: matches/live.json answers for every competition at once - and the one whose cost grows with
#: covering the world anyway, because a live window is open whenever ANY covered match is inside
#: it, and national-team fixtures are spread across every time zone there is. At the shipped
#: 120-second interval an uninterrupted day of open windows is 720 requests, which is most of the
#: plan spent on the cheapest task. This counts what has actually been spent so the ceiling can be
#: a fact rather than an assumption about how many hours of football a day holds.
LIVE_POLL_COUNT_KEY = "sync:live:polls:{day}"


def forecast_keys() -> List[str]:
    """Competitions the forecast task rotates over.

    The club set unchanged, plus any national-team competition carrying a VERIFIED forecast
    provider id - today UEFA Nations League and CONCACAF Nations League, of the 29 covered.

    A verified id is the admission ticket, rather than coverage by the match provider, because the
    two providers cover different things and the forecast plan allows 8 requests a day. A
    competition with no recorded id spends one of those discovering it has none, and 27 of those
    would spend the whole allowance for days on end without a single forecast being fetched -
    while the club competitions, which do have ids, never reached the head of the rotation.
    `ForecastService.sync_order` puts never-synced competitions first, so offering it the unpriced
    ones is precisely how the priced ones would be starved.

    A national-team competition joins this rotation on the day an id for it is verified in
    `competitions.py`, with nothing to change here.
    """
    club = comps.covered_keys(settings.COVERED_COMPETITIONS, national_setting="")
    priced = set(comps.keys_with_provider_id("gameforecast_id"))
    national = [key for key in comps.national_team_keys(
        settings.COVERED_NATIONAL_TEAM_COMPETITIONS) if key in priced]
    return club + [key for key in national if key not in club]


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
                                                   now=self._scheduler.fixed_now,
                                                   keys=forecast_keys()))
        return self._forecast


class SyncScheduler:
    """Decides what is due, runs it safely, and records what happened."""

    def __init__(self, session_factory: Optional[Callable[[], Any]] = None,
                 cache: Optional[MatchCache] = None,
                 now: Optional[Any] = None,
                 match_service_factory: Optional[Callable[[Any], MatchDataService]] = None,
                 forecast_service_factory: Optional[Callable[[Any], ForecastService]] = None,
                 tasks: Optional[Iterable[str]] = None,
                 close_sessions: bool = True,
                 budget_client: Any = _REAL_BUDGET_STORE):
        self._session_factory = session_factory
        self.cache = cache or MatchCache()
        #: The store the request budgets count in, which is where the scheduler's ledger of what it
        #: sent lives (see `status`). Not `cache`: the budgets are kept in a different Redis
        #: database, and the ledger has to sit beside the counters it is compared with.
        self._budget_client = budget_client
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
            TASK_RECOVER: settings.SYNC_RECOVERY_INTERVAL_SECONDS,
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
                error: Optional[str], started: datetime,
                sent: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        now = self.now
        state = self.state(name)
        state["last_run_at"] = now.isoformat()
        state["last_duration_ms"] = int(max((now - started).total_seconds(), 0) * 1000)
        state["runs"] = int(state.get("runs") or 0) + 1
        state["last_result"] = result
        # Per provider, every request this pass was granted - including by a pass that then raised,
        # because the provider charged those all the same.
        state["last_requests_sent"] = dict(sent or {})
        state["last_skip_reason"] = None
        if ok:
            state["last_success_at"] = now.isoformat()
            state["consecutive_failures"] = 0
            state["last_error"] = None
            state["backoff_seconds"] = None
            state["next_due_at"] = (now + timedelta(seconds=self.interval(name))).isoformat()
        else:
            failures = int(state.get("consecutive_failures") or 0) + 1
            state["failures"] = int(state.get("failures") or 0) + 1
            state["consecutive_failures"] = failures
            state["last_error_at"] = now.isoformat()
            state["last_error"] = (error or "task reported no usable data")[:MAX_ERROR_CHARS]
            if name in NO_BACKOFF_TASKS:
                # A REPAIR KEEPS ITS CADENCE THROUGH A FAILURE. The pass that reached no provider
                # is the pass a stranded fixture is waiting on, and parking it for six hours is how
                # a fixture stays wrong all night after connectivity came back. The failure is
                # still recorded in full - `last_error`, the streak, the failure count - so the
                # task appears in the health signals alongside the other five; only the penalty is
                # dropped. See `_run_recovery` for what one pass costs while an outage lasts.
                state["backoff_seconds"] = None
                state["next_due_at"] = (now + timedelta(seconds=self.interval(name))).isoformat()
                self._save_state(name, state)
                return state
            backoff = self._backoff_seconds(name, failures)
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

    # ------------------------------------------------------- what a pass may spend on coverage
    def _national_block(self, services: _Services) -> Optional[str]:
        """Why this pass must spend nothing on national-team competitions, or None.

        The club six are what this installation has always served, and this floor is the thing
        that guarantees them: once the day's remaining allowance has fallen to it, the extra
        competitions are dropped and the six are refreshed exactly as they were before any of this
        existed. It is a floor on what is LEFT rather than a share of the plan, because what it
        protects is the rest of today.

        Scaled down for a small plan the way every other guard here is, so a 10-request allowance
        is not simply told it can never cover anything. An unmetered provider cannot say the
        allowance is low, so it does not block.
        """
        if not services.match.national_keys:
            return None
        floor = max(int(settings.SYNC_NATIONAL_TEAM_BUDGET_FLOOR), 0)
        if not floor:
            return None
        low = []
        for provider in services.match.providers:
            budget = getattr(provider, "budget", None)
            try:
                limit = int(getattr(budget, "daily_limit", 0) or 0)
                if budget is None or not limit:
                    return None
                scaled = min(floor, limit // 2)
                remaining = budget.remaining()
            except Exception as exc:  # pragma: no cover - a floor is never worth a crash
                logger.debug("National-team coverage floor check failed: %s", exc)
                return None
            if remaining >= scaled:
                return None
            low.append(f"{budget.provider} ({remaining} left, floor {scaled})")
        if not low:
            return None
        return ("national-team coverage was skipped to keep the day's remaining allowance for the "
                "club competitions: " + " and ".join(low))

    def _refresh_coverage(self, service: MatchDataService,
                          blocked: Optional[str]) -> Dict[str, Any]:
        """Buy calendars for the national-team competitions whose stored one has expired.

        One request each, stalest first, at most `SYNC_COVERAGE_CALENDAR_REFRESH_PER_PASS` of them.
        This is the step that makes an international break need no settings change: a competition
        that was dormant when it was last read comes back with fixture days on it, and every
        selection below starts including it on those days from this same pass onwards.

        `requests` is an upper bound - a calendar still inside its own short cache costs nothing -
        and the per-provider calendar ceiling in `match_data_service` bounds it besides.
        """
        if blocked:
            return {"refreshed": {}, "requests": 0, "skipped": blocked}
        limit = max(int(settings.SYNC_COVERAGE_CALENDAR_REFRESH_PER_PASS), 0)
        due = service.coverage_refresh_due(limit)
        refreshed: Dict[str, Any] = {}
        for key in due:
            record = service.refresh_coverage_calendar(key)
            refreshed[key] = {"answered": bool(record.get("answered")),
                              "next_kickoff": record.get("next_kickoff"),
                              "fixture_days": record.get("fixture_days") or [],
                              "refresh_after": record.get("refresh_after"),
                              "error": record.get("error")}
        return {"refreshed": refreshed, "requests": len(due)}

    @staticmethod
    def _fixture_plan(service: MatchDataService, today, days: int, national: bool
                      ) -> Tuple[List[Tuple[Any, List[str]]], int, List[str]]:
        """(day, competitions) per day in the window, plus what the cap deferred.

        The club competitions go into every day unconditionally. That is a MEMBERSHIP rule and not
        a priority ordering, so no cap applied afterwards can reach them: the cap counts only the
        national-team extras, and a pass that defers all of them still asks for the same six
        competitions on the same three days it asks for today.

        The days are filled in order, so a cap that binds costs the furthest day rather than the
        nearest - a fixture the day after tomorrow has two more passes to be picked up in, and one
        today has none.
        """
        cap = max(int(settings.SYNC_FIXTURES_MAX_NATIONAL_REQUESTS_PER_PASS), 0)
        club = list(service.club_keys)
        club_set = set(club)
        plan: List[Tuple[Any, List[str]]] = []
        deferred: List[str] = []
        spent = 0
        for offset in range(days):
            day = today + timedelta(days=offset)
            extra: List[str] = []
            if national:
                for key in service.coverage_keys_for_day(day):
                    if key in club_set:
                        continue
                    if spent < cap:
                        extra.append(key)
                        spent += 1
                    else:
                        deferred.append(f"{key}@{day.isoformat()}")
            plan.append((day, club + extra))
        return plan, spent, deferred

    @staticmethod
    def _results_order(service: MatchDataService, pending: Sequence[str], turn: int) -> List[str]:
        """Competitions to poll for results, most protected first.

        Clubs lead, in registry order, so the cap can never take a request from one of them. The
        national-team competitions behind them are rotated by the pass number, so a cap that binds
        cuts a different one each pass instead of the same tail every half hour for ever.
        """
        club_set = set(service.club_keys)
        clubs = [key for key in pending if key in club_set]
        national = [key for key in pending if key not in club_set]
        if national:
            offset = int(turn) % len(national)
            national = national[offset:] + national[:offset]
        return clubs + national

    # --------------------------------------------------------------- the live task's daily cap
    # The counter itself belongs to MatchDataService, which is where the requests are made and
    # which the fixtures task also polls through. Two counters would be two ceilings, and the
    # lower one would be the only one anybody could see.
    def _live_polls_today(self) -> int:
        return live_polls_today(self.cache, self.now)

    def _note_live_poll(self) -> None:
        note_live_poll(self.cache, self.now)

    # ------------------------------------------------------------------ the tasks
    def _run_fixtures(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        service = services.match
        days = max(int(settings.SYNC_FIXTURES_DAYS_AHEAD), 1)
        today = service.now.date()
        # The previous pass's own summary is the only record of how long this has been quiet; it is
        # carried forward below rather than kept in a second key that could disagree with it.
        #
        # That ties both streaks to that summary surviving. It is absent whenever the task raised
        # (`_maybe_run` records `last_result=None`), whenever the state entry has passed its
        # STATE_TTL_SECONDS, and on every pass when Redis is unavailable, since the cache read then
        # returns None and the save is a no-op. In each of those the streaks restart at 0 and the
        # sighting falls back to `_carry_last_seen`'s reconstruction. They count passes since the
        # last stored summary, not passes since the last fixture.
        previous = self.state(TASK_FIXTURES).get("last_result") or {}
        out: Dict[str, Any] = {"days": {}, "errors": []}
        # Calendars first, then the selection that reads them, so a break that begins between two
        # passes is discovered and acted on inside the SAME pass rather than six hours later.
        national_blocked = self._national_block(services)
        out["coverage"] = self._refresh_coverage(service, national_blocked)
        plan, national_requests, deferred = self._fixture_plan(
            service, today, days, national=national_blocked is None)
        out["club_competitions"] = len(service.club_keys)
        out["national_competitions_covered"] = len(service.national_keys)
        out["national_requests"] = national_requests
        out["national_deferred"] = deferred[:MAX_STORED_ERRORS]
        if national_blocked:
            out["national_skipped"] = national_blocked
        got_data = False
        seen = stored = forward_seen = forward_stored = 0
        answered = from_stale = unanswered = 0
        offered_at: List[datetime] = []
        for day, keys in plan:
            meta = service.sync_day(day, keys=keys)
            out["days"][day.isoformat()] = {**meta.to_dict(), "competitions": len(keys)}
            out["errors"].extend(meta.errors)
            seen += meta.fixtures_seen
            stored += meta.fixtures_stored
            forward_seen += meta.forward_fixtures_seen
            forward_stored += meta.forward_fixtures_stored
            if meta.forward_source in ("provider", "cache"):
                answered += 1
                if meta.forward_fixtures_seen:
                    # Time the sighting by when the answer was fetched, not by when this pass read
                    # it: a cache hit is a provider answer from up to MATCH_CACHE_TTL_FIXTURES ago.
                    offered_at.append(_parse(meta.forward_fetched_at) or self.now)
            elif meta.forward_source == "stale-cache":
                from_stale += 1
            else:
                unanswered += 1
            if meta.source != "database":
                got_data = True
        out["errors"] = _clip(out["errors"])
        out["days_requested"] = days
        out["fixtures_seen"] = seen
        out["fixtures_stored"] = stored
        out["forward_seen"] = forward_seen
        out["forward_stored"] = forward_stored
        out["days_answered"] = answered
        out["days_from_stale_cache"] = from_stale
        out["days_unanswered"] = unanswered
        # Reaching the provider is not the same as being given a fixture: an empty answer and a
        # full matchday both write `source="provider"` with no errors, and neither field tells
        # them apart. Hence the counts - but only the FORWARD list answers "did the provider hand
        # back a fixture for a day we asked about". One `sync_day` runs three ingests through the
        # same counters (the forward list, then results, then live scores), and one unsettled
        # match dated today that has already kicked off - or kicks off within the next quarter of
        # an hour - makes the other two hand back a day of fixtures on a pass whose forward list
        # came back empty, so `fixtures_seen` cannot be read for this.
        #
        # `forward_answer` summarises the whole pass in one word, and a sighting outranks an
        # outage:
        #
        #   fixtures      at least ONE day was offered a forward fixture, in an answer fetched for
        #                 this pass or still inside its cache TTL. Both streaks reset. This says
        #                 nothing about the other days: a three-day pass where today answers and
        #                 the other two raise lands here too, and the two dead days show up only
        #                 in `days_unanswered` / `days_from_stale_cache` beside it. Read those
        #                 counts, not this word, to see whether every day was answered.
        #   empty         no day was offered a forward fixture, and every day asked was answered.
        #                 A league between rounds genuinely has none, so this stays a success -
        #                 but the run of them is counted, because a dead forward path looks the
        #                 same from here.
        #   not_answered  no day was offered a forward fixture, and at least one fell back to the
        #                 24-hour stale copy or got no answer at all. Nothing was learned about
        #                 the calendar, so `empty_passes` is left exactly where it was rather than
        #                 advanced - an outage must not read as a quiet week - and it gets a
        #                 streak of its own instead.
        #
        # What none of this does is decide that something is wrong. These are two streaks and a
        # timestamp on the status page; judging them is still a person's job.
        if offered_at:
            out["forward_answer"] = "fixtures"
            out["last_seen_at"] = max(offered_at).isoformat()
            out["last_seen_basis"] = "sync_pass"
            out["empty_passes"] = out["unanswered_passes"] = 0
        else:
            out["last_seen_at"], out["last_seen_basis"] = self._carry_last_seen(previous, service)
            if from_stale or unanswered:
                out["forward_answer"] = "not_answered"
                out["empty_passes"] = int(previous.get("empty_passes") or 0)
                out["unanswered_passes"] = int(previous.get("unanswered_passes") or 0) + 1
            else:
                out["forward_answer"] = "empty"
                out["empty_passes"] = int(previous.get("empty_passes") or 0) + 1
                out["unanswered_passes"] = 0
        error = None if got_data else "; ".join(out["errors"]) or "no fixture data could be obtained"
        return out, got_data, error

    @staticmethod
    def _carry_last_seen(previous: Dict[str, Any],
                         service: MatchDataService) -> Tuple[Optional[str], Optional[str]]:
        """(when a fixture was last seen, what that timestamp is), for a pass offered none.

        Normally the previous pass's answer, carried forward. When no stored summary carries one
        there is still something knowable - the newest match row written before its own kickoff.
        Without it a pass reports that no fixture has ever been seen on an installation whose
        table is full of rows written days ahead of their kickoff, which reads as a broken
        integration rather than as the calendar gap that is actually there.

        "No stored summary" is not only the first pass ever. The summary is also gone after a pass
        that raised, after the state entry passes its TTL, and on every pass while Redis is
        unavailable - so this reconstruction can reappear long after a real sighting, and the
        basis is the only thing that keeps the two apart.

        The basis travels with the timestamp so they are never confused: "sync_pass" is a fixture
        this task was handed, "matches_table" is the row above, and None means no fixture sighting
        is recorded and none could be reconstructed.
        """
        carried = previous.get("last_seen_at")
        if carried:
            # A stored summary carrying a timestamp but no basis was written by a pass that was
            # handed a fixture - nothing else writes one - so it is attributed to one.
            return carried, previous.get("last_seen_basis") or "sync_pass"
        stored_at = None
        try:
            stored_at = service.last_forward_fixture_stored_at()
        except Exception:  # a seed for a report must never fail the pass that reports it
            logger.debug("Could not seed the last-seen fixture time", exc_info=True)
        if not isinstance(stored_at, datetime):
            return None, None
        return stored_at.isoformat(), "matches_table"

    def _run_results(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        service = services.match
        lookback = max(int(settings.SYNC_RESULTS_LOOKBACK_DAYS), 0)
        today = service.now.date()
        cap = max(int(settings.SYNC_RESULTS_MAX_REQUESTS_PER_PASS), 0)
        # The pass number the rotation turns on. `runs` counts every pass this task has recorded,
        # so it advances once per pass whatever happened in it.
        turn = int(self.state(TASK_RESULTS).get("runs") or 0)
        out: Dict[str, Any] = {"days": {}, "errors": [], "polled": False,
                               "requests": 0, "deferred": []}
        spent = 0
        # EVERY DAY GETS A SHARE, because a cap spent in day order is a cap that starves the older
        # days entirely. Walking today first with one running budget means a busy today - and 35
        # competitions makes today busy - takes the whole cap on every pass, so yesterday's stuck
        # match is never asked about again by any of the 48 passes in a day, and never settles.
        # Older days are also the ones that will not fix themselves: today's fixture will be asked
        # about again in half an hour anyway.
        days = [today - timedelta(days=offset) for offset in range(lookback + 1)]
        share = max(cap // len(days), 1) if cap else 0
        for index, day in enumerate(days):
            # The last day sweeps up whatever the earlier ones did not want, so an integer division
            # never quietly leaves part of the allowance unused.
            allowance = (cap - spent) if index == len(days) - 1 else share
            # A day costs one request per competition that still holds an unsettled match on it,
            # and nothing at all for the competitions that do not. That is the difference between
            # 3,360 requests a day at 35 competitions and the handful a matchday actually needs.
            # Of those, only the ones the retry schedule says are due are asked: a match under six
            # hours past kickoff is due every pass, an older one ever more rarely (RETRY_SCHEDULE).
            wanted = self._results_order(service, service.due_result_keys(day), turn)
            take = wanted[:max(allowance, 0)] if cap else []
            out["deferred"].extend(f"{key}@{day.isoformat()}" for key in wanted[len(take):])
            meta = SyncMeta()
            if take:
                service._sync_results(day, meta, keys=take)
                spent += len(take)
            out["days"][day.isoformat()] = {**meta.to_dict(), "competitions": len(take)}
            out["errors"].extend(meta.errors)
            out["polled"] = out["polled"] or meta.results_polled
        out["requests"] = spent
        out["deferred"] = out["deferred"][:MAX_STORED_ERRORS]
        out["errors"] = _clip(out["errors"])
        ok = not out["errors"]
        return out, ok, "; ".join(out["errors"]) or None

    def _run_live(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        service = services.match
        if not service._live_window_open():
            # The single most expensive mistake available here is polling live scores all night.
            return ({"live_window_open": False, "live_polled": False, "polls_today": self._live_polls_today(),
                     "note": "no covered match is in its live window; no provider request made"},
                    True, None)
        # The second expensive mistake is polling all day. One poll answers for every competition
        # at once, so this bounds HOURS rather than coverage: no competition is served in
        # preference to another by it, and the day it binds is a day whose live windows have run
        # for fourteen hours, which no club matchday does.
        cap = max(int(settings.SYNC_LIVE_MAX_REQUESTS_PER_DAY), 0)
        polled_today = self._live_polls_today()
        if cap and polled_today >= cap:
            return ({"live_window_open": True, "live_polled": False, "polls_today": polled_today,
                     "note": f"the day's live-poll ceiling is reached ({polled_today}/{cap}); "
                             f"polling resumes at the UTC reset"},
                    True, None)
        meta = SyncMeta()
        service._sync_live(meta)
        # Only a request is counted, and every request is: a poll that went out and failed was
        # charged by the provider exactly like an answered one, so it counts against the ceiling
        # too. A poll served from the 60-second live cache, or refused before it left, spent
        # nothing, and charging it would stop the day early over requests that never happened.
        if meta.requests > 0:
            self._note_live_poll()
        out = {"live_window_open": True, **meta.to_dict(), "polls_today": self._live_polls_today()}
        out["errors"] = _clip(out["errors"])
        ok = not out["errors"]
        return out, ok, "; ".join(out["errors"]) or None

    def _run_recovery(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        """Go and get the final scores nothing else will, unattended and inside a stated bound.

        THE HOLE THIS FILLS. The live poll considers a match for 150 minutes after kickoff - this
        application's polling window - and the results task looks back `SYNC_RESULTS_LOOKBACK_DAYS`
        days. A match whose result did not arrive inside both sat reading "LIVE, HT" until somebody
        ran `scripts/repair_unsettled_matches.py`. This is that sweep, on a clock: see
        `MatchDataService.recover_stranded` for what it asks, when, and what it concludes.

        WHAT IS A FAILURE. A pass fails when a request it sent was not answered (`failed_calls`):
        that is an outage, and it must show as one. A pass whose calls were answered is a healthy
        pass however little came back - "the archive returned no rows for that date" is what the
        call observed, recorded per competition and date, and not a fault here. It says what the
        archive answered when asked, not why, and not whether it will ever answer otherwise. A call that
        never left - refused by an allowance, or skipped while the provider cools down after a
        failure - is a deferral and not a failure: nothing was unreachable. A pass with nothing due
        makes no call and is a success with nothing to say.

        A FAILED PASS DOES NOT BACK OFF, and this is the one place in this module where that is
        true. `_record` backs a failing task off exponentially, up to six hours, because a retry is
        a provider request nobody asked for. For a repair that reasoning inverts: the pass that
        reaches no provider is the pass a stranded fixture is waiting on, and parking it for six
        hours is how a fixture stays wrong all night after connectivity came back - which is what
        happened on 2026-09-24, when backoff pushed the results task to a two-hour wait and the
        live task past 22:30. So `NO_BACKOFF_TASKS` holds this task and only this task. The failure
        is still recorded in full (`last_error`, the streak), so an outage lasting a week does not
        read on the status endpoint like a week with nothing to repair.

        WHAT NOT BACKING OFF COSTS. During an outage the provider cool-down `_call_chain` sets
        after a failure (two minutes) turns every later call in the same pass into a skip, so a
        pass makes about one real request, and a failed call does not move the retry schedule. That
        one request is charged: to the recovery task's daily ceiling when it was a results request,
        to the live ceiling when it was the poll, so an outage that lasts all day ends at those
        ceilings rather than running past them. `_budget_block` and `RequestBudget` bound it besides.

        A pass that RAISES is still a failure: `_maybe_run` catches it and backs off, which is
        what should happen to a bug.
        """
        service = services.match
        report = service.recover_stranded()
        report["requests"] = int(report.get("results_requests") or 0) + int(report.get("live_requests") or 0)
        report["recovery_requests_today"] = self._recovery_requests_today()
        report["errors"] = _clip(report.get("errors") or [])
        report["failed_calls"] = _clip(report.get("failed_calls") or [])
        report["deferred"] = list(report.get("deferred") or [])[:MAX_STORED_ERRORS]
        # The per-fixture detail is the part that grows without bound, and `status()` publishes
        # `last_result` on every call. The counts and the deferrals are kept; the roll-call is
        # trimmed to the fixtures a reader would act on.
        report["fixtures"] = list(report.get("fixtures") or [])[:MAX_STORED_ERRORS]
        if report["failed_calls"]:
            return report, False, ("reached no provider on " + str(len(report["failed_calls"]))
                                   + " call(s): " + "; ".join(report["failed_calls"]))
        return report, True, None

    def _recovery_requests_today(self) -> int:
        return recovery_requests_today(self.cache, self.now)

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
        since = now - timedelta(days=lookback)
        db = self._db_of(services)
        service = SettlementService(db)
        report = service.settle_range(start=since, end=now, commit=False)
        # A RESULT CAN ARRIVE LATER THAN THE WINDOW ABOVE LOOKS BACK. The recovery sweep keeps
        # asking for up to `RETRY_HORIZON` after kickoff, so a final score recovered on day five
        # belongs to a match this range no longer includes and would be stored and never scored.
        # Those matches are added here - only the ones the sweep settled inside the same window -
        # through the same idempotent `settle_match` the range uses.
        late = services.match.registry.recovered_since(since, kicked_off_before=since)
        for match in late:
            service.settle_match(match, report)
        report["late_recoveries"] = [str(m.id) for m in late]
        db.flush()
        db.commit()
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
            TASK_RECOVER: self._run_recovery,
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
                # Every request granted on this thread until the block ends is this task's, whichever
                # provider object grants it - see `request_budget.spending_for_task`.
                with request_budget.spending_for_task(name) as spend:
                    result, ok, error = self._execute(name, services)
            except Exception as exc:  # a broken task must not stop the other three, or the loop
                logger.exception("Sync task %s failed", name)
                state = self._record(name, result=None, ok=False, error=str(exc), started=started,
                                     sent=spend.granted)
                return {"ran": True, "ok": False, "error": str(exc),
                        "next_due_at": state.get("next_due_at"),
                        "consecutive_failures": state.get("consecutive_failures")}
            state = self._record(name, result=result, ok=ok, error=error, started=started,
                                 sent=spend.granted)
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
    def estimate(self, only: Optional[Iterable[str]] = None, force: bool = False) -> Dict[str, Any]:
        """What a pass would do and what it would cost. Makes no provider request.

        `force` means the same thing here as in `run_once`: the interval is ignored, the budget
        ceiling is not. It has to be passed in for the estimate to describe the pass the caller is
        actually about to make — an estimate of the unforced pass, printed in answer to a forced
        one, reports a task as skipped and then prices the work it is about to do anyway.
        """
        names = self._selected(only)
        report: Dict[str, Any] = {"estimated_at": self.now.isoformat(), "tasks": {},
                                  "total_requests": 0, "forced": force}
        if not names:
            report["note"] = "no sync task is enabled"
            return report
        db = self._open_session()
        services = _Services(self, db)
        try:
            for name in names:
                entry = self._estimate_task(name, services, force=force)
                report["tasks"][name] = entry
                if entry.get("would_run"):
                    report["total_requests"] += int(entry.get("estimated_requests") or 0)
        finally:
            self._close_session(db)
        return report

    def _estimate_task(self, name: str, services: _Services, force: bool = False) -> Dict[str, Any]:
        is_due, why = self.due(name)
        budget = self._budget_of(services, name)
        entry: Dict[str, Any] = {
            "due_now": is_due,
            "reason_not_due": why,
            # Whether the interval was overridden, kept beside `due_now` rather than folded into
            # it: a reader has to be able to see both that the task was not due and that it will
            # run regardless.
            "forced": force,
            "interval_seconds": self.interval(name),
            "provider": getattr(budget, "provider", None),
            "budget_remaining": budget.remaining() if budget is not None else None,
        }
        blocked = self._budget_block(services, name)
        entry["blocked"] = blocked
        entry["would_run"] = bool((is_due or force) and not blocked)
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
        if name == TASK_FIXTURES:
            days = max(int(settings.SYNC_FIXTURES_DAYS_AHEAD), 1)
            blocked = self._national_block(services)
            # The estimate prices the plan the pass would actually make, competition by
            # competition, rather than multiplying the covered set by the window. The two answers
            # differ by a factor of five once national-team coverage is on, and the estimate is
            # the number somebody reads before running this against a trial plan.
            plan, national, _ = self._fixture_plan(service, service.now.date(), days,
                                                   national=blocked is None)
            fixtures = sum(len(keys) for _, keys in plan)
            rotation = len(service.coverage_refresh_due(
                0 if blocked else max(int(settings.SYNC_COVERAGE_CALENDAR_REFRESH_PER_PASS), 0)))
            basis = (f"{len(service.club_keys)} club competition(s) x {days} day(s) = "
                     f"{len(service.club_keys) * days}, plus {national} national-team "
                     f"competition-day(s) whose calendar says they play, plus {rotation} "
                     f"calendar refresh(es)")
            if blocked:
                basis += f"; national-team coverage is held back ({blocked})"
            return fixtures + rotation, basis
        if name == TASK_LIVE:
            if not service._live_window_open():
                return 0, "no covered match is in its live window"
            cap = max(int(settings.SYNC_LIVE_MAX_REQUESTS_PER_DAY), 0)
            polled = self._live_polls_today()
            if cap and polled >= cap:
                return 0, f"the day's live-poll ceiling is reached ({polled}/{cap})"
            return 1, ("1 request (matches/live.json covers every competition at once); "
                       f"{polled} poll(s) made today of at most {cap or 'unbounded'}")
        if name == TASK_RECOVER:
            plan = service.recovery_plan()
            if not plan["stranded"]:
                return 0, "no fixture is stranded; a recovery pass makes no request"
            if not plan["due"]:
                return 0, (f"{len(plan['stranded'])} stranded fixture(s), none due an ask under the "
                           f"retry schedule; a recovery pass makes no request")
            left = recovery_requests_left_today(self.cache, self.now)
            per_pass = max(int(settings.SYNC_RECOVERY_MAX_REQUESTS_PER_PASS), 0)
            allowance = per_pass if left is None else min(per_pass, left)
            results = min(plan["results_requests"], allowance)
            live_left = bool(plan["live_requests"])
            basis = (f"{len(plan['stranded'])} stranded fixture(s), {len(plan['due'])} due under "
                     f"the retry schedule, over {len(plan['days'])} day(s) behind the results "
                     f"lookback: {results} results request(s) of the {plan['results_requests']} "
                     f"they want, capped at {allowance} left to this pass")
            if live_left:
                basis += ("; plus 1 live poll, charged to the live task's daily ceiling rather "
                          "than added beside it")
            else:
                basis += "; the live poll is refused, the day's live ceiling being reached"
            # The live poll is priced here because it IS a request this pass would make, even
            # though it is billed to another task's ceiling. An estimate that left it out would
            # under-report the pass, which is the one direction an estimate must not err in.
            return results + (1 if live_left else 0), basis
        lookback = max(int(settings.SYNC_RESULTS_LOOKBACK_DAYS), 0)
        cap = max(int(settings.SYNC_RESULTS_MAX_REQUESTS_PER_PASS), 0)
        today = service.now.date()
        spent, days_with_work, deferred = 0, 0, 0
        for offset in range(lookback + 1):
            pending = service.due_result_keys(today - timedelta(days=offset))
            if pending:
                days_with_work += 1
            take = min(len(pending), max(cap - spent, 0)) if cap else 0
            spent += take
            deferred += len(pending) - take
        basis = (f"1 request per competition holding an unsettled match the retry schedule "
                 f"says is due: {spent} over {days_with_work} day(s) with work, capped at {cap} "
                 f"a pass")
        if deferred:
            basis += f"; {deferred} deferred to the next pass by that cap"
        return spent, basis

    # ------------------------------------------------------------------ status
    def coverage_status(self) -> Dict[str, Any]:
        """What is covered and how much of it has a calendar yet. Reads Redis; no database.

        A national-team competition with no calendar read yet is not being asked about, so the two
        counts have to be reported apart: "29 covered" alone would claim a coverage the scheduler
        is not yet providing, and the gap between them is exactly how far through its first
        rotation this installation is.
        """
        club = comps.covered_keys(settings.COVERED_COMPETITIONS, national_setting="")
        national = comps.national_team_keys(settings.COVERED_NATIONAL_TEAM_COMPETITIONS)
        now = self.now
        with_calendar = playing_soon = 0
        soonest: Optional[str] = None
        for key in national:
            record = self.cache.get(COVERAGE_CALENDAR_KEY.format(key=key))
            if not isinstance(record, dict) or not record.get("answered"):
                continue
            with_calendar += 1
            kickoff = _parse(record.get("next_kickoff"))
            if kickoff is None:
                continue
            if kickoff - now <= timedelta(days=settings.SYNC_FIXTURES_DAYS_AHEAD):
                playing_soon += 1
            if soonest is None or record["next_kickoff"] < soonest:
                soonest = record["next_kickoff"]
        return {
            "club_competitions": len(club),
            "national_team_competitions": len(national),
            "national_setting": settings.COVERED_NATIONAL_TEAM_COMPETITIONS,
            "national_with_calendar": with_calendar,
            "national_playing_inside_the_fixture_window": playing_soon,
            "next_national_kickoff": soonest,
            "calendar_refresh_per_pass": int(settings.SYNC_COVERAGE_CALENDAR_REFRESH_PER_PASS),
            "live_polls_today": self._live_polls_today(),
            "live_polls_per_day_ceiling": int(settings.SYNC_LIVE_MAX_REQUESTS_PER_DAY),
            # Published beside the live counter because the recovery pass spends out of BOTH: its
            # results requests out of this one, its live poll out of the one above. Two numbers,
            # because one of them is the recovery task's own ceiling and the other is not.
            "recovery_requests_today": self._recovery_requests_today(),
            "recovery_requests_per_day_ceiling": int(settings.SYNC_RECOVERY_MAX_REQUESTS_PER_DAY),
        }

    def status(self) -> Dict[str, Any]:
        enabled = self.enabled_tasks()
        payload: Dict[str, Any] = {
            "enabled": bool(settings.SYNC_SCHEDULER_ENABLED),
            "running": is_running(),
            "tick_seconds": max(int(settings.SYNC_SCHEDULER_TICK_SECONDS), 5),
            "startup_delay_seconds": max(int(settings.SYNC_SCHEDULER_STARTUP_DELAY_SECONDS), 0),
            "budget_reserve": int(settings.SYNC_SCHEDULER_BUDGET_RESERVE),
            "enabled_tasks": enabled,
            "coverage": self.coverage_status(),
            # Due-times and history live in Redis. Without it the scheduler still runs, but it cannot
            # remember when a task last ran, so freshness here would be a guess. Say so.
            "state_store_available": self.cache.available,
            "tasks": {},
        }
        ledger = self._requests_ledger()
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
                # Per provider, what the last pass that ran was granted. None for a task whose last
                # pass was recorded before this was kept.
                "last_requests_sent": state.get("last_requests_sent"),
                # Per provider, everything this task has sent since the ledger began: a running
                # total that only grows. It is written with the budget counter it is compared with,
                # at the instant each request is granted, so it is never behind a pass still in
                # flight. None when the ledger cannot be read - unknown, not zero.
                "requests_sent_total": (None if ledger is None else
                                        {provider: tasks[name] for provider, tasks in ledger.items()
                                         if name in tasks}),
            }
        return payload

    def _requests_ledger(self) -> Optional[Dict[str, Dict[str, int]]]:
        """{provider: {task: requests sent}} from the budget store, or None when it is unreadable."""
        if self._budget_client is None:
            return None
        if self._budget_client is _REAL_BUDGET_STORE:
            return request_budget.read_scheduler_sent()
        return request_budget.read_scheduler_sent(self._budget_client)

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
