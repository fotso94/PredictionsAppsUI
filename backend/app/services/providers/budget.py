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
- Spending is attributed by `reason` (discovery / fetch / page / retry) in a parallel hash, so a
  plan that is being eaten by league discovery can be told apart from one eaten by real fetches.
  Attribution is best effort and never blocks or fails a request.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

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
REASONS = ("discovery", "fetch", "page", "retry")


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

    def can_afford(self, amount: int = 1) -> bool:
        """True when `amount` more requests fit in today's budget. Does not reserve anything."""
        if self._client is None:
            return self.fail_open
        if not self.daily_limit:
            return True
        return self.used_today() + amount <= self.daily_limit

    def consume(self, amount: int = 1, reason: str = "fetch") -> None:
        """Reserve `amount` outbound requests; raise ProviderQuotaError when the budget is spent.

        The counter is only advanced when the reservation succeeds, so a refusal never consumes
        allowance that was not actually spent at the provider.

        `reason` ("discovery", "fetch", "page", "retry") attributes the spending; it is recorded
        best effort and never changes whether the request is allowed. A request granted while the
        counter could not be written is NOT attributed - see `unmetered_today`.
        """
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
                f"({used}/{self.daily_limit} used)",
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
        counted, counter_readable = self._counter_read(self._usage_key())
        unmetered = self.unmetered_today()
        # Every outbound request today this process knows about. Reporting the counter alone turns
        # a day spent through a broken counter into an untouched allowance, which is the reading
        # that hid a 1,200/day ceiling disappearing at 00:00 and staying gone.
        used = counted + unmetered
        return {
            "provider": self.provider,
            "daily_limit": self.daily_limit,
            "used_today": used,
            #: What the shared counter itself holds, and what went out beside it uncounted.
            "counted_today": counted,
            "unmetered_today": unmetered,
            "refused_today": self.refused_today(),
            "remaining_today": max(self.daily_limit - used, 0) if self.daily_limit else None,
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
