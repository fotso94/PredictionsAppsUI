"""
Authentication Schemas
Pydantic models for authentication requests and responses
"""

from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class Token(BaseModel):
    """Token response schema"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Token payload schema"""
    sub: str  # User ID
    role: str  # User role
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    type: str  # Token type (access or refresh)
    jti: Optional[str] = None  # JWT ID (for refresh tokens)


class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="User password")


class RegisterRequest(BaseModel):
    """User registration request schema"""
    email: EmailStr = Field(..., description="User email address")
    username: Optional[str] = Field(None, min_length=3, max_length=50, description="Username (auto-generated from email if not provided)")
    password: str = Field(..., min_length=8, description="User password")
    first_name: str = Field(..., min_length=1, max_length=100, description="User first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="User last name")
    role: Optional[str] = Field(default="regular", description="User role (regular, expert, admin)")


class UserInfo(BaseModel):
    """User information schema"""
    user_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """Login response schema"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class RegisterResponse(BaseModel):
    """User registration response schema"""
    access_token: str
    refresh_token: str
    token_type: str
    user: UserInfo
    message: str = "Registration successful"


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema"""
    refresh_token: str = Field(..., description="Valid refresh token")


class RefreshTokenResponse(BaseModel):
    """Refresh token response schema"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Access token expiration in seconds


class LogoutRequest(BaseModel):
    """Logout request schema"""
    refresh_token: str = Field(..., description="Refresh token to invalidate")


class LogoutResponse(BaseModel):
    """Logout response schema"""
    message: str = "Successfully logged out"


class PasswordChangeRequest(BaseModel):
    """Password change request schema"""
    current_password: str = Field(..., min_length=8, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")


class PasswordChangeResponse(BaseModel):
    """Password change response schema"""
    message: str = "Password successfully changed"


class PasswordResetRequest(BaseModel):
    """Password reset request schema"""
    email: EmailStr = Field(..., description="User email address")


class PasswordResetResponse(BaseModel):
    """Password reset response schema"""
    message: str = "Password reset email sent"


class PasswordResetConfirmRequest(BaseModel):
    """Password reset confirmation request schema"""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New password")


class PasswordResetConfirmResponse(BaseModel):
    """Password reset confirmation response schema"""
    message: str = "Password successfully reset"

