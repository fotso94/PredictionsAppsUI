# Audit Schema - Quick Reference
## Soccer Predictions Platform

**Version**: 1.0  
**Created**: 2025-10-08  
**Schema**: audit

---

## 📋 Overview

The **audit schema** provides comprehensive audit logging, compliance tracking, and security monitoring for the Soccer Predictions Platform.

**Total Tables**: 8  
**Total Indexes**: 40+  
**Storage Estimate**: ~9 GB (Year 1)  
**Retention**: 7 years (legal compliance)

---

## 📊 Tables Summary

### 1. audit_log
**Purpose**: Master audit log for all system events  
**Type**: Parent table for specialized audit logs  
**Key Fields**: event_type, user_id, ip_address, user_agent, severity, metadata, changes

**Event Types**:
- user_login, user_logout, user_registration
- prediction_created, prediction_updated, prediction_deleted
- admin_action, system_event, security_event
- data_access, data_export, data_deletion

### 2. data_access_log
**Purpose**: Track all data access for GDPR compliance  
**Relationship**: Extends audit_log  
**Key Fields**: resource_type, resource_id, access_type, data_accessed, purpose

**Access Types**:
- read, write, update, delete, export, share

**GDPR Compliance**: Article 30 (Records of processing activities)

### 3. prediction_change_log
**Purpose**: Track all prediction changes and overrides  
**Relationship**: Extends audit_log  
**Key Fields**: prediction_id, change_type, old_values, new_values, reason, approved_by

**Change Types**:
- created, updated, expert_override, admin_override, published, settled, voided

### 4. user_action_log
**Purpose**: Track user actions and behavior  
**Relationship**: Extends audit_log  
**Key Fields**: action_type, action_data, session_id, device_info, location

**Action Types**:
- view_prediction, follow_expert, subscribe, unsubscribe, update_profile, change_password

### 5. admin_action_log
**Purpose**: Track administrative actions  
**Relationship**: Extends audit_log  
**Key Fields**: admin_user_id, action_type, target_resource, action_data, approval_required

**Action Types**:
- approve_prediction, reject_prediction, ban_user, unban_user, modify_permissions, system_config_change

### 6. system_event_log
**Purpose**: Track system events and errors  
**Relationship**: Extends audit_log  
**Key Fields**: event_type, severity, component, error_message, stack_trace, resolution_status

**Severity Levels**:
- debug, info, warning, error, critical

### 7. gdpr_consent_log
**Purpose**: Track user consent for GDPR compliance  
**Key Fields**: user_id, consent_type, consent_given, consent_version, ip_address, user_agent

**Consent Types**:
- data_processing, marketing, analytics, third_party_sharing

**GDPR Compliance**: Article 7 (Conditions for consent)

### 8. data_export_log
**Purpose**: Track data export requests (GDPR right to data portability)  
**Key Fields**: user_id, export_type, data_scope, file_format, download_url, expires_at

**Export Types**:
- full_data, predictions_only, profile_only, analytics_only

**GDPR Compliance**: Article 20 (Right to data portability)

---

## 🔑 Key Indexes

### High-Performance Indexes

```sql
-- User activity lookup
CREATE INDEX idx_audit_log_user_id
    ON audit.audit_log(user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- Event type filtering
CREATE INDEX idx_audit_log_event_type
    ON audit.audit_log(event_type, created_at DESC);

-- Time-based queries
CREATE INDEX idx_audit_log_created_at
    ON audit.audit_log(created_at DESC);

-- IP tracking
CREATE INDEX idx_audit_log_ip
    ON audit.audit_log(ip_address, created_at DESC);

-- JSONB queries
CREATE INDEX idx_audit_log_metadata_gin
    ON audit.audit_log USING GIN(metadata);

CREATE INDEX idx_audit_log_changes_gin
    ON audit.audit_log USING GIN(changes);

-- BRIN for time-series (large tables)
CREATE INDEX idx_audit_log_created_at_brin
    ON audit.audit_log USING BRIN(created_at);
```

---

## 📈 Common Queries

### User Activity History
```sql
SELECT
    event_type,
    ip_address,
    user_agent,
    metadata,
    created_at
FROM audit.audit_log
WHERE user_id = 'user-uuid'
ORDER BY created_at DESC
LIMIT 100;
```

### Prediction Change History
```sql
SELECT
    prediction_id,
    change_type,
    old_values,
    new_values,
    reason,
    approved_by,
    created_at
FROM audit.prediction_change_log
WHERE prediction_id = 'prediction-uuid'
ORDER BY created_at DESC;
```

### Admin Actions
```sql
SELECT
    admin_user_id,
    action_type,
    target_resource,
    action_data,
    created_at
FROM audit.admin_action_log
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY created_at DESC;
```

### Security Events
```sql
SELECT
    user_id,
    event_type,
    ip_address,
    severity,
    metadata,
    created_at
FROM audit.audit_log
WHERE event_type IN ('failed_login', 'suspicious_activity', 'unauthorized_access')
  AND created_at >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY created_at DESC;
```

### GDPR Data Access Report
```sql
SELECT
    user_id,
    resource_type,
    access_type,
    purpose,
    created_at
FROM audit.data_access_log
WHERE user_id = 'user-uuid'
  AND created_at >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY created_at DESC;
```

### GDPR Consent History
```sql
SELECT
    consent_type,
    consent_given,
    consent_version,
    ip_address,
    created_at
FROM audit.gdpr_consent_log
WHERE user_id = 'user-uuid'
ORDER BY created_at DESC;
```

---

## 🛡️ Security & Compliance

### GDPR Compliance

| Requirement | Implementation | Table |
|-------------|----------------|-------|
| Article 7 (Consent) | Track all consent | gdpr_consent_log |
| Article 15 (Right to access) | Log all data access | data_access_log |
| Article 17 (Right to erasure) | Log deletions | audit_log |
| Article 20 (Data portability) | Track exports | data_export_log |
| Article 30 (Records) | Comprehensive audit trail | All tables |

### Immutability

**All audit logs are immutable**:
- No UPDATE operations allowed
- No DELETE operations allowed (except automated retention cleanup)
- Only INSERT operations permitted
- Enforced by database triggers and application logic

```sql
-- Trigger to prevent updates
CREATE TRIGGER prevent_audit_log_update
    BEFORE UPDATE ON audit.audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_update();

-- Trigger to prevent deletes
CREATE TRIGGER prevent_audit_log_delete
    BEFORE DELETE ON audit.audit_log
    FOR EACH ROW
    EXECUTE FUNCTION prevent_delete();
```

### Data Retention

| Table | Retention Period | Reason |
|-------|------------------|--------|
| audit_log | 7 years | Legal compliance |
| data_access_log | 7 years | GDPR Article 30 |
| prediction_change_log | 7 years | Financial records |
| user_action_log | 2 years | Business analytics |
| admin_action_log | 7 years | Compliance |
| system_event_log | 1 year | Operational needs |
| gdpr_consent_log | Indefinite | Legal requirement |
| data_export_log | 7 years | GDPR compliance |

### Encryption

**Sensitive fields encrypted at rest**:
- ip_address (PII)
- user_agent (PII)
- location data (PII)
- metadata (may contain PII)

```sql
-- Encrypt sensitive data
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Example: Encrypt IP address
INSERT INTO audit.audit_log (ip_address, ...)
VALUES (pgp_sym_encrypt('192.168.1.1', 'encryption-key'), ...);

-- Decrypt for authorized access
SELECT pgp_sym_decrypt(ip_address::bytea, 'encryption-key') AS ip
FROM audit.audit_log;
```

---

## 📊 Storage Estimates

| Table | Rows (Year 1) | Size per Row | Total Size |
|-------|---------------|--------------|------------|
| audit_log | 100,000,000 | 2 KB | 200 GB* |
| data_access_log | 50,000,000 | 1.5 KB | 75 GB* |
| prediction_change_log | 5,000,000 | 2 KB | 10 GB |
| user_action_log | 200,000,000 | 1 KB | 200 GB* |
| admin_action_log | 100,000 | 2 KB | 200 MB |
| system_event_log | 10,000,000 | 1.5 KB | 15 GB |
| gdpr_consent_log | 500,000 | 1 KB | 500 MB |
| data_export_log | 50,000 | 1 KB | 50 MB |

**Note**: Tables marked with * should use partitioning.

**Total Year 1**: ~500 GB (with partitioning and compression)

---

## 🛠️ Maintenance

### Partitioning Strategy

**All large tables** partitioned by month:

```sql
-- audit_log partitioning
CREATE TABLE audit.audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMP NOT NULL,
    ...
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE audit.audit_log_2025_01
    PARTITION OF audit.audit_log
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE audit.audit_log_2025_02
    PARTITION OF audit.audit_log
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
```

### Automated Partition Management

```sql
-- Function to create next month's partition
CREATE OR REPLACE FUNCTION audit.create_next_partition()
RETURNS void AS $$
DECLARE
    next_month DATE := DATE_TRUNC('month', CURRENT_DATE + INTERVAL '1 month');
    partition_name TEXT := 'audit_log_' || TO_CHAR(next_month, 'YYYY_MM');
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS audit.%I PARTITION OF audit.audit_log
         FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        next_month,
        next_month + INTERVAL '1 month'
    );
END;
$$ LANGUAGE plpgsql;

-- Schedule to run monthly
SELECT cron.schedule('create-audit-partitions', '0 0 1 * *', 'SELECT audit.create_next_partition()');
```

### Data Archival

**Archive old partitions to S3**:

```bash
# Export partition to S3
pg_dump -t audit.audit_log_2024_01 | gzip | aws s3 cp - s3://bucket/audit/2024/01/audit_log.sql.gz

# Drop archived partition
DROP TABLE audit.audit_log_2024_01;
```

### Compression

**Enable compression for old partitions**:

```sql
-- Compress partition (PostgreSQL 14+)
ALTER TABLE audit.audit_log_2024_01 SET (toast_compression = lz4);
```

---

## 🎯 Performance Optimization

### Query Optimization

**Use partition pruning**:
```sql
-- Good: Partition pruning works
SELECT * FROM audit.audit_log
WHERE created_at >= '2025-01-01'
  AND created_at < '2025-02-01';

-- Bad: Full table scan
SELECT * FROM audit.audit_log
WHERE user_id = 'uuid';
```

### Indexing Strategy

**Composite indexes for common queries**:
```sql
-- User activity by date range
CREATE INDEX idx_audit_log_user_date
    ON audit.audit_log(user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

-- Event type filtering
CREATE INDEX idx_audit_log_event_date
    ON audit.audit_log(event_type, created_at DESC);
```

### Caching Strategy

**Redis Cache** (DB 5: API rate limiting):
- Recent user activity (TTL: 5 minutes)
- Security events (TTL: 1 minute)
- Admin actions (TTL: 10 minutes)

---

## 🚨 Monitoring & Alerts

### Critical Alerts

1. **Failed Login Attempts**
   - Threshold: >5 failed attempts in 5 minutes
   - Action: Lock account, notify security team

2. **Unauthorized Access**
   - Threshold: Any occurrence
   - Action: Immediate alert, log IP, block access

3. **Data Export Requests**
   - Threshold: >10 requests per day per user
   - Action: Review for suspicious activity

4. **Admin Actions**
   - Threshold: Any high-risk action
   - Action: Notify security team, require approval

### Monitoring Queries

```sql
-- Failed login attempts (last hour)
SELECT
    user_id,
    COUNT(*) AS failed_attempts,
    ARRAY_AGG(DISTINCT ip_address) AS ip_addresses
FROM audit.audit_log
WHERE event_type = 'failed_login'
  AND created_at >= NOW() - INTERVAL '1 hour'
GROUP BY user_id
HAVING COUNT(*) >= 5;

-- Suspicious data access
SELECT
    user_id,
    COUNT(*) AS access_count,
    ARRAY_AGG(DISTINCT resource_type) AS resources
FROM audit.data_access_log
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY user_id
HAVING COUNT(*) > 100;
```

---

## 📚 Related Documentation

- [audit-schema-er-diagram.md](./audit-schema-er-diagram.md) - Complete ER diagram
- [INDEX_STRATEGY.md](./INDEX_STRATEGY.md) - Index definitions
- [TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md](./TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md) - Relationships

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Database Architecture Team

