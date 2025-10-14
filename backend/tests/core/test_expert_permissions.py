"""
Unit tests for Expert RBAC permissions

Tests expert authentication and authorization for KAN-147.
"""

import pytest
from unittest.mock import Mock
from fastapi import HTTPException

from app.core.deps import (
    get_current_expert_user,
    get_current_verified_expert_user,
)
from app.core.permissions import (
    Permission,
    ROLE_PERMISSIONS,
    get_user_permissions,
    has_permission,
    require_permission,
)
from app.models.users import User, UserType


@pytest.fixture
def regular_user():
    """Create a regular user"""
    user = Mock(spec=User)
    user.id = "user-123"
    user.user_type = UserType.REGULAR
    user.account_status = "active"
    return user


@pytest.fixture
def expert_user_unverified():
    """Create an unverified expert user"""
    user = Mock(spec=User)
    user.id = "expert-123"
    user.user_type = UserType.EXPERT
    user.account_status = "active"
    
    # Mock expert profile (unverified)
    expert_profile = Mock()
    expert_profile.is_verified = False
    user.expert_profile = expert_profile
    
    return user


@pytest.fixture
def expert_user_verified():
    """Create a verified expert user"""
    user = Mock(spec=User)
    user.id = "expert-456"
    user.user_type = UserType.EXPERT
    user.account_status = "active"
    
    # Mock expert profile (verified)
    expert_profile = Mock()
    expert_profile.is_verified = True
    user.expert_profile = expert_profile
    
    return user


@pytest.fixture
def admin_user():
    """Create an admin user"""
    user = Mock(spec=User)
    user.id = "admin-789"
    user.user_type = UserType.ADMIN
    user.account_status = "active"
    return user


class TestExpertPermissions:
    """Test suite for expert permissions"""
    
    def test_expert_permissions_defined(self):
        """Test that all expert permissions are defined"""
        assert Permission.EXPERT_VIEW_ML_BASELINE == "expert:view_ml_baseline"
        assert Permission.EXPERT_CREATE_MANUAL == "expert:create_manual"
        assert Permission.EXPERT_OVERRIDE_ML == "expert:override_ml"
        assert Permission.EXPERT_ACCESS_ANALYTICS == "expert:access_analytics"
        assert Permission.EXPERT_USE_BACKTESTING == "expert:use_backtesting"
    
    def test_expert_role_has_expert_permissions(self):
        """Test that EXPERT role has all expert permissions"""
        expert_permissions = ROLE_PERMISSIONS[UserType.EXPERT]
        
        assert Permission.EXPERT_VIEW_ML_BASELINE in expert_permissions
        assert Permission.EXPERT_CREATE_MANUAL in expert_permissions
        assert Permission.EXPERT_OVERRIDE_ML in expert_permissions
        assert Permission.EXPERT_ACCESS_ANALYTICS in expert_permissions
        assert Permission.EXPERT_USE_BACKTESTING in expert_permissions
    
    def test_admin_role_has_expert_permissions(self):
        """Test that ADMIN role has all expert permissions"""
        admin_permissions = ROLE_PERMISSIONS[UserType.ADMIN]
        
        assert Permission.EXPERT_VIEW_ML_BASELINE in admin_permissions
        assert Permission.EXPERT_CREATE_MANUAL in admin_permissions
        assert Permission.EXPERT_OVERRIDE_ML in admin_permissions
        assert Permission.EXPERT_ACCESS_ANALYTICS in admin_permissions
        assert Permission.EXPERT_USE_BACKTESTING in admin_permissions
    
    def test_regular_user_no_expert_permissions(self):
        """Test that REGULAR users don't have expert permissions"""
        regular_permissions = ROLE_PERMISSIONS[UserType.REGULAR]
        
        assert Permission.EXPERT_VIEW_ML_BASELINE not in regular_permissions
        assert Permission.EXPERT_CREATE_MANUAL not in regular_permissions
        assert Permission.EXPERT_OVERRIDE_ML not in regular_permissions
        assert Permission.EXPERT_ACCESS_ANALYTICS not in regular_permissions
        assert Permission.EXPERT_USE_BACKTESTING not in regular_permissions
    
    def test_get_user_permissions_expert(self, expert_user_verified):
        """Test getting permissions for expert user"""
        permissions = get_user_permissions(expert_user_verified)
        
        assert Permission.EXPERT_VIEW_ML_BASELINE in permissions
        assert Permission.EXPERT_CREATE_MANUAL in permissions
        assert Permission.EXPERT_OVERRIDE_ML in permissions
    
    def test_get_user_permissions_regular(self, regular_user):
        """Test getting permissions for regular user"""
        permissions = get_user_permissions(regular_user)
        
        assert Permission.EXPERT_VIEW_ML_BASELINE not in permissions
        assert Permission.PREDICTION_READ in permissions
    
    def test_has_permission_expert_user(self, expert_user_verified):
        """Test has_permission for expert user"""
        assert has_permission(expert_user_verified, Permission.EXPERT_VIEW_ML_BASELINE) is True
        assert has_permission(expert_user_verified, Permission.EXPERT_CREATE_MANUAL) is True
        assert has_permission(expert_user_verified, Permission.ADMIN_MANAGE_USERS) is False
    
    def test_has_permission_regular_user(self, regular_user):
        """Test has_permission for regular user"""
        assert has_permission(regular_user, Permission.EXPERT_VIEW_ML_BASELINE) is False
        assert has_permission(regular_user, Permission.PREDICTION_READ) is True
    
    def test_require_permission_success(self, expert_user_verified):
        """Test require_permission succeeds for authorized user"""
        # Should not raise exception
        require_permission(expert_user_verified, Permission.EXPERT_VIEW_ML_BASELINE)
    
    def test_require_permission_failure(self, regular_user):
        """Test require_permission raises exception for unauthorized user"""
        with pytest.raises(HTTPException) as exc_info:
            require_permission(regular_user, Permission.EXPERT_VIEW_ML_BASELINE)
        
        assert exc_info.value.status_code == 403
        assert "Permission denied" in str(exc_info.value.detail)


class TestExpertUserDependencies:
    """Test suite for expert user dependencies"""
    
    @pytest.mark.asyncio
    async def test_get_current_expert_user_with_expert(self, expert_user_verified):
        """Test get_current_expert_user allows expert users"""
        result = await get_current_expert_user(expert_user_verified)
        assert result == expert_user_verified
    
    @pytest.mark.asyncio
    async def test_get_current_expert_user_with_admin(self, admin_user):
        """Test get_current_expert_user allows admin users"""
        result = await get_current_expert_user(admin_user)
        assert result == admin_user
    
    @pytest.mark.asyncio
    async def test_get_current_expert_user_with_regular_user(self, regular_user):
        """Test get_current_expert_user rejects regular users"""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_expert_user(regular_user)
        
        assert exc_info.value.status_code == 403
        assert "Expert or Admin access required" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_current_verified_expert_user_with_verified_expert(self, expert_user_verified):
        """Test get_current_verified_expert_user allows verified experts"""
        result = await get_current_verified_expert_user(expert_user_verified)
        assert result == expert_user_verified
    
    @pytest.mark.asyncio
    async def test_get_current_verified_expert_user_with_unverified_expert(self, expert_user_unverified):
        """Test get_current_verified_expert_user rejects unverified experts"""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_verified_expert_user(expert_user_unverified)
        
        assert exc_info.value.status_code == 403
        assert "Expert verification required" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_get_current_verified_expert_user_with_admin(self, admin_user):
        """Test get_current_verified_expert_user allows admins (always verified)"""
        result = await get_current_verified_expert_user(admin_user)
        assert result == admin_user
    
    @pytest.mark.asyncio
    async def test_get_current_verified_expert_user_no_profile(self):
        """Test get_current_verified_expert_user rejects expert without profile"""
        user = Mock(spec=User)
        user.id = "expert-no-profile"
        user.user_type = UserType.EXPERT
        user.account_status = "active"
        user.expert_profile = None
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_verified_expert_user(user)
        
        assert exc_info.value.status_code == 403
        assert "Expert profile not found" in str(exc_info.value.detail)


class TestPermissionIntegration:
    """Integration tests for permission system"""
    
    def test_expert_can_view_ml_baseline(self, expert_user_verified):
        """Test expert can view ML baseline predictions"""
        assert has_permission(expert_user_verified, Permission.EXPERT_VIEW_ML_BASELINE)
    
    def test_expert_can_create_manual_predictions(self, expert_user_verified):
        """Test expert can create manual predictions"""
        assert has_permission(expert_user_verified, Permission.EXPERT_CREATE_MANUAL)
    
    def test_expert_can_override_ml_predictions(self, expert_user_verified):
        """Test expert can override ML predictions"""
        assert has_permission(expert_user_verified, Permission.EXPERT_OVERRIDE_ML)
    
    def test_expert_can_access_analytics(self, expert_user_verified):
        """Test expert can access advanced analytics"""
        assert has_permission(expert_user_verified, Permission.EXPERT_ACCESS_ANALYTICS)
    
    def test_expert_can_use_backtesting(self, expert_user_verified):
        """Test expert can use backtesting tools"""
        assert has_permission(expert_user_verified, Permission.EXPERT_USE_BACKTESTING)
    
    def test_admin_has_all_expert_permissions(self, admin_user):
        """Test admin has all expert permissions"""
        assert has_permission(admin_user, Permission.EXPERT_VIEW_ML_BASELINE)
        assert has_permission(admin_user, Permission.EXPERT_CREATE_MANUAL)
        assert has_permission(admin_user, Permission.EXPERT_OVERRIDE_ML)
        assert has_permission(admin_user, Permission.EXPERT_ACCESS_ANALYTICS)
        assert has_permission(admin_user, Permission.EXPERT_USE_BACKTESTING)
    
    def test_regular_user_cannot_access_expert_features(self, regular_user):
        """Test regular user cannot access any expert features"""
        assert not has_permission(regular_user, Permission.EXPERT_VIEW_ML_BASELINE)
        assert not has_permission(regular_user, Permission.EXPERT_CREATE_MANUAL)
        assert not has_permission(regular_user, Permission.EXPERT_OVERRIDE_ML)
        assert not has_permission(regular_user, Permission.EXPERT_ACCESS_ANALYTICS)
        assert not has_permission(regular_user, Permission.EXPERT_USE_BACKTESTING)

