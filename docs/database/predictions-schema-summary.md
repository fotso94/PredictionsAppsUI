# Predictions Schema - Quick Reference Summary
## Soccer Predictions Platform

**Jira Task**: KAN-93  
**Status**: ✅ Complete - Ready for Review  
**Last Updated**: 2025-10-08

---

## Schema Overview

The **predictions** schema contains **16 tables** organized into 4 functional groups:

| Group | Tables | Purpose |
|-------|--------|---------|
| **Core Predictions** | 5 tables | Predictions, overrides, audit, results, markets |
| **Match Data** | 3 tables | Matches, results, statistics |
| **Analytics & Engagement** | 3 tables | Analytics, views, feedback |
| **Reference Data** | 3 tables | Leagues, teams, templates |

---

## Table Summary

### Core Prediction Tables (5 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 1 | `predictions` | 500K+ | All predictions (ML, Expert, Admin) | → matches, users, expert_profiles, ml_predictions |
| 2 | `prediction_markets` | 2M+ | Multiple markets per prediction | ← predictions (1:many) |
| 3 | `prediction_overrides` | 50K+ | Expert/Admin overrides | ← predictions (1:1 optional) |
| 4 | `prediction_audit` | 2M+ | Prediction lifecycle audit trail | ← predictions (1:many) |
| 5 | `prediction_results` | 400K+ | Settled prediction outcomes | ← predictions (1:1 optional) |

### Match Data Tables (3 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 6 | `matches` | 100K+ | Match data from external APIs | → leagues, teams |
| 7 | `match_results` | 80K+ | Final match results | ← matches (1:1 optional) |
| 8 | `match_statistics` | 300K+ | Pre-match, live, post-match stats | ← matches (1:many) |

### Analytics & Engagement Tables (3 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 9 | `prediction_analytics` | 1M+ | Aggregated performance metrics | ← predictions (1:many) |
| 10 | `user_prediction_views` | 5M+ | User engagement tracking | ← predictions, users (1:many) |
| 11 | `user_prediction_feedback` | 200K+ | User ratings and feedback | ← predictions, users (1:many) |

### Reference Data Tables (3 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 12 | `leagues` | 100-200 | League/competition reference | → matches (1:many) |
| 13 | `teams` | 1K-2K | Team reference data | → matches (1:many) |
| 14 | `prediction_templates` | 20-50 | Reusable prediction templates | → predictions (1:many) |

**Note**: Row estimates are for production scale after 1 year of operation.

---

## Relationship Types

### One-to-One (1:1)
- `predictions` → `prediction_overrides` (optional)
- `predictions` → `prediction_results` (optional)
- `matches` → `match_results` (optional)

### One-to-Many (1:N)
- `predictions` → `prediction_markets`
- `predictions` → `prediction_audit`
- `predictions` → `prediction_analytics`
- `predictions` → `user_prediction_views`
- `predictions` → `user_prediction_feedback`
- `matches` → `predictions`
- `matches` → `match_statistics`
- `leagues` → `matches`
- `teams` → `matches` (as home_team and away_team)
- `prediction_templates` → `predictions`

### Cross-Schema Relationships
- `predictions` → `users.users` (created_by, approved_by)
- `predictions` → `users.expert_profiles`
- `predictions` → `ml_models.ml_predictions`
- `prediction_overrides` → `users.users` (expert_user, reviewed_by_admin)
- `prediction_overrides` → `users.expert_profiles`
- `prediction_audit` → `users.users`
- `prediction_analytics` → `users.expert_profiles`
- `user_prediction_views` → `users.users`
- `user_prediction_feedback` → `users.users`

---

## Key Features

### 🎯 Hybrid Prediction System
- ✅ ML baseline predictions (automated)
- ✅ Expert review and override capabilities
- ✅ Admin approval for high-stakes predictions
- ✅ Complete audit trail of prediction sources
- ✅ Confidence tracking (ML vs final)

### 📊 Multiple Betting Markets
- ✅ 1X2 (Home/Draw/Away)
- ✅ Both Teams to Score (BTTS)
- ✅ Over/Under Goals
- ✅ Correct Score
- ✅ Double Chance
- ✅ Handicap/Asian Handicap
- ✅ Multiple markets per prediction

### 🔐 Access Control
- ✅ Subscription-based access (Free, Basic, Premium, Pro)
- ✅ Featured predictions
- ✅ Admin approval workflow
- ✅ Prediction expiration (match start time)

### 📈 Analytics & Tracking
- ✅ Performance metrics by source (ML, Expert, Admin)
- ✅ Performance metrics by market type
- ✅ Performance metrics by league
- ✅ Expert performance tracking
- ✅ User engagement tracking (views, duration)
- ✅ User feedback and ratings

### ⚽ Match Data Integration
- ✅ External API synchronization (API-Football, TheSportsDB)
- ✅ Match status tracking (scheduled, live, finished)
- ✅ Real-time match statistics
- ✅ Historical head-to-head data
- ✅ Team form and injury reports

---

## Data Types Used

| PostgreSQL Type | Usage | Examples |
|-----------------|-------|----------|
| `uuid` | All primary keys, foreign keys | `id`, `match_id`, `user_id` |
| `varchar` | Short text fields | `selection`, `template_name`, `season` |
| `text` | Long text fields | `analysis`, `override_reason`, `settlement_notes` |
| `enum` | Fixed value sets | `source_type`, `prediction_status`, `market_type` |
| `boolean` | True/false flags | `is_featured`, `is_correct`, `admin_reviewed` |
| `integer` | Counts, scores | `view_count`, `home_score`, `total_goals` |
| `decimal` | Percentages, odds, money | `confidence`, `odds`, `profit_loss`, `roi` |
| `timestamp` | Date and time | `created_at`, `published_at`, `expires_at` |
| `date` | Date only | `analytics_date` |
| `inet` | IP addresses | `ip_address` |
| `jsonb` | Flexible structured data | `key_factors`, `match_metadata`, `detailed_stats` |

---

## Index Strategy

### Total Indexes: ~100 indexes

| Index Type | Count | Purpose |
|------------|-------|---------|
| Primary Key | 16 | Unique row identification |
| Unique | 6 | Enforce uniqueness (prediction_id, match_id, external_api_id) |
| Foreign Key | 30 | Improve join performance |
| Query Optimization | 35 | Support common WHERE/ORDER BY clauses |
| JSONB GIN | 13 | Enable JSONB queries |
| Composite | 10 | Multi-column query optimization |

---

## Enum Types (11 enums)

| Enum Name | Values | Used In |
|-----------|--------|---------|
| `source_type` | ml_baseline, expert_created, expert_override, admin_created, admin_override | `predictions.source_type`, `prediction_analytics.source_type` |
| `prediction_status` | draft, pending_review, approved, published, settled, void, cancelled | `predictions.prediction_status` |
| `primary_market` | 1x2, btts, over_under, correct_score, double_chance, handicap | `predictions.primary_market` |
| `confidence_level` | low, medium, high, very_high | `predictions.confidence_level` |
| `subscription_tier_required` | free, basic, premium, pro | `predictions.subscription_tier_required` |
| `override_type` | confidence_adjustment, market_change, full_override | `prediction_overrides.override_type` |
| `action_type` | created, updated, overridden, approved, published, settled, voided | `prediction_audit.action_type` |
| `actor_type` | ml_system, expert_user, admin_user, system | `prediction_audit.actor_type` |
| `outcome` | won, lost, void, push, cancelled | `prediction_results.outcome` |
| `market_type` | 1x2, btts, over_under, correct_score, double_chance, handicap, asian_handicap | `prediction_markets.market_type`, `prediction_analytics.market_type` |
| `match_status` | scheduled, live, halftime, finished, postponed, cancelled | `matches.match_status` |
| `result_type` | home_win, draw, away_win | `match_results.result_type` |
| `stat_type` | pre_match, live, post_match | `match_statistics.stat_type` |
| `view_source` | web, mobile, api | `user_prediction_views.view_source` |
| `feedback_type` | helpful, not_helpful, inaccurate, excellent | `user_prediction_feedback.feedback_type` |
| `league_tier` | tier_1, tier_2, tier_3 | `leagues.league_tier` |

---

## JSONB Fields (13 fields)

| Table | Field | Purpose | Example Structure |
|-------|-------|---------|-------------------|
| `predictions` | `key_factors` | Factors influencing prediction | `["Home form", "Injuries", "H2H record"]` |
| `prediction_overrides` | `changes_made` | Before/after values | `{"confidence": {"before": 65, "after": 75}}` |
| `prediction_audit` | `action_details` | Action context | `{"action": "published", "reason": "..."}` |
| `prediction_audit` | `changes_made` | Field changes | `{"before": {...}, "after": {...}}` |
| `prediction_markets` | `market_data` | Market-specific data | `{"handicap": -1.5, "asian": true}` |
| `prediction_analytics` | `performance_metrics` | Additional metrics | `{"by_league": {...}, "by_confidence": {...}}` |
| `matches` | `match_metadata` | Additional match data | `{"attendance": 50000, "weather": "clear"}` |
| `match_results` | `detailed_stats` | Comprehensive stats | `{"goals": [...], "cards": [...], "corners": 12}` |
| `match_statistics` | `team_form` | Recent form | `{"home": ["W", "W", "D"], "away": ["L", "W", "D"]}` |
| `match_statistics` | `head_to_head` | H2H data | `{"last_5": [...], "home_wins": 3}` |
| `match_statistics` | `injuries` | Injury reports | `[{"player": "...", "status": "out"}]` |
| `match_statistics` | `lineups` | Team lineups | `{"home": {...}, "away": {...}}` |
| `match_statistics` | `live_stats` | Live statistics | `{"possession": {"home": 55, "away": 45}}` |
| `teams` | `team_colors` | Team colors | `{"primary": "#FF0000", "secondary": "#FFFFFF"}` |
| `prediction_templates` | `default_factors` | Default factors | `["Recent form", "Home advantage"]` |

---

## Constraints Summary

### Check Constraints (~30 constraints)
- Confidence ranges (0-100%)
- Confidence level consistency with confidence score
- Subscription tier validation
- Override reason minimum length (20 characters)
- Confidence adjustment limits (±30%)
- Match scores non-negative
- Halftime scores ≤ full-time scores
- Total goals consistency
- Both teams scored consistency
- Rating range (1-5 stars)
- Odds must be positive
- Probability range (0-100%)
- Season format validation
- Approval consistency
- Publish approval workflow

### Foreign Key Constraints (~30 constraints)
- All `match_id` references → `matches(id)`
- All `prediction_id` references → `predictions(id)`
- All `user_id` references → `users.users(id)`
- All `expert_profile_id` references → `users.expert_profiles(id)`
- All `ml_prediction_id` references → `ml_models.ml_predictions(id)`
- All `league_id` references → `leagues(id)`
- All `team_id` references → `teams(id)`

### Unique Constraints (~6 constraints)
- `prediction_results.prediction_id`
- `match_results.match_id`
- `prediction_overrides.prediction_id`
- `leagues.external_api_id`
- `teams.external_api_id`
- `prediction_markets(prediction_id)` WHERE `is_primary = true`
- `user_prediction_feedback(prediction_id, user_id)`

---

## Storage Estimates

### Year 1 Projections

| Table | Rows | Avg Row Size | Total Size |
|-------|------|--------------|------------|
| `predictions` | 500K | 800 bytes | ~400 MB |
| `prediction_markets` | 2M | 300 bytes | ~600 MB |
| `prediction_overrides` | 50K | 600 bytes | ~30 MB |
| `prediction_audit` | 2M | 400 bytes | ~800 MB |
| `prediction_results` | 400K | 350 bytes | ~140 MB |
| `matches` | 100K | 500 bytes | ~50 MB |
| `match_results` | 80K | 400 bytes | ~32 MB |
| `match_statistics` | 300K | 600 bytes | ~180 MB |
| `prediction_analytics` | 1M | 350 bytes | ~350 MB |
| `user_prediction_views` | 5M | 250 bytes | ~1.25 GB |
| `user_prediction_feedback` | 200K | 300 bytes | ~60 MB |
| `leagues` | 200 | 400 bytes | ~80 KB |
| `teams` | 2K | 400 bytes | ~800 KB |
| `prediction_templates` | 50 | 500 bytes | ~25 KB |
| **Total (predictions schema)** | | | **~3.9 GB** |

**Note**: Includes indexes (~2x data size), so total storage: **~12 GB** for predictions schema in Year 1.

---

## Performance Considerations

### Query Patterns Optimized For:
- ✅ Predictions by match (match_id lookup)
- ✅ Predictions by source type (ML, Expert, Admin)
- ✅ Predictions by status (published, settled)
- ✅ Predictions by subscription tier
- ✅ Featured predictions
- ✅ Expert predictions (expert_profile_id)
- ✅ Prediction accuracy by source/market/league
- ✅ User engagement metrics
- ✅ Match schedule (league, datetime)
- ✅ Match results lookup

### Potential Bottlenecks:
- ⚠️ `user_prediction_views` - Very high write volume (consider partitioning by month)
- ⚠️ `prediction_audit` - High write volume (consider partitioning by month)
- ⚠️ `prediction_analytics` - Time-series data (consider partitioning by date)
- ⚠️ `match_statistics` - Frequent updates during live matches

### Optimization Strategies:
- 📊 Partition `user_prediction_views` by month
- 📊 Partition `prediction_audit` by month
- 📊 Partition `prediction_analytics` by analytics_date
- 📊 Use read replicas for analytics queries
- 📊 Cache frequently accessed predictions (Redis)
- 📊 Implement connection pooling (asyncpg)
- 📊 Archive settled predictions older than 1 year

---

## Hybrid Prediction Workflow

### ML Baseline → Expert Review → Admin Approval → Published

1. **ML Baseline Creation**:
   - ML model generates prediction for upcoming match
   - `source_type = 'ml_baseline'`
   - `prediction_status = 'pending_review'`
   - `ml_confidence` set by ML model

2. **Expert Review** (Optional):
   - Expert reviews ML prediction
   - Expert can adjust confidence or fully override
   - Creates `prediction_override` record with reasoning
   - `source_type` changes to `'expert_override'`
   - `final_confidence` updated

3. **Admin Approval** (If Required):
   - High-stakes predictions require admin approval
   - Admin reviews prediction and override (if any)
   - `approved_by_admin_id` and `approved_at` set
   - `prediction_status = 'approved'`

4. **Publication**:
   - Prediction published to users based on subscription tier
   - `prediction_status = 'published'`
   - `published_at` timestamp set
   - Visible to users with appropriate subscription

5. **Settlement**:
   - Match completes and result is recorded
   - Prediction outcome calculated
   - `prediction_results` record created
   - `prediction_status = 'settled'`
   - Analytics updated

---

## Next Steps

1. ✅ **Review ER diagram** - Stakeholder approval
2. 🔄 **Create Alembic migrations** (KAN-16)
3. 🔄 **Implement SQLAlchemy models** (KAN-18)
4. 🔄 **Write unit tests** for constraints
5. 🔄 **Create seed data** (KAN-20)
6. 🔄 **API integration** for match data sync
7. 🔄 **Performance testing** with realistic data volumes

---

## Related Documentation

- **Detailed ER Diagram**: [predictions-schema-er-diagram.md](./predictions-schema-er-diagram.md)
- **Database Overview**: [README.md](./README.md)
- **Users Schema**: [users-schema-er-diagram.md](./users-schema-er-diagram.md)
- **Architecture Plans**:
  - `AWS_PRODUCTION_DEPLOYMENT_PLAN.md`
  - `LOCAL_DEVELOPMENT_ARCHITECTURE_PLAN.md`
  - `FRONTEND_ARCHITECTURE_ANALYSIS.md`

---

**Status**: ✅ Ready for Implementation  
**Jira Task**: KAN-93 (Complete)  
**Next Task**: KAN-94 (ML Models Schema ER Diagram)

