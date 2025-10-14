# KAN-26 Manual Testing Guide

## Expert API Endpoints - Manual Testing Guide

This guide provides step-by-step instructions for manually testing all Expert API endpoints implemented in KAN-26.

---

## Prerequisites

1. **Backend server running**: `http://localhost:8000`
2. **Swagger UI available**: `http://localhost:8000/api/docs`
3. **Test users created**:
   - Expert user (verified)
   - Admin user
   - Regular user (for negative testing)

---

## Test Environment Setup

### 1. Start Backend Server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 2. Access Swagger UI

Open browser: `http://localhost:8000/api/docs`

### 3. Authenticate

1. Click "Authorize" button in Swagger UI
2. Login with expert user credentials
3. Copy the access token
4. Enter token in format: `Bearer <your-token>`

---

## Test Cases

### **Test 1: Create Manual Expert Prediction (KAN-149)**

**Endpoint**: `POST /api/v1/expert/predictions/manual`

**Test Data**:
```json
{
  "match_id": "550e8400-e29b-41d4-a716-446655440000",
  "home_win_prob": 0.6,
  "draw_prob": 0.25,
  "away_win_prob": 0.15,
  "confidence_score": 0.85,
  "reasoning": "Home team has excellent form with 5 consecutive wins. Away team missing key players.",
  "key_factors": {
    "home_form": "WWWWW",
    "away_injuries": ["Player A", "Player B"],
    "head_to_head": "Home team won last 3 meetings"
  }
}
```

**Expected Response**:
- Status: `200 OK`
- Response body contains:
  - `id`: UUID of created prediction
  - `source`: `"expert_manual"`
  - `priority_level`: `100`
  - `status`: `"pending"`
  - All probability fields match input

**Verification**:
1. ✅ Prediction created successfully
2. ✅ Status is PENDING (requires approval)
3. ✅ Priority level is 100 (highest)
4. ✅ Audit log entry created

---

### **Test 2: Override Existing Prediction (KAN-150)**

**Endpoint**: `POST /api/v1/expert/predictions/override`

**Prerequisites**:
- Create a prediction first (use Test 1)
- Copy the `prediction_id` from response

**Test Data**:
```json
{
  "prediction_id": "<paste-prediction-id-here>",
  "home_win_prob": 0.7,
  "draw_prob": 0.2,
  "away_win_prob": 0.1,
  "confidence_score": 0.9,
  "reasoning": "Updated analysis: Home team confirmed starting lineup. Away team's star player ruled out.",
  "key_factors": {
    "lineup_confirmed": true,
    "away_star_player_out": true
  }
}
```

**Expected Response**:
- Status: `200 OK`
- Response body contains:
  - `source`: `"expert_override"`
  - `priority_level`: `100`
  - `status`: `"pending"`
  - Original prediction marked as superseded

**Verification**:
1. ✅ Override prediction created
2. ✅ Original prediction has `superseded_by` field set
3. ✅ Audit trail shows override event
4. ✅ Reasoning is required (min 10 chars)

**Negative Test**:
- Try with invalid `prediction_id` → Expect `404 Not Found`
- Try with probabilities that don't sum to 1.0 → Expect `422 Validation Error`

---

### **Test 3: Get Review Queue (KAN-151)**

**Endpoint**: `GET /api/v1/expert/predictions/review-queue`

**Query Parameters**:
- `limit`: `10`
- `offset`: `0`

**Expected Response**:
- Status: `200 OK`
- Array of predictions with `status: "pending"`
- Ordered by `created_at` DESC (newest first)

**Verification**:
1. ✅ Returns only PENDING predictions
2. ✅ Pagination works correctly
3. ✅ Results ordered by creation date

**Test Pagination**:
```
GET /api/v1/expert/predictions/review-queue?limit=5&offset=0  # First page
GET /api/v1/expert/predictions/review-queue?limit=5&offset=5  # Second page
```

---

### **Test 4: Get My Predictions (KAN-152)**

**Endpoint**: `GET /api/v1/expert/predictions/my-predictions`

**Query Parameters**:
- `limit`: `20`
- `offset`: `0`
- `status`: `"pending"` (optional)

**Expected Response**:
- Status: `200 OK`
- Array of predictions created by current expert
- Filtered by status if provided

**Verification**:
1. ✅ Returns only current expert's predictions
2. ✅ Status filter works correctly
3. ✅ Pagination works

**Test Status Filters**:
```
GET /api/v1/expert/predictions/my-predictions?status=pending
GET /api/v1/expert/predictions/my-predictions?status=approved
GET /api/v1/expert/predictions/my-predictions?status=published
```

**Negative Test**:
- Invalid status → Expect `400 Bad Request`

---

### **Test 5: Get Expert Performance Metrics (KAN-153)**

**Endpoint**: `GET /api/v1/expert/analytics/performance`

**Expected Response**:
- Status: `200 OK`
- Response body contains:
  ```json
  {
    "expert_id": "...",
    "expert_name": "...",
    "total_predictions": 10,
    "published_predictions": 5,
    "pending_predictions": 3,
    "accuracy_rate": null,
    "average_confidence": 0.82,
    "predictions_by_league": {},
    "recent_predictions": [...],
    "performance_trend": []
  }
  ```

**Verification**:
1. ✅ Metrics calculated correctly
2. ✅ Recent predictions included (up to 10)
3. ✅ Average confidence calculated
4. ✅ Counts match actual predictions

---

## Database Verification

### Check Prediction Priority System

```sql
-- View predictions with priority levels
SELECT 
    id,
    match_id,
    source,
    priority_level,
    status,
    superseded_by,
    created_at
FROM predictions.predictions
ORDER BY priority_level DESC, created_at DESC
LIMIT 10;
```

### Check Audit Trail

```sql
-- View audit logs for predictions
SELECT 
    action,
    user_id,
    resource_type,
    resource_id,
    description,
    created_at
FROM audit.audit_logs
WHERE resource_type = 'prediction'
ORDER BY created_at DESC
LIMIT 10;
```

### Check Prediction Overrides

```sql
-- View prediction overrides
SELECT 
    original_prediction_id,
    override_prediction_id,
    overridden_by,
    override_reason,
    created_at
FROM predictions.prediction_overrides
ORDER BY created_at DESC
LIMIT 10;
```

---

## Authorization Testing

### Test Expert Access Control

1. **Verified Expert User**:
   - ✅ Can create manual predictions
   - ✅ Can override predictions
   - ✅ Can view review queue
   - ✅ Can view own predictions
   - ✅ Can view performance metrics

2. **Unverified Expert User**:
   - ❌ Cannot create manual predictions → `403 Forbidden`
   - ❌ Cannot override predictions → `403 Forbidden`
   - ✅ Can view review queue
   - ✅ Can view own predictions

3. **Regular User**:
   - ❌ Cannot access any expert endpoints → `403 Forbidden`

4. **Admin User**:
   - ✅ Has all expert permissions
   - ✅ Always considered "verified"

---

## Performance Testing

### Test Response Times

Expected response times (P95):
- Create prediction: < 500ms
- Override prediction: < 500ms
- Get review queue: < 300ms
- Get my predictions: < 300ms
- Get performance metrics: < 500ms

### Test Concurrent Requests

```bash
# Use Apache Bench or similar tool
ab -n 100 -c 10 -H "Authorization: Bearer <token>" \
   http://localhost:8000/api/v1/expert/predictions/review-queue
```

Expected:
- ✅ No errors
- ✅ Consistent response times
- ✅ No database deadlocks

---

## Cache Verification

### Test Cache Invalidation

1. Create a prediction for match X
2. Get prediction for match X → Should return new prediction
3. Override prediction for match X
4. Get prediction for match X → Should return override (cache invalidated)

---

## Error Handling Testing

### Test Validation Errors

1. **Probabilities don't sum to 1.0**:
   ```json
   {
     "home_win_prob": 0.5,
     "draw_prob": 0.3,
     "away_win_prob": 0.3
   }
   ```
   Expected: `422 Validation Error`

2. **Missing required fields**:
   ```json
   {
     "match_id": "...",
     "home_win_prob": 0.6
   }
   ```
   Expected: `422 Validation Error`

3. **Invalid reasoning (too short)**:
   ```json
   {
     "reasoning": "short"
   }
   ```
   Expected: `422 Validation Error`

---

## Success Criteria

✅ All 5 Expert API endpoints functional
✅ Authentication/authorization working correctly
✅ Database schema changes applied
✅ Audit logging working
✅ Cache invalidation working
✅ Response times within acceptable limits
✅ Error handling working correctly
✅ Swagger UI documentation accurate

---

## Troubleshooting

### Common Issues

1. **403 Forbidden**:
   - Check user has expert role
   - Check expert is verified
   - Check token is valid

2. **422 Validation Error**:
   - Check probabilities sum to 1.0
   - Check all required fields present
   - Check field types match schema

3. **500 Internal Server Error**:
   - Check backend logs
   - Check database connection
   - Check Redis connection

---

## Next Steps

After manual testing:
1. Run automated integration tests
2. Run E2E tests
3. Update API documentation
4. Deploy to staging environment
5. Perform UAT (User Acceptance Testing)

