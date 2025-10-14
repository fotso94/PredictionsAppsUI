# KAN-26: Storage Strategy & User Tracking Analysis

**Project**: Soccer Predictions Platform  
**Related Task**: KAN-26 - Multi-Source Prediction Priority System  
**Document Type**: Storage & Analytics Analysis  
**Date**: 2025-10-12  
**Author**: Augment Code (Co-authored by Steph)

---

## Table of Contents

1. [Storage Strategy Analysis](#storage-strategy-analysis)
2. [Storage Volume Estimates](#storage-volume-estimates)
3. [Alternative Storage Strategies](#alternative-storage-strategies)
4. [Data Retention Policies](#data-retention-policies)
5. [User Prediction Usage Tracking](#user-prediction-usage-tracking)
6. [Recommendations](#recommendations)

---

## Storage Strategy Analysis

### Current Recommendation: Store ALL Predictions

The main analysis document recommends storing ALL predictions from all sources. Let's evaluate this approach.

#### Benefits of Storing ALL Predictions

| Benefit | Business Value | Technical Value | Priority |
|---------|---------------|-----------------|----------|
| **Complete Audit Trail** | Legal compliance, dispute resolution | Full lifecycle tracking | HIGH |
| **A/B Testing** | Optimize prediction sources, improve accuracy | Compare source performance | HIGH |
| **Fallback Options** | Service continuity if expert prediction voided | Graceful degradation | MEDIUM |
| **Analytics & Insights** | Understand which sources perform best | Data-driven decisions | HIGH |
| **Transparency (Pro Tier)** | Premium feature differentiation | Multi-source comparison view | MEDIUM |
| **ML Training Data** | Improve future ML models | Historical prediction patterns | MEDIUM |
| **Expert Performance Tracking** | Quality control, expert verification | Accuracy metrics by source | HIGH |

**Total Value Score**: 7/7 benefits rated MEDIUM-HIGH priority

#### Drawbacks of Storing ALL Predictions

| Drawback | Impact | Severity | Mitigation Available? |
|----------|--------|----------|----------------------|
| **Storage Costs** | $200-500/month at scale | MEDIUM | ✅ Yes - Compression, archival |
| **Database Performance** | Slower queries with large datasets | MEDIUM | ✅ Yes - Indexes, partitioning |
| **Backup Costs** | Larger backup sizes, longer backup times | LOW | ✅ Yes - Incremental backups |
| **Query Complexity** | More complex queries to filter by priority | LOW | ✅ Yes - Indexed queries |
| **Data Management** | Need retention policies, cleanup jobs | LOW | ✅ Yes - Automated cleanup |

**Total Impact**: All drawbacks have available mitigations

### Storage Volume Estimates

#### Assumptions

**Per Prediction Record**:
- Base fields (UUIDs, timestamps, status): ~200 bytes
- Probabilities (3 × DECIMAL): ~24 bytes
- Confidence score: ~8 bytes
- Reasoning (TEXT, avg 500 chars): ~500 bytes
- Key factors (JSONB, avg 200 chars): ~200 bytes
- Metadata (JSONB): ~100 bytes
- **Total per prediction**: ~1,032 bytes ≈ **1 KB**

**Prediction Sources per Match**:
- Expert prediction: 0-1 (not all matches have expert predictions)
- LLM prediction: 0-1 (future, not all matches)
- API-Football prediction: 0-1 (most matches)
- ML baseline: 0-1 (legacy, being phased out)
- **Average**: 1.5 predictions per match (conservative estimate)

#### Scenario 1: Small Scale (1,000 matches/day)

```
Daily Storage:
- Matches: 1,000
- Predictions: 1,000 × 1.5 = 1,500 predictions/day
- Storage: 1,500 × 1 KB = 1.5 MB/day

Monthly Storage:
- 1.5 MB × 30 = 45 MB/month

Annual Storage:
- 45 MB × 12 = 540 MB/year

3-Year Storage (with retention):
- 540 MB × 3 = 1.62 GB
```

**Cost Estimate** (AWS RDS PostgreSQL):
- Storage: 1.62 GB × $0.115/GB = **$0.19/month**
- Backup: 1.62 GB × $0.095/GB = **$0.15/month**
- **Total**: **$0.34/month** (negligible)

#### Scenario 2: Medium Scale (5,000 matches/day)

```
Daily Storage:
- Matches: 5,000
- Predictions: 5,000 × 1.5 = 7,500 predictions/day
- Storage: 7,500 × 1 KB = 7.5 MB/day

Monthly Storage:
- 7.5 MB × 30 = 225 MB/month

Annual Storage:
- 225 MB × 12 = 2.7 GB/year

3-Year Storage (with retention):
- 2.7 GB × 3 = 8.1 GB
```

**Cost Estimate** (AWS RDS PostgreSQL):
- Storage: 8.1 GB × $0.115/GB = **$0.93/month**
- Backup: 8.1 GB × $0.095/GB = **$0.77/month**
- **Total**: **$1.70/month** (still negligible)

#### Scenario 3: Large Scale (20,000 matches/day)

```
Daily Storage:
- Matches: 20,000
- Predictions: 20,000 × 1.5 = 30,000 predictions/day
- Storage: 30,000 × 1 KB = 30 MB/day

Monthly Storage:
- 30 MB × 30 = 900 MB/month

Annual Storage:
- 900 MB × 12 = 10.8 GB/year

3-Year Storage (with retention):
- 10.8 GB × 3 = 32.4 GB
```

**Cost Estimate** (AWS RDS PostgreSQL):
- Storage: 32.4 GB × $0.115/GB = **$3.73/month**
- Backup: 32.4 GB × $0.095/GB = **$3.08/month**
- **Total**: **$6.81/month** (very affordable)

#### Scenario 4: Enterprise Scale (50,000 matches/day)

```
Daily Storage:
- Matches: 50,000
- Predictions: 50,000 × 1.5 = 75,000 predictions/day
- Storage: 75,000 × 1 KB = 75 MB/day

Monthly Storage:
- 75 MB × 30 = 2.25 GB/month

Annual Storage:
- 2.25 GB × 12 = 27 GB/year

3-Year Storage (with retention):
- 27 GB × 3 = 81 GB
```

**Cost Estimate** (AWS RDS PostgreSQL):
- Storage: 81 GB × $0.115/GB = **$9.32/month**
- Backup: 81 GB × $0.095/GB = **$7.70/month**
- **Total**: **$17.02/month** (still very affordable)

### Storage Cost Summary

| Scale | Matches/Day | Storage (3yr) | Monthly Cost | Annual Cost |
|-------|-------------|---------------|--------------|-------------|
| **Small** | 1,000 | 1.62 GB | $0.34 | $4.08 |
| **Medium** | 5,000 | 8.1 GB | $1.70 | $20.40 |
| **Large** | 20,000 | 32.4 GB | $6.81 | $81.72 |
| **Enterprise** | 50,000 | 81 GB | $17.02 | $204.24 |

**Key Insight**: Even at enterprise scale (50,000 matches/day), storage costs are **less than $20/month** - negligible compared to API costs ($200-800/month) and infrastructure costs ($1,000+/month).

---

## Alternative Storage Strategies

### Strategy 1: Store ALL Predictions (RECOMMENDED)

**Approach**: Store every prediction from every source.

**Pros**:
- ✅ Complete audit trail
- ✅ Full A/B testing capabilities
- ✅ Maximum transparency
- ✅ Best for analytics and ML training
- ✅ Supports all business requirements

**Cons**:
- ⚠️ Slightly higher storage costs (but negligible as shown above)
- ⚠️ More complex queries (mitigated by indexes)

**Recommendation**: **STRONGLY RECOMMENDED** - Storage costs are negligible, benefits are substantial.

### Strategy 2: Store Only Active Prediction + Audit Log

**Approach**: Store only the highest priority (active) prediction, log others in audit table.

**Pros**:
- ✅ Minimal storage footprint
- ✅ Simpler queries
- ✅ Still maintains audit trail

**Cons**:
- ❌ Cannot compare predictions side-by-side
- ❌ Difficult to implement A/B testing
- ❌ Pro tier multi-source view not possible
- ❌ Limited analytics capabilities

**Recommendation**: **NOT RECOMMENDED** - Savings are minimal ($5-10/month), but feature limitations are significant.

### Strategy 3: Tiered Storage (Hot/Warm/Cold)

**Approach**: 
- **Hot storage** (PostgreSQL): Recent predictions (last 30 days)
- **Warm storage** (PostgreSQL with compression): Predictions 30-365 days old
- **Cold storage** (S3 Glacier): Predictions >1 year old

**Pros**:
- ✅ Optimized query performance for recent data
- ✅ Reduced costs for historical data
- ✅ Still maintains complete history

**Cons**:
- ⚠️ More complex data management
- ⚠️ Requires data migration jobs
- ⚠️ Historical queries slower

**Recommendation**: **CONSIDER FOR FUTURE** - Implement when storage exceeds 100 GB (2-3 years at enterprise scale).

### Strategy 4: Hybrid Approach (Selective Storage)

**Approach**:
- Store ALL expert predictions (high value)
- Store ALL LLM predictions (medium value)
- Store ONLY USED API-Football predictions (low value)
- Don't store randomized defaults

**Pros**:
- ✅ Reduces storage of low-value predictions
- ✅ Maintains high-value audit trail
- ✅ Moderate storage savings

**Cons**:
- ❌ Incomplete audit trail
- ❌ Cannot analyze API-Football performance
- ❌ Complex logic to determine "used" predictions

**Recommendation**: **NOT RECOMMENDED** - Complexity outweighs minimal savings.

---

## Data Retention Policies

### Recommended Retention Policy

| Data Type | Retention Period | Storage Location | Rationale |
|-----------|------------------|------------------|-----------|
| **Active Predictions** | Indefinite | PostgreSQL (hot) | Ongoing matches, user access |
| **Settled Predictions** | 2 years | PostgreSQL (hot) | Analytics, performance tracking |
| **Historical Predictions** | 2-5 years | PostgreSQL (warm) | Long-term analytics, ML training |
| **Archived Predictions** | 5+ years | S3 Glacier (cold) | Compliance, historical reference |
| **Audit Logs** | 7 years | PostgreSQL + S3 | Legal compliance (SOX, GDPR) |
| **User Views/Feedback** | 1 year | PostgreSQL | Recent engagement metrics |

### Retention Implementation

```sql
-- Automated cleanup job (runs monthly)
CREATE OR REPLACE FUNCTION cleanup_old_predictions()
RETURNS void AS $$
BEGIN
    -- Archive predictions older than 5 years to S3
    -- (Implemented via application logic, not SQL)
    
    -- Delete randomized default predictions older than 30 days
    DELETE FROM predictions.predictions
    WHERE source = 'default_randomized'
      AND created_at < NOW() - INTERVAL '30 days'
      AND deleted_at IS NULL;
    
    -- Soft delete user views older than 1 year
    UPDATE analytics.user_prediction_views
    SET deleted_at = NOW()
    WHERE created_at < NOW() - INTERVAL '1 year'
      AND deleted_at IS NULL;
    
    -- Keep audit logs for 7 years (no deletion)
END;
$$ LANGUAGE plpgsql;
```

### Storage Optimization Techniques

1. **Compression**:
   - Enable PostgreSQL table compression for predictions older than 90 days
   - Estimated savings: 40-60% storage reduction

2. **Partitioning**:
   - Partition predictions table by month
   - Faster queries, easier archival

3. **Selective Indexing**:
   - Index only recent data (last 6 months)
   - Reduces index size by 50%+

4. **JSONB Optimization**:
   - Store only essential data in JSONB fields
   - Move verbose data to separate tables if needed

---

## User Prediction Usage Tracking

### 5.1 Metrics to Capture

#### Primary Metrics

| Metric | Description | Granularity | Storage Location |
|--------|-------------|-------------|------------------|
| **Prediction Views** | How many times a prediction was viewed | Per prediction | `analytics.user_prediction_views` |
| **Views by Tier** | Views segmented by subscription tier | Per tier | Aggregated in analytics |
| **Views by Source** | Which prediction source was shown | Per source | `analytics.prediction_source_views` (NEW) |
| **Active Prediction Selection** | Which prediction was selected by priority logic | Per match | `predictions.prediction_audit` |
| **Multi-Source Views** | Pro tier users viewing all sources | Per match | `analytics.user_prediction_views` |
| **Prediction Engagement** | Clicks, shares, feedback on predictions | Per prediction | `predictions.user_prediction_feedback` |

#### Secondary Metrics

| Metric | Description | Purpose |
|--------|-------------|---------|
| **Source Preference** | Which sources users engage with most | Optimize prediction generation |
| **Tier Conversion** | Users upgrading after seeing expert predictions | Measure feature value |
| **Prediction Accuracy by Source** | Win rate by source type | Quality control |
| **Cache Hit Rate by Source** | How often cached predictions are used | Performance optimization |
| **API Cost per View** | Cost efficiency of each prediction source | ROI analysis |

### 5.2 Tracking Implementation

#### New Table: `prediction_source_views`

```sql
CREATE TABLE analytics.prediction_source_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Match & Prediction
    match_id UUID NOT NULL REFERENCES predictions.matches(id),
    prediction_id UUID NOT NULL REFERENCES predictions.predictions(id),

    -- Source Information
    prediction_source VARCHAR(50) NOT NULL,  -- expert_manual, llm_generated, etc.
    priority_level INTEGER NOT NULL,
    is_active_prediction BOOLEAN NOT NULL,  -- Was this the highest priority shown?

    -- User Information
    user_id UUID REFERENCES users.users(id),
    user_tier VARCHAR(20) NOT NULL,  -- free, basic, premium, pro
    is_authenticated BOOLEAN NOT NULL,

    -- View Context
    view_type VARCHAR(20) NOT NULL,  -- single, multi_source, comparison
    device_type VARCHAR(20),  -- web, mobile, tablet

    -- Engagement
    view_duration_seconds INTEGER,  -- How long user viewed prediction
    engaged BOOLEAN DEFAULT FALSE,  -- Did user interact (click, share, feedback)?

    -- Metadata
    session_id VARCHAR(100),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW(),

    -- Indexes
    INDEX idx_source_views_match_id (match_id),
    INDEX idx_source_views_prediction_id (prediction_id),
    INDEX idx_source_views_source (prediction_source),
    INDEX idx_source_views_user_tier (user_tier),
    INDEX idx_source_views_created_at (created_at)
);
```

#### Tracking Service Implementation

```python
# backend/app/services/prediction_tracking.py

from typing import Optional
from sqlalchemy.orm import Session
from app.models.analytics import PredictionSourceView
from app.models.predictions import Prediction
from app.models.users import User

class PredictionTrackingService:
    """Service for tracking prediction views and usage"""

    def __init__(self, db: Session):
        self.db = db

    async def track_prediction_view(
        self,
        prediction: Prediction,
        user: Optional[User],
        view_context: dict
    ):
        """
        Track when a prediction is viewed by a user

        Args:
            prediction: Prediction being viewed
            user: User viewing prediction (None for anonymous)
            view_context: Additional context (device, session, etc.)
        """
        view_record = PredictionSourceView(
            match_id=prediction.match_id,
            prediction_id=prediction.id,
            prediction_source=prediction.source,
            priority_level=prediction.priority_level,
            is_active_prediction=view_context.get('is_active', True),
            user_id=user.id if user else None,
            user_tier=user.subscription_tier if user else 'free',
            is_authenticated=user is not None,
            view_type=view_context.get('view_type', 'single'),
            device_type=view_context.get('device_type'),
            session_id=view_context.get('session_id'),
            ip_address=view_context.get('ip_address'),
            user_agent=view_context.get('user_agent')
        )

        self.db.add(view_record)
        await self.db.commit()

    async def track_multi_source_view(
        self,
        match_id: str,
        predictions: list[Prediction],
        user: User,
        view_context: dict
    ):
        """
        Track when Pro tier user views all prediction sources

        Args:
            match_id: Match identifier
            predictions: All predictions for match
            user: Pro tier user
            view_context: Additional context
        """
        for i, prediction in enumerate(predictions):
            await self.track_prediction_view(
                prediction=prediction,
                user=user,
                view_context={
                    **view_context,
                    'view_type': 'multi_source',
                    'is_active': i == 0  # First is active (highest priority)
                }
            )

    async def get_source_performance_metrics(
        self,
        date_from: str,
        date_to: str
    ) -> dict:
        """
        Get performance metrics by prediction source

        Returns:
            Dictionary with metrics by source
        """
        from sqlalchemy import func

        metrics = self.db.query(
            PredictionSourceView.prediction_source,
            func.count(PredictionSourceView.id).label('total_views'),
            func.count(func.distinct(PredictionSourceView.user_id)).label('unique_users'),
            func.avg(PredictionSourceView.view_duration_seconds).label('avg_duration'),
            func.sum(
                func.cast(PredictionSourceView.engaged, Integer)
            ).label('engaged_views')
        ).filter(
            PredictionSourceView.created_at >= date_from,
            PredictionSourceView.created_at <= date_to
        ).group_by(
            PredictionSourceView.prediction_source
        ).all()

        return {
            metric.prediction_source: {
                'total_views': metric.total_views,
                'unique_users': metric.unique_users,
                'avg_duration_seconds': float(metric.avg_duration or 0),
                'engaged_views': metric.engaged_views,
                'engagement_rate': metric.engaged_views / metric.total_views if metric.total_views > 0 else 0
            }
            for metric in metrics
        }
```

### 5.3 Analytics Schema Integration

**Recommendation**: Use **existing analytics schema** with new table.

**Rationale**:
- ✅ Keeps analytics data centralized
- ✅ Easier to query across analytics tables
- ✅ Consistent with existing architecture
- ✅ Simpler backup/archival strategy

**Schema Structure**:
```
analytics schema
├── user_prediction_views (existing)
├── user_prediction_feedback (existing)
├── prediction_analytics (existing)
└── prediction_source_views (NEW)
```

---

### 5.4 Using Data to Optimize Predictions

#### Optimization Strategy 1: Source Prioritization

**Question**: Should we generate LLM predictions for all matches or only high-value ones?

**Data-Driven Answer**:
```sql
-- Identify which matches get the most views
SELECT
    m.league_id,
    l.name as league_name,
    COUNT(DISTINCT psv.user_id) as unique_viewers,
    COUNT(psv.id) as total_views,
    AVG(psv.view_duration_seconds) as avg_engagement
FROM analytics.prediction_source_views psv
JOIN predictions.matches m ON psv.match_id = m.id
JOIN predictions.leagues l ON m.league_id = l.id
WHERE psv.created_at >= NOW() - INTERVAL '30 days'
GROUP BY m.league_id, l.name
ORDER BY total_views DESC
LIMIT 20;
```

**Action**: Generate LLM predictions only for top 20 leagues (80/20 rule).

#### Optimization Strategy 2: Expert Assignment

**Question**: Which matches should we flag for expert review?

**Data-Driven Answer**:
```sql
-- Identify matches with high engagement but low confidence
SELECT
    m.id,
    m.home_team_id,
    m.away_team_id,
    p.confidence_score,
    COUNT(psv.id) as view_count,
    AVG(psv.view_duration_seconds) as avg_engagement
FROM predictions.predictions p
JOIN predictions.matches m ON p.match_id = m.id
JOIN analytics.prediction_source_views psv ON p.id = psv.prediction_id
WHERE p.source = 'api_football_baseline'
  AND p.confidence_score < 0.7
  AND psv.created_at >= NOW() - INTERVAL '7 days'
GROUP BY m.id, m.home_team_id, m.away_team_id, p.confidence_score
HAVING COUNT(psv.id) > 100  -- High engagement
ORDER BY view_count DESC;
```

**Action**: Flag these matches for expert review (high value, low confidence).

#### Optimization Strategy 3: Tier Conversion

**Question**: Do users upgrade after seeing expert predictions?

**Data-Driven Answer**:
```sql
-- Track tier upgrades after viewing expert predictions
SELECT
    u.subscription_tier as original_tier,
    COUNT(DISTINCT u.id) as users_who_viewed_expert,
    COUNT(DISTINCT CASE
        WHEN sh.new_tier IN ('premium', 'pro')
        THEN u.id
    END) as users_who_upgraded,
    COUNT(DISTINCT CASE
        WHEN sh.new_tier IN ('premium', 'pro')
        THEN u.id
    END)::FLOAT / COUNT(DISTINCT u.id) as conversion_rate
FROM users.users u
JOIN analytics.prediction_source_views psv ON u.id = psv.user_id
LEFT JOIN users.subscription_history sh ON u.id = sh.user_id
    AND sh.changed_at > psv.created_at
    AND sh.changed_at < psv.created_at + INTERVAL '7 days'
WHERE psv.prediction_source IN ('expert_manual', 'expert_override')
  AND psv.created_at >= NOW() - INTERVAL '90 days'
  AND u.subscription_tier IN ('free', 'basic')
GROUP BY u.subscription_tier;
```

**Action**: If conversion rate > 10%, invest more in expert predictions.

#### Optimization Strategy 4: Cost Efficiency

**Question**: What's the ROI of each prediction source?

**Data-Driven Answer**:
```sql
-- Calculate cost per view by source
WITH source_costs AS (
    SELECT
        'expert_manual' as source,
        500.00 as monthly_cost  -- Expert salaries, platform costs
    UNION ALL
    SELECT 'llm_generated', 200.00  -- LLM API costs
    UNION ALL
    SELECT 'api_football_baseline', 100.00  -- API-Football subscription
),
source_views AS (
    SELECT
        prediction_source,
        COUNT(id) as total_views,
        COUNT(DISTINCT user_id) as unique_users
    FROM analytics.prediction_source_views
    WHERE created_at >= NOW() - INTERVAL '30 days'
    GROUP BY prediction_source
)
SELECT
    sv.prediction_source,
    sc.monthly_cost,
    sv.total_views,
    sv.unique_users,
    sc.monthly_cost / sv.total_views as cost_per_view,
    sc.monthly_cost / sv.unique_users as cost_per_user
FROM source_views sv
JOIN source_costs sc ON sv.prediction_source = sc.source
ORDER BY cost_per_view;
```

**Action**: Optimize budget allocation based on cost per view.

---

## Recommendations

### Storage Strategy: FINAL RECOMMENDATION

**✅ RECOMMENDED: Store ALL Predictions**

**Rationale**:
1. **Negligible Cost**: Even at enterprise scale (50,000 matches/day), storage costs are <$20/month
2. **High Business Value**: Complete audit trail, A/B testing, analytics, transparency
3. **Future-Proof**: Supports all planned features (Pro tier multi-source view, ML training)
4. **Risk Mitigation**: Fallback options if higher priority predictions are voided

**Implementation**:
- Store all predictions in PostgreSQL (hot storage)
- Implement 2-year retention in hot storage
- Archive to S3 Glacier after 2 years
- Delete randomized defaults after 30 days
- Enable table compression for predictions >90 days old

**Cost Projection** (3-year horizon):
- Year 1 (5,000 matches/day): $1.70/month = $20.40/year
- Year 2 (15,000 matches/day): $5.10/month = $61.20/year
- Year 3 (30,000 matches/day): $10.20/month = $122.40/year
- **Total 3-year cost**: $204.00 (less than one month of API costs)

### User Tracking: FINAL RECOMMENDATION

**✅ RECOMMENDED: Comprehensive Tracking with Analytics Schema**

**Implementation**:
1. Create `analytics.prediction_source_views` table
2. Track every prediction view with source, tier, engagement
3. Implement `PredictionTrackingService` for centralized tracking
4. Build analytics dashboards for source performance
5. Use data to optimize prediction generation and expert assignment

**Key Metrics to Monitor**:
- Views by source (Expert vs LLM vs API-Football)
- Engagement rate by source
- Tier conversion rate after viewing expert predictions
- Cost per view by source
- Expert prediction ROI

**Data Retention**:
- Keep view data for 1 year in hot storage
- Archive to S3 after 1 year
- Aggregate metrics stored indefinitely

### Data Retention: FINAL RECOMMENDATION

| Data Type | Retention | Storage | Cost Impact |
|-----------|-----------|---------|-------------|
| **Active Predictions** | Indefinite | PostgreSQL | Minimal |
| **Settled Predictions** | 2 years | PostgreSQL | $5-10/month |
| **Historical Predictions** | 2-5 years | PostgreSQL (compressed) | $2-5/month |
| **Archived Predictions** | 5+ years | S3 Glacier | $0.50/month |
| **Audit Logs** | 7 years | PostgreSQL + S3 | $1-2/month |
| **User Views** | 1 year | PostgreSQL | $1-2/month |

**Total Estimated Cost**: $10-20/month at enterprise scale

---

## Conclusion

### Storage Strategy

The analysis clearly shows that **storing ALL predictions is the optimal strategy**:

1. **Cost is negligible**: <$20/month even at enterprise scale
2. **Benefits are substantial**: Audit trail, analytics, A/B testing, transparency
3. **Future-proof**: Supports all planned features
4. **Risk mitigation**: Fallback options and quality control

**Alternative strategies save minimal costs ($5-10/month) but sacrifice critical features.**

### User Tracking

Comprehensive tracking provides **data-driven insights** for:

1. **Optimization**: Which predictions to generate/store
2. **ROI Analysis**: Cost efficiency by source
3. **Feature Validation**: Do expert predictions drive upgrades?
4. **Quality Control**: Which sources perform best?

**Recommendation**: Implement full tracking from day one to inform future decisions.

### Next Steps

1. ✅ Approve storage strategy: Store ALL predictions
2. ✅ Implement `analytics.prediction_source_views` table
3. ✅ Build `PredictionTrackingService`
4. ✅ Set up retention policies and automated cleanup
5. ✅ Create analytics dashboards for monitoring
6. ✅ Review metrics monthly to optimize prediction generation

---

**Document Status**: ✅ Analysis Complete
**Last Updated**: 2025-10-12
**Version**: 1.0
**Author**: Augment Code (Co-authored by Steph)

---

*This document supplements the main KAN-26 analysis with detailed storage and tracking recommendations.*
