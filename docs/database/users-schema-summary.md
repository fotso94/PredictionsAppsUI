# Users Schema - Quick Reference Summary
## Soccer Predictions Platform

**Jira Task**: KAN-92  
**Status**: ✅ Complete - Ready for Review  
**Last Updated**: 2025-10-08

---

## Schema Overview

The **users** schema contains **17 tables** organized into 4 functional groups:

| Group | Tables | Purpose |
|-------|--------|---------|
| **Core User** | 6 tables | User accounts, sessions, preferences, subscriptions |
| **Expert User** | 3 tables | Expert profiles, specialties, performance tracking |
| **Admin User** | 3 tables | Admin profiles, permissions, activity logging |
| **RBAC System** | 5 tables | Roles, permissions, and assignments |

---

## Table Summary

### Core User Tables (6 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 1 | `users` | 100K+ | Main user accounts | → expert_profiles, admin_profiles, user_preferences |
| 2 | `user_preferences` | 100K+ | User settings | ← users (1:1) |
| 3 | `user_sessions` | 500K+ | Active sessions | ← users (1:many) |
| 4 | `user_activity_log` | 10M+ | Activity tracking | ← users (1:many) |
| 5 | `user_subscriptions` | 200K+ | Subscription history | ← users (1:many) |
| 6 | `user_notifications` | 1M+ | In-app notifications | ← users (1:many) |

### Expert User Tables (3 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 7 | `expert_profiles` | 1K-5K | Expert user profiles | ← users (1:1 optional) |
| 8 | `expert_specialties` | 5K-20K | Expert specializations | ← expert_profiles (1:many) |
| 9 | `expert_performance_metrics` | 100K+ | Time-series performance | ← expert_profiles (1:many) |

### Admin User Tables (3 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 10 | `admin_profiles` | 10-50 | Admin user profiles | ← users (1:1 optional) |
| 11 | `admin_permissions` | 50-200 | Granular permissions | ← admin_profiles (1:many) |
| 12 | `admin_activity_log` | 100K+ | Admin action audit | ← admin_profiles (1:many) |

### RBAC System Tables (5 tables)

| # | Table | Rows (Est.) | Purpose | Key Relationships |
|---|-------|-------------|---------|-------------------|
| 13 | `roles` | 10-20 | System roles | ↔ permissions (many:many) |
| 14 | `permissions` | 50-100 | System permissions | ↔ roles (many:many) |
| 15 | `user_roles` | 100K+ | User-role assignments | ← users, roles (junction) |
| 16 | `role_permissions` | 200-500 | Role-permission grants | ← roles, permissions (junction) |

**Note**: Row estimates are for production scale after 1 year of operation.

---

## Relationship Types

### One-to-One (1:1)
- `users` → `expert_profiles` (optional)
- `users` → `admin_profiles` (optional)
- `users` → `user_preferences` (required)

### One-to-Many (1:N)
- `users` → `user_sessions`
- `users` → `user_activity_log`
- `users` → `user_subscriptions`
- `users` → `user_notifications`
- `expert_profiles` → `expert_specialties`
- `expert_profiles` → `expert_performance_metrics`
- `admin_profiles` → `admin_permissions`
- `admin_profiles` → `admin_activity_log`

### Many-to-Many (M:N)
- `users` ↔ `roles` (via `user_roles`)
- `roles` ↔ `permissions` (via `role_permissions`)

---

## Key Features

### 🔐 Security
- ✅ UUID primary keys (prevent enumeration)
- ✅ Bcrypt password hashing
- ✅ JWT session tokens with refresh
- ✅ Email verification workflow
- ✅ Password reset with expiring tokens
- ✅ Soft deletes for data recovery
- ✅ Comprehensive audit logging

### 🚀 Performance
- ✅ 50+ strategic indexes
- ✅ Unique indexes on email, username, tokens
- ✅ Foreign key indexes for joins
- ✅ Composite indexes for common queries
- ✅ JSONB GIN indexes for flexible data
- ✅ Partial indexes for boolean flags

### 👥 Multi-Profile System
- ✅ Regular Users (consumption)
- ✅ Expert Users (prediction creation/override)
- ✅ Admin Users (system management)
- ✅ Flexible role assignment (users can have multiple roles)
- ✅ Expert verification workflow
- ✅ Admin permission hierarchy

### 📊 Analytics & Tracking
- ✅ User activity logging
- ✅ Expert performance metrics (time-series)
- ✅ Admin action audit trail
- ✅ Subscription history tracking
- ✅ Session management and device tracking

### 🎯 Business Features
- ✅ Subscription tiers (Free, Basic, Premium, Pro)
- ✅ Trial period support
- ✅ Expert specialties (leagues, teams, markets)
- ✅ Expert ranking system (1-10 levels)
- ✅ Featured experts
- ✅ In-app notifications with priority

---

## Data Types Used

| PostgreSQL Type | Usage | Examples |
|-----------------|-------|----------|
| `uuid` | All primary keys, foreign keys | `id`, `user_id` |
| `varchar` | Short text fields | `email`, `username`, `role_name` |
| `text` | Long text fields | `bio`, `message`, `description` |
| `enum` | Fixed value sets | `user_type`, `account_status`, `subscription_tier` |
| `boolean` | True/false flags | `email_verified`, `is_featured`, `is_active` |
| `integer` | Counts, levels | `expert_level`, `predictions_count` |
| `decimal` | Percentages, money | `accuracy`, `monthly_price` |
| `timestamp` | Date and time | `created_at`, `updated_at`, `expires_at` |
| `date` | Date only | `start_date`, `end_date`, `verified_at` |
| `inet` | IP addresses | `last_login_ip`, `ip_address` |
| `jsonb` | Flexible structured data | `performance_data`, `device_info`, `favorite_teams` |

---

## Index Strategy

### Total Indexes: ~80 indexes

| Index Type | Count | Purpose |
|------------|-------|---------|
| Primary Key | 17 | Unique row identification |
| Unique | 12 | Enforce uniqueness (email, username, tokens) |
| Foreign Key | 20 | Improve join performance |
| Query Optimization | 25 | Support common WHERE/ORDER BY clauses |
| JSONB GIN | 10 | Enable JSONB queries |
| Composite | 6 | Multi-column query optimization |

---

## Constraints Summary

### Check Constraints (~25 constraints)
- Password hash required for active users
- Email verification consistency
- Expert level range (1-10)
- Accuracy range (0-100%)
- Date consistency (end_date > start_date)
- Session expiration logic
- Specialty type validation
- Priority validation

### Foreign Key Constraints (~20 constraints)
- All `user_id` references → `users(id)`
- All `expert_profile_id` references → `expert_profiles(id)`
- All `admin_profile_id` references → `admin_profiles(id)`
- All `role_id` references → `roles(id)`
- All `permission_id` references → `permissions(id)`

### Unique Constraints (~12 constraints)
- `users.email` (case-insensitive, excluding deleted)
- `users.username` (case-insensitive, excluding deleted)
- `users.email_verification_token`
- `users.password_reset_token`
- `expert_profiles.user_id`
- `admin_profiles.user_id`
- `user_preferences.user_id`
- `user_sessions.session_token`
- `user_sessions.refresh_token`
- `roles.role_name`
- `permissions.permission_key`
- `expert_specialties.expert_profile_id` (WHERE is_primary = true)

---

## JSONB Fields (10 fields)

| Table | Field | Purpose | Example Structure |
|-------|-------|---------|-------------------|
| `expert_profiles` | `performance_data` | Detailed metrics | `{"monthly_accuracy": {...}, "trends": [...]}` |
| `expert_performance_metrics` | `detailed_metrics` | Additional metrics | `{"by_league": {...}, "by_market": {...}}` |
| `admin_permissions` | `scope_constraints` | Permission rules | `{"league_ids": [1, 2, 3], "team_ids": [...]}` |
| `admin_activity_log` | `action_details` | Action context | `{"action": "user_suspended", "reason": "..."}` |
| `admin_activity_log` | `changes_made` | Before/after | `{"before": {...}, "after": {...}}` |
| `user_preferences` | `favorite_teams` | Team IDs array | `["team-uuid-1", "team-uuid-2"]` |
| `user_preferences` | `favorite_leagues` | League IDs array | `["league-uuid-1", "league-uuid-2"]` |
| `user_sessions` | `device_info` | Device details | `{"browser": "Chrome", "os": "macOS"}` |
| `user_activity_log` | `activity_metadata` | Activity context | `{"match_id": "...", "duration": 120}` |
| `user_notifications` | `data` | Notification data | `{"match_id": "...", "prediction_id": "..."}` |

---

## Enum Types (9 enums)

| Enum Name | Values | Used In |
|-----------|--------|---------|
| `user_type` | regular, expert, admin | `users.user_type` |
| `account_status` | active, suspended, deleted, pending_verification | `users.account_status` |
| `verification_status` | pending, verified, rejected, suspended | `expert_profiles.verification_status` |
| `admin_level` | super_admin, admin, moderator | `admin_profiles.admin_level` |
| `subscription_tier` | free, basic, premium, pro | `user_subscriptions.subscription_tier` |
| `subscription_status` | active, cancelled, expired, trial | `user_subscriptions.subscription_status` |
| `theme` | light, dark, auto | `user_preferences.theme` |
| `odds_format` | decimal, fractional, american | `user_preferences.odds_format` |
| `priority` | low, medium, high | `user_notifications.priority` |

---

## Migration Phases

### Phase 1: Core Tables (Day 1)
1. `users`
2. `user_preferences`
3. `roles`
4. `permissions`
5. `user_roles`
6. `role_permissions`

### Phase 2: Profile Tables (Day 2)
1. `expert_profiles`
2. `expert_specialties`
3. `expert_performance_metrics`
4. `admin_profiles`
5. `admin_permissions`

### Phase 3: Activity Tables (Day 3)
1. `user_sessions`
2. `user_activity_log`
3. `admin_activity_log`

### Phase 4: Subscription Tables (Day 4)
1. `user_subscriptions`
2. `user_notifications`

### Phase 5: Seed Data (Day 5)
1. Default roles (regular_user, expert_user, admin_user)
2. Default permissions
3. Role-permission assignments
4. Initial admin user

---

## Storage Estimates

### Year 1 Projections

| Table | Rows | Avg Row Size | Total Size |
|-------|------|--------------|------------|
| `users` | 100K | 500 bytes | ~50 MB |
| `user_sessions` | 500K | 300 bytes | ~150 MB |
| `user_activity_log` | 10M | 200 bytes | ~2 GB |
| `user_subscriptions` | 200K | 250 bytes | ~50 MB |
| `user_notifications` | 1M | 300 bytes | ~300 MB |
| `expert_performance_metrics` | 100K | 400 bytes | ~40 MB |
| `admin_activity_log` | 100K | 500 bytes | ~50 MB |
| **Total (users schema)** | | | **~2.7 GB** |

**Note**: Includes indexes (~2x data size), so total storage: **~8 GB** for users schema in Year 1.

---

## Performance Considerations

### Query Patterns Optimized For:
- ✅ User login (email/username lookup)
- ✅ Session validation (token lookup)
- ✅ Permission checks (role-permission joins)
- ✅ Expert ranking (expert_level, overall_accuracy)
- ✅ Active subscriptions (user_id + status)
- ✅ Unread notifications (user_id + is_read)
- ✅ Recent activity (user_id + created_at)
- ✅ Admin audit queries (action_type, created_at)

### Potential Bottlenecks:
- ⚠️ `user_activity_log` - High write volume (consider partitioning)
- ⚠️ `user_notifications` - High read/write volume (consider archiving)
- ⚠️ `expert_performance_metrics` - Time-series data (consider partitioning by date)

### Optimization Strategies:
- 📊 Partition `user_activity_log` by month
- 📊 Archive old notifications (>30 days)
- 📊 Use read replicas for analytics queries
- 📊 Cache frequently accessed data (Redis)
- 📊 Implement connection pooling (asyncpg)

---

## Next Steps

1. ✅ **Review ER diagram** - Stakeholder approval
2. 🔄 **Create Alembic migrations** (KAN-16)
3. 🔄 **Implement SQLAlchemy models** (KAN-17)
4. 🔄 **Write unit tests** for constraints
5. 🔄 **Create seed data** (KAN-20)
6. 🔄 **Performance testing** with realistic data volumes

---

## Related Documentation

- **Detailed ER Diagram**: [users-schema-er-diagram.md](./users-schema-er-diagram.md)
- **Database Overview**: [README.md](./README.md)
- **Architecture Plans**:
  - `AWS_PRODUCTION_DEPLOYMENT_PLAN.md`
  - `LOCAL_DEVELOPMENT_ARCHITECTURE_PLAN.md`
  - `FRONTEND_ARCHITECTURE_ANALYSIS.md`

---

**Status**: ✅ Ready for Implementation  
**Jira Task**: KAN-92 (Complete)  
**Next Task**: KAN-93 (Predictions Schema ER Diagram)

