# PostgreSQL Configuration
## Soccer Predictions Platform - Database Setup

**Version**: 1.0  
**Created**: 2025-10-08  
**Jira Task**: KAN-103 - Configure PostgreSQL container with initialization

---

## 📋 Overview

This directory contains PostgreSQL configuration and initialization scripts for the Soccer Predictions Platform local development environment.

**PostgreSQL Version**: 15-alpine  
**Database Name**: soccer_predictions  
**Default User**: postgres  
**Default Password**: postgres123

---

## 📁 Directory Structure

```
docker/postgres/
├── README.md                    # This file
├── init/                        # Initialization scripts (run once on first start)
│   └── 01-init-database.sql    # Creates schemas, extensions, types
└── conf/                        # Configuration files
    └── postgresql.conf          # PostgreSQL server configuration
```

---

## 🚀 Initialization Process

### Automatic Initialization

When the PostgreSQL container starts for the first time (empty data volume), it automatically runs all `.sql` and `.sh` files in the `init/` directory in alphabetical order.

**Initialization Sequence:**

1. **Container Starts**: PostgreSQL 15 initializes with default settings
2. **Run Init Scripts**: Executes `01-init-database.sql`
3. **Create Schemas**: Creates 5 schemas (users, predictions, ml_models, analytics, audit)
4. **Enable Extensions**: Enables uuid-ossp, btree_gin, pg_trgm, pgcrypto
5. **Create Types**: Creates custom enum types for all schemas
6. **Set Permissions**: Grants permissions to postgres user
7. **Log Completion**: Logs initialization status to `db_init_log` table

### Initialization Script: 01-init-database.sql

**Purpose**: Sets up the multi-schema database architecture

**What It Does:**

1. **Creates Schemas:**
   - `users` - User accounts, profiles, authentication
   - `predictions` - Predictions, matches, results
   - `ml_models` - ML models, training, predictions
   - `analytics` - User and prediction analytics
   - `audit` - Audit logs, data access tracking

2. **Enables Extensions:**
   - `uuid-ossp` - UUID generation for primary keys
   - `btree_gin` - JSONB indexing support
   - `pg_trgm` - Full-text search capabilities
   - `pgcrypto` - Cryptographic functions

3. **Creates Custom Types (Enums):**
   - User roles: regular, expert, admin
   - Subscription tiers: free, basic, premium, pro
   - Prediction sources: ml_baseline, expert_created, admin_override
   - Prediction statuses: draft, pending_review, approved, published
   - And many more...

4. **Creates Utility Functions:**
   - `update_updated_at_column()` - Auto-update timestamps
   - `generate_slug()` - Generate URL-friendly slugs

5. **Sets Permissions:**
   - Grants usage on all schemas
   - Grants privileges on tables and sequences
   - Sets default privileges for future objects

### Manual Re-initialization

If you need to re-run initialization scripts:

```bash
# WARNING: This will delete all data!

# Stop and remove containers and volumes
docker-compose down -v

# Start fresh (will run init scripts again)
docker-compose up -d postgres
```

---

## ⚙️ Configuration

### PostgreSQL Configuration File: postgresql.conf

**Location**: `docker/postgres/conf/postgresql.conf`

**Key Settings:**

| Setting | Value | Purpose |
|---------|-------|---------|
| `max_connections` | 200 | Maximum concurrent connections |
| `shared_buffers` | 256MB | Shared memory buffer cache |
| `effective_cache_size` | 1GB | Planner's assumption of OS cache |
| `work_mem` | 4MB | Memory per query operation |
| `maintenance_work_mem` | 64MB | Memory for maintenance operations |
| `wal_buffers` | 16MB | Write-ahead log buffer |
| `min_wal_size` | 1GB | Minimum WAL size |
| `max_wal_size` | 4GB | Maximum WAL size |
| `log_min_duration_statement` | 1000ms | Log slow queries |
| `log_connections` | on | Log connections |
| `log_disconnections` | on | Log disconnections |

**Optimizations:**

- **SSD Optimized**: `random_page_cost = 1.1` (lower for SSD)
- **I/O Concurrency**: `effective_io_concurrency = 200` (for SSD)
- **Autovacuum**: Enabled with 3 workers
- **Logging**: Slow queries, connections, lock waits

### Modifying Configuration

1. **Edit Configuration File:**
   ```bash
   nano docker/postgres/conf/postgresql.conf
   ```

2. **Restart PostgreSQL:**
   ```bash
   docker-compose restart postgres
   ```

3. **Verify Changes:**
   ```bash
   docker-compose exec postgres psql -U postgres -c "SHOW shared_buffers;"
   ```

---

## 🗄️ Database Schema

### Multi-Schema Architecture

The database uses a **multi-schema architecture** to organize tables by domain:

```
soccer_predictions (database)
│
├── users (schema) - 17 tables
│   ├── users
│   ├── expert_profiles
│   ├── admin_profiles
│   ├── roles
│   ├── permissions
│   ├── user_roles
│   ├── role_permissions
│   ├── user_sessions
│   ├── refresh_tokens
│   ├── user_subscriptions
│   ├── subscription_tiers
│   ├── expert_specialties
│   ├── expert_permissions
│   ├── admin_permissions
│   ├── user_preferences
│   ├── user_notifications
│   └── notification_preferences
│
├── predictions (schema) - 16 tables
│   ├── predictions
│   ├── matches
│   ├── teams
│   ├── leagues
│   ├── seasons
│   ├── prediction_overrides
│   ├── prediction_audit
│   ├── prediction_results
│   ├── betting_markets
│   ├── prediction_analytics
│   ├── match_statistics
│   ├── team_statistics
│   ├── head_to_head
│   ├── form_guide
│   ├── injury_news
│   └── weather_data
│
├── ml_models (schema) - 12 tables
│   ├── ml_models
│   ├── ml_model_versions
│   ├── ml_predictions
│   ├── ml_training_runs
│   ├── ml_training_data
│   ├── ml_feature_importance
│   ├── ml_hyperparameters
│   ├── ml_metrics
│   ├── ml_ab_tests
│   ├── ml_champion_models
│   ├── ml_model_registry
│   └── ml_deployment_history
│
├── analytics (schema) - 13 tables
│   ├── user_analytics
│   ├── user_engagement_metrics
│   ├── user_activity_log
│   ├── prediction_analytics_summary
│   ├── prediction_performance_metrics
│   ├── expert_performance_metrics
│   ├── model_performance_comparison
│   ├── revenue_analytics
│   ├── subscription_analytics
│   ├── feature_usage_analytics
│   ├── api_usage_analytics
│   ├── error_analytics
│   └── system_health_metrics
│
└── audit (schema) - 8 tables
    ├── audit_log
    ├── data_access_log
    ├── prediction_change_log
    ├── user_action_log
    ├── admin_action_log
    ├── system_event_log
    ├── gdpr_consent_log
    └── data_export_log
```

**Total**: 66 tables across 5 schemas

### Schema Documentation

For detailed schema documentation, see:
- [Database Schema README](../../docs/database/README.md)
- [Users Schema ER Diagram](../../docs/database/users-schema-er-diagram.md)
- [Predictions Schema ER Diagram](../../docs/database/predictions-schema-er-diagram.md)
- [ML Models Schema ER Diagram](../../docs/database/ml-models-schema-er-diagram.md)
- [Analytics Schema ER Diagram](../../docs/database/analytics-schema-er-diagram.md)
- [Audit Schema ER Diagram](../../docs/database/audit-schema-er-diagram.md)

---

## 🔧 Common Operations

### Connect to Database

```bash
# Using psql in container
docker-compose exec postgres psql -U postgres -d soccer_predictions

# From host (requires psql installed)
psql -h localhost -p 5432 -U postgres -d soccer_predictions
```

### List Schemas

```sql
-- List all schemas
\dn

-- List tables in specific schema
\dt users.*
\dt predictions.*
\dt ml_models.*
\dt analytics.*
\dt audit.*
```

### Set Search Path

```sql
-- Set search path to include all schemas
SET search_path TO users, predictions, ml_models, analytics, audit, public;

-- Make it permanent for session
ALTER DATABASE soccer_predictions SET search_path TO users, predictions, ml_models, analytics, audit, public;
```

### Backup Database

```bash
# Backup entire database
docker-compose exec postgres pg_dump -U postgres -d soccer_predictions > backup.sql

# Backup specific schema
docker-compose exec postgres pg_dump -U postgres -d soccer_predictions -n users > users_backup.sql

# Backup with custom format (compressed)
docker-compose exec postgres pg_dump -U postgres -d soccer_predictions -Fc > backup.dump
```

### Restore Database

```bash
# Restore from SQL dump
docker-compose exec -T postgres psql -U postgres -d soccer_predictions < backup.sql

# Restore from custom format
docker-compose exec postgres pg_restore -U postgres -d soccer_predictions /path/to/backup.dump
```

### Check Database Size

```sql
-- Database size
SELECT pg_size_pretty(pg_database_size('soccer_predictions'));

-- Schema sizes
SELECT schemaname, pg_size_pretty(sum(pg_total_relation_size(schemaname||'.'||tablename))::bigint)
FROM pg_tables
WHERE schemaname IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
GROUP BY schemaname;

-- Table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 20;
```

---

## 🔍 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs postgres

# Common issues:
# 1. Port 5432 already in use
lsof -i :5432

# 2. Configuration syntax error
docker-compose exec postgres cat /etc/postgresql/conf.d/postgresql.conf

# 3. Initialization script error
docker-compose logs postgres | grep ERROR
```

### Cannot Connect

```bash
# Check service is running
docker-compose ps postgres

# Check health status
docker-compose exec postgres pg_isready -U postgres

# Test connection
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT 1;"
```

### Slow Performance

```sql
-- Check active connections
SELECT count(*) FROM pg_stat_activity;

-- Check slow queries
SELECT pid, usename, state, query, now() - query_start AS duration
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY duration DESC;

-- Run VACUUM
VACUUM ANALYZE;
```

---

## 📚 Related Documentation

- [Docker README](../README.md) - Main Docker documentation
- [Docker Architecture](../DOCKER_ARCHITECTURE.md) - Architecture details
- [Troubleshooting Guide](../TROUBLESHOOTING.md) - Problem solving
- [Database Schema Documentation](../../docs/database/README.md) - Schema details

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Backend Development Team


