# Quick Backup & Restore Reference

## 🎯 TL;DR - Your Data is Safe!

✅ **Your PostgreSQL data IS persistent** - it survives container stops/restarts  
✅ **Volume configured**: `soccer_predictions_postgres_data`  
✅ **Backup scripts ready**: Located in `docker/scripts/`  

---

## 📦 Quick Commands

### Create Backup
```bash
cd docker
./scripts/backup-database.sh
```
**Output**: `backups/soccer_predictions_YYYYMMDD_HHMMSS.sql.gz`

### Restore Backup
```bash
cd docker
./scripts/restore-database.sh backups/soccer_predictions_20251008_223847.sql.gz
```

### List Backups
```bash
ls -lh docker/backups/
```

---

## 🔍 Check Data Persistence

### Verify Volume Exists
```bash
docker volume ls | grep soccer
# Should show: soccer_predictions_postgres_data
```

### Test Persistence
```bash
# 1. Check current data
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT COUNT(*) FROM users.users;"

# 2. Restart container
docker restart soccer_predictions_postgres

# 3. Verify data still exists (same count)
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT COUNT(*) FROM users.users;"
```

---

## ⚠️ Safe vs Dangerous Operations

### ✅ SAFE (Data Persists)
```bash
docker stop soccer_predictions_postgres
docker restart soccer_predictions_postgres
docker-compose down
docker-compose up -d
docker-compose restart
```

### ❌ DANGEROUS (Data Loss)
```bash
docker-compose down -v              # -v removes volumes!
docker volume rm soccer_predictions_postgres_data
docker volume prune -a
```

---

## 🚀 Common Scenarios

### Before Running Migrations
```bash
cd docker
./scripts/backup-database.sh
cd ../backend
alembic upgrade head
```

### Before Major Changes
```bash
# 1. Backup
cd docker && ./scripts/backup-database.sh

# 2. Make changes
# ... your work ...

# 3. If something goes wrong, restore
./scripts/restore-database.sh backups/latest_backup.sql.gz
```

### Moving to Another Machine
```bash
# On source machine:
cd docker
./scripts/backup-database.sh
scp backups/soccer_predictions_*.sql.gz user@new-machine:/path/

# On new machine:
cd /path/docker
docker-compose up -d postgres
./scripts/restore-database.sh backups/soccer_predictions_*.sql.gz
```

---

## 📊 Backup Contents

Each backup includes:
- ✅ All 5 schemas (users, predictions, ml_models, analytics, audit)
- ✅ All 67 tables
- ✅ All data
- ✅ All indexes and constraints
- ✅ All enum types
- ✅ Database structure

**Backup size**: ~40KB (compressed, empty database)  
**Backup format**: PostgreSQL SQL dump (gzipped)

---

## 🔧 Manual Backup (Advanced)

### Full Database Backup
```bash
docker exec -t soccer_predictions_postgres pg_dump \
  -U postgres -d soccer_predictions \
  --clean --if-exists --create \
  | gzip > backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Specific Schema Only
```bash
docker exec -t soccer_predictions_postgres pg_dump \
  -U postgres -d soccer_predictions \
  --schema=users \
  | gzip > users_backup_$(date +%Y%m%d_%H%M%S).sql.gz
```

### Custom Format (Faster Restore)
```bash
docker exec -t soccer_predictions_postgres pg_dump \
  -U postgres -d soccer_predictions \
  -Fc > backup_$(date +%Y%m%d_%H%M%S).dump
```

---

## 🔧 Manual Restore (Advanced)

### From Compressed SQL
```bash
gunzip -c backup.sql.gz | \
  docker exec -i soccer_predictions_postgres \
  psql -U postgres -d postgres
```

### From Custom Format
```bash
docker exec -i soccer_predictions_postgres pg_restore \
  -U postgres -d soccer_predictions \
  --clean --if-exists \
  < backup.dump
```

---

## 🆘 Emergency Recovery

### If You Accidentally Deleted Data

```bash
# 1. STOP container immediately
docker stop soccer_predictions_postgres

# 2. Restore from latest backup
cd docker
./scripts/restore-database.sh backups/$(ls -t backups/*.sql.gz | head -1)

# 3. Verify data
docker exec -it soccer_predictions_postgres psql \
  -U postgres -d soccer_predictions \
  -c "SELECT COUNT(*) FROM users.users;"
```

### If Container Won't Start

```bash
# 1. Check logs
docker logs soccer_predictions_postgres

# 2. Check volume
docker volume inspect soccer_predictions_postgres_data

# 3. If volume corrupted, restore from backup
docker-compose down
docker volume rm soccer_predictions_postgres_data
docker-compose up -d postgres
cd docker && ./scripts/restore-database.sh backups/latest.sql.gz
```

---

## 📅 Recommended Backup Schedule

### Development
- **Before migrations**: Always
- **Weekly**: Every Friday
- **Before major changes**: Always

### Production
- **Daily**: Automated at 2 AM
- **Weekly**: Full backup to external storage
- **Monthly**: Archive to long-term storage
- **Before deployments**: Always

---

## 🔗 Quick Links

- **Full Guide**: [DATA_PERSISTENCE_GUIDE.md](./DATA_PERSISTENCE_GUIDE.md)
- **Docker Docs**: [README.md](./README.md)
- **Backup Script**: [scripts/backup-database.sh](./scripts/backup-database.sh)
- **Restore Script**: [scripts/restore-database.sh](./scripts/restore-database.sh)

---

## 📞 Troubleshooting

### Backup Script Fails
```bash
# Check container is running
docker ps | grep postgres

# Check disk space
df -h

# Check permissions
ls -la docker/backups/
```

### Restore Script Fails
```bash
# Verify backup file
gunzip -t backups/backup.sql.gz

# Check PostgreSQL logs
docker logs soccer_predictions_postgres

# Try manual restore with verbose output
gunzip -c backups/backup.sql.gz | \
  docker exec -i soccer_predictions_postgres \
  psql -U postgres -d postgres --echo-errors
```

### Volume Not Found
```bash
# List all volumes
docker volume ls

# Recreate volume
docker volume create soccer_predictions_postgres_data

# Restore from backup
cd docker && ./scripts/restore-database.sh backups/latest.sql.gz
```

---

## ✅ Verification Checklist

After restore, verify:

```bash
# 1. Check schemas
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "\dn"

# 2. Check tables count
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "
SELECT schemaname, COUNT(*) 
FROM pg_tables 
WHERE schemaname IN ('users', 'predictions', 'ml_models', 'analytics', 'audit') 
GROUP BY schemaname 
ORDER BY schemaname;"

# 3. Check alembic version
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT * FROM users.alembic_version;"

# 4. Verify data (if you have any)
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT COUNT(*) FROM users.users;"
```

Expected results:
- 5 schemas: analytics, audit, ml_models, predictions, users
- 67 total tables (18 users, 16 predictions, 12 ml_models, 13 analytics, 8 audit)
- Alembic version: 9b3c8646a52d

---

## 🎓 Key Takeaways

1. **Your data is persistent** - Docker volumes ensure data survives container lifecycle
2. **Backup before changes** - Always backup before migrations or major changes
3. **Test your restores** - Regularly verify backups can be restored
4. **Automate backups** - Set up cron jobs for production
5. **Store off-site** - Keep backups in cloud storage for disaster recovery

---

**Last Updated**: 2025-10-08  
**Database Version**: PostgreSQL 15  
**Alembic Version**: 9b3c8646a52d  
**Total Tables**: 67 across 5 schemas

