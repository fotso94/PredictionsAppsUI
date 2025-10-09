# Docker Quick Reference Guide
## Soccer Predictions Platform - Command Cheat Sheet

**Version**: 1.0  
**Created**: 2025-10-08  
**Jira Task**: KAN-30

---

## 🚀 Quick Start Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

---

## 📦 Service Management

### Start/Stop Services

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d postgres
docker-compose up -d redis
docker-compose up -d adminer

# Stop all services (keeps data)
docker-compose down

# Stop all services (DELETES data)
docker-compose down -v

# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart postgres
docker-compose restart redis
```

### View Logs

```bash
# All services (follow mode)
docker-compose logs -f

# Specific service
docker-compose logs -f postgres
docker-compose logs -f redis
docker-compose logs -f adminer

# Last 100 lines
docker-compose logs --tail=100 postgres

# Since specific time
docker-compose logs --since 2024-01-01T00:00:00
```

### Check Status

```bash
# List all services
docker-compose ps

# Check health status
docker-compose ps | grep healthy

# View resource usage
docker stats
```

---

## 🗄️ PostgreSQL Commands

### Connection

```bash
# Connect via psql
docker-compose exec postgres psql -U postgres -d soccer_predictions

# Connect from host (requires psql installed)
psql -h localhost -p 5432 -U postgres -d soccer_predictions
```

### Database Operations

```bash
# List databases
docker-compose exec postgres psql -U postgres -c "\l"

# List schemas
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "\dn"

# List tables in schema
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "\dt users.*"

# Describe table
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "\d users.users"

# Execute SQL file
docker-compose exec -T postgres psql -U postgres -d soccer_predictions < script.sql

# Execute SQL command
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT * FROM users.users LIMIT 10;"
```

### Backup & Restore

```bash
# Backup entire database
docker-compose exec postgres pg_dump -U postgres -d soccer_predictions > backup.sql

# Backup specific schema
docker-compose exec postgres pg_dump -U postgres -d soccer_predictions -n users > users_backup.sql

# Backup with custom format
docker-compose exec postgres pg_dump -U postgres -d soccer_predictions -Fc > backup.dump

# Restore from SQL dump
docker-compose exec -T postgres psql -U postgres -d soccer_predictions < backup.sql

# Restore from custom format
docker-compose exec postgres pg_restore -U postgres -d soccer_predictions /path/to/backup.dump
```

### Maintenance

```bash
# Vacuum database
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "VACUUM ANALYZE;"

# Reindex database
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "REINDEX DATABASE soccer_predictions;"

# Check database size
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT pg_size_pretty(pg_database_size('soccer_predictions'));"

# Check table sizes
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"
```

---

## 🔴 Redis Commands

### Connection

```bash
# Connect via redis-cli
docker-compose exec redis redis-cli

# Connect to specific database
docker-compose exec redis redis-cli -n 1

# Connect from host (requires redis-cli installed)
redis-cli -h localhost -p 6379
```

### Basic Operations

```bash
# Ping
docker-compose exec redis redis-cli ping

# Select database
docker-compose exec redis redis-cli SELECT 0

# List all keys
docker-compose exec redis redis-cli KEYS "*"

# Get value
docker-compose exec redis redis-cli GET key_name

# Set value
docker-compose exec redis redis-cli SET key_name "value"

# Set value with expiration (seconds)
docker-compose exec redis redis-cli SETEX key_name 3600 "value"

# Delete key
docker-compose exec redis redis-cli DEL key_name

# Check if key exists
docker-compose exec redis redis-cli EXISTS key_name

# Get TTL
docker-compose exec redis redis-cli TTL key_name
```

### Monitoring

```bash
# Get info
docker-compose exec redis redis-cli INFO

# Get memory info
docker-compose exec redis redis-cli INFO memory

# Get stats
docker-compose exec redis redis-cli INFO stats

# Monitor commands in real-time
docker-compose exec redis redis-cli MONITOR

# Check slow log
docker-compose exec redis redis-cli SLOWLOG GET 10
```

### Database Management

```bash
# Flush current database
docker-compose exec redis redis-cli FLUSHDB

# Flush all databases
docker-compose exec redis redis-cli FLUSHALL

# Save snapshot
docker-compose exec redis redis-cli BGSAVE

# Get last save time
docker-compose exec redis redis-cli LASTSAVE
```

---

## 🌐 Adminer Access

```bash
# Open in browser
open http://localhost:8081

# Login credentials
System: PostgreSQL
Server: postgres
Username: postgres
Password: postgres123
Database: soccer_predictions
```

---

## 🐳 Docker Management

### Container Operations

```bash
# List running containers
docker ps

# List all containers
docker ps -a

# Execute command in container
docker-compose exec postgres bash
docker-compose exec redis sh

# Copy file to container
docker cp file.txt soccer_predictions_postgres:/tmp/

# Copy file from container
docker cp soccer_predictions_postgres:/tmp/file.txt ./
```

### Volume Operations

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect soccer_predictions_postgres_data

# Remove unused volumes
docker volume prune

# Backup volume
docker run --rm -v soccer_predictions_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
```

### Network Operations

```bash
# List networks
docker network ls

# Inspect network
docker network inspect soccer_predictions_network

# Remove unused networks
docker network prune
```

### Cleanup

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove unused networks
docker network prune

# Remove everything unused
docker system prune -a --volumes
```

---

## 🔍 Debugging

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service with timestamps
docker-compose logs -f --timestamps postgres

# Last N lines
docker-compose logs --tail=50 postgres

# Save logs to file
docker-compose logs > debug.log
```

### Inspect Services

```bash
# Check service health
docker-compose ps

# Inspect container
docker inspect soccer_predictions_postgres

# Check resource usage
docker stats

# View container processes
docker-compose top postgres
```

### Network Debugging

```bash
# Test connectivity between containers
docker-compose exec adminer ping postgres
docker-compose exec backend ping redis

# Check open ports
docker-compose exec postgres netstat -tuln

# Check DNS resolution
docker-compose exec postgres nslookup redis
```

---

## 📊 Monitoring

### PostgreSQL Monitoring

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity;

-- Active queries
SELECT pid, usename, application_name, state, query
FROM pg_stat_activity
WHERE state != 'idle';

-- Database size
SELECT pg_size_pretty(pg_database_size('soccer_predictions'));

-- Table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;

-- Slow queries (from log)
-- Check docker-compose logs postgres | grep "duration:"
```

### Redis Monitoring

```bash
# Memory usage
docker-compose exec redis redis-cli INFO memory | grep used_memory_human

# Hit rate
docker-compose exec redis redis-cli INFO stats | grep keyspace

# Connected clients
docker-compose exec redis redis-cli INFO clients

# Commands per second
docker-compose exec redis redis-cli INFO stats | grep instantaneous_ops_per_sec
```

---

## 🔧 Configuration

### Update Configuration

```bash
# Edit PostgreSQL config
nano docker/postgres/conf/postgresql.conf

# Edit Redis config
nano docker/redis/redis.conf

# Restart service to apply changes
docker-compose restart postgres
docker-compose restart redis
```

### Environment Variables

```bash
# Create .env file
cat > .env << EOF
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=soccer_predictions
POSTGRES_PORT=5432
REDIS_PORT=6379
ADMINER_PORT=8080
EOF

# Use in docker-compose.yml
# ${POSTGRES_USER}
```

---

## 🆘 Emergency Commands

```bash
# Force stop all containers
docker-compose kill

# Remove all containers and volumes (NUCLEAR OPTION)
docker-compose down -v
docker system prune -a --volumes

# Restart Docker Desktop
# macOS: killall Docker && open /Applications/Docker.app
# Windows: Restart-Service docker

# Check Docker disk usage
docker system df

# Clean up disk space
docker system prune -a --volumes
```

---

## 📱 Useful Aliases

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
# Docker Compose shortcuts
alias dc='docker-compose'
alias dcu='docker-compose up -d'
alias dcd='docker-compose down'
alias dcl='docker-compose logs -f'
alias dcp='docker-compose ps'
alias dcr='docker-compose restart'

# PostgreSQL shortcuts
alias pgcli='docker-compose exec postgres psql -U postgres -d soccer_predictions'
alias pgdump='docker-compose exec postgres pg_dump -U postgres -d soccer_predictions'

# Redis shortcuts
alias rediscli='docker-compose exec redis redis-cli'
```

---

## 🔗 Quick Links

- **Adminer**: http://localhost:8081
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **Backend API** (future): http://localhost:8000

---

## 📚 Related Documentation

- [Docker README](./README.md) - Full documentation
- [Docker Architecture](./DOCKER_ARCHITECTURE.md) - Architecture details
- [Troubleshooting Guide](./TROUBLESHOOTING.md) - Problem solving
- [Database Schema](../docs/database/README.md) - Database documentation

---

**Status**: ✅ Complete  
**Last Updated**: 2025-10-08  
**Maintained By**: Backend Development Team


