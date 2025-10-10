"""
Prediction Endpoints for Public API
Endpoints for regular users to view predictions
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.core.deps import get_db, get_current_active_user
from app.models.users import User
from app.models.predictions import Prediction
from app.schemas.predictions import FeedbackRequest
from app.services.subscription_tier import subscription_checker

router = APIRouter()


@router.get("/")
async def list_predictions(
    league_id: Optional[str] = Query(None, description="Filter by league ID"),
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
    date_from: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    List predictions with subscription tier-based filtering

    **Permission**: Any authenticated user

    **Subscription Tier Limits:**
    - Free: 3 predictions/day, 7 days history
    - Basic: 10 predictions/day, 30 days history
    - Premium: Unlimited predictions, 90 days history
    - Pro: Unlimited predictions, unlimited history
    """
    # Get user's subscription tier
    user_tier = subscription_checker.get_user_tier(current_user)

    # Check daily limit
    await subscription_checker.check_daily_limit(current_user)

    # Get historical data cutoff
    history_cutoff = subscription_checker.get_history_cutoff(current_user)

    # Build query - only get published predictions
    from app.models.predictions import PredictionStatus
    query = db.query(Prediction).filter(
        Prediction.status == PredictionStatus.PUBLISHED,
        Prediction.deleted_at.is_(None)
    )

    # Apply historical data limit
    if history_cutoff:
        query = query.filter(Prediction.created_at >= history_cutoff)

    # Apply date filters
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Prediction.created_at >= date_from_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date_from format. Use YYYY-MM-DD"
            )

    if date_to:
        try:
            date_to_dt = datetime.strptime(date_to, "%Y-%m-%d")
            query = query.filter(Prediction.created_at <= date_to_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date_to format. Use YYYY-MM-DD"
            )

    # Get total count
    total = query.count()

    # Apply pagination
    skip = (page - 1) * page_size
    predictions = query.order_by(Prediction.created_at.desc()).offset(skip).limit(page_size).all()

    # Increment daily count
    await subscription_checker.increment_daily_count(current_user)

    # Prepare response - simplified for now
    prediction_list = []
    for pred in predictions:
        prediction_list.append({
            "id": str(pred.id),
            "match_id": str(pred.match_id),
            "home_win_prob": float(pred.home_win_prob),
            "draw_prob": float(pred.draw_prob),
            "away_win_prob": float(pred.away_win_prob),
            "confidence_level": float(pred.confidence_score) if subscription_checker.should_show_confidence(current_user) else None,
            "source": pred.source.value,
            "created_at": pred.created_at
        })

    # Get tier info
    tier_limits = subscription_checker.TIER_LIMITS[user_tier]
    daily_used = await subscription_checker.get_daily_count(current_user)
    daily_limit = tier_limits['daily']

    return {
        "predictions": prediction_list,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size
        },
        "tier_info": {
            "tier": user_tier,
            "daily_limit": daily_limit,
            "daily_used": daily_used,
            "daily_remaining": daily_limit - daily_used if daily_limit else None
        }
    }


@router.get("/today")
async def get_today_predictions(
    sort_by: str = Query("created_at", description="Sort by: confidence, created_at"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get today's predictions with subscription tier filtering

    **Permission**: Any authenticated user

    Returns predictions created today.
    """
    # Get user's subscription tier
    user_tier = subscription_checker.get_user_tier(current_user)

    # Check daily limit
    await subscription_checker.check_daily_limit(current_user)

    # Calculate today's date range (UTC)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Build query
    from app.models.predictions import PredictionStatus
    query = db.query(Prediction).filter(
        Prediction.status == PredictionStatus.PUBLISHED,
        Prediction.deleted_at.is_(None),
        Prediction.created_at >= today_start,
        Prediction.created_at < today_end
    )

    # Apply sorting
    if sort_by == "confidence":
        query = query.order_by(Prediction.confidence_score.desc())
    else:
        query = query.order_by(Prediction.created_at.desc())

    predictions = query.all()

    # Increment daily count
    await subscription_checker.increment_daily_count(current_user)

    # Prepare response
    prediction_list = []
    for pred in predictions:
        prediction_list.append({
            "id": str(pred.id),
            "match_id": str(pred.match_id),
            "home_win_prob": float(pred.home_win_prob),
            "draw_prob": float(pred.draw_prob),
            "away_win_prob": float(pred.away_win_prob),
            "confidence_level": float(pred.confidence_score) if subscription_checker.should_show_confidence(current_user) else None,
            "source": pred.source.value,
            "created_at": pred.created_at
        })

    # Get tier info
    tier_limits = subscription_checker.TIER_LIMITS[user_tier]
    daily_used = await subscription_checker.get_daily_count(current_user)
    daily_limit = tier_limits['daily']

    return {
        "predictions": prediction_list,
        "pagination": {
            "page": 1,
            "page_size": len(prediction_list),
            "total_items": len(prediction_list),
            "total_pages": 1
        },
        "tier_info": {
            "tier": user_tier,
            "daily_limit": daily_limit,
            "daily_used": daily_used,
            "daily_remaining": daily_limit - daily_used if daily_limit else None
        }
    }


@router.get("/{prediction_id}")
async def get_prediction_detail(
    prediction_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information for a specific prediction

    **Permission**: Any authenticated user

    Returns detailed prediction data including match details and analysis.
    """
    # Fetch prediction
    from app.models.predictions import PredictionStatus
    prediction = db.query(Prediction).filter(
        Prediction.id == prediction_id,
        Prediction.deleted_at.is_(None)
    ).first()

    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction not found"
        )

    # Check if prediction is within historical data limit
    history_cutoff = subscription_checker.get_history_cutoff(current_user)
    if history_cutoff and prediction.created_at < history_cutoff:
        user_tier = subscription_checker.get_user_tier(current_user)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Prediction too old for {user_tier} tier"
        )

    # Prepare response
    return {
        "id": str(prediction.id),
        "match_id": str(prediction.match_id),
        "home_win_prob": float(prediction.home_win_prob),
        "draw_prob": float(prediction.draw_prob),
        "away_win_prob": float(prediction.away_win_prob),
        "confidence_level": float(prediction.confidence_score) if subscription_checker.should_show_confidence(current_user) else None,
        "source": prediction.source.value,
        "reasoning": prediction.reasoning,
        "key_factors": prediction.key_factors,
        "status": prediction.status.value,
        "created_at": prediction.created_at
    }


@router.post("/{prediction_id}/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    prediction_id: str,
    feedback_data: FeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Submit feedback for a prediction

    **Permission**: Any authenticated user

    Allows users to rate and comment on predictions.
    """
    # Check if prediction exists
    prediction = db.query(Prediction).filter(
        Prediction.id == prediction_id,
        Prediction.deleted_at.is_(None)
    ).first()

    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction not found"
        )

    # Check if user already submitted feedback
    from app.models.predictions import UserPredictionFeedback
    existing_feedback = db.query(UserPredictionFeedback).filter(
        UserPredictionFeedback.prediction_id == prediction_id,
        UserPredictionFeedback.user_id == current_user.id
    ).first()

    if existing_feedback:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted feedback for this prediction"
        )

    # Validate rating if provided
    if feedback_data.rating and (feedback_data.rating < 1 or feedback_data.rating > 5):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating must be between 1 and 5"
        )

    # Create feedback
    feedback = UserPredictionFeedback(
        prediction_id=prediction_id,
        user_id=current_user.id,
        rating=feedback_data.rating,
        comment=feedback_data.comment,
        is_upvote=feedback_data.is_upvote,
        is_downvote=feedback_data.is_downvote,
        created_at=datetime.utcnow()
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return {
        "id": str(feedback.id),
        "prediction_id": str(feedback.prediction_id),
        "user_id": str(feedback.user_id),
        "rating": feedback.rating,
        "comment": feedback.comment,
        "is_upvote": feedback.is_upvote,
        "is_downvote": feedback.is_downvote,
        "created_at": feedback.created_at,
        "message": "Feedback submitted successfully"
    }


@router.get("/{prediction_id}/feedback")
async def get_prediction_feedback(
    prediction_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get feedback for a prediction

    **Permission**: Any authenticated user

    Returns paginated list of feedback for a prediction.
    """
    # Check if prediction exists
    prediction = db.query(Prediction).filter(
        Prediction.id == prediction_id,
        Prediction.deleted_at.is_(None)
    ).first()

    if not prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prediction not found"
        )

    # Get feedback
    from app.models.predictions import UserPredictionFeedback
    query = db.query(UserPredictionFeedback).filter(
        UserPredictionFeedback.prediction_id == prediction_id
    )

    total = query.count()
    skip = (page - 1) * page_size
    feedback_list = query.order_by(UserPredictionFeedback.created_at.desc()).offset(skip).limit(page_size).all()

    # Calculate summary
    all_feedback = db.query(UserPredictionFeedback).filter(
        UserPredictionFeedback.prediction_id == prediction_id
    ).all()

    total_feedback = len(all_feedback)
    ratings_only = [f.rating for f in all_feedback if f.rating is not None]
    average_rating = sum(ratings_only) / len(ratings_only) if ratings_only else 0
    rating_distribution = {i: sum(1 for f in all_feedback if f.rating == i) for i in range(1, 6)}
    upvote_count = sum(1 for f in all_feedback if f.is_upvote)
    downvote_count = sum(1 for f in all_feedback if f.is_downvote)

    # Prepare feedback list
    feedback_data = []
    for f in feedback_list:
        feedback_data.append({
            "id": str(f.id),
            "prediction_id": str(f.prediction_id),
            "user_id": str(f.user_id),
            "rating": f.rating,
            "comment": f.comment,
            "is_upvote": f.is_upvote,
            "is_downvote": f.is_downvote,
            "created_at": f.created_at
        })

    return {
        "prediction_id": prediction_id,
        "summary": {
            "average_rating": round(average_rating, 2),
            "total_feedback": total_feedback,
            "rating_distribution": rating_distribution,
            "upvote_count": upvote_count,
            "downvote_count": downvote_count
        },
        "feedback": feedback_data,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    }

