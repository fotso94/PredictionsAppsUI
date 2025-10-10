"""
Prediction Cache Service
Specialized caching for predictions, match data, and ML model outputs
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json
import logging

from app.services.cache import CacheService, predictions_cache, ml_models_cache, match_data_cache

logger = logging.getLogger(__name__)


class PredictionCacheService:
    """Prediction-specific caching operations"""
    
    def __init__(self):
        self.cache = predictions_cache
        self.ml_cache = ml_models_cache
        self.match_cache = match_data_cache
        self.default_ttl = 300  # 5 minutes
        self.match_ttl = 180  # 3 minutes for live match data
        self.ml_ttl = 600  # 10 minutes for ML predictions
    
    # Prediction Caching
    
    def cache_prediction(
        self,
        prediction_id: str,
        prediction_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache prediction data
        
        Args:
            prediction_id: Prediction ID
            prediction_data: Prediction data to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"pred:{prediction_id}"
        ttl = ttl or self.default_ttl
        
        # Add metadata
        prediction_data["cached_at"] = datetime.utcnow().isoformat()
        prediction_data["prediction_id"] = prediction_id
        
        return self.cache.set(key, prediction_data, ttl=ttl)
    
    def get_cached_prediction(self, prediction_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached prediction
        
        Args:
            prediction_id: Prediction ID
            
        Returns:
            Prediction data or None
        """
        key = f"pred:{prediction_id}"
        return self.cache.get(key)
    
    def invalidate_prediction(self, prediction_id: str) -> bool:
        """
        Invalidate cached prediction
        
        Args:
            prediction_id: Prediction ID
            
        Returns:
            True if deleted
        """
        key = f"pred:{prediction_id}"
        return self.cache.delete(key)
    
    # Match Predictions Caching
    
    def cache_match_predictions(
        self,
        match_id: str,
        predictions: List[Dict[str, Any]],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache all predictions for a match
        
        Args:
            match_id: Match ID
            predictions: List of predictions
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"match:{match_id}:predictions"
        ttl = ttl or self.default_ttl
        
        data = {
            "match_id": match_id,
            "predictions": predictions,
            "count": len(predictions),
            "cached_at": datetime.utcnow().isoformat()
        }
        
        return self.cache.set(key, data, ttl=ttl)
    
    def get_cached_match_predictions(self, match_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached predictions for a match
        
        Args:
            match_id: Match ID
            
        Returns:
            List of predictions or None
        """
        key = f"match:{match_id}:predictions"
        data = self.cache.get(key)
        
        if data and isinstance(data, dict):
            return data.get("predictions")
        return None
    
    def invalidate_match_predictions(self, match_id: str) -> bool:
        """
        Invalidate all predictions for a match
        
        Args:
            match_id: Match ID
            
        Returns:
            True if deleted
        """
        key = f"match:{match_id}:predictions"
        return self.cache.delete(key)
    
    # ML Model Predictions
    
    def cache_ml_prediction(
        self,
        match_id: str,
        model_version: str,
        ml_output: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache ML model prediction
        
        Args:
            match_id: Match ID
            model_version: ML model version
            ml_output: ML model output
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"ml:{model_version}:match:{match_id}"
        ttl = ttl or self.ml_ttl
        
        data = {
            "match_id": match_id,
            "model_version": model_version,
            "prediction": ml_output,
            "cached_at": datetime.utcnow().isoformat()
        }
        
        return self.ml_cache.set(key, data, ttl=ttl)
    
    def get_cached_ml_prediction(
        self,
        match_id: str,
        model_version: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached ML prediction
        
        Args:
            match_id: Match ID
            model_version: ML model version
            
        Returns:
            ML prediction or None
        """
        key = f"ml:{model_version}:match:{match_id}"
        data = self.ml_cache.get(key)
        
        if data and isinstance(data, dict):
            return data.get("prediction")
        return None
    
    def invalidate_ml_prediction(self, match_id: str, model_version: str) -> bool:
        """
        Invalidate ML prediction
        
        Args:
            match_id: Match ID
            model_version: ML model version
            
        Returns:
            True if deleted
        """
        key = f"ml:{model_version}:match:{match_id}"
        return self.ml_cache.delete(key)
    
    # Match Data Caching
    
    def cache_match_data(
        self,
        match_id: str,
        match_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache match data
        
        Args:
            match_id: Match ID
            match_data: Match data to cache
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        key = f"data:{match_id}"
        ttl = ttl or self.match_ttl
        
        # Add metadata
        match_data["cached_at"] = datetime.utcnow().isoformat()
        match_data["match_id"] = match_id
        
        return self.match_cache.set(key, match_data, ttl=ttl)
    
    def get_cached_match_data(self, match_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached match data
        
        Args:
            match_id: Match ID
            
        Returns:
            Match data or None
        """
        key = f"data:{match_id}"
        return self.match_cache.get(key)
    
    def invalidate_match_data(self, match_id: str) -> bool:
        """
        Invalidate cached match data
        
        Args:
            match_id: Match ID
            
        Returns:
            True if deleted
        """
        key = f"data:{match_id}"
        return self.match_cache.delete(key)
    
    # Batch Operations
    
    def cache_multiple_predictions(
        self,
        predictions: Dict[str, Dict[str, Any]],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Cache multiple predictions at once
        
        Args:
            predictions: Dictionary of prediction_id -> prediction_data
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        ttl = ttl or self.default_ttl
        
        # Prepare data with metadata
        cache_data = {}
        for pred_id, pred_data in predictions.items():
            pred_data["cached_at"] = datetime.utcnow().isoformat()
            pred_data["prediction_id"] = pred_id
            cache_data[f"pred:{pred_id}"] = pred_data
        
        return self.cache.set_many(cache_data, ttl=ttl)
    
    def get_multiple_predictions(
        self,
        prediction_ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get multiple predictions at once
        
        Args:
            prediction_ids: List of prediction IDs
            
        Returns:
            Dictionary of prediction_id -> prediction_data
        """
        keys = [f"pred:{pred_id}" for pred_id in prediction_ids]
        cached_data = self.cache.get_many(keys)
        
        # Remove key prefix from results
        result = {}
        for key, value in cached_data.items():
            pred_id = key.replace("pred:", "")
            result[pred_id] = value
        
        return result
    
    # Statistics and Monitoring
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Cache statistics
        """
        try:
            # Count keys by type
            pred_pattern = self.cache._make_key("pred:*")
            match_pattern = self.cache._make_key("match:*")
            
            pred_keys = self.cache.redis.keys(pred_pattern)
            match_keys = self.cache.redis.keys(match_pattern)
            
            ml_pattern = self.ml_cache._make_key("ml:*")
            ml_keys = self.ml_cache.redis.keys(ml_pattern)
            
            match_data_pattern = self.match_cache._make_key("data:*")
            match_data_keys = self.match_cache.redis.keys(match_data_pattern)
            
            return {
                "predictions_cached": len(pred_keys),
                "match_predictions_cached": len(match_keys),
                "ml_predictions_cached": len(ml_keys),
                "match_data_cached": len(match_data_keys),
                "total_cached": len(pred_keys) + len(match_keys) + len(ml_keys) + len(match_data_keys)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            return {
                "predictions_cached": 0,
                "match_predictions_cached": 0,
                "ml_predictions_cached": 0,
                "match_data_cached": 0,
                "total_cached": 0,
                "error": str(e)
            }
    
    def clear_all_predictions(self) -> int:
        """
        Clear all cached predictions
        
        Returns:
            Number of keys deleted
        """
        count = 0
        count += self.cache.delete_pattern("pred:*")
        count += self.cache.delete_pattern("match:*")
        count += self.ml_cache.delete_pattern("ml:*")
        count += self.match_cache.delete_pattern("data:*")
        return count


# Initialize prediction cache service
prediction_cache_service = PredictionCacheService()

