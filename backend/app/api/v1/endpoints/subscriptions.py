"""
Subscription Endpoints for Public API
Endpoints for managing user subscriptions
"""

from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user
from app.models.users import User, UserSubscription, SubscriptionTier
from app.schemas.subscriptions import (
    SubscriptionResponse,
    SubscriptionTierResponse,
    SubscriptionUpdateRequest,
    SubscriptionUpdateResponse,
)

router = APIRouter()


# Subscription tier definitions
SUBSCRIPTION_TIERS = {
    "free": {
        "name": "Free",
        "price": 0.00,
        "currency": "USD",
        "billing_period": "monthly",
        "features": {
            "daily_predictions": 3,
            "markets": ["1X2"],
            "history_days": 7,
            "confidence_visible": False,
            "expert_predictions": False,
            "advanced_analytics": False,
            "api_access": False,
            "priority_support": False
        },
        "description": "Basic access to predictions"
    },
    "basic": {
        "name": "Basic",
        "price": 9.99,
        "currency": "USD",
        "billing_period": "monthly",
        "features": {
            "daily_predictions": 10,
            "markets": ["1X2", "BTTS", "O/U"],
            "history_days": 30,
            "confidence_visible": True,
            "expert_predictions": False,
            "advanced_analytics": False,
            "api_access": False,
            "priority_support": False
        },
        "description": "Enhanced prediction access with more markets"
    },
    "premium": {
        "name": "Premium",
        "price": 29.99,
        "currency": "USD",
        "billing_period": "monthly",
        "features": {
            "daily_predictions": None,  # Unlimited
            "markets": ["1X2", "BTTS", "O/U", "Correct Score", "HT/FT", "Asian Handicap"],
            "history_days": 90,
            "confidence_visible": True,
            "expert_predictions": True,
            "advanced_analytics": True,
            "api_access": False,
            "priority_support": True
        },
        "description": "Full access to all predictions and expert insights"
    },
    "pro": {
        "name": "Pro",
        "price": 99.99,
        "currency": "USD",
        "billing_period": "monthly",
        "features": {
            "daily_predictions": None,  # Unlimited
            "markets": ["1X2", "BTTS", "O/U", "Correct Score", "HT/FT", "Asian Handicap"],
            "history_days": None,  # Unlimited
            "confidence_visible": True,
            "expert_predictions": True,
            "advanced_analytics": True,
            "api_access": True,
            "priority_support": True
        },
        "description": "Professional tier with API access and unlimited history"
    }
}


@router.get("/me", response_model=SubscriptionResponse)
async def get_current_subscription(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get current user's subscription details
    
    **Permission**: Any authenticated user
    
    Returns current subscription tier, usage statistics, and feature availability.
    """
    # Get user's subscription
    subscription = db.query(UserSubscription).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).first()
    
    # Default to free tier if no subscription
    tier = subscription.tier if subscription else "free"
    tier_info = SUBSCRIPTION_TIERS.get(tier, SUBSCRIPTION_TIERS["free"])
    
    # Get usage statistics from Redis
    from app.services.subscription_tier import subscription_checker
    daily_used = await subscription_checker.get_daily_count(current_user)
    daily_limit = tier_info["features"]["daily_predictions"]
    
    # Calculate usage percentage
    usage_percentage = (daily_used / daily_limit * 100) if daily_limit else 0
    
    return SubscriptionResponse(
        subscription_id=str(subscription.id) if subscription else None,
        user_id=str(current_user.id),
        tier=tier,
        tier_name=tier_info["name"],
        status=subscription.status.value if subscription else "active",
        price=tier_info["price"],
        currency=tier_info["currency"],
        billing_period=tier_info["billing_period"],
        features=tier_info["features"],
        usage={
            "daily_predictions_used": daily_used,
            "daily_predictions_limit": daily_limit,
            "daily_predictions_remaining": daily_limit - daily_used if daily_limit else None,
            "usage_percentage": round(usage_percentage, 2)
        },
        started_at=subscription.starts_at if subscription else current_user.created_at,
        expires_at=subscription.expires_at if subscription else None,
        auto_renew=False,  # Not in model, would need to add
        next_billing_date=None  # Not in model, would need to calculate
    )


@router.put("/me", response_model=SubscriptionUpdateResponse)
async def update_subscription(
    update_data: SubscriptionUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update user's subscription (upgrade/downgrade)
    
    **Permission**: Any authenticated user
    
    Allows users to change their subscription tier.
    """
    # Validate new tier
    if update_data.new_tier not in SUBSCRIPTION_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid subscription tier. Must be one of: {', '.join(SUBSCRIPTION_TIERS.keys())}"
        )
    
    # Get current subscription
    subscription = db.query(UserSubscription).filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status == "active"
    ).first()
    
    current_tier = subscription.tier if subscription else "free"
    
    # Check if already on this tier
    if current_tier == update_data.new_tier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You are already on the {update_data.new_tier} tier"
        )
    
    # Determine if upgrade or downgrade
    tier_order = ["free", "basic", "premium", "pro"]
    is_upgrade = tier_order.index(update_data.new_tier) > tier_order.index(current_tier)
    
    # Process payment (placeholder - integrate with payment provider)
    # In production, this would call Stripe/PayPal API
    payment_successful = True  # Placeholder
    
    if not payment_successful:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment processing failed"
        )
    
    # Update or create subscription
    if subscription:
        # Update existing subscription
        from app.models.users import SubscriptionTier, SubscriptionStatus
        subscription.tier = SubscriptionTier(update_data.new_tier)
        subscription.updated_at = datetime.utcnow()

        if is_upgrade:
            # Immediate activation for upgrades
            subscription.status = SubscriptionStatus.ACTIVE
        else:
            # Downgrade at end of billing period - would need additional fields
            subscription.status = SubscriptionStatus.ACTIVE
    else:
        # Create new subscription
        from app.models.users import SubscriptionTier, SubscriptionStatus
        new_tier_info = SUBSCRIPTION_TIERS[update_data.new_tier]

        subscription = UserSubscription(
            user_id=current_user.id,
            tier=SubscriptionTier(update_data.new_tier),
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30),  # 30 days from now
            price_amount=new_tier_info["price"],
            currency=new_tier_info["currency"],
            billing_cycle=new_tier_info["billing_period"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(subscription)
    
    db.commit()
    db.refresh(subscription)
    
    # Get new tier info
    new_tier_info = SUBSCRIPTION_TIERS[update_data.new_tier]
    
    return SubscriptionUpdateResponse(
        message=f"Successfully {'upgraded' if is_upgrade else 'downgraded'} to {new_tier_info['name']} tier",
        subscription_id=str(subscription.id),
        previous_tier=current_tier,
        new_tier=update_data.new_tier,
        effective_date=datetime.utcnow() if is_upgrade else subscription.expires_at,
        is_upgrade=is_upgrade,
        price=new_tier_info["price"],
        currency=new_tier_info["currency"],
        next_billing_date=subscription.expires_at  # Use expires_at as next billing
    )


@router.get("/tiers", response_model=List[SubscriptionTierResponse])
async def list_subscription_tiers(
    current_user: User = Depends(get_current_active_user)
):
    """
    List all available subscription tiers
    
    **Permission**: Any authenticated user
    
    Returns information about all subscription tiers including features and pricing.
    """
    # Get current user's tier
    from app.models.users import UserSubscription
    from app.core.deps import get_db
    
    # Get current tier
    current_tier = "free"  # Default
    
    # Build response
    tiers = []
    for tier_key, tier_data in SUBSCRIPTION_TIERS.items():
        tier_response = SubscriptionTierResponse(
            tier=tier_key,
            name=tier_data["name"],
            description=tier_data["description"],
            price=tier_data["price"],
            currency=tier_data["currency"],
            billing_period=tier_data["billing_period"],
            features=tier_data["features"],
            is_current=tier_key == current_tier,
            is_popular=tier_key == "premium",  # Mark premium as popular
            savings_percentage=0 if tier_key == "free" else None  # Could calculate annual savings
        )
        tiers.append(tier_response)
    
    return tiers

