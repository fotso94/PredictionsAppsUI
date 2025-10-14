# KAN-26: Storage & Tracking Recommendations - Brief Summary

**Date**: 2025-10-12 | **Author**: Development Team (Co-authored by Steph)

## Executive Recommendation

**REVISED STORAGE STRATEGY**: Store ONLY Expert and LLM predictions in database. Access API-Football predictions directly from API/cache.

### Storage Strategy

| Source | Store in DB? | Rationale | Access Method |
|--------|-------------|-----------|---------------|
| **Expert Predictions** | ✅ YES | High value, audit trail, performance tracking | PostgreSQL |
| **LLM Predictions** | ✅ YES | Medium value, A/B testing, ML training | PostgreSQL |
| **API-Football** | ❌ NO | Low value, external source, real-time data | Direct API + Redis cache (15min TTL) |

**Benefits**: 60-70% storage reduction, simpler data management, lower costs, still maintains audit trail for high-value predictions.

**Cost Impact**: $6/month (vs $17/month storing all) at enterprise scale (50,000 matches/day).

### User Tracking Strategy

**Create**: `analytics.prediction_source_views` table to track which predictions users actually see.

**Key Metrics**: Views by source (Expert/LLM/API), views by tier (Free/Basic/Premium/Pro), engagement rate, tier conversion after viewing expert predictions.

**Implementation**: Track in existing analytics schema, 1-year retention, use data to optimize which predictions to generate.

---

## Detailed Analysis

### 1. Revised Storage Strategy: Expert + LLM Only

#### Why NOT Store API-Football Predictions?

**Rationale**:
1. **External Source**: API-Football is third-party data we don't own
2. **Real-time Access**: API provides fresh data on-demand
3. **Low Audit Value**: Not our predictions, no need for historical tracking
4. **Storage Waste**: Storing data we can retrieve anytime from API
5. **Caching Sufficient**: 15-minute Redis cache provides performance without DB storage

#### Proposed Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              PREDICTION STORAGE ARCHITECTURE                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PostgreSQL Database (Long-term Storage)                    │
│  ├── Expert Predictions (priority 100)                      │
│  │   └── Store: ALL (audit trail, performance tracking)     │
│  └── LLM Predictions (priority 50)                          │
│      └── Store: ALL (A/B testing, ML training)              │
│                                                             │
│  Redis Cache (Short-term, 15min TTL)                        │
│  └── API-Football Predictions (priority 25)                 │
│      └── Cache: Recent only (performance optimization)      │
│                                                             │
│  API-Football API (Real-time Access)                        │
│  └── Fetch on-demand when not in cache                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Implementation Details

**PredictionAggregatorService (Updated)**:

```python
async def get_prediction_for_match(self, match_id: str, user_tier: str) -> Prediction:
    """Get highest priority prediction with revised storage strategy"""
    
    # 1. Check Expert prediction (stored in DB)
    if user_tier in ['premium', 'pro']:
        expert_pred = await self.db.query(Prediction).filter(
            Prediction.match_id == match_id,
            Prediction.source.in_(['expert_manual', 'expert_override']),
            Prediction.status == 'published'
        ).first()
        if expert_pred:
            return expert_pred
    
    # 2. Check LLM prediction (stored in DB)
    if user_tier in ['basic', 'premium', 'pro']:
        llm_pred = await self.db.query(Prediction).filter(
            Prediction.match_id == match_id,
            Prediction.source == 'llm_generated',
            Prediction.status == 'published'
        ).first()
        if llm_pred:
            return llm_pred
    
    # 3. Check API-Football (Redis cache first, then API)
    api_pred = await self._get_api_football_prediction(match_id)
    if api_pred:
        return api_pred
    
    # 4. Fallback to randomized
    return await self._generate_randomized_prediction(match_id)

async def _get_api_football_prediction(self, match_id: str) -> Optional[Prediction]:
    """Get API-Football prediction from cache or API (NOT database)"""
    
    # Check Redis cache first
    cache_key = f"api_football:prediction:{match_id}"
    cached = await self.cache.get(cache_key)
    if cached:
        return self._convert_to_prediction_object(cached)
    
    # Fetch from API-Football API
    api_response = await self.api_football_client.get_prediction(match_id)
    if api_response:
        # Cache for 15 minutes
        await self.cache.set(cache_key, api_response, ttl=900)
        return self._convert_to_prediction_object(api_response)
    
    return None
```

#### Storage Comparison

| Scenario | Store ALL | Store Expert+LLM Only | Savings |
|----------|-----------|------------------------|---------|
| **Small** (1,000 matches/day) | 1.62 GB | 0.54 GB | 67% |
| **Medium** (5,000 matches/day) | 8.1 GB | 2.7 GB | 67% |
| **Large** (20,000 matches/day) | 32.4 GB | 10.8 GB | 67% |
| **Enterprise** (50,000 matches/day) | 81 GB | 27 GB | 67% |

**Cost Savings** (Enterprise scale, 3-year retention):
- Store ALL: $17.02/month
- Store Expert+LLM: $6.00/month
- **Savings**: $11/month ($132/year)

#### Audit Trail Considerations

**Question**: Do we lose audit trail by not storing API-Football predictions?

**Answer**: No, we maintain audit trail where it matters:

1. **Track Selection**: Log which prediction was shown to user in `prediction_audit` table
2. **Track Views**: Log user views in `analytics.prediction_source_views` table
3. **API-Football Data**: Can always retrieve historical data from API-Football API if needed
4. **High-Value Predictions**: Expert and LLM predictions (our IP) are fully tracked

**Audit Log Entry** (when API-Football prediction shown):
```json
{
  "action_type": "prediction_selected",
  "match_id": "abc-123",
  "source": "api_football_baseline",
  "priority_level": 25,
  "selection_reason": "no_expert_or_llm_available",
  "api_football_prediction_id": "ext-456",  // External ID
  "probabilities": {
    "home_win": 0.45,
    "draw": 0.30,
    "away_win": 0.25
  },
  "user_id": "user-789",
  "user_tier": "free",
  "created_at": "2025-10-12T10:00:00Z"
}
```

### 2. Data Retention Policies (Revised)

| Data Type | Retention | Storage | Rationale |
|-----------|-----------|---------|-----------|
| **Expert Predictions** | 3 years | PostgreSQL | High value, performance tracking, legal compliance |
| **LLM Predictions** | 2 years | PostgreSQL | ML training, A/B testing |
| **API-Football Cache** | 15 minutes | Redis | Performance only, no long-term storage |
| **Audit Logs** (all sources) | 7 years | PostgreSQL + S3 | Legal compliance, includes API-Football selection logs |
| **User Views** | 1 year | PostgreSQL | Analytics, engagement tracking |

**Cleanup Jobs**:

```python
# Monthly cleanup job
async def cleanup_old_predictions():
    """Remove old predictions based on retention policy"""
    
    # Delete expert predictions older than 3 years
    await db.execute("""
        DELETE FROM predictions.predictions
        WHERE source IN ('expert_manual', 'expert_override')
          AND created_at < NOW() - INTERVAL '3 years'
    """)
    
    # Delete LLM predictions older than 2 years
    await db.execute("""
        DELETE FROM predictions.predictions
        WHERE source = 'llm_generated'
          AND created_at < NOW() - INTERVAL '2 years'
    """)
    
    # Delete randomized defaults older than 30 days
    await db.execute("""
        DELETE FROM predictions.predictions
        WHERE source = 'default_randomized'
          AND created_at < NOW() - INTERVAL '30 days'
    """)
    
    # Archive audit logs older than 2 years to S3
    # (Keep in PostgreSQL for 2 years, S3 for 5 more years)
    await archive_old_audit_logs()
```

---

## 3. User Prediction Usage Tracking

### Metrics to Capture

#### Primary Metrics (Must Have)

| Metric | Description | Storage | Purpose |
|--------|-------------|---------|---------|
| **Views by Source** | Count of views per source (Expert/LLM/API) | `analytics.prediction_source_views` | Understand which sources users see |
| **Views by Tier** | Count of views per subscription tier | `analytics.prediction_source_views` | Measure tier-based access |
| **Active Prediction** | Which prediction was shown (highest priority) | `predictions.prediction_audit` | Track priority logic execution |
| **Engagement Rate** | % of views with interaction (click/share/feedback) | Calculated from views + feedback | Measure prediction quality |

#### Secondary Metrics (Nice to Have)

| Metric | Description | Purpose |
|--------|-------------|---------|
| **Tier Conversion** | Users upgrading after viewing expert predictions | Measure feature value |
| **Source Preference** | Which sources users engage with most | Optimize prediction generation |
| **View Duration** | How long users view predictions | Engagement quality |
| **Cost per View** | Cost efficiency by source | ROI analysis |

### Tracking Implementation

#### Schema: `analytics.prediction_source_views`

```sql
CREATE TABLE analytics.prediction_source_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- What was shown
    match_id UUID NOT NULL,
    prediction_source VARCHAR(50) NOT NULL,  -- expert_manual, llm_generated, api_football_baseline
    priority_level INTEGER NOT NULL,
    is_active_prediction BOOLEAN NOT NULL,  -- Was this the one shown?
    
    -- Who saw it
    user_id UUID REFERENCES users.users(id),
    user_tier VARCHAR(20) NOT NULL,  -- free, basic, premium, pro
    
    -- Context
    view_type VARCHAR(20) NOT NULL,  -- single, multi_source
    device_type VARCHAR(20),
    view_duration_seconds INTEGER,
    engaged BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    session_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Indexes
    INDEX idx_source_views_source (prediction_source),
    INDEX idx_source_views_tier (user_tier),
    INDEX idx_source_views_created_at (created_at)
);
```

#### Tracking Service

```python
class PredictionTrackingService:
    """Track prediction views and usage"""
    
    async def track_prediction_view(
        self,
        match_id: str,
        prediction_source: str,
        priority_level: int,
        user: Optional[User],
        is_active: bool = True
    ):
        """Track when a prediction is viewed"""
        
        view = PredictionSourceView(
            match_id=match_id,
            prediction_source=prediction_source,
            priority_level=priority_level,
            is_active_prediction=is_active,
            user_id=user.id if user else None,
            user_tier=user.subscription_tier if user else 'free',
            view_type='single',
            device_type=self._detect_device(),
            session_id=self._get_session_id()
        )
        
        self.db.add(view)
        await self.db.commit()
    
    async def get_source_performance(self, days: int = 30) -> dict:
        """Get performance metrics by source"""
        
        return await self.db.query(
            PredictionSourceView.prediction_source,
            func.count(PredictionSourceView.id).label('total_views'),
            func.count(func.distinct(PredictionSourceView.user_id)).label('unique_users'),
            func.avg(PredictionSourceView.view_duration_seconds).label('avg_duration'),
            (func.sum(func.cast(PredictionSourceView.engaged, Integer)) / 
             func.count(PredictionSourceView.id)).label('engagement_rate')
        ).filter(
            PredictionSourceView.created_at >= datetime.now() - timedelta(days=days)
        ).group_by(
            PredictionSourceView.prediction_source
        ).all()
```

### Analytics Queries

#### Query 1: Views by Source

```sql
-- Which prediction sources are users seeing?
SELECT 
    prediction_source,
    COUNT(*) as total_views,
    COUNT(DISTINCT user_id) as unique_users,
    AVG(view_duration_seconds) as avg_duration,
    SUM(CASE WHEN engaged THEN 1 ELSE 0 END)::FLOAT / COUNT(*) as engagement_rate
FROM analytics.prediction_source_views
WHERE created_at >= NOW() - INTERVAL '30 days'
GROUP BY prediction_source
ORDER BY total_views DESC;
```

**Expected Output**:
```
prediction_source        | total_views | unique_users | avg_duration | engagement_rate
-------------------------|-------------|--------------|--------------|----------------
api_football_baseline    | 45,000      | 8,500        | 12.3         | 0.15
llm_generated            | 12,000      | 3,200        | 18.7         | 0.28
expert_manual            | 3,500       | 1,800        | 45.2         | 0.62
```

**Insight**: Expert predictions have highest engagement (62%) despite fewer views.

#### Query 2: Tier Conversion Analysis

```sql
-- Do users upgrade after viewing expert predictions?
SELECT 
    original_tier,
    COUNT(DISTINCT user_id) as users_who_viewed_expert,
    COUNT(DISTINCT upgraded_user_id) as users_who_upgraded,
    COUNT(DISTINCT upgraded_user_id)::FLOAT / COUNT(DISTINCT user_id) as conversion_rate
FROM (
    SELECT 
        psv.user_id,
        psv.user_tier as original_tier,
        CASE 
            WHEN sh.new_tier IN ('premium', 'pro') 
                AND sh.changed_at BETWEEN psv.created_at AND psv.created_at + INTERVAL '7 days'
            THEN psv.user_id 
        END as upgraded_user_id
    FROM analytics.prediction_source_views psv
    LEFT JOIN users.subscription_history sh ON psv.user_id = sh.user_id
    WHERE psv.prediction_source IN ('expert_manual', 'expert_override')
      AND psv.created_at >= NOW() - INTERVAL '90 days'
      AND psv.user_tier IN ('free', 'basic')
) subquery
GROUP BY original_tier;
```

**Expected Output**:
```
original_tier | users_who_viewed_expert | users_who_upgraded | conversion_rate
--------------|-------------------------|--------------------|-----------------
free          | 1,200                   | 180                | 0.15 (15%)
basic         | 800                     | 120                | 0.15 (15%)
```

**Insight**: 15% conversion rate justifies investment in expert predictions.

#### Query 3: Cost Efficiency by Source

```sql
-- What's the ROI of each prediction source?
WITH source_costs AS (
    SELECT 'expert_manual' as source, 1000.00 as monthly_cost
    UNION ALL SELECT 'llm_generated', 200.00
    UNION ALL SELECT 'api_football_baseline', 100.00
),
source_views AS (
    SELECT 
        prediction_source,
        COUNT(*) as total_views,
        COUNT(DISTINCT user_id) as unique_users
    FROM analytics.prediction_source_views
    WHERE created_at >= NOW() - INTERVAL '30 days'
    GROUP BY prediction_source
)
SELECT 
    sv.prediction_source,
    sc.monthly_cost,
    sv.total_views,
    sc.monthly_cost / sv.total_views as cost_per_view,
    sc.monthly_cost / sv.unique_users as cost_per_user
FROM source_views sv
JOIN source_costs sc ON sv.prediction_source = sc.source
ORDER BY cost_per_view;
```

**Expected Output**:
```
prediction_source        | monthly_cost | total_views | cost_per_view | cost_per_user
-------------------------|--------------|-------------|---------------|---------------
api_football_baseline    | $100         | 45,000      | $0.0022       | $0.012
llm_generated            | $200         | 12,000      | $0.0167       | $0.063
expert_manual            | $1,000       | 3,500       | $0.2857       | $0.556
```

**Insight**: API-Football is most cost-efficient per view, but expert predictions drive conversions.

---

## Final Recommendations

### ✅ Storage Strategy (REVISED)

**APPROVED**: Store ONLY Expert and LLM predictions in database

**Implementation**:
1. Store Expert predictions (3-year retention)
2. Store LLM predictions (2-year retention)
3. Cache API-Football predictions in Redis (15-minute TTL)
4. Access API-Football data directly from API when cache misses
5. Log ALL prediction selections in audit table (including API-Football)

**Benefits**:
- 67% storage reduction (27 GB vs 81 GB at enterprise scale)
- $11/month cost savings ($6 vs $17)
- Simpler data management
- Still maintains complete audit trail for high-value predictions

### ✅ User Tracking (APPROVED)

**Implementation**:
1. Create `analytics.prediction_source_views` table
2. Track every prediction view with source, tier, engagement
3. Implement `PredictionTrackingService`
4. Build analytics dashboards
5. Use data to optimize prediction generation

**Key Metrics**:
- Views by source (Expert/LLM/API)
- Views by tier (Free/Basic/Premium/Pro)
- Engagement rate by source
- Tier conversion after viewing expert predictions
- Cost per view by source

**Data Retention**: 1 year in PostgreSQL, then archive to S3

---

## Implementation Checklist

- [ ] Update database schema (remove API-Football from predictions table)
- [ ] Implement Redis caching for API-Football predictions
- [ ] Update `PredictionAggregatorService` to fetch API-Football from API/cache
- [ ] Create `analytics.prediction_source_views` table
- [ ] Implement `PredictionTrackingService`
- [ ] Update audit logging to track API-Football selections
- [ ] Set up automated cleanup jobs (monthly)
- [ ] Build analytics dashboards
- [ ] Document API-Football caching strategy

---

**Document Status**: ✅ Analysis Complete - Ready for Implementation  
**Last Updated**: 2025-10-12  
**Version**: 2.0 (Revised Storage Strategy)  
**Author**: Development Team (Co-authored by Steph)

