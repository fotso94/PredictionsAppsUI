# Table Relationships and Constraints Documentation
## Soccer Predictions Platform - Complete Relationship Mapping

**Version**: 1.0  
**Created**: 2025-10-08  
**Jira Task**: KAN-95 - Document all table relationships and constraints

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Cross-Schema Relationships](#cross-schema-relationships)
3. [Intra-Schema Relationships](#intra-schema-relationships)
4. [Constraint Types](#constraint-types)
5. [Referential Integrity Rules](#referential-integrity-rules)
6. [Cascade Behaviors](#cascade-behaviors)

---

## 🎯 Overview

This document provides a comprehensive mapping of all table relationships and constraints across the 5-schema database architecture for the Soccer Predictions Platform.

### Database Statistics

- **Total Schemas**: 5 (users, predictions, ml_models, analytics, audit)
- **Total Tables**: 66
- **Cross-Schema Relationships**: 33
- **Intra-Schema Relationships**: 85+
- **Total Foreign Keys**: 118+
- **Check Constraints**: 80+
- **Unique Constraints**: 50+

---

## 🔗 Cross-Schema Relationships

### Overview

Cross-schema relationships connect tables across different schemas, enabling data integrity while maintaining logical separation.

### 1. Users Schema → Other Schemas

#### users.users → predictions Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| users.users | id | predictions.predictions | created_by_user_id | 1:N | SET NULL |
| users.users | id | predictions.predictions | expert_user_id | 1:N | SET NULL |
| users.users | id | predictions.predictions | admin_user_id | 1:N | SET NULL |
| users.users | id | predictions.prediction_overrides | user_id | 1:N | CASCADE |
| users.users | id | predictions.user_predictions | user_id | 1:N | CASCADE |

**Business Rules:**
- Users can create multiple predictions
- Expert users can review/override predictions
- Admin users can approve/publish predictions
- User predictions are deleted when user is deleted (GDPR compliance)

#### users.users → ml_models Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| users.users | id | ml_models.ml_models | created_by_user_id | 1:N | SET NULL |
| users.users | id | ml_models.ml_training_runs | triggered_by_user_id | 1:N | SET NULL |
| users.users | id | ml_models.ml_ab_tests | created_by_user_id | 1:N | SET NULL |

**Business Rules:**
- ML models track who created them
- Training runs track who triggered them
- A/B tests track who created them
- Model metadata preserved even if user deleted

#### users.users → analytics Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| users.users | id | analytics.user_analytics | user_id | 1:1 | CASCADE |
| users.users | id | analytics.user_engagement_metrics | user_id | 1:N | CASCADE |
| users.users | id | analytics.user_activity_log | user_id | 1:N | CASCADE |
| users.users | id | analytics.revenue_analytics | user_id | 1:N | CASCADE |

**Business Rules:**
- Each user has one analytics record
- User analytics deleted with user (GDPR compliance)
- Activity logs deleted with user
- Revenue analytics deleted with user

#### users.users → audit Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| users.users | id | audit.audit_log | user_id | 1:N | SET NULL |
| users.users | id | audit.data_access_log | user_id | 1:N | SET NULL |
| users.users | id | audit.user_action_log | user_id | 1:N | SET NULL |
| users.users | id | audit.admin_action_log | admin_user_id | 1:N | SET NULL |

**Business Rules:**
- Audit logs preserved even if user deleted
- SET NULL maintains audit trail integrity
- Immutable audit logs for compliance

#### users.expert_profiles → predictions Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| users.expert_profiles | user_id | predictions.predictions | expert_user_id | 1:N | SET NULL |
| users.expert_profiles | user_id | predictions.prediction_overrides | expert_user_id | 1:N | SET NULL |

**Business Rules:**
- Expert profiles linked to predictions
- Expert overrides tracked
- Predictions preserved if expert profile deleted

#### users.admin_profiles → predictions Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| users.admin_profiles | user_id | predictions.predictions | admin_user_id | 1:N | SET NULL |
| users.admin_profiles | user_id | predictions.prediction_overrides | admin_user_id | 1:N | SET NULL |

**Business Rules:**
- Admin profiles linked to predictions
- Admin approvals tracked
- Predictions preserved if admin profile deleted

### 2. Predictions Schema → Other Schemas

#### predictions.predictions → ml_models Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| predictions.predictions | ml_prediction_id | ml_models.ml_predictions | id | N:1 | SET NULL |
| predictions.matches | id | ml_models.ml_predictions | match_id | 1:N | CASCADE |

**Business Rules:**
- Predictions can reference ML baseline predictions
- ML predictions linked to matches
- ML predictions deleted when match deleted

#### predictions.predictions → analytics Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| predictions.predictions | id | analytics.prediction_analytics_summary | prediction_id | 1:1 | CASCADE |
| predictions.predictions | id | analytics.prediction_performance_metrics | prediction_id | 1:N | CASCADE |

**Business Rules:**
- Each prediction has analytics summary
- Performance metrics tracked per prediction
- Analytics deleted with prediction

#### predictions.matches → analytics Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| predictions.matches | id | analytics.prediction_analytics_summary | match_id | 1:N | CASCADE |

**Business Rules:**
- Match analytics tracked
- Analytics deleted when match deleted

### 3. ML Models Schema → Other Schemas

#### ml_models.ml_models → analytics Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| ml_models.ml_models | id | analytics.model_performance_comparison | model_id | 1:N | CASCADE |

**Business Rules:**
- Model performance tracked in analytics
- Performance data deleted with model

#### ml_models.ml_predictions → audit Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| ml_models.ml_predictions | id | audit.prediction_change_log | ml_prediction_id | 1:N | SET NULL |

**Business Rules:**
- ML prediction changes audited
- Audit log preserved even if prediction deleted

### 4. Analytics Schema → Audit Schema

| Source Table | Source Column | Target Table | Target Column | Relationship | On Delete |
|--------------|---------------|--------------|---------------|--------------|-----------|
| analytics.user_analytics | user_id | audit.data_access_log | user_id | 1:N | SET NULL |

**Business Rules:**
- User analytics access logged
- Access logs preserved for compliance

---

## 🔄 Intra-Schema Relationships

### Users Schema (17 tables, 25+ relationships)

#### Core User Relationships

```
users
├── expert_profiles (1:1, CASCADE)
├── admin_profiles (1:1, CASCADE)
├── user_sessions (1:N, CASCADE)
├── refresh_tokens (1:N, CASCADE)
├── user_subscriptions (1:N, CASCADE)
├── user_preferences (1:1, CASCADE)
├── user_notifications (1:N, CASCADE)
└── notification_preferences (1:1, CASCADE)
```

#### RBAC Relationships

```
users
└── user_roles (N:N via junction table)
    └── roles
        └── role_permissions (N:N via junction table)
            └── permissions
```

#### Expert Relationships

```
expert_profiles
├── expert_specialties (1:N, CASCADE)
└── expert_permissions (1:N, CASCADE)
```

#### Admin Relationships

```
admin_profiles
└── admin_permissions (1:N, CASCADE)
```

#### Subscription Relationships

```
subscription_tiers
└── user_subscriptions (1:N, RESTRICT)
    └── users (N:1)
```

### Predictions Schema (16 tables, 30+ relationships)

#### Core Prediction Relationships

```
predictions
├── prediction_overrides (1:N, CASCADE)
├── prediction_audit (1:N, CASCADE)
├── prediction_results (1:1, CASCADE)
└── prediction_analytics (1:1, CASCADE)
```

#### Match Relationships

```
matches
├── predictions (1:N, CASCADE)
├── match_statistics (1:1, CASCADE)
├── head_to_head (1:N, CASCADE)
├── form_guide (1:N, CASCADE)
├── injury_news (1:N, CASCADE)
└── weather_data (1:1, CASCADE)
```

#### League/Team Relationships

```
leagues
└── seasons (1:N, CASCADE)
    └── matches (1:N, CASCADE)

teams
├── home_matches (1:N, CASCADE)
├── away_matches (1:N, CASCADE)
└── team_statistics (1:N, CASCADE)
```

#### Betting Market Relationships

```
betting_markets
└── predictions (1:N, RESTRICT)
```

### ML Models Schema (12 tables, 20+ relationships)

#### Model Versioning

```
ml_models
├── ml_model_versions (1:N, CASCADE)
├── ml_predictions (1:N, CASCADE)
├── ml_training_runs (1:N, CASCADE)
└── ml_deployment_history (1:N, CASCADE)
```

#### Training Relationships

```
ml_training_runs
├── ml_training_data (1:N, CASCADE)
├── ml_feature_importance (1:N, CASCADE)
├── ml_hyperparameters (1:N, CASCADE)
└── ml_metrics (1:N, CASCADE)
```

#### A/B Testing Relationships

```
ml_ab_tests
└── ml_champion_models (1:N, CASCADE)
    └── ml_model_registry (1:N, CASCADE)
```

### Analytics Schema (13 tables, 15+ relationships)

#### User Analytics

```
user_analytics
├── user_engagement_metrics (1:N, CASCADE)
└── user_activity_log (1:N, CASCADE)
```

#### Prediction Analytics

```
prediction_analytics_summary
└── prediction_performance_metrics (1:N, CASCADE)
```

#### Expert Analytics

```
expert_performance_metrics
└── prediction_analytics_summary (N:1)
```

#### System Analytics

```
feature_usage_analytics
├── api_usage_analytics (1:N, CASCADE)
└── error_analytics (1:N, CASCADE)
```

### Audit Schema (8 tables, 10+ relationships)

#### Audit Log Hierarchy

```
audit_log (parent table)
├── data_access_log (specialized)
├── prediction_change_log (specialized)
├── user_action_log (specialized)
├── admin_action_log (specialized)
└── system_event_log (specialized)
```

#### GDPR Compliance

```
gdpr_consent_log
└── data_export_log (1:N, CASCADE)
```

---

## 🛡️ Constraint Types

### 1. Primary Key Constraints

**All tables** use UUID primary keys:

```sql
id UUID PRIMARY KEY DEFAULT uuid_generate_v4()
```

**Benefits:**
- Prevents enumeration attacks
- Supports distributed systems
- Globally unique identifiers

### 2. Foreign Key Constraints

**Total**: 118+ foreign key constraints

**Naming Convention:**
```sql
CONSTRAINT fk_{source_table}_{target_table}_{column}
```

**Example:**
```sql
CONSTRAINT fk_predictions_users_created_by
    FOREIGN KEY (created_by_user_id)
    REFERENCES users.users(id)
    ON DELETE SET NULL
```

### 3. Unique Constraints

**Total**: 50+ unique constraints

**Examples:**

```sql
-- users.users
CONSTRAINT uq_users_email UNIQUE (email)
CONSTRAINT uq_users_username UNIQUE (username)

-- predictions.predictions
CONSTRAINT uq_predictions_match_market UNIQUE (match_id, betting_market_id)

-- ml_models.ml_models
CONSTRAINT uq_ml_models_name_version UNIQUE (name, version)
```

### 4. Check Constraints

**Total**: 80+ check constraints

**Categories:**

#### Value Range Constraints
```sql
-- Confidence must be between 0 and 1
CONSTRAINT chk_predictions_confidence
    CHECK (confidence >= 0 AND confidence <= 1)

-- Odds must be positive
CONSTRAINT chk_predictions_odds
    CHECK (odds > 0)
```

#### Enum Constraints
```sql
-- Prediction source validation
CONSTRAINT chk_predictions_source
    CHECK (source IN ('ml_baseline', 'expert_created', 'expert_override', 'admin_created', 'admin_override'))

-- Status validation
CONSTRAINT chk_predictions_status
    CHECK (status IN ('draft', 'pending_review', 'approved', 'published', 'settled', 'void', 'cancelled'))
```

#### Date/Time Constraints
```sql
-- Match date must be in the future
CONSTRAINT chk_matches_future_date
    CHECK (match_date > CURRENT_TIMESTAMP)

-- End date must be after start date
CONSTRAINT chk_seasons_date_range
    CHECK (end_date > start_date)
```

#### Business Logic Constraints
```sql
-- Expert override requires expert_user_id
CONSTRAINT chk_predictions_expert_override
    CHECK (
        (source = 'expert_override' AND expert_user_id IS NOT NULL)
        OR source != 'expert_override'
    )

-- Published predictions must have approval
CONSTRAINT chk_predictions_published_approval
    CHECK (
        (status = 'published' AND admin_user_id IS NOT NULL)
        OR status != 'published'
    )
```

### 5. Not Null Constraints

**Critical fields** marked as NOT NULL:

```sql
-- All tables
id UUID NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL

-- users.users
email VARCHAR(255) NOT NULL
username VARCHAR(100) NOT NULL
password_hash VARCHAR(255) NOT NULL

-- predictions.predictions
match_id UUID NOT NULL
betting_market_id UUID NOT NULL
prediction_value VARCHAR(50) NOT NULL
confidence DECIMAL(5,4) NOT NULL
```

---

## 🔒 Referential Integrity Rules

### Cascade Behaviors

#### ON DELETE CASCADE

**Use Cases:**
- Parent-child relationships where child has no meaning without parent
- User data deletion (GDPR compliance)
- Cleanup of dependent data

**Examples:**
```sql
-- User sessions deleted when user deleted
users.users → users.user_sessions (CASCADE)

-- Predictions deleted when match deleted
predictions.matches → predictions.predictions (CASCADE)

-- Analytics deleted when user deleted
users.users → analytics.user_analytics (CASCADE)
```

#### ON DELETE SET NULL

**Use Cases:**
- Audit trail preservation
- Historical data retention
- Optional relationships

**Examples:**
```sql
-- Predictions preserved when user deleted
users.users → predictions.predictions (SET NULL)

-- Audit logs preserved when user deleted
users.users → audit.audit_log (SET NULL)

-- ML predictions preserved when model deleted
ml_models.ml_models → ml_models.ml_predictions (SET NULL)
```

#### ON DELETE RESTRICT

**Use Cases:**
- Prevent deletion of referenced data
- Enforce business rules
- Protect critical data

**Examples:**
```sql
-- Cannot delete subscription tier if users subscribed
subscription_tiers → user_subscriptions (RESTRICT)

-- Cannot delete betting market if predictions exist
betting_markets → predictions (RESTRICT)

-- Cannot delete league if seasons exist
leagues → seasons (RESTRICT)
```

### Update Behaviors

**All foreign keys** use `ON UPDATE CASCADE`:

```sql
FOREIGN KEY (user_id)
    REFERENCES users.users(id)
    ON UPDATE CASCADE
    ON DELETE SET NULL
```

**Rationale:**
- UUID primary keys rarely change
- Cascade ensures consistency if they do
- Simplifies data management

---

## 📊 Relationship Summary by Schema

### Users Schema

| Relationship Type | Count |
|-------------------|-------|
| Outgoing Cross-Schema | 15 |
| Intra-Schema | 25 |
| Total | 40 |

### Predictions Schema

| Relationship Type | Count |
|-------------------|-------|
| Incoming Cross-Schema | 10 |
| Outgoing Cross-Schema | 8 |
| Intra-Schema | 30 |
| Total | 48 |

### ML Models Schema

| Relationship Type | Count |
|-------------------|-------|
| Incoming Cross-Schema | 3 |
| Outgoing Cross-Schema | 5 |
| Intra-Schema | 20 |
| Total | 28 |

### Analytics Schema

| Relationship Type | Count |
|-------------------|-------|
| Incoming Cross-Schema | 8 |
| Outgoing Cross-Schema | 2 |
| Intra-Schema | 15 |
| Total | 25 |

### Audit Schema

| Relationship Type | Count |
|-------------------|-------|
| Incoming Cross-Schema | 7 |
| Intra-Schema | 10 |
| Total | 17 |

---

## 🎯 Best Practices

### 1. Foreign Key Naming

```sql
-- Pattern: fk_{source_table}_{target_table}_{column}
CONSTRAINT fk_predictions_users_created_by
CONSTRAINT fk_user_roles_users_user_id
CONSTRAINT fk_ml_predictions_matches_match_id
```

### 2. Index on Foreign Keys

**All foreign keys** should have indexes:

```sql
CREATE INDEX idx_predictions_created_by_user_id
    ON predictions.predictions(created_by_user_id);
```

### 3. Constraint Validation

**Check constraints** should be simple and fast:

```sql
-- Good: Simple value check
CHECK (confidence >= 0 AND confidence <= 1)

-- Avoid: Complex subqueries
-- CHECK (EXISTS (SELECT 1 FROM ...))
```

### 4. Cascade Strategy

**Decision Matrix:**

| Scenario | Strategy | Reason |
|----------|----------|--------|
| User data (GDPR) | CASCADE | Legal requirement |
| Audit logs | SET NULL | Preserve history |
| Reference data | RESTRICT | Prevent orphans |
| Optional links | SET NULL | Maintain flexibility |

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Database Architecture Team


