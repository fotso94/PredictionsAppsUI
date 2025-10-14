# Analytics Schema - Quick Reference
## Soccer Predictions Platform

**Version**: 1.0  
**Created**: 2025-10-08  
**Schema**: analytics

---

## 📋 Overview

The **analytics schema** tracks performance metrics, user engagement, and system analytics across the Soccer Predictions Platform.

**Total Tables**: 13  
**Total Indexes**: 50+  
**Storage Estimate**: ~6 GB (Year 1)

---

## 📊 Tables Summary

### 1. user_analytics
**Purpose**: Aggregate user performance metrics  
**Relationship**: 1:1 with users.users  
**Key Fields**: total_predictions, accuracy_rate, roi_percentage, total_winnings

### 2. user_engagement_metrics
**Purpose**: Track user engagement over time  
**Relationship**: N:1 with users.users  
**Key Fields**: date, login_count, predictions_made, time_spent_minutes

### 3. user_activity_log
**Purpose**: Detailed user activity tracking  
**Relationship**: N:1 with users.users  
**Key Fields**: activity_type, activity_data, session_id, duration_seconds

### 4. prediction_analytics_summary
**Purpose**: Aggregate prediction performance  
**Relationship**: 1:1 with predictions.predictions  
**Key Fields**: accuracy_score, roi_percentage, view_count, engagement_score

### 5. prediction_performance_metrics
**Purpose**: Time-series prediction performance  
**Relationship**: N:1 with predictions.predictions  
**Key Fields**: date, accuracy, roi, views, engagement

### 6. expert_performance_metrics
**Purpose**: Expert user performance tracking  
**Relationship**: N:1 with users.expert_profiles  
**Key Fields**: period_start, period_end, total_predictions, accuracy_rate, roi

### 7. model_performance_comparison
**Purpose**: Compare ML model performance  
**Relationship**: N:1 with ml_models.ml_models  
**Key Fields**: comparison_date, accuracy, precision, recall, f1_score

### 8. league_analytics
**Purpose**: League-level statistics  
**Relationship**: N:1 with predictions.leagues  
**Key Fields**: total_matches, total_predictions, avg_accuracy, popular_markets

### 9. team_analytics
**Purpose**: Team-level statistics  
**Relationship**: N:1 with predictions.teams  
**Key Fields**: total_matches, win_rate, avg_goals_scored, form_rating

### 10. feature_usage_analytics
**Purpose**: Track feature adoption  
**Key Fields**: feature_name, usage_count, unique_users, avg_session_duration

### 11. api_usage_analytics
**Purpose**: API endpoint usage tracking  
**Key Fields**: endpoint, method, request_count, avg_response_time, error_rate

### 12. revenue_analytics
**Purpose**: Revenue and subscription metrics  
**Relationship**: N:1 with users.users  
**Key Fields**: date, subscription_revenue, transaction_amount, payment_method

### 13. error_analytics
**Purpose**: System error tracking  
**Key Fields**: error_type, error_message, occurrence_count, affected_users

---

## 🔑 Key Indexes

### High-Performance Indexes

```sql
-- User analytics lookup
CREATE UNIQUE INDEX uq_user_analytics_user_id
    ON analytics.user_analytics(user_id);

-- Prediction analytics lookup
CREATE UNIQUE INDEX uq_prediction_analytics_prediction_id
    ON analytics.prediction_analytics_summary(prediction_id);

-- Time-series queries
CREATE INDEX idx_user_engagement_date
    ON analytics.user_engagement_metrics(date DESC);

-- Performance ranking
CREATE INDEX idx_user_analytics_accuracy
    ON analytics.user_analytics(accuracy_rate DESC)
    WHERE total_predictions >= 10;
```

---

## 📈 Common Queries

### Top Performing Users
```sql
SELECT
    user_id,
    total_predictions,
    accuracy_rate,
    roi_percentage,
    total_winnings
FROM analytics.user_analytics
WHERE total_predictions >= 10
ORDER BY accuracy_rate DESC, roi_percentage DESC
LIMIT 10;
```

### User Engagement Trends
```sql
SELECT
    date,
    SUM(login_count) AS total_logins,
    SUM(predictions_made) AS total_predictions,
    AVG(time_spent_minutes) AS avg_time_spent
FROM analytics.user_engagement_metrics
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY date
ORDER BY date DESC;
```

### Expert Performance
```sql
SELECT
    expert_user_id,
    period_start,
    period_end,
    total_predictions,
    accuracy_rate,
    roi_percentage
FROM analytics.expert_performance_metrics
WHERE period_end >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY accuracy_rate DESC;
```

### Model Comparison
```sql
SELECT
    model_id,
    comparison_date,
    accuracy,
    precision,
    recall,
    f1_score
FROM analytics.model_performance_comparison
WHERE comparison_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY f1_score DESC;
```

---

## 🎯 Business Metrics

### User Metrics
- Total active users
- User retention rate
- Average predictions per user
- User accuracy distribution
- ROI distribution

### Prediction Metrics
- Total predictions made
- Prediction accuracy by source (ML, Expert, Admin)
- Prediction confidence distribution
- Most popular betting markets
- Prediction engagement (views, follows)

### Expert Metrics
- Expert accuracy ranking
- Expert ROI ranking
- Expert prediction volume
- Expert specialization performance
- Expert user growth

### System Metrics
- API response times
- Error rates by endpoint
- Feature adoption rates
- System uptime
- Database performance

### Revenue Metrics
- Monthly recurring revenue (MRR)
- Subscription conversion rate
- Average revenue per user (ARPU)
- Churn rate
- Lifetime value (LTV)

---

## 🔄 Data Refresh Strategy

### Real-Time Updates
- user_activity_log (on every action)
- api_usage_analytics (on every request)
- error_analytics (on every error)

### Hourly Updates
- user_engagement_metrics (aggregate hourly)
- prediction_performance_metrics (update hourly)

### Daily Updates
- user_analytics (aggregate daily)
- prediction_analytics_summary (aggregate daily)
- expert_performance_metrics (aggregate daily)
- league_analytics (aggregate daily)
- team_analytics (aggregate daily)

### Weekly Updates
- model_performance_comparison (compare weekly)
- feature_usage_analytics (aggregate weekly)

### Monthly Updates
- revenue_analytics (aggregate monthly)

---

## 📊 Storage Estimates

| Table | Rows (Year 1) | Size per Row | Total Size |
|-------|---------------|--------------|------------|
| user_analytics | 100,000 | 2 KB | 200 MB |
| user_engagement_metrics | 36,500,000 | 500 B | 18 GB |
| user_activity_log | 500,000,000 | 1 KB | 500 GB* |
| prediction_analytics_summary | 1,000,000 | 1.5 KB | 1.5 GB |
| prediction_performance_metrics | 365,000,000 | 500 B | 183 GB* |
| expert_performance_metrics | 36,500 | 1 KB | 37 MB |
| model_performance_comparison | 3,650 | 1 KB | 4 MB |
| league_analytics | 3,650 | 2 KB | 7 MB |
| team_analytics | 73,000 | 2 KB | 146 MB |
| feature_usage_analytics | 36,500 | 1 KB | 37 MB |
| api_usage_analytics | 365,000 | 1 KB | 365 MB |
| revenue_analytics | 1,200,000 | 1 KB | 1.2 GB |
| error_analytics | 365,000 | 1 KB | 365 MB |

**Note**: Tables marked with * should use partitioning for large datasets.

---

## 🛠️ Maintenance

### Partitioning Strategy

**Large tables** should be partitioned by date:

```sql
-- user_activity_log (partition by month)
CREATE TABLE analytics.user_activity_log_2025_01
    PARTITION OF analytics.user_activity_log
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

-- prediction_performance_metrics (partition by month)
CREATE TABLE analytics.prediction_performance_metrics_2025_01
    PARTITION OF analytics.prediction_performance_metrics
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

### Data Retention

| Table | Retention Period | Archive Strategy |
|-------|------------------|------------------|
| user_activity_log | 90 days | Archive to S3 |
| user_engagement_metrics | 2 years | Keep all |
| prediction_performance_metrics | 1 year | Archive to S3 |
| api_usage_analytics | 90 days | Archive to S3 |
| error_analytics | 90 days | Archive to S3 |
| All others | Indefinite | Keep all |

### Aggregation Jobs

**Daily Aggregation** (runs at 2 AM UTC):
```sql
-- Update user_analytics
INSERT INTO analytics.user_analytics (...)
SELECT ... FROM predictions.predictions
WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
ON CONFLICT (user_id) DO UPDATE SET ...;

-- Update prediction_analytics_summary
INSERT INTO analytics.prediction_analytics_summary (...)
SELECT ... FROM predictions.predictions
WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
ON CONFLICT (prediction_id) DO UPDATE SET ...;
```

---

## 🎯 Performance Optimization

### Materialized Views

**Top Users Leaderboard**:
```sql
CREATE MATERIALIZED VIEW analytics.top_users_leaderboard AS
SELECT
    user_id,
    total_predictions,
    accuracy_rate,
    roi_percentage,
    RANK() OVER (ORDER BY accuracy_rate DESC) AS accuracy_rank,
    RANK() OVER (ORDER BY roi_percentage DESC) AS roi_rank
FROM analytics.user_analytics
WHERE total_predictions >= 10;

-- Refresh daily
REFRESH MATERIALIZED VIEW CONCURRENTLY analytics.top_users_leaderboard;
```

### Caching Strategy

**Redis Cache** (DB 2: Expert tools cache):
- Top users leaderboard (TTL: 1 hour)
- Expert performance metrics (TTL: 1 hour)
- League analytics (TTL: 6 hours)
- Team analytics (TTL: 6 hours)

---

## 📚 Related Documentation

- [analytics-schema-er-diagram.md](./analytics-schema-er-diagram.md) - Complete ER diagram
- [INDEX_STRATEGY.md](./INDEX_STRATEGY.md) - Index definitions
- [TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md](./TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md) - Relationships

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Database Architecture Team

