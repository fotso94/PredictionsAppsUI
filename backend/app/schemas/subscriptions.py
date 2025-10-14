"""
Subscription Schemas
Pydantic models for subscription-related API requests and responses
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class SubscriptionResponse(BaseModel):
    """Current subscription response schema"""
    subscription_id: Optional[str] = None
    user_id: str
    tier: str
    tier_name: str
    status: str
    price: float
    currency: str
    billing_period: str
    features: Dict[str, Any]
    usage: Dict[str, Any]
    started_at: datetime
    expires_at: Optional[datetime] = None
    auto_renew: bool
    next_billing_date: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SubscriptionUpdateRequest(BaseModel):
    """Subscription update request schema"""
    new_tier: str = Field(..., description="New subscription tier (free, basic, premium, pro)")
    payment_method_id: Optional[str] = Field(None, description="Payment method ID for paid tiers")


class SubscriptionUpdateResponse(BaseModel):
    """Subscription update response schema"""
    message: str
    subscription_id: str
    previous_tier: str
    new_tier: str
    effective_date: datetime
    is_upgrade: bool
    price: float
    currency: str
    next_billing_date: Optional[datetime] = None


class SubscriptionTierResponse(BaseModel):
    """Subscription tier information schema"""
    tier: str
    name: str
    description: str
    price: float
    currency: str
    billing_period: str
    features: Dict[str, Any]
    is_current: bool = False
    is_popular: bool = False
    savings_percentage: Optional[float] = None

