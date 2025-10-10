"""
User Management Endpoints
Demonstrates role-based permission system
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import (
    get_db,
    get_current_user,
    get_current_active_user,
    get_current_admin_user
)
from app.core.permissions import (
    Permission,
    require_permission,
    get_user_permissions,
    check_resource_ownership
)
from app.models.users import User
from app.schemas.users import UserResponse, UserListResponse, UserPermissionsResponse

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user information
    
    **Permission**: Any authenticated user
    
    Returns the authenticated user's profile information.
    """
    return current_user


@router.get("/me/permissions", response_model=UserPermissionsResponse)
async def get_current_user_permissions(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user's permissions
    
    **Permission**: Any authenticated user
    
    Returns a list of all permissions the current user has based on their role.
    """
    permissions = get_user_permissions(current_user)
    return {
        "user_id": str(current_user.id),
        "role": current_user.user_type.value,
        "permissions": [p.value for p in permissions]
    }


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get user by ID
    
    **Permission**: 
    - Users can view their own profile
    - Admins can view any user profile
    
    Returns user information for the specified user ID.
    """
    # Check if user is viewing their own profile or is an admin
    check_resource_ownership(current_user, user_id, allow_admin_override=True)
    
    # Fetch user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


@router.get("/", response_model=UserListResponse)
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    List all users
    
    **Permission**: Admin only
    
    Returns a paginated list of all users in the system.
    Only accessible by administrators.
    """
    # This endpoint uses get_current_admin_user dependency
    # which automatically checks for admin role
    
    users = db.query(User).offset(skip).limit(limit).all()
    total = db.query(User).count()
    
    return {
        "users": users,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.put("/{user_id}/role")
async def update_user_role(
    user_id: str,
    new_role: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Update user role
    
    **Permission**: Admin only (with USER_MANAGE_ROLES permission)
    
    Allows administrators to change a user's role.
    """
    # Additional permission check beyond admin role
    require_permission(current_user, Permission.USER_MANAGE_ROLES)
    
    # Fetch user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Validate new role
    valid_roles = ["regular", "expert", "admin"]
    if new_role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )
    
    # Update user role
    from app.models.users import UserType
    user.user_type = UserType(new_role)
    db.commit()
    db.refresh(user)
    
    return {
        "message": f"User role updated to {new_role}",
        "user_id": str(user.id),
        "new_role": new_role
    }


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Delete user (soft delete)
    
    **Permission**: Admin only (with USER_DELETE permission)
    
    Soft deletes a user account. The user data is retained but marked as deleted.
    """
    # Additional permission check beyond admin role
    require_permission(current_user, Permission.USER_DELETE)
    
    # Prevent self-deletion
    if str(current_user.id) == str(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    # Fetch user from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Soft delete (set deleted_at timestamp)
    from datetime import datetime
    from app.models.users import AccountStatus
    user.deleted_at = datetime.utcnow()
    user.account_status = AccountStatus.DELETED
    db.commit()
    
    return {
        "message": "User deleted successfully",
        "user_id": str(user.id)
    }

