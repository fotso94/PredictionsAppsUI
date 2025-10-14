"""
Expert Endpoints
Expert-specific API endpoints for prediction management
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.deps import (
    get_db,
    get_current_expert_user,
    get_current_verified_expert_user,
    get_current_admin_user
)
from app.core.permissions import (
    Permission,
    require_permission,
    require_any_permission,
    is_expert_verified
)
from app.models.users import User
from app.models.predictions import PredictionStatus
from app.schemas.predictions import (
    ExpertPredictionCreate,
    ExpertPredictionOverride,
    ExpertPredictionUpdate,
    ExpertPredictionResponse,
    ReviewQueueItem,
    ExpertPerformanceMetrics,
)
from app.services.expert_prediction import ExpertPredictionService
from app.services.prediction_audit import PredictionAuditService

router = APIRouter()


@router.get("/dashboard")
async def get_expert_dashboard(
    current_user: User = Depends(get_current_expert_user)
):
    """
    Get expert dashboard data
    
    **Permission**: Expert or Admin
    
    Returns dashboard overview for expert users including:
    - Prediction statistics
    - Performance metrics
    - Recent activity
    """
    # This endpoint uses get_current_expert_user dependency
    # which allows both experts and admins
    
    return {
        "user_id": str(current_user.id),
        "role": current_user.user_type.value,
        "is_verified": is_expert_verified(current_user),
        "dashboard_data": {
            "total_predictions": 0,  # Placeholder
            "accuracy_rate": 0.0,    # Placeholder
            "recent_predictions": [] # Placeholder
        }
    }


@router.get("/ml-baseline")
async def get_ml_baseline_predictions(
    match_id: str,
    current_user: User = Depends(get_current_expert_user)
):
    """
    Get ML baseline predictions for a match
    
    **Permission**: Expert or Admin (with EXPERT_VIEW_ML_BASELINE permission)
    
    Returns the ML model's baseline predictions that experts can review
    before creating their own predictions or overrides.
    """
    # Check specific permission
    require_permission(current_user, Permission.EXPERT_VIEW_ML_BASELINE)
    
    return {
        "match_id": match_id,
        "ml_baseline": {
            "home_win_probability": 0.45,  # Placeholder
            "draw_probability": 0.30,       # Placeholder
            "away_win_probability": 0.25,   # Placeholder
            "model_confidence": 0.75,       # Placeholder
            "model_version": "v1.0.0"       # Placeholder
        },
        "expert_can_override": True
    }


@router.post("/predictions/manual", response_model=ExpertPredictionResponse)
async def create_manual_prediction(
    prediction_data: ExpertPredictionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_expert_user)
):
    """
    Create manual expert prediction (KAN-149)

    **Permission**: Verified Expert or Admin (with EXPERT_CREATE_MANUAL permission)

    Allows verified experts to create manual predictions from scratch,
    independent of ML baseline predictions.

    **Request Body**:
    - match_id: Match ID
    - home_win_prob: Home win probability (0-1)
    - draw_prob: Draw probability (0-1)
    - away_win_prob: Away win probability (0-1)
    - confidence_score: Confidence score (0-1, optional)
    - reasoning: Expert reasoning (optional)
    - key_factors: Key factors influencing prediction (optional)

    **Returns**: Created prediction with status PENDING (requires approval)
    """
    # Check permission
    require_permission(current_user, Permission.EXPERT_CREATE_MANUAL)

    # Create prediction
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
        prediction = expert_service.create_manual_prediction(prediction_data, current_user)

        # Log audit trail
        audit_service.log_prediction_created(
            prediction=prediction,
            user=current_user,
            metadata={"endpoint": "create_manual_prediction"}
        )

        return prediction
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create prediction: {str(e)}"
        )


@router.post("/predictions/override", response_model=ExpertPredictionResponse)
async def override_prediction(
    override_data: ExpertPredictionOverride,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_expert_user)
):
    """
    Override existing prediction (KAN-150)

    **Permission**: Verified Expert or Admin (with EXPERT_OVERRIDE_ML permission)

    Allows verified experts to override ML/API-Football/LLM predictions with their
    own analysis. Creates an audit trail of the override.

    **Request Body**:
    - prediction_id: ID of prediction to override
    - home_win_prob: Home win probability (0-1)
    - draw_prob: Draw probability (0-1)
    - away_win_prob: Away win probability (0-1)
    - confidence_score: Confidence score (0-1, optional)
    - reasoning: Reason for override (required, min 10 chars)
    - key_factors: Key factors influencing override (optional)

    **Returns**: New expert override prediction with status PENDING
    """
    # Check permission
    require_permission(current_user, Permission.EXPERT_OVERRIDE_ML)

    # Create override
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
        # Get original prediction for audit logging
        from app.models.predictions import Prediction
        import uuid
        original_prediction = db.query(Prediction).filter(
            Prediction.id == uuid.UUID(override_data.prediction_id)
        ).first()

        if not original_prediction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prediction {override_data.prediction_id} not found"
            )

        # Create override prediction
        override_prediction = expert_service.override_prediction(override_data, current_user)

        # Log audit trail
        audit_service.log_prediction_override(
            original_prediction=original_prediction,
            override_prediction=override_prediction,
            user=current_user,
            reason=override_data.reasoning
        )

        return override_prediction
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create override: {str(e)}"
        )


@router.get("/predictions/review-queue", response_model=List[ExpertPredictionResponse])
async def get_review_queue(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Get predictions pending review/approval (KAN-151)

    **Permission**: Expert or Admin

    Returns list of predictions awaiting approval, ordered by creation date (newest first).
    Includes match details (team names, logos) and user details (username).

    **Query Parameters**:
    - limit: Maximum number of results (1-100, default 50)
    - offset: Offset for pagination (default 0)

    **Returns**: List of pending predictions with match and user details
    """
    expert_service = ExpertPredictionService(db)

    predictions = expert_service.get_review_queue(limit=limit, offset=offset)

    # Enrich predictions with match and user details
    enriched_predictions = [
        expert_service.enrich_prediction_with_details(p) for p in predictions
    ]

    return enriched_predictions


@router.get("/predictions/my-predictions", response_model=List[ExpertPredictionResponse])
async def get_my_predictions(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status (pending, approved, published, rejected)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Get expert's own predictions (KAN-152)

    **Permission**: Expert or Admin

    Returns list of predictions created by the current expert user.
    Includes match details (team names, logos) and user details (username).

    **Query Parameters**:
    - limit: Maximum number of results (1-100, default 50)
    - offset: Offset for pagination (default 0)
    - status: Filter by status (optional)

    **Returns**: List of expert's predictions with match and user details
    """
    expert_service = ExpertPredictionService(db)

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = PredictionStatus[status.upper()]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}. Valid values: pending, approved, published, rejected"
            )

    predictions = expert_service.get_expert_predictions(
        expert_user=current_user,
        limit=limit,
        offset=offset,
        status=status_filter
    )

    # Enrich predictions with match and user details
    enriched_predictions = [
        expert_service.enrich_prediction_with_details(p) for p in predictions
    ]

    return enriched_predictions


@router.post("/predictions/{prediction_id}/approve", response_model=ExpertPredictionResponse)
async def approve_prediction(
    prediction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Approve a prediction

    **Permission**: Expert or Admin

    **TEMPORARY**: Currently allows experts to approve their own predictions.
    This is a temporary workaround until the admin system is fully implemented.

    **TODO**: Once admin system is in place:
    - Restrict this endpoint to admin users only
    - Experts should NOT be able to approve their own predictions
    - Add proper admin approval workflow

    **Returns**: Approved prediction
    """
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
        # TODO: Change this to require admin user once admin system is implemented
        # For now, allow experts to approve their own predictions (temporary)
        prediction = expert_service.approve_prediction(prediction_id, current_user)

        # Log audit trail - both approval and publication
        audit_service.log_prediction_approved(
            prediction=prediction,
            admin_user=current_user
        )
        audit_service.log_prediction_published(
            prediction=prediction,
            user=current_user
        )

        # Enrich with details
        enriched = expert_service.enrich_prediction_with_details(prediction)

        return enriched
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/predictions/{prediction_id}/reject", response_model=ExpertPredictionResponse)
async def reject_prediction(
    prediction_id: str,
    reason: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Reject a prediction

    **Permission**: Expert or Admin

    **TEMPORARY**: Currently allows experts to reject their own predictions.
    This is a temporary workaround until the admin system is fully implemented.

    **TODO**: Once admin system is in place:
    - Restrict this endpoint to admin users only
    - Experts should NOT be able to reject their own predictions

    **Returns**: Rejected prediction
    """
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
        # TODO: Change this to require admin user once admin system is implemented
        prediction = expert_service.reject_prediction(prediction_id, current_user, reason)

        # Log audit trail
        audit_service.log_prediction_rejected(
            prediction=prediction,
            admin_user=current_user,
            reason=reason or "No reason provided"
        )

        # Enrich with details
        enriched = expert_service.enrich_prediction_with_details(prediction)

        return enriched
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/predictions/{prediction_id}", response_model=ExpertPredictionResponse)
async def update_prediction(
    prediction_id: str,
    update_data: ExpertPredictionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Update an existing prediction

    **Permission**: Expert or Admin (can only update own predictions)

    Allows experts to update their own PENDING predictions.
    Once a prediction is APPROVED or PUBLISHED, it cannot be edited.

    **Request Body**:
    - home_win_prob: Home win probability (0-1)
    - draw_prob: Draw probability (0-1)
    - away_win_prob: Away win probability (0-1)
    - confidence_score: Confidence score (0-1, optional)
    - reasoning: Expert reasoning (optional)
    - key_factors: Key factors influencing prediction (optional)

    **Returns**: Updated prediction
    """
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
        prediction = expert_service.update_prediction(prediction_id, update_data, current_user)

        # Log audit trail (using override method for updates)
        # TODO: Add dedicated log_prediction_updated method to audit service
        audit_service.log_prediction_override(
            original_prediction=prediction,
            override_prediction=prediction,
            user=current_user,
            reason="Expert updated their own prediction"
        )

        # Enrich with details
        enriched = expert_service.enrich_prediction_with_details(prediction)

        return enriched
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/predictions/{prediction_id}")
async def delete_prediction(
    prediction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Delete a prediction

    **Permission**: Expert or Admin (can only delete own predictions)

    Allows experts to delete their own PENDING predictions.
    Once a prediction is APPROVED or PUBLISHED, it cannot be deleted.

    **Returns**: Success message
    """
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
        # Get prediction before deletion for audit log
        from app.models.predictions import Prediction
        import uuid as uuid_lib
        prediction = db.query(Prediction).filter(
            Prediction.id == uuid_lib.UUID(prediction_id)
        ).first()

        if not prediction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Prediction {prediction_id} not found"
            )

        # Store prediction data for audit log before deletion
        prediction_data = {
            "id": str(prediction.id),
            "match_id": str(prediction.match_id),
            "source": prediction.source.value if hasattr(prediction.source, 'value') else prediction.source,
            "created_by": str(prediction.created_by),
            "status": prediction.status.value if hasattr(prediction.status, 'value') else prediction.status
        }

        # Delete prediction
        expert_service.delete_prediction(prediction_id, current_user)

        # Log audit trail (using stored data since prediction is now soft-deleted)
        try:
            audit_service.log_prediction_deleted(
                prediction=prediction,
                user=current_user,
                reason="Expert deleted their own prediction"
            )
        except Exception as audit_error:
            # Log the audit error but don't fail the deletion
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log audit trail for prediction deletion: {audit_error}")

        return {
            "message": "Prediction deleted successfully",
            "prediction_id": prediction_id
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/analytics/performance", response_model=ExpertPerformanceMetrics)
async def get_expert_performance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Get expert performance analytics (KAN-153)

    **Permission**: Expert or Admin (with EXPERT_ACCESS_ANALYTICS permission)

    Returns performance metrics for the current expert user including:
    - Total predictions created
    - Published vs pending predictions
    - Accuracy rate (if available)
    - Average confidence score
    - Predictions by league
    - Recent predictions
    - Performance trend over time

    **Returns**: Expert performance metrics
    """
    # Check specific permission
    require_permission(current_user, Permission.EXPERT_ACCESS_ANALYTICS)

    expert_service = ExpertPredictionService(db)

    # Get expert's predictions
    all_predictions = expert_service.get_expert_predictions(
        expert_user=current_user,
        limit=1000,  # Get all for analytics
        offset=0
    )

    # Calculate metrics
    total_predictions = len(all_predictions)
    published_predictions = len([p for p in all_predictions if p.status == PredictionStatus.PUBLISHED])
    pending_predictions = len([p for p in all_predictions if p.status == PredictionStatus.PENDING])

    # Calculate average confidence
    avg_confidence = 0.0
    if all_predictions:
        avg_confidence = sum([float(p.confidence_score) for p in all_predictions]) / len(all_predictions)

    # Group by league (placeholder - would need match data)
    predictions_by_league = {}

    # Get recent predictions and enrich with match details
    recent_predictions_raw = all_predictions[:10]
    recent_predictions = [
        expert_service.enrich_prediction_with_details(p) for p in recent_predictions_raw
    ]

    # Performance trend (placeholder)
    performance_trend = []

    return ExpertPerformanceMetrics(
        expert_id=str(current_user.id),
        expert_name=current_user.username,
        total_predictions=total_predictions,
        published_predictions=published_predictions,
        pending_predictions=pending_predictions,
        accuracy_rate=None,  # TODO: Calculate from match outcomes
        average_confidence=avg_confidence,
        predictions_by_league=predictions_by_league,
        recent_predictions=recent_predictions,
        performance_trend=performance_trend
    )


@router.get("/analytics/advanced")
async def get_advanced_analytics(
    current_user: User = Depends(get_current_expert_user)
):
    """
    Get advanced analytics

    **Permission**: Expert or Admin (with EXPERT_ACCESS_ANALYTICS permission)

    Returns advanced analytics and insights available only to expert users.
    """
    # Check specific permission
    require_permission(current_user, Permission.EXPERT_ACCESS_ANALYTICS)

    return {
        "user_id": str(current_user.id),
        "analytics": {
            "prediction_accuracy_by_league": {},  # Placeholder
            "confidence_calibration": {},         # Placeholder
            "feature_importance": {},             # Placeholder
            "model_performance_trends": []        # Placeholder
        }
    }


@router.post("/backtesting/run")
async def run_backtesting(
    strategy_config: Dict[str, Any],
    current_user: User = Depends(get_current_verified_expert_user)
):
    """
    Run backtesting simulation
    
    **Permission**: Verified Expert or Admin (with EXPERT_USE_BACKTESTING permission)
    
    Allows verified experts to run backtesting simulations on their
    prediction strategies using historical data.
    """
    # Check specific permission
    require_permission(current_user, Permission.EXPERT_USE_BACKTESTING)
    
    return {
        "message": "Backtesting simulation started",
        "expert_id": str(current_user.id),
        "simulation_id": "sim_123456",  # Placeholder
        "status": "running",
        "estimated_completion": "2 minutes"
    }


@router.get("/verification-status")
async def get_verification_status(
    current_user: User = Depends(get_current_expert_user)
):
    """
    Get expert verification status
    
    **Permission**: Expert or Admin
    
    Returns the current verification status of an expert user.
    """
    # Admins are always verified
    if current_user.user_type.value == "admin":
        return {
            "user_id": str(current_user.id),
            "role": "admin",
            "is_verified": True,
            "verification_status": "N/A - Admin users are automatically verified"
        }
    
    # Check expert profile
    if not hasattr(current_user, 'expert_profile') or current_user.expert_profile is None:
        return {
            "user_id": str(current_user.id),
            "role": "expert",
            "is_verified": False,
            "verification_status": "No expert profile found. Please apply for expert status."
        }
    
    expert_profile = current_user.expert_profile
    
    return {
        "user_id": str(current_user.id),
        "role": "expert",
        "is_verified": expert_profile.is_verified,
        "verification_status": "verified" if expert_profile.is_verified else "pending",
        "application_date": expert_profile.created_at.isoformat() if expert_profile.created_at else None,
        "verified_date": expert_profile.verified_at.isoformat() if expert_profile.verified_at else None,
        "verified_by": str(expert_profile.verified_by_admin_id) if expert_profile.verified_by_admin_id else None
    }

