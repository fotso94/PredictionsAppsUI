"""
Database Base
SQLAlchemy declarative base - imports from models.base
"""

# Import Base from models.base for backward compatibility
from app.models.base import Base

__all__ = ["Base"]

