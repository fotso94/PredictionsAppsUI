# Role-Based Permission System

## Overview

The Soccer Predictions Platform implements a comprehensive role-based access control (RBAC) system that differentiates between three user types:

- **Regular Users**: Basic access to view predictions and track personal history
- **Expert Users**: Enhanced access to review ML predictions, create overrides, and access analytics
- **Admin Users**: Full system access including user management, prediction approval, and audit trail

## Architecture

### Components

1. **Permission Definitions** (`app/core/permissions.py`)
   - Enumeration of all system permissions
   - Role-to-permission mapping
   - Permission checking utilities

2. **Authentication Dependencies** (`app/core/deps.py`)
   - JWT token validation
   - User authentication
   - Role-based dependencies

3. **API Endpoints**
   - `/api/v1/users/*` - User management (role-based access)
   - `/api/v1/expert/*` - Expert-specific features
   - `/api/v1/admin/*` - Admin-only features

## User Roles

### Regular User (UserType.REGULAR)

**Permissions:**
- `prediction:read` - View predictions
- `analytics:view_basic` - View basic analytics

**Access:**
- View published predictions
- Track personal prediction history
- View basic performance metrics
- Manage own profile

### Expert User (UserType.EXPERT)

**Permissions:** (includes all Regular permissions plus)
- `expert:view_ml_baseline` - View ML model baseline predictions
- `expert:create_manual` - Create manual predictions
- `expert:override_ml` - Override ML predictions
- `expert:access_analytics` - Access advanced analytics
- `expert:use_backtesting` - Run backtesting simulations
- `analytics:view_advanced` - View advanced analytics
- `analytics:export_data` - Export analytics data
- `prediction:create` - Create predictions
- `prediction:update` - Update predictions

**Access:**
- All Regular user features
- View ML baseline predictions before they're published
- Create manual predictions from scratch
- Override ML predictions with expert analysis
- Access advanced analytics and insights
- Run backtesting simulations
- Export analytics data

**Verification Requirement:**
Expert users must be verified by an admin before accessing certain features:
- Creating manual predictions
- Overriding ML predictions
- Running backtesting simulations

### Admin User (UserType.ADMIN)

**Permissions:** (includes all Expert permissions plus)
- `user:read` - Read user information
- `user:create` - Create users
- `user:update` - Update users
- `user:delete` - Delete users
- `user:manage_roles` - Manage user roles
- `prediction:delete` - Delete predictions
- `prediction:override` - Override any prediction
- `prediction:approve` - Approve predictions for publication
- `admin:manage_users` - Manage user accounts
- `admin:manage_experts` - Manage expert verifications
- `admin:approve_predictions` - Approve predictions
- `admin:system_config` - Configure system settings
- `admin:access_audit` - Access audit logs
- `admin:manage_subscriptions` - Manage subscriptions

**Access:**
- All Expert user features (automatically verified)
- Manage user accounts (create, update, delete, suspend)
- Verify expert applications
- Approve predictions for publication
- Access system audit logs
- Configure system settings
- Manage subscriptions

## Implementation Guide

### Using Dependencies in Endpoints

#### Basic Authentication
```python
from app.core.deps import get_current_active_user

@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_active_user)):
    # Any authenticated user can access
    return current_user
```

#### Expert-Only Access
```python
from app.core.deps import get_current_expert_user

@router.get("/expert/dashboard")
async def expert_dashboard(current_user: User = Depends(get_current_expert_user)):
    # Only experts and admins can access
    return {"data": "expert dashboard"}
```

#### Verified Expert Access
```python
from app.core.deps import get_current_verified_expert_user

@router.post("/expert/predictions/manual")
async def create_manual_prediction(
    current_user: User = Depends(get_current_verified_expert_user)
):
    # Only verified experts and admins can access
    return {"message": "Prediction created"}
```

#### Admin-Only Access
```python
from app.core.deps import get_current_admin_user

@router.get("/admin/users")
async def list_users(current_user: User = Depends(get_current_admin_user)):
    # Only admins can access
    return {"users": []}
```

### Using Permission Checks

#### Single Permission Check
```python
from app.core.permissions import Permission, require_permission

@router.post("/admin/config")
async def update_config(current_user: User = Depends(get_current_admin_user)):
    # Check specific permission beyond role
    require_permission(current_user, Permission.ADMIN_SYSTEM_CONFIG)
    return {"message": "Config updated"}
```

#### Multiple Permission Check (Any)
```python
from app.core.permissions import Permission, require_any_permission

@router.get("/analytics")
async def get_analytics(current_user: User = Depends(get_current_active_user)):
    # User needs at least one of these permissions
    require_any_permission(current_user, [
        Permission.ANALYTICS_VIEW_BASIC,
        Permission.ANALYTICS_VIEW_ADVANCED
    ])
    return {"analytics": {}}
```

#### Multiple Permission Check (All)
```python
from app.core.permissions import Permission, require_all_permissions

@router.post("/advanced-operation")
async def advanced_operation(current_user: User = Depends(get_current_admin_user)):
    # User needs all of these permissions
    require_all_permissions(current_user, [
        Permission.ADMIN_MANAGE_USERS,
        Permission.ADMIN_ACCESS_AUDIT
    ])
    return {"message": "Operation completed"}
```

#### Resource Ownership Check
```python
from app.core.permissions import check_resource_ownership

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_active_user)
):
    # User can view their own profile, admins can view any profile
    check_resource_ownership(current_user, user_id, allow_admin_override=True)
    return {"user": {}}
```

## API Endpoint Structure

### Public Endpoints (No Authentication)
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/login` - User login
- `GET /api/v1/health` - Health check

### Authenticated Endpoints (Any Role)
- `GET /api/v1/users/me` - Get current user info
- `GET /api/v1/users/me/permissions` - Get user permissions
- `POST /api/v1/auth/logout` - Logout
- `POST /api/v1/auth/refresh` - Refresh token

### Expert Endpoints (Expert + Admin)
- `GET /api/v1/expert/dashboard` - Expert dashboard
- `GET /api/v1/expert/ml-baseline` - View ML baseline predictions
- `GET /api/v1/expert/analytics/advanced` - Advanced analytics
- `GET /api/v1/expert/verification-status` - Check verification status

### Verified Expert Endpoints (Verified Expert + Admin)
- `POST /api/v1/expert/predictions/manual` - Create manual prediction
- `POST /api/v1/expert/predictions/override` - Override ML prediction
- `POST /api/v1/expert/backtesting/run` - Run backtesting

### Admin Endpoints (Admin Only)
- `GET /api/v1/admin/dashboard` - Admin dashboard
- `GET /api/v1/admin/experts/pending` - Pending expert applications
- `POST /api/v1/admin/experts/{user_id}/verify` - Verify expert
- `POST /api/v1/admin/experts/{user_id}/reject` - Reject expert
- `GET /api/v1/admin/audit-logs` - System audit logs
- `POST /api/v1/admin/system/config` - Update system config
- `POST /api/v1/admin/predictions/{id}/approve` - Approve prediction
- `GET /api/v1/admin/users/suspended` - List suspended users
- `POST /api/v1/admin/users/{user_id}/suspend` - Suspend user
- `GET /api/v1/users/` - List all users
- `PUT /api/v1/users/{user_id}/role` - Update user role
- `DELETE /api/v1/users/{user_id}` - Delete user

## JWT Token Structure

Access tokens include the user's role in the payload:

```json
{
  "sub": "user-uuid",
  "role": "expert",
  "type": "access",
  "exp": 1234567890,
  "iat": 1234567890
}
```

This allows for fast permission checks without database queries.

## Security Considerations

1. **Defense in Depth**: Multiple layers of security
   - JWT token validation
   - Role-based dependencies
   - Fine-grained permission checks
   - Resource ownership validation

2. **Principle of Least Privilege**: Users only get permissions they need
   - Regular users: minimal permissions
   - Experts: prediction-related permissions
   - Admins: full system access

3. **Audit Trail**: All admin actions should be logged
   - User role changes
   - Expert verifications
   - Prediction approvals
   - System configuration changes

4. **Expert Verification**: Two-tier expert system
   - Unverified experts: limited access
   - Verified experts: full expert features
   - Admins: automatically verified

## Testing

Run permission system tests:

```bash
cd backend
pytest tests/test_permissions.py -v
```

## Future Enhancements

1. **Dynamic Permissions**: Database-driven permissions for more flexibility
2. **Permission Groups**: Group permissions for easier management
3. **Temporary Permissions**: Time-limited permission grants
4. **Permission Delegation**: Allow admins to delegate specific permissions
5. **API Rate Limiting**: Different rate limits per role
6. **Feature Flags**: Role-based feature flag access

