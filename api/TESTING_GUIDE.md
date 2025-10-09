# API Connection Testing Guide

Complete guide for testing PostgreSQL and Redis connections in the Soccer Predictions Platform API.

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Health Check Endpoints](#health-check-endpoints)
3. [Automated Test Scripts](#automated-test-scripts)
4. [Manual Testing](#manual-testing)
5. [Direct Database Testing](#direct-database-testing)
6. [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites

1. **Start Docker services**:
   ```bash
   cd docker
   docker-compose up -d
   ```

2. **Start FastAPI server**:
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Quick Test

```bash
# Test all connections at once
./backend/scripts/test_api.sh

# Or use Python script
cd backend
source venv/bin/activate
python scripts/test_connections.py
```

---

## 🏥 Health Check Endpoints

The API provides several health check endpoints to test connections:

### 1. Root Endpoint

```bash
curl http://localhost:8000/
```

**Response**:
```json
{
  "name": "Soccer Predictions Platform API",
  "version": "0.1.0",
  "environment": "development",
  "docs": "/api/v1/docs",
  "status": "operational"
}
```

### 2. Basic Health Check

```bash
curl http://localhost:8000/health
```

**Response**:
```json
{
  "status": "healthy",
  "environment": "development",
  "version": "0.1.0"
}
```

### 3. Detailed Health Check (Database + Redis)

```bash
curl http://localhost:8000/api/v1/health/detailed
```

**Response**:
```json
{
  "status": "healthy",
  "service": "Soccer Predictions Platform API",
  "version": "0.1.0",
  "environment": "development",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "PostgreSQL connection successful"
    },
    "redis": {
      "status": "healthy",
      "message": "Redis connection successful"
    }
  }
}
```

### 4. Database Health Check

```bash
curl http://localhost:8000/api/v1/health/database
```

**Response**:
```json
{
  "status": "healthy",
  "database": "PostgreSQL",
  "version": "PostgreSQL 15.14...",
  "schemas": ["analytics", "audit", "ml_models", "predictions", "users"],
  "schemas_count": 5,
  "expected_schemas": 5
}
```

### 5. Redis Health Check

```bash
curl http://localhost:8000/api/v1/health/redis
```

**Response**:
```json
{
  "status": "healthy",
  "redis_version": "7.4.6",
  "connected_clients": 1,
  "used_memory_human": "1.01M",
  "database_allocation": {
    "sessions": 0,
    "predictions": 1,
    "expert_tools": 2,
    "ml_models": 3,
    "match_data": 4,
    "rate_limit": 5
  }
}
```

---

## 🧪 Automated Test Scripts

### 1. Bash Script (Quick Testing)

**Location**: `backend/scripts/test_api.sh`

**Usage**:
```bash
./backend/scripts/test_api.sh
```

**Features**:
- ✅ Tests all health endpoints
- ✅ Direct PostgreSQL connection test
- ✅ Direct Redis connection test
- ✅ Tests all Redis databases (0-5)
- ✅ Colored output for easy reading
- ✅ Detailed error messages

### 2. Python Script (Comprehensive Testing)

**Location**: `backend/scripts/test_connections.py`

**Usage**:
```bash
cd backend
source venv/bin/activate
python scripts/test_connections.py
```

**Features**:
- ✅ PostgreSQL connection test
- ✅ Redis connection test
- ✅ All Redis databases test (0-5)
- ✅ Connection pooling test
- ✅ Error handling test
- ✅ Detailed test summary

**Tests Performed**:
1. **PostgreSQL Connection**
   - Version check
   - Basic query test
   - Schema verification
   - Table count per schema

2. **Redis Connection**
   - PING test
   - Version check
   - SET/GET operations
   - Memory usage

3. **Redis Databases**
   - Sessions (DB 0)
   - Predictions (DB 1)
   - Expert Tools (DB 2)
   - ML Models (DB 3)
   - Match Data (DB 4)
   - Rate Limiting (DB 5)

4. **Connection Pooling**
   - Multiple PostgreSQL connections
   - Redis connection pool
   - Concurrent operations

5. **Error Handling**
   - Invalid PostgreSQL connection
   - Invalid Redis connection

---

## 🔧 Manual Testing

### PostgreSQL Testing

#### Using psql (Docker)

```bash
# Connect to PostgreSQL
docker exec -it soccer_predictions_postgres psql -U postgres -d soccer_predictions

# Check version
SELECT version();

# List schemas
\dn

# List tables in a schema
\dt users.*

# Check schema existence
SELECT schema_name 
FROM information_schema.schemata 
WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
ORDER BY schema_name;

# Exit
\q
```

#### Using Python

```python
from sqlalchemy import create_engine, text

# Create engine
engine = create_engine("postgresql://postgres:postgres123@localhost:5432/soccer_predictions")

# Test connection
with engine.connect() as conn:
    result = conn.execute(text("SELECT version()"))
    print(result.scalar())
    
    # Check schemas
    result = conn.execute(text("""
        SELECT schema_name 
        FROM information_schema.schemata 
        WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
    """))
    for row in result:
        print(row[0])
```

### Redis Testing

#### Using redis-cli (Docker)

```bash
# Connect to Redis
docker exec -it soccer_predictions_redis redis-cli

# Test connection
PING

# Get server info
INFO server

# Test SET/GET
SET test:key "Hello World"
GET test:key
DEL test:key

# Switch database
SELECT 1
PING

# Exit
exit
```

#### Using Python

```python
import redis

# Create client
client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Test connection
print(client.ping())  # Should return True

# Test SET/GET
client.set('test:key', 'Hello World', ex=60)
value = client.get('test:key')
print(value)  # Should print: Hello World

# Test different databases
for db in range(6):
    client = redis.Redis(host='localhost', port=6379, db=db, decode_responses=True)
    print(f"DB {db}: {client.ping()}")
```

---

## 🔍 Direct Database Testing

### Check Docker Containers

```bash
# List running containers
docker ps | grep soccer_predictions

# Check PostgreSQL logs
docker logs soccer_predictions_postgres

# Check Redis logs
docker logs soccer_predictions_redis
```

### PostgreSQL Direct Commands

```bash
# Check if PostgreSQL is running
docker exec soccer_predictions_postgres pg_isready

# Get PostgreSQL version
docker exec soccer_predictions_postgres psql -U postgres -c "SELECT version();"

# List databases
docker exec soccer_predictions_postgres psql -U postgres -c "\l"

# Check connection count
docker exec soccer_predictions_postgres psql -U postgres -d soccer_predictions -c "SELECT count(*) FROM pg_stat_activity;"
```

### Redis Direct Commands

```bash
# Check if Redis is running
docker exec soccer_predictions_redis redis-cli PING

# Get Redis info
docker exec soccer_predictions_redis redis-cli INFO

# Check memory usage
docker exec soccer_predictions_redis redis-cli INFO memory

# Check connected clients
docker exec soccer_predictions_redis redis-cli CLIENT LIST

# Test all databases
for db in {0..5}; do
  echo "Testing DB $db:"
  docker exec soccer_predictions_redis redis-cli -n $db PING
done
```

---

## 🐛 Troubleshooting

### PostgreSQL Connection Issues

**Problem**: Cannot connect to PostgreSQL

**Solutions**:
1. Check if container is running:
   ```bash
   docker ps | grep postgres
   ```

2. Check PostgreSQL logs:
   ```bash
   docker logs soccer_predictions_postgres
   ```

3. Verify connection settings in `.env`:
   ```bash
   POSTGRES_SERVER=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=postgres123
   POSTGRES_DB=soccer_predictions
   ```

4. Test direct connection:
   ```bash
   docker exec soccer_predictions_postgres pg_isready
   ```

### Redis Connection Issues

**Problem**: Cannot connect to Redis

**Solutions**:
1. Check if container is running:
   ```bash
   docker ps | grep redis
   ```

2. Check Redis logs:
   ```bash
   docker logs soccer_predictions_redis
   ```

3. Verify connection settings in `.env`:
   ```bash
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_DB=0
   ```

4. Test direct connection:
   ```bash
   docker exec soccer_predictions_redis redis-cli PING
   ```

### API Server Issues

**Problem**: Health endpoints return errors

**Solutions**:
1. Check if API server is running:
   ```bash
   curl http://localhost:8000/
   ```

2. Check API logs:
   ```bash
   # Look at terminal where uvicorn is running
   ```

3. Restart API server:
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Service not running | Start Docker containers |
| `Authentication failed` | Wrong credentials | Check `.env` file |
| `Database does not exist` | Database not created | Run initialization script |
| `Schema not found` | Schemas not created | Run migrations |
| `Redis timeout` | Redis not responding | Restart Redis container |

---

## 📊 Expected Test Results

### All Tests Passing

```
✅ PostgreSQL Connection: PASSED
✅ Redis Connection: PASSED
✅ Redis Databases: PASSED
✅ Connection Pooling: PASSED
✅ Error Handling: PASSED

Total: 5/5 tests passed
```

### Database Schemas

```
Expected: 5 schemas
Found: analytics, audit, ml_models, predictions, users
```

### Redis Databases

```
DB 0: Sessions ✅
DB 1: Predictions ✅
DB 2: Expert Tools ✅
DB 3: ML Models ✅
DB 4: Match Data ✅
DB 5: Rate Limiting ✅
```

---

## 🎯 Next Steps

After confirming all connections are working:

1. **Run migrations** to create tables:
   ```bash
   cd backend
   alembic upgrade head
   ```

2. **Create seed data** for development

3. **Start building API endpoints**

4. **Write integration tests**

---

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Redis Documentation](https://redis.io/documentation)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

