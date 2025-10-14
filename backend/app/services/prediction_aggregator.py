"""
Prediction Aggregator Service

Implements multi-source prediction priority system with waterfall logic.
Selects the highest priority prediction based on user tier and availability.

Priority Levels:
- Expert predictions: 100
- Admin predictions: 90
- LLM predictions: 50
- ML baseline (legacy): 40
- API-Football predictions: 25
- Randomized default: 0
"""

import random
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc

from app.models.predictions import Prediction, PredictionSource, PredictionStatus
from app.models.users import SubscriptionTier
from app.services.prediction_cache import PredictionCacheService

logger = logging.getLogger(__name__)


class PredictionAggregatorService:
    """
    Aggregates predictions from multiple sources with priority-based selection.
    
    Implements waterfall logic:
    1. Check for highest priority stored prediction (Expert/LLM/ML)
    2. Fall back to API-Football (via cache or API call)
    3. Generate randomized prediction as last resort
    """
    
    # Priority levels for each source
    PRIORITY_LEVELS = {
        PredictionSource.EXPERT_MANUAL: 100,
        PredictionSource.EXPERT_OVERRIDE: 100,
        PredictionSource.ADMIN_MANUAL: 90,
        PredictionSource.LLM_GENERATED: 50,
        PredictionSource.ML_BASELINE: 40,
        PredictionSource.API_FOOTBALL_BASELINE: 25,
        PredictionSource.DEFAULT_RANDOMIZED: 0,
    }
    
    # Tier-based access control
    TIER_ACCESS = {
        SubscriptionTier.FREE: [
            PredictionSource.API_FOOTBALL_BASELINE,
            PredictionSource.DEFAULT_RANDOMIZED,
        ],
        SubscriptionTier.PREMIUM: [
            PredictionSource.EXPERT_MANUAL,
            PredictionSource.EXPERT_OVERRIDE,
            PredictionSource.LLM_GENERATED,
            PredictionSource.API_FOOTBALL_BASELINE,
            PredictionSource.DEFAULT_RANDOMIZED,
        ],
        SubscriptionTier.PRO: [
            PredictionSource.EXPERT_MANUAL,
            PredictionSource.EXPERT_OVERRIDE,
            PredictionSource.ADMIN_MANUAL,
            PredictionSource.LLM_GENERATED,
            PredictionSource.ML_BASELINE,
            PredictionSource.API_FOOTBALL_BASELINE,
            PredictionSource.DEFAULT_RANDOMIZED,
        ],
    }
    
    def __init__(self, db: Session, cache_service: Optional[PredictionCacheService] = None):
        """
        Initialize PredictionAggregatorService
        
        Args:
            db: Database session
            cache_service: Optional cache service (defaults to PredictionCacheService)
        """
        self.db = db
        self.cache_service = cache_service or PredictionCacheService()
    
    def get_prediction_for_match(
        self,
        match_id: str,
        user_tier: SubscriptionTier = SubscriptionTier.FREE,
        market_type: str = "match_winner"
    ) -> Optional[Dict[str, Any]]:
        """
        Get the highest priority prediction for a match based on user tier.
        
        Implements waterfall logic:
        1. Check cache for stored prediction
        2. Query database for highest priority stored prediction
        3. Fall back to API-Football (via cache or API)
        4. Generate randomized prediction as last resort
        
        Args:
            match_id: Match ID
            user_tier: User's subscription tier
            market_type: Market type (default: "match_winner")
        
        Returns:
            Prediction dict with probabilities, source, confidence, etc.
        """
        logger.info(f"Getting prediction for match {match_id}, tier={user_tier.value}, market={market_type}")
        
        # 1. Check cache first
        cache_key = f"prediction:{match_id}:{user_tier.value}:{market_type}"
        cached_prediction = self.cache_service.get_cached_prediction(cache_key)
        if cached_prediction:
            logger.info(f"Cache hit for {cache_key}")
            return cached_prediction
        
        # 2. Get highest priority stored prediction from database
        stored_prediction = self._get_highest_priority_stored(match_id, user_tier, market_type)
        if stored_prediction:
            prediction_dict = self._prediction_to_dict(stored_prediction)
            # Cache for 5 minutes
            self.cache_service.cache_prediction(cache_key, prediction_dict, ttl=300)
            return prediction_dict
        
        # 3. Fall back to API-Football prediction (if tier allows)
        if PredictionSource.API_FOOTBALL_BASELINE in self.TIER_ACCESS.get(user_tier, []):
            api_prediction = self._get_api_football_prediction(match_id, market_type)
            if api_prediction:
                # Cache for 5 minutes
                self.cache_service.cache_prediction(cache_key, api_prediction, ttl=300)
                return api_prediction
        
        # 4. Generate randomized prediction as last resort
        logger.warning(f"No predictions available for match {match_id}, generating randomized prediction")
        randomized_prediction = self._generate_randomized_prediction(match_id, market_type)
        # Cache for 5 minutes
        self.cache_service.cache_prediction(cache_key, randomized_prediction, ttl=300)
        return randomized_prediction
    
    def get_all_predictions_for_match(
        self,
        match_id: str,
        market_type: str = "match_winner"
    ) -> List[Dict[str, Any]]:
        """
        Get ALL predictions for a match (Pro tier only).
        
        Returns predictions from all sources, ordered by priority.
        
        Args:
            match_id: Match ID
            market_type: Market type (default: "match_winner")
        
        Returns:
            List of prediction dicts ordered by priority (highest first)
        """
        logger.info(f"Getting all predictions for match {match_id}, market={market_type}")
        
        # Query all published predictions for this match
        predictions = self.db.query(Prediction).filter(
            and_(
                Prediction.match_id == match_id,
                Prediction.status == PredictionStatus.PUBLISHED,
                Prediction.deleted_at.is_(None)
            )
        ).order_by(
            desc(Prediction.priority_level),
            desc(Prediction.published_at)
        ).all()
        
        return [self._prediction_to_dict(p) for p in predictions]
    
    def _get_highest_priority_stored(
        self,
        match_id: str,
        user_tier: SubscriptionTier,
        market_type: str
    ) -> Optional[Prediction]:
        """
        Get the highest priority stored prediction from database.
        
        Filters by:
        - Match ID
        - User tier access
        - Published status
        - Not deleted
        - Not superseded
        
        Args:
            match_id: Match ID
            user_tier: User's subscription tier
            market_type: Market type
        
        Returns:
            Highest priority Prediction or None
        """
        # Get allowed sources for this tier
        allowed_sources = self.TIER_ACCESS.get(user_tier, [])
        
        # Query highest priority prediction
        prediction = self.db.query(Prediction).filter(
            and_(
                Prediction.match_id == match_id,
                Prediction.source.in_(allowed_sources),
                Prediction.status == PredictionStatus.PUBLISHED,
                Prediction.deleted_at.is_(None),
                Prediction.superseded_by.is_(None)  # Not superseded
            )
        ).order_by(
            desc(Prediction.priority_level),
            desc(Prediction.published_at)
        ).first()
        
        return prediction
    
    def _get_api_football_prediction(
        self,
        match_id: str,
        market_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get prediction from API-Football (via cache or API call).
        
        This is a placeholder - actual implementation would call API-Football API.
        
        Args:
            match_id: Match ID
            market_type: Market type
        
        Returns:
            Prediction dict or None
        """
        # TODO: Implement actual API-Football API call
        # For now, return None to trigger randomized fallback
        logger.info(f"API-Football prediction not implemented yet for match {match_id}")
        return None
    
    def _generate_randomized_prediction(
        self,
        match_id: str,
        market_type: str
    ) -> Dict[str, Any]:
        """
        Generate a randomized prediction as fallback.
        
        Uses realistic probability distributions:
        - Home win: 35-50%
        - Draw: 20-30%
        - Away win: 25-40%
        
        Args:
            match_id: Match ID
            market_type: Market type
        
        Returns:
            Randomized prediction dict
        """
        # Generate random probabilities that sum to 1.0
        home_win = round(random.uniform(0.35, 0.50), 4)
        draw = round(random.uniform(0.20, 0.30), 4)
        away_win = round(1.0 - home_win - draw, 4)
        
        return {
            "match_id": match_id,
            "market_type": market_type,
            "source": PredictionSource.DEFAULT_RANDOMIZED.value,
            "priority_level": self.PRIORITY_LEVELS[PredictionSource.DEFAULT_RANDOMIZED],
            "home_win_prob": home_win,
            "draw_prob": draw,
            "away_win_prob": away_win,
            "confidence_score": 0.0,
            "reasoning": "Randomized prediction - no data available",
            "created_at": datetime.utcnow().isoformat(),
        }
    
    def _prediction_to_dict(self, prediction: Prediction) -> Dict[str, Any]:
        """
        Convert Prediction model to dict.
        
        Args:
            prediction: Prediction model instance
        
        Returns:
            Prediction dict
        """
        return {
            "id": str(prediction.id),
            "match_id": str(prediction.match_id),
            "market_type": "match_winner",  # TODO: Get from prediction metadata
            "source": prediction.source.value,
            "priority_level": prediction.priority_level,
            "home_win_prob": float(prediction.home_win_prob),
            "draw_prob": float(prediction.draw_prob),
            "away_win_prob": float(prediction.away_win_prob),
            "confidence_score": float(prediction.confidence_score) if prediction.confidence_score else 0.0,
            "reasoning": prediction.reasoning,
            "created_at": prediction.created_at.isoformat() if prediction.created_at else None,
            "published_at": prediction.published_at.isoformat() if prediction.published_at else None,
            "created_by": str(prediction.created_by) if prediction.created_by else None,
        }

