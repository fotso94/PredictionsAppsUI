"""
Application Configuration
Centralized settings management using Pydantic BaseSettings
"""

from typing import Any, List, Optional, Union
from pydantic import AnyHttpUrl, field_validator, ValidationInfo
from pydantic_settings import BaseSettings
import secrets
import json


class Settings(BaseSettings):
    """Application settings"""

    # Project Information
    PROJECT_NAME: str = "Soccer Predictions Platform API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = "development"  # development, staging, production
    DEBUG: bool = True

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days
    ALGORITHM: str = "HS256"

    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",  # React frontend
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            # Try to parse as JSON first
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
            # Otherwise split by comma
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        raise ValueError(f"Invalid CORS origins format: {v}")
    
    # Allowed Hosts (for production)
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    
    # Database - PostgreSQL
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres123"
    POSTGRES_DB: str = "soccer_predictions"
    DATABASE_URL: Optional[str] = None
    
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> str:
        if isinstance(v, str):
            return v
        return (
            f"postgresql://{info.data.get('POSTGRES_USER')}:"
            f"{info.data.get('POSTGRES_PASSWORD')}@"
            f"{info.data.get('POSTGRES_SERVER')}:"
            f"{info.data.get('POSTGRES_PORT')}/"
            f"{info.data.get('POSTGRES_DB')}"
        )
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0  # Default database for sessions
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None
    
    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def assemble_redis_connection(cls, v: Optional[str], info: ValidationInfo) -> str:
        if isinstance(v, str):
            return v
        password = info.data.get('REDIS_PASSWORD')
        if password:
            return (
                f"redis://:{password}@"
                f"{info.data.get('REDIS_HOST')}:"
                f"{info.data.get('REDIS_PORT')}/"
                f"{info.data.get('REDIS_DB')}"
            )
        return (
            f"redis://{info.data.get('REDIS_HOST')}:"
            f"{info.data.get('REDIS_PORT')}/"
            f"{info.data.get('REDIS_DB')}"
        )
    
    # Redis Database Allocation (from KAN-30)
    REDIS_DB_SESSIONS: int = 0  # User sessions and authentication
    REDIS_DB_PREDICTIONS: int = 1  # Prediction caching
    REDIS_DB_EXPERT_TOOLS: int = 2  # Expert tools cache
    REDIS_DB_ML_MODELS: int = 3  # ML model predictions cache
    REDIS_DB_MATCH_DATA: int = 4  # Real-time match data
    REDIS_DB_RATE_LIMIT: int = 5  # API rate limiting
    
    # Email (for future use)
    SMTP_TLS: bool = True
    SMTP_PORT: Optional[int] = None
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: Optional[str] = None
    
    # External APIs
    API_FOOTBALL_KEY: Optional[str] = None
    THESPORTSDB_KEY: Optional[str] = "773015"
    
    # ML/AI Configuration
    ML_MODEL_PATH: str = "/app/ml/models"
    ML_ENABLED: bool = True
    
    # Feature Flags
    EXPERT_TOOLS_ENABLED: bool = True
    ADMIN_FEATURES_ENABLED: bool = True
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    
    # First Superuser (for initialization)
    FIRST_SUPERUSER_EMAIL: str = "admin@soccerpredictions.com"
    FIRST_SUPERUSER_PASSWORD: str = "changeme123"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()

