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
from urllib.parse import urlsplit

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.source_identity import source_identity
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
    # What this process loaded, on the record from the first line of its log: the same identity
    # GET /health serves for as long as it runs (app.core.source_identity).
    identity = source_identity()
    dirty = identity["commit_dirty_app_files"]
    logger.info(f"Source identity: commit {identity['commit']} with "
                f"{'an unknown number of' if dirty is None else len(dirty)} uncommitted application file(s); "
                f"app tree sha256 {identity['app_tree_sha256']} over {identity['app_files']} file(s); "
                f"computed {identity['started_at']}")

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


def _database_name() -> str:
    """The configured database's NAME alone. The URL carries the password and never leaves here."""
    return urlsplit(settings.DATABASE_URL or "").path.lstrip("/") or settings.POSTGRES_DB


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint, and this process's own account of what it loaded.

    `source` is the identity app.core.source_identity recorded when the process started: its
    commit, the application files that differed from that commit, and a digest of the application
    tree it loaded. The tools that judge evidence against the running code measure it against the
    checkout (backend/scripts/prove_journey.py, scripts/test_evidence.py) instead of inferring it
    from file timestamps. The database is named, never its URL.
    """
    identity = source_identity()
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": app.version,
        "started_at": identity["started_at"],
        "database": _database_name(),
        "source": identity,
    }


@app.get(f"{settings.API_V1_STR}/health", tags=["Health"])
async def api_health_check():
    """API v1 health check endpoint"""
    return {
        "status": "healthy",
        "api_version": "v1",
        "environment": settings.ENVIRONMENT
    }

