"""
Main FastAPI Application
Entry point for the Soccer Predictions Platform API
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.v1.api import api_router
from app.db.init_db import init_db
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.sync_scheduler import start_background_scheduler, stop_background_scheduler

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start-up and shut-down, including the background data-refresh loop.

    The scheduler is owned here rather than by a scheduling dependency: one asyncio task, started
    after the app is otherwise ready and cancelled before the process goes away. It does not run a
    sync on start (see SYNC_SCHEDULER_STARTUP_DELAY_SECONDS and the persisted per-task due-times),
    so restarting the backend in development costs nothing.
    """
    logger.info(f"Starting {settings.PROJECT_NAME} v{app.version}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    # Initialize database (create schemas if needed)
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    scheduler_task = start_background_scheduler()
    try:
        yield
    finally:
        await stop_background_scheduler(scheduler_task)
        logger.info(f"Shutting down {settings.PROJECT_NAME}")


# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Soccer Predictions Platform - Multi-Profile Prediction System with ML/AI Integration",
    version="0.1.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Page", "X-Per-Page"],
)

# Security Middleware
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )

# GZip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint - API information"""
    return {
        "name": settings.PROJECT_NAME,
        "version": app.version,
        "environment": settings.ENVIRONMENT,
        "docs": f"{settings.API_V1_STR}/docs",
        "status": "operational"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": app.version
    }


@app.get(f"{settings.API_V1_STR}/health", tags=["Health"])
async def api_health_check():
    """API v1 health check endpoint"""
    return {
        "status": "healthy",
        "api_version": "v1",
        "environment": settings.ENVIRONMENT
    }

