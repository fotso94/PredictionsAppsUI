"""
API v1 Router
Main router that includes all API v1 endpoints
"""

from fastapi import APIRouter

from app.api.v1.endpoints import health, auth, users, expert, admin, predictions, subscriptions

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# Role-based endpoint routers
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(expert.router, prefix="/expert", tags=["expert"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

# Public API routers
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])

# Future routers will be added here:
# api_router.include_router(matches.router, prefix="/matches", tags=["matches"])
# api_router.include_router(leagues.router, prefix="/leagues", tags=["leagues"])
# api_router.include_router(teams.router, prefix="/teams", tags=["teams"])

