"""
Subscription Management Endpoints
Handles subscription tier management and upgrades/downgrades
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.users import User

router = APIRouter()


# Mock subscription data (to be replaced with real database queries later)
SUBSCRIPTION_TIERS = {
    "free": {
        "tier": "free",
        "name": "Free",
        "description": "Basic predictions for casual users",
        "price": 0.00,
        "currency": "USD",
        "billing_period": "month",
        "features": {
            "daily_predictions": 5,
            "markets": ["1X2", "Over/Under"],
            "history_days": 7,
            "confidence_visible": False,
            "expert_predictions": False,
            "advanced_analytics": False,
            "api_access": False,
            "priority_support": False,
        },
        "is_popular": False,
        "savings_percentage": 0,
    },
    "basic": {
        "tier": "basic",
        "name": "Basic",
        "description": "Enhanced predictions for regular users",
        "price": 9.99,
        "currency": "USD",
        "billing_period": "month",
        "features": {
            "daily_predictions": 20,
            "markets": ["1X2", "Over/Under", "BTTS"],
            "history_days": 30,
            "confidence_visible": True,
            "expert_predictions": False,
            "advanced_analytics": False,
            "api_access": False,
            "priority_support": False,
        },
        "is_popular": True,
        "savings_percentage": 0,
    },
    "premium": {
        "tier": "premium",
        "name": "Premium",
        "description": "Professional predictions with expert insights",
        "price": 29.99,
        "currency": "USD",
        "billing_period": "month",
        "features": {
            "daily_predictions": 100,
            "markets": ["1X2", "Over/Under", "BTTS", "Correct Score", "HT/FT"],
            "history_days": 90,
            "confidence_visible": True,
            "expert_predictions": True,
            "advanced_analytics": True,
            "api_access": False,
            "priority_support": True,
        },
        "is_popular": False,
        "savings_percentage": 25,
    },
    "pro": {
        "tier": "pro",
        "name": "Pro",
        "description": "Complete access with API for professionals",
        "price": 99.99,
        "currency": "USD",
        "billing_period": "month",
        "features": {
            "daily_predictions": None,  # Unlimited
            "markets": ["1X2", "Over/Under", "BTTS", "Correct Score", "HT/FT", "Asian Handicap"],
            "history_days": None,  # Unlimited
            "confidence_visible": True,
            "expert_predictions": True,
            "advanced_analytics": True,
            "api_access": True,
            "priority_support": True,
        },
        "is_popular": False,
        "savings_percentage": 40,
    },
}


@router.get("/me")
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get current user's subscription information
    """
    # For now, return a mock subscription based on user type
    # In production, this would query the subscriptions table
    
    # Default to free tier
    tier = "free"
    
    # Map user types to subscription tiers (temporary logic)
    if hasattr(current_user, 'user_type'):
        if current_user.user_type == "admin":
            tier = "pro"
        elif current_user.user_type == "expert":
            tier = "premium"
        elif current_user.user_type == "regular":
            tier = "basic"
    
    tier_info = SUBSCRIPTION_TIERS[tier]
    
    return {
        "subscription_id": f"sub_{current_user.id}",
        "user_id": str(current_user.id),
        "tier": tier,
        "tier_name": tier_info["name"],
        "status": "active",
        "price": tier_info["price"],
        "currency": tier_info["currency"],
        "billing_period": tier_info["billing_period"],
        "features": tier_info["features"],
        "starts_at": current_user.created_at.isoformat(),
        "ends_at": None,  # No end date for active subscriptions
        "usage": {
            "predictions_today": 0,  # Would be queried from database
            "predictions_limit": tier_info["features"]["daily_predictions"],
            "predictions_remaining": tier_info["features"]["daily_predictions"] if tier_info["features"]["daily_predictions"] else None,
        },
    }


@router.get("/tiers")
async def get_subscription_tiers(
    current_user: User = Depends(get_current_user),
):
    """
    Get all available subscription tiers
    """
    # Get current user's tier
    current_tier = "free"
    if hasattr(current_user, 'user_type'):
        if current_user.user_type == "admin":
            current_tier = "pro"
        elif current_user.user_type == "expert":
            current_tier = "premium"
        elif current_user.user_type == "regular":
            current_tier = "basic"
    
    # Build response with all tiers
    tiers = []
    for tier_key, tier_data in SUBSCRIPTION_TIERS.items():
        tiers.append({
            **tier_data,
            "is_current": tier_key == current_tier,
        })
    
    return tiers


@router.put("/me")
async def update_subscription(
    new_tier: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update user's subscription tier (upgrade/downgrade)
    """
    # Validate tier
    if new_tier not in SUBSCRIPTION_TIERS:
        raise HTTPException(status_code=400, detail="Invalid subscription tier")
    
    # Get current tier
    current_tier = "free"
    if hasattr(current_user, 'user_type'):
        if current_user.user_type == "admin":
            current_tier = "pro"
        elif current_user.user_type == "expert":
            current_tier = "premium"
        elif current_user.user_type == "regular":
            current_tier = "basic"
    
    if new_tier == current_tier:
        raise HTTPException(status_code=400, detail="You are already on this tier")
    
    # In production, this would:
    # 1. Create a new subscription record
    # 2. Process payment if upgrading
    # 3. Update user's subscription_id
    # 4. Send confirmation email
    
    # For now, just return success message
    tier_info = SUBSCRIPTION_TIERS[new_tier]
    
    return {
        "subscription": {
            "subscription_id": f"sub_{current_user.id}",
            "user_id": str(current_user.id),
            "tier": new_tier,
            "tier_name": tier_info["name"],
            "status": "active",
            "price": tier_info["price"],
            "currency": tier_info["currency"],
            "billing_period": tier_info["billing_period"],
            "features": tier_info["features"],
            "starts_at": datetime.utcnow().isoformat(),
            "ends_at": None,
            "usage": {
                "predictions_today": 0,
                "predictions_limit": tier_info["features"]["daily_predictions"],
                "predictions_remaining": tier_info["features"]["daily_predictions"] if tier_info["features"]["daily_predictions"] else None,
            },
        },
        "message": f"Successfully {'upgraded' if SUBSCRIPTION_TIERS[new_tier]['price'] > SUBSCRIPTION_TIERS[current_tier]['price'] else 'downgraded'} to {tier_info['name']} plan",
    }

