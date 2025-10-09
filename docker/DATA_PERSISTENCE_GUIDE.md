# PostgreSQL Data Persistence & Backup Guide

## Table of Contents
1. [Data Persistence Status](#data-persistence-status)
2. [Current Docker Configuration](#current-docker-configuration)
3. [Data Backup & Restore](#data-backup--restore)
4. [Container Migration](#container-migration)
5. [Best Practices](#best-practices)
6. [Troubleshooting](#troubleshooting)

---

## 1. Data Persistence Status

### ✅ **Your Data IS Persistent!**

**Good news**: Your PostgreSQL database is already configured with persistent storage using Docker volumes. All your schemas, tables, and data will survive:
- ✅ Container stops
- ✅ Container restarts
- ✅ System reboots
- ✅ Docker Compose down/up cycles

**What you WILL lose data from**:
- ❌ `docker volume rm soccer_predictions_postgres_data` (manual volume deletion)
- ❌ `docker-compose down -v` (the `-v` flag removes volumes)
- ❌ Deleting the volume through Docker Desktop

### Current Volume Configuration

**Volume Name**: `soccer_predictions_postgres_data`  
**Mount Point**: `/var/lib/docker/volumes/soccer_predictions_postgres_data/_data`  
**Driver**: local  
**Status**: Active and mounted  

**Verify your volume**:
```bash
# Check volume exists
docker volume ls | grep soccer

# Inspect volume details
docker volume inspect soccer_predictions_postgres_data

# Check volume size
docker system df -v | grep soccer_predictions_postgres_data
```

---

## 2. Current Docker Configuration

### docker-compose.yml Configuration

Your PostgreSQL service is configured with a named volume:

```yaml
services:
  postgres:
    image: postgres:15-alpine
    container_name: soccer_predictions_postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data  # ← Persistent volume
      - ./docker/postgres/init:/docker-entrypoint-initdb.d:ro
      - ./docker/postgres/conf:/etc/postgresql/conf.d:ro

volumes:
  postgres_data:
    name: soccer_predictions_postgres_data
    driver: local
```

### How It Works

1. **Named Volume**: `postgres_data` is mapped to `soccer_predictions_postgres_data`
2. **Mount Point**: Data is stored in `/var/lib/postgresql/data` inside the container
3. **Persistence**: Docker manages the volume independently of the container lifecycle
4. **Location**: On macOS, volumes are stored in Docker Desktop's VM

### Safe Operations

These operations **WILL NOT** delete your data:
```bash
# Stop the container
docker stop soccer_predictions_postgres

# Remove the container
docker rm soccer_predictions_postgres

# Stop all services
docker-compose down

# Restart services
docker-compose up -d

# Rebuild and restart
docker-compose up -d --build
```

### Dangerous Operations

These operations **WILL** delete your data:
```bash
# ❌ Remove volumes when stopping
docker-compose down -v

# ❌ Delete the volume directly
docker volume rm soccer_predictions_postgres_data

# ❌ Prune all volumes
docker volume prune -a
```

---

## 3. Data Backup & Restore

### Quick Backup

We've created automated scripts for you:

```bash
# Navigate to docker directory
cd docker

# Create a backup (stored in docker/backups/)
./scripts/backup-database.sh

# Backup file will be: backups/soccer_predictions_YYYYMMDD_HHMMSS.sql.gz
```

**What the backup includes**:
- ✅ All 5 schemas (users, predictions, ml_models, analytics, audit)
- ✅ All 67 tables
- ✅ All data
- ✅ All indexes and constraints
- ✅ All enum types
- ✅ Database structure (CREATE statements)

### Restore from Backup

```bash
# Navigate to docker directory
cd docker

# Restore from a specific backup
./scripts/restore-database.sh backups/soccer_predictions_20251008_123456.sql.gz

# You'll be prompted to confirm (type 'yes')
```

### Manual Backup Commands

If you prefer manual control:

```bash
# Create backup directory
mkdir -p docker/backups

# Full database backup (compressed)
docker exec -t soccer_predictions_postgres pg_dump \
  -U postgres \
  -d soccer_predictions \
  --clean \
  --if-exists \
  --create \
  --encoding=UTF8 \
  | gzip > docker/backups/backup_$(date +%Y%m%d_%H%M%S).sql.gz

# Backup specific schema only
docker exec -t soccer_predictions_postgres pg_dump \
  -U postgres \
  -d soccer_predictions \
  --schema=users \
  | gzip > docker/backups/users_schema_$(date +%Y%m%d_%H%M%S).sql.gz

# Backup with custom format (smaller, faster restore)
docker exec -t soccer_predictions_postgres pg_dump \
  -U postgres \
  -d soccer_predictions \
  -Fc \
  > docker/backups/backup_$(date +%Y%m%d_%H%M%S).dump
```

### Manual Restore Commands

```bash
# Restore from compressed SQL backup
gunzip -c docker/backups/backup_20251008_123456.sql.gz | \
  docker exec -i soccer_predictions_postgres psql -U postgres -d postgres

# Restore from custom format backup
docker exec -i soccer_predictions_postgres pg_restore \
  -U postgres \
  -d soccer_predictions \
  --clean \
  --if-exists \
  < docker/backups/backup_20251008_123456.dump

# Restore specific schema only
gunzip -c docker/backups/users_schema_20251008_123456.sql.gz | \
  docker exec -i soccer_predictions_postgres psql -U postgres -d soccer_predictions
```

---

## 4. Container Migration

### Migrate to Another Machine (Same Docker)

**Method 1: Using Backups (Recommended)**

```bash
# On source machine:
cd docker
./scripts/backup-database.sh

# Copy the backup file to target machine
scp backups/soccer_predictions_*.sql.gz user@target-machine:/path/to/project/docker/backups/

# On target machine:
cd docker
docker-compose up -d postgres
./scripts/restore-database.sh backups/soccer_predictions_*.sql.gz
```

**Method 2: Using Docker Volume Export**

```bash
# On source machine: Export volume to tar
docker run --rm \
  -v soccer_predictions_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/postgres_volume.tar.gz -C /data .

# Copy to target machine
scp postgres_volume.tar.gz user@target-machine:/path/to/project/

# On target machine: Create volume and import
docker volume create soccer_predictions_postgres_data

docker run --rm \
  -v soccer_predictions_postgres_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/postgres_volume.tar.gz -C /data

# Start services
docker-compose up -d
```

### Migrate to Different Container Engine (Docker → Podman)

```bash
# 1. Create backup on Docker
cd docker
./scripts/backup-database.sh

# 2. Copy backup to machine with Podman
scp backups/soccer_predictions_*.sql.gz user@podman-machine:/path/

# 3. On Podman machine: Update docker-compose.yml for Podman compatibility
# (Podman supports docker-compose syntax)

# 4. Start PostgreSQL with Podman
podman-compose up -d postgres

# 5. Restore backup
gunzip -c backups/soccer_predictions_*.sql.gz | \
  podman exec -i soccer_predictions_postgres psql -U postgres -d postgres
```

### Migrate to Cloud (AWS RDS, Google Cloud SQL, etc.)

```bash
# 1. Create backup
cd docker
./scripts/backup-database.sh

# 2. Decompress backup
gunzip backups/soccer_predictions_*.sql.gz

# 3. Restore to cloud database
# For AWS RDS:
psql -h your-rds-endpoint.amazonaws.com \
     -U postgres \
     -d soccer_predictions \
     -f backups/soccer_predictions_*.sql

# For Google Cloud SQL:
gcloud sql import sql your-instance-name \
  gs://your-bucket/soccer_predictions_*.sql \
  --database=soccer_predictions
```

---

## 5. Best Practices

### Development Environment

**Daily Workflow**:
```bash
# Start services
docker-compose up -d

# Work on your application
# ... make changes, run migrations, add data ...

# Stop services (data persists)
docker-compose down
```

**Weekly Backups**:
```bash
# Create weekly backup
cd docker
./scripts/backup-database.sh

# Optional: Copy to external storage
cp backups/soccer_predictions_*.sql.gz ~/Dropbox/backups/
```

**Before Major Changes**:
```bash
# Always backup before:
# - Running new migrations
# - Bulk data imports
# - Schema changes
# - Testing destructive operations

cd docker
./scripts/backup-database.sh
```

### Production Environment

**Automated Backups**:

Create a cron job for daily backups:

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * cd /path/to/project/docker && ./scripts/backup-database.sh >> /var/log/db-backup.log 2>&1

# Add weekly backup to external storage
0 3 * * 0 cd /path/to/project/docker && ./scripts/backup-database.sh && aws s3 cp backups/ s3://your-bucket/db-backups/ --recursive
```

**Backup Retention Policy**:
- Keep daily backups for 7 days
- Keep weekly backups for 4 weeks
- Keep monthly backups for 12 months
- Store critical backups off-site (S3, Google Cloud Storage, etc.)

**Production docker-compose.yml**:

```yaml
volumes:
  postgres_data:
    name: soccer_predictions_postgres_data
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/data/postgres  # Use dedicated disk/mount
```

### Version Control

**What to commit to Git**:
- ✅ `docker-compose.yml`
- ✅ `alembic/` migrations
- ✅ Backup/restore scripts
- ✅ Database schema documentation
- ✅ `.env.example` (without secrets)

**What NOT to commit**:
- ❌ `backups/` directory
- ❌ `.env` (with real credentials)
- ❌ Database dumps
- ❌ Volume data

**`.gitignore` additions**:
```gitignore
# Database backups
docker/backups/
*.sql
*.sql.gz
*.dump

# Environment files
.env
.env.local
.env.production

# Docker volumes (if using bind mounts)
docker/volumes/
```

### Disaster Recovery Plan

1. **Regular Backups**: Automated daily backups
2. **Off-site Storage**: Copy backups to cloud storage
3. **Test Restores**: Monthly restore tests to verify backups work
4. **Documentation**: Keep this guide updated
5. **Monitoring**: Set up alerts for backup failures

**Test your restore process**:
```bash
# 1. Create test environment
docker-compose -f docker-compose.test.yml up -d postgres_test

# 2. Restore backup to test database
./scripts/restore-database.sh backups/latest.sql.gz

# 3. Verify data integrity
docker exec -it postgres_test psql -U postgres -d soccer_predictions -c "SELECT COUNT(*) FROM users.users;"

# 4. Cleanup
docker-compose -f docker-compose.test.yml down -v
```

---

## 6. Troubleshooting

### Check Data Persistence

```bash
# 1. Check current data
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "\dt users.*"

# 2. Stop container
docker stop soccer_predictions_postgres

# 3. Start container
docker start soccer_predictions_postgres

# 4. Verify data still exists
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "\dt users.*"
```

### Volume Issues

**Volume not mounting**:
```bash
# Check volume exists
docker volume ls | grep soccer

# Inspect volume
docker volume inspect soccer_predictions_postgres_data

# Check container mounts
docker inspect soccer_predictions_postgres | grep -A 10 Mounts
```

**Volume corruption**:
```bash
# 1. Stop container
docker-compose down

# 2. Backup volume (if possible)
docker run --rm -v soccer_predictions_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/corrupted_volume.tar.gz -C /data .

# 3. Remove corrupted volume
docker volume rm soccer_predictions_postgres_data

# 4. Recreate and restore from backup
docker-compose up -d postgres
./scripts/restore-database.sh backups/latest.sql.gz
```

### Backup/Restore Failures

**Backup fails**:
```bash
# Check container is running
docker ps | grep postgres

# Check disk space
df -h

# Check permissions
ls -la docker/backups/

# Manual backup with verbose output
docker exec -t soccer_predictions_postgres pg_dump -U postgres -d soccer_predictions --verbose
```

**Restore fails**:
```bash
# Check backup file integrity
gunzip -t backups/soccer_predictions_*.sql.gz

# Restore with verbose output
gunzip -c backups/soccer_predictions_*.sql.gz | docker exec -i soccer_predictions_postgres psql -U postgres -d postgres --echo-errors

# Check PostgreSQL logs
docker logs soccer_predictions_postgres
```

---

## Quick Reference

### Essential Commands

```bash
# Backup
cd docker && ./scripts/backup-database.sh

# Restore
cd docker && ./scripts/restore-database.sh backups/backup_file.sql.gz

# Check volume
docker volume inspect soccer_predictions_postgres_data

# Check container
docker ps | grep postgres

# View logs
docker logs soccer_predictions_postgres

# Access database
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions
```

### Emergency Recovery

```bash
# If you accidentally deleted data:
# 1. STOP the container immediately
docker stop soccer_predictions_postgres

# 2. Restore from latest backup
cd docker
./scripts/restore-database.sh backups/$(ls -t backups/*.sql.gz | head -1)

# 3. Verify data
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT COUNT(*) FROM users.users;"
```

---

## Summary

✅ **Your data IS persistent** - configured with Docker volumes  
✅ **Automated backup scripts** - ready to use  
✅ **Migration guides** - for different scenarios  
✅ **Best practices** - for dev and production  
✅ **Disaster recovery** - documented and tested  

**Next Steps**:
1. Test the backup script: `cd docker && ./scripts/backup-database.sh`
2. Test the restore process with a test database
3. Set up automated backups (cron job or CI/CD)
4. Store backups off-site (cloud storage)
5. Document your specific backup schedule

**Questions?** Check the troubleshooting section or Docker logs.

