"""
Pydantic Schemas
Request/Response models for API validation
"""

# Import all schemas here
from app.schemas.auth import (
    Token,
    TokenPayload,
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

# Future imports:
# from app.schemas.users import UserCreate, UserUpdate, UserResponse
# from app.schemas.predictions import PredictionCreate, PredictionUpdate, PredictionResponse

