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
- Spending is attributed by `reason` (discovery / fetch / page / retry) in a parallel hash, so a
  plan that is being eaten by league discovery can be told apart from one eaten by real fetches.
  Attribution is best effort and never blocks or fails a request.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

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

    def __init__(self, provider: str, daily_limit: int, client=None, fail_open: Optional[bool] = None):
        self.provider = provider
        self.daily_limit = max(int(daily_limit), 0)
        self._client = client if client is not None else _redis()
        #: What to do when the counter store is unreachable. Small plans refuse (fail closed);
        #: large ones proceed (fail open). An explicit value always wins.
        self.fail_open = (self.daily_limit > FAIL_OPEN_MIN_DAILY_LIMIT) if fail_open is None else bool(fail_open)
        if self._client is None and not self.fail_open:
            logger.warning("Request budget store unavailable for %s (%d/day): outbound requests will be "
                           "refused rather than spent unmetered", self.provider, self.daily_limit)

    def _counter(self, key: str) -> int:
        if self._client is None:
            return 0
        try:
            value = self._client.get(key)
            return int(value) if value else 0
        except Exception as exc:  # pragma: no cover
            logger.warning("Budget read failed for %s: %s", self.provider, exc)
            return 0

    def used_today(self) -> int:
        return self._counter(budget_key(self.provider))

    def refused_today(self) -> int:
        """Reservations refused because the budget was already spent (no request was sent)."""
        return self._counter(refused_key(self.provider))

    def remaining(self) -> int:
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
        best effort and never changes whether the request is allowed.
        """
        if self._client is None:
            if self.fail_open:
                return
            raise ProviderQuotaError("budget store unavailable; refusing outbound request",
                                     provider=self.provider)
        key = budget_key(self.provider)
        used, allowed = self._reserve(key, amount)
        if not allowed:
            raise ProviderQuotaError(
                f"Daily request budget for {self.provider} exhausted "
                f"({used}/{self.daily_limit} used)",
                provider=self.provider,
            )
        self._record_reason(reason, amount)

    def _record_reason(self, reason: str, amount: int) -> None:
        """Attribute a granted reservation to a reason. Best effort: never raises, never blocks."""
        if self._client is None:
            return
        field = reason if reason in REASONS else "other"
        key = by_reason_key(self.provider)
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
            raw = self._client.hgetall(by_reason_key(self.provider)) or {}
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

    def _reserve(self, key: str, amount: int):
        """Returns (usage_after_or_current, allowed). Atomic when the Redis client supports EVAL."""
        try:
            result = self._client.eval(_RESERVE_LUA, 2, key, refused_key(self.provider),
                                       amount, self.daily_limit, KEY_TTL_SECONDS)
            return int(result[0]), bool(int(result[1]))
        except ProviderQuotaError:  # pragma: no cover - defensive
            raise
        except Exception as exc:
            logger.debug("Budget EVAL unavailable for %s (%s); using non-atomic path", self.provider, exc)
        # Fallback for clients without EVAL (e.g. simple fakes in tests): check, then increment.
        try:
            used = self.used_today()
            if self.daily_limit and used + amount > self.daily_limit:
                try:
                    refused = self._client.incrby(refused_key(self.provider), amount)
                    if refused == amount:
                        self._client.expire(refused_key(self.provider), KEY_TTL_SECONDS)
                except Exception:  # pragma: no cover
                    pass
                return used, False
            new_value = self._client.incrby(key, amount)
            if new_value == amount:
                self._client.expire(key, KEY_TTL_SECONDS)
            return int(new_value), True
        except Exception as exc:
            # The store went away mid-flight. Same rule as a store that was never reachable:
            # a small plan refuses rather than spending the day's allowance unmetered.
            logger.warning("Budget update failed for %s: %s", self.provider, exc)
            if not self.fail_open:
                raise ProviderQuotaError("budget store unavailable; refusing outbound request",
                                         provider=self.provider) from exc
            return 0, True

    def snapshot(self) -> dict:
        used = self.used_today()
        return {
            "provider": self.provider,
            "daily_limit": self.daily_limit,
            "used_today": used,
            "refused_today": self.refused_today(),
            "remaining_today": max(self.daily_limit - used, 0) if self.daily_limit else None,
            "enforced": self._client is not None,
            "fail_open": self.fail_open,
            "by_reason": self.by_reason(),
        }
