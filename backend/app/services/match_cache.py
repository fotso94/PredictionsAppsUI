"""JSON cache for provider data in Redis (DB 4), with a long-lived stale copy for graceful degradation."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

STALE_TTL_SECONDS = 24 * 3600


class MatchCache:
    def __init__(self, client=None):
        self._client = client
        self._checked = client is not None

    def _redis(self):
        if not self._checked:
            self._checked = True
            try:
                from app.core.redis import get_match_data_redis
                client = get_match_data_redis()
                client.ping()
                self._client = client
            except Exception as exc:  # pragma: no cover - environment dependent
                logger.warning("Match cache disabled, Redis unavailable: %s", exc)
                self._client = None
        return self._client

    @property
    def available(self) -> bool:
        return self._redis() is not None

    def get(self, key: str) -> Optional[Any]:
        client = self._redis()
        if client is None:
            return None
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache read failed (%s): %s", key, exc)
            return None

    def get_stale(self, key: str) -> Optional[Any]:
        return self.get(f"{key}:stale")

    def set(self, key: str, value: Any, ttl: int, stale_ttl: int = STALE_TTL_SECONDS) -> None:
        client = self._redis()
        if client is None:
            return
        try:
            payload = json.dumps(value, default=str)
            client.setex(key, max(int(ttl), 1), payload)
            client.setex(f"{key}:stale", max(int(stale_ttl), 1), payload)
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache write failed (%s): %s", key, exc)

    def delete(self, key: str) -> None:
        client = self._redis()
        if client is None:
            return
        try:
            client.delete(key, f"{key}:stale")
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache delete failed (%s): %s", key, exc)
