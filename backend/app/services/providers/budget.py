"""
Daily request budget per provider, tracked in Redis.

The trial plans in use are small (Live Score API 1,500/day, GameForecastAPI 10/day), so the
backend refuses to call a provider once the configured daily budget is spent and serves cached
data instead. Without Redis the budget is not enforced (a warning is logged).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.services.providers.base import ProviderQuotaError

logger = logging.getLogger(__name__)


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


class RequestBudget:
    """Counts outbound requests per provider per UTC day."""

    def __init__(self, provider: str, daily_limit: int, client=None):
        self.provider = provider
        self.daily_limit = max(int(daily_limit), 0)
        self._client = client if client is not None else _redis()

    def used_today(self) -> int:
        if self._client is None:
            return 0
        try:
            value = self._client.get(budget_key(self.provider))
            return int(value) if value else 0
        except Exception as exc:  # pragma: no cover
            logger.warning("Budget read failed for %s: %s", self.provider, exc)
            return 0

    def remaining(self) -> int:
        return max(self.daily_limit - self.used_today(), 0)

    def consume(self, amount: int = 1) -> None:
        """Reserve `amount` requests; raise ProviderQuotaError when the budget is spent."""
        if self._client is None:
            return
        key = budget_key(self.provider)
        try:
            new_value = self._client.incrby(key, amount)
            if new_value == amount:
                self._client.expire(key, 2 * 24 * 3600)
        except Exception as exc:  # pragma: no cover
            logger.warning("Budget update failed for %s: %s", self.provider, exc)
            return
        if self.daily_limit and new_value > self.daily_limit:
            raise ProviderQuotaError(
                f"Daily request budget for {self.provider} exhausted "
                f"({new_value - amount}/{self.daily_limit} used)",
                provider=self.provider,
            )

    def snapshot(self) -> dict:
        used = self.used_today()
        return {
            "provider": self.provider,
            "daily_limit": self.daily_limit,
            "used_today": used,
            "remaining_today": max(self.daily_limit - used, 0) if self.daily_limit else None,
            "enforced": self._client is not None,
        }
