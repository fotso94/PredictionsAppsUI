"""
Application Configuration
Centralized settings management using Pydantic BaseSettings
"""

from typing import Any, List, Optional, Union
from pydantic import field_validator, ValidationInfo
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
    
    # Email Configuration
    # Email Provider: smtp, sendgrid, ses
    EMAIL_PROVIDER: str = "smtp"
    EMAIL_ENABLED: bool = True

    # SMTP Configuration
    SMTP_TLS: bool = True
    SMTP_PORT: int = 587
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # Email Sender Information
    EMAILS_FROM_EMAIL: Optional[str] = None
    EMAILS_FROM_NAME: str = "Soccer Predictions Platform"

    # SendGrid Configuration (for future use)
    SENDGRID_API_KEY: Optional[str] = None

    # AWS SES Configuration (for future use)
    AWS_SES_REGION: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # Email Templates
    EMAIL_TEMPLATES_DIR: str = "app/templates/emails"

    # Frontend URL (for email links)
    FRONTEND_URL: str = "http://localhost:3000"
    
    # External APIs (retained integrations)
    API_FOOTBALL_KEY: Optional[str] = None
    THESPORTSDB_KEY: Optional[str] = None  # optional; used by the retained TheSportsDB fallback provider

    # ------------------------------------------------------------------
    # Match-data and prediction providers (Phase 1 integrations)
    # ------------------------------------------------------------------
    # Active match-data provider: livescore | api_football | thesportsdb | sample
    DATA_PROVIDER: str = "livescore"
    # Comma-separated providers tried in order when the active one fails (e.g. "api_football,thesportsdb")
    DATA_PROVIDER_FALLBACKS: str = ""
    # Active prediction provider: gameforecast | api_football | none | sample
    PREDICTION_PROVIDER: str = "gameforecast"
    # Canonical competition keys covered by the product (see app/services/providers/competitions.py)
    COVERED_COMPETITIONS: str = "premier_league,la_liga,serie_a,bundesliga,ligue_1,champions_league"

    # Live Score API (https://live-score-api.com) — key + secret from the account profile
    LIVESCORE_API_KEY: Optional[str] = None
    LIVESCORE_API_SECRET: Optional[str] = None
    LIVESCORE_API_BASE_URL: str = "https://livescore-api.com/api-client"
    # Trial allows 1,500 requests/day; keep headroom for retries and manual checks
    LIVESCORE_DAILY_REQUEST_BUDGET: int = 1200
    # Optional override of competition ids, e.g. "premier_league=2,la_liga=3"; otherwise resolved by name
    LIVESCORE_COMPETITION_IDS: Optional[str] = None

    # GameForecastAPI (https://www.gameforecastapi.com, served through RapidAPI)
    GAMEFORECAST_API_KEY: Optional[str] = None
    GAMEFORECAST_API_HOST: str = "game-forecast-api.p.rapidapi.com"
    GAMEFORECAST_API_BASE_URL: str = "https://game-forecast-api.p.rapidapi.com"
    # Free plan allows 10 requests/day (10/hour); Pro 5,000/month. Keep a small margin.
    GAMEFORECAST_DAILY_REQUEST_BUDGET: int = 8
    # Optional override of league ids, e.g. "premier_league=15"; otherwise resolved by name (1 request per league)
    GAMEFORECAST_LEAGUE_IDS: Optional[str] = None
    GAMEFORECAST_SYNC_DAYS_AHEAD: int = 7
    # Minimum hours between two forecast syncs of the same competition
    GAMEFORECAST_SYNC_INTERVAL_HOURS: int = 24

    # Forecasts older than this (since the provider generated them) are reported as stale, never as current
    FORECAST_MAX_AGE_HOURS: int = 72

    # Cache TTLs (seconds) for provider data
    MATCH_CACHE_TTL_FIXTURES: int = 1800
    MATCH_CACHE_TTL_LIVE: int = 60
    MATCH_CACHE_TTL_RESULTS: int = 1800
    MATCH_CACHE_TTL_STANDINGS: int = 3600
    MATCH_CACHE_TTL_COMPETITIONS: int = 86400
    
    # ML/AI Configuration
    ML_MODEL_PATH: str = "/app/ml/models"
    ML_ENABLED: bool = True
    
    # Feature Flags
    EXPERT_TOOLS_ENABLED: bool = True
    # Phase 1 product decision: expert predictions go live immediately (no mandatory admin approval).
    # Set to False to restore the review-queue workflow (predictions created as PENDING).
    EXPERT_DIRECT_PUBLISH: bool = True
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

