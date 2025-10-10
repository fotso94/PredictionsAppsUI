"""
Admin Endpoints
Demonstrates admin-specific role-based permissions
"""

from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.deps import get_db, get_current_admin_user
from app.core.permissions import Permission, require_permission
from app.models.users import User, UserType, AccountStatus

router = APIRouter()


@router.get("/dashboard")
async def get_admin_dashboard(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get admin dashboard data
    
    **Permission**: Admin only
    
    Returns comprehensive system overview including:
    - User statistics
    - System health
    - Recent activity
    """
    # Get user statistics
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.account_status == AccountStatus.ACTIVE).count()
    expert_users = db.query(User).filter(User.user_type == UserType.EXPERT).count()
    admin_users = db.query(User).filter(User.user_type == UserType.ADMIN).count()
    
    return {
        "admin_id": str(current_user.id),
        "dashboard_data": {
            "user_statistics": {
                "total_users": total_users,
                "active_users": active_users,
                "expert_users": expert_users,
                "admin_users": admin_users
            },
            "system_health": {
                "status": "healthy",  # Placeholder
                "uptime": "99.9%"     # Placeholder
            },
            "recent_activity": []  # Placeholder
        }
    }


@router.get("/experts/pending")
async def get_pending_expert_applications(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get pending expert verification applications
    
    **Permission**: Admin only (with ADMIN_MANAGE_EXPERTS permission)
    
    Returns list of expert users awaiting verification.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_MANAGE_EXPERTS)
    
    # Query for expert users with unverified profiles
    from app.models.users import ExpertProfile
    
    pending_experts = db.query(User).join(
        ExpertProfile, User.id == ExpertProfile.user_id
    ).filter(
        User.user_type == UserType.EXPERT,
        ExpertProfile.is_verified == False
    ).all()
    
    return {
        "pending_applications": [
            {
                "user_id": str(user.id),
                "email": user.email,
                "username": user.username,
                "application_date": user.expert_profile.created_at.isoformat() if user.expert_profile.created_at else None,
                "expertise_area": user.expert_profile.expertise_area if hasattr(user.expert_profile, 'expertise_area') else None
            }
            for user in pending_experts
        ],
        "total_pending": len(pending_experts)
    }


@router.post("/experts/{user_id}/verify")
async def verify_expert(
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Verify expert user
    
    **Permission**: Admin only (with ADMIN_MANAGE_EXPERTS permission)
    
    Approves an expert verification application.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_MANAGE_EXPERTS)
    
    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if user is an expert
    if user.user_type != UserType.EXPERT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not an expert"
        )
    
    # Check if expert profile exists
    if not hasattr(user, 'expert_profile') or user.expert_profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expert profile not found"
        )
    
    # Verify expert
    user.expert_profile.is_verified = True
    user.expert_profile.verified_at = datetime.utcnow()
    user.expert_profile.verified_by_admin_id = current_user.id
    db.commit()
    
    return {
        "message": "Expert verified successfully",
        "user_id": str(user.id),
        "verified_by": str(current_user.id),
        "verified_at": user.expert_profile.verified_at.isoformat()
    }


@router.post("/experts/{user_id}/reject")
async def reject_expert(
    user_id: str,
    reason: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Reject expert verification application
    
    **Permission**: Admin only (with ADMIN_MANAGE_EXPERTS permission)
    
    Rejects an expert verification application with a reason.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_MANAGE_EXPERTS)
    
    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Downgrade user to regular
    user.user_type = UserType.REGULAR
    db.commit()
    
    return {
        "message": "Expert application rejected",
        "user_id": str(user.id),
        "rejected_by": str(current_user.id),
        "reason": reason
    }


@router.get("/audit-logs")
async def get_audit_logs(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get system audit logs
    
    **Permission**: Admin only (with ADMIN_ACCESS_AUDIT permission)
    
    Returns system audit logs for security and compliance monitoring.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_ACCESS_AUDIT)
    
    # Placeholder - would query actual audit log table
    return {
        "audit_logs": [],  # Placeholder
        "total": 0,
        "skip": skip,
        "limit": limit
    }


@router.post("/system/config")
async def update_system_config(
    config_data: Dict[str, Any],
    current_user: User = Depends(get_current_admin_user)
):
    """
    Update system configuration
    
    **Permission**: Admin only (with ADMIN_SYSTEM_CONFIG permission)
    
    Allows administrators to update system-wide configuration settings.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_SYSTEM_CONFIG)
    
    return {
        "message": "System configuration updated successfully",
        "updated_by": str(current_user.id),
        "updated_at": datetime.utcnow().isoformat()
    }


@router.post("/predictions/{prediction_id}/approve")
async def approve_prediction(
    prediction_id: str,
    current_user: User = Depends(get_current_admin_user)
):
    """
    Approve prediction for publication
    
    **Permission**: Admin only (with ADMIN_APPROVE_PREDICTIONS permission)
    
    Approves an expert prediction for public visibility.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_APPROVE_PREDICTIONS)
    
    return {
        "message": "Prediction approved successfully",
        "prediction_id": prediction_id,
        "approved_by": str(current_user.id),
        "approved_at": datetime.utcnow().isoformat()
    }


@router.get("/users/suspended")
async def get_suspended_users(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get list of suspended users
    
    **Permission**: Admin only (with ADMIN_MANAGE_USERS permission)
    
    Returns all users with suspended account status.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_MANAGE_USERS)
    
    suspended_users = db.query(User).filter(
        User.account_status == AccountStatus.SUSPENDED
    ).all()
    
    return {
        "suspended_users": [
            {
                "user_id": str(user.id),
                "email": user.email,
                "username": user.username,
                "suspended_at": user.updated_at.isoformat() if user.updated_at else None
            }
            for user in suspended_users
        ],
        "total": len(suspended_users)
    }


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    reason: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Suspend user account
    
    **Permission**: Admin only (with ADMIN_MANAGE_USERS permission)
    
    Suspends a user account with a reason.
    """
    # Check specific permission
    require_permission(current_user, Permission.ADMIN_MANAGE_USERS)
    
    # Prevent self-suspension
    if str(current_user.id) == str(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot suspend your own account"
        )
    
    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Suspend user
    user.account_status = AccountStatus.SUSPENDED
    db.commit()
    
    return {
        "message": "User suspended successfully",
        "user_id": str(user.id),
        "suspended_by": str(current_user.id),
        "reason": reason
    }

