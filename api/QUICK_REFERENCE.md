# Quick Reference - Soccer Predictions Platform API

Quick command reference for common operations.

## 🚀 Development Commands

### Start Services

```bash
# Start infrastructure (PostgreSQL, Redis, Adminer)
cd docker && docker-compose up -d

# Start backend API
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use start script
chmod +x scripts/start.sh
./scripts/start.sh
```

### Stop Services

```bash
# Stop backend (Ctrl+C in terminal)

# Stop infrastructure
cd docker && docker-compose down

# Stop and remove volumes (WARNING: deletes data)
cd docker && docker-compose down -v
```

## 📦 Installation

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt  # If exists
```

## 🗄️ Database Commands

### PostgreSQL

```bash
# Connect to database
docker-compose exec postgres psql -U postgres -d soccer_predictions

# List schemas
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "\dn"

# List tables in a schema
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "\dt users.*"

# Check database size
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "SELECT pg_size_pretty(pg_database_size('soccer_predictions'));"

# Backup database
docker-compose exec postgres pg_dump -U postgres soccer_predictions > backup.sql

# Restore database
docker-compose exec -T postgres psql -U postgres soccer_predictions < backup.sql
```

### Alembic Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply all migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Rollback all migrations
alembic downgrade base

# View migration history
alembic history

# View current migration
alembic current

# Show SQL for migration (without applying)
alembic upgrade head --sql
```

## 🗃️ Redis Commands

```bash
# Connect to Redis
docker-compose exec redis redis-cli

# Test connection
docker-compose exec redis redis-cli ping

# Get Redis info
docker-compose exec redis redis-cli info

# Check memory usage
docker-compose exec redis redis-cli info memory

# List all keys (use with caution in production)
docker-compose exec redis redis-cli keys "*"

# Switch to different database
docker-compose exec redis redis-cli -n 1  # DB 1 (predictions)

# Flush specific database
docker-compose exec redis redis-cli -n 1 flushdb

# Flush all databases (WARNING: deletes all data)
docker-compose exec redis redis-cli flushall
```

## 🧪 Testing Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/test_health.py

# Run specific test function
pytest tests/test_health.py::test_root_endpoint

# Run with verbose output
pytest -v

# Run with print statements
pytest -s

# Stop on first failure
pytest -x

# Run last failed tests
pytest --lf

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## 🔍 Code Quality

```bash
# Format code with Black
black app/

# Check formatting (without changes)
black --check app/

# Sort imports with isort
isort app/

# Check import sorting
isort --check app/

# Lint with flake8
flake8 app/

# Type check with mypy
mypy app/

# Run all quality checks
black app/ && isort app/ && flake8 app/ && mypy app/
```

## 🐳 Docker Commands

```bash
# Build backend image
docker build -t soccer-predictions-api:latest .

# Run backend container
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://postgres:postgres123@host.docker.internal:5432/soccer_predictions \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  soccer-predictions-api:latest

# View logs
docker-compose logs -f backend

# View specific service logs
docker-compose logs -f postgres
docker-compose logs -f redis

# Restart service
docker-compose restart backend

# Rebuild and restart
docker-compose up -d --build backend

# Execute command in container
docker-compose exec backend python -c "print('Hello')"

# Access container shell
docker-compose exec backend /bin/bash
```

## 🌐 API Testing

### cURL Examples

```bash
# Root endpoint
curl http://localhost:8000/

# Health check
curl http://localhost:8000/health

# Detailed health check
curl http://localhost:8000/api/v1/health/detailed

# Database health
curl http://localhost:8000/api/v1/health/database

# Redis health
curl http://localhost:8000/api/v1/health/redis

# With authentication (future)
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/api/v1/users/me
```

### HTTPie Examples

```bash
# Install HTTPie
pip install httpie

# Root endpoint
http localhost:8000/

# Health check
http localhost:8000/health

# POST request (future)
http POST localhost:8000/api/v1/auth/login \
  email=user@example.com \
  password=password123

# With authentication (future)
http localhost:8000/api/v1/users/me \
  Authorization:"Bearer YOUR_TOKEN"
```

## 📊 Monitoring

```bash
# View API logs
tail -f logs/api.log  # If logging to file

# View Uvicorn logs
# Logs are output to stdout when running with --reload

# Check API status
curl http://localhost:8000/health

# Check database connection
curl http://localhost:8000/api/v1/health/database

# Check Redis connection
curl http://localhost:8000/api/v1/health/redis

# Monitor Docker containers
docker-compose ps
docker stats
```

## 🔧 Environment Management

```bash
# Copy environment template
cp .env.example .env

# Edit environment variables
nano .env  # or vim, code, etc.

# Load environment variables
source .env  # Bash
set -a; source .env; set +a  # More reliable

# Check environment variable
echo $DATABASE_URL

# Run with specific environment
ENVIRONMENT=production uvicorn app.main:app
```

## 📝 Useful Queries

### PostgreSQL

```sql
-- List all schemas
SELECT schema_name FROM information_schema.schemata 
WHERE schema_name IN ('users', 'predictions', 'ml_models', 'analytics', 'audit');

-- Count tables in each schema
SELECT schemaname, COUNT(*) 
FROM pg_tables 
WHERE schemaname IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
GROUP BY schemaname;

-- Check database size
SELECT pg_size_pretty(pg_database_size('soccer_predictions'));

-- Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
FROM pg_tables
WHERE schemaname IN ('users', 'predictions', 'ml_models', 'analytics', 'audit')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Redis

```bash
# Get database size
INFO keyspace

# Get memory usage
INFO memory

# Get server info
INFO server

# Monitor commands in real-time
MONITOR

# Get slow log
SLOWLOG GET 10
```

## 🚀 Deployment

```bash
# Production build
docker build -t soccer-predictions-api:prod --target production .

# Run production container
docker run -d \
  --name soccer-predictions-api \
  -p 8000:8000 \
  --env-file .env.production \
  --restart unless-stopped \
  soccer-predictions-api:prod

# View production logs
docker logs -f soccer-predictions-api

# Health check in production
curl https://api.yourdomain.com/health
```

## 📖 Documentation

```bash
# View API documentation
open http://localhost:8000/api/v1/docs  # Swagger UI
open http://localhost:8000/api/v1/redoc  # ReDoc

# Generate OpenAPI spec
curl http://localhost:8000/api/v1/openapi.json > openapi.json
```

## 🆘 Troubleshooting

```bash
# Check if port is in use
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill process on port
kill -9 $(lsof -t -i:8000)  # macOS/Linux

# Check Docker services
docker-compose ps

# View Docker logs
docker-compose logs -f

# Restart all services
docker-compose restart

# Clean Docker system
docker system prune -a

# Check Python version
python --version

# Check installed packages
pip list

# Verify database connection
python -c "from app.db.session import engine; print(engine.url)"

# Verify Redis connection
python -c "from app.core.redis import get_redis_client; print(get_redis_client().ping())"
```

