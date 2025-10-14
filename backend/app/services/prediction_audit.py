"""
Prediction Audit Service

Handles audit logging for prediction-related actions.
Tracks who created, modified, approved, or published predictions.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
import uuid

from app.models.audit import AuditLog, AuditAction, AuditSeverity
from app.models.users import User
from app.models.predictions import Prediction

logger = logging.getLogger(__name__)


class PredictionAuditService:
    """
    Service for auditing prediction-related actions.
    
    Logs all significant prediction events:
    - Creation (manual, override)
    - Approval/rejection
    - Publication
    - Deletion
    - Supersession
    """
    
    def __init__(self, db: Session):
        """
        Initialize PredictionAuditService
        
        Args:
            db: Database session
        """
        self.db = db
    
    def log_prediction_created(
        self,
        prediction: Prediction,
        user: User,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log prediction creation event.
        
        Args:
            prediction: Created prediction
            user: User who created the prediction
            metadata: Additional metadata
        
        Returns:
            Created audit log entry
        """
        return self._create_audit_log(
            action=AuditAction.CREATE,
            user=user,
            resource_type="prediction",
            resource_id=str(prediction.id),
            severity=AuditSeverity.INFO,
            description=f"Expert {user.id} created {prediction.source.value} prediction for match {prediction.match_id}",
            metadata={
                "match_id": str(prediction.match_id),
                "source": prediction.source.value,
                "priority_level": prediction.priority_level,
                "status": prediction.status.value,
                **(metadata or {})
            }
        )
    
    def log_prediction_override(
        self,
        original_prediction: Prediction,
        override_prediction: Prediction,
        user: User,
        reason: str
    ) -> AuditLog:
        """
        Log prediction override event.
        
        Args:
            original_prediction: Original prediction being overridden
            override_prediction: New override prediction
            user: User who created the override
            reason: Reason for override
        
        Returns:
            Created audit log entry
        """
        return self._create_audit_log(
            action=AuditAction.UPDATE,
            user=user,
            resource_type="prediction",
            resource_id=str(override_prediction.id),
            severity=AuditSeverity.WARNING,
            description=f"Expert {user.id} overrode {original_prediction.source.value} prediction {original_prediction.id}",
            metadata={
                "match_id": str(original_prediction.match_id),
                "original_prediction_id": str(original_prediction.id),
                "original_source": original_prediction.source.value,
                "override_prediction_id": str(override_prediction.id),
                "override_reason": reason,
                "original_probabilities": {
                    "home_win": float(original_prediction.home_win_prob),
                    "draw": float(original_prediction.draw_prob),
                    "away_win": float(original_prediction.away_win_prob),
                },
                "new_probabilities": {
                    "home_win": float(override_prediction.home_win_prob),
                    "draw": float(override_prediction.draw_prob),
                    "away_win": float(override_prediction.away_win_prob),
                },
            }
        )
    
    def log_prediction_approved(
        self,
        prediction: Prediction,
        admin_user: User
    ) -> AuditLog:
        """
        Log prediction approval event.
        
        Args:
            prediction: Approved prediction
            admin_user: Admin who approved the prediction
        
        Returns:
            Created audit log entry
        """
        return self._create_audit_log(
            action=AuditAction.APPROVE,
            user=admin_user,
            resource_type="prediction",
            resource_id=str(prediction.id),
            severity=AuditSeverity.INFO,
            description=f"Admin {admin_user.id} approved prediction {prediction.id}",
            metadata={
                "match_id": str(prediction.match_id),
                "source": prediction.source.value,
                "created_by": str(prediction.created_by),
                "approved_at": datetime.utcnow().isoformat(),
            }
        )
    
    def log_prediction_published(
        self,
        prediction: Prediction,
        user: Optional[User] = None
    ) -> AuditLog:
        """
        Log prediction publication event.
        
        Args:
            prediction: Published prediction
            user: User who published (optional, can be system)
        
        Returns:
            Created audit log entry
        """
        return self._create_audit_log(
            action=AuditAction.PUBLISH,
            user=user,
            resource_type="prediction",
            resource_id=str(prediction.id),
            severity=AuditSeverity.INFO,
            description=f"Prediction {prediction.id} published",
            metadata={
                "match_id": str(prediction.match_id),
                "source": prediction.source.value,
                "created_by": str(prediction.created_by),
                "published_at": datetime.utcnow().isoformat(),
            }
        )
    
    def log_prediction_rejected(
        self,
        prediction: Prediction,
        admin_user: User,
        reason: str
    ) -> AuditLog:
        """
        Log prediction rejection event.
        
        Args:
            prediction: Rejected prediction
            admin_user: Admin who rejected the prediction
            reason: Reason for rejection
        
        Returns:
            Created audit log entry
        """
        return self._create_audit_log(
            action=AuditAction.REJECT,
            user=admin_user,
            resource_type="prediction",
            resource_id=str(prediction.id),
            severity=AuditSeverity.WARNING,
            description=f"Admin {admin_user.id} rejected prediction {prediction.id}",
            metadata={
                "match_id": str(prediction.match_id),
                "source": prediction.source.value,
                "created_by": str(prediction.created_by),
                "rejection_reason": reason,
                "rejected_at": datetime.utcnow().isoformat(),
            }
        )
    
    def log_prediction_deleted(
        self,
        prediction: Prediction,
        user: User,
        reason: Optional[str] = None
    ) -> AuditLog:
        """
        Log prediction deletion event.
        
        Args:
            prediction: Deleted prediction
            user: User who deleted the prediction
            reason: Optional reason for deletion
        
        Returns:
            Created audit log entry
        """
        return self._create_audit_log(
            action=AuditAction.DELETE,
            user=user,
            resource_type="prediction",
            resource_id=str(prediction.id),
            severity=AuditSeverity.WARNING,
            description=f"User {user.id} deleted prediction {prediction.id}",
            metadata={
                "match_id": str(prediction.match_id),
                "source": prediction.source.value,
                "created_by": str(prediction.created_by),
                "deletion_reason": reason,
                "deleted_at": datetime.utcnow().isoformat(),
            }
        )
    
    def get_prediction_audit_trail(
        self,
        prediction_id: str,
        limit: int = 50
    ) -> List[AuditLog]:
        """
        Get audit trail for a specific prediction.
        
        Args:
            prediction_id: Prediction ID
            limit: Maximum number of results
        
        Returns:
            List of audit log entries
        """
        logs = self.db.query(AuditLog).filter(
            and_(
                AuditLog.resource_type == "prediction",
                AuditLog.resource_id == prediction_id
            )
        ).order_by(
            desc(AuditLog.created_at)
        ).limit(limit).all()
        
        return logs
    
    def get_expert_audit_trail(
        self,
        expert_user_id: str,
        limit: int = 100
    ) -> List[AuditLog]:
        """
        Get audit trail for a specific expert's actions.
        
        Args:
            expert_user_id: Expert user ID
            limit: Maximum number of results
        
        Returns:
            List of audit log entries
        """
        logs = self.db.query(AuditLog).filter(
            and_(
                AuditLog.user_id == uuid.UUID(expert_user_id),
                AuditLog.resource_type == "prediction"
            )
        ).order_by(
            desc(AuditLog.created_at)
        ).limit(limit).all()
        
        return logs
    
    def _create_audit_log(
        self,
        action: AuditAction,
        user: Optional[User],
        resource_type: str,
        resource_id: str,
        severity: AuditSeverity,
        description: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Create an audit log entry.
        
        Args:
            action: Audit action
            user: User performing the action (None for system actions)
            resource_type: Type of resource
            resource_id: Resource ID
            severity: Severity level
            description: Human-readable description
            metadata: Additional metadata
        
        Returns:
            Created audit log entry
        """
        audit_log = AuditLog(
            id=uuid.uuid4(),
            user_id=user.id if user else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            severity=severity,
            action_description=description,
            metadata=metadata or {},
            ip_address=None,  # TODO: Get from request context
            user_agent=None,  # TODO: Get from request context
        )
        
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        
        logger.info(f"Created audit log: {action.value} on {resource_type} {resource_id}")
        
        return audit_log

