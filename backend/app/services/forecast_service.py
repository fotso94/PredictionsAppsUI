"""
Third-party forecast synchronisation and freshness rules.

Forecasts are fetched per covered competition within the provider's daily budget, matched to
internal matches with `match_matching.find_match` (provider refs first, then competition + teams
+ kickoff), and stored in `provider_forecasts`. Ambiguous or unmatched forecasts are counted and
logged but never attached.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.predictions import Match, MatchStatus, Team
from app.models.provider_data import ProviderForecastRecord, ProviderForecastSnapshot
from app.services import match_matching
from app.services.forecast_refresh_policy import (
    CalendarEvidence, RefreshPlan, RefreshPolicy, judge_calendar,
)
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry, _aware_utc
from app.services.providers import competitions as comps
from app.services.providers.base import (
    ProviderQuotaError,
    ProviderAuthError,
    parse_utc,
    ForecastProvider, ProviderError, ProviderForecast, ProviderNotConfiguredError,
)
from app.services.providers.registry import forecast_provider as default_forecast_provider
from app.services.sync_lease import HOLDER_REFUSAL, FencedCache, LeaseLost, SyncLease, lease_scope

if TYPE_CHECKING:  # pragma: no cover
    from app.services.match_data_service import MatchDataService

logger = logging.getLogger(__name__)

LAST_SYNC_KEY = "forecast:last_sync:{provider}:{key}"
STATUS_KEY = "forecast:status:{provider}"
#: What ONE competition's turn actually fetched, kept under that competition's own key.
#:
#: `STATUS_KEY` holds the last run of any kind and is rewritten by every later code path, including
#: the cooling-down early return that makes no provider request at all. That is how the only real
#: fetch of a day gets erased by a no-op hours later, leaving a fixture with no record that can say
#: whether the provider returned it. This key is written ONLY by a turn that actually called the
#: provider, so an unrelated later pass cannot overwrite it, and it carries the retrieval time and
#: the window it covered so a reader can tell a record that is older than the fixture it would
#: explain from one that is not.
COMPETITION_STATUS_KEY = "forecast:status:{provider}:{key}"
COMPETITION_STATUS_TTL_SECONDS = 7 * 24 * 3600
PENDING_KEY = "forecast:pending:{provider}:{key}"
COOLDOWN_KEY = "forecast:cooldown:{provider}"
SYNC_LOCK_KEY = "forecast:sync_lock:{provider}"
#: One term of the sync lease. A pass is not limited to it: the lease is renewed every
#: `SYNC_LOCK_RENEW_SECONDS` while the pass runs, and lapses after one term only when nobody renews
#: it - a crashed worker, or one cut off from Redis - so another worker can then take over.
SYNC_LOCK_TTL_SECONDS = 300
SYNC_LOCK_RENEW_SECONDS = 100

_UNSET = object()
AUTH_COOLDOWN_SECONDS = 30 * 60
UNAVAILABLE_COOLDOWN_SECONDS = 2 * 60


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - now).total_seconds()), 60)


# ------------------------------------------------------------- what happens to a forecast nobody could place
#: A pending forecast - paid for, not yet attachable - is retried on every pass while its kick-off
#: is no further past than this. A fixture that arrives late, an alias added for a club spelled two
#: ways, a re-listed match: each of those binds it for nothing, and each can happen well after the
#: match was played. The retrieval time travels with the payload, so a forecast retrieved before
#: kick-off and bound weeks later is still prematch evidence (`captured_before_kickoff`), and one
#: retrieved after kick-off never is, however soon it binds.
PENDING_RETRY_DAYS = 30
#: The pending store lives at least as long as the retry window, with a week in hand for a stopped
#: scheduler; it is renewed on every pass. 48 h, which it used to be, would have let the key expire
#: - a deletion nobody recorded - long before the retry window closed.
PENDING_TTL_SECONDS = (PENDING_RETRY_DAYS + 7) * 24 * 3600
#: Past the retry window a forecast is RETAINED, not deleted: its full payload, original
#: `fetched_at`, `model_run_at` and provenance move under an explicit retention record that says it
#: is no longer retried automatically and why. `reattach_pending(include_retained=True)` still
#: attaches it on request - after an alias correction, say - for nothing. Six months, so a match
#: whose identity is only sorted out at the end of a season can still be scored.
RETAINED_KEY = "forecast:retained:{provider}:{key}"
RETAINED_TTL_SECONDS = 180 * 24 * 3600
RETENTION_REASON_KICKOFF_PAST = "kick-off more than {days} days past; kept, not retried automatically"
RETENTION_REASON_NO_MARKET = "no usable market in the payload; kept for the record, never attachable"

_DATETIME_FIELDS = ("kickoff_utc", "model_run_at", "provider_updated_at", "fetched_at")


# ------------------------------------------------------- which snapshot is "the" snapshot
#: The order of forecast evidence: oldest first, so the newest version of it is the last row.
#:
#: ``first_fetched_at`` decides, and stays the primary key of the decision: the forecast a reader
#: saw is the one the provider last published before they looked. It is not unique, and that is not
#: corruption. The migration that backfilled this table stamped its one row per forecast with the
#: record's retrieval time, and ``scripts/repair_forecasts.py`` appends its corrected re-reading of
#: the same payload under the SAME retrieval time deliberately, because a repair retrieves nothing
#: and must not move the clock forward. Rows that share a retrieval time therefore describe a single
#: retrieval, and the row written last is the corrected reading of it - so ``created_at`` breaks the
#: tie, and the later-created row wins.
#:
#: ``id`` closes the order. ``created_at`` comes from a Python-side default, so two rows written in
#: one transaction can carry the same value to the microsecond; with no unique final key the
#: database is free to return such rows in any order it likes, and "any order it likes" changes
#: when a row is updated and rewritten elsewhere in the heap. That is exactly the failure this
#: ordering exists to prevent: scoring picked one twin, the performance read picked the other, and
#: a scored forecast was reported as still pending.
SNAPSHOT_ORDER = (
    ProviderForecastSnapshot.first_fetched_at.asc(),
    ProviderForecastSnapshot.created_at.asc(),
    ProviderForecastSnapshot.id.asc(),
)


def order_snapshots(query):
    """Apply :data:`SNAPSHOT_ORDER` to a snapshot query. The one place that orders this table."""
    return query.order_by(*SNAPSHOT_ORDER)


def choose_snapshots(query) -> Dict[Tuple[uuid.UUID, str], ProviderForecastSnapshot]:
    """The chosen snapshot per (match, provider) out of an already-filtered snapshot query.

    The single place in the codebase that answers "which snapshot is the forecast?". Callers differ
    only in what they filter to - settlement scores prematch snapshots, a resync compares against
    the newest one of any kind - and never in how the winner is picked, because a scorer and a
    reader that disagree about the row produce a score that the page cannot find.

    Cost: one indexed query over the rows the caller filtered to, read rather than reduced in SQL.
    The table holds one row per distinct forecast content per match and provider - a handful - so
    the alternative, a per-key DISTINCT ON, would buy nothing and split the rule into SQL.
    """
    chosen: Dict[Tuple[uuid.UUID, str], ProviderForecastSnapshot] = {}
    for row in order_snapshots(query).all():
        chosen[(row.match_id, row.provider)] = row  # oldest first, so the newest row lands last
    return chosen


def _forecast_to_dict(forecast: ProviderForecast) -> Dict[str, Any]:
    data = asdict(forecast)
    for field_name in _DATETIME_FIELDS:
        value = data.get(field_name)
        data[field_name] = value.isoformat() if isinstance(value, datetime) else value
    return data


def _forecast_from_dict(data: Dict[str, Any]) -> ProviderForecast:
    payload = dict(data)
    for field_name in _DATETIME_FIELDS:
        payload[field_name] = parse_utc(payload.get(field_name)) if payload.get(field_name) else None
    return ProviderForecast(**payload)


def _dec(value: Optional[float]) -> Optional[Decimal]:
    return Decimal(str(round(value, 4))) if value is not None else None


#: Values that define a distinct forecast. Two payloads with the same values are the same evidence.
_SNAPSHOT_FIELDS = (
    "home_prob", "draw_prob", "away_prob", "btts_yes_prob", "btts_no_prob",
    "over_25_prob", "under_25_prob", "over_35_prob", "under_35_prob",
    "exact_score", "exact_score_other_prob", "recommended_bets", "reasoning", "confidence",
)


def _legacy_content_hash(forecast: ProviderForecast) -> str:
    """The hash as written before the selectable blocks were part of it (rows still carry it)."""
    payload = {name: getattr(forecast, name) for name in _SNAPSHOT_FIELDS}
    payload["model_run_at"] = forecast.model_run_at.isoformat() if forecast.model_run_at else None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def content_hash(forecast: ProviderForecast) -> str:
    """Stable hash of a forecast's values, used to tell a genuinely new snapshot from a re-fetch.

    Covers the five stored markets AND every other selectable block plus the carried prices
    (`app.services.markets.markets_digest`): a payload that changed only its first-half block is a
    new forecast, and a leg taken from it must be attributable to a snapshot that holds it.
    """
    payload = {name: getattr(forecast, name) for name in _SNAPSHOT_FIELDS}
    payload["model_run_at"] = forecast.model_run_at.isoformat() if forecast.model_run_at else None
    from app.services.markets import markets_digest
    payload["markets_digest"] = markets_digest(forecast.raw) if isinstance(forecast.raw, dict) else None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _retrieved_at(forecast: ProviderForecast, fallback: datetime) -> datetime:
    """When this forecast actually came off the wire.

    Stamping the attach moment instead would make a forecast replayed from the pending cache two
    days later look like it was just retrieved, and freshness is judged on this value.
    """
    return getattr(forecast, "fetched_at", None) or fallback


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


class ForecastService:
    #: Paces the sync lease's renewal worker (see `SyncLease`); None waits on real time. Tests set
    #: a controlled one to make renewals happen exactly when they say.
    lease_waiter = None

    def __init__(self, db: Session, provider: Optional[ForecastProvider] = None, cache: Optional[MatchCache] = None,
                 now: Optional[datetime] = None, keys: Optional[List[str]] = None, use_default_provider: bool = True,
                 fixtures: Optional["MatchDataService"] = None, sync_fixtures: bool = True,
                 policy: Optional[RefreshPolicy] = None):
        self.db = db
        self.registry = MatchRegistry(db)
        self.cache = cache or MatchCache()
        self._provider = provider
        self._use_default = use_default_provider and provider is None
        self._now = now
        self.keys = keys or comps.covered_keys(settings.COVERED_COMPETITIONS)
        self._fixtures = fixtures
        self._sync_fixtures = sync_fixtures
        self._lease: Optional[SyncLease] = None
        self._lock_refusal: Optional[str] = None
        self._cooldown_cache: Any = _UNSET
        self._policy = policy

    @property
    def policy(self) -> RefreshPolicy:
        """The refresh rule this service follows (`GAMEFORECAST_REFRESH_POLICY`), built on first use.

        One object for the whole service: `ensure_synced` asks it which competitions to walk and
        in what order, `estimate_pass` asks it the same question for the dry run, and both read
        and write the same per-day state in Redis.
        """
        if self._policy is None:
            name = self.provider.name if self.provider else "none"
            self._policy = RefreshPolicy.from_settings(self.cache, name, lambda: self.now)
        return self._policy

    @property
    def fixtures(self) -> Optional["MatchDataService"]:
        """Match-data service used to make sure fixtures exist before forecasts are attached."""
        if self._fixtures is None and self._sync_fixtures:
            from app.services.match_data_service import MatchDataService
            self._fixtures = MatchDataService(self.db, cache=self.cache, now=self._now, keys=self.keys)
        return self._fixtures

    @property
    def now(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    @property
    def provider(self) -> Optional[ForecastProvider]:
        if self._provider is None and self._use_default:
            self._provider = default_forecast_provider()
            self._use_default = False
        return self._provider

    # ------------------------------------------------------------------ sync
    def _last_sync(self, key: str) -> Optional[datetime]:
        if not self.provider:
            return None
        value = self.cache.get(LAST_SYNC_KEY.format(provider=self.provider.name, key=key))
        return datetime.fromisoformat(value) if value else None

    def _mark_synced(self, key: str) -> None:
        if self.provider:
            self.cache.set(LAST_SYNC_KEY.format(provider=self.provider.name, key=key), self.now.isoformat(),
                           ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)

    def _record_status(self, report: Dict[str, Any]) -> None:
        if self.provider:
            self.cache.set(STATUS_KEY.format(provider=self.provider.name), report, ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)

    def sync_order(self) -> List[str]:
        """Covered competitions, least recently synced first.

        The daily allowance (10 requests on the GameForecastAPI free plan) is usually too small for
        all six competitions in one run. Always starting at the head of the configured list would
        spend the whole allowance on the same leagues and never reach the tail, so the competitions
        that did not get their turn yesterday go first today. Never-synced competitions come first.
        """
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return sorted(self.keys, key=lambda key: (self._last_sync(key) or epoch, self.keys.index(key)))

    def _budget_remaining(self) -> Optional[int]:
        """What the next turn can actually be paid for out of - the binding number of the two.

        Our configured ceiling and the provider's own remaining count are separate constraints,
        and the smaller one governs. On 2026-09-19 our counter said five were left and the
        provider said none, so a pass that consulted only our counter started turns the provider
        had already refused to serve.
        """
        budget = getattr(self.provider, "budget", None)
        if budget is None or not getattr(budget, "daily_limit", 0):
            return None
        try:
            effective = getattr(budget, "remaining_effective", None)
            return effective() if callable(effective) else budget.remaining()
        except Exception:  # pragma: no cover - budget is best effort
            return None

    def _turn_cost(self, key: str) -> int:
        """How many outbound requests this competition's turn will cost, before it is started.

        Only the provider knows, because only it knows whether it still has to discover the
        competition's league id: that discovery is a second request, paid BEFORE the fetch. A
        provider that does not price its turns is charged one, which is what the gate assumed for
        every competition before - and why a turn that needed two could be started with one left.
        """
        price = getattr(self.provider, "request_cost", None)
        if not callable(price):
            return 1
        try:
            return max(int(price(key)), 0)
        except Exception as exc:  # pragma: no cover - pricing must never break a sync
            logger.debug("Could not price the %s turn for %s (%s); assuming one request",
                         getattr(self.provider, "name", "provider"), key, exc)
            return 1

    def _unaffordable(self, key: str, remaining: Optional[int]) -> Optional[str]:
        """Why this competition's turn cannot be started now, or None when it can be paid for.

        The turn is all-or-nothing. Starting one whose discovery fits but whose fetch does not
        spends the last unit on a league id and returns no forecast at all, which is worse than
        not starting: the allowance is gone and the competition is no better off. So the whole
        cost has to fit - discovery and every page the provider last needed - and when it does
        not, what happens next is the refresh policy's call (`ensure_synced`): the earlier rule
        stops the pass here rather than half-spending; the daily-slot rule defers this
        competition, which then leads the next pass, and moves on to the next affordable one.
        """
        if remaining is None:
            return None
        cost = self._turn_cost(key)
        if cost == 0 or remaining >= cost:
            return None
        detail = "a league-id discovery and then a fetch" if cost > 1 else "a fetch"
        return (f"{self.provider.name}'s remaining daily allowance ({remaining}{self._remaining_source()}) "
                f"cannot cover the next competition's turn: {key} costs {cost} request(s) ({detail})")

    def _remaining_source(self) -> str:
        """Which side that remaining figure came from, as a clause for the stop reason.

        "We have 0 left" and "the provider says it has 0 left" call for different next steps and
        different pauses, so the message names which one stopped the pass.
        """
        budget = getattr(self.provider, "budget", None)
        try:
            binding = budget.limited_by() if budget is not None else "nothing"
        except Exception:  # pragma: no cover - reporting is never worth an exception
            return ""
        if binding == "the_provider":
            return ", which is what the provider itself reports is left in its own window"
        if binding == "both":
            return ", our configured ceiling and the provider's own count agreeing"
        if binding == "our_configured_ceiling":
            return ", per the daily ceiling we configured"
        return ""

    def _provider_reset_seconds(self) -> Optional[int]:
        """Seconds until the provider says its own window turns, or None when it never said."""
        rate_limit = getattr(getattr(self.provider, "budget", None), "rate_limit", None)
        if rate_limit is None:
            return None
        try:
            return rate_limit.seconds_until_reset()
        except Exception:  # pragma: no cover - never worth failing a sync over
            return None

    def _quota_cooldown_seconds(self, exc: Optional[Exception] = None) -> Tuple[int, str]:
        """How long to pause after a quota refusal, and what decided it.

        The flat "until UTC midnight" this replaces was a guess dressed as a fact. When the
        provider publishes a reset, that instant IS the answer for a refusal the provider made:
        pausing a full day on a window that reopens in three hours throws away twenty-one hours
        of allowance, which is exactly what happened on 2026-09-19 (paused ~86,000s at 00:01Z).

        Which side refused decides which clock to wait on, because only that side's window has
        to turn before there is anything to retry:
          - the provider (an HTTP 429, or its own remaining count at zero) -> its reset;
          - our configured ceiling -> UTC midnight, when our counter's day rolls over;
          - both -> the later of the two, since a request needs both to allow it.
        When the provider published no reset there is nothing new to go on, and today's
        behaviour is kept exactly: UTC midnight.
        """
        midnight = _seconds_until_utc_midnight(self.now)
        budget = getattr(self.provider, "budget", None)
        refused_by = "the_provider" if getattr(exc, "status_code", None) == 429 else None
        if refused_by is None:
            try:
                refused_by = budget.limited_by() if budget is not None else "nothing"
            except Exception:  # pragma: no cover
                refused_by = "nothing"
        reset = self._provider_reset_seconds()
        if reset is None:
            return midnight, "our counter's UTC day (the provider published no reset)"
        ours_spent = False
        theirs_spent = False
        try:
            ours_spent = bool(getattr(budget, "daily_limit", 0)) and budget.remaining() <= 0
        except Exception:  # pragma: no cover
            pass
        try:
            theirs = budget.provider_remaining() if budget is not None else None
            theirs_spent = theirs is not None and theirs <= 0
        except Exception:  # pragma: no cover
            pass
        if refused_by == "the_provider" and not (ours_spent and midnight > reset):
            return max(int(reset), 60), "the provider's own reset"
        if not theirs_spent:
            # Our own ceiling is what refused, and the provider's window still has room in it.
            # Only OUR day has to turn before there is something to retry, so the provider's
            # reset must not extend the pause past it: a provider whose window is not the UTC
            # day publishes a reset beyond our midnight most of the time, and honouring it here
            # would sleep through the allowance our own counter hands back at 00:00 - the same
            # throwing-away of hours this package exists to stop, in the opposite direction.
            return midnight, ("our counter's UTC day (the provider's own window still has room "
                              "and is not what refused)")
        if midnight >= reset:
            return midnight, ("our counter's UTC day, which outlasts the provider's own reset in "
                              f"{reset}s")
        return max(int(reset), 60), ("the provider's own reset, which outlasts our counter's UTC "
                                     f"day in {midnight}s")

    def _plan(self, force: bool = False) -> RefreshPlan:
        """What a pass would walk now, from the refresh policy. Reads Redis and the database only."""
        return self.policy.plan(list(self.keys), kickoff_of=self._next_kickoff,
                                last_sync_of=self._last_sync, force=force)

    def ensure_synced(self, days_ahead: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
        """Refresh every covered competition the refresh policy says is eligible, in its order.

        Each competition's turn is decided in a fixed order, and the order is the point:

          1. the calendar - the fixture sync runs, and only sufficient evidence (see
             `judge_calendar`) makes the competition dormant, in which case the turn is taken for
             nothing BEFORE the allowance is so much as read, so a dormant competition can never
             stand between the allowance and an active one behind it;
          2. the allowance - the whole turn must be affordable (`_unaffordable`); what happens
             when it is not depends on the policy: stop (elapsed-interval) or defer and move on
             (daily-slot);
          3. the fetch, then the policy records what it bought.

        `force` bypasses eligibility and nothing else. Re-attaching forecasts already paid for
        runs on every path, for every competition, and never consults the policy or the budget.

        Eligibility is decided after the sync lock is taken, from the shared state at that moment,
        so a worker that waited for the lock never acts on a plan another worker has since made
        untrue; the lock is released on every path that took it.
        """
        report: Dict[str, Any] = {"provider": self.provider.name if self.provider else None, "competitions": {}, "skipped": []}
        if not self.provider:
            report["error"] = "no prediction provider configured"
            return report
        days_ahead = days_ahead or settings.GAMEFORECAST_SYNC_DAYS_AHEAD
        policy = self.policy
        report["policy"] = policy.name
        report["retried"] = {}
        report["deferred"] = []
        # The memo exists so one page render does not ask Redis the same question thirty times.
        # A sync is a new operation, so it re-reads: another worker may have paused the provider since.
        self._cooldown_cache = _UNSET
        cooling = self._cooldown_reason()
        if cooling:
            # No provider calls while paused, but forecasts fetched earlier can still be attached to
            # fixtures that appeared (or became matchable) since.
            self._retry_all_pending(self.keys, report)
            report["error"] = f"skipped (recent failure: {cooling})"
            report["paused"] = True
            report["synced_at"] = self.now.isoformat()
            self._record_status(report)
            return report
        if not self._acquire_sync_lock():
            # Either another worker holds the lease and is spending the allowance, or the lease
            # could not be taken at all (no Redis, or Redis failing) - and a provider-fetching pass
            # that cannot coordinate does not fetch. Attaching what is already cached is free and
            # still runs, as far as the cache can be read; nothing is fetched.
            refusal = self._lock_refusal or "the lease could not be taken"
            if refusal == HOLDER_REFUSAL:
                report["error"] = f"a {self.provider.name} sync is already running"
            else:
                report["error"] = f"forecast sync refused: {refusal}"
                report["coordination_unavailable"] = True
            self._retry_all_pending(list(self.keys), report)
            report["synced_at"] = self.now.isoformat()
            return report
        lease = self._lease
        plain_cache = self.cache
        fenced = FencedCache(plain_cache, lease)
        # One policy object per service instance (see `policy`), so swapping its store for the
        # length of the pass affects this pass only.
        self.cache = fenced
        policy.cache = fenced
        try:
            lease.start_renewing()
            # Under the lease scope every budget reservation is owner-checked inside its own script,
            # and the providers' control-state writes (page counts, league ids) are fenced.
            with lease_scope(lease):
                return self._leased_pass(report, policy, days_ahead, force)
        except LeaseLost as exc:
            # Another worker may be running the pass now. This one has sent nothing since it noticed
            # and every write it attempted after the loss was refused by the fence; it records
            # nothing more, not even its status, and leaves the store to the lease's holder.
            report["lease_lost"] = True
            report["error"] = (f"stopped: this worker lost the {self.provider.name} sync lease ({exc}); "
                               "no further request was started and nothing more was written")
            report["synced_at"] = self.now.isoformat()
            return report
        finally:
            # Every path that took the lease gives it back and stops renewing it: success, planning
            # and provider errors, a lost lease, any other exception, cancellation and shutdown.
            self.cache = plain_cache
            policy.cache = plain_cache
            self._release_sync_lock()

    def _leased_pass(self, report: Dict[str, Any], policy: RefreshPolicy, days_ahead: int,
                     force: bool) -> Dict[str, Any]:
        """The pass proper, run only while this worker holds the sync lease.

        Every shared write below goes through the fenced cache `ensure_synced` installed, so it
        lands only while the lease is still this worker's; every budget reservation runs the
        lease check first; and each competition's turn re-confirms the lease before it starts and
        again before it applies what the provider answered. A lost lease raises `LeaseLost`, which
        `ensure_synced` turns into a clean stop.
        """
        stop_reason: Optional[str] = None
        deferred_now: Dict[str, str] = {}
        succeeded: set = set()
        plan: Optional[RefreshPlan] = None
        order: List[str] = list(self.keys)
        # Decide under the lock, from what the shared store says now. A plan made before the
        # lock goes stale while this worker waits for it: another worker can take the lock,
        # fetch a competition this one judged due, record its slot and let go, and the outdated
        # plan would then pay for the same competition twice out of an allowance other
        # competitions need. The pause is re-read for the same reason: the worker that held
        # the lock may have been refused and paused the provider since the check above.
        self._cooldown_cache = _UNSET
        cooling = self._cooldown_reason()
        if not cooling:
            plan = self._plan(force)
            # Every competition, the ones the pass walks first: the free re-attachment below
            # covers all of them, and a reader of "order" sees every competition considered.
            order = plan.order + [key for key in self.keys if key not in plan.order]
            report["order"] = order
            report["skipped"] = list(plan.ineligible)
            report["plan"] = plan.to_dict()
        for key in (plan.order if plan is not None else []):
            recheck = key in plan.recheck
            # Still this worker's? Asked again before every turn, renewing the lease as it does.
            self._confirm_lease()
            try:
                # 1. The calendar, before the allowance is even read. Forecasts can only be
                #    attached to fixtures we know about, so the fixture sync fills the calendar
                #    first (cached, one match-data request per competition at most every few
                #    hours), and the same sync is the evidence dormancy is judged on: on
                #    2026-10-18 two of the day's eight requests went to Nations Leagues with
                #    no match until November. A dormant turn is taken for nothing.
                evidence = self._calendar_evidence(key, days_ahead)
                if evidence.dormant:
                    report["competitions"][key] = {"skipped": "no fixture in window", "fetched": 0,
                                                   "attached": 0, "calendar": evidence.reason}
                    report.setdefault("dormant", []).append(key)
                    self._mark_synced(key)
                    policy.record_dormant(key, evidence)
                    succeeded.add(key)
                    continue
                # 2. The allowance. Nothing is reserved before the whole turn is known to fit.
                unaffordable = self._unaffordable(key, self._budget_remaining())
                if unaffordable:
                    if policy.stops_when_unaffordable:
                        # The earlier rule: stop here rather than half-spending, and rather
                        # than reordering by price, which would put an expensive competition
                        # permanently last - and permanently last on a small allowance means
                        # never fetched. The starved competition keeps the head of the next
                        # order. The pause runs to whichever window actually has to turn.
                        seconds, decided_by = self._quota_cooldown_seconds()
                        stop_reason = (f"{unaffordable}. Stopped rather than spending part of it, and "
                                       f"rather than reordering by price, which would starve {key} "
                                       f"permanently. Paused for {seconds}s, per {decided_by}")
                        self._pause(stop_reason, seconds)
                        break
                    if recheck:
                        # A re-check is paid from what is left over and nothing is left: it is
                        # not owed, so it is neither deferred nor recorded as a failure.
                        report.setdefault("recheck_skipped", {})[key] = unaffordable
                        continue
                    # Daily slot: this competition is deferred - it leads the next pass - and
                    # the pass moves on to the next competition the allowance can serve.
                    deferred_now[key] = unaffordable
                    policy.record_deferred(key, unaffordable)
                    continue
                # 3. The fetch.
                stats = self.sync_competition(
                    key, self.now.date(), self.now.date() + timedelta(days=days_ahead))
                if evidence.errors:
                    stats["fixture_errors"] = list(evidence.errors)
                report["competitions"][key] = stats
                self._mark_synced(key)
                latest_run = parse_utc(stats["model_run_at"]) if stats.get("model_run_at") else None
                policy.record_fetch(key, fetched_at=self.now, model_run_at=latest_run,
                                    forecasts=int(stats.get("fetched") or 0), recheck=recheck)
                succeeded.add(key)
                if recheck:
                    report.setdefault("rechecked", []).append(key)
            except ProviderNotConfiguredError as exc:
                stop_reason = str(exc)
                break
            except ProviderError as exc:
                report["competitions"][key] = {"error": str(exc)}
                logger.warning("Forecast sync for %s failed: %s", key, exc)
                policy.record_failed(key, str(exc))
                # quota/auth failures affect every competition: stop here and back off
                stop_reason = str(exc)
                if isinstance(exc, ProviderQuotaError):
                    # The provider's own window, when it published one, decides how long this
                    # is - not our assumption about when its day turns.
                    seconds, decided_by = self._quota_cooldown_seconds(exc)
                    stop_reason = f"{stop_reason} (paused for {seconds}s, per {decided_by})"
                else:
                    seconds = AUTH_COOLDOWN_SECONDS if isinstance(exc, ProviderAuthError) \
                        else UNAVAILABLE_COOLDOWN_SECONDS
                self._pause(stop_reason, seconds)
                break
        if plan is None:
            # The provider was paused while this worker waited for the lock: nothing is asked of
            # it, and forecasts already paid for are still attached.
            self._retry_all_pending(order, report)
            report["error"] = f"skipped (recent failure: {cooling})"
            report["paused"] = True
            report["synced_at"] = self.now.isoformat()
            self._record_status(report)
            return report
        # Whatever stopped the run, forecasts already paid for can still be attached to fixtures that
        # exist now. This costs no provider request, so it must happen on every path - especially the
        # path where the allowance ran out, which is exactly when the cache is all there is.
        self._retry_all_pending(order, report)
        if deferred_now and not stop_reason:
            # The allowance could not pay for every turn the pass owed. Nothing more can be bought
            # until whichever window refused it turns, so the pause runs to that reset: ours when
            # our ceiling is the binding number, the provider's when its own count is.
            seconds, decided_by = self._quota_cooldown_seconds()
            first, why = next(iter(deferred_now.items()))
            stop_reason = (f"{why}. Deferred rather than spending part of it; the pass moved on to the "
                           f"next competition the allowance could serve, and {first} leads the next pass. "
                           f"Paused for {seconds}s, per {decided_by}")
            self._pause(stop_reason, seconds)
        if stop_reason:
            # A competition whose own request failed was not synced either: it belongs at the head of
            # the next run just like the ones that were never reached. Re-checks are not owed, so
            # one that was not made is not deferred.
            deferred = [k for k in plan.fetch if k not in succeeded]
            report["deferred"] = deferred
            report["error"] = stop_reason + (
                f"; {len(deferred)} competition(s) deferred to the next reset" if deferred else "")
        report["synced_at"] = self.now.isoformat()
        self._record_status(report)
        return report

    def estimate_pass(self, days_ahead: Optional[int] = None, force: bool = False,
                      price: Optional[Any] = None) -> Dict[str, Any]:
        """What `ensure_synced` would walk and spend now. Reads Redis and the database; never a provider.

        The same plan, the same dormancy decision and the same affordability rule as the pass,
        walked against the allowance that is left right now, so the number here is the number
        the pass is about to spend - the only figure that has to be read exactly on a plan of
        eight requests a day. Two things the pass knows that this cannot: a calendar answer the
        fixture cache no longer holds (priced active, the expensive way), and a page the
        provider has not shown before (priced from the last fetch's page count; the first fetch
        of a competition with more than one page costs one more than quoted).

        `price` prices one turn; the scheduler passes its own, which rounds an unpriced provider
        UP, so an estimate that cannot know errs towards over-reporting.
        """
        days_ahead = days_ahead or settings.GAMEFORECAST_SYNC_DAYS_AHEAD
        price = price or self._turn_cost
        plan = self._plan(force)
        remaining = self._budget_remaining()
        out: Dict[str, Any] = {"policy": plan.policy, "publication_hour": plan.publication_hour,
                               "hour_reached": plan.hour_reached, "ineligible": dict(plan.ineligible),
                               "fetch": [], "recheck": [], "dormant": {}, "deferred": [], "recheck_skipped": [],
                               "costs": {}, "requests": 0, "remaining_before": remaining}
        stopped = False
        for key in plan.order:
            kind = "recheck" if key in plan.recheck else "fetch"
            if stopped:
                if kind == "fetch":
                    out["deferred"].append(key)
                continue
            dormant, why = self.policy.calendar_still_dormant(
                key, window_days=days_ahead, valid_for_seconds=settings.MATCH_CACHE_TTL_FIXTURES * 4,
                count=lambda key=key: self._fixture_count(key, days_ahead))
            if dormant:
                out["dormant"][key] = why
                out["costs"][key] = 0
                continue
            cost = max(int(price(key)), 0)
            out["costs"][key] = cost
            if remaining is not None and cost > 0 and remaining < cost:
                if kind == "fetch":
                    out["deferred"].append(key)
                else:
                    out["recheck_skipped"].append(key)
                if self.policy.stops_when_unaffordable:
                    stopped = True
                continue
            out[kind].append(key)
            out["requests"] += cost
            if remaining is not None:
                remaining -= cost
        out["remaining_after"] = remaining
        return out

    def _retry_all_pending(self, keys: List[str], report: Dict[str, Any]) -> None:
        """Attach every cached unmatched forecast we already paid for. Makes no provider request."""
        for key in keys:
            try:
                retried = self._retry_pending(key)
            except LeaseLost:
                raise  # not a broken entry: this worker's writes are no longer accepted
            except Exception as exc:  # a broken cache entry must not abort the whole run
                logger.warning("Retrying pending forecasts for %s failed: %s", key, exc)
                continue
            if retried:
                report.setdefault("retried", {})[key] = retried

    def _pause(self, reason: str, seconds: int) -> None:
        self.cache.set(COOLDOWN_KEY.format(provider=self.provider.name), {"reason": reason},
                       ttl=seconds, stale_ttl=seconds)
        self._cooldown_cache = reason

    # ------------------------------------------------------------------ concurrency
    def _acquire_sync_lock(self) -> bool:
        """Take the provider's sync lease, so one worker spends the allowance at a time.

        A provider-fetching pass needs coordination: with no Redis behind the cache (it failed to
        initialise) or a Redis that fails while the lease is being taken, the lease is not taken
        and the pass does not fetch. `_lock_refusal` says which. Cached data stays readable.
        """
        self._lock_refusal = None
        if not self.provider:
            self._lease = None
            return True
        client = getattr(self.cache, "_redis", lambda: None)()
        lease = SyncLease(client, SYNC_LOCK_KEY.format(provider=self.provider.name), SYNC_LOCK_TTL_SECONDS,
                          renew_every=SYNC_LOCK_RENEW_SECONDS, waiter=self.lease_waiter,
                          name=f"{self.provider.name} forecast sync")
        if not lease.acquire():
            self._lease = None
            self._lock_refusal = lease.refusal
            return False
        self._lease = lease
        return True

    def _release_sync_lock(self) -> None:
        """Stop renewing and give the lease back, if it is still this worker's. Never raises."""
        lease, self._lease = self._lease, None
        if lease is not None:
            lease.release()

    def _confirm_lease(self) -> None:
        """Raise `LeaseLost` unless this worker still holds its sync lease; renews it as it checks.

        A no-op outside a pass. Installed as the spending guard for the pass, so it also runs before
        every budget reservation the pass makes, on any provider.
        """
        lease = self._lease
        if lease is not None:
            lease.confirm()

    # ------------------------------------------------------------------ the calendar
    def _fixture_count(self, key: str, days_ahead: int) -> Optional[int]:
        """Fixtures of `key` still to be played inside the forecast window, or None when unreadable."""
        league = self.registry.ensure_canonical_league(key)
        count = self.registry.fixtures_in_window(league.id, self.now, self.now + timedelta(days=days_ahead))
        return count if isinstance(count, int) and not isinstance(count, bool) else None

    def _next_kickoff(self, key: str) -> Optional[datetime]:
        """When `key` next plays, for the order of a pass; None when unknown, which sorts last."""
        try:
            league = self.registry.ensure_canonical_league(key)
            value = self.registry.next_kickoff(league.id, self.now)
        except Exception as exc:  # the order is a preference, never worth failing a sync over
            logger.debug("Could not read the next kick-off for %s: %s", key, exc)
            return None
        return value if isinstance(value, datetime) else None

    def _calendar_evidence(self, key: str, days_ahead: int) -> CalendarEvidence:
        """Run this turn's fixture sync and judge what it established about the forecast window.

        The verdict and the evidence it rests on are recorded under the competition's own key, so
        the dry run can tell a competition that was found dormant from one that was never checked.
        Fixture problems never block forecast handling: a sync that raises is evidence of nothing,
        and the competition stays active.
        """
        fixtures = self.fixtures
        ran, source, stale, errors, asked = False, None, False, [], None
        if fixtures is not None:
            ran, asked = True, days_ahead
            try:
                meta = fixtures.sync_upcoming(key, days_ahead)
                source = getattr(meta, "source", None)
                stale = bool(getattr(meta, "stale", False))
                errors = [str(e) for e in (getattr(meta, "errors", None) or [])]
            except LeaseLost:
                # Raised by the spending guard before the calendar request was reserved: the pass
                # stops; no provider is blamed, paused or cooled down for it.
                raise
            except Exception as exc:
                logger.warning("Fixture sync before forecasts failed for %s: %s", key, exc)
                errors = [str(exc)]
        evidence = judge_calendar(key, self.now, days_ahead, ran=ran,
                                  source=source if isinstance(source, str) else None, stale=stale,
                                  errors=errors, asked_days=asked,
                                  count=lambda: self._fixture_count(key, days_ahead))
        self.policy.record_calendar(evidence)
        return evidence

    def sync_competition(self, key: str, date_from: date, date_to: date) -> Dict[str, Any]:
        assert self.provider is not None
        # Free first: fixtures may have appeared since the last run, so attach what we already paid for
        # before spending anything. Without this the retry never runs on the path that actually fetches.
        retried = self._retry_pending(key)
        forecasts = self.provider.get_forecasts(key, date_from, date_to)
        # The request may have been in flight for a while. If this worker lost the lease meanwhile,
        # another worker may already have fetched this competition and recorded it: the late
        # answer is dropped here, before it can overwrite anything, and the pass stops.
        self._confirm_lease()
        league = self.registry.ensure_canonical_league(key)
        stats: Dict[str, Any] = {"fetched": len(forecasts), "attached": 0, "ambiguous": 0, "unmatched": 0,
                                 "without_markets": 0, "details": []}
        # The newest run date in the response: what the refresh policy reads to tell a fetch that
        # bought the day's run from one that bought the previous day's, and the hour it learns from.
        runs = [_aware_utc(f.model_run_at) for f in forecasts if isinstance(f.model_run_at, datetime)]
        stats["model_run_at"] = max(runs).isoformat() if runs else None
        if retried:
            stats["retried"] = retried
        pending: List[Dict[str, Any]] = []
        for forecast in forecasts:
            outcome = self.attach_forecast(forecast, key, league.id)
            stats[outcome["result"]] += 1
            if outcome["result"] != "attached":
                stats["details"].append({k: v for k, v in outcome.items() if k != "result"} | {"result": outcome["result"]})
            if outcome["result"] in ("unmatched", "ambiguous"):
                pending.append(_forecast_to_dict(forecast))
        self.db.commit()
        self._store_pending(key, pending)
        stats["details"] = stats["details"][:25]
        self._record_competition_fetch(key, stats)
        return stats

    def _record_competition_fetch(self, key: str, stats: Dict[str, Any]) -> None:
        """Retain what this competition's turn actually fetched, under its own key.

        Written here and nowhere else, so only a turn that really called the provider leaves a
        record: a cooling-down early return, a run that skipped this competition as not due, and a
        turn whose request failed (this is never reached, the exception propagates) all leave the
        last real record standing instead of replacing it with a no-op.

        Bounded by construction: the provider's own report names discarded events by id, teams and
        reason up to its cap and never carries a payload, this adds counters only, and the key
        expires. Six covered competitions means at most six of these.
        """
        if not self.provider:
            return
        reported = getattr(self.provider, "last_fetch", None)
        # Only a report that names THIS competition is used. A report left over from another
        # competition's turn would attribute one response's events to a different league, and a
        # reader would then evidence "the provider did not return this fixture" from a listing
        # that was never about it. Mis-attributed evidence is worse than none.
        if not (isinstance(reported, dict) and reported.get("key") == key):
            reported = None
        record: Dict[str, Any] = dict(reported) if reported else {}
        record.setdefault("provider", self.provider.name)
        record.setdefault("key", key)
        # The provider stamps the moment the response was read. Only a provider that reports
        # nothing falls back to now, and a record with no real retrieval time can still be placed
        # against a fixture row by the reader, who checks this field before trusting anything else.
        record.setdefault("fetched_at", self.now.isoformat())
        record["recorded_at"] = self.now.isoformat()
        for name in ("fetched", "attached", "unmatched", "ambiguous", "without_markets"):
            record[name] = stats.get(name, 0)
        self.cache.set(COMPETITION_STATUS_KEY.format(provider=self.provider.name, key=key), record,
                       ttl=COMPETITION_STATUS_TTL_SECONDS, stale_ttl=COMPETITION_STATUS_TTL_SECONDS)

    # ------------------------------------------------------------------ pending (unmatched) forecasts
    def _pending_key(self, key: str) -> str:
        return PENDING_KEY.format(provider=self.provider.name if self.provider else "none", key=key)

    def _store_pending(self, key: str, pending: List[Dict[str, Any]], replace: bool = False) -> None:
        """Keep unmatched forecasts so they can be attached later without paying for them again.

        Merged by provider event id rather than replaced: a fetch that covers the next seven days
        must not discard a forecast for day eight that an earlier fetch already paid for out of a
        ten-request daily allowance.
        """
        pending_key = self._pending_key(key)
        merged: Dict[str, Dict[str, Any]] = {}
        if not replace:
            for item in (self.cache.get(pending_key) or []):
                if isinstance(item, dict) and item.get("external_event_id"):
                    merged[str(item["external_event_id"])] = item
        for item in pending:
            if item.get("external_event_id"):
                merged[str(item["external_event_id"])] = item
        if merged:
            self.cache.set(pending_key, list(merged.values()), ttl=PENDING_TTL_SECONDS, stale_ttl=PENDING_TTL_SECONDS)
        else:
            self.cache.delete(pending_key)

    def reattach_pending(self, key: Optional[str] = None, include_retained: bool = False) -> Dict[str, Any]:
        """Re-attach forecasts ALREADY PAID FOR, spending nothing.

        A forecast the provider gave us but whose fixture we could not identify is kept, so that a
        later change - a team alias, a fixture that has since been stored, a name spelled two ways
        by two providers - can bind it without asking again. Until now the only way to reach that
        retry was `sync_competition`, which runs it first and then FETCHES; a caller who wanted the
        free half had to pay for the other half, and on an allowance of eight requests a day that
        is the difference between fixing a mis-attachment and not being able to.

        `key` narrows it to one competition; omitted, it covers every competition in the rotation.
        `include_retained` also tries the forecasts past the retry window (`PENDING_RETRY_DAYS`),
        which are kept but not retried on their own: the call to make after an alias correction.
        Nothing here touches the provider - `_retry_pending` reads the stored payloads and the
        database only - and `test_reattaching_pending_forecasts_spends_nothing` asserts the request
        counter is unmoved rather than trusting this sentence.

        The summary adds up: `still_pending` is what was pending minus what attached minus what
        moved into retention; `retained` counts the moves; `retained_attached` what an explicit
        retained attempt bound.
        """
        keys = [key] if key else list(self.keys)
        report: Dict[str, Any] = {"competitions": {}, "attached": 0, "still_pending": 0, "retained": 0}
        for competition in keys:
            counts = dict(self._retry_pending(competition) or {})
            if include_retained:
                counts.update(self._reattach_retained(competition) or {})
            if not counts:
                continue
            report["competitions"][competition] = counts
            report["attached"] += counts.get("attached", 0) + counts.get("retained_attached", 0)
            report["retained"] += counts.get("retained", 0)
            report["still_pending"] += (counts.get("pending", 0) - counts.get("attached", 0)
                                        - counts.get("retained", 0))
            if include_retained:
                report["retained_attached"] = report.get("retained_attached", 0) + counts.get("retained_attached", 0)
                report["retained_kept"] = report.get("retained_kept", 0) + counts.get("retained_kept", 0)
        return report

    def _retry_pending(self, key: str) -> Optional[Dict[str, int]]:
        """Attach previously unmatched forecasts to fixtures that exist now. No provider request is made.

        Every item is tried, whatever its kick-off: attaching reads the database only, and a
        forecast retrieved before kick-off that binds weeks later is prematch evidence the match
        page and settlement can still use. What its kick-off decides is only what happens to an
        item that STILL does not bind: inside `PENDING_RETRY_DAYS` it stays pending and is tried
        again next pass; past that it moves into retention with the reason, where it waits for an
        explicit `reattach_pending(include_retained=True)`. Nothing is deleted, and the stored
        payload - `fetched_at` and `model_run_at` included - is re-stored exactly as it was.
        """
        pending = self.cache.get(self._pending_key(key)) or []
        if not pending:
            return None
        league = self.registry.ensure_canonical_league(key)
        counts = {"pending": len(pending), "attached": 0}
        still_pending: List[Dict[str, Any]] = []
        retired: List[Dict[str, Any]] = []
        for item in pending:
            forecast = _forecast_from_dict(item)
            outcome = self.attach_forecast(forecast, key, league.id)
            if outcome["result"] == "attached":
                counts["attached"] += 1
            elif outcome["result"] == "without_markets":
                retired.append(self._retention_record(item, RETENTION_REASON_NO_MARKET, outcome))
            elif self._past_retry_window(item):
                retired.append(self._retention_record(
                    item, RETENTION_REASON_KICKOFF_PAST.format(days=PENDING_RETRY_DAYS), outcome))
            else:
                still_pending.append(item)
        self.db.commit()
        if retired:
            counts["retained"] = len(retired)
            self._store_retained(key, retired)
        # `still_pending` is the full remaining set, so this call replaces rather than merges
        self._store_pending(key, still_pending, replace=True)
        return counts

    def _past_retry_window(self, item: Dict[str, Any]) -> bool:
        """Is this forecast's kick-off further past than the automatic retry window reaches?"""
        kickoff = parse_utc(item.get("kickoff_utc")) if item.get("kickoff_utc") else None
        if kickoff is None:
            return False
        return kickoff < self.now - timedelta(days=PENDING_RETRY_DAYS)

    def _retention_record(self, item: Dict[str, Any], reason: str, outcome: Dict[str, Any]) -> Dict[str, Any]:
        """The payload, untouched, under a record that says why it is no longer retried."""
        return {"forecast": dict(item),
                "retention": {"retry": False, "reason": reason, "retired_at": self.now.isoformat(),
                              "kickoff_utc": item.get("kickoff_utc"),
                              "fetched_at": item.get("fetched_at"), "model_run_at": item.get("model_run_at"),
                              "last_refusal": outcome.get("reason"), "last_result": outcome.get("result")}}

    def _retained_key(self, key: str) -> str:
        return RETAINED_KEY.format(provider=self.provider.name if self.provider else "none", key=key)

    def retained(self, key: str) -> List[Dict[str, Any]]:
        """The forecasts of `key` kept past the retry window, each under its retention record."""
        stored = self.cache.get(self._retained_key(key)) or []
        return [record for record in stored if isinstance(record, dict) and isinstance(record.get("forecast"), dict)]

    def _store_retained(self, key: str, records: List[Dict[str, Any]], replace: bool = False) -> None:
        """Keep retention records, merged by provider event id so nothing already kept is lost."""
        merged: Dict[str, Dict[str, Any]] = {}
        if not replace:
            for record in self.retained(key):
                event = record["forecast"].get("external_event_id")
                if event:
                    merged[str(event)] = record
        for record in records:
            event = record["forecast"].get("external_event_id")
            if event:
                merged[str(event)] = record
        if merged:
            self.cache.set(self._retained_key(key), list(merged.values()),
                           ttl=RETAINED_TTL_SECONDS, stale_ttl=RETAINED_TTL_SECONDS)
        else:
            self.cache.delete(self._retained_key(key))

    def _reattach_retained(self, key: str) -> Optional[Dict[str, int]]:
        """Try every retained forecast of `key` once, on request. No provider request is made."""
        records = self.retained(key)
        if not records:
            return None
        league = self.registry.ensure_canonical_league(key)
        counts = {"retained_tried": len(records), "retained_attached": 0, "retained_kept": 0}
        kept: List[Dict[str, Any]] = []
        for record in records:
            outcome = self.attach_forecast(_forecast_from_dict(record["forecast"]), key, league.id)
            if outcome["result"] == "attached":
                counts["retained_attached"] += 1
                continue
            record = dict(record)
            record["retention"] = dict(record.get("retention") or {})
            record["retention"]["last_attempt_at"] = self.now.isoformat()
            record["retention"]["last_refusal"] = outcome.get("reason")
            record["retention"]["last_result"] = outcome.get("result")
            kept.append(record)
            counts["retained_kept"] += 1
        self.db.commit()
        self._store_retained(key, kept, replace=True)
        return counts

    def attach_forecast(self, forecast: ProviderForecast, key: str, league_id) -> Dict[str, Any]:
        if not forecast.has_any_market():
            return {"result": "without_markets", "event": forecast.external_event_id}
        # 1. previously linked event id -> same match (survives rescheduling)
        match = self.registry.match_by_ref(forecast.provider, forecast.external_event_id)
        confidence, matched_by = "exact", "provider_id"
        if match is not None and not self._ref_still_describes(match, forecast):
            # Provider event ids are small integers and get recycled between seasons. A ref that no
            # longer names the same teams is not evidence, so the forecast is refused rather than
            # attached to whatever match happens to hold that id.
            logger.warning("Forecast %s claims match %s but names %s vs %s; refusing to attach",
                           forecast.external_event_id, match.id, forecast.home_name, forecast.away_name)
            return {"result": "ambiguous", "event": forecast.external_event_id, "home": forecast.home_name,
                    "away": forecast.away_name,
                    "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None,
                    "reason": "provider event id no longer names the same teams in the same order",
                    "candidates": [str(match.id)]}
        if match is None:
            # 2. competition + teams + kickoff
            candidates = self.registry.candidates_for(league_id, forecast.kickoff_utc, competition_key=key) if forecast.kickoff_utc else []
            decision = match_matching.find_match(forecast.home_name, forecast.away_name, forecast.kickoff_utc, key, candidates)
            if not decision.attached:
                result = "ambiguous" if decision.confidence == "ambiguous" else "unmatched"
                logger.info("Forecast %s (%s vs %s @ %s) not attached: %s", forecast.external_event_id, forecast.home_name,
                            forecast.away_name, forecast.kickoff_utc, decision.reason)
                return {"result": result, "event": forecast.external_event_id, "home": forecast.home_name,
                        "away": forecast.away_name, "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None,
                        "reason": decision.reason, "candidates": decision.candidate_ids}
            match = self.db.query(Match).filter(Match.id == uuid.UUID(decision.match_id)).first()
            if match is None:
                # The candidate came from this same session, so it should still be there. If it is
                # not - deleted underneath us, or a stale id - refusing is the only safe answer:
                # attaching a forecast to a match we cannot load is exactly the uncertain association
                # this whole path exists to prevent.
                logger.warning("Forecast %s matched match %s, which no longer exists; refusing to attach",
                               forecast.external_event_id, decision.match_id)
                return {"result": "unmatched", "event": forecast.external_event_id, "home": forecast.home_name,
                        "away": forecast.away_name,
                        "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None,
                        "reason": "matched match no longer exists", "candidates": [decision.match_id]}
            confidence, matched_by = decision.confidence, "name_kickoff"
            self.registry.set_ref("match", match.id, forecast.provider, forecast.external_event_id, confidence=confidence,
                                  matched_by=matched_by, metadata={"home": forecast.home_name, "away": forecast.away_name,
                                                                   "kickoff_utc": forecast.kickoff_utc.isoformat() if forecast.kickoff_utc else None})
        self._upsert_record(match, forecast, confidence, matched_by)
        return {"result": "attached", "event": forecast.external_event_id, "match_id": str(match.id)}

    def _ref_still_describes(self, match: Match, forecast: ProviderForecast) -> bool:
        """Does the match a provider id points at still have the teams, in the order, just named?

        The orientation has to agree, not just the pair of names. Two reasons:

        - every probability is orientation-bound. Attaching a forecast listed the other way round
          would put the away side's win probability on the home side, which is worse than having no
          forecast at all.
        - in a two-legged tie, Liverpool v Everton and Everton v Liverpool are different matches, so
          a reversed pair is not evidence that this is the same fixture.

        The owner's rule is to reject a swapped fixture rather than guess, so a reversed listing
        fails this check and the forecast is refused.
        """
        if not forecast.home_name or not forecast.away_name:
            return True  # nothing to check against; the ref stands
        home = self.db.query(Team).filter(Team.id == match.home_team_id).first()
        away = self.db.query(Team).filter(Team.id == match.away_team_id).first()
        if home is None or away is None:
            return True
        return (match_matching.team_names_match(forecast.home_name, home.name)
                and match_matching.team_names_match(forecast.away_name, away.name))

    def _upsert_record(self, match: Match, forecast: ProviderForecast, confidence: str, matched_by: str) -> ProviderForecastRecord:
        """Make `forecast` the current row for (match, provider), unless the row holds a newer retrieval.

        One current row per (match, provider) - `uq_provider_forecasts_match_provider`. Two writers can
        reach a match that has no row yet at the same moment; a plain "read, then insert if absent"
        lets both insert, and the second one's unique-constraint failure rolls back its transaction
        and with it the newer forecast. So the row is first claimed with INSERT ... ON CONFLICT DO
        NOTHING - the second writer waits for the first's transaction and then inserts nothing -
        and then read back under FOR UPDATE, which every writer of the row holds until it commits.
        The comparison and the write below therefore always happen against the latest committed row:
        newer retrieval replaces it, older never does (kept as history), and an equal retrieval is
        the same retrieval re-read, applied in the order the lock serialises them, as
        `SNAPSHOT_ORDER` breaks the same tie.
        """
        retrieved = _naive(_retrieved_at(forecast, self.now))
        claimed_id = uuid.uuid4()
        bind = self.db.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", None) == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            self.db.execute(
                pg_insert(ProviderForecastRecord.__table__)
                .values(id=claimed_id, match_id=match.id, provider=forecast.provider,
                        external_event_id=forecast.external_event_id, match_confidence=confidence,
                        matched_by=matched_by, fetched_at=retrieved)
                .on_conflict_do_nothing(constraint="uq_provider_forecasts_match_provider"))
        # Locked for the rest of the transaction, so the "is this retrieval newer?" comparison below
        # and the write that follows it cannot be split by another writer of the same row.
        record = self.db.query(ProviderForecastRecord).filter(
            ProviderForecastRecord.match_id == match.id,
            ProviderForecastRecord.provider == forecast.provider,
        ).with_for_update().populate_existing().first()
        claimed = record is not None and record.id == claimed_id
        if (record is not None and not claimed and record.fetched_at is not None and retrieved is not None
                and retrieved < record.fetched_at):
            # An older retrieval never replaces a newer current row. Two ways one arrives: a worker
            # that lost its sync lease after confirming it and before writing (the window the lease
            # cannot close on its own), and a pending forecast re-attached after a newer fetch of the
            # same event. It is still evidence of what the model said then, so the history keeps it.
            self._record_snapshot(match, forecast, confidence, matched_by)
            self.db.flush()
            return record
        if record is None:
            # Not PostgreSQL (no ON CONFLICT here): the plain insert, as before.
            record = ProviderForecastRecord(id=claimed_id, match_id=match.id, provider=forecast.provider,
                                            external_event_id=forecast.external_event_id, match_confidence=confidence,
                                            matched_by=matched_by, fetched_at=retrieved)
            self.db.add(record)
        record.external_event_id = forecast.external_event_id
        record.home_win_prob = _dec(forecast.home_prob)
        record.draw_prob = _dec(forecast.draw_prob)
        record.away_win_prob = _dec(forecast.away_prob)
        record.btts_yes_prob = _dec(forecast.btts_yes_prob)
        record.btts_no_prob = _dec(forecast.btts_no_prob)
        record.total_goals_over_25_prob = _dec(forecast.over_25_prob)
        record.total_goals_under_25_prob = _dec(forecast.under_25_prob)
        record.total_goals_over_35_prob = _dec(forecast.over_35_prob)
        record.total_goals_under_35_prob = _dec(forecast.under_35_prob)
        record.exact_score = forecast.exact_score
        record.exact_score_other_prob = _dec(forecast.exact_score_other_prob)
        record.recommended_bets = forecast.recommended_bets
        record.reasoning = forecast.reasoning
        record.confidence = _dec(forecast.confidence)
        record.anomalies = forecast.anomalies or None
        record.match_confidence = confidence
        record.matched_by = matched_by
        record.model_run_at = _naive(forecast.model_run_at)
        record.provider_updated_at = _naive(forecast.provider_updated_at)
        record.fetched_at = _naive(_retrieved_at(forecast, self.now))
        record.raw_payload = forecast.raw or None
        self._record_snapshot(match, forecast, confidence, matched_by)
        self.db.flush()
        return record

    def _record_snapshot(self, match: Match, forecast: ProviderForecast, confidence: str,
                         matched_by: str) -> ProviderForecastSnapshot:
        """Append this forecast to the evidence history, or mark the existing one as seen again.

        A forecast is the record of what a model said before a match was played, so the current-row
        update must never be the only trace. Unchanged content only moves `last_fetched_at`, which
        keeps the table proportional to how often the model actually changes its mind.
        """
        digest = content_hash(forecast)
        retrieved = _naive(_retrieved_at(forecast, self.now))
        # The same "which snapshot is the forecast?" question settlement asks, so it goes through
        # the same helper: comparing new content against one twin while settlement scores the other
        # is how a duplicate snapshot gets appended for content that had not changed at all.
        latest = choose_snapshots(
            self.db.query(ProviderForecastSnapshot)
            .filter(ProviderForecastSnapshot.match_id == match.id,
                    ProviderForecastSnapshot.provider == forecast.provider)
        ).get((match.id, forecast.provider))
        now = _naive(self.now)
        if latest is not None and self._same_content(latest, forecast, digest):
            latest.content_hash = digest  # backfilled rows carry no hash until they are seen again
            seen = retrieved or now
            # Never backwards: an older retrieval of the same content says nothing newer.
            if latest.last_fetched_at is None or seen > latest.last_fetched_at:
                latest.last_fetched_at = seen
            return latest
        kickoff = _naive(_aware_utc(match.match_date)) if match.match_date else None
        snapshot = ProviderForecastSnapshot(
            id=uuid.uuid4(), match_id=match.id, provider=forecast.provider,
            external_event_id=forecast.external_event_id, content_hash=digest,
            home_win_prob=_dec(forecast.home_prob), draw_prob=_dec(forecast.draw_prob),
            away_win_prob=_dec(forecast.away_prob),
            btts_yes_prob=_dec(forecast.btts_yes_prob), btts_no_prob=_dec(forecast.btts_no_prob),
            total_goals_over_25_prob=_dec(forecast.over_25_prob),
            total_goals_under_25_prob=_dec(forecast.under_25_prob),
            total_goals_over_35_prob=_dec(forecast.over_35_prob),
            total_goals_under_35_prob=_dec(forecast.under_35_prob),
            exact_score=forecast.exact_score,
            exact_score_other_prob=_dec(forecast.exact_score_other_prob),
            recommended_bets=forecast.recommended_bets, reasoning=forecast.reasoning,
            confidence=_dec(forecast.confidence), anomalies=forecast.anomalies or None,
            match_confidence=confidence, matched_by=matched_by,
            model_run_at=_naive(forecast.model_run_at),
            provider_updated_at=_naive(forecast.provider_updated_at),
            first_fetched_at=retrieved or now, last_fetched_at=retrieved or now, kickoff_at_capture=kickoff,
            # NULL when the kickoff was not known: a stored False would assert "not prematch",
            # which is a claim we cannot make.
            captured_before_kickoff=((retrieved or now) < kickoff) if kickoff else None,
            raw_payload=forecast.raw or None,
        )
        self.db.add(snapshot)
        return snapshot

    @staticmethod
    def _same_content(snapshot: ProviderForecastSnapshot, forecast: ProviderForecast, digest: str) -> bool:
        if snapshot.content_hash:
            if snapshot.content_hash == digest:
                return True
            # A hash written before the selectable blocks were part of it: the same content only
            # if the legacy hash matches AND the blocks themselves do. Otherwise it is a new snapshot,
            # which is exactly what a changed first-half block or price has to become.
            if snapshot.content_hash == _legacy_content_hash(forecast):
                from app.services.markets import markets_digest
                return markets_digest(snapshot.raw_payload) == markets_digest(forecast.raw)
            return False
        # Rows backfilled by the migration have no hash: compare the stored values instead.
        pairs = (
            (snapshot.home_win_prob, forecast.home_prob), (snapshot.draw_prob, forecast.draw_prob),
            (snapshot.away_win_prob, forecast.away_prob),
            (snapshot.btts_yes_prob, forecast.btts_yes_prob), (snapshot.btts_no_prob, forecast.btts_no_prob),
            (snapshot.total_goals_over_25_prob, forecast.over_25_prob),
            (snapshot.total_goals_under_25_prob, forecast.under_25_prob),
            (snapshot.total_goals_over_35_prob, forecast.over_35_prob),
            (snapshot.total_goals_under_35_prob, forecast.under_35_prob),
            (snapshot.exact_score_other_prob, forecast.exact_score_other_prob),
        )
        for stored, fresh in pairs:
            if (stored is None) != (fresh is None):
                return False
            if stored is not None and abs(float(stored) - float(fresh)) > 1e-6:
                return False
        return (snapshot.exact_score or None) == (forecast.exact_score or None) and \
               _naive(forecast.model_run_at) == snapshot.model_run_at

    def snapshots_for_match(self, match_id, provider_name: Optional[str] = None) -> List[ProviderForecastSnapshot]:
        """Full forecast history for a match, oldest first. Evidence for later evaluation.

        Ordered by :data:`SNAPSHOT_ORDER`, so the last row of this history is the row settlement
        scores: a reader scrolling to the bottom of the evidence sees the forecast that was scored.
        """
        query = self.db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.match_id == match_id)
        name = provider_name or (self.provider.name if self.provider else settings.PREDICTION_PROVIDER)
        if name and name != "none":
            query = query.filter(ProviderForecastSnapshot.provider == name)
        return order_snapshots(query).all()

    # ------------------------------------------------------------------ reads
    def forecast_for_match(self, match: Match, provider_name: Optional[str] = None) -> Optional[ProviderForecastRecord]:
        query = self.db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id == match.id)
        name = provider_name or (self.provider.name if self.provider else settings.PREDICTION_PROVIDER)
        if name and name != "none":
            query = query.filter(ProviderForecastRecord.provider == name)
        return query.order_by(ProviderForecastRecord.fetched_at.desc()).first()

    def _cooldown_reason(self) -> Optional[str]:
        """Why forecast refreshes are paused, or None. Read once per service instance.

        A page renders thirty matches; each one must not hit Redis for the same answer.
        """
        if self._cooldown_cache is _UNSET:
            reason = None
            if self.provider:
                cooling = self.cache.get(COOLDOWN_KEY.format(provider=self.provider.name))
                if isinstance(cooling, dict):
                    reason = cooling.get("reason")
            self._cooldown_cache = reason
        return self._cooldown_cache

    def freshness(self, record: Optional[ProviderForecastRecord], match: Match) -> Dict[str, Any]:
        """Never present an old forecast as current: report stale/kickoff_passed explicitly.

        A paused refresh is reported separately from an absent forecast. "We cannot refresh this
        right now" and "no such forecast exists" are different statements, and only one of them is
        a reason to distrust the number on screen.
        """
        paused = self._cooldown_reason()
        if record is None:
            if paused:
                return {"state": "unavailable", "reason": "no forecast for this match",
                        "refresh_blocked": True, "refresh_blocked_reason": paused}
            return {"state": "unavailable", "reason": "no forecast for this match", "refresh_blocked": False}
        extra: Dict[str, Any] = {"refresh_blocked": bool(paused)}
        if paused:
            extra["refresh_blocked_reason"] = paused
        now = self.now
        kickoff = _aware_utc(match.match_date)
        if match.status == MatchStatus.FINISHED or (kickoff + timedelta(minutes=150) < now):
            return {"state": "kickoff_passed",
                    "reason": "match already played; forecast shown for reference only", **extra}
        generated = record.model_run_at or record.provider_updated_at or record.fetched_at
        if generated is not None:
            age = now - _aware_utc(generated)
            if age > timedelta(hours=settings.FORECAST_MAX_AGE_HOURS):
                hours = int(age.total_seconds() // 3600)
                reason = f"forecast generated {hours} h ago"
                if paused:
                    reason += "; refresh is paused, so it cannot be updated yet"
                return {"state": "stale", "reason": reason, **extra}
        return {"state": "available", "reason": None, **extra}

    def clear_cooldown(self) -> None:
        self._cooldown_cache = _UNSET
        if self.provider:
            self.cache.delete(COOLDOWN_KEY.format(provider=self.provider.name))

    def status(self) -> Dict[str, Any]:
        provider = self.provider
        payload = {"active_provider": settings.PREDICTION_PROVIDER, "configured": bool(provider and provider.is_configured()),
                   "integration_status": provider.integration_status if provider else None}
        if provider:
            budget = getattr(provider, "budget", None)
            payload["budget"] = budget.snapshot() if budget else None
            payload["last_sync"] = self.cache.get(STATUS_KEY.format(provider=provider.name))
            payload["cooling_down"] = self._cooldown_reason()
            try:
                payload["refresh_policy"] = self.policy.describe()
            except Exception as exc:  # pragma: no cover - a status payload is never worth an exception
                payload["refresh_policy"] = {"error": str(exc)}
        return payload
