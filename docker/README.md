# Docker Configuration for Soccer Predictions Platform
## Local Development Environment Setup

**Version**: 1.0  
**Created**: 2025-10-08  
**Jira Task**: KAN-30 - Set up Docker Compose for local development environment

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Services](#services)
5. [Configuration](#configuration)
6. [Database Management](#database-management)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Usage](#advanced-usage)

---

## 🎯 Overview

This Docker Compose configuration provides a complete local development environment for the Soccer Predictions Platform, including:

- **PostgreSQL 15**: Multi-schema database with initialization scripts
- **Redis 7**: Caching and session management
- **Adminer**: Web-based database management UI
- **Backend API**: the FastAPI application in `backend/` — it **is** implemented, but it is not
  started by this Compose file. Its service block in `docker/docker-compose.yml` is commented out,
  so the backend is run on the host (`uvicorn app.main:app --reload --port 8000`) against the
  PostgreSQL and Redis containers started here. See the root `README.md`.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Docker Network                              │
│              (soccer_predictions_network)                    │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  PostgreSQL  │  │    Redis     │  │   Adminer    │      │
│  │  Port: 5432  │  │  Port: 6379  │  │ Host: 8081   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                  │                  │             │
│         └──────────────────┴──────────────────┘             │
│                            │                                │
│                  ┌──────────────────┐                       │
│                  │  Backend API     │                       │
│                  │  Port: 8000      │                       │
│                  │ (runs on host,   │                       │
│                  │  not in Compose) │                       │
│                  └──────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Prerequisites

### Required Software

1. **Docker Desktop** (v20.10+)
   - Download: https://www.docker.com/products/docker-desktop
   - Verify: `docker --version`

2. **Docker Compose** (v2.0+)
   - Included with Docker Desktop
   - Verify: `docker compose version`

### System Requirements

- **RAM**: Minimum 4GB, Recommended 8GB+
- **Disk Space**: Minimum 10GB free
- **OS**: macOS, Windows 10/11, or Linux

---

## 🚀 Quick Start

### 0. The canonical command (read this first)

Every Compose command in this document must be run **from the repository root**, with both of these
flags:

```bash
docker compose -f docker/docker-compose.yml --project-directory . <subcommand>
```

To keep the rest of this document short, define this helper once per shell — it works in both `zsh`
and `bash`:

```bash
cd /path/to/PredictionsAppsUI          # the repository ROOT, not docker/
dc() { docker compose -f docker/docker-compose.yml --project-directory . "$@"; }
```

Every `dc …` below means exactly that command.

**Why both flags are required.** `docker/docker-compose.yml` writes its bind mounts relative to the
project directory (`./docker/postgres/init`, `./docker/postgres/conf`, `./docker/redis/redis.conf`).
Compose resolves the project directory from the **compose file's own directory** unless
`--project-directory` overrides it, so `-f` alone is not enough. The project name is derived from the
same directory, so getting it wrong also creates a *second*, separate stack.

Verify it yourself without starting anything — `config` only prints the resolved configuration:

```bash
# correct: run from the repository root, with both flags
docker compose -f docker/docker-compose.yml --project-directory . config | grep -E '^name:|source: /'
#   name: predictionsappsui
#   source: …/PredictionsAppsUI/docker/postgres/init        ✅ exists

# wrong: bare `docker compose` from docker/, or `-f` without --project-directory
cd docker && docker compose config | grep -E '^name:|source: /'
#   name: docker                                             ❌ a different project
#   source: …/PredictionsAppsUI/docker/docker/postgres/init   ❌ does not exist
```

With the wrong form the init scripts and `postgres.conf` silently resolve to non-existent
`docker/docker/…` paths (Docker then creates them as empty directories), and `redis.conf` is mounted
as a **directory** instead of a file, so Redis starts unconfigured.

### 1. Start All Services

```bash
dc up -d
```

**Expected Output** (exact wording varies by Compose version):
```
[+] Running 6/6
 ✔ Network soccer_predictions_network       Created
 ✔ Volume "soccer_predictions_postgres_data" Created
 ✔ Volume "soccer_predictions_redis_data"    Created
 ✔ Container soccer_predictions_postgres     Started
 ✔ Container soccer_predictions_redis        Started
 ✔ Container soccer_predictions_adminer      Started
```

### 2. Verify Services are Running

```bash
dc ps
```

**Expected Output:**
```
NAME                          STATUS          PORTS
soccer_predictions_postgres   Up (healthy)    0.0.0.0:5432->5432/tcp
soccer_predictions_redis      Up (healthy)    0.0.0.0:6379->6379/tcp
soccer_predictions_adminer    Up              0.0.0.0:8081->8080/tcp
```

Adminer listens on **8080 inside the container and 8081 on the host**
(`docker/docker-compose.yml`, `ports: "8081:8080"`), so the URL is <http://localhost:8081>.

### 3. Check Service Health

```bash
# Check PostgreSQL
dc exec postgres pg_isready -U postgres

# Check Redis
dc exec redis redis-cli ping
```

### 4. Access Services

- **Adminer (Database UI)**: http://localhost:8081
  - System: `PostgreSQL`
  - Server: `postgres`
  - Username: `postgres`
  - Password: `postgres123`
  - Database: `soccer_predictions`

- **PostgreSQL**: `localhost:5432`
- **Redis**: `localhost:6379`

### 5. Stop All Services

```bash
dc down
```

---

## 🐳 Services

### PostgreSQL Database

**Image**: `postgres:15-alpine`  
**Port**: `5432`  
**Container Name**: `soccer_predictions_postgres`

**Features:**
- Multi-schema architecture (users, predictions, ml_models, analytics, audit)
- UUID extension for primary keys
- JSONB support with GIN indexing
- Full-text search capabilities
- Automatic initialization with custom schemas and types
- Optimized configuration for development

**Environment Variables:**
- `POSTGRES_USER`: postgres
- `POSTGRES_PASSWORD`: postgres123
- `POSTGRES_DB`: soccer_predictions

**Volumes:**
- `postgres_data`: Persistent database storage
- `./docker/postgres/init`: Initialization scripts (read-only)
- `./docker/postgres/conf`: Configuration files (read-only)

**Health Check:**
- Command: `pg_isready -U postgres -d soccer_predictions`
- Interval: 10 seconds
- Timeout: 5 seconds
- Retries: 5

### Redis Cache

**Image**: `redis:7-alpine`  
**Port**: `6379`  
**Container Name**: `soccer_predictions_redis`

**Features:**
- Session management (DB 0)
- Prediction caching (DB 1)
- Expert tools cache (DB 2)
- ML model predictions cache (DB 3)
- Real-time match data (DB 4)
- API rate limiting (DB 5)
- Persistent storage with RDB snapshots
- LRU eviction policy

**Configuration:**
- Max Memory: 512MB
- Eviction Policy: allkeys-lru
- Persistence: RDB snapshots
- Databases: 16 (0-15)

**Volumes:**
- `redis_data`: Persistent cache storage
- `./docker/redis/redis.conf`: Configuration file (read-only)

**Health Check:**
- Command: `redis-cli ping`
- Interval: 10 seconds
- Timeout: 3 seconds
- Retries: 5

### Adminer Database UI

**Image**: `adminer:latest`
**Port**: `8081` (mapped to container port 8080)
**Container Name**: `soccer_predictions_adminer`

**Features:**
- Web-based database management
- SQL query execution
- Table browsing and editing
- Database schema visualization
- Import/Export capabilities

**Access**: http://localhost:8081

**Default Theme**: pepa-linha

---

## ⚙️ Configuration

### PostgreSQL Configuration

**File**: `docker/postgres/conf/postgresql.conf`

**Key Settings:**
- `max_connections`: 200
- `shared_buffers`: 256MB
- `effective_cache_size`: 1GB
- `work_mem`: 4MB
- `maintenance_work_mem`: 64MB
- `log_min_duration_statement`: 1000ms (log slow queries)

**Initialization Scripts:**

1. **01-init-database.sql**: Creates schemas, extensions, and types
   - Creates 5 schemas: users, predictions, ml_models, analytics, audit
   - Enables extensions: uuid-ossp, btree_gin, pg_trgm, pgcrypto
   - Creates custom enum types for all schemas
   - Sets up permissions and utility functions

### Redis Configuration

**File**: `docker/redis/redis.conf`

**Key Settings:**
- `maxmemory`: 512mb
- `maxmemory-policy`: allkeys-lru
- `save`: RDB snapshots (900s/1key, 300s/10keys, 60s/10000keys)
- `databases`: 16

**Database Allocation:**
- DB 0: User sessions and authentication tokens
- DB 1: Prediction caching
- DB 2: Expert tools cache
- DB 3: ML model predictions cache
- DB 4: Real-time match data
- DB 5: API rate limiting
- DB 6-15: Reserved for future use

### Docker Network

**Name**: `soccer_predictions_network`  
**Driver**: bridge  
**Subnet**: 172.20.0.0/16

**Purpose**: Isolates all services in a private network for secure communication.

### Docker Volumes

1. **postgres_data**: PostgreSQL data persistence
2. **redis_data**: Redis data persistence

**Location**: Docker managed volumes (use `docker volume inspect` to find path)

---

## 🗄️ Database Management

### Using Adminer

1. **Access Adminer**: http://localhost:8081
2. **Login**:
   - System: PostgreSQL
   - Server: postgres
   - Username: postgres
   - Password: postgres123
   - Database: soccer_predictions

3. **Browse Schemas**:
   - Click on "soccer_predictions" database
   - Select schema from dropdown (users, predictions, ml_models, analytics, audit)

4. **Execute SQL**:
   - Click "SQL command" in left sidebar
   - Enter SQL query
   - Click "Execute"

### Using psql (Command Line)

```bash
# Connect to PostgreSQL
dc exec postgres psql -U postgres -d soccer_predictions

# List schemas
\dn

# Set search path
SET search_path TO users, predictions, ml_models, analytics, audit, public;

# List tables in current schema
\dt

# Describe table
\d users.users

# Execute SQL
SELECT * FROM users.users LIMIT 10;

# Exit
\q
```

### Using Redis CLI

```bash
# Connect to Redis
dc exec redis redis-cli

# Select database
SELECT 0

# List all keys
KEYS *

# Get value
GET key_name

# Set value with expiration
SETEX key_name 3600 "value"

# Check memory usage
INFO memory

# Exit
exit
```

### Backup and Restore

**PostgreSQL Backup:**
```bash
# Backup all schemas
dc exec postgres pg_dump -U postgres -d soccer_predictions > backup.sql

# Backup specific schema
dc exec postgres pg_dump -U postgres -d soccer_predictions -n users > users_backup.sql
```

**PostgreSQL Restore:**
```bash
# Restore from backup
dc exec -T postgres psql -U postgres -d soccer_predictions < backup.sql
```

**Redis Backup:**
```bash
# Trigger RDB snapshot
dc exec redis redis-cli BGSAVE

# Copy RDB file
docker cp soccer_predictions_redis:/data/dump.rdb ./redis_backup.rdb
```

---

## 🔧 Troubleshooting

### Services Won't Start

**Problem**: `dc up` fails

**Solutions:**
1. Check if ports are already in use:
   ```bash
   # Check port 5432 (PostgreSQL)
   lsof -i :5432
   
   # Check port 6379 (Redis)
   lsof -i :6379
   
   # Check port 8081 (Adminer on the host)
   lsof -i :8081
   ```

2. Stop conflicting services or change ports in `docker/docker-compose.yml`

3. Check Docker Desktop is running

4. Restart Docker Desktop

### PostgreSQL Connection Refused

**Problem**: Cannot connect to PostgreSQL

**Solutions:**
1. Check service is running:
   ```bash
   dc ps postgres
   ```

2. Check logs:
   ```bash
   dc logs postgres
   ```

3. Wait for health check to pass:
   ```bash
   dc ps
   # Wait until STATUS shows "healthy"
   ```

4. Verify connection:
   ```bash
   dc exec postgres pg_isready -U postgres
   ```

### Redis Connection Issues

**Problem**: Cannot connect to Redis

**Solutions:**
1. Check service is running:
   ```bash
   dc ps redis
   ```

2. Test connection:
   ```bash
   dc exec redis redis-cli ping
   # Should return: PONG
   ```

3. Check logs:
   ```bash
   dc logs redis
   ```

### Adminer Cannot Connect to Database

**Problem**: Adminer shows "Unable to connect"

**Solutions:**
1. Ensure PostgreSQL is healthy:
   ```bash
   dc ps postgres
   ```

2. Use correct server name: `postgres` (not `localhost`)

3. Check credentials:
   - Username: `postgres`
   - Password: `postgres123`

### Data Not Persisting

**Problem**: Data is lost after `dc down`

**Solutions:**
1. Don't use `dc down -v` (removes volumes)

2. Check volumes exist:
   ```bash
   docker volume ls | grep soccer_predictions
   ```

3. Inspect volume:
   ```bash
   docker volume inspect soccer_predictions_postgres_data
   ```

### Slow Performance

**Problem**: Services are slow

**Solutions:**
1. Increase Docker Desktop resources:
   - Docker Desktop → Settings → Resources
   - Increase CPU and Memory allocation

2. Check resource usage:
   ```bash
   docker stats
   ```

3. Optimize PostgreSQL configuration in `docker/postgres/conf/postgresql.conf`

---

## 🚀 Advanced Usage

### View Logs

```bash
# All services
dc logs -f

# Specific service
dc logs -f postgres
dc logs -f redis
dc logs -f adminer

# Last 100 lines
dc logs --tail=100 postgres
```

### Execute Commands in Containers

```bash
# PostgreSQL
dc exec postgres bash
dc exec postgres psql -U postgres -d soccer_predictions

# Redis
dc exec redis sh
dc exec redis redis-cli
```

### Restart Services

```bash
# Restart all services
dc restart

# Restart specific service
dc restart postgres
dc restart redis
```

### Rebuild Services

```bash
# Rebuild all services
dc up -d --build

# Rebuild specific service
dc up -d --build postgres
```

### Clean Up

```bash
# Stop and remove containers (keeps volumes)
dc down

# Stop and remove containers and volumes (DELETES ALL DATA)
dc down -v

# Remove unused Docker resources
docker system prune -a
```

### Environment Variables

**These values are not configurable through a `.env` file today.** `docker/docker-compose.yml`
contains no `${VARIABLE}` substitution at all — the credentials and the port mappings are written
literally:

```yaml
environment:
  POSTGRES_USER: postgres
  POSTGRES_PASSWORD: postgres123
  POSTGRES_DB: soccer_predictions
ports:
  - "5432:5432"      # postgres
  - "6379:6379"      # redis
  - "8081:8080"      # adminer: host 8081 -> container 8080
```

To change any of them, edit `docker/docker-compose.yml` (and then the matching `DATABASE_URL` /
`REDIS_URL` in `backend/.env`), or add the substitutions yourself first, for example
`- "${POSTGRES_PORT:-5432}:5432"`. A root `.env` file has no effect until that change is made.

These are local development credentials committed to a public repository. They must never be reused
for anything reachable from outside this machine.

---

## 📚 Related Documentation

- [Database Schema Documentation](../docs/database/README.md)
- [Local Development Architecture Plan](../LOCAL_DEVELOPMENT_ARCHITECTURE_PLAN.md)
- [AWS Production Deployment Plan](../AWS_PRODUCTION_DEPLOYMENT_PLAN.md)

---

## 🔗 Useful Commands Cheat Sheet

```bash
# Start services
dc up -d

# Stop services
dc down

# View logs
dc logs -f

# Check status
dc ps

# Restart service
dc restart postgres

# Execute command
dc exec postgres psql -U postgres

# Backup database
dc exec postgres pg_dump -U postgres -d soccer_predictions > backup.sql

# Restore database
dc exec -T postgres psql -U postgres -d soccer_predictions < backup.sql

# Clean up
dc down -v
docker system prune -a
```

---

**Status**: ✅ Ready for Use  
**Last Updated**: 2025-10-08  
**Maintained By**: Backend Development Team


