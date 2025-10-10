# Redis Caching Integration Examples

This document provides practical examples of how to integrate the Redis caching layer into existing endpoints and services.

## Table of Contents

1. [Authentication Endpoints](#authentication-endpoints)
2. [User Management](#user-management)
3. [Prediction Endpoints](#prediction-endpoints)
4. [Expert Tools](#expert-tools)
5. [Performance Optimization](#performance-optimization)

---

## Authentication Endpoints

### Example 1: Cache User Data After Login

**Before (without caching):**

```python
@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    # Authenticate user
    user = authenticate_user(db, credentials.email, credentials.password)
    
    # Generate tokens
    access_token = create_access_token(user.id, user.user_type)
    refresh_token = create_refresh_token(user.id)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo.from_orm(user)
    )
```

**After (with caching):**

```python
from app.services.session_cache import session_cache_service

@router.post("/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db)
):
    # Authenticate user
    user = authenticate_user(db, credentials.email, credentials.password)
    
    # Generate tokens
    access_token = create_access_token(user.id, user.user_type)
    refresh_token = create_refresh_token(user.id)
    
    # Cache user session
    session_cache_service.set_user_session(
        user_id=str(user.id),
        session_data={
            "email": user.email,
            "username": user.username,
            "role": user.user_type.value,
            "login_time": datetime.utcnow().isoformat()
        },
        ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    
    # Cache user data for quick access
    session_cache_service.cache_user_data(
        user_id=str(user.id),
        user_data={
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "user_type": user.user_type.value,
            "account_status": user.account_status.value
        },
        ttl=300  # 5 minutes
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserInfo.from_orm(user)
    )
```

### Example 2: Cache User Permissions

```python
from app.services.session_cache import session_cache_service
from app.core.permissions import get_user_permissions

@router.get("/me/permissions", response_model=UserPermissionsResponse)
async def get_current_user_permissions(
    current_user: User = Depends(get_current_active_user)
):
    user_id = str(current_user.id)
    
    # Try to get from cache first
    cached_permissions = session_cache_service.get_cached_user_permissions(user_id)
    
    if cached_permissions is not None:
        return UserPermissionsResponse(
            user_id=user_id,
            role=current_user.user_type.value,
            permissions=cached_permissions
        )
    
    # Cache miss - compute and cache
    permissions = get_user_permissions(current_user)
    permission_strings = [p.value for p in permissions]
    
    # Cache for 10 minutes
    session_cache_service.cache_user_permissions(
        user_id=user_id,
        permissions=permission_strings,
        ttl=600
    )
    
    return UserPermissionsResponse(
        user_id=user_id,
        role=current_user.user_type.value,
        permissions=permission_strings
    )
```

---

## User Management

### Example 3: Cache User Profile Data

```python
from app.services.session_cache import session_cache_service

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    # Try cache first
    cached_user = session_cache_service.get_cached_user_data(user_id)
    
    if cached_user:
        return UserResponse(**cached_user)
    
    # Cache miss - fetch from database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prepare response
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "user_type": user.user_type.value,
        "account_status": user.account_status.value,
        "email_verified": user.email_verified,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat()
    }
    
    # Cache for 5 minutes
    session_cache_service.cache_user_data(user_id, user_data, ttl=300)
    
    return UserResponse(**user_data)
```

### Example 4: Invalidate Cache on Update

```python
from app.services.session_cache import session_cache_service

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    # Update user in database
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Apply updates
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    # Invalidate all cached data for this user
    session_cache_service.invalidate_user_data(user_id)
    session_cache_service.invalidate_user_permissions(user_id)
    session_cache_service.delete_user_session(user_id)
    
    return UserResponse.from_orm(user)
```

---

## Prediction Endpoints

### Example 5: Cache Match Predictions

```python
from app.services.prediction_cache import prediction_cache_service

@router.get("/matches/{match_id}/predictions")
async def get_match_predictions(
    match_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Try cache first
    cached_predictions = prediction_cache_service.get_cached_match_predictions(match_id)
    
    if cached_predictions:
        return {"match_id": match_id, "predictions": cached_predictions}
    
    # Cache miss - fetch from database
    predictions = db.query(Prediction).filter(
        Prediction.match_id == match_id
    ).all()
    
    # Prepare prediction data
    prediction_data = [
        {
            "id": str(p.id),
            "source": p.source_type.value,
            "home_win_prob": p.home_win_probability,
            "draw_prob": p.draw_probability,
            "away_win_prob": p.away_win_probability,
            "confidence": p.confidence_score
        }
        for p in predictions
    ]
    
    # Cache for 5 minutes
    prediction_cache_service.cache_match_predictions(
        match_id=match_id,
        predictions=prediction_data,
        ttl=300
    )
    
    return {"match_id": match_id, "predictions": prediction_data}
```

### Example 6: Cache ML Model Predictions

```python
from app.services.prediction_cache import prediction_cache_service

async def generate_ml_prediction(match_id: str, model_version: str):
    """Generate ML prediction with caching"""
    
    # Try cache first
    cached_ml_pred = prediction_cache_service.get_cached_ml_prediction(
        match_id=match_id,
        model_version=model_version
    )
    
    if cached_ml_pred:
        return cached_ml_pred
    
    # Cache miss - run ML model (expensive operation)
    ml_output = run_ml_model(match_id, model_version)
    
    # Cache for 10 minutes
    prediction_cache_service.cache_ml_prediction(
        match_id=match_id,
        model_version=model_version,
        ml_output=ml_output,
        ttl=600
    )
    
    return ml_output
```

---

## Expert Tools

### Example 7: Cache Expert Analysis

```python
from app.services.cache import expert_tools_cache

@router.get("/expert/analysis/{match_id}")
async def get_expert_analysis(
    match_id: str,
    current_user: User = Depends(get_current_verified_expert_user),
    db: Session = Depends(get_db)
):
    cache_key = f"analysis:{match_id}"
    
    # Try cache first
    cached_analysis = expert_tools_cache.get(cache_key)
    if cached_analysis:
        return cached_analysis
    
    # Fetch and compute analysis (expensive)
    analysis = compute_expert_analysis(match_id, db)
    
    # Cache for 15 minutes
    expert_tools_cache.set(cache_key, analysis, ttl=900)
    
    return analysis
```

---

## Performance Optimization

### Example 8: Using Cache Decorators

```python
from app.services.cache import cached, predictions_cache

@cached(predictions_cache, key_prefix="top_predictions", ttl=600)
def get_top_predictions(limit: int = 10):
    """Get top predictions - cached for 10 minutes"""
    # Expensive database query
    predictions = db.query(Prediction).order_by(
        Prediction.confidence_score.desc()
    ).limit(limit).all()
    
    return [p.to_dict() for p in predictions]

# Usage
top_preds = get_top_predictions(limit=10)  # First call: cache miss
top_preds = get_top_predictions(limit=10)  # Second call: cache hit!
```

### Example 9: Batch Cache Operations

```python
from app.services.prediction_cache import prediction_cache_service

async def cache_multiple_match_predictions(match_ids: List[str], db: Session):
    """Cache predictions for multiple matches efficiently"""
    
    predictions_by_match = {}
    
    for match_id in match_ids:
        predictions = db.query(Prediction).filter(
            Prediction.match_id == match_id
        ).all()
        
        predictions_by_match[match_id] = [
            {
                "id": str(p.id),
                "home_win": p.home_win_probability,
                "draw": p.draw_probability,
                "away_win": p.away_win_probability
            }
            for p in predictions
        ]
    
    # Cache all at once (more efficient than individual sets)
    for match_id, preds in predictions_by_match.items():
        prediction_cache_service.cache_match_predictions(
            match_id=match_id,
            predictions=preds,
            ttl=300
        )
```

### Example 10: Cache Statistics Monitoring

```python
from app.services.prediction_cache import prediction_cache_service
from app.services.session_cache import session_cache_service

@router.get("/admin/cache/stats")
async def get_cache_statistics(
    current_user: User = Depends(get_current_admin_user)
):
    """Get cache statistics for monitoring"""
    
    pred_stats = prediction_cache_service.get_cache_stats()
    active_sessions = session_cache_service.get_active_sessions_count()
    
    return {
        "predictions": pred_stats,
        "sessions": {
            "active_count": active_sessions
        },
        "timestamp": datetime.utcnow().isoformat()
    }
```

---

## Best Practices Summary

1. **Always set appropriate TTL** - Balance between data freshness and performance
2. **Try cache first** - Check cache before hitting the database
3. **Invalidate on updates** - Clear cache when data changes
4. **Use batch operations** - More efficient for multiple keys
5. **Monitor cache performance** - Track hit rates and memory usage
6. **Handle cache failures gracefully** - Always have a fallback to database
7. **Use meaningful key patterns** - Makes debugging and invalidation easier
8. **Cache expensive operations** - ML predictions, complex queries, external API calls

---

## Related Documentation

- [Redis Caching Layer](./REDIS_CACHING_LAYER.md)
- [Role-Based Permissions](./ROLE_BASED_PERMISSIONS.md)
- [Backend API Documentation](../api/README.md)

