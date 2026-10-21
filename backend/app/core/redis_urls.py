"""
The URL each Redis client connects with - pure string building, with no import of the settings at
module level.

It lives apart from app/core/redis.py so that the isolation preflight (app/core/target_guard.py)
can judge exactly these URLs from inside the settings module's own import: under pytest,
app/core/config.py runs the preflight as soon as `settings` exists, and when the first module to
import the settings is app/core/redis.py (tests/test_cache_services.py, through the caches), that
module is still half-built at that moment. Nothing here imports it back, so the preflight never
meets a partly initialised module (2026-10-21 review: it did, and the run ended in an ImportError
at collection - stopped, but not refused).
"""

from typing import Any, Optional

#: The six role databases (app/core/config.py, "Redis Database Allocation").
REDIS_ROLE_FIELDS = ("REDIS_DB_SESSIONS", "REDIS_DB_PREDICTIONS", "REDIS_DB_EXPERT_TOOLS",
                     "REDIS_DB_ML_MODELS", "REDIS_DB_MATCH_DATA", "REDIS_DB_RATE_LIMIT")
LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def redis_url_for(db: Optional[int] = None, config: Any = None) -> str:
    """The URL get_redis_client(db) connects with. Pure: it only builds a string.

    No database, or REDIS_DB itself, is the default client: REDIS_URL as it stands, whose own path
    names the database it really serves. Any other database is REDIS_URL with its last path
    segment replaced. The isolation preflight (app.core.target_guard) judges exactly these URLs.
    """
    if config is None:
        from app.core.config import settings as config
    if db is None or db == config.REDIS_DB:
        return config.REDIS_URL
    return config.REDIS_URL.rsplit('/', 1)[0] + f'/{db}'
