"""
Analytics Schema Models
13 tables for analytics, metrics, and performance tracking
"""

from datetime import datetime
from typing import List

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, Enum,
    ForeignKey, Index, UniqueConstraint, CheckConstraint, DECIMAL, BigInteger, Float
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, UUIDMixin, TimestampMixin, uuid_fk
import enum


# Enums
class AnalyticsPeriod(str, enum.Enum):
    """Analytics period enumeration"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class EngagementLevel(str, enum.Enum):
    """User engagement level enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# Models

class UserAnalytics(Base, UUIDMixin, TimestampMixin):
    """User analytics summary"""
    __tablename__ = "user_analytics"
    __table_args__ = (
        Index('idx_user_analytics_user_id', 'user_id'),
        Index('idx_user_analytics_period_start', 'period_start'),
        Index('idx_user_analytics_period_type', 'period_type'),
        {'schema': 'analytics', 'comment': 'User analytics summary'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)
    
    # Activity Metrics
    total_logins = Column(Integer, nullable=False, default=0)
    total_sessions = Column(Integer, nullable=False, default=0)
    total_session_duration_seconds = Column(BigInteger, nullable=False, default=0)
    average_session_duration_seconds = Column(Integer)
    
    # Prediction Metrics
    predictions_viewed = Column(Integer, nullable=False, default=0)
    predictions_shared = Column(Integer, nullable=False, default=0)
    predictions_commented = Column(Integer, nullable=False, default=0)
    predictions_rated = Column(Integer, nullable=False, default=0)
    
    # Engagement
    engagement_score = Column(DECIMAL(10, 2), comment="Composite engagement score")
    engagement_level = Column(Enum(EngagementLevel))
    
    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class UserEngagementMetric(Base, UUIDMixin, TimestampMixin):
    """Detailed user engagement metrics"""
    __tablename__ = "user_engagement_metrics"
    __table_args__ = (
        Index('idx_user_engagement_metrics_user_id', 'user_id'),
        Index('idx_user_engagement_metrics_metric_date', 'metric_date'),
        Index('idx_user_engagement_metrics_metric_type', 'metric_type'),
        {'schema': 'analytics', 'comment': 'User engagement metrics'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Metric Info
    metric_date = Column(DateTime, nullable=False)
    metric_type = Column(String(100), nullable=False, comment="page_view, click, scroll, etc.")
    metric_category = Column(String(100), comment="navigation, content, interaction")
    
    # Value
    metric_value = Column(DECIMAL(15, 4), nullable=False)
    metric_count = Column(Integer, nullable=False, default=1)
    
    # Context
    page_url = Column(String(500))
    referrer_url = Column(String(500))
    
    # Metadata
    metric_metadata = Column(JSONB)


class UserActivityLog(Base, UUIDMixin, TimestampMixin):
    """Analytics-specific user activity log"""
    __tablename__ = "user_activity_log"
    __table_args__ = (
        Index('idx_analytics_user_activity_log_user_id', 'user_id'),
        Index('idx_analytics_user_activity_log_activity_type', 'activity_type'),
        Index('idx_analytics_user_activity_log_created_at', 'created_at'),
        {'schema': 'analytics', 'comment': 'Analytics user activity log'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=True, comment="Null for anonymous")
    
    # Activity Info
    activity_type = Column(String(100), nullable=False)
    activity_category = Column(String(100))
    activity_description = Column(Text)
    
    # Context
    session_id = Column(String(255))
    page_url = Column(String(500))
    referrer_url = Column(String(500))
    
    # Device Info
    device_type = Column(String(50), comment="desktop, mobile, tablet")
    browser = Column(String(100))
    os = Column(String(100))
    
    # Location
    country = Column(String(100))
    city = Column(String(100))
    
    # Metadata
    activity_metadata = Column(JSONB)


class PredictionAnalyticsSummary(Base, UUIDMixin, TimestampMixin):
    """Prediction analytics summary"""
    __tablename__ = "prediction_analytics_summary"
    __table_args__ = (
        Index('idx_prediction_analytics_summary_period_start', 'period_start'),
        Index('idx_prediction_analytics_summary_period_type', 'period_type'),
        {'schema': 'analytics', 'comment': 'Prediction analytics summary'}
    )
    
    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)
    
    # Volume Metrics
    total_predictions = Column(Integer, nullable=False, default=0)
    ml_predictions = Column(Integer, nullable=False, default=0)
    expert_predictions = Column(Integer, nullable=False, default=0)
    expert_overrides = Column(Integer, nullable=False, default=0)
    
    # Accuracy Metrics
    total_settled = Column(Integer, nullable=False, default=0)
    total_correct = Column(Integer, nullable=False, default=0)
    overall_accuracy = Column(DECIMAL(5, 4))
    ml_accuracy = Column(DECIMAL(5, 4))
    expert_accuracy = Column(DECIMAL(5, 4))
    
    # Engagement Metrics
    total_views = Column(BigInteger, nullable=False, default=0)
    total_shares = Column(Integer, nullable=False, default=0)
    total_comments = Column(Integer, nullable=False, default=0)
    
    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class PredictionPerformanceMetric(Base, UUIDMixin, TimestampMixin):
    """Detailed prediction performance metrics"""
    __tablename__ = "prediction_performance_metrics"
    __table_args__ = (
        Index('idx_prediction_performance_metrics_metric_date', 'metric_date'),
        Index('idx_prediction_performance_metrics_league_id', 'league_id'),
        Index('idx_prediction_performance_metrics_market_type', 'market_type'),
        {'schema': 'analytics', 'comment': 'Prediction performance metrics'}
    )
    
    # Dimensions
    metric_date = Column(DateTime, nullable=False)
    league_id = uuid_fk('predictions.leagues.id', nullable=True)
    market_type = Column(String(50))
    
    # Performance
    total_predictions = Column(Integer, nullable=False, default=0)
    correct_predictions = Column(Integer, nullable=False, default=0)
    accuracy_rate = Column(DECIMAL(5, 4))
    
    # Confidence
    average_confidence = Column(DECIMAL(5, 4))
    confidence_calibration = Column(DECIMAL(5, 4))
    
    # ROI
    average_roi = Column(DECIMAL(10, 2))
    total_roi = Column(DECIMAL(15, 2))
    
    # Metadata
    performance_metadata = Column(JSONB)


class ExpertAnalytics(Base, UUIDMixin, TimestampMixin):
    """Expert performance analytics"""
    __tablename__ = "expert_analytics"
    __table_args__ = (
        Index('idx_expert_analytics_expert_profile_id', 'expert_profile_id'),
        Index('idx_expert_analytics_period_start', 'period_start'),
        Index('idx_expert_analytics_period_type', 'period_type'),
        {'schema': 'analytics', 'comment': 'Expert analytics'}
    )
    
    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=False)
    
    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)
    
    # Prediction Metrics
    total_predictions = Column(Integer, nullable=False, default=0)
    total_overrides = Column(Integer, nullable=False, default=0)
    predictions_approved = Column(Integer, nullable=False, default=0)
    predictions_rejected = Column(Integer, nullable=False, default=0)
    
    # Accuracy Metrics
    total_settled = Column(Integer, nullable=False, default=0)
    total_correct = Column(Integer, nullable=False, default=0)
    accuracy_rate = Column(DECIMAL(5, 4))
    
    # Override Performance
    override_accuracy = Column(DECIMAL(5, 4))
    override_improvement = Column(DECIMAL(6, 4), comment="Improvement over ML baseline")
    
    # Engagement
    total_followers = Column(Integer, nullable=False, default=0)
    follower_growth = Column(Integer, default=0)
    average_prediction_views = Column(DECIMAL(10, 2))
    
    # Reputation
    reputation_score = Column(Integer)
    reputation_change = Column(Integer)
    
    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class ModelPerformanceAnalytics(Base, UUIDMixin, TimestampMixin):
    """ML model performance analytics"""
    __tablename__ = "model_performance_analytics"
    __table_args__ = (
        Index('idx_model_performance_analytics_model_id', 'model_id'),
        Index('idx_model_performance_analytics_period_start', 'period_start'),
        {'schema': 'analytics', 'comment': 'Model performance analytics'}
    )
    
    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)
    
    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)
    
    # Prediction Volume
    total_predictions = Column(Integer, nullable=False, default=0)
    predictions_used = Column(Integer, nullable=False, default=0, comment="Not overridden")
    predictions_overridden = Column(Integer, nullable=False, default=0)
    
    # Accuracy
    total_settled = Column(Integer, nullable=False, default=0)
    total_correct = Column(Integer, nullable=False, default=0)
    accuracy_rate = Column(DECIMAL(5, 4))
    
    # Confidence
    average_confidence = Column(DECIMAL(5, 4))
    confidence_calibration = Column(DECIMAL(5, 4))
    
    # Override Analysis
    override_rate = Column(DECIMAL(5, 4))
    override_accuracy_delta = Column(DECIMAL(6, 4), comment="Accuracy change after override")
    
    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class SystemAnalytics(Base, UUIDMixin, TimestampMixin):
    """System-wide analytics"""
    __tablename__ = "system_analytics"
    __table_args__ = (
        Index('idx_system_analytics_period_start', 'period_start'),
        Index('idx_system_analytics_period_type', 'period_type'),
        {'schema': 'analytics', 'comment': 'System analytics'}
    )
    
    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)
    
    # User Metrics
    total_users = Column(Integer, nullable=False, default=0)
    active_users = Column(Integer, nullable=False, default=0)
    new_users = Column(Integer, nullable=False, default=0)
    churned_users = Column(Integer, nullable=False, default=0)
    
    # Subscription Metrics
    total_subscribers = Column(Integer, nullable=False, default=0)
    new_subscribers = Column(Integer, nullable=False, default=0)
    cancelled_subscriptions = Column(Integer, nullable=False, default=0)
    
    # Prediction Metrics
    total_predictions = Column(Integer, nullable=False, default=0)
    published_predictions = Column(Integer, nullable=False, default=0)
    
    # Performance
    average_response_time_ms = Column(Integer)
    error_rate = Column(DECIMAL(5, 4))
    uptime_percentage = Column(DECIMAL(5, 2))
    
    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class APIUsageAnalytics(Base, UUIDMixin, TimestampMixin):
    """API usage analytics"""
    __tablename__ = "api_usage_analytics"
    __table_args__ = (
        Index('idx_api_usage_analytics_period_start', 'period_start'),
        Index('idx_api_usage_analytics_endpoint', 'endpoint'),
        Index('idx_api_usage_analytics_user_id', 'user_id'),
        {'schema': 'analytics', 'comment': 'API usage analytics'}
    )

    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)

    # Endpoint
    endpoint = Column(String(255), nullable=False)
    http_method = Column(String(10), nullable=False)

    # User
    user_id = uuid_fk('users.users.id', nullable=True)

    # Metrics
    total_requests = Column(BigInteger, nullable=False, default=0)
    successful_requests = Column(BigInteger, nullable=False, default=0)
    failed_requests = Column(BigInteger, nullable=False, default=0)

    # Performance
    average_response_time_ms = Column(Integer)
    p50_response_time_ms = Column(Integer)
    p95_response_time_ms = Column(Integer)
    p99_response_time_ms = Column(Integer)

    # Errors
    error_rate = Column(DECIMAL(5, 4))

    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class FeatureUsageAnalytics(Base, UUIDMixin, TimestampMixin):
    """Feature usage analytics"""
    __tablename__ = "feature_usage_analytics"
    __table_args__ = (
        Index('idx_feature_usage_analytics_period_start', 'period_start'),
        Index('idx_feature_usage_analytics_feature_name', 'feature_name'),
        {'schema': 'analytics', 'comment': 'Feature usage analytics'}
    )

    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)

    # Feature
    feature_name = Column(String(255), nullable=False)
    feature_category = Column(String(100))

    # Usage Metrics
    total_users = Column(Integer, nullable=False, default=0)
    total_uses = Column(BigInteger, nullable=False, default=0)
    unique_users = Column(Integer, nullable=False, default=0)

    # Engagement
    average_uses_per_user = Column(DECIMAL(10, 2))
    adoption_rate = Column(DECIMAL(5, 4), comment="% of active users using feature")

    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class ConversionAnalytics(Base, UUIDMixin, TimestampMixin):
    """Conversion funnel analytics"""
    __tablename__ = "conversion_analytics"
    __table_args__ = (
        Index('idx_conversion_analytics_period_start', 'period_start'),
        Index('idx_conversion_analytics_funnel_name', 'funnel_name'),
        {'schema': 'analytics', 'comment': 'Conversion analytics'}
    )

    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)

    # Funnel
    funnel_name = Column(String(255), nullable=False, comment="signup, subscription, etc.")
    funnel_step = Column(String(100), nullable=False)
    funnel_step_order = Column(Integer, nullable=False)

    # Metrics
    total_entered = Column(Integer, nullable=False, default=0)
    total_completed = Column(Integer, nullable=False, default=0)
    total_dropped = Column(Integer, nullable=False, default=0)

    # Rates
    completion_rate = Column(DECIMAL(5, 4))
    drop_off_rate = Column(DECIMAL(5, 4))

    # Time
    average_time_to_complete_seconds = Column(Integer)

    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class RevenueAnalytics(Base, UUIDMixin, TimestampMixin):
    """Revenue analytics"""
    __tablename__ = "revenue_analytics"
    __table_args__ = (
        Index('idx_revenue_analytics_period_start', 'period_start'),
        Index('idx_revenue_analytics_period_type', 'period_type'),
        Index('idx_revenue_analytics_subscription_tier', 'subscription_tier'),
        {'schema': 'analytics', 'comment': 'Revenue analytics'}
    )

    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)

    # Subscription Tier
    subscription_tier = Column(String(50))

    # Revenue Metrics
    total_revenue = Column(DECIMAL(15, 2), nullable=False, default=0)
    new_revenue = Column(DECIMAL(15, 2), nullable=False, default=0)
    recurring_revenue = Column(DECIMAL(15, 2), nullable=False, default=0)

    # MRR/ARR
    mrr = Column(DECIMAL(15, 2), comment="Monthly Recurring Revenue")
    arr = Column(DECIMAL(15, 2), comment="Annual Recurring Revenue")

    # Customer Metrics
    total_paying_customers = Column(Integer, nullable=False, default=0)
    new_customers = Column(Integer, nullable=False, default=0)
    churned_customers = Column(Integer, nullable=False, default=0)

    # ARPU
    arpu = Column(DECIMAL(10, 2), comment="Average Revenue Per User")

    # Churn
    churn_rate = Column(DECIMAL(5, 4))

    # Detailed Metrics
    detailed_metrics = Column(JSONB)


class ErrorAnalytics(Base, UUIDMixin, TimestampMixin):
    """Error and exception analytics"""
    __tablename__ = "error_analytics"
    __table_args__ = (
        Index('idx_error_analytics_period_start', 'period_start'),
        Index('idx_error_analytics_error_type', 'error_type'),
        Index('idx_error_analytics_severity', 'severity'),
        {'schema': 'analytics', 'comment': 'Error analytics'}
    )

    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(Enum(AnalyticsPeriod), nullable=False)

    # Error Info
    error_type = Column(String(255), nullable=False)
    error_category = Column(String(100))
    severity = Column(String(50), comment="critical, error, warning")

    # Occurrence
    total_occurrences = Column(BigInteger, nullable=False, default=0)
    unique_users_affected = Column(Integer, nullable=False, default=0)

    # Impact
    total_requests_affected = Column(BigInteger, nullable=False, default=0)
    error_rate = Column(DECIMAL(5, 4))

    # Resolution
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime)

    # Detailed Metrics
    detailed_metrics = Column(JSONB)
