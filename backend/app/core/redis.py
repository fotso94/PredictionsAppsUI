"""
Redis Client
Redis connection and utilities
"""

import redis
from typing import Optional
from app.core.config import settings

# Redis client instance
_redis_client: Optional[redis.Redis] = None


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
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    
    # If specific database requested, create new client
    if db is not None and db != settings.REDIS_DB:
        return redis.from_url(
            settings.REDIS_URL.rsplit('/', 1)[0] + f'/{db}',
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

