"""
Audit Schema Models
8 tables for audit logging, GDPR compliance, and security monitoring
"""

from datetime import datetime
from typing import List

from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, Enum,
    ForeignKey, Index, UniqueConstraint, CheckConstraint, DECIMAL, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship

from app.models.base import Base, UUIDMixin, TimestampMixin, uuid_fk
import enum


# Enums
class AuditAction(str, enum.Enum):
    """Audit action enumeration"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    APPROVE = "approve"
    REJECT = "reject"
    PUBLISH = "publish"
    ARCHIVE = "archive"


class AuditSeverity(str, enum.Enum):
    """Audit severity enumeration"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class GDPRConsentType(str, enum.Enum):
    """GDPR consent type enumeration"""
    MARKETING = "marketing"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    THIRD_PARTY_SHARING = "third_party_sharing"
    ESSENTIAL = "essential"


class DataExportStatus(str, enum.Enum):
    """Data export status enumeration"""
    REQUESTED = "requested"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


# Models

class AuditLog(Base, UUIDMixin, TimestampMixin):
    """
    Master audit log table
    Comprehensive audit trail for all system actions
    """
    __tablename__ = "audit_log"
    __table_args__ = (
        Index('idx_audit_log_user_id', 'user_id'),
        Index('idx_audit_log_action', 'action'),
        Index('idx_audit_log_resource_type', 'resource_type'),
        Index('idx_audit_log_resource_id', 'resource_id'),
        Index('idx_audit_log_severity', 'severity'),
        Index('idx_audit_log_created_at', 'created_at'),
        Index('idx_audit_log_ip_address', 'ip_address'),
        {'schema': 'audit', 'comment': 'Master audit log'}
    )
    
    # User Info
    user_id = uuid_fk('users.users.id', nullable=True, comment="Null for system actions")
    user_type = Column(String(50), comment="regular, expert, admin, system")
    
    # Action Info
    action = Column(Enum(AuditAction), nullable=False)
    action_description = Column(Text)
    severity = Column(Enum(AuditSeverity), nullable=False, default=AuditSeverity.INFO)
    
    # Resource Info
    resource_type = Column(String(100), nullable=False, comment="user, prediction, match, etc.")
    resource_id = Column(UUID, comment="ID of affected resource")
    resource_name = Column(String(255))
    
    # Changes
    old_values = Column(JSONB, comment="Previous values")
    new_values = Column(JSONB, comment="New values")
    changes_summary = Column(Text)
    
    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    session_id = Column(String(255))
    request_id = Column(String(255), comment="Request tracking ID")
    
    # Metadata
    audit_metadata = Column(JSONB, comment="Additional audit data")
    
    # Retention
    retention_until = Column(DateTime, comment="GDPR retention date")


class DataAccessLog(Base, UUIDMixin, TimestampMixin):
    """
    Data access audit log
    Track all data access for GDPR compliance
    """
    __tablename__ = "data_access_log"
    __table_args__ = (
        Index('idx_data_access_log_user_id', 'user_id'),
        Index('idx_data_access_log_accessed_user_id', 'accessed_user_id'),
        Index('idx_data_access_log_data_type', 'data_type'),
        Index('idx_data_access_log_created_at', 'created_at'),
        Index('idx_data_access_log_is_authorized', 'is_authorized'),
        {'schema': 'audit', 'comment': 'Data access log'}
    )
    
    # Accessor Info
    user_id = uuid_fk('users.users.id', nullable=True, comment="Who accessed the data")
    user_role = Column(String(50))
    
    # Accessed Data
    accessed_user_id = uuid_fk('users.users.id', nullable=True, comment="Whose data was accessed")
    data_type = Column(String(100), nullable=False, comment="user_profile, prediction, etc.")
    data_id = Column(UUID)
    
    # Access Details
    access_method = Column(String(50), nullable=False, comment="api, admin_panel, export")
    access_reason = Column(Text, comment="Reason for access")
    
    # Authorization
    is_authorized = Column(Boolean, nullable=False, default=True)
    authorization_basis = Column(String(100), comment="consent, legitimate_interest, etc.")
    
    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    
    # Metadata
    access_metadata = Column(JSONB)
    
    # Retention
    retention_until = Column(DateTime)


class PredictionChangeLog(Base, UUIDMixin, TimestampMixin):
    """
    Prediction change audit log
    Detailed tracking of all prediction changes
    """
    __tablename__ = "prediction_change_log"
    __table_args__ = (
        Index('idx_prediction_change_log_prediction_id', 'prediction_id'),
        Index('idx_prediction_change_log_changed_by', 'changed_by'),
        Index('idx_prediction_change_log_change_type', 'change_type'),
        Index('idx_prediction_change_log_created_at', 'created_at'),
        {'schema': 'audit', 'comment': 'Prediction change log'}
    )
    
    prediction_id = uuid_fk('predictions.predictions.id', nullable=False)
    changed_by = uuid_fk('users.users.id', nullable=False)
    
    # Change Info
    change_type = Column(String(50), nullable=False, comment="created, updated, approved, published")
    change_description = Column(Text)
    
    # Changes
    field_changed = Column(String(100))
    old_value = Column(JSONB)
    new_value = Column(JSONB)
    
    # Probabilities (if changed)
    old_probabilities = Column(JSONB)
    new_probabilities = Column(JSONB)
    probability_delta = Column(JSONB, comment="Change in probabilities")
    
    # Confidence (if changed)
    old_confidence = Column(DECIMAL(5, 4))
    new_confidence = Column(DECIMAL(5, 4))
    confidence_delta = Column(DECIMAL(6, 4))
    
    # Reason
    change_reason = Column(Text)
    
    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    
    # Retention
    retention_until = Column(DateTime)


class UserActionLog(Base, UUIDMixin, TimestampMixin):
    """
    User action audit log
    Track user actions for security and compliance
    """
    __tablename__ = "user_action_log"
    __table_args__ = (
        Index('idx_user_action_log_user_id', 'user_id'),
        Index('idx_user_action_log_action_type', 'action_type'),
        Index('idx_user_action_log_created_at', 'created_at'),
        Index('idx_user_action_log_is_suspicious', 'is_suspicious'),
        {'schema': 'audit', 'comment': 'User action log'}
    )
    
    user_id = uuid_fk('users.users.id', nullable=False)
    
    # Action Info
    action_type = Column(String(100), nullable=False)
    action_category = Column(String(50), comment="authentication, profile, prediction, etc.")
    action_description = Column(Text)
    
    # Result
    action_result = Column(String(50), comment="success, failure, blocked")
    error_message = Column(Text)
    
    # Security
    is_suspicious = Column(Boolean, nullable=False, default=False)
    risk_score = Column(Integer, comment="0-100 risk score")
    
    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    session_id = Column(String(255))
    
    # Location
    country = Column(String(100))
    city = Column(String(100))
    
    # Metadata
    action_metadata = Column(JSONB)
    
    # Retention
    retention_until = Column(DateTime)


class AdminActionLog(Base, UUIDMixin, TimestampMixin):
    """
    Admin action audit log
    Track all admin actions for accountability
    """
    __tablename__ = "admin_action_log"
    __table_args__ = (
        Index('idx_admin_action_log_admin_user_id', 'admin_user_id'),
        Index('idx_admin_action_log_action_type', 'action_type'),
        Index('idx_admin_action_log_target_user_id', 'target_user_id'),
        Index('idx_admin_action_log_created_at', 'created_at'),
        {'schema': 'audit', 'comment': 'Admin action log'}
    )
    
    admin_user_id = uuid_fk('users.users.id', nullable=False)
    admin_profile_id = uuid_fk('users.admin_profiles.id', nullable=True)
    
    # Action Info
    action_type = Column(String(100), nullable=False)
    action_category = Column(String(50), comment="user_management, prediction_approval, etc.")
    action_description = Column(Text, nullable=False)
    
    # Target
    target_resource_type = Column(String(100), comment="user, prediction, expert, etc.")
    target_resource_id = Column(UUID)
    target_user_id = uuid_fk('users.users.id', nullable=True, comment="If action targets a user")
    
    # Changes
    changes_made = Column(JSONB, nullable=False, comment="Detailed changes")
    justification = Column(Text, comment="Reason for action")
    
    # Approval (for sensitive actions)
    requires_approval = Column(Boolean, nullable=False, default=False)
    approved_by_admin_id = uuid_fk('users.users.id', nullable=True)
    approved_at = Column(DateTime)
    
    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    
    # Retention
    retention_until = Column(DateTime)


class SystemEventLog(Base, UUIDMixin, TimestampMixin):
    """
    System event audit log
    Track system-level events and errors
    """
    __tablename__ = "system_event_log"
    __table_args__ = (
        Index('idx_system_event_log_event_type', 'event_type'),
        Index('idx_system_event_log_severity', 'severity'),
        Index('idx_system_event_log_created_at', 'created_at'),
        Index('idx_system_event_log_is_resolved', 'is_resolved'),
        {'schema': 'audit', 'comment': 'System event log'}
    )
    
    # Event Info
    event_type = Column(String(100), nullable=False)
    event_category = Column(String(50), comment="deployment, error, performance, security")
    event_description = Column(Text, nullable=False)
    severity = Column(Enum(AuditSeverity), nullable=False)
    
    # Source
    source_component = Column(String(100), comment="api, ml_service, database, etc.")
    source_function = Column(String(255))
    
    # Error Details (if applicable)
    error_message = Column(Text)
    error_traceback = Column(Text)
    error_code = Column(String(50))
    
    # Impact
    affected_users_count = Column(Integer)
    affected_requests_count = Column(Integer)
    
    # Resolution
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_at = Column(DateTime)
    resolved_by_admin_id = uuid_fk('users.users.id', nullable=True)
    resolution_notes = Column(Text)
    
    # Metadata
    event_metadata = Column(JSONB)
    
    # Retention
    retention_until = Column(DateTime)


class GDPRConsentLog(Base, UUIDMixin, TimestampMixin):
    """
    GDPR consent tracking
    Track user consent for data processing
    """
    __tablename__ = "gdpr_consent_log"
    __table_args__ = (
        Index('idx_gdpr_consent_log_user_id', 'user_id'),
        Index('idx_gdpr_consent_log_consent_type', 'consent_type'),
        Index('idx_gdpr_consent_log_is_active', 'is_active'),
        Index('idx_gdpr_consent_log_created_at', 'created_at'),
        {'schema': 'audit', 'comment': 'GDPR consent log'}
    )

    user_id = uuid_fk('users.users.id', nullable=False)

    # Consent Info
    consent_type = Column(Enum(GDPRConsentType), nullable=False)
    consent_version = Column(String(50), nullable=False, comment="Version of consent text")

    # Status
    is_granted = Column(Boolean, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Timing
    granted_at = Column(DateTime)
    revoked_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Consent Text
    consent_text = Column(Text, nullable=False, comment="Exact consent text shown")
    consent_language = Column(String(10), default="en")

    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)

    # Method
    consent_method = Column(String(50), comment="web_form, api, email, etc.")

    # Metadata
    consent_metadata = Column(JSONB)

    # Retention (7 years for legal compliance)
    retention_until = Column(DateTime, nullable=False)


class DataExportLog(Base, UUIDMixin, TimestampMixin):
    """
    GDPR data export requests
    Track user data export requests (Right to Data Portability)
    """
    __tablename__ = "data_export_log"
    __table_args__ = (
        Index('idx_data_export_log_user_id', 'user_id'),
        Index('idx_data_export_log_status', 'status'),
        Index('idx_data_export_log_created_at', 'created_at'),
        Index('idx_data_export_log_expires_at', 'expires_at'),
        {'schema': 'audit', 'comment': 'GDPR data export log'}
    )

    user_id = uuid_fk('users.users.id', nullable=False)

    # Request Info
    request_type = Column(String(50), nullable=False, comment="full_export, specific_data")
    requested_data_types = Column(JSONB, comment="Types of data requested")

    # Status
    status = Column(Enum(DataExportStatus), nullable=False, default=DataExportStatus.REQUESTED)

    # Timing
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    processing_started_at = Column(DateTime)
    completed_at = Column(DateTime)
    expires_at = Column(DateTime, comment="Export file expiration")

    # Export File
    export_file_path = Column(String(500), comment="S3 path to export file")
    export_file_size_bytes = Column(BigInteger)
    export_format = Column(String(20), default="json", comment="json, csv, xml")

    # Download
    download_count = Column(Integer, nullable=False, default=0)
    last_downloaded_at = Column(DateTime)

    # Error Handling
    error_message = Column(Text)

    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)

    # Metadata
    export_metadata = Column(JSONB)

    # Retention
    retention_until = Column(DateTime, nullable=False)
