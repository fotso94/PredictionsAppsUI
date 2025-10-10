"""
Session Cache Service
Specialized caching for user sessions, authentication tokens, and user data
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json
import logging

from app.services.cache import CacheService, sessions_cache
from app.core.config import settings

logger = logging.getLogger(__name__)


class SessionCacheService:
    """Session-specific caching operations"""
    
    def __init__(self):
        self.cache = sessions_cache
        self.default_ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
    
    # User Session Management
    
    def set_user_session(
        self,
        user_id: str,
        session_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store user session data
        
        Args:
            user_id: User ID
            session_data: Session data to cache
            ttl: Time to live in seconds (default: ACCESS_TOKEN_EXPIRE_MINUTES)
            
        Returns:
            True if successful
        """
        key = f"user:{user_id}:session"
        ttl = ttl or self.default_ttl
        
        # Add metadata
        session_data["cached_at"] = datetime.utcnow().isoformat()
        session_data["user_id"] = user_id
        
        return self.cache.set(key, session_data, ttl=ttl)
    
    def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user session data
        
        Args:
            user_id: User ID
            
        Returns:
            Session data or None
        """
        key = f"user:{user_id}:session"
        return self.cache.get(key)
    
    def delete_user_session(self, user_id: str) -> bool:
        """
        Delete user session
        
        Args:
            user_id: User ID
            
        Returns:
            True if deleted
        """
        key = f"user:{user_id}:session"
        return self.cache.delete(key)
    
    def extend_user_session(self, user_id: str, ttl: Optional[int] = None) -> bool:
        """
        Extend user session TTL
        
        Args:
            user_id: User ID
            ttl: New TTL in seconds
            
        Returns:
            True if successful
        """
        key = f"user:{user_id}:session"
        ttl = ttl or self.default_ttl
        return self.cache.expire(key, ttl)
    
    # Token Blacklist Management
    
    def blacklist_token(self, jti: str, ttl: int) -> bool:
        """
        Add token to blacklist
        
        Args:
            jti: JWT ID
            ttl: Time until token expires
            
        Returns:
            True if successful
        """
        key = f"blacklist:token:{jti}"
        return self.cache.set(key, "1", ttl=ttl)
    
    def is_token_blacklisted(self, jti: str) -> bool:
        """
        Check if token is blacklisted
        
        Args:
            jti: JWT ID
            
        Returns:
            True if blacklisted
        """
        key = f"blacklist:token:{jti}"
        return self.cache.exists(key)
    
    # Refresh Token Management
    
    def store_refresh_token(
        self,
        user_id: str,
        jti: str,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store refresh token
        
        Args:
            user_id: User ID
            jti: JWT ID
            ttl: Time to live (default: REFRESH_TOKEN_EXPIRE_MINUTES)
            
        Returns:
            True if successful
        """
        key = f"refresh:{user_id}:{jti}"
        ttl = ttl or (settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60)
        
        token_data = {
            "user_id": user_id,
            "jti": jti,
            "created_at": datetime.utcnow().isoformat()
        }
        
        return self.cache.set(key, token_data, ttl=ttl)
    
    def get_refresh_token(self, user_id: str, jti: str) -> Optional[Dict[str, Any]]:
        """
        Get refresh token data
        
        Args:
            user_id: User ID
            jti: JWT ID
            
        Returns:
            Token data or None
        """
        key = f"refresh:{user_id}:{jti}"
        return self.cache.get(key)
    
    def delete_refresh_token(self, user_id: str, jti: str) -> bool:
        """
        Delete refresh token
        
        Args:
            user_id: User ID
            jti: JWT ID
            
        Returns:
            True if deleted
        """
        key = f"refresh:{user_id}:{jti}"
        return self.cache.delete(key)
    
    def delete_all_user_refresh_tokens(self, user_id: str) -> int:
        """
        Delete all refresh tokens for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Number of tokens deleted
        """
        pattern = f"refresh:{user_id}:*"
        return self.cache.delete_pattern(pattern)
    
    # User Data Caching
    
    def cache_user_data(
        self,
        user_id: str,
        user_data: Dict[str, Any],
        ttl: int = 300  # 5 minutes default
    ) -> bool:
        """
        Cache user profile data
        
        Args:
            user_id: User ID
            user_data: User data to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"user:{user_id}:data"
        
        # Add metadata
        user_data["cached_at"] = datetime.utcnow().isoformat()
        
        return self.cache.set(key, user_data, ttl=ttl)
    
    def get_cached_user_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached user data
        
        Args:
            user_id: User ID
            
        Returns:
            User data or None
        """
        key = f"user:{user_id}:data"
        return self.cache.get(key)
    
    def invalidate_user_data(self, user_id: str) -> bool:
        """
        Invalidate cached user data
        
        Args:
            user_id: User ID
            
        Returns:
            True if deleted
        """
        key = f"user:{user_id}:data"
        return self.cache.delete(key)
    
    # User Permissions Caching
    
    def cache_user_permissions(
        self,
        user_id: str,
        permissions: List[str],
        ttl: int = 600  # 10 minutes default
    ) -> bool:
        """
        Cache user permissions
        
        Args:
            user_id: User ID
            permissions: List of permission strings
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"user:{user_id}:permissions"
        
        data = {
            "permissions": permissions,
            "cached_at": datetime.utcnow().isoformat()
        }
        
        return self.cache.set(key, data, ttl=ttl)
    
    def get_cached_user_permissions(self, user_id: str) -> Optional[List[str]]:
        """
        Get cached user permissions
        
        Args:
            user_id: User ID
            
        Returns:
            List of permissions or None
        """
        key = f"user:{user_id}:permissions"
        data = self.cache.get(key)
        
        if data and isinstance(data, dict):
            return data.get("permissions")
        return None
    
    def invalidate_user_permissions(self, user_id: str) -> bool:
        """
        Invalidate cached user permissions
        
        Args:
            user_id: User ID
            
        Returns:
            True if deleted
        """
        key = f"user:{user_id}:permissions"
        return self.cache.delete(key)
    
    # Session Statistics
    
    def get_active_sessions_count(self) -> int:
        """
        Get count of active sessions
        
        Returns:
            Number of active sessions
        """
        try:
            pattern = self.cache._make_key("user:*:session")
            keys = self.cache.redis.keys(pattern)
            return len(keys)
        except Exception as e:
            logger.error(f"Error getting active sessions count: {str(e)}")
            return 0
    
    def get_user_session_info(self, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive session info for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Session information
        """
        session_key = f"user:{user_id}:session"
        data_key = f"user:{user_id}:data"
        permissions_key = f"user:{user_id}:permissions"
        
        return {
            "has_session": self.cache.exists(session_key),
            "session_ttl": self.cache.get_ttl(session_key),
            "has_cached_data": self.cache.exists(data_key),
            "data_ttl": self.cache.get_ttl(data_key),
            "has_cached_permissions": self.cache.exists(permissions_key),
            "permissions_ttl": self.cache.get_ttl(permissions_key)
        }


# Initialize session cache service
session_cache_service = SessionCacheService()

