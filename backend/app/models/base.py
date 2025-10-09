"""
Base Model Classes and Mixins
Common functionality for all database models
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all models"""
    pass


class UUIDMixin:
    """Mixin for UUID primary key"""
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Primary key (UUID)"
    )


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps"""
    
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="Record creation timestamp"
    )
    
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Record last update timestamp"
    )


class SoftDeleteMixin:
    """Mixin for soft delete functionality"""
    
    deleted_at = Column(
        DateTime,
        nullable=True,
        comment="Soft delete timestamp"
    )
    
    @property
    def is_deleted(self) -> bool:
        """Check if record is soft deleted"""
        return self.deleted_at is not None
    
    def soft_delete(self) -> None:
        """Soft delete the record"""
        self.deleted_at = datetime.utcnow()
    
    def restore(self) -> None:
        """Restore a soft deleted record"""
        self.deleted_at = None


class ActiveMixin:
    """Mixin for is_active flag"""
    
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Active status flag"
    )


def create_table_args(schema: str, **kwargs: Any) -> dict:
    """
    Create __table_args__ for a model with schema and additional options
    
    Args:
        schema: Schema name (users, predictions, ml_models, analytics, audit)
        **kwargs: Additional table arguments (indexes, constraints, etc.)
    
    Returns:
        Dictionary with schema and other table arguments
    
    Example:
        __table_args__ = create_table_args(
            'users',
            comment='User accounts table',
            indexes=[Index('idx_email', 'email')]
        )
    """
    table_args = {'schema': schema}
    table_args.update(kwargs)
    return table_args


# Common column types for reuse
def uuid_fk(foreign_key: str, **kwargs: Any) -> Column:
    """
    Create a UUID foreign key column
    
    Args:
        foreign_key: Foreign key reference (e.g., 'users.users.id')
        **kwargs: Additional column arguments
    
    Returns:
        Column with UUID type and foreign key
    """
    from sqlalchemy import ForeignKey
    
    return Column(
        UUID(as_uuid=True),
        ForeignKey(foreign_key, **kwargs.pop('fk_kwargs', {})),
        **kwargs
    )


def email_column(**kwargs: Any) -> Column:
    """Create an email column with standard configuration"""
    return Column(
        String(255),
        nullable=False,
        unique=True,
        **kwargs
    )


def username_column(**kwargs: Any) -> Column:
    """Create a username column with standard configuration"""
    return Column(
        String(50),
        nullable=False,
        unique=True,
        **kwargs
    )

