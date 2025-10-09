# Database Backup Documentation

## Current Backup

**Backup File**: `soccer_predictions_20251008_224941.sql.gz`  
**Created**: October 8, 2025 at 22:49:41  
**Size**: 38 KB (compressed)  
**Format**: PostgreSQL SQL dump (gzipped)  
**MD5 Checksum**: `8a16b83cbea232cea328d5778cf57e6f`  

---

## Backup Contents

This backup contains the complete Soccer Predictions Platform database with all schemas, tables, and structure created by Alembic migration `9b3c8646a52d`.

### Database Information
- **Database Name**: `soccer_predictions`
- **PostgreSQL Version**: 15-alpine
- **Encoding**: UTF8
- **Alembic Migration**: `9b3c8646a52d` (Initial migration: Create all 66 tables across 5 schemas)

### Schemas Included (5)
1. **users** - User management and RBAC (18 tables including alembic_version)
2. **predictions** - Predictions and match data (16 tables)
3. **ml_models** - ML model lifecycle management (12 tables)
4. **analytics** - Analytics and metrics (13 tables)
5. **audit** - Audit logs and GDPR compliance (8 tables)

### Total Tables: 67
- Users schema: 18 tables
- Predictions schema: 16 tables
- ML Models schema: 12 tables
- Analytics schema: 13 tables
- Audit schema: 8 tables

### What's Included
✅ All table structures (CREATE TABLE statements)  
✅ All indexes and constraints  
✅ All enum types  
✅ All foreign key relationships  
✅ All sequences  
✅ Database metadata  
✅ Schema definitions  
✅ Clean and recreate statements (--clean --if-exists)  

### What's NOT Included
❌ User data (database is empty - no INSERT statements)  
❌ PostgreSQL system catalogs  
❌ PostgreSQL configuration files  
❌ WAL (Write-Ahead Log) files  

---

## How to Restore This Backup

### Method 1: Using Automated Script (Recommended)

```bash
# From project root
cd docker
./scripts/restore-database.sh ../docs/database/soccer_predictions_20251008_224941.sql.gz
```

### Method 2: Manual Restore

```bash
# Decompress and restore
gunzip -c docs/database/soccer_predictions_20251008_224941.sql.gz | \
  docker exec -i soccer_predictions_postgres psql -U postgres -d postgres
```

### Method 3: Restore to New Database

```bash
# Create new database
docker exec -it soccer_predictions_postgres psql -U postgres -c "CREATE DATABASE soccer_predictions_restored;"

# Restore to new database
gunzip -c docs/database/soccer_predictions_20251008_224941.sql.gz | \
  docker exec -i soccer_predictions_postgres psql -U postgres -d soccer_predictions_restored
```

---

## Verification After Restore

### Check Schemas
```bash
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "\dn"
```

Expected output: 5 schemas (analytics, audit, ml_models, predictions, users)

### Check Tables Count
```bash
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "
SELECT schemaname, COUNT(*) 
FROM pg_tables 
WHERE schemaname IN ('users', 'predictions', 'ml_models', 'analytics', 'audit') 
GROUP BY schemaname 
ORDER BY schemaname;"
```

Expected output:
- analytics: 13 tables
- audit: 8 tables
- ml_models: 12 tables
- predictions: 16 tables
- users: 18 tables

### Check Alembic Version
```bash
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT * FROM users.alembic_version;"
```

Expected output: `9b3c8646a52d`

---

## Backup Details

### Creation Command
```bash
docker exec -t soccer_predictions_postgres pg_dump \
  -U postgres \
  -d soccer_predictions \
  --clean \
  --if-exists \
  --create \
  --encoding=UTF8 \
  --verbose
```

### Compression
```bash
gzip -9  # Maximum compression
```

### File Integrity
- **MD5 Checksum**: `8a16b83cbea232cea328d5778cf57e6f`
- **Verify**: `md5 soccer_predictions_20251008_224941.sql.gz`

---

## Use Cases

### 1. Fresh Database Setup
Use this backup to quickly set up a new development environment with the complete database structure.

```bash
# Start PostgreSQL
docker-compose up -d postgres

# Restore structure
cd docker
./scripts/restore-database.sh ../docs/database/soccer_predictions_20251008_224941.sql.gz
```

### 2. Migration Testing
Test Alembic migrations by restoring to this known state.

```bash
# Restore to baseline
./scripts/restore-database.sh ../docs/database/soccer_predictions_20251008_224941.sql.gz

# Test migration
cd ../backend
alembic upgrade head
```

### 3. CI/CD Pipeline
Use this backup in CI/CD to create test databases.

```bash
# In CI pipeline
docker-compose up -d postgres
gunzip -c docs/database/soccer_predictions_20251008_224941.sql.gz | \
  docker exec -i soccer_predictions_postgres psql -U postgres -d postgres
```

### 4. Documentation Reference
This backup serves as a snapshot of the database structure at migration `9b3c8646a52d`.

---

## Related Documentation

- **Database Schema Design**: [docs/database/](.)
- **Table Relationships**: [TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md](./TABLE_RELATIONSHIPS_AND_CONSTRAINTS.md)
- **Index Strategy**: [INDEX_STRATEGY.md](./INDEX_STRATEGY.md)
- **Data Persistence Guide**: [docker/DATA_PERSISTENCE_GUIDE.md](../../docker/DATA_PERSISTENCE_GUIDE.md)
- **Backup Scripts**: [docker/scripts/](../../docker/scripts/)

---

## Backup History

| Date | Time | File | Size | Migration | Notes |
|------|------|------|------|-----------|-------|
| 2025-10-08 | 22:49:41 | soccer_predictions_20251008_224941.sql.gz | 38 KB | 9b3c8646a52d | Initial structure backup (empty database) |

---

## Important Notes

⚠️ **This is a structure-only backup** - The database was empty when this backup was created. It contains all table definitions, indexes, and constraints, but no user data.

✅ **Safe to restore** - This backup uses `--clean --if-exists` flags, so it will safely drop and recreate the database.

🔒 **Version controlled** - This backup is stored in the repository to provide a baseline database structure for all developers.

📅 **Update policy** - This backup should be updated whenever:
- New Alembic migrations are created
- Database schema changes are made
- Major structural changes occur

---

## Troubleshooting

### Restore Fails with "database does not exist"
The backup includes `CREATE DATABASE` statement, so restore to the `postgres` database:
```bash
gunzip -c backup.sql.gz | docker exec -i soccer_predictions_postgres psql -U postgres -d postgres
```

### Restore Fails with "already exists"
The backup includes `--clean --if-exists` flags, but if you still get errors:
```bash
# Drop database first
docker exec -it soccer_predictions_postgres psql -U postgres -c "DROP DATABASE IF EXISTS soccer_predictions;"

# Then restore
gunzip -c backup.sql.gz | docker exec -i soccer_predictions_postgres psql -U postgres -d postgres
```

### Verify Backup Integrity
```bash
# Test decompression
gunzip -t soccer_predictions_20251008_224941.sql.gz

# Check MD5
md5 soccer_predictions_20251008_224941.sql.gz
# Should output: 8a16b83cbea232cea328d5778cf57e6f
```

---

## Contact & Support

For questions about this backup or database structure:
- See [DATABASE_MODELS_IMPLEMENTATION.md](../../backend/docs/DATABASE_MODELS_IMPLEMENTATION.md)
- Check [DATA_PERSISTENCE_GUIDE.md](../../docker/DATA_PERSISTENCE_GUIDE.md)
- Review Alembic migrations in `backend/alembic/versions/`

---

**Last Updated**: 2025-10-08  
**Backup Created By**: Automated backup script  
**PostgreSQL Version**: 15-alpine  
**Database**: soccer_predictions  
**Migration**: 9b3c8646a52d

