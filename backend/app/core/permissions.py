"""
Permission System
Role-based permission checking utilities and decorators
"""

from enum import Enum
from typing import List, Optional
from fastapi import HTTPException, status

from app.models.users import User, UserType


class Permission(str, Enum):
    """
    Permission enumeration for fine-grained access control
    """
    # User Management
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    USER_MANAGE_ROLES = "user:manage_roles"
    
    # Prediction Management
    PREDICTION_READ = "prediction:read"
    PREDICTION_CREATE = "prediction:create"
    PREDICTION_UPDATE = "prediction:update"
    PREDICTION_DELETE = "prediction:delete"
    PREDICTION_OVERRIDE = "prediction:override"
    PREDICTION_APPROVE = "prediction:approve"
    
    # Expert Features
    EXPERT_VIEW_ML_BASELINE = "expert:view_ml_baseline"
    EXPERT_CREATE_MANUAL = "expert:create_manual"
    EXPERT_OVERRIDE_ML = "expert:override_ml"
    EXPERT_ACCESS_ANALYTICS = "expert:access_analytics"
    EXPERT_USE_BACKTESTING = "expert:use_backtesting"
    
    # Admin Features
    ADMIN_MANAGE_USERS = "admin:manage_users"
    ADMIN_MANAGE_EXPERTS = "admin:manage_experts"
    ADMIN_APPROVE_PREDICTIONS = "admin:approve_predictions"
    ADMIN_SYSTEM_CONFIG = "admin:system_config"
    ADMIN_ACCESS_AUDIT = "admin:access_audit"
    ADMIN_MANAGE_SUBSCRIPTIONS = "admin:manage_subscriptions"
    
    # Analytics
    ANALYTICS_VIEW_BASIC = "analytics:view_basic"
    ANALYTICS_VIEW_ADVANCED = "analytics:view_advanced"
    ANALYTICS_EXPORT_DATA = "analytics:export_data"


# Role-Permission Mapping
ROLE_PERMISSIONS = {
    UserType.REGULAR: [
        # Basic permissions for regular users
        Permission.PREDICTION_READ,
        Permission.ANALYTICS_VIEW_BASIC,
    ],
    UserType.EXPERT: [
        # All regular permissions
        Permission.PREDICTION_READ,
        Permission.ANALYTICS_VIEW_BASIC,
        # Expert-specific permissions
        Permission.EXPERT_VIEW_ML_BASELINE,
        Permission.EXPERT_CREATE_MANUAL,
        Permission.EXPERT_OVERRIDE_ML,
        Permission.EXPERT_ACCESS_ANALYTICS,
        Permission.EXPERT_USE_BACKTESTING,
        Permission.ANALYTICS_VIEW_ADVANCED,
        Permission.ANALYTICS_EXPORT_DATA,
        Permission.PREDICTION_CREATE,
        Permission.PREDICTION_UPDATE,
    ],
    UserType.ADMIN: [
        # All expert permissions
        Permission.PREDICTION_READ,
        Permission.ANALYTICS_VIEW_BASIC,
        Permission.EXPERT_VIEW_ML_BASELINE,
        Permission.EXPERT_CREATE_MANUAL,
        Permission.EXPERT_OVERRIDE_ML,
        Permission.EXPERT_ACCESS_ANALYTICS,
        Permission.EXPERT_USE_BACKTESTING,
        Permission.ANALYTICS_VIEW_ADVANCED,
        Permission.ANALYTICS_EXPORT_DATA,
        Permission.PREDICTION_CREATE,
        Permission.PREDICTION_UPDATE,
        # Admin-specific permissions
        Permission.USER_READ,
        Permission.USER_CREATE,
        Permission.USER_UPDATE,
        Permission.USER_DELETE,
        Permission.USER_MANAGE_ROLES,
        Permission.PREDICTION_DELETE,
        Permission.PREDICTION_OVERRIDE,
        Permission.PREDICTION_APPROVE,
        Permission.ADMIN_MANAGE_USERS,
        Permission.ADMIN_MANAGE_EXPERTS,
        Permission.ADMIN_APPROVE_PREDICTIONS,
        Permission.ADMIN_SYSTEM_CONFIG,
        Permission.ADMIN_ACCESS_AUDIT,
        Permission.ADMIN_MANAGE_SUBSCRIPTIONS,
    ],
}


def get_user_permissions(user: User) -> List[Permission]:
    """
    Get all permissions for a user based on their role
    
    Args:
        user: User object
        
    Returns:
        List of permissions
    """
    return ROLE_PERMISSIONS.get(user.user_type, [])


def has_permission(user: User, permission: Permission) -> bool:
    """
    Check if user has a specific permission
    
    Args:
        user: User object
        permission: Permission to check
        
    Returns:
        True if user has permission, False otherwise
    """
    user_permissions = get_user_permissions(user)
    return permission in user_permissions


def has_any_permission(user: User, permissions: List[Permission]) -> bool:
    """
    Check if user has any of the specified permissions
    
    Args:
        user: User object
        permissions: List of permissions to check
        
    Returns:
        True if user has at least one permission, False otherwise
    """
    user_permissions = get_user_permissions(user)
    return any(perm in user_permissions for perm in permissions)


def has_all_permissions(user: User, permissions: List[Permission]) -> bool:
    """
    Check if user has all of the specified permissions
    
    Args:
        user: User object
        permissions: List of permissions to check
        
    Returns:
        True if user has all permissions, False otherwise
    """
    user_permissions = get_user_permissions(user)
    return all(perm in user_permissions for perm in permissions)


def require_permission(user: User, permission: Permission) -> None:
    """
    Require user to have a specific permission
    
    Args:
        user: User object
        permission: Required permission
        
    Raises:
        HTTPException: If user doesn't have permission
    """
    if not has_permission(user, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required permission: {permission.value}"
        )


def require_any_permission(user: User, permissions: List[Permission]) -> None:
    """
    Require user to have at least one of the specified permissions
    
    Args:
        user: User object
        permissions: List of required permissions
        
    Raises:
        HTTPException: If user doesn't have any of the permissions
    """
    if not has_any_permission(user, permissions):
        permission_names = [p.value for p in permissions]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required one of: {', '.join(permission_names)}"
        )


def require_all_permissions(user: User, permissions: List[Permission]) -> None:
    """
    Require user to have all of the specified permissions
    
    Args:
        user: User object
        permissions: List of required permissions
        
    Raises:
        HTTPException: If user doesn't have all permissions
    """
    if not has_all_permissions(user, permissions):
        permission_names = [p.value for p in permissions]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required all of: {', '.join(permission_names)}"
        )


def check_resource_ownership(
    user: User,
    resource_user_id: str,
    allow_admin_override: bool = True
) -> None:
    """
    Check if user owns a resource or is an admin
    
    Args:
        user: User object
        resource_user_id: ID of the user who owns the resource
        allow_admin_override: Whether admins can access any resource
        
    Raises:
        HTTPException: If user doesn't own resource and isn't admin
    """
    # Check if user owns the resource
    if str(user.id) == str(resource_user_id):
        return
    
    # Check if admin override is allowed
    if allow_admin_override and user.user_type == UserType.ADMIN:
        return
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to access this resource"
    )


def is_expert_verified(user: User) -> bool:
    """
    Check if user is a verified expert
    
    Args:
        user: User object
        
    Returns:
        True if user is verified expert or admin, False otherwise
    """
    # Admins are always considered verified
    if user.user_type == UserType.ADMIN:
        return True
    
    # Check if user is expert
    if user.user_type != UserType.EXPERT:
        return False
    
    # Check if expert profile exists and is verified
    if not hasattr(user, 'expert_profile') or user.expert_profile is None:
        return False
    
    return user.expert_profile.is_verified


def require_expert_verification(user: User) -> None:
    """
    Require user to be a verified expert
    
    Args:
        user: User object
        
    Raises:
        HTTPException: If user is not a verified expert
    """
    if not is_expert_verified(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert verification required. Your application is pending approval."
        )

