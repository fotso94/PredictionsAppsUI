# Database Schema Documentation
## Soccer Predictions Platform - Multi-Schema Architecture

**Last Updated**: 2025-10-08  
**Status**: Design Phase  
**Jira Epic**: KAN-15 - Design PostgreSQL multi-schema database architecture

---

## Overview

This directory contains comprehensive database schema documentation for the Soccer Predictions Platform. The platform uses a **multi-schema PostgreSQL architecture** to organize data by domain and support a sophisticated multi-profile user system.

---

## Schema Organization

The database is organized into **five primary schemas**:

### 1. **users** Schema
**Purpose**: User management, authentication, and role-based access control

**Documentation**: [users-schema-er-diagram.md](./users-schema-er-diagram.md)

**Key Tables**:
- `users` - Core user accounts (Regular, Expert, Admin)
- `expert_profiles` - Extended profiles for Expert Users
- `admin_profiles` - Extended profiles for Admin Users
- `user_sessions` - Authentication sessions and JWT tokens
- `user_subscriptions` - Subscription tier management
- `roles` & `permissions` - RBAC system

**Supports**:
- ✅ Multi-profile user system (Regular, Expert, Admin)
- ✅ JWT authentication with session management
- ✅ Role-based access control (RBAC)
- ✅ Expert verification and performance tracking
- ✅ Subscription management (Free, Basic, Premium, Pro)
- ✅ Comprehensive audit trail

---

### 2. **predictions** Schema
**Purpose**: Prediction management, tracking, and results

**Documentation**: [predictions-schema-er-diagram.md](./predictions-schema-er-diagram.md) ✅ **COMPLETE**

**Key Tables** (16 tables):
- `predictions` - Core prediction records
- `prediction_overrides` - Expert overrides of ML predictions
- `prediction_audit` - Audit trail for prediction changes
- `prediction_results` - Match results and prediction outcomes
- `prediction_markets` - Multiple betting markets per prediction
- `prediction_analytics` - Performance metrics by source
- `user_prediction_views` - User engagement tracking
- `user_prediction_feedback` - User ratings and feedback
- `matches` - Match data from external APIs
- `match_results` - Final match results
- `match_statistics` - Pre-match, live, post-match stats
- `leagues` - League/competition reference
- `teams` - Team reference data
- `prediction_templates` - Reusable prediction templates

**Supports**:
- ✅ Hybrid prediction system (ML + Expert + Admin)
- ✅ Prediction source tracking (ML model, Expert, Admin)
- ✅ Expert override capabilities
- ✅ Prediction confidence levels
- ✅ Result tracking and accuracy calculation
- ✅ Multiple betting markets
- ✅ User engagement and feedback

---

### 3. **ml_models** Schema
**Purpose**: Machine learning model management and versioning

**Documentation**: [ml-models-schema-er-diagram.md](./ml-models-schema-er-diagram.md) ✅ **COMPLETE**

**Key Tables** (12 tables):
- `ml_models` - Model versions and metadata
- `ml_predictions` - Raw ML model outputs
- `ml_training_runs` - Training history and hyperparameters
- `ml_training_metrics` - Epoch-level training metrics
- `ml_model_performance` - Model accuracy and metrics
- `ml_model_deployments` - Deployment history and status
- `ml_features` - Feature registry and metadata
- `ml_feature_importance` - Feature importance scores
- `ml_feature_engineering` - Feature engineering versions
- `ml_prediction_explanations` - Model explainability (SHAP, LIME)
- `ml_ab_tests` - A/B testing framework
- `ml_ab_test_results` - A/B test results over time

**Supports**:
- ✅ ML model versioning and A/B testing
- ✅ Training pipeline tracking
- ✅ Model performance monitoring
- ✅ Feature engineering documentation
- ✅ Model deployment history
- ✅ Model explainability (SHAP, LIME)
- ✅ Continuous learning from expert feedback

---

### 4. **analytics** Schema
**Purpose**: Business intelligence and reporting

**Documentation**: [analytics-schema-er-diagram.md](./analytics-schema-er-diagram.md) ✅ **COMPLETE**

**Key Tables** (13 tables):
- `user_analytics` - User behavior and engagement metrics
- `user_engagement_metrics` - Aggregated engagement metrics
- `user_retention_cohorts` - Cohort-based retention analysis
- `prediction_analytics_summary` - Prediction performance by dimensions
- `prediction_performance_trends` - Time-series performance trends
- `expert_analytics_summary` - Expert performance metrics
- `expert_performance_trends` - Expert performance trends
- `expert_rankings` - Expert rankings by criteria
- `subscription_analytics_summary` - Subscription metrics by tier
- `revenue_metrics` - Revenue breakdown (MRR, ARR, ARPU)
- `churn_analysis` - Churn analysis by tier
- `system_analytics_summary` - System health metrics
- `api_performance_metrics` - API endpoint performance
- `error_rate_metrics` - Error tracking and analysis

**Supports**:
- ✅ User engagement tracking
- ✅ Prediction accuracy analytics
- ✅ Expert performance rankings
- ✅ Revenue and subscription analytics
- ✅ System health monitoring
- ✅ Cohort-based retention analysis
- ✅ API performance monitoring

---

### 5. **audit** Schema
**Purpose**: Comprehensive audit trail and compliance

**Documentation**: [audit-schema-er-diagram.md](./audit-schema-er-diagram.md) ✅ **COMPLETE**

**Key Tables** (8 tables):
- `audit_log` - Comprehensive system-wide audit trail
- `data_access_log` - Data access tracking for compliance
- `permission_changes` - Permission and role change history
- `system_events` - Critical system events
- `compliance_reports` - Generated compliance reports
- `user_consent_log` - User consent tracking (GDPR)
- `data_retention_log` - Data retention and deletion tracking
- `security_incidents` - Security incident tracking

**Supports**:
- ✅ GDPR compliance (Articles 15, 17, 20, 7, 30)
- ✅ Security auditing and incident response
- ✅ Permission change tracking
- ✅ Data access logging
- ✅ Compliance reporting
- ✅ Immutable audit trail (7-year retention)
- ✅ User consent management

---

## Multi-Profile User System

The platform supports **three distinct user profiles**:

### 1. **Regular Users**
- **Purpose**: Standard users who consume predictions
- **Capabilities**: View predictions, track personal performance, manage subscription
- **Tables**: `users`, `user_preferences`, `user_subscriptions`, `user_activity_log`

### 2. **Expert Users**
- **Purpose**: Domain experts who create and override ML predictions
- **Capabilities**: 
  - Review ML predictions and override when necessary
  - Create manual predictions
  - Access advanced analytics tools
  - Track personal performance metrics
- **Tables**: `users`, `expert_profiles`, `expert_specialties`, `expert_performance_metrics`
- **Verification**: Experts must be verified by Admin users before creating predictions

### 3. **Admin Users**
- **Purpose**: System administrators with full platform control
- **Capabilities**:
  - Manage users and experts
  - Moderate predictions
  - Configure system settings
  - Access all analytics and reports
  - Manage permissions
- **Tables**: `users`, `admin_profiles`, `admin_permissions`, `admin_activity_log`
- **Hierarchy**: super_admin > admin > moderator

---

## Key Design Principles

### 1. **Security First**
- ✅ UUID primary keys (prevent enumeration attacks)
- ✅ Bcrypt password hashing (never store plain text)
- ✅ JWT session management with refresh tokens
- ✅ Comprehensive audit logging
- ✅ Role-based access control (RBAC)
- ✅ Soft deletes for data recovery

### 2. **Performance Optimized**
- ✅ Strategic indexing (unique, foreign key, composite, JSONB GIN)
- ✅ Separate schemas for domain isolation
- ✅ JSONB for flexible data without schema changes
- ✅ Partial indexes for boolean flags
- ✅ Time-series tables for analytics

### 3. **Scalability**
- ✅ Multi-schema architecture for horizontal scaling
- ✅ Read replicas support (separate analytics schema)
- ✅ Partitioning-ready design (time-series tables)
- ✅ JSONB for schema evolution without migrations

### 4. **Compliance Ready**
- ✅ GDPR-compliant (soft deletes, data retention policies)
- ✅ Comprehensive audit trail
- ✅ Data access logging
- ✅ Permission change tracking
- ✅ Configurable data retention

### 5. **Developer Friendly**
- ✅ Clear naming conventions
- ✅ Comprehensive documentation
- ✅ Alembic migrations for version control
- ✅ SQLAlchemy ORM models
- ✅ Seed data for development

---

## Technology Stack

- **Database**: PostgreSQL 15+ (for JSONB, UUID, and advanced features)
- **Migration Tool**: Alembic (Python-based migrations)
- **ORM**: SQLAlchemy 2.0+ (async support)
- **Connection Pooling**: asyncpg (high-performance async driver)
- **Caching**: Redis (session storage, query caching)

---

## Development Workflow

### 1. **Schema Design** (Current Phase)
- ✅ Create ER diagrams for each schema
- ✅ Document tables, relationships, and constraints
- ✅ Review and approve with stakeholders

### 2. **Migration Scripts** (Next Phase - KAN-16)
- Create Alembic migration scripts
- Implement tables, indexes, and constraints
- Test migrations (up and down)

### 3. **ORM Models** (KAN-17, KAN-18, KAN-19)
- Create SQLAlchemy models
- Implement relationships and constraints
- Add model-level validation

### 4. **Seed Data** (KAN-20)
- Create development seed data
- Create test fixtures
- Create production initial data (roles, permissions)

### 5. **Testing**
- Unit tests for model constraints
- Integration tests for relationships
- Performance tests for queries

---

## File Structure

```
docs/database/
├── README.md                                      # This file
├── CROSS_SCHEMA_REVIEW.md                         # ✅ Complete - Cross-schema validation
├── TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md         # ✅ Complete (KAN-95)
├── INDEX_STRATEGY.md                              # ✅ Complete (KAN-96)
│
├── users-schema-er-diagram.md                     # ✅ Complete (KAN-92)
├── users-schema-summary.md                        # ✅ Complete
│
├── predictions-schema-er-diagram.md               # ✅ Complete (KAN-93)
├── predictions-schema-summary.md                  # ✅ Complete
│
├── ml-models-schema-er-diagram.md                 # ✅ Complete (KAN-94)
├── ml-models-schema-summary.md                    # ✅ Complete
│
├── analytics-schema-er-diagram.md                 # ✅ Complete
├── analytics-schema-summary.md                    # ✅ Complete
│
├── audit-schema-er-diagram.md                     # ✅ Complete
└── audit-schema-summary.md                        # ✅ Complete
```

---

## 📚 Documentation Index

### Schema ER Diagrams (Complete)

1. **[users-schema-er-diagram.md](./users-schema-er-diagram.md)** - Users schema (17 tables) ✅
2. **[predictions-schema-er-diagram.md](./predictions-schema-er-diagram.md)** - Predictions schema (16 tables) ✅
3. **[ml-models-schema-er-diagram.md](./ml-models-schema-er-diagram.md)** - ML Models schema (12 tables) ✅
4. **[analytics-schema-er-diagram.md](./analytics-schema-er-diagram.md)** - Analytics schema (13 tables) ✅
5. **[audit-schema-er-diagram.md](./audit-schema-er-diagram.md)** - Audit schema (8 tables) ✅

### Quick Reference Summaries (Complete)

1. **[users-schema-summary.md](./users-schema-summary.md)** - Quick reference for users schema ✅
2. **[predictions-schema-summary.md](./predictions-schema-summary.md)** - Quick reference for predictions schema ✅
3. **[ml-models-schema-summary.md](./ml-models-schema-summary.md)** - Quick reference for ml_models schema ✅
4. **[analytics-schema-summary.md](./analytics-schema-summary.md)** - Quick reference for analytics schema ✅
5. **[audit-schema-summary.md](./audit-schema-summary.md)** - Quick reference for audit schema ✅

### Cross-Schema Documentation (Complete)

1. **[CROSS_SCHEMA_REVIEW.md](./CROSS_SCHEMA_REVIEW.md)** - Comprehensive validation and analysis ✅
2. **[TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md](./TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md)** - Complete relationship mapping (KAN-95) ✅
3. **[INDEX_STRATEGY.md](./INDEX_STRATEGY.md)** - Comprehensive index strategy (KAN-96) ✅

---

## Related Jira Tasks

### Epic: KAN-15 - Design PostgreSQL multi-schema database architecture

**Subtasks**:
- ✅ **KAN-92**: Create ER diagram for users schema (COMPLETE)
- ✅ **KAN-93**: Create ER diagram for predictions schema (COMPLETE)
- ✅ **KAN-94**: Create ER diagram for ml_models schema (COMPLETE)
- ✅ **KAN-95**: Document all table relationships and constraints (COMPLETE)
- ✅ **KAN-96**: Define index strategy for all schemas (COMPLETE)

**Dependent Tasks**:
- **KAN-16**: Set up database migration system with Alembic
- **KAN-17**: Create database models for user management schema
- **KAN-18**: Create database models for predictions schema
- **KAN-19**: Create database models for ml_models schema
- **KAN-20**: Create comprehensive seed data for development

---

## Quick Reference

### Users Schema Tables (17 tables)

**Core User Tables**:
1. `users` - Main user accounts
2. `user_preferences` - User settings
3. `user_sessions` - Authentication sessions
4. `user_activity_log` - User activity tracking
5. `user_subscriptions` - Subscription management
6. `user_notifications` - In-app notifications

**Expert User Tables**:
7. `expert_profiles` - Expert user profiles
8. `expert_specialties` - Expert specialization areas
9. `expert_performance_metrics` - Expert performance tracking

**Admin User Tables**:
10. `admin_profiles` - Admin user profiles
11. `admin_permissions` - Granular admin permissions
12. `admin_activity_log` - Admin action audit trail

**RBAC Tables**:
13. `roles` - System roles
14. `permissions` - System permissions
15. `user_roles` - User-role assignments
16. `role_permissions` - Role-permission assignments

---

## Next Steps

1. ✅ **Complete users schema ER diagram** (KAN-92) - DONE
2. ✅ **Create predictions schema ER diagram** (KAN-93) - DONE
3. ✅ **Create ml_models schema ER diagram** (KAN-94) - DONE
4. ✅ **Create analytics schema ER diagram** (KAN-95) - DONE
5. ✅ **Create audit schema ER diagram** (KAN-96) - DONE
6. 🔄 **Review and approve all schemas** with stakeholders - NEXT
7. 🔄 **Begin Alembic migration implementation** (KAN-16)

---

## Documentation Status

| Schema | ER Diagram | Summary | Jira Task | Status |
|--------|-----------|---------|-----------|--------|
| **users** | ✅ Complete | ✅ Complete | KAN-92 | ✅ Ready for Review |
| **predictions** | ✅ Complete | ✅ Complete | KAN-93 | ✅ Ready for Review |
| **ml_models** | ✅ Complete | ✅ Complete | KAN-94 | ✅ Ready for Review |
| **analytics** | ✅ Complete | ⏳ Planned | KAN-95 | ✅ Ready for Review |
| **audit** | ✅ Complete | ⏳ Planned | KAN-96 | ✅ Ready for Review |

**Total Documentation Created**:
- **5 ER Diagram Documents** (~5,000 lines)
- **3 Summary Documents** (~900 lines)
- **1 README** (300 lines)
- **1 Cross-Schema Review** (to be created)
- **Total: ~6,200+ lines of comprehensive database documentation**

---

## Questions or Feedback?

For questions about the database schema design, please:
1. Review the detailed ER diagram documentation
2. Check the architecture documents in the project root
3. Consult with the backend development team
4. Create a Jira comment on the relevant task

---

**Document Status**: ✅ Active  
**Maintained By**: Backend Development Team  
**Last Review**: 2025-10-08

