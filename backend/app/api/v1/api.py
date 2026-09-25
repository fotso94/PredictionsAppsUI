"""
API v1 Router
Main router that includes all API v1 endpoints
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    health, auth, users, expert, admin, subscriptions, predictions,
    matches, leagues, teams, data_providers, favourites, performance, slips, suggestions,
)

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# Public endpoints (no authentication required)
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])

# Role-based endpoint routers
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(expert.router, prefix="/expert", tags=["expert"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])

# The signed-in user's own favourites and saved matches (stored data only, never a provider call)
api_router.include_router(favourites.router, prefix="/me", tags=["favourites"])
# The signed-in reader's own selection slips (stored forecasts and results only, never a provider call)
api_router.include_router(slips.router, prefix="/me", tags=["slips"])

# Match data (Live Score API primary, retained fallbacks) and provider forecasts (GameForecastAPI)
api_router.include_router(matches.router, prefix="/matches", tags=["matches"])
api_router.include_router(leagues.router, prefix="/leagues", tags=["leagues"])
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])
api_router.include_router(data_providers.router, prefix="/data-providers", tags=["data-providers"])

# Measured performance: figures counted from settled results, never estimated (stored data only)
api_router.include_router(performance.router, prefix="/performance", tags=["performance"])

# Suggested combinations and the market capability matrix (stored forecasts only)
api_router.include_router(suggestions.router, prefix="/suggestions", tags=["suggestions"])

