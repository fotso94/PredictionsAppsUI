"""
Users Schema Models
17 tables for user management, authentication, and RBAC
"""

from datetime import datetime
from typing import List

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, Enum,
    ForeignKey, Index, UniqueConstraint, CheckConstraint, DECIMAL
)
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, uuid_fk
import enum


# Enums
class UserType(str, enum.Enum):
    """User type enumeration"""
    REGULAR = "regular"
    EXPERT = "expert"
    ADMIN = "admin"


class AccountStatus(str, enum.Enum):
    """Account status enumeration"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    PENDING_VERIFICATION = "pending_verification"


class SubscriptionTier(str, enum.Enum):
    """Subscription tier enumeration"""
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    PRO = "pro"


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enumeration"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"


class NotificationType(str, enum.Enum):
    """Notification type enumeration"""
    PREDICTION_PUBLISHED = "prediction_published"
    PREDICTION_RESULT = "prediction_result"
    EXPERT_OVERRIDE = "expert_override"
    SYSTEM_ALERT = "system_alert"
    SUBSCRIPTION_EXPIRING = "subscription_expiring"


# Models

class User(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Core user accounts table
    Supports Regular, Expert, and Admin user types
    """
    __tablename__ = "users"
    __table_args__ = (
        Index('idx_users_email', 'email'),
        Index('idx_users_username', 'username'),
        Index('idx_users_user_type', 'user_type'),
        Index('idx_users_account_status', 'account_status'),
        Index('idx_users_created_at', 'created_at'),
        {'schema': 'users', 'comment': 'Core user accounts'}
    )
    
    # Basic Info
    email = Column(String(255), nullable=False, unique=True, comment="User email address")
    username = Column(String(50), nullable=False, unique=True, comment="Unique username")
    password_hash = Column(String(255), nullable=False, comment="Bcrypt hashed password")
    first_name = Column(String(100), comment="First name")
    last_name = Column(String(100), comment="Last name")
    avatar_url = Column(String(500), comment="Profile image URL")
    
    # User Type & Status
    user_type = Column(Enum(UserType), nullable=False, default=UserType.REGULAR, comment="User type")
    account_status = Column(Enum(AccountStatus), nullable=False, default=AccountStatus.PENDING_VERIFICATION)
    
    # Email Verification
    email_verified = Column(Boolean, nullable=False, default=False)
    email_verification_token = Column(String(255))
    email_verified_at = Column(DateTime)
    
    # Password Reset
    password_reset_token = Column(String(255))
    password_reset_expires_at = Column(DateTime)
    
    # Login Tracking
    last_login_at = Column(DateTime)
    last_login_ip = Column(INET)
    
    # Localization
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="en")
    
    # Relationships
    expert_profile = relationship("ExpertProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    admin_profile = relationship("AdminProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("UserActivityLog", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("UserSubscription", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("UserNotification", back_populates="user", cascade="all, delete-orphan")
    user_roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, type={self.user_type})>"


class ExpertProfile(Base, UUIDMixin, TimestampMixin):
    """Expert user extended profile"""
    __tablename__ = "expert_profiles"
    __table_args__ = (
        Index('idx_expert_profiles_user_id', 'user_id'),
        Index('idx_expert_profiles_is_verified', 'is_verified'),
        Index('idx_expert_profiles_accuracy_score', 'accuracy_score'),
        {'schema': 'users', 'comment': 'Expert user profiles'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False, unique=True, comment="Reference to user")
    
    # Expert Info
    bio = Column(Text, comment="Expert biography")
    expertise_areas = Column(JSONB, comment="Areas of expertise (leagues, teams)")
    years_of_experience = Column(Integer, comment="Years of experience")
    
    # Verification
    is_verified = Column(Boolean, nullable=False, default=False)
    verified_at = Column(DateTime)
    verified_by_admin_id = uuid_fk('users.users.id', nullable=True)
    
    # Performance Metrics
    total_predictions = Column(Integer, nullable=False, default=0)
    correct_predictions = Column(Integer, nullable=False, default=0)
    accuracy_score = Column(DECIMAL(5, 2), comment="Overall accuracy percentage")
    average_confidence = Column(DECIMAL(5, 2), comment="Average confidence score")
    roi_percentage = Column(DECIMAL(10, 2), comment="Return on investment %")
    
    # Reputation
    reputation_score = Column(Integer, nullable=False, default=0)
    follower_count = Column(Integer, nullable=False, default=0)
    
    # Performance Data (JSONB)
    performance_data = Column(JSONB, comment="Detailed performance metrics")
    
    # Relationships
    user = relationship("User", back_populates="expert_profile")
    specialties = relationship("ExpertSpecialty", back_populates="expert_profile", cascade="all, delete-orphan")
    performance_metrics = relationship("ExpertPerformanceMetric", back_populates="expert_profile", cascade="all, delete-orphan")


class AdminProfile(Base, UUIDMixin, TimestampMixin):
    """Admin user extended profile"""
    __tablename__ = "admin_profiles"
    __table_args__ = (
        Index('idx_admin_profiles_user_id', 'user_id'),
        Index('idx_admin_profiles_is_super_admin', 'is_super_admin'),
        {'schema': 'users', 'comment': 'Admin user profiles'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False, unique=True)
    
    # Admin Info
    department = Column(String(100), comment="Department/team")
    job_title = Column(String(100), comment="Job title")
    
    # Permissions
    is_super_admin = Column(Boolean, nullable=False, default=False)
    can_approve_predictions = Column(Boolean, nullable=False, default=False)
    can_manage_users = Column(Boolean, nullable=False, default=False)
    can_manage_experts = Column(Boolean, nullable=False, default=False)
    can_access_audit_logs = Column(Boolean, nullable=False, default=False)
    can_manage_system_settings = Column(Boolean, nullable=False, default=False)
    
    # Activity Tracking
    last_admin_action_at = Column(DateTime)
    total_actions_count = Column(Integer, nullable=False, default=0)
    
    # Relationships
    user = relationship("User", back_populates="admin_profile")
    permissions = relationship("AdminPermission", back_populates="admin_profile", cascade="all, delete-orphan")
    activity_logs = relationship("AdminActivityLog", back_populates="admin_profile", cascade="all, delete-orphan")


class UserSession(Base, UUIDMixin, TimestampMixin):
    """User authentication sessions (JWT refresh tokens)"""
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index('idx_user_sessions_user_id', 'user_id'),
        Index('idx_user_sessions_refresh_token', 'refresh_token'),
        Index('idx_user_sessions_expires_at', 'expires_at'),
        Index('idx_user_sessions_is_active', 'is_active'),
        {'schema': 'users', 'comment': 'User authentication sessions'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Session Info
    refresh_token = Column(String(500), nullable=False, unique=True)
    access_token_jti = Column(String(255), comment="JWT ID of access token")
    
    # Device Info
    device_info = Column(JSONB, comment="Device information")
    ip_address = Column(INET)
    user_agent = Column(Text)
    
    # Session Status
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime, nullable=False)
    last_activity_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="sessions")


class UserPreference(Base, UUIDMixin, TimestampMixin):
    """User preferences and settings"""
    __tablename__ = "user_preferences"
    __table_args__ = (
        Index('idx_user_preferences_user_id', 'user_id'),
        {'schema': 'users', 'comment': 'User preferences'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False, unique=True)
    
    # Notification Preferences
    email_notifications = Column(Boolean, nullable=False, default=True)
    push_notifications = Column(Boolean, nullable=False, default=True)
    sms_notifications = Column(Boolean, nullable=False, default=False)
    
    # Display Preferences
    theme = Column(String(20), default="light", comment="UI theme")
    odds_format = Column(String(20), default="decimal", comment="Odds display format")
    
    # Content Preferences
    favorite_leagues = Column(JSONB, comment="Favorite league IDs")
    favorite_teams = Column(JSONB, comment="Favorite team IDs")
    favorite_experts = Column(JSONB, comment="Favorite expert IDs")
    
    # Privacy Settings
    profile_visibility = Column(String(20), default="public")
    show_prediction_history = Column(Boolean, nullable=False, default=True)
    
    # Other Settings
    additional_settings = Column(JSONB, comment="Additional user settings")
    
    # Relationships
    user = relationship("User", back_populates="preferences")


class UserActivityLog(Base, UUIDMixin, TimestampMixin):
    """User activity audit trail"""
    __tablename__ = "user_activity_log"
    __table_args__ = (
        Index('idx_user_activity_log_user_id', 'user_id'),
        Index('idx_user_activity_log_activity_type', 'activity_type'),
        Index('idx_user_activity_log_created_at', 'created_at'),
        {'schema': 'users', 'comment': 'User activity log'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Activity Info
    activity_type = Column(String(100), nullable=False, comment="Type of activity")
    activity_description = Column(Text)
    activity_data = Column(JSONB, comment="Additional activity data")
    
    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    session_id = Column(UUID)
    
    # Relationships
    user = relationship("User", back_populates="activity_logs")


class UserSubscription(Base, UUIDMixin, TimestampMixin):
    """User subscription management"""
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        Index('idx_user_subscriptions_user_id', 'user_id'),
        Index('idx_user_subscriptions_status', 'status'),
        Index('idx_user_subscriptions_expires_at', 'expires_at'),
        {'schema': 'users', 'comment': 'User subscriptions'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Subscription Info
    tier = Column(Enum(SubscriptionTier), nullable=False, default=SubscriptionTier.FREE)
    status = Column(Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.ACTIVE)
    
    # Billing
    stripe_subscription_id = Column(String(255), unique=True)
    stripe_customer_id = Column(String(255))
    
    # Dates
    starts_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    trial_ends_at = Column(DateTime)
    
    # Pricing
    price_amount = Column(DECIMAL(10, 2))
    currency = Column(String(3), default="USD")
    billing_cycle = Column(String(20), comment="monthly, yearly")
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")


class UserNotification(Base, UUIDMixin, TimestampMixin):
    """User notifications"""
    __tablename__ = "user_notifications"
    __table_args__ = (
        Index('idx_user_notifications_user_id', 'user_id'),
        Index('idx_user_notifications_is_read', 'is_read'),
        Index('idx_user_notifications_created_at', 'created_at'),
        {'schema': 'users', 'comment': 'User notifications'}
    )

    user_id = uuid_fk('users.users.id', nullable=False)

    # Notification Info
    notification_type = Column(Enum(NotificationType), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # Status
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime)

    # Data
    notification_data = Column(JSONB, comment="Additional notification data")
    action_url = Column(String(500), comment="URL for notification action")

    # Relationships
    user = relationship("User", back_populates="notifications")


class ExpertSpecialty(Base, UUIDMixin, TimestampMixin):
    """Expert specialization areas"""
    __tablename__ = "expert_specialties"
    __table_args__ = (
        Index('idx_expert_specialties_expert_profile_id', 'expert_profile_id'),
        Index('idx_expert_specialties_specialty_type', 'specialty_type'),
        {'schema': 'users', 'comment': 'Expert specialties'}
    )

    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=False)

    # Specialty Info
    specialty_type = Column(String(50), nullable=False, comment="league, team, market_type")
    specialty_value = Column(String(255), nullable=False, comment="Specific league/team/market")

    # Performance in Specialty
    predictions_count = Column(Integer, nullable=False, default=0)
    accuracy_rate = Column(DECIMAL(5, 2))
    confidence_level = Column(String(20), comment="high, medium, low")

    # Relationships
    expert_profile = relationship("ExpertProfile", back_populates="specialties")


class ExpertPerformanceMetric(Base, UUIDMixin, TimestampMixin):
    """Expert performance metrics over time"""
    __tablename__ = "expert_performance_metrics"
    __table_args__ = (
        Index('idx_expert_performance_metrics_expert_profile_id', 'expert_profile_id'),
        Index('idx_expert_performance_metrics_period_start', 'period_start'),
        {'schema': 'users', 'comment': 'Expert performance metrics'}
    )

    expert_profile_id = uuid_fk('users.expert_profiles.id', nullable=False)

    # Time Period
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    period_type = Column(String(20), nullable=False, comment="daily, weekly, monthly, yearly")

    # Metrics
    total_predictions = Column(Integer, nullable=False, default=0)
    correct_predictions = Column(Integer, nullable=False, default=0)
    accuracy_rate = Column(DECIMAL(5, 2))
    average_confidence = Column(DECIMAL(5, 2))
    roi_percentage = Column(DECIMAL(10, 2))

    # Detailed Metrics
    detailed_metrics = Column(JSONB, comment="Detailed performance data")

    # Relationships
    expert_profile = relationship("ExpertProfile", back_populates="performance_metrics")


class AdminPermission(Base, UUIDMixin, TimestampMixin):
    """Admin-specific permissions"""
    __tablename__ = "admin_permissions"
    __table_args__ = (
        Index('idx_admin_permissions_admin_profile_id', 'admin_profile_id'),
        Index('idx_admin_permissions_permission_type', 'permission_type'),
        {'schema': 'users', 'comment': 'Admin permissions'}
    )

    admin_profile_id = uuid_fk('users.admin_profiles.id', nullable=False)

    # Permission Info
    permission_type = Column(String(100), nullable=False)
    permission_scope = Column(String(100), comment="global, league, team")
    scope_constraints = Column(JSONB, comment="Scope limitations")

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    granted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    granted_by_admin_id = uuid_fk('users.users.id', nullable=True)
    expires_at = Column(DateTime)

    # Relationships
    admin_profile = relationship("AdminProfile", back_populates="permissions")


class AdminActivityLog(Base, UUIDMixin, TimestampMixin):
    """Admin action audit trail"""
    __tablename__ = "admin_activity_log"
    __table_args__ = (
        Index('idx_admin_activity_log_admin_profile_id', 'admin_profile_id'),
        Index('idx_admin_activity_log_action_type', 'action_type'),
        Index('idx_admin_activity_log_created_at', 'created_at'),
        {'schema': 'users', 'comment': 'Admin activity log'}
    )

    admin_profile_id = uuid_fk('users.admin_profiles.id', nullable=False)

    # Action Info
    action_type = Column(String(100), nullable=False)
    action_description = Column(Text)
    target_resource_type = Column(String(100), comment="user, prediction, expert")
    target_resource_id = Column(UUID)

    # Action Data
    action_details = Column(JSONB, comment="Detailed action data")
    changes_made = Column(JSONB, comment="Before/after changes")

    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)

    # Relationships
    admin_profile = relationship("AdminProfile", back_populates="activity_logs")


class Role(Base, UUIDMixin, TimestampMixin):
    """RBAC roles"""
    __tablename__ = "roles"
    __table_args__ = (
        Index('idx_roles_name', 'name'),
        Index('idx_roles_is_active', 'is_active'),
        {'schema': 'users', 'comment': 'RBAC roles'}
    )

    # Role Info
    name = Column(String(50), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    is_system_role = Column(Boolean, nullable=False, default=False, comment="System-defined role")

    # Relationships
    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")


class Permission(Base, UUIDMixin, TimestampMixin):
    """RBAC permissions"""
    __tablename__ = "permissions"
    __table_args__ = (
        Index('idx_permissions_name', 'name'),
        Index('idx_permissions_resource_type', 'resource_type'),
        {'schema': 'users', 'comment': 'RBAC permissions'}
    )

    # Permission Info
    name = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(150), nullable=False)
    description = Column(Text)

    # Resource
    resource_type = Column(String(50), nullable=False, comment="prediction, user, expert, admin")
    action = Column(String(50), nullable=False, comment="create, read, update, delete, approve")

    # Relationships
    role_permissions = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")


class UserRole(Base, UUIDMixin, TimestampMixin):
    """User-Role assignments"""
    __tablename__ = "user_roles"
    __table_args__ = (
        Index('idx_user_roles_user_id', 'user_id'),
        Index('idx_user_roles_role_id', 'role_id'),
        UniqueConstraint('user_id', 'role_id', name='uq_user_roles_user_role'),
        {'schema': 'users', 'comment': 'User-role assignments'}
    )

    user_id = uuid_fk('users.users.id', nullable=False)
    role_id = uuid_fk('users.roles.id', nullable=False)

    # Assignment Info
    assigned_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    assigned_by_admin_id = uuid_fk('users.users.id', nullable=True)
    expires_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class RolePermission(Base, UUIDMixin, TimestampMixin):
    """Role-Permission assignments"""
    __tablename__ = "role_permissions"
    __table_args__ = (
        Index('idx_role_permissions_role_id', 'role_id'),
        Index('idx_role_permissions_permission_id', 'permission_id'),
        UniqueConstraint('role_id', 'permission_id', name='uq_role_permissions_role_permission'),
        {'schema': 'users', 'comment': 'Role-permission assignments'}
    )

    role_id = uuid_fk('users.roles.id', nullable=False)
    permission_id = uuid_fk('users.permissions.id', nullable=False)

    # Assignment Info
    granted_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    granted_by_admin_id = uuid_fk('users.users.id', nullable=True)

    # Relationships
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


class PasswordResetToken(Base, UUIDMixin, TimestampMixin):
    """Password reset tokens"""
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index('idx_password_reset_tokens_user_id', 'user_id'),
        Index('idx_password_reset_tokens_token', 'token'),
        Index('idx_password_reset_tokens_expires_at', 'expires_at'),
        {'schema': 'users', 'comment': 'Password reset tokens'}
    )

    user_id = uuid_fk('users.users.id', nullable=False)

    # Token Info
    token = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)

    # Status
    is_used = Column(Boolean, nullable=False, default=False)
    used_at = Column(DateTime)

    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)

