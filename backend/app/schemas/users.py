"""
User Schemas
Pydantic models for user-related API requests and responses
"""

from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UserResponse(BaseModel):
    """User response schema"""
    id: str
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
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)


class UserRoleUpdateRequest(BaseModel):
    """User role update request schema"""
    role: str = Field(..., description="New user role (regular, expert, admin)")

