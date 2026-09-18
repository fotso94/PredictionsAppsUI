"""JSON cache for provider data in Redis (DB 4), with a long-lived stale copy for graceful degradation."""

from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

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

    def keys(self, pattern: str) -> List[str]:
        """Cache keys matching a glob, base keys only (the parallel `:stale` copies are omitted).

        SCAN is used rather than KEYS so a large cache is never blocked.
        """
        client = self._redis()
        if client is None:
            return []
        found = []
        try:
            for raw in client.scan_iter(match=pattern, count=200):
                key = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
                if not key.endswith(":stale"):
                    found.append(key)
        except Exception as exc:  # pragma: no cover
            logger.warning("Cache scan failed (%s): %s", pattern, exc)
        return found

    def delete_pattern(self, pattern: str) -> int:
        """Drop every cached entry matching a glob, with its stale copy. Returns how many were removed.

        Used when stored data changes underneath the cache - an expert publishing a prediction, or a
        forecast repair - so the public pages never keep serving the superseded payload.
        """
        keys = self.keys(pattern)
        for key in keys:
            self.delete(key)
        if keys:
            logger.info("Cache invalidated: %d entries matching %s", len(keys), pattern)
        return len(keys)
