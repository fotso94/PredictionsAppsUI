"""
Redis Client
Redis connection and utilities
"""

import redis
from typing import Any, List, Optional, Tuple
from app.core.config import settings

# Redis client instance
_redis_client: Optional[redis.Redis] = None

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
    config = settings if config is None else config
    if db is None or db == config.REDIS_DB:
        return config.REDIS_URL
    return config.REDIS_URL.rsplit('/', 1)[0] + f'/{db}'


def redis_targets_in_use(config: Any = None) -> List[Tuple[str, str, int, int]]:
    """(field, host, port, database) of every client this process can open: the default client
    and the six roles, as redis-py will read their URLs. Pure: nothing connects."""
    from redis.connection import parse_url

    config = settings if config is None else config
    targets = []
    for field, db in (("REDIS_DB", None),) + tuple((name, getattr(config, name)) for name in REDIS_ROLE_FIELDS):
        parsed = parse_url(redis_url_for(db, config))
        targets.append((field, parsed.get("host") or "localhost", int(parsed.get("port") or 6379),
                        int(parsed.get("db") or 0)))
    return targets


def get_redis_client(db: Optional[int] = None) -> redis.Redis:
    """
    Get Redis client
    
    Args:
        db: Redis database number (0-15). If None, uses default from settings.
    
    Returns:
        Redis client instance
    """
    global _redis_client
    
    if _redis_client is None:
        _redis_client = redis.from_url(
            redis_url_for(None),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    
    # If specific database requested, create new client
    if db is not None and db != settings.REDIS_DB:
        return redis.from_url(
            redis_url_for(db),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    
    return _redis_client


def get_sessions_redis() -> redis.Redis:
    """Get Redis client for sessions (DB 0)"""
    return get_redis_client(settings.REDIS_DB_SESSIONS)


def get_predictions_redis() -> redis.Redis:
    """Get Redis client for predictions cache (DB 1)"""
    return get_redis_client(settings.REDIS_DB_PREDICTIONS)


def get_expert_tools_redis() -> redis.Redis:
    """Get Redis client for expert tools cache (DB 2)"""
    return get_redis_client(settings.REDIS_DB_EXPERT_TOOLS)


def get_ml_models_redis() -> redis.Redis:
    """Get Redis client for ML model predictions cache (DB 3)"""
    return get_redis_client(settings.REDIS_DB_ML_MODELS)


def get_match_data_redis() -> redis.Redis:
    """Get Redis client for real-time match data (DB 4)"""
    return get_redis_client(settings.REDIS_DB_MATCH_DATA)


def get_rate_limit_redis() -> redis.Redis:
    """Get Redis client for API rate limiting (DB 5)"""
    return get_redis_client(settings.REDIS_DB_RATE_LIMIT)

