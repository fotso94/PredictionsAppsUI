"""
Predictions Schema Models
16 tables for prediction management, matches, and analytics
"""

from datetime import datetime
from typing import List

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, Enum,
    ForeignKey, Index, UniqueConstraint, CheckConstraint, DECIMAL, Float
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, uuid_fk
import enum


# Enums
class PredictionSource(str, enum.Enum):
    """Prediction source enumeration"""
    ML_BASELINE = "ml_baseline"
    EXPERT_OVERRIDE = "expert_override"
    EXPERT_MANUAL = "expert_manual"
    ADMIN_MANUAL = "admin_manual"
    LLM_GENERATED = "llm_generated"
    API_FOOTBALL_BASELINE = "api_football_baseline"
    DEFAULT_RANDOMIZED = "default_randomized"


class PredictionStatus(str, enum.Enum):
    """Prediction status enumeration"""
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    REJECTED = "rejected"


class MatchStatus(str, enum.Enum):
    """Match status enumeration"""
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"


class MarketType(str, enum.Enum):
    """Betting market type enumeration"""
    MATCH_RESULT = "match_result"  # 1X2
    OVER_UNDER = "over_under"
    BOTH_TEAMS_SCORE = "both_teams_score"
    CORRECT_SCORE = "correct_score"
    DOUBLE_CHANCE = "double_chance"


class PredictionOutcome(str, enum.Enum):
    """Prediction outcome enumeration"""
    PENDING = "pending"
    WON = "won"
    LOST = "lost"
    VOID = "void"
    PUSH = "push"


# Models

class Prediction(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Core predictions table
    Supports hybrid ML + Expert prediction system
    """
    __tablename__ = "predictions"
    __table_args__ = (
        Index('idx_predictions_match_id', 'match_id'),
        Index('idx_predictions_created_by', 'created_by'),
        Index('idx_predictions_source', 'source'),
        Index('idx_predictions_status', 'status'),
        Index('idx_predictions_published_at', 'published_at'),
        Index('idx_predictions_created_at', 'created_at'),
        Index('idx_predictions_superseded_by', 'superseded_by'),
        Index('idx_predictions_match_priority_published', 'match_id', 'priority_level', 'published_at'),
        CheckConstraint('home_win_prob + draw_prob + away_win_prob = 1.0', name='ck_predictions_prob_sum'),
        CheckConstraint('confidence_score >= 0 AND confidence_score <= 1', name='ck_predictions_confidence'),
        CheckConstraint('priority_level >= 0 AND priority_level <= 100', name='ck_predictions_priority_level_range'),
        {'schema': 'predictions', 'comment': 'Core predictions'}
    )
    
    # Match Reference
    match_id = uuid_fk('predictions.matches.id', nullable=False)
    
    # Source Attribution
    source = Column(Enum(PredictionSource), nullable=False, comment="Prediction source")
    created_by = uuid_fk('users.users.id', nullable=False, comment="User who created prediction")
    ml_prediction_id = uuid_fk('ml_models.ml_predictions.id', nullable=True, comment="Original ML prediction")
    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=True, comment="Expert who created/modified")
    
    # Probabilities (must sum to 1.0)
    home_win_prob = Column(DECIMAL(5, 4), nullable=False, comment="Home win probability")
    draw_prob = Column(DECIMAL(5, 4), nullable=False, comment="Draw probability")
    away_win_prob = Column(DECIMAL(5, 4), nullable=False, comment="Away win probability")
    
    # Confidence & Reasoning
    confidence_score = Column(DECIMAL(5, 4), nullable=False, comment="Confidence score 0-1")
    reasoning = Column(Text, comment="Prediction reasoning/explanation")
    key_factors = Column(JSONB, comment="Key factors influencing prediction")
    
    # Status & Approval
    status = Column(Enum(PredictionStatus), nullable=False, default=PredictionStatus.PENDING)
    approved_by = uuid_fk('users.users.id', nullable=True, comment="Admin who approved")
    approved_at = Column(DateTime)
    published_at = Column(DateTime)

    # Multi-Source Priority System
    priority_level = Column(Integer, nullable=False, comment="Priority level (0-100): Expert=100, LLM=50, API-Football=25, Randomized=0")
    superseded_by = uuid_fk('predictions.predictions.id', nullable=True, comment="ID of prediction that supersedes this one")

    # Metadata
    prediction_metadata = Column(JSONB, comment="Additional prediction metadata")
    
    # Relationships
    match = relationship("Match", back_populates="predictions")
    overrides = relationship("PredictionOverride", back_populates="prediction", cascade="all, delete-orphan")
    audit_logs = relationship("PredictionAudit", back_populates="prediction", cascade="all, delete-orphan")
    result = relationship("PredictionResult", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    markets = relationship("PredictionMarket", back_populates="prediction", cascade="all, delete-orphan")
    analytics = relationship("PredictionAnalytics", back_populates="prediction", uselist=False, cascade="all, delete-orphan")
    views = relationship("UserPredictionView", back_populates="prediction", cascade="all, delete-orphan")
    feedback = relationship("UserPredictionFeedback", back_populates="prediction", cascade="all, delete-orphan")
    comments = relationship("PredictionComment", back_populates="prediction", cascade="all, delete-orphan")
    shares = relationship("PredictionShare", back_populates="prediction", cascade="all, delete-orphan")


class PredictionOverride(Base, UUIDMixin, TimestampMixin):
    """Expert overrides of ML predictions"""
    __tablename__ = "prediction_overrides"
    __table_args__ = (
        Index('idx_prediction_overrides_prediction_id', 'prediction_id'),
        Index('idx_prediction_overrides_expert_user_id', 'expert_user_id'),
        Index('idx_prediction_overrides_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'Prediction overrides'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False, unique=True)
    expert_user_id = uuid_fk('users.users.id', nullable=False)
    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=False)
    
    # Original ML Prediction
    original_ml_prediction_id = uuid_fk('ml_models.ml_predictions.id', nullable=True)
    original_probabilities = Column(JSONB, nullable=False, comment="Original ML probabilities")
    original_confidence = Column(DECIMAL(5, 4), comment="Original ML confidence")
    
    # New Expert Prediction
    new_probabilities = Column(JSONB, nullable=False, comment="Expert-adjusted probabilities")
    new_confidence = Column(DECIMAL(5, 4), nullable=False, comment="Expert confidence")
    
    # Override Details
    override_reason = Column(Text, nullable=False, comment="Reason for override")
    confidence_adjustment = Column(DECIMAL(6, 4), comment="Confidence change")
    key_insights = Column(JSONB, comment="Expert insights")
    
    # Review & Approval
    reviewed_by_admin_id = uuid_fk('users.users.id', nullable=True)
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    is_approved = Column(Boolean, default=False)
    
    # Relationships
    prediction = relationship("Prediction", back_populates="overrides")


class PredictionAudit(Base, UUIDMixin, TimestampMixin):
    """Audit trail for prediction changes"""
    __tablename__ = "prediction_audit"
    __table_args__ = (
        Index('idx_prediction_audit_prediction_id', 'prediction_id'),
        Index('idx_prediction_audit_user_id', 'user_id'),
        Index('idx_prediction_audit_action', 'action'),
        Index('idx_prediction_audit_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'Prediction audit trail'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Action Info
    action = Column(String(50), nullable=False, comment="created, updated, approved, published, etc.")
    action_description = Column(Text)
    
    # Changes
    old_values = Column(JSONB, comment="Previous values")
    new_values = Column(JSONB, comment="New values")
    changes_summary = Column(Text, comment="Human-readable summary")
    
    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)
    
    # Relationships
    prediction = relationship("Prediction", back_populates="audit_logs")


class PredictionResult(Base, UUIDMixin, TimestampMixin):
    """Prediction results and outcomes"""
    __tablename__ = "prediction_results"
    __table_args__ = (
        Index('idx_prediction_results_prediction_id', 'prediction_id'),
        Index('idx_prediction_results_outcome', 'outcome'),
        Index('idx_prediction_results_settled_at', 'settled_at'),
        {'schema': 'predictions', 'comment': 'Prediction results'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False, unique=True)
    match_result_id = uuid_fk('predictions.match_results.id', nullable=False)
    
    # Outcome
    outcome = Column(Enum(PredictionOutcome), nullable=False)
    is_correct = Column(Boolean, comment="Was prediction correct")
    
    # Accuracy Metrics
    probability_accuracy = Column(DECIMAL(5, 4), comment="How close probabilities were")
    confidence_calibration = Column(DECIMAL(5, 4), comment="Confidence vs actual")
    
    # Financial Metrics
    potential_return = Column(DECIMAL(10, 2))
    actual_return = Column(DECIMAL(10, 2))
    roi_percentage = Column(DECIMAL(10, 2))
    
    # Settlement
    settled_at = Column(DateTime, nullable=False)
    settled_by_system = Column(Boolean, default=True)
    
    # Relationships
    prediction = relationship("Prediction", back_populates="result")


class PredictionMarket(Base, UUIDMixin, TimestampMixin):
    """Multiple betting markets per prediction"""
    __tablename__ = "prediction_markets"
    __table_args__ = (
        Index('idx_prediction_markets_prediction_id', 'prediction_id'),
        Index('idx_prediction_markets_market_type', 'market_type'),
        {'schema': 'predictions', 'comment': 'Prediction markets'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    
    # Market Info
    market_type = Column(Enum(MarketType), nullable=False)
    market_value = Column(String(50), comment="e.g., 'Over 2.5', 'BTTS Yes'")
    
    # Prediction
    predicted_outcome = Column(String(50), nullable=False)
    probability = Column(DECIMAL(5, 4), nullable=False)
    confidence = Column(DECIMAL(5, 4), nullable=False)
    
    # Odds
    recommended_odds = Column(DECIMAL(6, 2))
    market_odds = Column(DECIMAL(6, 2))
    
    # Status
    is_primary = Column(Boolean, default=False, comment="Primary market for this prediction")
    
    # Relationships
    prediction = relationship("Prediction", back_populates="markets")


class PredictionAnalytics(Base, UUIDMixin, TimestampMixin):
    """Analytics for individual predictions"""
    __tablename__ = "prediction_analytics"
    __table_args__ = (
        Index('idx_prediction_analytics_prediction_id', 'prediction_id'),
        {'schema': 'predictions', 'comment': 'Prediction analytics'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False, unique=True)
    
    # Engagement Metrics
    view_count = Column(Integer, nullable=False, default=0)
    unique_viewers = Column(Integer, nullable=False, default=0)
    share_count = Column(Integer, nullable=False, default=0)
    comment_count = Column(Integer, nullable=False, default=0)
    
    # Feedback Metrics
    upvote_count = Column(Integer, nullable=False, default=0)
    downvote_count = Column(Integer, nullable=False, default=0)
    average_rating = Column(DECIMAL(3, 2))
    total_ratings = Column(Integer, nullable=False, default=0)
    
    # Performance Metrics
    accuracy_score = Column(DECIMAL(5, 4))
    roi_percentage = Column(DECIMAL(10, 2))
    engagement_score = Column(DECIMAL(10, 2), comment="Composite engagement metric")
    
    # Relationships
    prediction = relationship("Prediction", back_populates="analytics")


class UserPredictionView(Base, UUIDMixin, TimestampMixin):
    """Track user views of predictions"""
    __tablename__ = "user_prediction_views"
    __table_args__ = (
        Index('idx_user_prediction_views_prediction_id', 'prediction_id'),
        Index('idx_user_prediction_views_user_id', 'user_id'),
        Index('idx_user_prediction_views_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'User prediction views'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=True, comment="Null for anonymous users")

    # View Info
    session_id = Column(String(255))
    view_duration_seconds = Column(Integer)

    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)
    referrer = Column(String(500))

    # Relationships
    prediction = relationship("Prediction", back_populates="views")


class UserPredictionFeedback(Base, UUIDMixin, TimestampMixin):
    """User feedback on predictions"""
    __tablename__ = "user_prediction_feedback"
    __table_args__ = (
        Index('idx_user_prediction_feedback_prediction_id', 'prediction_id'),
        Index('idx_user_prediction_feedback_user_id', 'user_id'),
        UniqueConstraint('prediction_id', 'user_id', name='uq_user_prediction_feedback'),
        {'schema': 'predictions', 'comment': 'User prediction feedback'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=False)

    # Feedback
    rating = Column(Integer, comment="1-5 star rating")
    is_upvote = Column(Boolean)
    is_downvote = Column(Boolean)

    # Comment
    comment = Column(Text)

    # Relationships
    prediction = relationship("Prediction", back_populates="feedback")


class Match(Base, UUIDMixin, TimestampMixin):
    """Match information"""
    __tablename__ = "matches"
    __table_args__ = (
        Index('idx_matches_home_team_id', 'home_team_id'),
        Index('idx_matches_away_team_id', 'away_team_id'),
        Index('idx_matches_league_id', 'league_id'),
        Index('idx_matches_match_date', 'match_date'),
        Index('idx_matches_status', 'status'),
        Index('idx_matches_external_api_id', 'external_api_id'),
        {'schema': 'predictions', 'comment': 'Match information'}
    )

    # Teams
    home_team_id = uuid_fk('predictions.teams.id', nullable=False)
    away_team_id = uuid_fk('predictions.teams.id', nullable=False)

    # League
    league_id = uuid_fk('predictions.leagues.id', nullable=False)

    # Match Details
    match_date = Column(DateTime, nullable=False)
    venue = Column(String(255))
    season = Column(String(20), comment="e.g., '2023-24'")
    round = Column(String(50), comment="e.g., 'Matchday 15'")

    # Status
    status = Column(Enum(MatchStatus), nullable=False, default=MatchStatus.SCHEDULED)

    # External API
    external_api_id = Column(String(100), unique=True, comment="External API match ID")
    external_api_source = Column(String(50), comment="API source name")

    # Metadata
    match_metadata = Column(JSONB, comment="Additional match data")

    # Relationships
    predictions = relationship("Prediction", back_populates="match", cascade="all, delete-orphan")
    result = relationship("MatchResult", back_populates="match", uselist=False, cascade="all, delete-orphan")
    statistics = relationship("MatchStatistic", back_populates="match", cascade="all, delete-orphan")


class MatchResult(Base, UUIDMixin, TimestampMixin):
    """Match results"""
    __tablename__ = "match_results"
    __table_args__ = (
        Index('idx_match_results_match_id', 'match_id'),
        {'schema': 'predictions', 'comment': 'Match results'}
    )

    match_id = uuid_fk('predictions.matches.id', nullable=False, unique=True)

    # Score
    home_score = Column(Integer, nullable=False)
    away_score = Column(Integer, nullable=False)

    # Half Time
    home_score_ht = Column(Integer)
    away_score_ht = Column(Integer)

    # Result
    result = Column(String(10), comment="H, D, A")

    # Additional Stats
    home_corners = Column(Integer)
    away_corners = Column(Integer)
    home_yellow_cards = Column(Integer)
    away_yellow_cards = Column(Integer)
    home_red_cards = Column(Integer)
    away_red_cards = Column(Integer)

    # Metadata
    result_metadata = Column(JSONB, comment="Additional result data")

    # Relationships
    match = relationship("Match", back_populates="result")


class MatchStatistic(Base, UUIDMixin, TimestampMixin):
    """Match statistics (pre-match, live, post-match)"""
    __tablename__ = "match_statistics"
    __table_args__ = (
        Index('idx_match_statistics_match_id', 'match_id'),
        Index('idx_match_statistics_stat_type', 'stat_type'),
        {'schema': 'predictions', 'comment': 'Match statistics'}
    )

    match_id = uuid_fk('predictions.matches.id', nullable=False)

    # Stat Type
    stat_type = Column(String(50), nullable=False, comment="pre_match, live, post_match")
    stat_category = Column(String(50), comment="possession, shots, passes, etc.")

    # Values
    home_value = Column(DECIMAL(10, 2))
    away_value = Column(DECIMAL(10, 2))

    # Metadata
    stat_metadata = Column(JSONB)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    match = relationship("Match", back_populates="statistics")


class League(Base, UUIDMixin, TimestampMixin):
    """League/competition reference data"""
    __tablename__ = "leagues"
    __table_args__ = (
        Index('idx_leagues_name', 'name'),
        Index('idx_leagues_country', 'country'),
        Index('idx_leagues_external_api_id', 'external_api_id'),
        {'schema': 'predictions', 'comment': 'League reference data'}
    )

    # League Info
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    country = Column(String(100), nullable=False)
    country_code = Column(String(3))

    # Details
    logo_url = Column(String(500))
    tier = Column(Integer, comment="League tier/division")

    # External API
    external_api_id = Column(String(100), unique=True)
    external_api_source = Column(String(50))

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Metadata
    league_metadata = Column(JSONB)


class Team(Base, UUIDMixin, TimestampMixin):
    """Team reference data"""
    __tablename__ = "teams"
    __table_args__ = (
        Index('idx_teams_name', 'name'),
        Index('idx_teams_country', 'country'),
        Index('idx_teams_external_api_id', 'external_api_id'),
        {'schema': 'predictions', 'comment': 'Team reference data'}
    )

    # Team Info
    name = Column(String(255), nullable=False)
    short_name = Column(String(50))
    code = Column(String(10), comment="3-letter team code")
    country = Column(String(100))

    # Details
    logo_url = Column(String(500))
    founded_year = Column(Integer)
    venue_name = Column(String(255))
    venue_capacity = Column(Integer)

    # External API
    external_api_id = Column(String(100), unique=True)
    external_api_source = Column(String(50))

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Metadata
    team_metadata = Column(JSONB)


class PredictionTemplate(Base, UUIDMixin, TimestampMixin):
    """Reusable prediction templates"""
    __tablename__ = "prediction_templates"
    __table_args__ = (
        Index('idx_prediction_templates_created_by', 'created_by'),
        Index('idx_prediction_templates_is_active', 'is_active'),
        {'schema': 'predictions', 'comment': 'Prediction templates'}
    )

    # Template Info
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_by = uuid_fk('users.users.id', nullable=False)

    # Template Data
    template_data = Column(JSONB, nullable=False, comment="Template configuration")

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_public = Column(Boolean, nullable=False, default=False)

    # Usage Stats
    usage_count = Column(Integer, nullable=False, default=0)


class PredictionComment(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Comments on predictions"""
    __tablename__ = "prediction_comments"
    __table_args__ = (
        Index('idx_prediction_comments_prediction_id', 'prediction_id'),
        Index('idx_prediction_comments_user_id', 'user_id'),
        Index('idx_prediction_comments_created_at', 'created_at'),
        {'schema': 'predictions', 'comment': 'Prediction comments'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=False)
    parent_comment_id = uuid_fk('predictions.prediction_comments.id', nullable=True, comment="For nested comments")

    # Comment
    comment_text = Column(Text, nullable=False)

    # Moderation
    is_flagged = Column(Boolean, nullable=False, default=False)
    is_approved = Column(Boolean, nullable=False, default=True)

    # Relationships
    prediction = relationship("Prediction", back_populates="comments")


class PredictionShare(Base, UUIDMixin, TimestampMixin):
    """Track prediction shares"""
    __tablename__ = "prediction_shares"
    __table_args__ = (
        Index('idx_prediction_shares_prediction_id', 'prediction_id'),
        Index('idx_prediction_shares_user_id', 'user_id'),
        Index('idx_prediction_shares_platform', 'platform'),
        {'schema': 'predictions', 'comment': 'Prediction shares'}
    )

    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    user_id = uuid_fk('users.users.id', nullable=True)

    # Share Info
    platform = Column(String(50), nullable=False, comment="twitter, facebook, whatsapp, etc.")
    share_url = Column(String(500))

    # Context
    ip_address = Column(String(45))
    user_agent = Column(Text)

    # Relationships
    prediction = relationship("Prediction", back_populates="shares")
