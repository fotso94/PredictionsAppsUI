"""
Public Predictions Endpoints
Endpoints for retrieving published predictions (no authentication required)
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
import uuid

from app.db.session import get_db
from app.models.predictions import Prediction, PredictionStatus, Match, Team, League
from app.schemas.predictions import PublicPredictionResponse

router = APIRouter()


@router.get("/published", response_model=List[PublicPredictionResponse])
async def get_published_predictions(
    match_id: Optional[str] = Query(None, description="Match UUID"),
    external_match_id: Optional[str] = Query(None, description="External API match ID (e.g., API-Football fixture ID)"),
    date: Optional[str] = Query(None, description="Match date (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    Get published expert predictions (PUBLIC endpoint - no authentication required)
    
    This endpoint returns published expert predictions that can be displayed on public pages.
    Predictions are filtered by status=PUBLISHED and ordered by priority (highest first).
    
    **Query Parameters**:
    - match_id: Filter by match UUID (optional)
    - external_match_id: Filter by external API match ID like API-Football fixture ID (optional)
    - date: Filter by match date in YYYY-MM-DD format (optional)
    - limit: Maximum number of results (1-500, default 100)
    
    **Returns**: List of published predictions with match details
    
    **Use Cases**:
    - Display expert predictions on home/today/tomorrow pages
    - Show predictions for specific matches
    - Get predictions for a specific date
    
    **Priority System**:
    - Expert Manual predictions have highest priority (100)
    - Expert Override predictions have priority 95
    - Admin Manual predictions have priority 90
    - LLM Generated predictions have priority 70
    - ML Model predictions have priority 50
    - API-Football Baseline predictions have priority 30
    """
    query = db.query(Prediction).filter(
        Prediction.status == PredictionStatus.PUBLISHED,
        Prediction.deleted_at.is_(None)
    )
    
    # Filter by match_id if provided
    if match_id:
        try:
            match_uuid = uuid.UUID(match_id)
            query = query.filter(Prediction.match_id == match_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid match_id format: {match_id}"
            )
    
    # Filter by external_match_id if provided
    if external_match_id:
        # First, find matches with this external_match_id
        matches = db.query(Match).filter(
            Match.external_api_id == external_match_id
        ).all()
        
        if matches:
            match_ids = [m.id for m in matches]
            query = query.filter(Prediction.match_id.in_(match_ids))
        else:
            # No matches found with this external_match_id, return empty list
            return []
    
    # Filter by date if provided
    if date:
        # Find matches on this date
        from datetime import datetime
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            # Get matches on this date (ignoring time)
            matches = db.query(Match).filter(
                db.func.date(Match.match_date) == date_obj.date()
            ).all()
            
            if matches:
                match_ids = [m.id for m in matches]
                query = query.filter(Prediction.match_id.in_(match_ids))
            else:
                # No matches found on this date, return empty list
                return []
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date format: {date}. Use YYYY-MM-DD format."
            )
    
    # Order by priority (highest first), then by published_at (newest first)
    query = query.order_by(
        Prediction.priority_level.desc(),
        Prediction.published_at.desc()
    )
    
    # Limit results
    predictions = query.limit(limit).all()
    
    # Enrich predictions with match details
    enriched_predictions = []
    for prediction in predictions:
        # Get match details
        match = db.query(Match).filter(Match.id == prediction.match_id).first()
        if not match:
            continue
        
        # Get team details
        home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
        away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
        league = db.query(League).filter(League.id == match.league_id).first()
        
        # Build response
        enriched_predictions.append({
            "id": str(prediction.id),
            "match_id": str(prediction.match_id),
            "external_match_id": match.external_api_id,
            "source": prediction.source.value,
            "priority_level": prediction.priority_level,
            "home_win_prob": float(prediction.home_win_prob),
            "draw_prob": float(prediction.draw_prob),
            "away_win_prob": float(prediction.away_win_prob),
            "confidence_score": float(prediction.confidence_score) if prediction.confidence_score else None,
            "reasoning": prediction.reasoning,
            "published_at": prediction.published_at.isoformat() if prediction.published_at else None,
            "match_details": {
                "home_team_name": home_team.name if home_team else "Unknown",
                "away_team_name": away_team.name if away_team else "Unknown",
                "home_team_logo": home_team.logo_url if home_team else None,
                "away_team_logo": away_team.logo_url if away_team else None,
                "league_name": league.display_name if league else None,
                "match_date": match.match_date.isoformat() if match.match_date else None,
            }
        })
    
    return enriched_predictions


@router.get("/published/by-match/{external_match_id}", response_model=Optional[PublicPredictionResponse])
async def get_published_prediction_by_match(
    external_match_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the highest priority published prediction for a specific match (PUBLIC endpoint)
    
    This endpoint returns the single highest priority published prediction for a match,
    identified by its external API match ID (e.g., API-Football fixture ID).
    
    **Path Parameters**:
    - external_match_id: External API match ID (e.g., API-Football fixture ID)
    
    **Returns**: Single highest priority published prediction, or null if none found
    
    **Use Cases**:
    - Get expert prediction for a specific match on public pages
    - Display expert prediction on match detail pages
    - Check if expert prediction exists before showing API-Football prediction
    """
    # Find match with this external_match_id
    match = db.query(Match).filter(
        Match.external_api_id == external_match_id
    ).first()
    
    if not match:
        return None
    
    # Get highest priority published prediction for this match
    prediction = db.query(Prediction).filter(
        Prediction.match_id == match.id,
        Prediction.status == PredictionStatus.PUBLISHED,
        Prediction.deleted_at.is_(None)
    ).order_by(
        Prediction.priority_level.desc(),
        Prediction.published_at.desc()
    ).first()
    
    if not prediction:
        return None
    
    # Get team and league details
    home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
    away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
    league = db.query(League).filter(League.id == match.league_id).first()
    
    # Build response
    return {
        "id": str(prediction.id),
        "match_id": str(prediction.match_id),
        "external_match_id": match.external_api_id,
        "source": prediction.source.value,
        "priority_level": prediction.priority_level,
        "home_win_prob": float(prediction.home_win_prob),
        "draw_prob": float(prediction.draw_prob),
        "away_win_prob": float(prediction.away_win_prob),
        "confidence_score": float(prediction.confidence_score) if prediction.confidence_score else None,
        "reasoning": prediction.reasoning,
        "published_at": prediction.published_at.isoformat() if prediction.published_at else None,
        "match_details": {
            "home_team_name": home_team.name if home_team else "Unknown",
            "away_team_name": away_team.name if away_team else "Unknown",
            "home_team_logo": home_team.logo_url if home_team else None,
            "away_team_logo": away_team.logo_url if away_team else None,
            "league_name": league.display_name if league else None,
            "match_date": match.match_date.isoformat() if match.match_date else None,
        }
    }

