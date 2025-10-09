# Soccer Predictions Platform - API Documentation

Comprehensive documentation for the FastAPI backend of the Soccer Predictions Platform.

## 📚 Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [API Endpoints](#api-endpoints)
5. [Authentication](#authentication)
6. [Database](#database)
7. [Caching](#caching)
8. [Testing](#testing)
9. [Deployment](#deployment)

## 🎯 Overview

The Soccer Predictions Platform API is built with FastAPI and provides:

- **Multi-Profile System**: Regular users, Expert users, and Admin users
- **Hybrid Prediction Engine**: ML baseline predictions with expert override capabilities
- **Multi-Schema Database**: PostgreSQL with 5 schemas (users, predictions, ml_models, analytics, audit)
- **Redis Caching**: 16 databases for different caching purposes
- **Comprehensive Audit Trail**: GDPR-compliant logging and data tracking
- **ML/AI Integration**: Machine learning models for prediction generation

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Required
- Python 3.11+
- PostgreSQL 15+ (via Docker)
- Redis 7+ (via Docker)
- Docker & Docker Compose

# Optional
- Poetry (for dependency management)
- Make (for convenience commands)
```

### 2. Infrastructure Setup

```bash
# Start PostgreSQL, Redis, and Adminer
cd docker
docker-compose up -d

# Verify services are running
docker-compose ps

# Check PostgreSQL schemas
docker-compose exec postgres psql -U postgres -d soccer_predictions -c "\dn"

# Check Redis
docker-compose exec redis redis-cli ping
```

### 3. Backend Setup

```bash
# Navigate to backend
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env if needed (defaults work for local development)

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Verify Installation

```bash
# Test root endpoint
curl http://localhost:8000/

# Test health check
curl http://localhost:8000/health

# Test detailed health check
curl http://localhost:8000/api/v1/health/detailed

# Open API documentation
open http://localhost:8000/api/v1/docs
```

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React)                         │
│                   Port 3000 / 5173                          │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/REST
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                FastAPI Backend (Port 8000)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Auth API   │  │ Predictions  │  │  Expert API  │     │
│  │              │  │     API      │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Admin API   │  │  ML Engine   │  │ Audit Logger │     │
│  │              │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────┬───────────────────┬────────────────────────────┘
             │                   │
             ▼                   ▼
┌─────────────────────┐  ┌─────────────────────┐
│   PostgreSQL 15     │  │      Redis 7        │
│   Port 5432         │  │     Port 6379       │
│                     │  │                     │
│  5 Schemas:         │  │  16 Databases:      │
│  - users            │  │  - DB 0: Sessions   │
│  - predictions      │  │  - DB 1: Predictions│
│  - ml_models        │  │  - DB 2: Expert     │
│  - analytics        │  │  - DB 3: ML Models  │
│  - audit            │  │  - DB 4: Match Data │
│                     │  │  - DB 5: Rate Limit │
└─────────────────────┘  └─────────────────────┘
```

### Technology Stack

- **Framework**: FastAPI 0.104+
- **Server**: Uvicorn with hot reload
- **Database**: PostgreSQL 15 with SQLAlchemy 2.0
- **Cache**: Redis 7 with multiple databases
- **Migrations**: Alembic
- **Authentication**: JWT with python-jose
- **Validation**: Pydantic v2
- **Testing**: Pytest with coverage
- **Code Quality**: Black, isort, flake8, mypy

## 📡 API Endpoints

### Current Endpoints

#### Root & Health

```
GET  /                          # API information
GET  /health                    # Basic health check
GET  /api/v1/health             # API v1 health check
GET  /api/v1/health/detailed    # Detailed health (DB + Redis)
GET  /api/v1/health/database    # Database health
GET  /api/v1/health/redis       # Redis health
```

### Planned Endpoints

#### Authentication
```
POST /api/v1/auth/register      # User registration
POST /api/v1/auth/login         # User login
POST /api/v1/auth/logout        # User logout
POST /api/v1/auth/refresh       # Refresh access token
GET  /api/v1/auth/me            # Get current user
```

#### Users
```
GET    /api/v1/users            # List users (admin)
GET    /api/v1/users/{id}       # Get user
PUT    /api/v1/users/{id}       # Update user
DELETE /api/v1/users/{id}       # Delete user (admin)
GET    /api/v1/users/me         # Get current user profile
PUT    /api/v1/users/me         # Update current user profile
```

#### Predictions
```
GET    /api/v1/predictions      # List predictions
POST   /api/v1/predictions      # Create prediction (expert/admin)
GET    /api/v1/predictions/{id} # Get prediction
PUT    /api/v1/predictions/{id} # Update prediction (expert/admin)
DELETE /api/v1/predictions/{id} # Delete prediction (admin)
```

#### Matches
```
GET    /api/v1/matches          # List matches
GET    /api/v1/matches/{id}     # Get match details
GET    /api/v1/matches/today    # Today's matches
GET    /api/v1/matches/upcoming # Upcoming matches
```

#### Expert Tools
```
GET    /api/v1/expert/dashboard # Expert dashboard
POST   /api/v1/expert/override  # Override ML prediction
GET    /api/v1/expert/analytics # Expert analytics
```

#### Admin
```
GET    /api/v1/admin/users      # User management
GET    /api/v1/admin/stats      # System statistics
GET    /api/v1/admin/audit      # Audit logs
POST   /api/v1/admin/approve    # Approve predictions
```

## 🔐 Authentication

### JWT Token Flow

```
1. User Login
   POST /api/v1/auth/login
   Body: { "email": "user@example.com", "password": "password" }
   
2. Receive Tokens
   Response: {
     "access_token": "eyJ...",
     "refresh_token": "eyJ...",
     "token_type": "bearer"
   }
   
3. Use Access Token
   Headers: { "Authorization": "Bearer eyJ..." }
   
4. Refresh Token
   POST /api/v1/auth/refresh
   Body: { "refresh_token": "eyJ..." }
```

### User Roles

- **Regular User**: View predictions, manage profile
- **Expert User**: Create/override predictions, access expert tools
- **Admin User**: Full system access, user management, approval workflow

## 💾 Database

### Multi-Schema Architecture

#### users Schema (17 tables)
- User accounts and authentication
- Profiles and preferences
- Roles and permissions
- Subscriptions and payments

#### predictions Schema (16 tables)
- Predictions and matches
- Teams and leagues
- Betting markets and odds
- Prediction history

#### ml_models Schema (12 tables)
- ML model registry
- Training runs and metrics
- Model deployments
- A/B testing framework

#### analytics Schema (13 tables)
- User performance metrics
- Prediction analytics
- Expert performance tracking
- Revenue and engagement

#### audit Schema (8 tables)
- Comprehensive audit logging
- Data access tracking
- GDPR compliance
- Security monitoring

### Connection Details

```python
# Database URL format
DATABASE_URL = "postgresql://user:password@host:port/database"

# Example (local development)
DATABASE_URL = "postgresql://postgres:postgres123@localhost:5432/soccer_predictions"
```

## 🗄️ Caching

### Redis Database Allocation

```python
# DB 0: User sessions and authentication
REDIS_DB_SESSIONS = 0

# DB 1: Prediction caching
REDIS_DB_PREDICTIONS = 1

# DB 2: Expert tools cache
REDIS_DB_EXPERT_TOOLS = 2

# DB 3: ML model predictions cache
REDIS_DB_ML_MODELS = 3

# DB 4: Real-time match data
REDIS_DB_MATCH_DATA = 4

# DB 5: API rate limiting
REDIS_DB_RATE_LIMIT = 5
```

### Cache Usage Examples

```python
from app.core.redis import get_predictions_redis

# Get Redis client for predictions
redis_client = get_predictions_redis()

# Cache prediction
redis_client.setex(
    f"prediction:{prediction_id}",
    300,  # 5 minutes TTL
    json.dumps(prediction_data)
)

# Get cached prediction
cached = redis_client.get(f"prediction:{prediction_id}")
```

## 🧪 Testing

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/test_health.py

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Structure

```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── test_health.py           # Health check tests
├── test_auth.py             # Authentication tests (future)
├── test_predictions.py      # Prediction tests (future)
└── test_expert.py           # Expert tools tests (future)
```

## 🚀 Deployment

### Production Checklist

```bash
# 1. Environment
export ENVIRONMENT=production
export DEBUG=false

# 2. Security
export SECRET_KEY=$(openssl rand -hex 32)

# 3. Database
export DATABASE_URL=postgresql://user:pass@prod-db:5432/soccer_predictions

# 4. Redis
export REDIS_URL=redis://prod-redis:6379/0

# 5. CORS
export BACKEND_CORS_ORIGINS=https://yourdomain.com

# 6. Allowed Hosts
export ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
```

### Docker Deployment

```bash
# Build image
docker build -t soccer-predictions-api:latest .

# Run container
docker run -d \
  --name soccer-predictions-api \
  -p 8000:8000 \
  --env-file .env.production \
  soccer-predictions-api:latest
```

## 📖 Additional Resources

- **API Architecture**: See `API_ARCHITECTURE.md`
- **Quick Reference**: See `QUICK_REFERENCE.md`
- **Implementation Summary**: See `IMPLEMENTATION_SUMMARY.md`
- **Database Schema**: See `docs/database/`
- **Docker Setup**: See `docker/`

## 🤝 Support

For issues and questions:
- Check the documentation in `api/` folder
- Review health check endpoints
- Check logs for errors
- Verify database and Redis connections

