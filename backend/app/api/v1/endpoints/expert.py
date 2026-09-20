"""
Expert Endpoints
Expert-specific API endpoints for prediction management
"""

from types import SimpleNamespace
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.deps import (
    get_db,
    get_current_admin_user,
    get_current_expert_user,
    get_current_verified_expert_user
)
from app.core.permissions import (
    Permission,
    require_permission,
    is_expert_verified
)
from app.models.users import User
from app.models.predictions import PredictionStatus
from app.schemas.predictions import (
    to_utc_iso_z,
    ExpertPredictionCreate,
    ExpertPredictionOverride,
    ExpertPredictionUpdate,
    ExpertPredictionResponse,
    ExpertPerformanceMetrics,
    TestDataClassificationRequest,
)
from app.services.expert_prediction import (
    ClassificationNotAllowed,
    ExpertPredictionService,
    ForeignExpertRecord,
    RecordClosed,
)
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
    except HTTPException:
        # An HTTPException raised inside the block already carries its own status and detail
        # (404, 403, ...). Letting the catch-all below swallow it turns it into a 400 with a
        # meaningless message.
        raise
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

        # Create override prediction. The service refuses an override of another expert's
        # published record, and any override at all once the match has kicked off: after kickoff
        # the original stays scored on what it said beforehand, and a supersession written now
        # would only take it out of view.
        override_prediction = expert_service.override_prediction(override_data, current_user)

        # Log audit trail
        audit_service.log_prediction_override(
            original_prediction=original_prediction,
            override_prediction=override_prediction,
            user=current_user,
            reason=override_data.reasoning
        )

        return override_prediction
    except HTTPException:
        # The 404 raised above for an unknown prediction must reach the client as a 404; the
        # catch-all below would otherwise report it as a 400 with an empty detail.
        raise
    except ForeignExpertRecord as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except RecordClosed as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
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
            # NB: the `status` query parameter shadows fastapi.status inside this function, so the
            # numeric code is used directly here instead of status.HTTP_400_BAD_REQUEST.
            raise HTTPException(
                status_code=400,
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
    current_user: User = Depends(get_current_admin_user)
):
    """
    Approve a prediction.

    **Permission**: Admin only.

    This used to accept any expert, with a TODO saying it should be admin-only "once the admin
    system is in place". It let an expert approve their own prediction, which makes the word
    approval mean nothing. The blocker that TODO named is gone: administrators are granted with
    `backend/scripts/grant_admin.py`, so the restriction it asked for now applies.

    Nothing changes while EXPERT_DIRECT_PUBLISH is on, because predictions are published on
    creation and never sit waiting. It matters when the flag is off, which is precisely when
    somebody is expecting a real review step.

    **Returns**: Approved prediction
    """
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
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
    current_user: User = Depends(get_current_admin_user)
):
    """
    Reject a prediction.

    **Permission**: Admin only, for the same reason as approve above: a review an author can
    perform on their own work is not a review.

    **Returns**: Rejected prediction
    """
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
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

    Allows experts to update their own predictions. Because experts publish directly, PUBLISHED and
    ARCHIVED predictions stay editable as well: an edit keeps the current status and published_at and
    only refreshes updated_at. REJECTED predictions cannot be edited.

    The version an edit replaces is preserved as an append-only revision in
    `predictions.prediction_audit` and is exposed on the match payload, so a correction never makes
    the earlier published view disappear - not even a correction made after kickoff.

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
        prediction, revision = expert_service.update_prediction_with_revision(
            prediction_id, update_data, current_user)

        # The durable record of the edit is `revision`: an append-only row in
        # predictions.prediction_audit holding the full previous version and its timestamps.
        # The operational audit log gets an entry too, and it now carries the values that were
        # actually replaced. It used to be passed the same (already updated) prediction as both the
        # original and the override, so it recorded the new probabilities as the old ones - an audit
        # entry asserting that nothing had changed. `previous` is a read-only view of the preserved
        # values, deliberately not an ORM object: nothing here may be written back to the database.
        old = revision.old_values or {}
        previous = SimpleNamespace(
            id=prediction.id, match_id=prediction.match_id, source=prediction.source,
            home_win_prob=old.get("home_win_prob", prediction.home_win_prob),
            draw_prob=old.get("draw_prob", prediction.draw_prob),
            away_win_prob=old.get("away_win_prob", prediction.away_win_prob),
        )
        audit_service.log_prediction_override(
            original_prediction=previous,
            override_prediction=prediction,
            user=current_user,
            reason=f"Expert edited their own prediction (previous version preserved as revision {revision.id})"
        )

        # Enrich with details
        enriched = expert_service.enrich_prediction_with_details(prediction)

        return enriched
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prediction violates a database constraint (probabilities must be within 0-1 and BTTS yes/no must sum to 1.0)"
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

    Allows experts to delete their own PENDING, REJECTED, PUBLISHED, or ARCHIVED predictions.

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

        # Deletion is a soft delete, so the loaded row stays readable and the audit entry below can
        # use it directly. (A dict was being built here for that purpose and never passed anywhere.)
        expert_service.delete_prediction(prediction_id, current_user)

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


@router.post("/predictions/{prediction_id}/toggle-publish", response_model=ExpertPredictionResponse)
async def toggle_publish_status(
    prediction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Toggle the publication status of a prediction

    **Permission**: Expert or Admin (can only toggle own predictions)

    Toggles between PUBLISHED and ARCHIVED status.
    - If PUBLISHED: Changes to ARCHIVED (unpublishes the prediction)
    - If ARCHIVED: Changes to PUBLISHED (publishes the prediction)

    **Returns**: Updated prediction
    """
    expert_service = ExpertPredictionService(db)
    audit_service = PredictionAuditService(db)

    try:
        # Toggle publish status
        prediction = expert_service.toggle_publish_status(prediction_id, current_user)

        # Log audit trail
        try:
            audit_service.log_prediction_status_toggled(prediction=prediction, user=current_user)
        except Exception as audit_error:
            # Log error but don't fail the request
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log audit trail for prediction status toggle: {audit_error}")

        # Enrich prediction with match and user details
        enriched_prediction = expert_service.enrich_prediction_with_details(prediction)

        return enriched_prediction
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/predictions/{prediction_id}/test-classification",
             response_model=ExpertPredictionResponse)
async def classify_prediction_as_test_data(
    prediction_id: str,
    classification: TestDataClassificationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_expert_user)
):
    """
    Classify one of your own records as test data, or clear that classification

    **Permission**: Expert or Admin, and only on their own predictions

    A record classified as test data is left out of measured performance and out of the
    leaderboard. This is the ONLY supported way to say "this is not a real prediction": the
    exclusion is driven by a stored flag, never by anything written in the reasoning text, which
    an expert controls and could otherwise use to keep a loss off their record.

    **Availability**: refused with 404 unless the installation allows test-data classification
    (`ALLOW_TEST_DATA_CLASSIFICATION`), which is off by default. It is meant for a machine running
    the end-to-end suite, and it must stay off wherever real predictions are published.

    **Returns**: the updated prediction
    """
    expert_service = ExpertPredictionService(db)
    try:
        prediction = expert_service.classify_as_test_data(
            prediction_id, current_user, classification.is_test_data)
        return expert_service.enrich_prediction_with_details(prediction)
    except ClassificationNotAllowed as e:
        # 404, not 403: where this is switched off the capability does not exist at all, and
        # saying so is more truthful than implying the caller could be given permission for it.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


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

    # The average of the convictions that EXIST, and None when none do.
    #
    # A conviction is optional: an expert who publishes probabilities without rating their own
    # certainty has not rated it at zero, and since the column became nullable this line was
    # calling float() on None and returning HTTP 500 for any expert with one such prediction.
    # Averaging over the whole list with the blanks read as zero would be the older, quieter
    # version of the same error: it drags the mean down with a number nobody supplied.
    #
    # No conviction at all gives None rather than 0.0, because "nobody said" and "everybody said
    # zero" are different answers and the response model carries the distinction.
    stated = [float(p.confidence_score) for p in all_predictions if p.confidence_score is not None]
    avg_confidence = (sum(stated) / len(stated)) if stated else None

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
        # UTC ISO-8601 with a trailing Z, like every other timestamp leaving the expert endpoints
        "application_date": to_utc_iso_z(expert_profile.created_at),
        "verified_date": to_utc_iso_z(expert_profile.verified_at),
        "verified_by": str(expert_profile.verified_by_admin_id) if expert_profile.verified_by_admin_id else None
    }

