"""
Subscription Tier Service
Handles subscription tier-based filtering and access control
"""

from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import HTTPException, status

from app.core.redis import get_sessions_redis
from app.models.users import User


class SubscriptionTierChecker:
    """Service for checking subscription tier limits and access"""
    
    # Subscription tier limits
    TIER_LIMITS = {
        "free": {
            "daily": 3,
            "markets": ["1X2"],
            "history_days": 7,
            "show_confidence": False,
            "show_expert": False
        },
        "basic": {
            "daily": 10,
            "markets": ["1X2", "BTTS", "O/U"],
            "history_days": 30,
            "show_confidence": True,
            "show_expert": False
        },
        "premium": {
            "daily": None,  # Unlimited
            "markets": ["1X2", "BTTS", "O/U", "Correct Score", "HT/FT", "Asian Handicap"],
            "history_days": 90,
            "show_confidence": True,
            "show_expert": True
        },
        "pro": {
            "daily": None,  # Unlimited
            "markets": ["1X2", "BTTS", "O/U", "Correct Score", "HT/FT", "Asian Handicap"],
            "history_days": None,  # Unlimited
            "show_confidence": True,
            "show_expert": True
        }
    }
    
    def __init__(self):
        self.redis_client = get_sessions_redis()
    
    def get_user_tier(self, user: User) -> str:
        """Get user's subscription tier"""
        # Check if user has an active subscription
        if hasattr(user, 'subscription') and user.subscription:
            return user.subscription.tier
        return "free"  # Default to free tier
    
    async def check_daily_limit(self, user: User) -> None:
        """
        Check if user has exceeded daily prediction limit
        
        Raises:
            HTTPException: If daily limit exceeded
        """
        tier = self.get_user_tier(user)
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
        daily_limit = limits["daily"]
        
        # Unlimited access for premium/pro
        if daily_limit is None:
            return
        
        # Get current daily count from Redis
        daily_count = await self.get_daily_count(user)
        
        if daily_count >= daily_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Daily prediction limit ({daily_limit}) exceeded. Upgrade your subscription for more access."
            )
    
    async def get_daily_count(self, user: User) -> int:
        """Get user's daily prediction count from Redis"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"daily_predictions:{user.id}:{today}"
        
        count = self.redis_client.get(key)
        return int(count) if count else 0
    
    async def increment_daily_count(self, user: User) -> int:
        """Increment user's daily prediction count in Redis"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        key = f"daily_predictions:{user.id}:{today}"
        
        # Increment counter
        new_count = self.redis_client.incr(key)
        
        # Set expiration to end of day (24 hours)
        if new_count == 1:
            self.redis_client.expire(key, 86400)  # 24 hours in seconds
        
        return new_count
    
    def check_market_access(self, user: User, market_type: str) -> None:
        """
        Check if user has access to specific market type
        
        Args:
            user: User object
            market_type: Market type (1X2, BTTS, O/U, etc.)
        
        Raises:
            HTTPException: If user doesn't have access to market
        """
        tier = self.get_user_tier(user)
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
        allowed_markets = limits["markets"]
        
        if market_type not in allowed_markets:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Market type '{market_type}' not available for {tier} tier. Upgrade to access more markets."
            )
    
    def get_history_cutoff(self, user: User) -> Optional[datetime]:
        """
        Get historical data cutoff date for user's tier
        
        Returns:
            Cutoff datetime or None for unlimited access
        """
        tier = self.get_user_tier(user)
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
        history_days = limits["history_days"]
        
        if history_days is None:
            return None  # Unlimited access
        
        return datetime.utcnow() - timedelta(days=history_days)
    
    def should_show_confidence(self, user: User) -> bool:
        """Check if confidence levels should be shown to user"""
        tier = self.get_user_tier(user)
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
        return limits["show_confidence"]
    
    def should_show_expert_predictions(self, user: User) -> bool:
        """Check if expert predictions should be shown to user"""
        tier = self.get_user_tier(user)
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
        return limits["show_expert"]
    
    def get_tier_features(self, tier: str) -> dict:
        """Get features for a specific tier"""
        return self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
    
    def filter_predictions_by_tier(self, predictions: List, user: User) -> List:
        """
        Filter predictions based on user's subscription tier
        
        Args:
            predictions: List of prediction objects
            user: User object
        
        Returns:
            Filtered list of predictions
        """
        tier = self.get_user_tier(user)
        limits = self.TIER_LIMITS.get(tier, self.TIER_LIMITS["free"])
        
        # Filter by market type
        allowed_markets = limits["markets"]
        filtered = [p for p in predictions if p.market_type in allowed_markets]
        
        # Filter by historical data limit
        history_cutoff = self.get_history_cutoff(user)
        if history_cutoff:
            filtered = [p for p in filtered if p.created_at >= history_cutoff]
        
        # Filter expert predictions for free/basic tiers
        if not limits["show_expert"]:
            filtered = [p for p in filtered if p.source != "expert"]
        
        # Hide confidence for free tier
        if not limits["show_confidence"]:
            for p in filtered:
                p.confidence_score = None
        
        return filtered


# Global instance
subscription_checker = SubscriptionTierChecker()

