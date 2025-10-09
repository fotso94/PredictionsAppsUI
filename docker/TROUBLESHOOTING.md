# Docker Troubleshooting Guide
## Soccer Predictions Platform - Common Issues and Solutions

**Version**: 1.0  
**Created**: 2025-10-08  
**Jira Task**: KAN-30

---

## 📋 Table of Contents

1. [Service Startup Issues](#service-startup-issues)
2. [Connection Problems](#connection-problems)
3. [Performance Issues](#performance-issues)
4. [Data Persistence Issues](#data-persistence-issues)
5. [Configuration Issues](#configuration-issues)
6. [Debugging Tools](#debugging-tools)

---

## 🚨 Service Startup Issues

### Issue: Services Won't Start

**Symptoms:**
- `docker-compose up` fails
- Containers exit immediately
- Error messages in logs

**Diagnosis:**

```bash
# Check Docker is running
docker info

# Check for port conflicts
lsof -i :5432  # PostgreSQL
lsof -i :6379  # Redis
lsof -i :8080  # Adminer

# Check Docker Compose file syntax
docker-compose config
```

**Solutions:**

1. **Port Already in Use:**
   ```bash
   # Find process using port
   lsof -i :5432
   
   # Kill process (replace PID)
   kill -9 <PID>
   
   # Or change port in docker-compose.yml
   ports:
     - "5433:5432"  # Use different host port
   ```

2. **Docker Desktop Not Running:**
   - Start Docker Desktop application
   - Wait for Docker to fully start
   - Retry `docker-compose up`

3. **Insufficient Resources:**
   - Docker Desktop → Settings → Resources
   - Increase CPU to 4+ cores
   - Increase Memory to 8GB+
   - Click "Apply & Restart"

4. **Corrupted Docker State:**
   ```bash
   # Clean up Docker
   docker-compose down -v
   docker system prune -a
   docker volume prune
   
   # Restart Docker Desktop
   # Retry docker-compose up
   ```

### Issue: Container Exits Immediately

**Symptoms:**
- Container starts then stops
- Status shows "Exited (1)" or "Exited (137)"

**Diagnosis:**

```bash
# Check container logs
docker-compose logs postgres
docker-compose logs redis

# Check container exit code
docker-compose ps
```

**Solutions:**

1. **Exit Code 1 (Configuration Error):**
   ```bash
   # Check configuration files
   cat docker/postgres/conf/postgresql.conf
   cat docker/redis/redis.conf
   
   # Look for syntax errors in logs
   docker-compose logs postgres | grep -i error
   ```

2. **Exit Code 137 (Out of Memory):**
   ```bash
   # Increase Docker memory limit
   # Docker Desktop → Settings → Resources → Memory
   
   # Or reduce service memory usage
   # Edit docker-compose.yml and add:
   deploy:
     resources:
       limits:
         memory: 512M
   ```

3. **Initialization Script Errors:**
   ```bash
   # Check init script
   cat docker/postgres/init/01-init-database.sql
   
   # Test SQL syntax
   docker-compose exec postgres psql -U postgres -d soccer_predictions -f /docker-entrypoint-initdb.d/01-init-database.sql
   ```

---

## 🔌 Connection Problems

### Issue: Cannot Connect to PostgreSQL

**Symptoms:**
- Connection refused
- Timeout errors
- "could not connect to server"

**Diagnosis:**

```bash
# Check service is running
docker-compose ps postgres

# Check health status
docker-compose ps | grep postgres

# Test connection from host
psql -h localhost -p 5432 -U postgres -d soccer_predictions

# Test connection from container
docker-compose exec postgres pg_isready -U postgres
```

**Solutions:**

1. **Service Not Ready:**
   ```bash
   # Wait for health check to pass
   docker-compose ps
   # Look for "healthy" status
   
   # Check logs for startup progress
   docker-compose logs -f postgres
   ```

2. **Wrong Connection Parameters:**
   ```bash
   # From host machine:
   Host: localhost
   Port: 5432
   User: postgres
   Password: postgres123
   Database: soccer_predictions
   
   # From another container:
   Host: postgres  # Use container name
   Port: 5432
   User: postgres
   Password: postgres123
   Database: soccer_predictions
   ```

3. **Firewall Blocking Connection:**
   ```bash
   # Check firewall rules (macOS)
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
   
   # Allow Docker in firewall
   # System Preferences → Security & Privacy → Firewall → Firewall Options
   # Add Docker.app
   ```

4. **PostgreSQL Not Listening:**
   ```bash
   # Check PostgreSQL is listening
   docker-compose exec postgres netstat -an | grep 5432
   
   # Check PostgreSQL configuration
   docker-compose exec postgres cat /var/lib/postgresql/data/postgresql.conf | grep listen_addresses
   ```

### Issue: Cannot Connect to Redis

**Symptoms:**
- Connection refused
- "Could not connect to Redis"
- Timeout errors

**Diagnosis:**

```bash
# Check service is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping
# Should return: PONG

# Check from host
redis-cli -h localhost -p 6379 ping
```

**Solutions:**

1. **Service Not Running:**
   ```bash
   # Start Redis
   docker-compose up -d redis
   
   # Check logs
   docker-compose logs redis
   ```

2. **Wrong Connection Parameters:**
   ```bash
   # From host machine:
   Host: localhost
   Port: 6379
   
   # From another container:
   Host: redis  # Use container name
   Port: 6379
   ```

3. **Redis Configuration Error:**
   ```bash
   # Check configuration
   docker-compose exec redis cat /usr/local/etc/redis/redis.conf
   
   # Look for bind and protected-mode settings
   # Should be:
   # bind 0.0.0.0
   # protected-mode no
   ```

### Issue: Adminer Cannot Connect to Database

**Symptoms:**
- "Unable to connect" error in Adminer
- Login fails

**Diagnosis:**

```bash
# Check Adminer is running
docker-compose ps adminer

# Check PostgreSQL is healthy
docker-compose ps postgres

# Check network connectivity
docker-compose exec adminer ping postgres
```

**Solutions:**

1. **Wrong Server Name:**
   - Use `postgres` (not `localhost` or `127.0.0.1`)
   - Adminer connects through Docker network

2. **Wrong Credentials:**
   ```
   System: PostgreSQL
   Server: postgres
   Username: postgres
   Password: postgres123
   Database: soccer_predictions
   ```

3. **PostgreSQL Not Ready:**
   ```bash
   # Wait for PostgreSQL to be healthy
   docker-compose ps postgres
   
   # Restart Adminer after PostgreSQL is ready
   docker-compose restart adminer
   ```

---

## ⚡ Performance Issues

### Issue: Slow Query Performance

**Symptoms:**
- Queries take longer than expected
- Database feels sluggish

**Diagnosis:**

```bash
# Check slow query log
docker-compose exec postgres tail -f /var/lib/postgresql/data/pg_log/*.log | grep "duration:"

# Check active connections
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT count(*) FROM pg_stat_activity;"

# Check table sizes
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"
```

**Solutions:**

1. **Missing Indexes:**
   ```sql
   -- Check for missing indexes
   SELECT schemaname, tablename, attname, n_distinct, correlation
   FROM pg_stats
   WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
   ORDER BY abs(correlation) DESC;
   
   -- Create indexes as needed (will be done via Alembic migrations)
   ```

2. **Too Many Connections:**
   ```bash
   # Check connection count
   docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT count(*) FROM pg_stat_activity;"
   
   # Increase max_connections in postgresql.conf if needed
   # Edit docker/postgres/conf/postgresql.conf
   max_connections = 300
   
   # Restart PostgreSQL
   docker-compose restart postgres
   ```

3. **Insufficient Resources:**
   ```bash
   # Check Docker stats
   docker stats
   
   # Increase Docker resources
   # Docker Desktop → Settings → Resources
   ```

4. **Need VACUUM:**
   ```bash
   # Run VACUUM ANALYZE
   docker-compose exec postgres psql -U postgres -d soccer_predictions -c "VACUUM ANALYZE;"
   ```

### Issue: Redis Memory Issues

**Symptoms:**
- Redis evicting keys unexpectedly
- Out of memory errors

**Diagnosis:**

```bash
# Check memory usage
docker-compose exec redis redis-cli INFO memory

# Check eviction stats
docker-compose exec redis redis-cli INFO stats | grep evicted

# Check key count
docker-compose exec redis redis-cli DBSIZE
```

**Solutions:**

1. **Increase Max Memory:**
   ```bash
   # Edit docker/redis/redis.conf
   maxmemory 1gb  # Increase from 512mb
   
   # Restart Redis
   docker-compose restart redis
   ```

2. **Change Eviction Policy:**
   ```bash
   # Edit docker/redis/redis.conf
   maxmemory-policy volatile-lru  # Only evict keys with TTL
   
   # Restart Redis
   docker-compose restart redis
   ```

3. **Set TTL on Keys:**
   ```bash
   # Set expiration on keys
   docker-compose exec redis redis-cli EXPIRE key_name 3600
   
   # Or use SETEX when creating keys
   docker-compose exec redis redis-cli SETEX key_name 3600 "value"
   ```

---

## 💾 Data Persistence Issues

### Issue: Data Lost After Restart

**Symptoms:**
- Database is empty after `docker-compose down`
- Redis cache is empty after restart

**Diagnosis:**

```bash
# Check if volumes exist
docker volume ls | grep soccer_predictions

# Inspect volume
docker volume inspect soccer_predictions_postgres_data
docker volume inspect soccer_predictions_redis_data
```

**Solutions:**

1. **Don't Use `-v` Flag:**
   ```bash
   # WRONG (deletes volumes):
   docker-compose down -v
   
   # CORRECT (keeps volumes):
   docker-compose down
   ```

2. **Recreate Volumes:**
   ```bash
   # If volumes were deleted, recreate them
   docker volume create soccer_predictions_postgres_data
   docker volume create soccer_predictions_redis_data
   
   # Restore from backup
   docker-compose up -d postgres
   docker-compose exec -T postgres psql -U postgres -d soccer_predictions < backup.sql
   ```

3. **Check Volume Mounts:**
   ```bash
   # Verify volumes are mounted
   docker-compose exec postgres df -h | grep postgresql
   docker-compose exec redis df -h | grep data
   ```

### Issue: Cannot Restore Backup

**Symptoms:**
- Restore command fails
- Data not appearing after restore

**Diagnosis:**

```bash
# Check backup file exists
ls -lh backup.sql

# Check backup file format
head -n 20 backup.sql

# Check PostgreSQL is running
docker-compose ps postgres
```

**Solutions:**

1. **Use Correct Restore Command:**
   ```bash
   # For SQL dump
   docker-compose exec -T postgres psql -U postgres -d soccer_predictions < backup.sql
   
   # For custom format
   docker-compose exec postgres pg_restore -U postgres -d soccer_predictions /path/to/backup.dump
   ```

2. **Create Database First:**
   ```bash
   # If database doesn't exist
   docker-compose exec postgres createdb -U postgres soccer_predictions
   
   # Then restore
   docker-compose exec -T postgres psql -U postgres -d soccer_predictions < backup.sql
   ```

3. **Check Permissions:**
   ```bash
   # Ensure backup file is readable
   chmod 644 backup.sql
   
   # Retry restore
   docker-compose exec -T postgres psql -U postgres -d soccer_predictions < backup.sql
   ```

---

## ⚙️ Configuration Issues

### Issue: Configuration Changes Not Applied

**Symptoms:**
- Changes to config files don't take effect
- Service still using old configuration

**Diagnosis:**

```bash
# Check if config file is mounted
docker-compose exec postgres ls -l /etc/postgresql/conf.d/
docker-compose exec redis ls -l /usr/local/etc/redis/

# Check current configuration
docker-compose exec postgres psql -U postgres -c "SHOW shared_buffers;"
docker-compose exec redis redis-cli CONFIG GET maxmemory
```

**Solutions:**

1. **Restart Service:**
   ```bash
   # Restart to apply changes
   docker-compose restart postgres
   docker-compose restart redis
   ```

2. **Rebuild Container:**
   ```bash
   # If restart doesn't work, rebuild
   docker-compose up -d --build postgres
   docker-compose up -d --build redis
   ```

3. **Check File Permissions:**
   ```bash
   # Ensure config files are readable
   chmod 644 docker/postgres/conf/postgresql.conf
   chmod 644 docker/redis/redis.conf
   ```

---

## 🔍 Debugging Tools

### Useful Commands

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f postgres
docker-compose logs -f redis

# Execute commands in container
docker-compose exec postgres bash
docker-compose exec redis sh

# Check resource usage
docker stats

# Inspect container
docker inspect soccer_predictions_postgres

# Check network
docker network inspect soccer_predictions_network

# Check volumes
docker volume inspect soccer_predictions_postgres_data
```

### PostgreSQL Debugging

```bash
# Connect to database
docker-compose exec postgres psql -U postgres -d soccer_predictions

# Check active queries
SELECT pid, usename, application_name, client_addr, state, query
FROM pg_stat_activity
WHERE state != 'idle';

# Check locks
SELECT * FROM pg_locks WHERE NOT granted;

# Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Redis Debugging

```bash
# Connect to Redis
docker-compose exec redis redis-cli

# Check memory
INFO memory

# Check stats
INFO stats

# Monitor commands
MONITOR

# Check slow log
SLOWLOG GET 10
```

---

## 📞 Getting Help

If you're still experiencing issues:

1. **Check Logs:**
   ```bash
   docker-compose logs -f > debug.log
   ```

2. **Gather System Info:**
   ```bash
   docker version
   docker-compose version
   docker info
   ```

3. **Create Issue:**
   - Include error messages
   - Include relevant logs
   - Include steps to reproduce
   - Include system information

---

## 🔗 Related Documentation

- [Docker README](./README.md)
- [Docker Architecture](./DOCKER_ARCHITECTURE.md)
- [Database Schema Documentation](../docs/database/README.md)

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Backend Development Team


