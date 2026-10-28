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
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.services.forecast_service import (
    PASS_COMPLETED as FORECAST_PASS_COMPLETED, PASS_DEFERRED as FORECAST_PASS_DEFERRED,
    PASS_FAILED as FORECAST_PASS_FAILED, PASS_PARTIAL as FORECAST_PASS_PARTIAL, ForecastService,
)
from app.services.match_cache import MatchCache
from app.services.match_data_service import (
    CALL_CACHE, CALL_DEFERRED, CALL_FAILED, CALL_FRESH, CALL_STALE, COVERAGE_CALENDAR_KEY,
    MatchDataService, SyncMeta, call_outcome, live_polls_today, note_live_poll,
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
#: A forecasts pass that stopped for a reason of COORDINATION rather than of the provider - its sync
#: lease lost mid-pass, or found held by another worker when the pass came due - is retried on a
#: short, bounded schedule instead of being backed off like a failure. On 2026-10-24 the lease was
#: lost after one of five competitions (most likely because the Redis server's clock, in Docker
#: Desktop's VM, had stood still through two host sleeps and was stepped forward past the lease's
#: term seconds after the wake - an inference from Redis's own save log, see
#: docs/evidence/forecast-recovery-2026-10-24/REPORT.md), the pass was recorded as a failure, and the
#: ordinary backoff - the task's own
#: six-hour interval - left the other four competitions unfetched until 18:10 UTC: eleven fixtures
#: kicked off in the gap on the previous day's forecasts, with the allowance at 5 of 8. Nothing a
#: retry could buy twice was at stake: the daily-slot policy keeps the slot of every competition the
#: interrupted pass did fetch, so a retry buys only what is still owed.
#:
#: The first wait is one lease term, because by then a lease nobody renews has lapsed; each further
#: wait doubles; after FORECASTS_RECOVERY_MAX_RETRIES in one episode the ordinary backoff applies. A
#: retry that finds the provider paused waits for the pause instead (`paused_until`); one that finds
#: the allowance spent is skipped exactly as any pass is. A provider's failure is not an
#: interruption and keeps its backoff: a retry after one is a request nobody asked for, and it may
#: fail again. The retry buys the turns the interrupted pass owed and leaves the day's re-check of
#: an older run to the ordinary pass (`ForecastService.ensure_synced(recovery=True)`). Unlike the
#: ordinary waits, a retry is not pulled forward to the budget reset: the reset gives back an
#: allowance, not a reason to retry sooner than the minimum or before a provider's pause has ended,
#: and what the new day may buy is decided by the eligibility rules as ever. The episode lives in
#: the task's state in Redis and spans midnight and restarts, so neither resets its count nor
#: repeats finished work.
FORECASTS_RECOVERY_RETRY_SECONDS = 300
FORECASTS_RECOVERY_MAX_RETRIES = 3
FORECAST_PASS_OUTCOMES: FrozenSet[str] = frozenset({FORECAST_PASS_COMPLETED, FORECAST_PASS_PARTIAL,
                                                     FORECAST_PASS_DEFERRED, FORECAST_PASS_FAILED})

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


def parse_slot_anchor(value: Any) -> Optional[time]:
    """"HH:MM" (UTC) as a time, or None for anything else: the grid is then undefined and the task
    waits its interval from completion, as it always did."""
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def forecast_slot_after(instant: datetime, anchor: Optional[time], interval_seconds: int) -> Optional[datetime]:
    """The first ordinary forecasts slot strictly after `instant`, on the grid `anchor` + k * interval.

    The grid repeats daily only when the interval divides a day (6 h does; 7 h would not), so any
    other interval has no grid and the caller falls back to counting from completion. Strictly after:
    a pass that started exactly on its slot is followed by the next one, never by itself.
    """
    if anchor is None or interval_seconds <= 0 or 86400 % interval_seconds:
        return None
    instant = instant.astimezone(timezone.utc) if instant.tzinfo else instant.replace(tzinfo=timezone.utc)
    step = timedelta(seconds=interval_seconds)
    slot = datetime.combine(instant.date() - timedelta(days=1), anchor, tzinfo=timezone.utc)
    while slot <= instant:
        slot += step
    return slot


def _next_budget_reset(now: datetime) -> datetime:
    """Both providers count per UTC day, so their allowances come back at UTC midnight.

    A minute of slack keeps a clock a hair ahead of the provider's from asking before the reset.
    """
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(minutes=1)


# ------------------------------------------------- what a pass is judged by: what answered
#: The live and results passes are judged by what each of their calls was actually SERVED
#: (`match_data_service.CALL_*`, classified from the answer's source), never by the chain's error
#: list: `_call_chain` records every provider it gave up on before the one that answered, so a
#: fallback's answer arrives with the primary's error beside it. Judged by "any error", the pass
#: that was served failed - on 2026-10-18 a Live Score timeout answered by API-Football, live
#: scores stored, still failed the live task and backed it off BACKOFF_MIN_SECONDS: a five-minute
#: live gap on a matchday over an answer that had arrived.
#:
#: Three outcomes fail a pass. `failed`: a request went out, nobody answered, nothing was served.
#: `stale`: nothing answered and the stale copy stood in - the outage is as real and backing off
#: from it is as right. `deferred`: a call the pass wanted was held back by an allowance or a
#: provider's cool-down, so the pass did not get what it came for; that keeps the verdict such a
#: pass always had, and `_record` already clamps its backoff to the next budget reset. What does
#: NOT fail a pass: `fresh` and `cache`, which are the pass being served (an empty answer is an
#: answer); `not_asked`, a question no provider in the chain can take - a gap in coverage that the
#: next pass cannot change, which the chain already keeps out of `errors` for that reason; and a
#: pass with no call to judge (nothing due, no live window, the ceiling reached), which is a
#: success with nothing to say. The verdict is over EVERY call of the pass, so one competition
#: answered cannot hide another that was not, and the report says which ended how.
PASS_FAILING_OUTCOMES: FrozenSet[str] = frozenset({CALL_FAILED, CALL_STALE, CALL_DEFERRED})
#: The pass-level words beside the per-call ones: `partial` when its calls ended differently
#: (`by_outcome` says which ended how), `skipped` when there was no call to judge.
PASS_PARTIAL = "partial"
PASS_SKIPPED = "skipped"


def forecast_pass_outcome(result: Optional[Dict[str, Any]], ok: bool) -> str:
    """How a forecasts pass ended: as its own report says (`ForecastService` states `outcome`), or,
    for a report that does not, from the verdict and the lease flags it has always carried."""
    if isinstance(result, dict):
        said = result.get("outcome")
        if said in FORECAST_PASS_OUTCOMES:
            return said
        if ok:
            return FORECAST_PASS_COMPLETED
        if result.get("lease_lost"):
            return FORECAST_PASS_PARTIAL
        if result.get("lease_held"):
            return FORECAST_PASS_DEFERRED
        return FORECAST_PASS_FAILED
    return FORECAST_PASS_COMPLETED if ok else FORECAST_PASS_FAILED


def _pass_outcome(calls: Dict[str, Dict[str, Any]]) -> str:
    ended = {str(record.get("outcome")) for record in calls.values()}
    if not ended:
        return PASS_SKIPPED
    return ended.pop() if len(ended) == 1 else PASS_PARTIAL


def _by_outcome(calls: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """Which calls ended which way, so one answered competition cannot hide another's failure."""
    grouped: Dict[str, List[str]] = {}
    for name, record in calls.items():
        grouped.setdefault(str(record.get("outcome")), []).append(name)
    return grouped


def _verdict(calls: Dict[str, Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """(ok, why not) over every call of the pass: ok unless one ended in PASS_FAILING_OUTCOMES."""
    failing = [(name, record) for name, record in calls.items()
               if record.get("outcome") in PASS_FAILING_OUTCOMES]
    if not failing:
        return True, None
    said = []
    for name, record in failing[:MAX_STORED_ERRORS]:
        detail = record.get("detail")
        said.append(f"{name}: {record['outcome']}" + (f" ({detail})" if detail else ""))
    return False, "; ".join(said)


def _diagnostics(metas: Iterable[SyncMeta]) -> Dict[str, Any]:
    """What the chain met on the way, kept beside the verdict and never inside it.

    `provider_errors` is every request that went out and got no usable answer - the primary's
    timeout on a pass the fallback answered lives here, and on that provider's own status record
    (`MatchDataService._record_status`), not in the task's failure verdict. `not_sent` and
    `declined` are why providers were passed over without a request. The report's `errors` keeps
    the chain's flat list exactly as it always was.
    """
    provider_errors: List[str] = []
    not_sent: List[str] = []
    declined: List[str] = []
    request_failed = False
    for meta in metas:
        for failure in meta.failed_requests:
            if failure not in provider_errors:
                provider_errors.append(failure)
        not_sent.extend(meta.not_sent)
        for decline in meta.declined:
            if decline not in declined:
                declined.append(decline)
        request_failed = request_failed or meta.request_failed
    return {"provider_errors": _clip(provider_errors), "not_sent": not_sent[:MAX_STORED_ERRORS],
            "declined": _clip(declined), "request_failed": request_failed}


def _clipped_call(record: Dict[str, Any]) -> Dict[str, Any]:
    """A call's record with its detail cut to MAX_ERROR_CHARS, like every message the stored
    summary carries: the status endpoint reads it on every call."""
    detail = record.get("detail")
    return {**record, "detail": str(detail)[:MAX_ERROR_CHARS] if detail else None}


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
        """(due now, why not). A task that has never run on this installation is due - except the
        forecasts task under the `elapsed-interval` refresh policy before
        `SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR`: one dated model run a day has been OBSERVED from the
        provider, obtained at 12:xx and 18:xx UTC and never at 00:xx, and a pass before it buys
        yesterday's forecasts with today's request. Under `daily-slot` the task is offered every
        pass and the policy decides inside it, from the hour it has observed, whether anything is
        eligible (`ForecastService.ensure_synced`)."""
        now = self.now
        if name == TASK_FORECASTS and settings.GAMEFORECAST_REFRESH_POLICY == "elapsed-interval":
            not_before = int(settings.SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR or 0)
            if not_before and now.astimezone(timezone.utc).hour < not_before:
                return False, (f"forecasts are not fetched before {not_before:02d}:00 UTC: the provider's "
                               f"daily model run has not been observed that early, and a pass before it "
                               f"buys yesterday's")
        next_due = _parse(self.state(name).get("next_due_at"))
        if next_due is None:
            return True, None
        if now >= next_due:
            return True, None
        return False, f"next due at {next_due.isoformat()}"

    def _backoff_seconds(self, name: str, consecutive_failures: int) -> int:
        base = max(self.interval(name), BACKOFF_MIN_SECONDS)
        return int(min(base * (2 ** max(consecutive_failures - 1, 0)), BACKOFF_MAX_SECONDS))

    def slot_anchor(self, name: str) -> Optional[time]:
        """The wall-clock anchor of this task's ordinary grid, or None: only the forecasts task has one."""
        if name != TASK_FORECASTS:
            return None
        return parse_slot_anchor(settings.SYNC_FORECASTS_SLOT_ANCHOR_UTC)

    def _ordinary_due(self, name: str, after: datetime) -> datetime:
        """When the next ORDINARY pass is due, once a pass that began at `after` has ended.

        The forecasts task is anchored: the first grid slot after the pass began. A pass that ran
        late keeps the grid where it was, so a sleep across any number of slots costs one catch-up
        pass (the one that was due when the host went to sleep) and the slots after it stand; a
        pass long enough to cross the next slot is followed by that slot at once, exactly once.
        A slot minutes after a pass that fetched is harmless: what it may re-check is the policy's
        decision, and the policy re-checks nothing within `RECHECK_MIN_GAP` of the fetch it would
        re-check, per competition, from the request's own time. Every other task, and the
        forecasts task without a grid, waits its interval from now.
        """
        slot = forecast_slot_after(after, self.slot_anchor(name), self.interval(name))
        return slot if slot is not None else self.now + timedelta(seconds=self.interval(name))

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
        # The ordinary grid counts from when this pass began. A recovery pass that closes an episode
        # counts from the interrupted pass instead: the retries were never slots, and the slot the
        # interruption fell in is still the one that is owed.
        anchor_from = started
        if name == TASK_FORECASTS:
            # An interrupted forecasts pass is retried soon and within bounds (see
            # FORECASTS_RECOVERY_RETRY_SECONDS); a completed or failed one ends any such episode.
            kind = forecast_pass_outcome(result, ok)
            state["last_outcome"] = kind
            if kind in (FORECAST_PASS_PARTIAL, FORECAST_PASS_DEFERRED) and \
                    self._schedule_forecast_retry(state, result, kind, now, error):
                self._save_state(name, state)
                return state
            episode = state.pop("recovery", None)
            if isinstance(episode, dict):
                state["last_recovery"] = {**episode, "ended": kind, "ended_at": now.isoformat()}
                anchor_from = _parse(episode.get("started_at")) or started
        if ok:
            state["last_success_at"] = now.isoformat()
            state["consecutive_failures"] = 0
            state["last_error"] = None
            state["backoff_seconds"] = None
            state["next_due_at"] = self._ordinary_due(name, anchor_from).isoformat()
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
            due = min(now + timedelta(seconds=backoff), _next_budget_reset(now))
            if name == TASK_FORECASTS and isinstance(result, dict):
                # ...but never before a pause the pass reported (`paused_until`): the reset gives
                # back our allowance, not the provider's answer, and a pass before the pause ends is
                # deferred again for nothing.
                paused_until = _parse(result.get("paused_until"))
                if paused_until is not None and paused_until > due:
                    due = paused_until
            state["next_due_at"] = due.isoformat()
        self._save_state(name, state)
        return state

    def _schedule_forecast_retry(self, state: Dict[str, Any], result: Optional[Dict[str, Any]], kind: str,
                                 now: datetime, error: Optional[str]) -> bool:
        """Put the next forecasts pass on the recovery schedule, or say no: the ordinary wait applies.

        An episode is the run of retries that follows one interruption, however many days or
        restarts it spans. It starts when a pass is interrupted (`partial`) or finds the lease held
        by another worker (`deferred`), and only then: a pause or a spent allowance met with no
        episode open keeps the wait it always had. Each pass inside the episode, whatever it meets,
        counts as an attempt; a pass that finds the provider paused waits for the pause to end and
        no less than its scheduled delay. Past FORECASTS_RECOVERY_MAX_RETRIES the episode is marked
        spent and the caller backs off. It ends when a pass completes or fails (`_record`).
        """
        result = result if isinstance(result, dict) else {}
        episode = state.get("recovery")
        active = isinstance(episode, dict)
        if not active:
            if kind == FORECAST_PASS_DEFERRED and not result.get("lease_held"):
                return False
            episode = {"started_at": now.isoformat(), "attempts": 0}
        attempts = int(episode.get("attempts") or 0)
        if attempts >= FORECASTS_RECOVERY_MAX_RETRIES:
            episode["exhausted_at"] = now.isoformat()
            state["recovery"] = episode
            return False
        due = now + timedelta(seconds=FORECASTS_RECOVERY_RETRY_SECONDS * (2 ** attempts))
        paused_until = _parse(result.get("paused_until"))
        if paused_until is not None and paused_until > due:
            due = paused_until
        # Not clamped to the budget reset, unlike the ordinary waits: an interruption at 23:59 would
        # otherwise be retried at 00:01, under the minimum, and a pause the provider's answer set
        # would be cut short at midnight. The reset gives back an allowance; what the new day may
        # buy is decided by the eligibility rules, which before the publication hour buy nothing.
        episode.update({"attempts": attempts + 1, "reason": kind,
                        "detail": str(error or "")[:MAX_ERROR_CHARS],
                        "unfinished": result.get("unfinished"), "retry_at": due.isoformat()})
        state["recovery"] = episode
        state["failures"] = int(state.get("failures") or 0) + 1
        state["last_error_at"] = now.isoformat()
        state["last_error"] = str(error or "the pass was interrupted")[:MAX_ERROR_CHARS]
        # Not a failure streak: the provider did nothing, so the exponential backoff stays untouched.
        state["backoff_seconds"] = None
        state["next_due_at"] = due.isoformat()
        return True

    def _record_skip(self, name: str, reason: str, advance: bool) -> None:
        now = self.now
        state = self.state(name)
        state["last_skipped_at"] = now.isoformat()
        state["last_skip_reason"] = reason[:MAX_ERROR_CHARS]
        if advance:
            # Re-asking every minute is free but pointless, and it floods the log. Wait a normal
            # interval - but never past the next budget reset: a task blocked late in the evening
            # should resume when the allowance comes back, not hours into the new day. The forecasts
            # task waits for its next slot instead, which is at most its interval away and, at
            # 12 minutes past the reset, as good as the reset for a task the allowance blocked.
            slot = forecast_slot_after(now, self.slot_anchor(name), self.interval(name))
            state["next_due_at"] = (slot if slot is not None else
                                    min(now + timedelta(seconds=self.interval(name)), _next_budget_reset(now))).isoformat()
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
        #: Every competition-day the pass asked about, as "<key>@<day>" -> what it was served.
        calls: Dict[str, Dict[str, Any]] = {}
        metas: List[SyncMeta] = []
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
            outcomes: Dict[str, Dict[str, Any]] = {}
            if take:
                service._sync_results(day, meta, keys=take)
                spent += len(take)
                # Per competition, what THIS call was served - a fresh answer, the cache, the stale
                # copy, a failed request, or nothing - with who answered and why not.
                outcomes = {key: _clipped_call(record)
                            for key, record in service.results_call_outcomes(day, take).items()}
            out["days"][day.isoformat()] = {**meta.to_dict(), "competitions": len(take),
                                            "call_outcomes": outcomes}
            out["errors"].extend(meta.errors)
            out["polled"] = out["polled"] or meta.results_polled
            metas.append(meta)
            calls.update({f"{key}@{day.isoformat()}": record for key, record in outcomes.items()})
        out["requests"] = spent
        out["deferred"] = out["deferred"][:MAX_STORED_ERRORS]
        out["errors"] = _clip(out["errors"])
        # JUDGED BY WHAT EACH COMPETITION-DAY WAS SERVED, not by `errors` (see PASS_FAILING_OUTCOMES):
        # a primary that failed before the fallback answered is in `diagnostics`, not in the
        # verdict. The verdict is over every competition the pass asked about, so a club
        # competition answered cannot hide a national-team one whose request went out and got
        # nothing; `by_outcome` and the error name which. An empty answer for a day with nothing
        # to report is `fresh`, and ok.
        out["call_outcomes"] = calls
        out["outcome"] = _pass_outcome(calls)
        out["by_outcome"] = _by_outcome(calls)
        out["diagnostics"] = _diagnostics(metas)
        ok, error = _verdict(calls)
        return out, ok, error

    def _run_live(self, services: _Services) -> Tuple[Dict[str, Any], bool, Optional[str]]:
        service = services.match
        if not service._live_window_open():
            # The single most expensive mistake available here is polling live scores all night.
            return ({"live_window_open": False, "live_polled": False, "polls_today": self._live_polls_today(),
                     "outcome": PASS_SKIPPED, "call_outcomes": {}, "by_outcome": {},
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
                     "outcome": PASS_SKIPPED, "call_outcomes": {}, "by_outcome": {},
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
        # JUDGED BY WHAT THE POLL WAS SERVED, not by `errors` (see PASS_FAILING_OUTCOMES): a timeout
        # at the primary answered by the fallback is a poll that was answered, with the timeout kept
        # in `diagnostics` and on the primary's own status record rather than in the verdict.
        call = self._live_call_record(meta)
        out["call_outcomes"] = {"live": call}
        out["outcome"] = call["outcome"]
        out["by_outcome"] = _by_outcome(out["call_outcomes"])
        out["diagnostics"] = _diagnostics([meta])
        ok, error = _verdict(out["call_outcomes"])
        return out, ok, error

    @staticmethod
    def _chain_account(meta: SyncMeta) -> str:
        """Why the poll was not served, in the chain's own words: each provider's failure, skip or
        refusal and each decline, without the one-line summary `_sync_live` adds after them."""
        account = [e for e in meta.errors if not e.startswith("live: ")] + list(meta.declined)
        return "; ".join(account or meta.errors)

    def _live_call_record(self, meta: SyncMeta) -> Dict[str, Any]:
        """The one live poll as a `call_outcomes` entry: what it was served, by whom, and why not."""
        outcome = call_outcome(meta)
        if outcome in (CALL_FRESH, CALL_CACHE):
            detail = (f"answered by {meta.provider} after a request that got no answer: "
                      + "; ".join(meta.failed_requests)) if meta.failed_requests else None
        elif outcome == CALL_STALE:
            detail = (f"served from the stale copy {meta.provider} fetched at {meta.fetched_at}; "
                      + self._chain_account(meta))
        else:
            detail = self._chain_account(meta) or None
        return _clipped_call({"outcome": outcome, "provider": meta.provider, "detail": detail})

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
        # Inside a recovery episode (FORECASTS_RECOVERY_RETRY_SECONDS) the pass is the retry of an
        # interrupted one: it completes the turns that pass owed and leaves re-checks to the
        # ordinary pass that follows.
        recovery = isinstance(self.state(TASK_FORECASTS).get("recovery"), dict)
        report = services.forecast.ensure_synced(recovery=recovery)
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
            if name == TASK_FORECASTS:
                outcome["outcome"] = state.get("last_outcome")
                if state.get("recovery"):
                    outcome["recovery"] = state["recovery"]
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
        costs: List[int] = []
        unpriced = 0
        for key in due_keys:
            cost, priced = SyncScheduler._price_turn(provider, key)
            if not priced:
                unpriced += 1
            costs.append(cost)
        return sum(costs), SyncScheduler._describe_costs(provider, costs, unpriced, due_keys) or "nothing is due"

    @staticmethod
    def _price_turn(provider: Any, key: str) -> Tuple[int, bool]:
        """(what one turn for `key` is expected to cost, whether the provider itself priced it).

        Through the provider's `request_cost`, the same seam `ForecastService` prices a turn with
        before starting it, so discovery and the pages the last fetch needed are counted alike by
        the gate and by the estimate. A provider that will not price a turn is charged the
        expensive case: an estimate that cannot know rounds UP.
        """
        price = getattr(provider, "request_cost", None)
        if callable(price):
            try:
                return max(int(price(key)), 0), True
            except Exception as exc:  # pragma: no cover - pricing must never break an estimate
                logger.debug("Could not price the %s turn for %s: %s",
                             getattr(provider, "name", "provider"), key, exc)
        return UNPRICED_TURN_COST, False

    @staticmethod
    def _describe_costs(provider: Any, costs: Sequence[int], unpriced: int,
                        keys: Optional[Sequence[str]] = None) -> str:
        """The pricing in words. A turn costing 2 is a discovery and then a fetch, unless the
        provider says the league id is already recorded - then the last fetch needed two pages."""
        known = getattr(provider, "league_id_is_known", None)
        paged_at_two = 0
        if keys is not None and callable(known):
            for key, cost in zip(keys, costs):
                if cost == 2:
                    try:
                        paged_at_two += 1 if known(key) else 0
                    except Exception:  # pragma: no cover - wording is never worth an exception
                        pass
        parts = []
        for cost in sorted(set(costs), reverse=True):
            count = list(costs).count(cost)
            if cost == 0:
                wording = "costing nothing (a remembered discovery failure short-circuits the turn)"
            elif cost == 1:
                wording = "costing 1 request (the provider league id is already recorded)"
            elif cost == 2 and paged_at_two == count:
                wording = "costing 2 (the last fetch needed two pages)"
            elif cost == 2 and paged_at_two:
                wording = (f"costing 2 (a league-id discovery, then the fetch, for {count - paged_at_two}; "
                           f"two pages last time for {paged_at_two})")
            elif cost == 2:
                wording = "costing 2 (a league-id discovery, then the fetch)"
            else:
                wording = (f"costing {cost} request(s) (the pages the last fetch needed, plus a "
                           f"league-id discovery where the id is not recorded)")
            parts.append(f"{count} {wording}")
        if unpriced:
            parts.append(f"{unpriced} of them not priced by "
                         f"{getattr(provider, 'name', 'the provider')!r}, so charged the "
                         f"expensive case rather than assumed cheap")
        return "; ".join(parts)

    def _forecast_estimate(self, forecast: Any) -> Tuple[int, str]:
        """The forecasts task's estimate from the service's own dry run of a pass.

        `ForecastService.estimate_pass` walks the SAME plan the pass walks - the refresh policy's
        eligibility and order, dormancy from the last recorded calendar evidence, the all-or-
        nothing affordability of each turn against the allowance left right now - with this
        scheduler's pricing (`_price_turn`, which rounds an unpriced provider up). So the number
        here is what the pass is about to spend, and the basis says what it assumed.
        """
        provider = forecast.provider
        plan = forecast.estimate_pass(days_ahead=settings.GAMEFORECAST_SYNC_DAYS_AHEAD,
                                      price=lambda key: self._price_turn(provider, key)[0])
        walked = list(plan["fetch"]) + list(plan["recheck"])
        costs = [int(plan["costs"][key]) for key in walked]
        unpriced = sum(1 for key in walked if not self._price_turn(provider, key)[1])
        pricing = self._describe_costs(provider, costs, unpriced, walked) or "nothing to fetch"
        budget = getattr(provider, "budget", None)
        basis = (f"{plan['policy']}: {len(plan['fetch'])} competition(s) to fetch and "
                 f"{len(plan['recheck'])} to re-check ({pricing}), {len(plan['dormant'])} dormant on "
                 f"recorded calendar evidence and priced at 0, {len(plan['deferred'])} deferred by "
                 f"the remaining {getattr(budget, 'provider', 'forecast')} allowance "
                 f"({plan['remaining_before']} before, {plan['remaining_after']} after), "
                 f"{len(plan['ineligible'])} not eligible")
        if plan.get("publication_hour") is not None:
            basis += (f"; observed publication hour {plan['publication_hour']:02d}:00 UTC, "
                      f"{'reached' if plan.get('hour_reached') else 'not reached'}")
        basis += (". Assumes a dormant competition's calendar answer is still the one the fixture "
                  "cache holds and the database still has no fixture in its window (re-counted "
                  "now); prices each competition's pages from its last fetch, so the first fetch "
                  "of a competition with more than one page costs one more than quoted. Each one "
                  "also syncs fixtures, billed to the match-data providers, not to this allowance")
        return int(plan["requests"]), basis

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
            if callable(getattr(forecast, "estimate_pass", None)):
                # The real service: the refresh policy's own dry run of the pass, so the estimate
                # and the pass decide eligibility, dormancy and affordability the same way.
                return self._forecast_estimate(forecast)
            # A service that cannot dry-run itself (the stubs in the test suite): the interval
            # rule over its rotation, every competition priced, capped by the allowance.
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
                # The forecasts task only: how its last pass ended (completed, partial, deferred or
                # failed), the recovery episode an interrupted pass opened while it is open, and
                # the last one that closed. None for the other tasks.
                "last_outcome": state.get("last_outcome"),
                "recovery": state.get("recovery"),
                "last_recovery": state.get("last_recovery"),
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
