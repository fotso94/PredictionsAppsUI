"""
Prediction Schemas
Pydantic models for prediction-related API requests and responses
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal


class PredictionBase(BaseModel):
    """Base prediction schema"""
    match_id: str
    market_type: str
    home_win_prob: Decimal
    draw_prob: Decimal
    away_win_prob: Decimal
    confidence_score: Optional[Decimal] = None


class PredictionResponse(BaseModel):
    """Prediction response schema for list views"""
    id: str
    match_id: str
    league_name: Optional[str] = None
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    match_date: Optional[datetime] = None
    market_type: str
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    confidence_level: Optional[str] = None  # Hidden for free tier
    source: str  # "ml" or "expert"
    created_at: datetime
    
    class Config:
        from_attributes = True
    
    @validator('home_win_prob', 'draw_prob', 'away_win_prob', pre=True)
    def convert_decimal_to_float(cls, v):
        if isinstance(v, Decimal):
            return float(v)
        return v


class PredictionDetailResponse(PredictionResponse):
    """Detailed prediction response with additional information"""
    reasoning: Optional[str] = None
    key_factors: Optional[Dict[str, Any]] = None
    expert_name: Optional[str] = None
    expert_accuracy: Optional[float] = None
    match_details: Optional[Dict[str, Any]] = None
    team_stats: Optional[Dict[str, Any]] = None
    head_to_head: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class PredictionListResponse(BaseModel):
    """Paginated prediction list response"""
    predictions: List[PredictionResponse]
    pagination: Dict[str, int]
    tier_info: Dict[str, Any]


class FeedbackRequest(BaseModel):
    """Feedback submission request"""
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating from 1 to 5")
    comment: Optional[str] = Field(None, max_length=500, description="Optional comment")
    is_upvote: Optional[bool] = Field(None, description="Upvote this prediction")
    is_downvote: Optional[bool] = Field(None, description="Downvote this prediction")


class FeedbackResponse(BaseModel):
    """Feedback response schema"""
    id: str
    prediction_id: str
    user_id: str
    username: Optional[str] = None
    rating: Optional[int] = None
    comment: Optional[str] = None
    is_upvote: Optional[bool] = None
    is_downvote: Optional[bool] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FeedbackListResponse(BaseModel):
    """Paginated feedback list response"""
    prediction_id: str
    summary: Dict[str, Any]
    feedback: List[FeedbackResponse]
    pagination: Dict[str, int]

