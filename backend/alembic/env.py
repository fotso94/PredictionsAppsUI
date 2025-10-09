"""
Alembic Environment Configuration
Database migration environment setup
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool, text
from alembic import context
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.base import Base
from app.core.config import settings

# Import all models for Alembic autogenerate (66 models across 5 schemas)
from app.models import (
    # Users schema (17)
    User, ExpertProfile, AdminProfile, UserSession, UserPreference,
    UserActivityLog, UserSubscription, UserNotification, ExpertSpecialty,
    ExpertPerformanceMetric, AdminPermission, AdminActivityLog,
    Role, Permission, UserRole, RolePermission, PasswordResetToken,

    # Predictions schema (16)
    Prediction, PredictionOverride, PredictionAudit, PredictionResult,
    PredictionMarket, PredictionAnalytics, UserPredictionView,
    UserPredictionFeedback, Match, MatchResult, MatchStatistic,
    League, Team, PredictionTemplate, PredictionComment, PredictionShare,

    # ML Models schema (12)
    MLModel, MLModelVersion, MLTrainingRun, MLModelPerformance,
    MLPrediction, MLFeature, MLFeatureEngineering, MLModelDeployment,
    MLABTest, MLABTestResult, MLEnsembleConfig, MLModelMetadata,

    # Analytics schema (13)
    UserAnalytics, UserEngagementMetric, AnalyticsUserActivityLog,
    PredictionAnalyticsSummary, PredictionPerformanceMetric,
    ExpertAnalytics, ModelPerformanceAnalytics, SystemAnalytics,
    APIUsageAnalytics, FeatureUsageAnalytics, ConversionAnalytics,
    RevenueAnalytics, ErrorAnalytics,

    # Audit schema (8)
    AuditLog, DataAccessLog, PredictionChangeLog, UserActionLog,
    AdminActionLog, SystemEventLog, GDPRConsentLog, DataExportLog,
)

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set sqlalchemy.url from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=True,  # Enable multi-schema support
        version_table_schema=None,  # Use default schema for version table
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Create schemas if they don't exist (outside transaction)
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS users"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS predictions"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ml_models"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS audit"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=True,  # Enable multi-schema support
            version_table_schema=None,  # Use default schema for version table
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

