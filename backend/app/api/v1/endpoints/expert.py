"""
Expert Endpoints
Demonstrates expert-specific role-based permissions
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
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


@router.post("/predictions/manual")
async def create_manual_prediction(
    match_id: str,
    prediction_data: Dict[str, Any],
    current_user: User = Depends(get_current_verified_expert_user)
):
    """
    Create manual prediction
    
    **Permission**: Verified Expert or Admin (with EXPERT_CREATE_MANUAL permission)
    
    Allows verified experts to create manual predictions from scratch,
    independent of ML baseline predictions.
    """
    # This endpoint uses get_current_verified_expert_user dependency
    # which checks expert verification status
    
    # Additional permission check
    require_permission(current_user, Permission.EXPERT_CREATE_MANUAL)
    
    return {
        "message": "Manual prediction created successfully",
        "match_id": match_id,
        "expert_id": str(current_user.id),
        "prediction_type": "manual",
        "status": "pending_review"
    }


@router.post("/predictions/override")
async def override_ml_prediction(
    match_id: str,
    override_data: Dict[str, Any],
    current_user: User = Depends(get_current_verified_expert_user)
):
    """
    Override ML prediction
    
    **Permission**: Verified Expert or Admin (with EXPERT_OVERRIDE_ML permission)
    
    Allows verified experts to override ML baseline predictions with their
    own analysis. Creates an audit trail of the override.
    """
    # Check specific permission
    require_permission(current_user, Permission.EXPERT_OVERRIDE_ML)
    
    return {
        "message": "ML prediction overridden successfully",
        "match_id": match_id,
        "expert_id": str(current_user.id),
        "prediction_type": "expert_override",
        "original_ml_prediction": {
            "home_win_probability": 0.45  # Placeholder
        },
        "expert_override": override_data,
        "status": "pending_review",
        "audit_trail_created": True
    }


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

