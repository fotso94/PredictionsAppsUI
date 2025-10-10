"""
Authentication Endpoints
Login, logout, token refresh, and user registration
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
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
    UserInfo,
)


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
    db: Session = Depends(get_db)
):
    """
    User registration endpoint
    
    Creates new user account
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

    new_user = User(
        email=register_data.email,
        username=register_data.email.split('@')[0],  # Generate username from email
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

    return RegisterResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=user_info,
        message="Registration successful! You are now logged in."
    )


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

