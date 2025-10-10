"""
Dependencies
FastAPI dependencies for authentication and authorization
"""

from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_access_token
from app.core.redis import get_sessions_redis
from app.db.session import SessionLocal
from app.models.users import User
from app.schemas.auth import TokenPayload


# HTTP Bearer token security scheme
security = HTTPBearer()


def get_db() -> Generator:
    """
    Database session dependency
    
    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenPayload:
    """
    Get current user from access token
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        Token payload
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    
    # Verify and decode token
    payload = verify_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create TokenPayload from dict
    try:
        token_data = TokenPayload(**payload)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data


async def get_current_user(
    db: Session = Depends(get_db),
    token_data: TokenPayload = Depends(get_current_user_token)
) -> User:
    """
    Get current user from database

    Args:
        db: Database session
        token_data: Token payload

    Returns:
        User object

    Raises:
        HTTPException: If user not found or inactive
    """
    user = db.query(User).filter(User.id == token_data.sub).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.account_status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user

    Args:
        current_user: Current user from token

    Returns:
        User object

    Raises:
        HTTPException: If user is inactive
    """
    if current_user.account_status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_current_expert_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get current expert user

    Requires user to be either Expert or Admin role.
    Admins have all expert permissions.

    Args:
        current_user: Current active user

    Returns:
        User object

    Raises:
        HTTPException: If user is not an expert or admin
    """
    if current_user.user_type.value not in ["expert", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert or Admin access required"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get current admin user

    Requires user to be Admin role only.

    Args:
        current_user: Current active user

    Returns:
        User object

    Raises:
        HTTPException: If user is not an admin
    """
    if current_user.user_type.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_verified_expert_user(
    current_user: User = Depends(get_current_expert_user)
) -> User:
    """
    Get current verified expert user

    Requires user to be a verified expert or admin.
    Checks that expert profile exists and is verified.

    Args:
        current_user: Current expert or admin user

    Returns:
        User object

    Raises:
        HTTPException: If expert is not verified
    """
    # Admins are always considered verified
    if current_user.user_type.value == "admin":
        return current_user

    # Check if expert profile exists and is verified
    if not hasattr(current_user, 'expert_profile') or current_user.expert_profile is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert profile not found"
        )

    if not current_user.expert_profile.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Expert verification required. Your application is pending approval."
        )

    return current_user


def verify_refresh_token_not_blacklisted(
    refresh_token: str,
    jti: str
) -> bool:
    """
    Verify refresh token is not blacklisted in Redis

    Args:
        refresh_token: Refresh token string
        jti: JWT ID from token payload

    Returns:
        True if token is valid, False if blacklisted
    """
    redis_client = get_sessions_redis()

    # Check if token is blacklisted
    blacklist_key = f"blacklist:refresh:{jti}"
    is_blacklisted = redis_client.exists(blacklist_key)

    return not is_blacklisted


def blacklist_refresh_token(
    jti: str,
    expires_in: int
) -> None:
    """
    Blacklist refresh token in Redis

    Args:
        jti: JWT ID from token payload
        expires_in: Token expiration time in seconds
    """
    redis_client = get_sessions_redis()

    # Add token to blacklist with expiration
    blacklist_key = f"blacklist:refresh:{jti}"
    redis_client.setex(blacklist_key, expires_in, "1")


def store_refresh_token(
    user_id: str,
    jti: str,
    expires_in: int
) -> None:
    """
    Store refresh token in Redis

    Args:
        user_id: User ID
        jti: JWT ID from token payload
        expires_in: Token expiration time in seconds
    """
    redis_client = get_sessions_redis()

    # Store token with user association
    token_key = f"refresh_token:{user_id}:{jti}"
    redis_client.setex(token_key, expires_in, "1")


def revoke_user_refresh_tokens(user_id: str) -> None:
    """
    Revoke all refresh tokens for a user

    Args:
        user_id: User ID
    """
    redis_client = get_sessions_redis()

    # Find all refresh tokens for user
    pattern = f"refresh_token:{user_id}:*"
    keys = redis_client.keys(pattern)

    # Delete all tokens
    if keys:
        redis_client.delete(*keys)

