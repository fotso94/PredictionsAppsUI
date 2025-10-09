# Data Persistence Architecture

## Overview

This document explains how data persistence works in the Soccer Predictions Platform's PostgreSQL setup.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Host (macOS)                          │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │              Docker Compose Network                           │ │
│  │              (soccer_predictions_network)                     │ │
│  │                                                               │ │
│  │  ┌─────────────────────────────────────────────────────┐     │ │
│  │  │  PostgreSQL Container                               │     │ │
│  │  │  (soccer_predictions_postgres)                      │     │ │
│  │  │                                                      │     │ │
│  │  │  ┌────────────────────────────────────────────┐    │     │ │
│  │  │  │  PostgreSQL Process                        │    │     │ │
│  │  │  │  - Port: 5432                              │    │     │ │
│  │  │  │  - User: postgres                          │    │     │ │
│  │  │  │  - Database: soccer_predictions            │    │     │ │
│  │  │  │                                            │    │     │ │
│  │  │  │  ┌──────────────────────────────────┐    │    │     │ │
│  │  │  │  │  Database Schemas                │    │    │     │ │
│  │  │  │  │  - users (18 tables)             │    │    │     │ │
│  │  │  │  │  - predictions (16 tables)       │    │    │     │ │
│  │  │  │  │  - ml_models (12 tables)         │    │    │     │ │
│  │  │  │  │  - analytics (13 tables)         │    │    │     │ │
│  │  │  │  │  - audit (8 tables)              │    │    │     │ │
│  │  │  │  └──────────────────────────────────┘    │    │     │ │
│  │  │  │                                            │    │     │ │
│  │  │  │  Data Directory: /var/lib/postgresql/data │    │     │ │
│  │  │  │         ↓ (mounted from volume)           │    │     │ │
│  │  │  └────────────────────────────────────────────┘    │     │ │
│  │  │                                                      │     │ │
│  │  └──────────────────────────────────────────────────────┘     │ │
│  │                           ↓                                    │ │
│  │                    Volume Mount                                │ │
│  │                           ↓                                    │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              ↓                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Docker Volume                                                │ │
│  │  Name: soccer_predictions_postgres_data                      │ │
│  │  Driver: local                                               │ │
│  │  Location: /var/lib/docker/volumes/                          │ │
│  │            soccer_predictions_postgres_data/_data            │ │
│  │                                                               │ │
│  │  ┌─────────────────────────────────────────────────────┐    │ │
│  │  │  Persistent Storage                                 │    │ │
│  │  │  - All database files                               │    │ │
│  │  │  - WAL (Write-Ahead Log) files                      │    │ │
│  │  │  - Configuration files                              │    │ │
│  │  │  - Transaction logs                                 │    │ │
│  │  │  - Indexes                                          │    │ │
│  │  │                                                      │    │ │
│  │  │  ✅ Survives container stops/restarts               │    │ │
│  │  │  ✅ Survives container deletion                     │    │ │
│  │  │  ✅ Survives system reboots                         │    │ │
│  │  │  ✅ Independent of container lifecycle              │    │ │
│  │  └─────────────────────────────────────────────────────┘    │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### 1. Container Startup

```
docker-compose up -d postgres
         ↓
Docker creates/starts container
         ↓
Docker mounts volume: soccer_predictions_postgres_data
         ↓
PostgreSQL reads data from /var/lib/postgresql/data
         ↓
Database is ready with all existing data
```

### 2. Data Write Operation

```
Application writes data (INSERT/UPDATE)
         ↓
PostgreSQL writes to WAL (Write-Ahead Log)
         ↓
Data written to /var/lib/postgresql/data
         ↓
Docker volume persists the data
         ↓
Data is safe on disk
```

### 3. Container Stop/Restart

```
docker-compose down
         ↓
Container stops and is removed
         ↓
Volume remains intact (NOT deleted)
         ↓
docker-compose up -d
         ↓
New container created
         ↓
Same volume mounted
         ↓
All data is still there ✅
```

---

## Backup & Restore Flow

### Backup Process

```
./scripts/backup-database.sh
         ↓
Connect to running container
         ↓
Execute pg_dump inside container
         ↓
Read data from /var/lib/postgresql/data
         ↓
Generate SQL dump
         ↓
Compress with gzip
         ↓
Save to docker/backups/soccer_predictions_YYYYMMDD_HHMMSS.sql.gz
         ↓
Backup complete ✅
```

### Restore Process

```
./scripts/restore-database.sh backup.sql.gz
         ↓
Decompress backup file
         ↓
Connect to running container
         ↓
Execute psql inside container
         ↓
DROP existing database (if exists)
         ↓
CREATE new database
         ↓
Restore all schemas, tables, data
         ↓
Write to /var/lib/postgresql/data
         ↓
Docker volume persists the restored data
         ↓
Restore complete ✅
```

---

## Volume Lifecycle

### Volume Creation

```yaml
# docker-compose.yml
volumes:
  postgres_data:
    name: soccer_predictions_postgres_data
    driver: local
```

**When created**:
- First time running `docker-compose up`
- Or manually: `docker volume create soccer_predictions_postgres_data`

**Location**:
- macOS: `/var/lib/docker/volumes/soccer_predictions_postgres_data/_data`
- Linux: `/var/lib/docker/volumes/soccer_predictions_postgres_data/_data`
- Windows: `\\wsl$\docker-desktop-data\data\docker\volumes\soccer_predictions_postgres_data\_data`

### Volume Persistence

```
┌─────────────────────────────────────────────────────────┐
│  Container Lifecycle        │  Volume State             │
├─────────────────────────────────────────────────────────┤
│  docker-compose up          │  Volume created/mounted   │
│  Container running          │  Data being written       │
│  docker-compose stop        │  Volume persists ✅       │
│  docker-compose down        │  Volume persists ✅       │
│  docker rm container        │  Volume persists ✅       │
│  System reboot              │  Volume persists ✅       │
│  docker-compose down -v     │  Volume DELETED ❌        │
│  docker volume rm           │  Volume DELETED ❌        │
└─────────────────────────────────────────────────────────┘
```

---

## Migration Scenarios

### Scenario 1: Move to Another Machine (Same Docker)

```
Source Machine                    Target Machine
     │                                 │
     ├─ Create backup                  │
     │  (pg_dump)                      │
     │                                 │
     ├─ Transfer backup ──────────────>│
     │  (scp/rsync)                    │
     │                                 │
     │                                 ├─ Start PostgreSQL
     │                                 │  (docker-compose up)
     │                                 │
     │                                 ├─ Restore backup
     │                                 │  (psql < backup.sql)
     │                                 │
     │                                 ├─ Data restored ✅
```

### Scenario 2: Volume Export/Import

```
Source Machine                    Target Machine
     │                                 │
     ├─ Export volume                  │
     │  (tar volume data)              │
     │                                 │
     ├─ Transfer tar ─────────────────>│
     │                                 │
     │                                 ├─ Create volume
     │                                 │
     │                                 ├─ Import tar
     │                                 │  (extract to volume)
     │                                 │
     │                                 ├─ Start PostgreSQL
     │                                 │
     │                                 ├─ Data available ✅
```

### Scenario 3: Docker to Podman

```
Docker Machine                    Podman Machine
     │                                 │
     ├─ Create backup                  │
     │  (pg_dump)                      │
     │                                 │
     ├─ Transfer backup ──────────────>│
     │                                 │
     │                                 ├─ Start PostgreSQL
     │                                 │  (podman-compose up)
     │                                 │
     │                                 ├─ Restore backup
     │                                 │  (psql < backup.sql)
     │                                 │
     │                                 ├─ Data restored ✅
```

---

## Storage Breakdown

### What's Stored in the Volume

```
/var/lib/postgresql/data/
├── base/                    # Database files
│   ├── 1/                   # Template database
│   ├── 13761/               # postgres database
│   └── 16384/               # soccer_predictions database
│       ├── users schema files
│       ├── predictions schema files
│       ├── ml_models schema files
│       ├── analytics schema files
│       └── audit schema files
├── global/                  # Cluster-wide tables
├── pg_wal/                  # Write-Ahead Log files
├── pg_xact/                 # Transaction commit status
├── pg_multixact/            # Multitransaction status
├── pg_stat/                 # Statistics files
├── pg_tblspc/               # Tablespace symbolic links
├── postgresql.conf          # Configuration
├── pg_hba.conf              # Host-based authentication
└── postmaster.pid           # Process ID file
```

### Current Storage Usage

```bash
# Check volume size
docker system df -v | grep soccer_predictions_postgres_data

# Typical sizes:
# - Empty database: ~40 MB
# - With sample data: ~100-500 MB
# - Production (1M users): ~5-50 GB
```

---

## Best Practices Summary

### ✅ DO

1. **Regular Backups**
   ```bash
   # Daily automated backups
   0 2 * * * cd /path/to/docker && ./scripts/backup-database.sh
   ```

2. **Test Restores**
   ```bash
   # Monthly restore test
   ./scripts/restore-database.sh backups/latest.sql.gz
   ```

3. **Off-site Storage**
   ```bash
   # Copy to cloud storage
   aws s3 cp backups/ s3://your-bucket/db-backups/ --recursive
   ```

4. **Monitor Volume**
   ```bash
   # Check volume health
   docker volume inspect soccer_predictions_postgres_data
   ```

### ❌ DON'T

1. **Don't use `-v` flag carelessly**
   ```bash
   # ❌ This deletes volumes!
   docker-compose down -v
   
   # ✅ Use this instead
   docker-compose down
   ```

2. **Don't rely on volume alone**
   - Always have backups
   - Store backups off-site
   - Test restore process

3. **Don't skip backups before changes**
   ```bash
   # ❌ Don't do this
   alembic upgrade head
   
   # ✅ Do this
   ./scripts/backup-database.sh && alembic upgrade head
   ```

---

## Monitoring & Alerts

### Health Checks

```bash
# Container health
docker ps --filter name=soccer_predictions_postgres --format "{{.Status}}"

# Volume exists
docker volume ls | grep soccer_predictions_postgres_data

# Database accessible
docker exec soccer_predictions_postgres pg_isready -U postgres

# Data integrity
docker exec soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT COUNT(*) FROM users.alembic_version;"
```

### Automated Monitoring Script

```bash
#!/bin/bash
# Save as: docker/scripts/monitor-database.sh

# Check container
if ! docker ps | grep -q soccer_predictions_postgres; then
    echo "❌ PostgreSQL container not running!"
    exit 1
fi

# Check volume
if ! docker volume ls | grep -q soccer_predictions_postgres_data; then
    echo "❌ PostgreSQL volume not found!"
    exit 1
fi

# Check database
if ! docker exec soccer_predictions_postgres pg_isready -U postgres > /dev/null 2>&1; then
    echo "❌ PostgreSQL not accepting connections!"
    exit 1
fi

echo "✅ All checks passed"
```

---

## Recovery Scenarios

### Scenario 1: Accidental Data Deletion

```bash
# 1. Stop container immediately
docker stop soccer_predictions_postgres

# 2. Restore from latest backup
./scripts/restore-database.sh backups/latest.sql.gz

# 3. Verify data
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions
```

### Scenario 2: Volume Corruption

```bash
# 1. Create backup of corrupted volume (if possible)
docker run --rm -v soccer_predictions_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/corrupted_volume.tar.gz -C /data .

# 2. Stop and remove container
docker-compose down

# 3. Remove corrupted volume
docker volume rm soccer_predictions_postgres_data

# 4. Recreate and restore
docker-compose up -d postgres
./scripts/restore-database.sh backups/latest.sql.gz
```

### Scenario 3: Disk Full

```bash
# 1. Check disk usage
df -h
docker system df

# 2. Clean up old backups
find docker/backups/ -name "*.sql.gz" -mtime +30 -delete

# 3. Clean up Docker
docker system prune -a

# 4. If still full, move volume to larger disk
# (Advanced - requires stopping services and copying data)
```

---

## Summary

**Key Points**:
1. ✅ Data is persistent via Docker volumes
2. ✅ Survives container lifecycle events
3. ✅ Automated backup/restore scripts available
4. ✅ Multiple migration paths supported
5. ✅ Monitoring and recovery procedures documented

**Volume Location**: `/var/lib/docker/volumes/soccer_predictions_postgres_data/_data`  
**Backup Location**: `docker/backups/`  
**Current Size**: ~40 KB (empty database)  
**Total Tables**: 67 across 5 schemas  

**Next Steps**:
1. Test backup: `cd docker && ./scripts/backup-database.sh`
2. Test restore: Create test environment and restore
3. Set up automated backups (cron job)
4. Configure off-site backup storage
5. Document your backup schedule

---

**Last Updated**: 2025-10-08  
**PostgreSQL Version**: 15-alpine  
**Docker Compose Version**: 3.8  
**Volume Driver**: local

