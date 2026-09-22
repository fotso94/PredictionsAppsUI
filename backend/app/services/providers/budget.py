"""
Daily request budget per provider, tracked in Redis.

The trial plans in use are small (Live Score API 1,500/day, GameForecastAPI 10/day), so the
backend refuses to call a provider once the configured daily budget is spent and serves cached
data instead. Without Redis the budget is not enforced (a warning is logged).

Accounting rules (owner requirement):
- The usage counter counts OUTBOUND requests only. A reservation that is refused because the
  budget is spent never reaches the provider, so it must not inflate the counter; refusals are
  counted separately under `:refused` for observability.
- A request that was sent and then failed (timeout, 5xx, auth error) still counts: the provider
  charged it against the plan.
- Counters are never reset to manufacture allowance. They are keyed by UTC day, which is when
  both providers reset, and expire on their own.
- When the counter store is unreachable, a SMALL plan fails CLOSED. A 10-requests/day plan that
  is spent blind is a plan that is gone; refusing the call and serving cached data is the cheaper
  failure. Large plans (Live Score API, 1,200/day) fail open so a Redis blip does not take the
  whole site's match data down. The threshold is a default, overridable per provider.
- "Unreachable" is decided by trying, not by guessing. A store that refuses EVAL but still answers
  GET/INCRBY is reachable, and a request it can count is a request that must be counted: the
  non-atomic path is weaker than the script, but it still keeps the ceiling, and not counting at
  all removes the ceiling for the rest of the day.
- A request that IS let out without being counted (fail open, store gone) is recorded in
  `unmetered_today()` and never attributed by reason: an attribution the usage counter never saw
  is a number the day cannot reconcile. `snapshot()` reports those requests as spent and drops
  `enforced` to false, so a degraded day never reads as an untouched allowance.
- Spending is attributed by `reason` (discovery / fetch / page / retry / calendar) in a parallel
  hash, so a plan that is being eaten by league discovery can be told apart from one eaten by
  real fetches. The label is the kind of call, not who made it: nothing here distinguishes a
  scheduled pass from a reader's page load. Attribution is best effort and never blocks or fails
  a request.
- The counter is OUR ceiling, keyed to OUR day. It is not the provider's window, and on
  2026-09-19 the two were shown not to be the same window at all: a clean UTC-day counter had
  five of eight left when the provider refused with "you have exceeded the DAILY quota". So the
  provider's own accounting - the rate-limit headers it returns on every response - is recorded
  beside the counter in `ProviderRateLimit`, and a request now goes out only when BOTH allow it.
  The configured ceiling is a cap we chose and it still holds; the provider's remaining count is
  a fact, and spending what it has already said is gone buys nothing. Where the provider said
  nothing, it stays unknown: unknown is never read as zero and never as a full allowance.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from app.services.providers.base import ProviderQuotaError

logger = logging.getLogger(__name__)

# Atomic check-and-increment: the counter only moves when the request is actually allowed out.
# KEYS[1] usage counter, KEYS[2] refused counter. ARGV: amount, limit, ttl.
# Returns {new_usage, allowed}
_RESERVE_LUA = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
if limit > 0 and (used + amount) > limit then
  local refused = redis.call('INCRBY', KEYS[2], amount)
  if refused == amount then redis.call('EXPIRE', KEYS[2], ttl) end
  return {used, 0}
end
local newv = redis.call('INCRBY', KEYS[1], amount)
if newv == amount then redis.call('EXPIRE', KEYS[1], ttl) end
return {newv, 1}
"""

KEY_TTL_SECONDS = 2 * 24 * 3600

#: Plans at or below this many requests a day are too small to spend blind: without the counter
#: store they refuse outbound requests instead of risking the whole day's allowance.
FAIL_OPEN_MIN_DAILY_LIMIT = 100

#: Recognised spending reasons, for attribution only (an unknown one is recorded as "other").
#: They name the KIND of call that spent, not the caller: a scheduled pass and a reader's page
#: load both fetch, and these counters cannot be split between them.
REASONS = ("discovery", "fetch", "page", "retry", "calendar")

#: "the caller passed nothing", kept apart from a caller that passed None meaning "unknown".
_UNSET = object()


def _redis():
    try:
        from app.core.redis import get_rate_limit_redis
        client = get_rate_limit_redis()
        client.ping()
        return client
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("Request budget disabled, Redis unavailable: %s", exc)
        return None


def budget_key(provider: str, day: Optional[datetime] = None) -> str:
    day = day or datetime.now(timezone.utc)
    return f"provider:budget:{provider}:{day.strftime('%Y%m%d')}"


def refused_key(provider: str, day: Optional[datetime] = None) -> str:
    return f"{budget_key(provider, day)}:refused"


def by_reason_key(provider: str, day: Optional[datetime] = None) -> str:
    return f"{budget_key(provider, day)}:by_reason"


# --------------------------------------------------------------------------- the provider's own view
#: NOT day-scoped, unlike every counter above: the whole point is that the provider's window is
#: not our day. One key per provider, overwritten by each reading and expiring on its own.
RATE_LIMIT_KEY = "provider:ratelimit:{provider}"

#: A reading is kept a little past the window it describes, so "the window just reset" is still
#: legible, and no longer: a remaining-count from a window that has rolled over is not a fact
#: about the current one.
RATE_LIMIT_GRACE_SECONDS = 15 * 60

#: How long a reading with no reset in it is kept. The provider told us a ceiling or a remaining
#: count but not when the window turns, so there is nothing to anchor a longer life to.
RATE_LIMIT_DEFAULT_TTL_SECONDS = 6 * 3600
RATE_LIMIT_MAX_TTL_SECONDS = 2 * 24 * 3600

#: How far the provider's reset may sit from the UTC midnight our counter is keyed to before the
#: two are called different windows. Small clock skew and a rounded seconds header are normal.
UTC_DAY_TOLERANCE_SECONDS = 10 * 60


def rate_limit_key(provider: str) -> str:
    return RATE_LIMIT_KEY.format(provider=provider)


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class ProviderRateLimit:
    """What the provider itself last said about its own window, per provider, in Redis.

    Redis rather than memory because the scheduler runs in-process and the backend is restarted:
    a reading held in a process that dies takes the only evidence of the provider's real window
    with it, and the next pass goes back to guessing UTC midnight.

    It stores one response's word and nothing more. There is no merging of a fresh remaining with
    an older ceiling, no inference of a window length from two readings, and no default for a
    header the provider never sent. Every accessor answers None for "the provider has not said",
    and None is propagated as unknown rather than collapsed into 0 or into a full allowance.
    """

    def __init__(self, provider: str, client=None, now=None):
        self.provider = provider
        self._client = client
        self._now = now

    @property
    def now(self) -> datetime:
        if self._now is None:
            return datetime.now(timezone.utc)
        return self._now() if callable(self._now) else self._now

    @property
    def key(self) -> str:
        return rate_limit_key(self.provider)

    # ------------------------------------------------------------------ write
    def record(self, reading) -> None:
        """Store one reading. Best effort: never raises, never blocks the request it came from.

        A reading with none of the three numbers in it is not stored and does not erase what is
        stored: a provider that sent no headers this time has not withdrawn what it said before.
        """
        if self._client is None or reading is None:
            return
        try:
            payload = reading.to_dict() if hasattr(reading, "to_dict") else dict(reading)
            if not any(payload.get(field) is not None
                       for field in ("limit", "remaining", "reset_seconds")):
                return
            reset_seconds = payload.get("reset_seconds")
            ttl = (int(reset_seconds) + RATE_LIMIT_GRACE_SECONDS) if isinstance(reset_seconds, int) \
                else RATE_LIMIT_DEFAULT_TTL_SECONDS
            ttl = max(min(ttl, RATE_LIMIT_MAX_TTL_SECONDS), 60)
            self._client.setex(self.key, ttl, json.dumps(payload))
        except Exception as exc:  # pragma: no cover - bookkeeping never fails a request
            logger.debug("Could not record the rate-limit reading for %s: %s", self.provider, exc)

    # ------------------------------------------------------------------ read
    def read(self) -> Optional[Dict[str, Any]]:
        """The stored reading, or None when the provider has never published a header to us."""
        if self._client is None:
            return None
        try:
            raw = self._client.get(self.key)
        except Exception as exc:  # pragma: no cover
            logger.debug("Could not read the rate-limit reading for %s: %s", self.provider, exc)
            return None
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "replace")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:  # pragma: no cover - a key someone else wrote
                return None
        return raw if isinstance(raw, dict) else None

    def reset_at(self) -> Optional[datetime]:
        stored = self.read()
        return _parse_iso(stored.get("reset_at")) if stored else None

    def seconds_until_reset(self) -> Optional[int]:
        """Seconds until the provider says its window turns, or None when it did not say.

        None also once that instant has passed: a reset in the past is not a reset to wait for.
        """
        reset_at = self.reset_at()
        if reset_at is None:
            return None
        seconds = int((reset_at - self.now).total_seconds())
        return seconds if seconds > 0 else None

    def window_expired(self, stored: Optional[Dict[str, Any]] = None) -> bool:
        """True when the window the stored reading described has already turned."""
        stored = stored if stored is not None else self.read()
        if not stored:
            return False
        reset_at = _parse_iso(stored.get("reset_at"))
        return reset_at is not None and reset_at <= self.now

    def remaining_now(self) -> Optional[int]:
        """What the provider says is left in its window right now, or None for "it did not say".

        Once the stored window has turned, the count it carried is no longer a fact about the
        current window, so this reads unknown again rather than keeping a stale zero - which
        would refuse requests for a window the provider has since reopened.
        """
        stored = self.read()
        if not stored or self.window_expired(stored):
            return None
        remaining = stored.get("remaining")
        return int(remaining) if isinstance(remaining, int) else None

    # ------------------------------------------------------------------ reporting
    def _utc_day_comparison(self, reset_at: Optional[datetime],
                            observed_at: Optional[datetime]) -> Tuple[Optional[bool], Optional[str]]:
        """Is the provider's window the UTC day our counter is keyed to? None when unknowable.

        This is the whole misalignment, made legible. Our counter's day ends at the UTC midnight
        after the response was observed; the provider's window ends when it says it does. When
        those are not the same instant, the counter is aligned to a clock the provider does not
        keep, and saying so beats letting a reader assume "used 3 of 8" explains a refusal.
        """
        if reset_at is None or observed_at is None:
            return None, None
        midnight = (observed_at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = int((reset_at - midnight).total_seconds())
        if abs(delta) <= UTC_DAY_TOLERANCE_SECONDS:
            return True, ("the provider's window resets within "
                          f"{UTC_DAY_TOLERANCE_SECONDS // 60} min of UTC midnight, which is the day "
                          "our counter is keyed to")
        hours, minutes = divmod(abs(delta) // 60, 60)
        direction = "after" if delta > 0 else "before"
        return False, (f"the provider's window resets at {reset_at.isoformat()}, "
                       f"{hours}h{minutes:02d}m {direction} the UTC midnight our daily counter is "
                       f"keyed to: the counter's day and the provider's window are different "
                       f"windows, so our used/limit figures cannot explain the provider's refusals")

    def snapshot(self) -> Dict[str, Any]:
        """The provider's own numbers for the status payload. Always says whether it knows.

        `known: false` is a statement, not a gap: it means no rate-limit header has ever reached
        this store for this provider, and the counter beside it is all there is.
        """
        stored = self.read()
        if not stored:
            return {"known": False, "limit": None, "remaining": None, "reset_at": None,
                    "reset_in_seconds": None, "observed_at": None, "observed_status": None,
                    "window_expired": None, "window_matches_utc_day": None,
                    "detail": ("this provider has never returned a rate-limit header to us (or the "
                               "last one has expired), so nothing is known about its own window")}
        reset_at = _parse_iso(stored.get("reset_at"))
        observed_at = _parse_iso(stored.get("observed_at"))
        expired = self.window_expired(stored)
        matches_day, note = self._utc_day_comparison(reset_at, observed_at)
        payload = {
            "known": True,
            "limit": stored.get("limit"),
            #: Deliberately `remaining_now()`, not the stored number: once the window has turned,
            #: what it held is no longer true of the window we are in.
            "remaining": None if expired else stored.get("remaining"),
            "remaining_as_observed": stored.get("remaining"),
            "reset_at": stored.get("reset_at"),
            "reset_in_seconds": self.seconds_until_reset(),
            "observed_at": stored.get("observed_at"),
            "observed_status": stored.get("observed_status"),
            "window_expired": expired,
            "window_matches_utc_day": matches_day,
        }
        if note:
            payload["window_note"] = note
        if expired:
            payload["detail"] = ("the window this reading described has already reset; its "
                                 "remaining count is no longer a fact about the current window")
        return payload


def record_rate_limit(reading) -> None:
    """Module-level sink used by :class:`ProviderHttpClient`. Never raises.

    It opens its own connection rather than borrowing a provider's, because the HTTP client is
    shared by providers that have no budget object at all.
    """
    provider = getattr(reading, "provider", None) or (reading or {}).get("provider")
    if not provider:
        return
    ProviderRateLimit(provider, client=_redis()).record(reading)


class RequestBudget:
    """Counts outbound requests per provider per UTC day."""

    def __init__(self, provider: str, daily_limit: int, client=None, fail_open: Optional[bool] = None,
                 now=None):
        self.provider = provider
        self.daily_limit = max(int(daily_limit), 0)
        self._client = client if client is not None else _redis()
        #: What to do when the counter store is unreachable. Small plans refuse (fail closed);
        #: large ones proceed (fail open). An explicit value always wins.
        self.fail_open = (self.daily_limit > FAIL_OPEN_MIN_DAILY_LIMIT) if fail_open is None else bool(fail_open)
        #: A datetime or a zero-argument callable; None means the real clock. Every counter key is
        #: day-scoped, so this is what lets a controlled clock cross a UTC day boundary and see the
        #: allowance come back - the same `now` seam SyncScheduler and the data services already have.
        self._now = now
        #: Requests this process let out today without the counter recording them, and the day key
        #: they belong to. In process because the counter store is exactly what is not working when
        #: they happen; day-scoped like every other counter, so a degraded hour never shadows
        #: tomorrow's allowance.
        self._unmetered_key: Optional[str] = None
        self._unmetered_count = 0
        #: The provider's own accounting, read from the same store and the same clock. Our
        #: ceiling and the provider's window are two independent constraints and both are checked.
        self.rate_limit = ProviderRateLimit(provider, client=self._client, now=self._now)
        if self._client is None and not self.fail_open:
            logger.warning("Request budget store unavailable for %s (%d/day): outbound requests will be "
                           "refused rather than spent unmetered", self.provider, self.daily_limit)

    @property
    def now(self) -> datetime:
        if self._now is None:
            return datetime.now(timezone.utc)
        return self._now() if callable(self._now) else self._now

    # The three counters for the budget day `now` falls in. Nothing reads yesterday's keys: at the
    # UTC boundary the old counters are not reset, they are simply abandoned (they expire on their
    # own), and the new day starts from a key that does not exist yet and therefore reads 0.
    def _usage_key(self) -> str:
        return budget_key(self.provider, self.now)

    def _refused_key(self) -> str:
        return refused_key(self.provider, self.now)

    def _reason_key(self) -> str:
        return by_reason_key(self.provider, self.now)

    def _counter_read(self, key: str) -> Tuple[int, bool]:
        """(value, whether the store actually answered).

        "The counter says 0" and "the counter did not answer" are the same number with opposite
        meanings, and only the reporting surface needs to tell them apart: a read that failed at
        report time is how a day that has been spending can still print a full allowance.
        """
        if self._client is None:
            return 0, False
        try:
            value = self._client.get(key)
            return (int(value) if value else 0), True
        except Exception as exc:  # pragma: no cover
            logger.warning("Budget read failed for %s: %s", self.provider, exc)
            return 0, False

    def _counter(self, key: str) -> int:
        """The counter, with an unreadable store answering 0 - what every scheduling caller wants."""
        return self._counter_read(key)[0]

    def used_today(self) -> int:
        return self._counter(self._usage_key())

    def refused_today(self) -> int:
        """Reservations refused because the budget was already spent (no request was sent)."""
        return self._counter(self._refused_key())

    def unmetered_today(self) -> int:
        """Requests granted today that the usage counter never recorded.

        A floor, not a total: this is what THIS process let out while the store could not be
        written, and another worker's unmetered grants live in its own memory. It exists so the
        reporting surface can say "the ceiling is not being enforced right now" instead of
        showing an allowance that looks untouched.
        """
        return self._unmetered_count if self._unmetered_key == self._usage_key() else 0

    def _note_unmetered(self, amount: int) -> None:
        key = self._usage_key()
        if key != self._unmetered_key:
            self._unmetered_key, self._unmetered_count = key, 0
        self._unmetered_count += int(amount)

    def remaining(self) -> int:
        """Allowance left according to the shared counter - the number scheduling decisions use.

        Deliberately the counter's own view: a fail-open provider must keep working through a
        Redis outage, which is the whole point of failing open. `snapshot()` is the reporting
        surface, and it subtracts the uncounted requests as well.
        """
        return max(self.daily_limit - self.used_today(), 0)

    # ------------------------------------------------------------------ the provider's own view
    def provider_remaining(self) -> Optional[int]:
        """What the provider says is left in ITS window, or None when it has never said.

        Never substituted for by our own counter, and never defaulted: None means unknown, and
        an unknown provider count constrains nothing.
        """
        try:
            return self.rate_limit.remaining_now()
        except Exception as exc:  # pragma: no cover - the provider's view is never worth a crash
            logger.debug("Provider rate-limit read failed for %s: %s", self.provider, exc)
            return None

    def remaining_effective(self) -> Optional[int]:
        """The binding number: the smaller of our remaining allowance and the provider's.

        Not a change to any limit. The configured ceiling is a cap we chose and it still refuses
        when it is the smaller number; the provider's count is a fact about what it will actually
        serve. Scheduling has to obey whichever is lower, because spending an allowance the
        provider has already said is gone buys a 429 and a 24-hour pause.

        None when neither side has a number - no configured ceiling and no header ever seen.
        """
        candidates = [value for value in (self.remaining() if self.daily_limit else None,
                                          self.provider_remaining()) if value is not None]
        return min(candidates) if candidates else None

    def limited_by(self, ours: Any = _UNSET, theirs: Any = _UNSET) -> str:
        """Which of the two constraints is currently the binding one. For reporting only.

        The two numbers can be passed in so a report describes exactly the figures it printed
        rather than re-reading counters that may have moved between two lines of one payload.
        """
        ours = (self.remaining() if self.daily_limit else None) if ours is _UNSET else ours
        theirs = self.provider_remaining() if theirs is _UNSET else theirs
        if ours is None and theirs is None:
            return "nothing"
        if theirs is None:
            return "our_configured_ceiling"
        if ours is None or theirs < ours:
            return "the_provider"
        if theirs == ours:
            return "both"
        return "our_configured_ceiling"

    def _provider_refusal(self, amount: int) -> Optional[str]:
        """Why the provider itself would refuse `amount` more requests, or None.

        Checked BEFORE our counter is touched, so a request the provider will not serve never
        advances our usage counter and never reaches the network.
        """
        theirs = self.provider_remaining()
        if theirs is None or theirs >= amount:
            return None
        reset_in = None
        try:
            reset_in = self.rate_limit.seconds_until_reset()
        except Exception:  # pragma: no cover
            pass
        when = f"; it says its window resets in {reset_in}s" if reset_in is not None else \
               "; it did not say when its window resets"
        return (f"{self.provider} itself reports {theirs} request(s) left in its own window, "
                f"which is fewer than the {amount} needed{when}. Our daily counter still shows "
                f"{self.remaining()} of {self.daily_limit} left, but the provider's window is not "
                f"our UTC day and its number is the one it will enforce")

    def can_afford(self, amount: int = 1) -> bool:
        """True when `amount` more requests fit - in today's budget AND in the provider's window.

        Both have to allow it. Either one saying no is a request that must not be sent: ours
        because it is the cap we chose, the provider's because it is what it will actually serve.
        """
        if self._provider_refusal(amount) is not None:
            return False
        if self._client is None:
            return self.fail_open
        if not self.daily_limit:
            return True
        return self.used_today() + amount <= self.daily_limit

    def consume(self, amount: int = 1, reason: str = "fetch") -> None:
        """Reserve `amount` outbound requests; raise ProviderQuotaError when the budget is spent.

        The counter is only advanced when the reservation succeeds, so a refusal never consumes
        allowance that was not actually spent at the provider.

        `reason` (see REASONS) attributes the spending by kind of call; it is recorded
        best effort and never changes whether the request is allowed. A request granted while the
        counter could not be written is NOT attributed - see `unmetered_today`.

        Two independent constraints, and the request goes out only when BOTH allow it. The
        provider's own remaining count is checked first and separately, so the refusal can say
        which of the two stopped the request: "our counter is spent" and "the provider says its
        window is spent while our counter still shows room" are different facts, and on
        2026-09-19 only the second one was true.
        """
        provider_refusal = self._provider_refusal(amount)
        if provider_refusal is not None:
            # Refused by the provider's own accounting, not by our ceiling. Nothing is sent, so
            # the usage counter must not move; the refusal is counted where every other refusal
            # is counted, so a day that never reached the network is still legible.
            self._note_refused(amount)
            raise ProviderQuotaError(provider_refusal, provider=self.provider)
        if self._client is None:
            if self.fail_open:
                self._note_unmetered(amount)
                return
            raise ProviderQuotaError("budget store unavailable; refusing outbound request",
                                     provider=self.provider)
        key = self._usage_key()
        used, allowed, metered = self._reserve(key, amount)
        if not allowed:
            raise ProviderQuotaError(
                f"Daily request budget for {self.provider} exhausted "
                f"({used}/{self.daily_limit} used); refused by the daily ceiling we configured, "
                f"not by the provider",
                provider=self.provider,
            )
        if not metered:
            # The request is going out, but the usage counter never saw it. Attributing it would
            # put a number in `by_reason` that nothing can be reconciled against - by_reason would
            # show spending on a day the counter reads as untouched. Record it as unmetered
            # instead, which is what `snapshot()` reports and what drops `enforced` to false.
            self._note_unmetered(amount)
            return
        self._record_reason(reason, amount)

    def _note_refused(self, amount: int) -> None:
        """Count a refusal the reserve script never saw. Best effort; never raises.

        The Lua reserve counts the refusals it makes itself. A request the provider's own
        accounting stopped never reaches that script, and leaving it uncounted would make a day
        of provider-side refusals look like a day nothing was attempted.
        """
        if self._client is None:
            return
        try:
            refused = self._client.incrby(self._refused_key(), amount)
            if refused == amount:
                self._client.expire(self._refused_key(), KEY_TTL_SECONDS)
        except Exception as exc:  # pragma: no cover
            logger.debug("Refusal count failed for %s: %s", self.provider, exc)

    def _record_reason(self, reason: str, amount: int) -> None:
        """Attribute a granted reservation to a reason. Best effort: never raises, never blocks."""
        if self._client is None:
            return
        field = reason if reason in REASONS else "other"
        key = self._reason_key()
        try:
            self._client.hincrby(key, field, amount)
            self._client.expire(key, KEY_TTL_SECONDS)
        except Exception as exc:  # pragma: no cover - attribution is never worth failing a request
            logger.debug("Budget reason attribution failed for %s/%s: %s", self.provider, field, exc)

    def by_reason(self) -> dict:
        """Today's granted requests per reason. Empty when unavailable."""
        if self._client is None:
            return {}
        try:
            raw = self._client.hgetall(self._reason_key()) or {}
        except Exception as exc:  # pragma: no cover
            logger.debug("Budget reason read failed for %s: %s", self.provider, exc)
            return {}
        result = {}
        for field, value in raw.items():
            name = field.decode("utf-8") if isinstance(field, (bytes, bytearray)) else str(field)
            try:
                result[name] = int(value)
            except (TypeError, ValueError):  # pragma: no cover
                continue
        return result

    def _store_unavailable(self, exc: Exception):
        """The counter store could not be used for this reservation at all.

        Reached only after the counting path has actually tried and failed, so "unavailable" here
        means the store did not answer a GET or an INCRBY - not merely that it declined EVAL.

        Same rule as a store that was never reachable: a small plan refuses rather than spending
        the day's allowance unmetered; a large one proceeds uncounted rather than taking the site
        down over a Redis blip. The grant it returns is NOT metered, and `consume` records it as
        such so it is never attributed and never reported as an untouched allowance.
        """
        if not self.fail_open:
            raise ProviderQuotaError("budget store unavailable; refusing outbound request",
                                     provider=self.provider) from exc
        return 0, True

    def _reserve(self, key: str, amount: int):
        """Returns (usage_after_or_current, allowed, metered).

        `metered` is False only when the request is being let out without the counter recording
        it; the caller must then not attribute it to a reason.

        Atomic whenever the client speaks EVAL, which every real redis-py client does, so the
        script is the path a healthy deployment takes: it checks the limit BEFORE it increments,
        so a refusal can never advance the usage counter.

        An EVAL that FAILS says nothing about whether the store itself is reachable - NOPERM on
        the command, a Cluster CROSSSLOT error and a dead connection all arrive here as one
        exception - so the counting path below is tried rather than assumed away. On a store that
        still answers GET and INCRBY it counts correctly, and the ceiling survives; on a store
        that answers nothing it raises, and only then is the store unavailable. Letting the
        failure pick the path is the difference between a plan that is metered non-atomically and
        a plan whose ceiling silently stops existing for the rest of the day.

        The non-atomic path is genuinely weaker: two concurrent reservations can read the same
        `used` and both proceed, so a limit can be overshot by the number of racing callers. That
        is bounded and visible in the counter. Not counting at all is unbounded and invisible.
        """
        evaluate = getattr(self._client, "eval", None)
        if callable(evaluate):
            try:
                result = evaluate(_RESERVE_LUA, 2, key, self._refused_key(),
                                  amount, self.daily_limit, KEY_TTL_SECONDS)
                return int(result[0]), bool(int(result[1])), True
            except ProviderQuotaError:  # pragma: no cover - defensive
                raise
            except Exception as exc:
                logger.warning("Atomic budget reservation failed for %s (%s); metering this "
                               "reservation with the non-atomic check-then-increment path",
                               self.provider, exc)
        # A client with no EVAL at all - the simple fakes in the test suite - lands here directly.
        return self._reserve_by_counting(key, amount)

    def _reserve_by_counting(self, key: str, amount: int):
        """Check the limit, then increment. Returns (usage, allowed, metered).

        Not atomic, so it is the fallback and never the first choice. It reads the counter
        directly rather than through `used_today()`, which swallows read errors and would report
        an unreachable store as an empty allowance.
        """
        try:
            raw = self._client.get(key)
            used = int(raw) if raw else 0
            if self.daily_limit and used + amount > self.daily_limit:
                try:
                    refused = self._client.incrby(self._refused_key(), amount)
                    if refused == amount:
                        self._client.expire(self._refused_key(), KEY_TTL_SECONDS)
                except Exception:  # pragma: no cover
                    pass
                return used, False, True
            new_value = self._client.incrby(key, amount)
            if new_value == amount:
                self._client.expire(key, KEY_TTL_SECONDS)
            return int(new_value), True, True
        except Exception as exc:
            logger.warning("Budget update failed for %s: %s", self.provider, exc)
            used, allowed = self._store_unavailable(exc)
            return used, allowed, False

    def snapshot(self) -> dict:
        """Our accounting and the provider's, side by side, so a divergence is legible.

        Every pre-existing key keeps its meaning: `used_today`, `remaining_today` and the rest
        are still OUR counter against OUR configured ceiling. What is added is what the provider
        itself said - under `provider_reported`, which always states whether anything is known -
        and the binding number of the two. On the night this was written our side read "3 of 8
        used, 5 left" and the provider's side read "0 left"; both were true, and only the second
        explained why the pass had stopped.

        Cost: one extra Redis GET per snapshot (the stored reading), on a payload that already
        reads three counters.
        """
        counted, counter_readable = self._counter_read(self._usage_key())
        unmetered = self.unmetered_today()
        # Every outbound request today this process knows about. Reporting the counter alone turns
        # a day spent through a broken counter into an untouched allowance, which is the reading
        # that hid a 1,200/day ceiling disappearing at 00:00 and staying gone.
        used = counted + unmetered
        ours_remaining = max(self.daily_limit - used, 0) if self.daily_limit else None
        provider_view = self.rate_limit.snapshot()
        theirs_remaining = provider_view.get("remaining") if provider_view.get("known") else None
        candidates = [v for v in (ours_remaining, theirs_remaining) if v is not None]
        return {
            "provider": self.provider,
            "daily_limit": self.daily_limit,
            "used_today": used,
            #: What the shared counter itself holds, and what went out beside it uncounted.
            "counted_today": counted,
            "unmetered_today": unmetered,
            "refused_today": self.refused_today(),
            "remaining_today": ours_remaining,
            #: The provider's own accounting, verbatim and never inferred. `known: false` says no
            #: rate-limit header has reached us; it is not a zero and not a full allowance.
            "provider_reported": provider_view,
            #: The smaller of the two, which is what the next request is actually measured
            #: against. None only when neither side has a number.
            "effective_remaining_today": min(candidates) if candidates else None,
            #: Which constraint is currently binding: our chosen cap, the provider's window, or
            #: both at the same figure. "nothing" means no ceiling and no header ever seen.
            "limited_by": self.limited_by(ours=ours_remaining, theirs=theirs_remaining),
            # The ceiling is only being enforced while every granted request is counted AND the
            # counter can still be read back. One uncounted grant and the limit is no longer
            # holding anything back; a counter that will not answer is a `used_today` of 0 that
            # means nothing, and pairing that with "enforced" is what let a spent day print an
            # untouched allowance. Either way, say false.
            "enforced": self._client is not None and not unmetered and counter_readable,
            "fail_open": self.fail_open,
            # A COUNTER above the ceiling cannot be produced by the accounting above: the reserve
            # refuses before it increments. It means the day's key carries a count this code did
            # not write - a counter left by an older build, or a hand-edited key - so say so
            # instead of leaving a reader to wonder how 9 of 8 requests were spent. Requests are
            # still refused; the number is flagged, never trimmed to make the limit look right.
            # Uncounted grants are excluded: those this code does know how it produced.
            "over_limit": bool(self.daily_limit) and counted > self.daily_limit,
            "by_reason": self.by_reason(),
        }
