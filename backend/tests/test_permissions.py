"""
Permission System Tests
Tests for role-based permission system
"""

import pytest
from fastapi import HTTPException

from app.core.permissions import (
    Permission,
    get_user_permissions,
    has_permission,
    has_any_permission,
    has_all_permissions,
    require_permission,
    require_any_permission,
    require_all_permissions,
    check_resource_ownership,
    is_expert_verified,
    require_expert_verification
)
from app.models.users import User, UserType, AccountStatus


class MockUser:
    """Mock user for testing"""
    def __init__(self, user_id: str, user_type: UserType, expert_profile=None):
        self.id = user_id
        self.user_type = user_type
        self.expert_profile = expert_profile


class MockExpertProfile:
    """Mock expert profile for testing"""
    def __init__(self, is_verified: bool = False):
        self.is_verified = is_verified


def test_get_user_permissions_regular():
    """Test getting permissions for regular user"""
    user = MockUser("user1", UserType.REGULAR)
    permissions = get_user_permissions(user)
    
    assert Permission.PREDICTION_READ in permissions
    assert Permission.ANALYTICS_VIEW_BASIC in permissions
    assert Permission.EXPERT_VIEW_ML_BASELINE not in permissions
    assert Permission.ADMIN_MANAGE_USERS not in permissions


def test_get_user_permissions_expert():
    """Test getting permissions for expert user"""
    user = MockUser("user2", UserType.EXPERT)
    permissions = get_user_permissions(user)
    
    # Expert should have regular permissions
    assert Permission.PREDICTION_READ in permissions
    assert Permission.ANALYTICS_VIEW_BASIC in permissions
    
    # Expert should have expert-specific permissions
    assert Permission.EXPERT_VIEW_ML_BASELINE in permissions
    assert Permission.EXPERT_CREATE_MANUAL in permissions
    assert Permission.EXPERT_OVERRIDE_ML in permissions
    assert Permission.ANALYTICS_VIEW_ADVANCED in permissions
    
    # Expert should NOT have admin permissions
    assert Permission.ADMIN_MANAGE_USERS not in permissions


def test_get_user_permissions_admin():
    """Test getting permissions for admin user"""
    user = MockUser("user3", UserType.ADMIN)
    permissions = get_user_permissions(user)
    
    # Admin should have all permissions
    assert Permission.PREDICTION_READ in permissions
    assert Permission.EXPERT_VIEW_ML_BASELINE in permissions
    assert Permission.ADMIN_MANAGE_USERS in permissions
    assert Permission.ADMIN_APPROVE_PREDICTIONS in permissions


def test_has_permission():
    """Test checking if user has specific permission"""
    regular_user = MockUser("user1", UserType.REGULAR)
    expert_user = MockUser("user2", UserType.EXPERT)
    admin_user = MockUser("user3", UserType.ADMIN)
    
    # Regular user
    assert has_permission(regular_user, Permission.PREDICTION_READ) is True
    assert has_permission(regular_user, Permission.EXPERT_VIEW_ML_BASELINE) is False
    
    # Expert user
    assert has_permission(expert_user, Permission.PREDICTION_READ) is True
    assert has_permission(expert_user, Permission.EXPERT_VIEW_ML_BASELINE) is True
    assert has_permission(expert_user, Permission.ADMIN_MANAGE_USERS) is False
    
    # Admin user
    assert has_permission(admin_user, Permission.PREDICTION_READ) is True
    assert has_permission(admin_user, Permission.EXPERT_VIEW_ML_BASELINE) is True
    assert has_permission(admin_user, Permission.ADMIN_MANAGE_USERS) is True


def test_has_any_permission():
    """Test checking if user has any of specified permissions"""
    regular_user = MockUser("user1", UserType.REGULAR)
    
    # Should return True if user has at least one permission
    assert has_any_permission(regular_user, [
        Permission.PREDICTION_READ,
        Permission.ADMIN_MANAGE_USERS
    ]) is True
    
    # Should return False if user has none of the permissions
    assert has_any_permission(regular_user, [
        Permission.EXPERT_VIEW_ML_BASELINE,
        Permission.ADMIN_MANAGE_USERS
    ]) is False


def test_has_all_permissions():
    """Test checking if user has all specified permissions"""
    expert_user = MockUser("user2", UserType.EXPERT)
    
    # Should return True if user has all permissions
    assert has_all_permissions(expert_user, [
        Permission.PREDICTION_READ,
        Permission.EXPERT_VIEW_ML_BASELINE
    ]) is True
    
    # Should return False if user is missing any permission
    assert has_all_permissions(expert_user, [
        Permission.PREDICTION_READ,
        Permission.ADMIN_MANAGE_USERS
    ]) is False


def test_require_permission_success():
    """Test require_permission with valid permission"""
    expert_user = MockUser("user2", UserType.EXPERT)
    
    # Should not raise exception
    require_permission(expert_user, Permission.EXPERT_VIEW_ML_BASELINE)


def test_require_permission_failure():
    """Test require_permission with invalid permission"""
    regular_user = MockUser("user1", UserType.REGULAR)
    
    # Should raise HTTPException
    with pytest.raises(HTTPException) as exc_info:
        require_permission(regular_user, Permission.EXPERT_VIEW_ML_BASELINE)
    
    assert exc_info.value.status_code == 403


def test_require_any_permission_success():
    """Test require_any_permission with valid permissions"""
    regular_user = MockUser("user1", UserType.REGULAR)
    
    # Should not raise exception (user has PREDICTION_READ)
    require_any_permission(regular_user, [
        Permission.PREDICTION_READ,
        Permission.ADMIN_MANAGE_USERS
    ])


def test_require_any_permission_failure():
    """Test require_any_permission with invalid permissions"""
    regular_user = MockUser("user1", UserType.REGULAR)
    
    # Should raise HTTPException
    with pytest.raises(HTTPException) as exc_info:
        require_any_permission(regular_user, [
            Permission.EXPERT_VIEW_ML_BASELINE,
            Permission.ADMIN_MANAGE_USERS
        ])
    
    assert exc_info.value.status_code == 403


def test_require_all_permissions_success():
    """Test require_all_permissions with valid permissions"""
    expert_user = MockUser("user2", UserType.EXPERT)
    
    # Should not raise exception
    require_all_permissions(expert_user, [
        Permission.PREDICTION_READ,
        Permission.EXPERT_VIEW_ML_BASELINE
    ])


def test_require_all_permissions_failure():
    """Test require_all_permissions with invalid permissions"""
    expert_user = MockUser("user2", UserType.EXPERT)
    
    # Should raise HTTPException (missing ADMIN_MANAGE_USERS)
    with pytest.raises(HTTPException) as exc_info:
        require_all_permissions(expert_user, [
            Permission.PREDICTION_READ,
            Permission.ADMIN_MANAGE_USERS
        ])
    
    assert exc_info.value.status_code == 403


def test_check_resource_ownership_owner():
    """Test resource ownership check for owner"""
    user = MockUser("user1", UserType.REGULAR)
    
    # Should not raise exception (user owns resource)
    check_resource_ownership(user, "user1")


def test_check_resource_ownership_admin():
    """Test resource ownership check for admin"""
    admin = MockUser("admin1", UserType.ADMIN)
    
    # Should not raise exception (admin can access any resource)
    check_resource_ownership(admin, "user1", allow_admin_override=True)


def test_check_resource_ownership_failure():
    """Test resource ownership check failure"""
    user = MockUser("user1", UserType.REGULAR)
    
    # Should raise HTTPException (user doesn't own resource)
    with pytest.raises(HTTPException) as exc_info:
        check_resource_ownership(user, "user2")
    
    assert exc_info.value.status_code == 403


def test_is_expert_verified_admin():
    """Test expert verification check for admin"""
    admin = MockUser("admin1", UserType.ADMIN)
    
    # Admins are always considered verified
    assert is_expert_verified(admin) is True


def test_is_expert_verified_verified_expert():
    """Test expert verification check for verified expert"""
    expert_profile = MockExpertProfile(is_verified=True)
    expert = MockUser("expert1", UserType.EXPERT, expert_profile=expert_profile)
    
    assert is_expert_verified(expert) is True


def test_is_expert_verified_unverified_expert():
    """Test expert verification check for unverified expert"""
    expert_profile = MockExpertProfile(is_verified=False)
    expert = MockUser("expert1", UserType.EXPERT, expert_profile=expert_profile)
    
    assert is_expert_verified(expert) is False


def test_is_expert_verified_regular_user():
    """Test expert verification check for regular user"""
    user = MockUser("user1", UserType.REGULAR)
    
    assert is_expert_verified(user) is False


def test_require_expert_verification_success():
    """Test require_expert_verification with verified expert"""
    expert_profile = MockExpertProfile(is_verified=True)
    expert = MockUser("expert1", UserType.EXPERT, expert_profile=expert_profile)
    
    # Should not raise exception
    require_expert_verification(expert)


def test_require_expert_verification_failure():
    """Test require_expert_verification with unverified expert"""
    expert_profile = MockExpertProfile(is_verified=False)
    expert = MockUser("expert1", UserType.EXPERT, expert_profile=expert_profile)
    
    # Should raise HTTPException
    with pytest.raises(HTTPException) as exc_info:
        require_expert_verification(expert)
    
    assert exc_info.value.status_code == 403

