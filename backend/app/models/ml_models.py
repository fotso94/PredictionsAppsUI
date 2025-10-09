"""
ML Models Schema Models
12 tables for ML model management, training, and performance tracking
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
class ModelStatus(str, enum.Enum):
    """ML model status enumeration"""
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ModelType(str, enum.Enum):
    """ML model type enumeration"""
    RANDOM_FOREST = "random_forest"
    XGBOOST = "xgboost"
    NEURAL_NETWORK = "neural_network"
    ENSEMBLE = "ensemble"
    LOGISTIC_REGRESSION = "logistic_regression"
    SVM = "svm"


class TrainingStatus(str, enum.Enum):
    """Training run status enumeration"""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeploymentStatus(str, enum.Enum):
    """Deployment status enumeration"""
    DEPLOYING = "deploying"
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# Models

class MLModel(Base, UUIDMixin, TimestampMixin):
    """
    ML model registry
    Central registry for all ML models
    """
    __tablename__ = "ml_models"
    __table_args__ = (
        Index('idx_ml_models_model_name', 'model_name'),
        Index('idx_ml_models_model_type', 'model_type'),
        Index('idx_ml_models_model_status', 'model_status'),
        Index('idx_ml_models_is_champion', 'is_champion'),
        Index('idx_ml_models_is_deployed', 'is_deployed'),
        {'schema': 'ml_models', 'comment': 'ML model registry'}
    )
    
    # Model Info
    model_name = Column(String(255), nullable=False)
    model_version = Column(String(50), nullable=False, comment="Semantic version")
    model_type = Column(Enum(ModelType), nullable=False)
    description = Column(Text)
    
    # Status
    model_status = Column(Enum(ModelStatus), nullable=False, default=ModelStatus.DEVELOPMENT)
    is_champion = Column(Boolean, nullable=False, default=False, comment="Best performing model")
    is_deployed = Column(Boolean, nullable=False, default=False)
    
    # Framework
    framework = Column(String(50), comment="scikit-learn, tensorflow, pytorch")
    framework_version = Column(String(50))
    
    # Hyperparameters
    hyperparameters = Column(JSONB, comment="Model hyperparameters")
    
    # Storage
    s3_model_path = Column(String(500), comment="S3 path to model artifact")
    s3_checkpoint_path = Column(String(500))
    model_size_bytes = Column(BigInteger)
    
    # Performance
    training_accuracy = Column(DECIMAL(5, 4))
    validation_accuracy = Column(DECIMAL(5, 4))
    test_accuracy = Column(DECIMAL(5, 4))
    
    # Ownership
    created_by_user_id = uuid_fk('users.users.id', nullable=True)
    
    # Metadata
    model_metadata = Column(JSONB)
    
    # Relationships
    versions = relationship("MLModelVersion", back_populates="model", cascade="all, delete-orphan")
    training_runs = relationship("MLTrainingRun", back_populates="model", cascade="all, delete-orphan")
    performance_metrics = relationship("MLModelPerformance", back_populates="model", cascade="all, delete-orphan")
    predictions = relationship("MLPrediction", back_populates="model", cascade="all, delete-orphan")
    deployments = relationship("MLModelDeployment", back_populates="model", cascade="all, delete-orphan")
    ab_tests = relationship("MLABTest", back_populates="model_a")


class MLModelVersion(Base, UUIDMixin, TimestampMixin):
    """ML model versions"""
    __tablename__ = "ml_model_versions"
    __table_args__ = (
        Index('idx_ml_model_versions_model_id', 'model_id'),
        Index('idx_ml_model_versions_version', 'version'),
        Index('idx_ml_model_versions_is_production', 'is_production'),
        UniqueConstraint('model_id', 'version', name='uq_ml_model_versions_model_version'),
        {'schema': 'ml_models', 'comment': 'ML model versions'}
    )
    
    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)
    
    # Version Info
    version = Column(String(50), nullable=False)
    version_notes = Column(Text)
    
    # Parameters
    parameters = Column(JSONB, nullable=False)
    model_artifact_path = Column(String(500), nullable=False)
    
    # Training Data
    training_data_hash = Column(String(255), comment="Hash of training data")
    training_data_size = Column(Integer)
    
    # Status
    is_production = Column(Boolean, nullable=False, default=False)
    deployed_at = Column(DateTime)
    deprecated_at = Column(DateTime)
    
    # Relationships
    model = relationship("MLModel", back_populates="versions")


class MLTrainingRun(Base, UUIDMixin, TimestampMixin):
    """ML model training runs"""
    __tablename__ = "ml_training_runs"
    __table_args__ = (
        Index('idx_ml_training_runs_model_id', 'model_id'),
        Index('idx_ml_training_runs_status', 'status'),
        Index('idx_ml_training_runs_started_at', 'started_at'),
        {'schema': 'ml_models', 'comment': 'ML training runs'}
    )
    
    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)
    model_version_id = uuid_fk('ml_models.ml_model_versions.id', nullable=True)
    
    # Training Info
    training_job_id = Column(String(255), unique=True)
    status = Column(Enum(TrainingStatus), nullable=False, default=TrainingStatus.QUEUED)
    
    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Integer)
    
    # Parameters
    training_parameters = Column(JSONB, nullable=False)
    training_data_size = Column(Integer)
    validation_data_size = Column(Integer)
    test_data_size = Column(Integer)
    
    # Results
    final_metrics = Column(JSONB, comment="Final training metrics")
    best_epoch = Column(Integer)
    total_epochs = Column(Integer)
    
    # Error Handling
    error_message = Column(Text)
    error_traceback = Column(Text)
    
    # Ownership
    triggered_by_user_id = uuid_fk('users.users.id', nullable=True)
    
    # Relationships
    model = relationship("MLModel", back_populates="training_runs")


class MLModelPerformance(Base, UUIDMixin, TimestampMixin):
    """ML model performance metrics"""
    __tablename__ = "ml_model_performance"
    __table_args__ = (
        Index('idx_ml_model_performance_model_id', 'model_id'),
        Index('idx_ml_model_performance_evaluation_date', 'evaluation_date'),
        {'schema': 'ml_models', 'comment': 'ML model performance'}
    )
    
    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)
    model_version_id = uuid_fk('ml_models.ml_model_versions.id', nullable=True)
    
    # Evaluation Info
    evaluation_date = Column(DateTime, nullable=False, default=datetime.utcnow)
    evaluation_period = Column(String(50), comment="daily, weekly, monthly")
    
    # Metrics
    accuracy = Column(DECIMAL(5, 4))
    precision = Column(DECIMAL(5, 4))
    recall = Column(DECIMAL(5, 4))
    f1_score = Column(DECIMAL(5, 4))
    auc_roc = Column(DECIMAL(5, 4))
    
    # Calibration
    confidence_calibration = Column(DECIMAL(5, 4))
    brier_score = Column(DECIMAL(5, 4))
    
    # Volume
    total_predictions = Column(Integer, nullable=False, default=0)
    correct_predictions = Column(Integer, nullable=False, default=0)
    
    # Detailed Metrics
    detailed_metrics = Column(JSONB, comment="Additional metrics")
    
    # Relationships
    model = relationship("MLModel", back_populates="performance_metrics")


class MLPrediction(Base, UUIDMixin, TimestampMixin):
    """Raw ML predictions"""
    __tablename__ = "ml_predictions"
    __table_args__ = (
        Index('idx_ml_predictions_model_id', 'model_id'),
        Index('idx_ml_predictions_match_id', 'match_id'),
        Index('idx_ml_predictions_created_at', 'created_at'),
        Index('idx_ml_predictions_was_overridden', 'was_overridden'),
        {'schema': 'ml_models', 'comment': 'Raw ML predictions'}
    )
    
    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)
    match_id = uuid_fk('predictions.matches.id', nullable=False)
    
    # Predictions
    home_win_prob = Column(DECIMAL(5, 4), nullable=False)
    draw_prob = Column(DECIMAL(5, 4), nullable=False)
    away_win_prob = Column(DECIMAL(5, 4), nullable=False)
    
    # Confidence
    confidence_score = Column(DECIMAL(5, 4), nullable=False)
    prediction_quality_score = Column(DECIMAL(5, 4))
    
    # Features Used
    features_used = Column(JSONB, comment="Features used for prediction")
    feature_importance = Column(JSONB, comment="Feature importance scores")
    
    # Override Tracking
    was_overridden = Column(Boolean, nullable=False, default=False)
    overridden_by_expert_id = uuid_fk('users.expert_profiles.id', nullable=True)
    override_reason = Column(Text)
    
    # Model Version
    model_version = Column(String(50))
    
    # Relationships
    model = relationship("MLModel", back_populates="predictions")


class MLFeature(Base, UUIDMixin, TimestampMixin):
    """ML feature definitions"""
    __tablename__ = "ml_features"
    __table_args__ = (
        Index('idx_ml_features_feature_name', 'feature_name'),
        Index('idx_ml_features_feature_category', 'feature_category'),
        Index('idx_ml_features_is_active', 'is_active'),
        {'schema': 'ml_models', 'comment': 'ML feature definitions'}
    )
    
    # Feature Info
    feature_name = Column(String(255), nullable=False, unique=True)
    feature_category = Column(String(100), comment="team_stats, player_stats, historical, etc.")
    description = Column(Text)
    
    # Data Type
    data_type = Column(String(50), nullable=False, comment="numeric, categorical, boolean")
    calculation_method = Column(Text, comment="How feature is calculated")
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Importance
    average_importance = Column(DECIMAL(5, 4))
    
    # Metadata
    feature_metadata = Column(JSONB)


class MLFeatureEngineering(Base, UUIDMixin, TimestampMixin):
    """Feature engineering transformations"""
    __tablename__ = "ml_feature_engineering"
    __table_args__ = (
        Index('idx_ml_feature_engineering_feature_id', 'feature_id'),
        Index('idx_ml_feature_engineering_is_active', 'is_active'),
        {'schema': 'ml_models', 'comment': 'Feature engineering'}
    )
    
    feature_id = uuid_fk('ml_models.ml_features.id', nullable=False)
    
    # Transformation Info
    transformation_name = Column(String(255), nullable=False)
    transformation_type = Column(String(100), comment="scaling, encoding, binning, etc.")
    transformation_config = Column(JSONB, nullable=False)
    
    # Code
    transformation_code = Column(Text, comment="Python code for transformation")
    
    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Ownership
    created_by_user_id = uuid_fk('users.users.id', nullable=True)


class MLModelDeployment(Base, UUIDMixin, TimestampMixin):
    """ML model deployment history"""
    __tablename__ = "ml_model_deployments"
    __table_args__ = (
        Index('idx_ml_model_deployments_model_id', 'model_id'),
        Index('idx_ml_model_deployments_status', 'status'),
        Index('idx_ml_model_deployments_deployed_at', 'deployed_at'),
        {'schema': 'ml_models', 'comment': 'ML model deployments'}
    )
    
    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)
    model_version_id = uuid_fk('ml_models.ml_model_versions.id', nullable=False)
    
    # Deployment Info
    deployment_environment = Column(String(50), nullable=False, comment="staging, production")
    status = Column(Enum(DeploymentStatus), nullable=False, default=DeploymentStatus.DEPLOYING)
    
    # Timing
    deployed_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    deactivated_at = Column(DateTime)
    
    # Deployment Config
    deployment_config = Column(JSONB)
    
    # Ownership
    deployed_by_user_id = uuid_fk('users.users.id', nullable=True)
    
    # Rollback
    rollback_reason = Column(Text)
    rolled_back_at = Column(DateTime)
    
    # Relationships
    model = relationship("MLModel", back_populates="deployments")


class MLABTest(Base, UUIDMixin, TimestampMixin):
    """A/B tests for model comparison"""
    __tablename__ = "ml_ab_tests"
    __table_args__ = (
        Index('idx_ml_ab_tests_model_a_id', 'model_a_id'),
        Index('idx_ml_ab_tests_model_b_id', 'model_b_id'),
        Index('idx_ml_ab_tests_is_active', 'is_active'),
        Index('idx_ml_ab_tests_started_at', 'started_at'),
        {'schema': 'ml_models', 'comment': 'ML A/B tests'}
    )

    # Test Info
    test_name = Column(String(255), nullable=False)
    description = Column(Text)

    # Models
    model_a_id = uuid_fk('ml_models.ml_models.id', nullable=False)
    model_b_id = uuid_fk('ml_models.ml_models.id', nullable=False)

    # Traffic Split
    traffic_split_percentage = Column(Integer, nullable=False, default=50, comment="% traffic to model A")

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Timing
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    ended_at = Column(DateTime)

    # Results
    winner_model_id = uuid_fk('ml_models.ml_models.id', nullable=True)
    conclusion = Column(Text)

    # Ownership
    created_by_user_id = uuid_fk('users.users.id', nullable=True)

    # Relationships
    model_a = relationship("MLModel", foreign_keys=[model_a_id], back_populates="ab_tests")
    results = relationship("MLABTestResult", back_populates="ab_test", cascade="all, delete-orphan")


class MLABTestResult(Base, UUIDMixin, TimestampMixin):
    """A/B test results"""
    __tablename__ = "ml_ab_test_results"
    __table_args__ = (
        Index('idx_ml_ab_test_results_ab_test_id', 'ab_test_id'),
        Index('idx_ml_ab_test_results_model_id', 'model_id'),
        Index('idx_ml_ab_test_results_evaluation_date', 'evaluation_date'),
        {'schema': 'ml_models', 'comment': 'ML A/B test results'}
    )

    ab_test_id = uuid_fk('ml_models.ml_ab_tests.id', nullable=False)
    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)

    # Evaluation
    evaluation_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Metrics
    total_predictions = Column(Integer, nullable=False, default=0)
    correct_predictions = Column(Integer, nullable=False, default=0)
    accuracy = Column(DECIMAL(5, 4))

    # User Engagement
    user_engagement_score = Column(DECIMAL(10, 2))
    average_confidence = Column(DECIMAL(5, 4))

    # Detailed Results
    detailed_results = Column(JSONB)

    # Relationships
    ab_test = relationship("MLABTest", back_populates="results")


class MLEnsembleConfig(Base, UUIDMixin, TimestampMixin):
    """Ensemble model configurations"""
    __tablename__ = "ml_ensemble_configs"
    __table_args__ = (
        Index('idx_ml_ensemble_configs_ensemble_model_id', 'ensemble_model_id'),
        Index('idx_ml_ensemble_configs_is_active', 'is_active'),
        {'schema': 'ml_models', 'comment': 'ML ensemble configurations'}
    )

    ensemble_model_id = uuid_fk('ml_models.ml_models.id', nullable=False)

    # Ensemble Info
    ensemble_method = Column(String(50), nullable=False, comment="voting, stacking, blending")
    member_models = Column(JSONB, nullable=False, comment="List of member model IDs and weights")

    # Weights
    model_weights = Column(JSONB, comment="Weights for each model")

    # Configuration
    ensemble_config = Column(JSONB, comment="Additional ensemble configuration")

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Performance
    ensemble_accuracy = Column(DECIMAL(5, 4))


class MLModelMetadata(Base, UUIDMixin, TimestampMixin):
    """Additional ML model metadata"""
    __tablename__ = "ml_model_metadata"
    __table_args__ = (
        Index('idx_ml_model_metadata_model_id', 'model_id'),
        Index('idx_ml_model_metadata_metadata_key', 'metadata_key'),
        {'schema': 'ml_models', 'comment': 'ML model metadata'}
    )

    model_id = uuid_fk('ml_models.ml_models.id', nullable=False)

    # Metadata
    metadata_key = Column(String(255), nullable=False)
    metadata_value = Column(JSONB, nullable=False)

    # Description
    description = Column(Text)
