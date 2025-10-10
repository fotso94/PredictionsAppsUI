"""
User Schemas
Pydantic models for user-related API requests and responses
"""

from pydantic import BaseModel, EmailStr, Field, field_serializer
from typing import List, Optional
from datetime import datetime
from uuid import UUID


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(BaseModel):
    """User response schema"""
    id: UUID  # Changed from str to UUID
    email: str
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    user_type: str
    account_status: str
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    @field_serializer('id')
    def serialize_id(self, value: UUID, _info):
        """Convert UUID to string"""
        return str(value)

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """User list response schema"""
    users: List[UserResponse]
    total: int
    skip: int
    limit: int


class UserPermissionsResponse(BaseModel):
    """User permissions response schema"""
    user_id: str
    role: str
    permissions: List[str]


class UserUpdateRequest(BaseModel):
    """User update request schema"""
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)


class UserRoleUpdateRequest(BaseModel):
    """User role update request schema"""
    role: str = Field(..., description="New user role (regular, expert, admin)")


class PasswordChangeRequest(BaseModel):
    """Password change request schema"""
    current_password: str = Field(..., min_length=8, description="Current password")
    new_password: str = Field(..., min_length=8, description="New password")
    confirm_password: str = Field(..., min_length=8, description="Confirm new password")


class UserPreferencesUpdateRequest(BaseModel):
    """User preferences update request schema"""
    theme: Optional[str] = Field(None, description="UI theme (light, dark, auto)")
    email_notifications: Optional[bool] = Field(None, description="Enable email notifications")
    push_notifications: Optional[bool] = Field(None, description="Enable push notifications")
    favorite_teams: Optional[List[str]] = Field(None, max_items=10, description="Favorite team IDs (max 10)")
    favorite_leagues: Optional[List[str]] = Field(None, max_items=5, description="Favorite league IDs (max 5)")
    odds_format: Optional[str] = Field(None, description="Odds format (decimal, fractional, american)")


class MessageResponse(BaseModel):
    """Generic message response schema"""
    message: str

