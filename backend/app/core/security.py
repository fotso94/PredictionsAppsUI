"""
Security Utilities
Password hashing, JWT token generation, validation, and security headers
"""

from datetime import datetime, timedelta
from typing import Any, Union, Optional, Dict
from jose import jwt, JWTError
from passlib.context import CryptContext
import uuid
import secrets

from app.core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(
    subject: Union[str, Any],
    role: str = "regular",
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token

    Args:
        subject: User ID (subject)
        role: User role (regular, expert, admin)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {
        "exp": expire,
        "iat": datetime.utcnow(),
        "sub": str(subject),
        "role": role,
        "type": "access"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    subject: Union[str, Any],
    role: str = "regular",
    expires_delta: Optional[timedelta] = None
) -> tuple[str, str]:
    """
    Create JWT refresh token with unique JTI

    Args:
        subject: User ID (subject)
        role: User role (regular, expert, admin)
        expires_delta: Optional custom expiration time

    Returns:
        Tuple of (encoded JWT token string, JTI for Redis storage)
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES
        )

    # Generate unique JTI (JWT ID) for token revocation
    jti = str(uuid.uuid4())

    to_encode = {
        "exp": expire,
        "iat": datetime.utcnow(),
        "sub": str(subject),
        "role": role,
        "type": "refresh",
        "jti": jti
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt, jti


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate JWT token

    Args:
        token: JWT token string

    Returns:
        Decoded token payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify access token and return payload

    Args:
        token: JWT access token string

    Returns:
        Token payload if valid, None otherwise
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # Verify token type
    if payload.get("type") != "access":
        return None

    # Verify expiration
    exp = payload.get("exp")
    if exp is None or datetime.fromtimestamp(exp) < datetime.utcnow():
        return None

    return payload


def verify_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify refresh token and return payload

    Args:
        token: JWT refresh token string

    Returns:
        Token payload if valid, None otherwise
    """
    payload = decode_token(token)
    if payload is None:
        return None

    # Verify token type
    if payload.get("type") != "refresh":
        return None

    # Verify expiration
    exp = payload.get("exp")
    if exp is None or datetime.fromtimestamp(exp) < datetime.utcnow():
        return None

    # Verify JTI exists
    if payload.get("jti") is None:
        return None

    return payload


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def generate_reset_token() -> str:
    """
    Generate a cryptographically secure password reset token

    Returns:
        A URL-safe random token string (43 characters)
    """
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    """
    Hash a reset token for secure storage in database

    Args:
        token: Plain reset token

    Returns:
        Hashed token
    """
    return pwd_context.hash(token)


def verify_reset_token(plain_token: str, hashed_token: str) -> bool:
    """
    Verify a reset token against its hash

    Args:
        plain_token: Plain reset token from URL
        hashed_token: Hashed token from database

    Returns:
        True if token matches, False otherwise
    """
    return pwd_context.verify(plain_token, hashed_token)


# Security Headers Middleware Configuration
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # Relaxed CSP for development to allow Swagger UI and ReDoc to work
    # ReDoc requires worker-src and child-src for web workers
    # In production, this should be more restrictive
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://cdn.jsdelivr.net; font-src 'self' data: https://cdn.jsdelivr.net; worker-src 'self' blob:; child-src 'self' blob:",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

