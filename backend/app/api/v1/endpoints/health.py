"""
Health Check Endpoints
System health and status monitoring
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import redis
from typing import Dict, Any

from app.db.session import get_db
from app.core.config import settings
from app.core.redis import get_redis_client

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
async def health_check():
    """
    Basic health check
    Returns API status
    """
    return {
        "status": "healthy",
        "service": "Soccer Predictions Platform API",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT
    }


@router.get("/detailed", response_model=Dict[str, Any])
async def detailed_health_check(db: Session = Depends(get_db)):
    """
    Detailed health check
    Checks database and Redis connections
    """
    health_status = {
        "status": "healthy",
        "service": "Soccer Predictions Platform API",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": {}
    }
    
    # Check database connection
    try:
        result = db.execute(text("SELECT 1"))
        result.scalar()
        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "PostgreSQL connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"PostgreSQL connection failed: {str(e)}"
        }
    
    # Check Redis connection
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "message": "Redis connection successful"
        }
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "message": f"Redis connection failed: {str(e)}"
        }
    
    return health_status


@router.get("/database", response_model=Dict[str, Any])
async def database_health(db: Session = Depends(get_db)):
    """
    Database health check
    Verifies PostgreSQL connection and schemas
    """
    try:
        # Check connection
        result = db.execute(text("SELECT version()"))
        version = result.scalar()
        
        # Check schemas
        result = db.execute(
            text("""
                SELECT schema_name 
                FROM information_schema.schemata 
                WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
                ORDER BY schema_name
            """)
        )
        schemas = [row[0] for row in result]
        
        return {
            "status": "healthy",
            "database": "PostgreSQL",
            "version": version,
            "schemas": schemas,
            "schemas_count": len(schemas),
            "expected_schemas": 5
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/redis", response_model=Dict[str, Any])
async def redis_health():
    """
    Redis health check
    Verifies Redis connection and database allocation
    """
    try:
        redis_client = get_redis_client()
        info = redis_client.info()
        
        return {
            "status": "healthy",
            "redis_version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "database_allocation": {
                "sessions": settings.REDIS_DB_SESSIONS,
                "predictions": settings.REDIS_DB_PREDICTIONS,
                "expert_tools": settings.REDIS_DB_EXPERT_TOOLS,
                "ml_models": settings.REDIS_DB_ML_MODELS,
                "match_data": settings.REDIS_DB_MATCH_DATA,
                "rate_limit": settings.REDIS_DB_RATE_LIMIT,
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }

