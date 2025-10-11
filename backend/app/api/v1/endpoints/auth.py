"""
Authentication Endpoints
Login, logout, token refresh, and user registration
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
import logging

from app.core.config import settings
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    generate_reset_token,
    hash_reset_token,
    verify_reset_token as verify_reset_token_hash,
)
from app.core.deps import (
    get_db,
    get_current_user,
    get_current_active_user,
    verify_refresh_token_not_blacklisted,
    blacklist_refresh_token,
    store_refresh_token,
    revoke_user_refresh_tokens,
)
from app.models.users import User, UserType, AccountStatus
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    LogoutRequest,
    LogoutResponse,
    RegisterRequest,
    RegisterResponse,
    PasswordChangeRequest,
    PasswordChangeResponse,
    PasswordResetRequest,
    PasswordResetResponse,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    UserInfo,
)
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """
    User login endpoint
    
    Authenticates user and returns access and refresh tokens
    """
    # Find user by email
    user = db.query(User).filter(User.email == login_data.email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Verify password
    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    # Check if user is active
    if user.account_status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    # Create access token
    access_token = create_access_token(
        subject=str(user.id),
        role=user.user_type.value
    )

    # Create refresh token
    refresh_token, jti = create_refresh_token(
        subject=str(user.id),
        role=user.user_type.value
    )
    
    # Store refresh token in Redis
    expires_in = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
    store_refresh_token(
        user_id=str(user.id),
        jti=jti,
        expires_in=expires_in
    )
    
    # Update last login timestamp
    user.last_login_at = datetime.utcnow()
    db.commit()

    # Prepare user info
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    user_info = UserInfo(
        user_id=str(user.id),
        email=user.email,
        full_name=full_name,
        role=user.user_type.value,
        is_active=(user.account_status == AccountStatus.ACTIVE),
        is_verified=user.email_verified,
        created_at=user.created_at,
        updated_at=user.updated_at
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=user_info
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token endpoint
    
    Validates refresh token and returns new access and refresh tokens
    """
    # Verify refresh token
    payload = verify_refresh_token(refresh_data.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    # Extract user ID and JTI
    user_id = payload.get("sub")
    jti = payload.get("jti")
    role = payload.get("role", "regular")
    
    if user_id is None or jti is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Check if token is blacklisted
    is_valid = verify_refresh_token_not_blacklisted(
        refresh_token=refresh_data.refresh_token,
        jti=jti
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked"
        )
    
    # Verify user exists and is active
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or user.account_status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Blacklist old refresh token
    old_expires_in = payload.get("exp") - int(datetime.utcnow().timestamp())
    if old_expires_in > 0:
        blacklist_refresh_token(jti=jti, expires_in=old_expires_in)

    # Create new access token
    new_access_token = create_access_token(
        subject=str(user.id),
        role=user.user_type.value
    )

    # Create new refresh token
    new_refresh_token, new_jti = create_refresh_token(
        subject=str(user.id),
        role=user.user_type.value
    )
    
    # Store new refresh token in Redis
    expires_in = settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
    store_refresh_token(
        user_id=str(user.id),
        jti=new_jti,
        expires_in=expires_in
    )
    
    return RefreshTokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    logout_data: LogoutRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    User logout endpoint
    
    Invalidates refresh token
    """
    # Verify refresh token
    payload = verify_refresh_token(logout_data.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Extract JTI
    jti = payload.get("jti")
    if jti is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Blacklist refresh token
    expires_in = payload.get("exp") - int(datetime.utcnow().timestamp())
    if expires_in > 0:
        blacklist_refresh_token(jti=jti, expires_in=expires_in)
    
    return LogoutResponse(message="Successfully logged out")


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    register_data: RegisterRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    User registration endpoint

    Creates new user account and sends welcome email
    """
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == register_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Validate role
    valid_roles = ["regular", "expert", "admin"]
    if register_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )
    
    # Create new user
    from app.models.users import UserType, AccountStatus

    # Use provided username or generate from email
    username = register_data.username if register_data.username else register_data.email.split('@')[0]

    new_user = User(
        email=register_data.email,
        username=username,
        password_hash=get_password_hash(register_data.password),
        first_name=register_data.first_name,
        last_name=register_data.last_name,
        user_type=UserType(register_data.role),
        account_status=AccountStatus.ACTIVE,
        email_verified=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate tokens for automatic login
    access_token = create_access_token(
        subject=str(new_user.id),
        role=new_user.user_type.value
    )
    refresh_token, jti = create_refresh_token(
        subject=str(new_user.id),
        role=new_user.user_type.value
    )

    # Store refresh token in Redis
    store_refresh_token(
        user_id=str(new_user.id),
        jti=jti,
        expires_in=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60  # Convert minutes to seconds
    )

    # Prepare user info
    full_name = f"{new_user.first_name or ''} {new_user.last_name or ''}".strip()
    user_info = UserInfo(
        user_id=str(new_user.id),
        email=new_user.email,
        full_name=full_name,
        role=new_user.user_type.value,
        is_active=(new_user.account_status == AccountStatus.ACTIVE),
        is_verified=new_user.email_verified,
        created_at=new_user.created_at,
        updated_at=new_user.updated_at
    )

    # Send welcome email asynchronously (non-blocking)
    background_tasks.add_task(
        send_welcome_email_task,
        to_email=new_user.email,
        user_name=full_name,
        user_id=str(new_user.id)
    )

    return RegisterResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=user_info,
        message="Registration successful! You are now logged in."
    )


async def send_welcome_email_task(to_email: str, user_name: str, user_id: str):
    """
    Background task to send welcome email

    This runs asynchronously and doesn't block the registration response
    """
    try:
        success = await email_service.send_welcome_email(
            to_email=to_email,
            user_name=user_name,
            user_id=user_id
        )
        if success:
            logger.info(f"Welcome email sent successfully to {to_email}")
        else:
            logger.warning(f"Failed to send welcome email to {to_email}")
    except Exception as e:
        # Log error but don't fail registration
        logger.error(f"Error sending welcome email to {to_email}: {str(e)}", exc_info=True)


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user information

    Returns authenticated user's profile
    """
    full_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip()

    return UserInfo(
        user_id=str(current_user.id),
        email=current_user.email,
        full_name=full_name,
        role=current_user.user_type.value,
        is_active=(current_user.account_status == "active"),
        is_verified=current_user.email_verified,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at
    )


@router.post("/change-password", response_model=PasswordChangeResponse)
async def change_password(
    password_data: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Change user password

    Requires current password for verification
    """
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

    # Revoke all refresh tokens for security
    revoke_user_refresh_tokens(user_id=str(current_user.id))

    return PasswordChangeResponse(message="Password successfully changed")


@router.post("/forgot-password", response_model=PasswordResetResponse)
async def forgot_password(
    reset_data: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Request password reset

    Sends a password reset email with a secure token to the user's email address.
    For security, always returns success even if email doesn't exist.
    """
    # Find user by email
    user = db.query(User).filter(User.email == reset_data.email).first()

    # For security, always return success message even if user doesn't exist
    # This prevents email enumeration attacks
    if user is None:
        logger.info(f"Password reset requested for non-existent email: {reset_data.email}")
        return PasswordResetResponse(message="If that email address is in our system, we have sent a password reset link to it.")

    # Generate secure reset token
    reset_token = generate_reset_token()

    # Hash token for storage
    token_hash = hash_reset_token(reset_token)

    # Store hashed token and expiration in database
    user.password_reset_token = token_hash
    user.password_reset_expires_at = datetime.utcnow() + timedelta(hours=1)
    user.updated_at = datetime.utcnow()
    db.commit()

    # Get user's full name
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username

    # Send password reset email asynchronously
    background_tasks.add_task(
        email_service.send_password_reset_email,
        to_email=user.email,
        user_name=full_name,
        reset_token=reset_token  # Send plain token in email
    )

    logger.info(f"Password reset requested for user: {user.email}")

    return PasswordResetResponse(message="If that email address is in our system, we have sent a password reset link to it.")


@router.get("/verify-reset-token/{token}")
async def verify_reset_token(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Verify if a password reset token is valid and not expired

    Returns 200 if valid, 400 if invalid/expired
    """
    # Find user with a non-expired reset token
    users = db.query(User).filter(
        User.password_reset_token.isnot(None),
        User.password_reset_expires_at > datetime.utcnow()
    ).all()

    # Check if any user has a matching token
    for user in users:
        if verify_reset_token_hash(token, user.password_reset_token):
            return {"valid": True, "message": "Token is valid"}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token"
    )


@router.post("/reset-password", response_model=PasswordResetConfirmResponse)
async def reset_password(
    reset_data: PasswordResetConfirmRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Reset password using reset token

    Validates the token, updates the password, and revokes all user sessions
    """
    # Find user with a non-expired reset token
    users = db.query(User).filter(
        User.password_reset_token.isnot(None),
        User.password_reset_expires_at > datetime.utcnow()
    ).all()

    # Check if any user has a matching token
    user = None
    for u in users:
        if verify_reset_token_hash(reset_data.token, u.password_reset_token):
            user = u
            break

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Update password
    user.password_hash = get_password_hash(reset_data.new_password)

    # Clear reset token (one-time use)
    user.password_reset_token = None
    user.password_reset_expires_at = None

    user.updated_at = datetime.utcnow()
    db.commit()

    # Revoke all refresh tokens for security (log out all devices)
    revoke_user_refresh_tokens(user_id=str(user.id))

    # Get user's full name
    full_name = f"{user.first_name} {user.last_name}".strip() or user.username

    # Send confirmation email asynchronously
    background_tasks.add_task(
        email_service.send_password_reset_confirmation_email,
        to_email=user.email,
        user_name=full_name
    )

    logger.info(f"Password reset successful for user: {user.email}")

    return PasswordResetConfirmResponse(message="Password successfully reset")

