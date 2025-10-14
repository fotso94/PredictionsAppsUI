"""
SQLAlchemy Models
All database models for the Soccer Predictions Platform
66 models across 5 schemas
"""

from app.models.base import Base

# Import all models for Alembic autogenerate
# Users schema models (17 tables)
from app.models.users import (
    User,
    ExpertProfile,
    AdminProfile,
    UserSession,
    UserPreference,
    UserActivityLog,
    UserSubscription,
    UserNotification,
    ExpertSpecialty,
    ExpertPerformanceMetric,
    AdminPermission,
    AdminActivityLog,
    Role,
    Permission,
    UserRole,
    RolePermission,
    PasswordResetToken,
)

# Predictions schema models (16 tables)
from app.models.predictions import (
    Prediction,
    PredictionOverride,
    PredictionAudit,
    PredictionResult,
    PredictionMarket,
    PredictionAnalytics,
    UserPredictionView,
    UserPredictionFeedback,
    Match,
    MatchResult,
    MatchStatistic,
    League,
    Team,
    PredictionTemplate,
    PredictionComment,
    PredictionShare,
)

# ML Models schema models (12 tables)
from app.models.ml_models import (
    MLModel,
    MLModelVersion,
    MLTrainingRun,
    MLModelPerformance,
    MLPrediction,
    MLFeature,
    MLFeatureEngineering,
    MLModelDeployment,
    MLABTest,
    MLABTestResult,
    MLEnsembleConfig,
    MLModelMetadata,
)

# Analytics schema models (13 tables)
from app.models.analytics import (
    UserAnalytics,
    UserEngagementMetric,
    UserActivityLog as AnalyticsUserActivityLog,
    PredictionAnalyticsSummary,
    PredictionPerformanceMetric,
    ExpertAnalytics,
    ModelPerformanceAnalytics,
    SystemAnalytics,
    APIUsageAnalytics,
    FeatureUsageAnalytics,
    ConversionAnalytics,
    RevenueAnalytics,
    ErrorAnalytics,
)

# Audit schema models (8 tables)
from app.models.audit import (
    AuditLog,
    DataAccessLog,
    PredictionChangeLog,
    UserActionLog,
    AdminActionLog,
    SystemEventLog,
    GDPRConsentLog,
    DataExportLog,
)

__all__ = [
    # Base
    "Base",

    # Users schema (17)
    "User",
    "ExpertProfile",
    "AdminProfile",
    "UserSession",
    "UserPreference",
    "UserActivityLog",
    "UserSubscription",
    "UserNotification",
    "ExpertSpecialty",
    "ExpertPerformanceMetric",
    "AdminPermission",
    "AdminActivityLog",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "PasswordResetToken",

    # Predictions schema (16)
    "Prediction",
    "PredictionOverride",
    "PredictionAudit",
    "PredictionResult",
    "PredictionMarket",
    "PredictionAnalytics",
    "UserPredictionView",
    "UserPredictionFeedback",
    "Match",
    "MatchResult",
    "MatchStatistic",
    "League",
    "Team",
    "PredictionTemplate",
    "PredictionComment",
    "PredictionShare",

    # ML Models schema (12)
    "MLModel",
    "MLModelVersion",
    "MLTrainingRun",
    "MLModelPerformance",
    "MLPrediction",
    "MLFeature",
    "MLFeatureEngineering",
    "MLModelDeployment",
    "MLABTest",
    "MLABTestResult",
    "MLEnsembleConfig",
    "MLModelMetadata",

    # Analytics schema (13)
    "UserAnalytics",
    "UserEngagementMetric",
    "AnalyticsUserActivityLog",
    "PredictionAnalyticsSummary",
    "PredictionPerformanceMetric",
    "ExpertAnalytics",
    "ModelPerformanceAnalytics",
    "SystemAnalytics",
    "APIUsageAnalytics",
    "FeatureUsageAnalytics",
    "ConversionAnalytics",
    "RevenueAnalytics",
    "ErrorAnalytics",

    # Audit schema (8)
    "AuditLog",
    "DataAccessLog",
    "PredictionChangeLog",
    "UserActionLog",
    "AdminActionLog",
    "SystemEventLog",
    "GDPRConsentLog",
    "DataExportLog",
]

