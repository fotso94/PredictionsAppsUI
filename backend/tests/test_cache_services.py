"""
Cache Services Tests
Tests for Redis caching layer including sessions and predictions
"""

import pytest
import time
from datetime import datetime

from app.services.cache import CacheService, sessions_cache, predictions_cache
from app.services.session_cache import SessionCacheService, session_cache_service
from app.services.prediction_cache import PredictionCacheService, prediction_cache_service


class TestCacheService:
    """Test base cache service"""
    
    def test_set_and_get_string(self):
        """Test setting and getting string value"""
        cache = sessions_cache
        key = "test:string"
        value = "test_value"
        
        # Set value
        assert cache.set(key, value, ttl=60) is True
        
        # Get value
        result = cache.get(key)
        assert result == value
        
        # Cleanup
        cache.delete(key)
    
    def test_set_and_get_dict(self):
        """Test setting and getting dictionary value"""
        cache = sessions_cache
        key = "test:dict"
        value = {"name": "test", "count": 42, "active": True}
        
        # Set value
        assert cache.set(key, value, ttl=60) is True
        
        # Get value
        result = cache.get(key)
        assert result == value
        assert result["name"] == "test"
        assert result["count"] == 42
        
        # Cleanup
        cache.delete(key)
    
    def test_delete(self):
        """Test deleting value"""
        cache = sessions_cache
        key = "test:delete"
        
        # Set and verify
        cache.set(key, "value", ttl=60)
        assert cache.exists(key) is True
        
        # Delete and verify
        assert cache.delete(key) is True
        assert cache.exists(key) is False
    
    def test_exists(self):
        """Test checking if key exists"""
        cache = sessions_cache
        key = "test:exists"
        
        # Should not exist initially
        assert cache.exists(key) is False
        
        # Set value
        cache.set(key, "value", ttl=60)
        
        # Should exist now
        assert cache.exists(key) is True
        
        # Cleanup
        cache.delete(key)
    
    def test_ttl_expiration(self):
        """Test TTL expiration"""
        cache = sessions_cache
        key = "test:ttl"
        
        # Set with 2 second TTL
        cache.set(key, "value", ttl=2)
        
        # Should exist immediately
        assert cache.exists(key) is True
        
        # Wait for expiration
        time.sleep(3)
        
        # Should not exist after TTL
        assert cache.exists(key) is False
    
    def test_get_many(self):
        """Test getting multiple values"""
        cache = sessions_cache
        keys = ["test:many:1", "test:many:2", "test:many:3"]
        values = {"key1": "value1", "key2": "value2", "key3": "value3"}
        
        # Set values
        for i, key in enumerate(keys, 1):
            cache.set(key, f"value{i}", ttl=60)
        
        # Get many
        result = cache.get_many(keys)
        assert len(result) == 3
        
        # Cleanup
        for key in keys:
            cache.delete(key)
    
    def test_set_many(self):
        """Test setting multiple values"""
        cache = sessions_cache
        data = {
            "test:batch:1": "value1",
            "test:batch:2": "value2",
            "test:batch:3": "value3"
        }
        
        # Set many
        assert cache.set_many(data, ttl=60) is True
        
        # Verify all set
        for key, value in data.items():
            assert cache.get(key) == value
        
        # Cleanup
        for key in data.keys():
            cache.delete(key)
    
    def test_increment_decrement(self):
        """Test increment and decrement"""
        cache = sessions_cache
        key = "test:counter"

        # Cleanup first to ensure clean state
        cache.delete(key)

        # Increment
        cache.increment(key, 1)
        assert cache.get(key) == 1

        cache.increment(key, 5)
        assert cache.get(key) == 6

        # Decrement
        cache.decrement(key, 2)
        assert cache.get(key) == 4

        # Cleanup
        cache.delete(key)


class TestSessionCacheService:
    """Test session cache service"""
    
    def test_set_and_get_user_session(self):
        """Test user session caching"""
        service = session_cache_service
        user_id = "test_user_123"
        session_data = {
            "email": "test@example.com",
            "role": "regular",
            "login_time": datetime.utcnow().isoformat()
        }
        
        # Set session
        assert service.set_user_session(user_id, session_data, ttl=60) is True
        
        # Get session
        result = service.get_user_session(user_id)
        assert result is not None
        assert result["email"] == "test@example.com"
        assert result["role"] == "regular"
        assert "cached_at" in result
        
        # Cleanup
        service.delete_user_session(user_id)
    
    def test_blacklist_token(self):
        """Test token blacklisting"""
        service = session_cache_service
        jti = "test_jti_123"
        
        # Should not be blacklisted initially
        assert service.is_token_blacklisted(jti) is False
        
        # Blacklist token
        assert service.blacklist_token(jti, ttl=60) is True
        
        # Should be blacklisted now
        assert service.is_token_blacklisted(jti) is True
        
        # Cleanup
        service.cache.delete(f"blacklist:token:{jti}")
    
    def test_refresh_token_management(self):
        """Test refresh token storage and retrieval"""
        service = session_cache_service
        user_id = "test_user_456"
        jti = "test_refresh_jti"
        
        # Store refresh token
        assert service.store_refresh_token(user_id, jti, ttl=60) is True
        
        # Get refresh token
        result = service.get_refresh_token(user_id, jti)
        assert result is not None
        assert result["user_id"] == user_id
        assert result["jti"] == jti
        
        # Delete refresh token
        assert service.delete_refresh_token(user_id, jti) is True
        
        # Should not exist anymore
        assert service.get_refresh_token(user_id, jti) is None
    
    def test_cache_user_data(self):
        """Test user data caching"""
        service = session_cache_service
        user_id = "test_user_789"
        user_data = {
            "id": user_id,
            "email": "user@example.com",
            "first_name": "Test",
            "last_name": "User"
        }
        
        # Cache user data
        assert service.cache_user_data(user_id, user_data, ttl=60) is True
        
        # Get cached data
        result = service.get_cached_user_data(user_id)
        assert result is not None
        assert result["email"] == "user@example.com"
        assert result["first_name"] == "Test"
        
        # Invalidate
        assert service.invalidate_user_data(user_id) is True
        assert service.get_cached_user_data(user_id) is None
    
    def test_cache_user_permissions(self):
        """Test user permissions caching"""
        service = session_cache_service
        user_id = "test_user_permissions"
        permissions = ["prediction:read", "analytics:view_basic"]
        
        # Cache permissions
        assert service.cache_user_permissions(user_id, permissions, ttl=60) is True
        
        # Get cached permissions
        result = service.get_cached_user_permissions(user_id)
        assert result is not None
        assert len(result) == 2
        assert "prediction:read" in result
        
        # Invalidate
        assert service.invalidate_user_permissions(user_id) is True
        assert service.get_cached_user_permissions(user_id) is None


class TestPredictionCacheService:
    """Test prediction cache service"""
    
    def test_cache_prediction(self):
        """Test prediction caching"""
        service = prediction_cache_service
        prediction_id = "pred_123"
        prediction_data = {
            "match_id": "match_456",
            "home_win_prob": 0.45,
            "draw_prob": 0.30,
            "away_win_prob": 0.25
        }
        
        # Cache prediction
        assert service.cache_prediction(prediction_id, prediction_data, ttl=60) is True
        
        # Get cached prediction
        result = service.get_cached_prediction(prediction_id)
        assert result is not None
        assert result["match_id"] == "match_456"
        assert result["home_win_prob"] == 0.45
        
        # Invalidate
        assert service.invalidate_prediction(prediction_id) is True
        assert service.get_cached_prediction(prediction_id) is None
    
    def test_cache_match_predictions(self):
        """Test match predictions caching"""
        service = prediction_cache_service
        match_id = "match_789"
        predictions = [
            {"source": "ml", "confidence": 0.75},
            {"source": "expert", "confidence": 0.85}
        ]
        
        # Cache match predictions
        assert service.cache_match_predictions(match_id, predictions, ttl=60) is True
        
        # Get cached predictions
        result = service.get_cached_match_predictions(match_id)
        assert result is not None
        assert len(result) == 2
        assert result[0]["source"] == "ml"
        
        # Invalidate
        assert service.invalidate_match_predictions(match_id) is True
        assert service.get_cached_match_predictions(match_id) is None
    
    def test_cache_ml_prediction(self):
        """Test ML prediction caching"""
        service = prediction_cache_service
        match_id = "match_ml_123"
        model_version = "v1.0.0"
        ml_output = {
            "home_win": 0.50,
            "draw": 0.30,
            "away_win": 0.20,
            "confidence": 0.80
        }
        
        # Cache ML prediction
        assert service.cache_ml_prediction(match_id, model_version, ml_output, ttl=60) is True
        
        # Get cached ML prediction
        result = service.get_cached_ml_prediction(match_id, model_version)
        assert result is not None
        assert result["home_win"] == 0.50
        assert result["confidence"] == 0.80
        
        # Invalidate
        assert service.invalidate_ml_prediction(match_id, model_version) is True
        assert service.get_cached_ml_prediction(match_id, model_version) is None
    
    def test_get_cache_stats(self):
        """Test cache statistics"""
        service = prediction_cache_service
        
        # Get stats
        stats = service.get_cache_stats()
        assert "predictions_cached" in stats
        assert "match_predictions_cached" in stats
        assert "ml_predictions_cached" in stats
        assert "total_cached" in stats

