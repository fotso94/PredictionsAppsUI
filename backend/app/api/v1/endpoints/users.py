"""
User Management Endpoints
Demonstrates role-based permission system
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import (
    get_db,
    get_current_active_user,
    get_current_admin_user
)
from app.core.permissions import (
    Permission,
    require_permission,
    get_user_permissions,
    check_resource_ownership
)
from app.models.users import User, UserPreference
from app.schemas.users import (
    UserResponse,
    UserListResponse,
    UserPermissionsResponse,
    UserUpdateRequest,
    UserPreferencesUpdateRequest,
    PasswordChangeRequest,
    MessageResponse
)
from app.core.security import verify_password, get_password_hash
from app.core.deps import revoke_user_refresh_tokens
from app.services.cache import cache_service
from datetime import datetime

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


@router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    update_data: UserUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's profile

    **Permission**: Any authenticated user

    Allows users to update their profile information (first_name, last_name, username, avatar_url).

    Only the fields the request names are touched. A named first_name, last_name or avatar_url
    carrying null or a blank string clears it; a username can be changed but never blanked (422)
    and must not belong to anyone else (409). See ``UserUpdateRequest``.
    """
    # The keys the body actually carried. `is not None` cannot be the test: it reads an explicit
    # null - "clear this" - as "not sent", and a name could then never be removed.
    supplied = update_data.model_fields_set
    changed = False

    # The schema has stripped it and refused a blank one, so a named username is a real one here.
    # It is compared with the STORED username stripped too: registration does not strip, so an
    # account can be stored as "name " and the form sends its unchanged username back as "name".
    # That is no change - not a reason to run the duplicate check (which would find another
    # account's "name" and refuse every save with 409) nor to rewrite the stored row.
    if "username" in supplied and update_data.username != (current_user.username or "").strip():
        existing_user = db.query(User).filter(
            User.username == update_data.username,
            User.id != current_user.id
        ).first()

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken"
            )
        current_user.username = update_data.username
        changed = True

    for field in ("first_name", "last_name", "avatar_url"):
        if field in supplied and getattr(update_data, field) != getattr(current_user, field):
            setattr(current_user, field, getattr(update_data, field))
            changed = True

    # A request that changes nothing claims no change: updated_at moves only when a field did.
    if changed:
        current_user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(current_user)

    # Invalidate user cache
    cache_service.delete_user_cache(str(current_user.id))

    return current_user


@router.put("/me/password", response_model=MessageResponse)
async def change_current_user_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Change current user's password

    **Permission**: Any authenticated user

    Requires current password for verification. The caller should sign in again with the new
    password.

    What this does NOT do, so neither this docstring nor the response claims it: sign the user out
    on other devices. Access tokens are stateless and stay valid until they expire, and the refresh
    tokens deleted below are not consulted by /auth/refresh, which checks only its blacklist.
    """
    # Validate passwords match
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match"
        )

    # Verify current password
    if not verify_password(password_data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )

    # Update password
    current_user.password_hash = get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.utcnow()

    db.commit()

    # Deletes the user's stored refresh-token keys. It does not sign anyone out (see the docstring),
    # which is why the message below no longer says it does.
    revoke_user_refresh_tokens(str(current_user.id))

    # TODO: Send confirmation email

    return MessageResponse(message="Password changed successfully. Sign in again with your new password.")


@router.put("/me/preferences", response_model=MessageResponse)
async def update_current_user_preferences(
    preferences_data: UserPreferencesUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Update current user's preferences

    **Permission**: Any authenticated user

    Allows users to update their preferences (theme, notifications, favorite teams/leagues).
    """
    # Get or create user preferences
    preferences = db.query(UserPreference).filter(
        UserPreference.user_id == current_user.id
    ).first()

    if not preferences:
        preferences = UserPreference(
            user_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.add(preferences)

    # Update theme
    if preferences_data.theme is not None:
        if preferences_data.theme not in ["light", "dark", "auto"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid theme. Must be one of: light, dark, auto"
            )
        preferences.theme = preferences_data.theme

    # Update notification preferences
    if preferences_data.email_notifications is not None:
        preferences.email_notifications = preferences_data.email_notifications

    if preferences_data.push_notifications is not None:
        preferences.push_notifications = preferences_data.push_notifications

    # Update favorite teams (max 10)
    if preferences_data.favorite_teams is not None:
        if len(preferences_data.favorite_teams) > 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 10 favorite teams allowed"
            )
        preferences.favorite_teams = preferences_data.favorite_teams

    # Update favorite leagues (max 5)
    if preferences_data.favorite_leagues is not None:
        if len(preferences_data.favorite_leagues) > 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 5 favorite leagues allowed"
            )
        preferences.favorite_leagues = preferences_data.favorite_leagues

    # Update odds format
    if preferences_data.odds_format is not None:
        if preferences_data.odds_format not in ["decimal", "fractional", "american"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid odds format. Must be one of: decimal, fractional, american"
            )
        preferences.odds_format = preferences_data.odds_format

    preferences.updated_at = datetime.utcnow()

    db.commit()

    return MessageResponse(message="Preferences updated successfully")


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

