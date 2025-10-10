"""
Manual Permission System Test
Quick verification that the permission system works correctly
"""

from app.core.permissions import (
    Permission,
    get_user_permissions,
    has_permission,
    ROLE_PERMISSIONS
)
from app.models.users import UserType


class MockUser:
    """Mock user for testing"""
    def __init__(self, user_id: str, user_type: UserType):
        self.id = user_id
        self.user_type = user_type


def test_permission_system():
    """Test the permission system"""
    print("=" * 60)
    print("PERMISSION SYSTEM TEST")
    print("=" * 60)
    
    # Test Regular User
    print("\n1. Testing Regular User Permissions:")
    print("-" * 60)
    regular_user = MockUser("user1", UserType.REGULAR)
    regular_permissions = get_user_permissions(regular_user)
    print(f"Regular user has {len(regular_permissions)} permissions:")
    for perm in regular_permissions:
        print(f"  ✓ {perm.value}")
    
    # Verify regular user permissions
    assert has_permission(regular_user, Permission.PREDICTION_READ), "Regular user should have PREDICTION_READ"
    assert has_permission(regular_user, Permission.ANALYTICS_VIEW_BASIC), "Regular user should have ANALYTICS_VIEW_BASIC"
    assert not has_permission(regular_user, Permission.EXPERT_VIEW_ML_BASELINE), "Regular user should NOT have EXPERT_VIEW_ML_BASELINE"
    assert not has_permission(regular_user, Permission.ADMIN_MANAGE_USERS), "Regular user should NOT have ADMIN_MANAGE_USERS"
    print("✅ Regular user permissions verified!")
    
    # Test Expert User
    print("\n2. Testing Expert User Permissions:")
    print("-" * 60)
    expert_user = MockUser("user2", UserType.EXPERT)
    expert_permissions = get_user_permissions(expert_user)
    print(f"Expert user has {len(expert_permissions)} permissions:")
    for perm in expert_permissions:
        print(f"  ✓ {perm.value}")
    
    # Verify expert user permissions
    assert has_permission(expert_user, Permission.PREDICTION_READ), "Expert should have PREDICTION_READ"
    assert has_permission(expert_user, Permission.EXPERT_VIEW_ML_BASELINE), "Expert should have EXPERT_VIEW_ML_BASELINE"
    assert has_permission(expert_user, Permission.EXPERT_CREATE_MANUAL), "Expert should have EXPERT_CREATE_MANUAL"
    assert has_permission(expert_user, Permission.EXPERT_OVERRIDE_ML), "Expert should have EXPERT_OVERRIDE_ML"
    assert not has_permission(expert_user, Permission.ADMIN_MANAGE_USERS), "Expert should NOT have ADMIN_MANAGE_USERS"
    print("✅ Expert user permissions verified!")
    
    # Test Admin User
    print("\n3. Testing Admin User Permissions:")
    print("-" * 60)
    admin_user = MockUser("user3", UserType.ADMIN)
    admin_permissions = get_user_permissions(admin_user)
    print(f"Admin user has {len(admin_permissions)} permissions:")
    for perm in admin_permissions:
        print(f"  ✓ {perm.value}")
    
    # Verify admin user permissions
    assert has_permission(admin_user, Permission.PREDICTION_READ), "Admin should have PREDICTION_READ"
    assert has_permission(admin_user, Permission.EXPERT_VIEW_ML_BASELINE), "Admin should have EXPERT_VIEW_ML_BASELINE"
    assert has_permission(admin_user, Permission.ADMIN_MANAGE_USERS), "Admin should have ADMIN_MANAGE_USERS"
    assert has_permission(admin_user, Permission.ADMIN_APPROVE_PREDICTIONS), "Admin should have ADMIN_APPROVE_PREDICTIONS"
    assert has_permission(admin_user, Permission.ADMIN_ACCESS_AUDIT), "Admin should have ADMIN_ACCESS_AUDIT"
    print("✅ Admin user permissions verified!")
    
    # Summary
    print("\n" + "=" * 60)
    print("PERMISSION SYSTEM TEST SUMMARY")
    print("=" * 60)
    print(f"✅ Regular User: {len(regular_permissions)} permissions")
    print(f"✅ Expert User:  {len(expert_permissions)} permissions")
    print(f"✅ Admin User:   {len(admin_permissions)} permissions")
    print("\n✅ ALL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test_permission_system()

