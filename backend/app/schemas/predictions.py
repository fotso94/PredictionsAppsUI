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


# Expert Prediction Schemas

class ExpertPredictionCreate(BaseModel):
    """Schema for creating manual expert predictions"""
    match_id: str = Field(..., description="Match ID")
    home_win_prob: float = Field(..., ge=0.0, le=1.0, description="Home win probability (0-1)")
    draw_prob: float = Field(..., ge=0.0, le=1.0, description="Draw probability (0-1)")
    away_win_prob: float = Field(..., ge=0.0, le=1.0, description="Away win probability (0-1)")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0-1)")
    reasoning: Optional[str] = Field(None, max_length=2000, description="Expert reasoning")
    key_factors: Optional[Dict[str, Any]] = Field(None, description="Key factors influencing prediction")

    @validator('away_win_prob')
    def probabilities_sum_to_one(cls, v, values):
        """Validate that probabilities sum to 1.0"""
        if 'home_win_prob' in values and 'draw_prob' in values:
            total = values['home_win_prob'] + values['draw_prob'] + v
            if not (0.99 <= total <= 1.01):
                raise ValueError('Probabilities must sum to 1.0')
        return v


class ExpertPredictionOverride(BaseModel):
    """Schema for overriding existing predictions"""
    prediction_id: str = Field(..., description="ID of prediction to override")
    home_win_prob: float = Field(..., ge=0.0, le=1.0, description="Home win probability (0-1)")
    draw_prob: float = Field(..., ge=0.0, le=1.0, description="Draw probability (0-1)")
    away_win_prob: float = Field(..., ge=0.0, le=1.0, description="Away win probability (0-1)")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0-1)")
    reasoning: str = Field(..., min_length=10, max_length=2000, description="Reason for override")
    key_factors: Optional[Dict[str, Any]] = Field(None, description="Key factors influencing override")

    @validator('away_win_prob')
    def probabilities_sum_to_one(cls, v, values):
        """Validate that probabilities sum to 1.0"""
        if 'home_win_prob' in values and 'draw_prob' in values:
            total = values['home_win_prob'] + values['draw_prob'] + v
            if not (0.99 <= total <= 1.01):
                raise ValueError('Probabilities must sum to 1.0')
        return v


class ExpertPredictionUpdate(BaseModel):
    """Schema for updating existing predictions"""
    home_win_prob: float = Field(..., ge=0.0, le=1.0, description="Home win probability (0-1)")
    draw_prob: float = Field(..., ge=0.0, le=1.0, description="Draw probability (0-1)")
    away_win_prob: float = Field(..., ge=0.0, le=1.0, description="Away win probability (0-1)")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0-1)")
    reasoning: Optional[str] = Field(None, max_length=2000, description="Expert reasoning")
    key_factors: Optional[Dict[str, Any]] = Field(None, description="Key factors influencing prediction")

    @validator('away_win_prob')
    def probabilities_sum_to_one(cls, v, values):
        """Validate that probabilities sum to 1.0"""
        if 'home_win_prob' in values and 'draw_prob' in values:
            total = values['home_win_prob'] + values['draw_prob'] + v
            if not (0.99 <= total <= 1.01):
                raise ValueError('Probabilities must sum to 1.0')
        return v


class MatchDetails(BaseModel):
    """Match details for prediction responses"""
    home_team_name: str
    away_team_name: str
    home_team_logo: Optional[str] = None
    away_team_logo: Optional[str] = None
    league_name: Optional[str] = None
    match_date: Optional[datetime] = None
    external_match_id: Optional[str] = None


class PublicPredictionResponse(BaseModel):
    """Public prediction response for published predictions (no authentication required)"""
    id: str
    match_id: str
    external_match_id: Optional[str] = None
    source: str
    priority_level: int
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    confidence_score: Optional[float] = None
    reasoning: Optional[str] = None
    published_at: Optional[str] = None
    match_details: Dict[str, Any]  # Using Dict to avoid circular dependency

    class Config:
        from_attributes = True


class UserDetails(BaseModel):
    """User details for prediction responses"""
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class ExpertPredictionResponse(BaseModel):
    """Response schema for expert predictions"""
    id: str
    match_id: str
    source: str
    priority_level: int
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    confidence_score: float
    reasoning: Optional[str] = None
    key_factors: Optional[Dict[str, Any]] = None
    status: str
    created_by: str
    created_at: datetime
    published_at: Optional[datetime] = None
    superseded_by: Optional[str] = None

    # Enhanced fields
    match_details: Optional[MatchDetails] = None
    user_details: Optional[UserDetails] = None

    class Config:
        from_attributes = True

    @validator('id', 'match_id', 'created_by', 'superseded_by', pre=True)
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string"""
        if v is None:
            return v
        return str(v)

    @validator('home_win_prob', 'draw_prob', 'away_win_prob', 'confidence_score', pre=True)
    def convert_decimal_to_float(cls, v):
        """Convert Decimal to float"""
        if isinstance(v, Decimal):
            return float(v)
        return v


class ReviewQueueItem(BaseModel):
    """Schema for review queue items"""
    prediction_id: str
    match_id: str
    match_details: Dict[str, Any]
    source: str
    created_by: str
    expert_name: Optional[str] = None
    created_at: datetime
    status: str
    requires_approval: bool

    class Config:
        from_attributes = True


class ExpertPerformanceMetrics(BaseModel):
    """Schema for expert performance analytics"""
    expert_id: str
    expert_name: str
    total_predictions: int
    published_predictions: int
    pending_predictions: int
    accuracy_rate: Optional[float] = None
    average_confidence: float
    predictions_by_league: Dict[str, int]
    recent_predictions: List[ExpertPredictionResponse]
    performance_trend: List[Dict[str, Any]]

