"""
Cache Service
Comprehensive Redis caching utilities for sessions, predictions, and general data
"""

import json
import hashlib
import logging
from typing import Any, Optional, Callable, Dict, List
from functools import wraps
from datetime import datetime, timedelta
import redis

from app.core.redis import (
    get_sessions_redis,
    get_predictions_redis,
    get_expert_tools_redis,
    get_ml_models_redis,
    get_match_data_redis,
    get_rate_limit_redis
)

logger = logging.getLogger(__name__)


class CacheService:
    """Base cache service with common operations"""
    
    def __init__(self, redis_client: redis.Redis, prefix: str = ""):
        """
        Initialize cache service
        
        Args:
            redis_client: Redis client instance
            prefix: Key prefix for namespacing
        """
        self.redis = redis_client
        self.prefix = prefix
    
    def _make_key(self, key: str) -> str:
        """Create namespaced cache key"""
        return f"{self.prefix}:{key}" if self.prefix else key
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found
        """
        try:
            cache_key = self._make_key(key)
            value = self.redis.get(cache_key)
            
            if value is None:
                return None
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {str(e)}")
            return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None = no expiration)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._make_key(key)
            
            # Serialize value if not string
            if not isinstance(value, str):
                value = json.dumps(value, default=str)
            
            if ttl:
                return self.redis.setex(cache_key, ttl, value)
            else:
                return self.redis.set(cache_key, value)
                
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {str(e)}")
            return False
    
    def delete(self, key: str) -> bool:
        """
        Delete value from cache
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            cache_key = self._make_key(key)
            return bool(self.redis.delete(cache_key))
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {str(e)}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists in cache
        
        Args:
            key: Cache key
            
        Returns:
            True if exists, False otherwise
        """
        try:
            cache_key = self._make_key(key)
            return bool(self.redis.exists(cache_key))
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {str(e)}")
            return False
    
    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values from cache
        
        Args:
            keys: List of cache keys
            
        Returns:
            Dictionary of key-value pairs
        """
        try:
            cache_keys = [self._make_key(k) for k in keys]
            values = self.redis.mget(cache_keys)
            
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        result[key] = value
            
            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {str(e)}")
            return {}
    
    def set_many(
        self,
        mapping: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set multiple values in cache
        
        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            pipe = self.redis.pipeline()
            
            for key, value in mapping.items():
                cache_key = self._make_key(key)
                if not isinstance(value, str):
                    value = json.dumps(value, default=str)
                
                if ttl:
                    pipe.setex(cache_key, ttl, value)
                else:
                    pipe.set(cache_key, value)
            
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Cache set_many error: {str(e)}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern
        
        Args:
            pattern: Key pattern (supports wildcards)
            
        Returns:
            Number of keys deleted
        """
        try:
            cache_pattern = self._make_key(pattern)
            keys = self.redis.keys(cache_pattern)
            
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache delete_pattern error for pattern {pattern}: {str(e)}")
            return 0
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment counter
        
        Args:
            key: Cache key
            amount: Amount to increment by
            
        Returns:
            New value or None on error
        """
        try:
            cache_key = self._make_key(key)
            return self.redis.incrby(cache_key, amount)
        except Exception as e:
            logger.error(f"Cache increment error for key {key}: {str(e)}")
            return None
    
    def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Decrement counter
        
        Args:
            key: Cache key
            amount: Amount to decrement by
            
        Returns:
            New value or None on error
        """
        try:
            cache_key = self._make_key(key)
            return self.redis.decrby(cache_key, amount)
        except Exception as e:
            logger.error(f"Cache decrement error for key {key}: {str(e)}")
            return None
    
    def get_ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for key
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        try:
            cache_key = self._make_key(key)
            return self.redis.ttl(cache_key)
        except Exception as e:
            logger.error(f"Cache get_ttl error for key {key}: {str(e)}")
            return None
    
    def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration on existing key
        
        Args:
            key: Cache key
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            cache_key = self._make_key(key)
            return bool(self.redis.expire(cache_key, ttl))
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {str(e)}")
            return False


# Initialize cache services
sessions_cache = CacheService(get_sessions_redis(), prefix="session")
predictions_cache = CacheService(get_predictions_redis(), prefix="prediction")
expert_tools_cache = CacheService(get_expert_tools_redis(), prefix="expert")
ml_models_cache = CacheService(get_ml_models_redis(), prefix="ml")
match_data_cache = CacheService(get_match_data_redis(), prefix="match")
rate_limit_cache = CacheService(get_rate_limit_redis(), prefix="ratelimit")


class UserCacheService:
    """User-specific cache operations"""

    def __init__(self):
        self.cache = sessions_cache

    def delete_user_cache(self, user_id: str) -> int:
        """Delete all cache entries for a user"""
        pattern = f"user:{user_id}:*"
        return self.cache.delete_pattern(pattern)

    def get_user_profile(self, user_id: str):
        """Get cached user profile"""
        return self.cache.get(f"user:{user_id}:profile")

    def set_user_profile(self, user_id: str, profile_data: dict, ttl: int = 300):
        """Cache user profile"""
        return self.cache.set(f"user:{user_id}:profile", profile_data, ttl=ttl)


# Global instance
cache_service = UserCacheService()


def cached(
    cache_service: CacheService,
    key_prefix: str = "",
    ttl: int = 300,
    key_builder: Optional[Callable] = None
):
    """
    Decorator to cache function results

    Args:
        cache_service: Cache service to use
        key_prefix: Prefix for cache key
        ttl: Time to live in seconds
        key_builder: Custom function to build cache key from args/kwargs

    Example:
        @cached(predictions_cache, key_prefix="match_pred", ttl=600)
        def get_match_predictions(match_id: str):
            # Expensive operation
            return predictions
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                # Default: use function name and arguments
                args_str = "_".join(str(arg) for arg in args)
                kwargs_str = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = f"{key_prefix}:{func.__name__}:{args_str}:{kwargs_str}"

            # Try to get from cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_result

            # Execute function
            logger.debug(f"Cache miss for key: {cache_key}")
            result = func(*args, **kwargs)

            # Store in cache
            cache_service.set(cache_key, result, ttl=ttl)

            return result

        return wrapper
    return decorator


def cache_invalidate(
    cache_service: CacheService,
    key_pattern: str
):
    """
    Decorator to invalidate cache after function execution

    Args:
        cache_service: Cache service to use
        key_pattern: Pattern of keys to invalidate

    Example:
        @cache_invalidate(predictions_cache, key_pattern="match_pred:*")
        def update_prediction(prediction_id: str, data: dict):
            # Update prediction
            return updated_prediction
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Execute function
            result = func(*args, **kwargs)

            # Invalidate cache
            deleted = cache_service.delete_pattern(key_pattern)
            logger.debug(f"Invalidated {deleted} cache keys matching pattern: {key_pattern}")

            return result

        return wrapper
    return decorator

