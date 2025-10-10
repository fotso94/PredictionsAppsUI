# Redis Caching Layer Documentation

## Overview

The Soccer Predictions Platform uses a comprehensive Redis caching layer to improve performance, reduce database load, and provide fast access to frequently accessed data. The caching system is organized into 6 dedicated Redis databases, each serving a specific purpose.

## Architecture

### Redis Database Allocation

```
Redis Instance (Port 6379)
├── DB 0: Sessions (User sessions and authentication)
├── DB 1: Predictions (Prediction data caching)
├── DB 2: Expert Tools (Expert-specific data)
├── DB 3: ML Models (ML model predictions)
├── DB 4: Match Data (Real-time match information)
└── DB 5: Rate Limiting (API rate limiting)
```

### Key Components

1. **Base Cache Service** (`app/services/cache.py`)
   - Generic caching operations (get, set, delete, etc.)
   - Batch operations (get_many, set_many)
   - Pattern-based deletion
   - Counter operations (increment, decrement)
   - TTL management

2. **Session Cache Service** (`app/services/session_cache.py`)
   - User session management
   - Token blacklisting
   - Refresh token storage
   - User data caching
   - Permission caching

3. **Prediction Cache Service** (`app/services/prediction_cache.py`)
   - Prediction data caching
   - Match predictions caching
   - ML model output caching
   - Match data caching
   - Batch operations

## Usage Guide

### Basic Cache Operations

```python
from app.services.cache import sessions_cache, predictions_cache

# Set a value with TTL
sessions_cache.set("user:123:session", {"email": "user@example.com"}, ttl=300)

# Get a value
session_data = sessions_cache.get("user:123:session")

# Delete a value
sessions_cache.delete("user:123:session")

# Check if key exists
exists = sessions_cache.exists("user:123:session")
```

### Session Caching

```python
from app.services.session_cache import session_cache_service

# Store user session
session_cache_service.set_user_session(
    user_id="user_123",
    session_data={
        "email": "user@example.com",
        "role": "expert",
        "login_time": datetime.utcnow().isoformat()
    },
    ttl=3600  # 1 hour
)

# Get user session
session = session_cache_service.get_user_session("user_123")

# Blacklist a token
session_cache_service.blacklist_token(jti="token_jti", ttl=3600)

# Check if token is blacklisted
is_blacklisted = session_cache_service.is_token_blacklisted("token_jti")

# Cache user permissions
session_cache_service.cache_user_permissions(
    user_id="user_123",
    permissions=["prediction:read", "expert:override_ml"],
    ttl=600  # 10 minutes
)

# Get cached permissions
permissions = session_cache_service.get_cached_user_permissions("user_123")
```

### Prediction Caching

```python
from app.services.prediction_cache import prediction_cache_service

# Cache a prediction
prediction_cache_service.cache_prediction(
    prediction_id="pred_123",
    prediction_data={
        "match_id": "match_456",
        "home_win_prob": 0.45,
        "draw_prob": 0.30,
        "away_win_prob": 0.25,
        "source": "ml",
        "confidence": 0.80
    },
    ttl=300  # 5 minutes
)

# Get cached prediction
prediction = prediction_cache_service.get_cached_prediction("pred_123")

# Cache all predictions for a match
prediction_cache_service.cache_match_predictions(
    match_id="match_456",
    predictions=[
        {"source": "ml", "confidence": 0.75, "home_win": 0.45},
        {"source": "expert", "confidence": 0.85, "home_win": 0.50}
    ],
    ttl=300
)

# Get all predictions for a match
predictions = prediction_cache_service.get_cached_match_predictions("match_456")

# Cache ML model prediction
prediction_cache_service.cache_ml_prediction(
    match_id="match_456",
    model_version="v1.2.0",
    ml_output={
        "home_win": 0.45,
        "draw": 0.30,
        "away_win": 0.25,
        "confidence": 0.80
    },
    ttl=600  # 10 minutes
)

# Get ML prediction
ml_pred = prediction_cache_service.get_cached_ml_prediction("match_456", "v1.2.0")
```

### Using Cache Decorators

```python
from app.services.cache import cached, cache_invalidate, predictions_cache

# Cache function results
@cached(predictions_cache, key_prefix="match_pred", ttl=600)
def get_match_predictions(match_id: str):
    # Expensive database query or API call
    predictions = fetch_predictions_from_db(match_id)
    return predictions

# Invalidate cache after update
@cache_invalidate(predictions_cache, key_pattern="match_pred:*")
def update_prediction(prediction_id: str, data: dict):
    # Update prediction in database
    updated = update_prediction_in_db(prediction_id, data)
    return updated

# Use the cached function
predictions = get_match_predictions("match_123")  # First call: cache miss, fetches from DB
predictions = get_match_predictions("match_123")  # Second call: cache hit, returns from cache
```

### Batch Operations

```python
from app.services.prediction_cache import prediction_cache_service

# Cache multiple predictions at once
predictions = {
    "pred_1": {"match_id": "match_1", "home_win": 0.45},
    "pred_2": {"match_id": "match_2", "home_win": 0.50},
    "pred_3": {"match_id": "match_3", "home_win": 0.40}
}
prediction_cache_service.cache_multiple_predictions(predictions, ttl=300)

# Get multiple predictions at once
prediction_ids = ["pred_1", "pred_2", "pred_3"]
cached_predictions = prediction_cache_service.get_multiple_predictions(prediction_ids)
```

## Cache Key Patterns

### Session Cache Keys

```
session:user:{user_id}:session          # User session data
session:user:{user_id}:data             # User profile data
session:user:{user_id}:permissions      # User permissions
session:blacklist:token:{jti}           # Blacklisted tokens
session:refresh:{user_id}:{jti}         # Refresh tokens
```

### Prediction Cache Keys

```
prediction:pred:{prediction_id}                    # Individual prediction
prediction:match:{match_id}:predictions            # All predictions for a match
ml:ml:{model_version}:match:{match_id}            # ML model prediction
match:data:{match_id}                              # Match data
```

## TTL Recommendations

| Data Type | Recommended TTL | Reason |
|-----------|----------------|--------|
| User Session | 7 days (604800s) | Matches access token expiration |
| User Data | 5 minutes (300s) | Balance between freshness and performance |
| User Permissions | 10 minutes (600s) | Permissions don't change frequently |
| Predictions | 5 minutes (300s) | Predictions may be updated |
| ML Predictions | 10 minutes (600s) | ML models run infrequently |
| Match Data | 3 minutes (180s) | Live match data changes frequently |
| Refresh Tokens | 30 days (2592000s) | Matches refresh token expiration |

## Cache Invalidation Strategies

### 1. Time-Based Expiration (TTL)
Most common approach - data expires automatically after TTL.

### 2. Event-Based Invalidation
Invalidate cache when data changes:

```python
# When prediction is updated
def update_prediction(prediction_id: str, data: dict):
    # Update in database
    updated = db.update(prediction_id, data)
    
    # Invalidate cache
    prediction_cache_service.invalidate_prediction(prediction_id)
    
    return updated
```

### 3. Pattern-Based Invalidation
Invalidate multiple related keys:

```python
# Invalidate all predictions for a match
prediction_cache_service.invalidate_match_predictions(match_id)

# Invalidate all user sessions
session_cache_service.cache.delete_pattern("user:*:session")
```

## Monitoring and Statistics

### Get Cache Statistics

```python
from app.services.prediction_cache import prediction_cache_service
from app.services.session_cache import session_cache_service

# Prediction cache stats
pred_stats = prediction_cache_service.get_cache_stats()
print(f"Predictions cached: {pred_stats['predictions_cached']}")
print(f"ML predictions cached: {pred_stats['ml_predictions_cached']}")

# Session cache stats
active_sessions = session_cache_service.get_active_sessions_count()
print(f"Active sessions: {active_sessions}")

# User session info
session_info = session_cache_service.get_user_session_info("user_123")
print(f"Has session: {session_info['has_session']}")
print(f"Session TTL: {session_info['session_ttl']} seconds")
```

## Best Practices

### 1. Always Set TTL
```python
# ✅ Good: Set appropriate TTL
cache.set("key", value, ttl=300)

# ❌ Bad: No TTL (data never expires)
cache.set("key", value)
```

### 2. Handle Cache Misses Gracefully
```python
# ✅ Good: Fallback to database
cached_data = cache.get("key")
if cached_data is None:
    cached_data = fetch_from_database()
    cache.set("key", cached_data, ttl=300)
return cached_data
```

### 3. Use Namespaced Keys
```python
# ✅ Good: Clear namespace
cache.set("user:123:session", data)

# ❌ Bad: Unclear key
cache.set("123", data)
```

### 4. Invalidate on Updates
```python
# ✅ Good: Invalidate after update
def update_user(user_id: str, data: dict):
    updated = db.update(user_id, data)
    session_cache_service.invalidate_user_data(user_id)
    return updated
```

### 5. Use Batch Operations When Possible
```python
# ✅ Good: Single batch operation
cache.set_many({"key1": "val1", "key2": "val2"}, ttl=300)

# ❌ Bad: Multiple individual operations
cache.set("key1", "val1", ttl=300)
cache.set("key2", "val2", ttl=300)
```

## Testing

Run cache tests:

```bash
# Run all cache tests
pytest backend/tests/test_cache_services.py -v

# Run specific test class
pytest backend/tests/test_cache_services.py::TestSessionCacheService -v

# Run with coverage
pytest backend/tests/test_cache_services.py --cov=app/services --cov-report=html
```

## Troubleshooting

### Cache Not Working

1. **Check Redis Connection**
   ```bash
   docker-compose exec redis redis-cli ping
   ```

2. **Check Redis Database**
   ```bash
   docker-compose exec redis redis-cli -n 0 KEYS "*"
   ```

3. **Check Logs**
   ```python
   from app.core.logging import logger
   logger.setLevel("DEBUG")
   ```

### High Memory Usage

1. **Check Key Count**
   ```bash
   docker-compose exec redis redis-cli DBSIZE
   ```

2. **Find Large Keys**
   ```bash
   docker-compose exec redis redis-cli --bigkeys
   ```

3. **Set Appropriate TTLs**
   - Review TTL settings
   - Implement cache eviction policies

## Performance Considerations

- **Cache Hit Rate**: Aim for >80% hit rate for frequently accessed data
- **TTL Balance**: Short TTL = fresher data but more DB queries; Long TTL = stale data but fewer queries
- **Memory Usage**: Monitor Redis memory usage and set maxmemory policies
- **Network Latency**: Redis is fast, but network calls still have overhead
- **Serialization**: JSON serialization adds overhead for complex objects

## Related Documentation

- [Local Development Architecture](../LOCAL_DEVELOPMENT_ARCHITECTURE_PLAN.md)
- [Backend API Documentation](../api/README.md)
- [Role-Based Permissions](./ROLE_BASED_PERMISSIONS.md)

