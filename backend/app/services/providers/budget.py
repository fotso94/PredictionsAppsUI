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


class RequestBudget:
    """Counts outbound requests per provider per UTC day."""

    def __init__(self, provider: str, daily_limit: int, client=None):
        self.provider = provider
        self.daily_limit = max(int(daily_limit), 0)
        self._client = client if client is not None else _redis()

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
        if self._client is None or not self.daily_limit:
            return True
        return self.used_today() + amount <= self.daily_limit

    def consume(self, amount: int = 1) -> None:
        """Reserve `amount` outbound requests; raise ProviderQuotaError when the budget is spent.

        The counter is only advanced when the reservation succeeds, so a refusal never consumes
        allowance that was not actually spent at the provider.
        """
        if self._client is None:
            return
        key = budget_key(self.provider)
        used, allowed = self._reserve(key, amount)
        if not allowed:
            raise ProviderQuotaError(
                f"Daily request budget for {self.provider} exhausted "
                f"({used}/{self.daily_limit} used)",
                provider=self.provider,
            )

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
        except Exception as exc:  # pragma: no cover
            logger.warning("Budget update failed for %s: %s", self.provider, exc)
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
        }
