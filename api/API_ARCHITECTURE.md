# API Architecture - Soccer Predictions Platform

Comprehensive architecture documentation for the FastAPI backend.

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Core Components](#core-components)
5. [Database Architecture](#database-architecture)
6. [Caching Strategy](#caching-strategy)
7. [Security](#security)
8. [API Design](#api-design)
9. [Error Handling](#error-handling)
10. [Performance](#performance)

## 🎯 System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Layer                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ React Web    │  │ Mobile App   │  │  Admin Panel │             │
│  │  (Port 3000) │  │   (Future)   │  │   (Future)   │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTPS/REST
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API Gateway Layer                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              FastAPI Application (Port 8000)                 │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐             │  │
│  │  │   CORS     │  │  Security  │  │   GZip     │             │  │
│  │  │ Middleware │  │  Headers   │  │ Compression│             │  │
│  │  └────────────┘  └────────────┘  └────────────┘             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Business Logic Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ Auth Service │  │  Prediction  │  │ Expert Tools │             │
│  │              │  │   Service    │  │   Service    │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ Admin Service│  │  ML Engine   │  │ Audit Logger │             │
│  │              │  │   Service    │  │   Service    │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Data Layer                                   │
│  ┌─────────────────────────┐  ┌─────────────────────────┐          │
│  │   PostgreSQL 15         │  │      Redis 7            │          │
│  │   (Port 5432)           │  │     (Port 6379)         │          │
│  │                         │  │                         │          │
│  │  5 Schemas:             │  │  16 Databases:          │          │
│  │  • users                │  │  • DB 0: Sessions       │          │
│  │  • predictions          │  │  • DB 1: Predictions    │          │
│  │  • ml_models            │  │  • DB 2: Expert Tools   │          │
│  │  • analytics            │  │  • DB 3: ML Models      │          │
│  │  • audit                │  │  • DB 4: Match Data     │          │
│  │                         │  │  • DB 5: Rate Limiting  │          │
│  │  66 Tables Total        │  │  • DB 6-15: Reserved    │          │
│  │  300+ Indexes           │  │                         │          │
│  └─────────────────────────┘  └─────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

### Multi-Profile Prediction Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Prediction Generation Flow                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Match Data Input                                                   │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────┐     ┌───────────────────────────────────────┐     │
│  │ ML Engine   │────▶│      Baseline Prediction              │     │
│  │ Processing  │     │   (Automated ML Analysis)             │     │
│  └─────────────┘     └───────────────────────────────────────┘     │
│         │                            │                             │
│         │                            ▼                             │
│         │             ┌───────────────────────────────────────┐     │
│         │             │         Expert Review                 │     │
│         │             │  ┌─────────────┐  ┌───────────────┐  │     │
│         │             │  │   Accept    │  │   Override/   │  │     │
│         │             │  │ ML Baseline │  │    Adjust     │  │     │
│         │             │  └─────────────┘  └───────────────┘  │     │
│         │             └───────────────────────────────────────┘     │
│         │                            │                             │
│         │                            ▼                             │
│         │             ┌───────────────────────────────────────┐     │
│         │             │        Admin Approval                 │     │
│         │             │    (Optional for High-Stakes)         │     │
│         │             └───────────────────────────────────────┘     │
│         │                            │                             │
│         ▼                            ▼                             │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │              Final Published Prediction                   │     │
│  │           (With Source Attribution)                       │     │
│  └───────────────────────────────────────────────────────────┘     │
│                            │                                        │
│                            ▼                                        │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │                  Audit Trail                              │     │
│  │   (Who, What, When, Why - GDPR Compliant)                │     │
│  └───────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

## 🛠️ Technology Stack

### Core Framework
- **FastAPI 0.104+**: Modern, fast web framework
- **Uvicorn**: ASGI server with hot reload
- **Pydantic v2**: Data validation and settings management
- **Python 3.11+**: Latest Python features

### Database
- **PostgreSQL 15**: Multi-schema relational database
- **SQLAlchemy 2.0**: ORM with async support
- **Alembic**: Database migration tool
- **psycopg2-binary**: PostgreSQL adapter

### Caching & Sessions
- **Redis 7**: In-memory data store
- **redis-py**: Redis client for Python
- **hiredis**: High-performance Redis parser

### Authentication & Security
- **python-jose**: JWT token handling
- **passlib**: Password hashing with bcrypt
- **python-multipart**: Form data parsing

### Development Tools
- **pytest**: Testing framework
- **black**: Code formatter
- **flake8**: Linter
- **mypy**: Static type checker
- **isort**: Import sorter

## 📁 Project Structure

```
backend/
├── app/
│   ├── __init__.py                 # Package initialization
│   ├── main.py                     # FastAPI application entry point
│   │
│   ├── api/                        # API routes
│   │   ├── __init__.py
│   │   └── v1/                     # API version 1
│   │       ├── __init__.py
│   │       ├── api.py              # Main API router
│   │       └── endpoints/          # Endpoint modules
│   │           ├── __init__.py
│   │           ├── health.py       # Health check endpoints
│   │           ├── auth.py         # Authentication (future)
│   │           ├── users.py        # User management (future)
│   │           ├── predictions.py  # Predictions (future)
│   │           ├── matches.py      # Matches (future)
│   │           ├── expert.py       # Expert tools (future)
│   │           └── admin.py        # Admin endpoints (future)
│   │
│   ├── core/                       # Core functionality
│   │   ├── __init__.py
│   │   ├── config.py               # Settings and configuration
│   │   ├── security.py             # Security utilities
│   │   ├── logging.py              # Logging configuration
│   │   └── redis.py                # Redis client
│   │
│   ├── db/                         # Database
│   │   ├── __init__.py
│   │   ├── base.py                 # SQLAlchemy base
│   │   ├── session.py              # Database session
│   │   └── init_db.py              # Database initialization
│   │
│   ├── models/                     # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── users.py                # User models (future)
│   │   ├── predictions.py          # Prediction models (future)
│   │   ├── ml_models.py            # ML model models (future)
│   │   ├── analytics.py            # Analytics models (future)
│   │   └── audit.py                # Audit models (future)
│   │
│   ├── schemas/                    # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── users.py                # User schemas (future)
│   │   ├── predictions.py          # Prediction schemas (future)
│   │   ├── auth.py                 # Auth schemas (future)
│   │   └── common.py               # Common schemas (future)
│   │
│   ├── services/                   # Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py         # Authentication (future)
│   │   ├── prediction_service.py   # Predictions (future)
│   │   ├── ml_service.py           # ML engine (future)
│   │   ├── expert_service.py       # Expert tools (future)
│   │   ├── admin_service.py        # Admin (future)
│   │   └── audit_service.py        # Audit logging (future)
│   │
│   ├── middleware/                 # Custom middleware
│   │   ├── __init__.py
│   │   └── security_headers.py     # Security headers
│   │
│   └── utils/                      # Utility functions
│       ├── __init__.py
│       ├── validators.py           # Custom validators (future)
│       └── helpers.py              # Helper functions (future)
│
├── alembic/                        # Database migrations
│   ├── versions/                   # Migration files
│   ├── env.py                      # Alembic environment
│   ├── script.py.mako              # Migration template
│   └── README                      # Alembic documentation
│
├── tests/                          # Tests
│   ├── __init__.py
│   ├── conftest.py                 # Pytest configuration
│   ├── test_health.py              # Health check tests
│   ├── test_auth.py                # Auth tests (future)
│   └── test_predictions.py         # Prediction tests (future)
│
├── scripts/                        # Utility scripts
│   ├── start.sh                    # Start script
│   └── test.sh                     # Test script
│
├── requirements.txt                # Python dependencies
├── pyproject.toml                  # Poetry configuration
├── Dockerfile                      # Docker image
├── alembic.ini                     # Alembic configuration
├── .env                            # Environment variables
├── .env.example                    # Environment template
├── .gitignore                      # Git ignore rules
└── README.md                       # Documentation
```

## 🔧 Core Components

### 1. FastAPI Application (main.py)

The main application file configures:
- FastAPI instance with metadata
- CORS middleware for frontend communication
- Security headers middleware
- GZip compression
- API router inclusion
- Startup/shutdown event handlers

### 2. Configuration (core/config.py)

Centralized settings using Pydantic BaseSettings:
- Environment-specific configuration
- Database connection strings
- Redis connection strings
- Security settings (JWT, CORS)
- Feature flags
- External API keys

### 3. Database Session (db/session.py)

SQLAlchemy engine and session management:
- Connection pooling
- Session lifecycle management
- Dependency injection for routes

### 4. Redis Client (core/redis.py)

Redis connection management:
- Multiple database support (0-15)
- Connection pooling
- Helper functions for each database

### 5. Security (core/security.py)

Security utilities:
- Password hashing (bcrypt)
- JWT token generation/validation
- Security headers configuration

### 6. Logging (core/logging.py)

Structured logging:
- JSON format for production
- Text format for development
- Configurable log levels
- Third-party library log filtering

## 💾 Database Architecture

### Multi-Schema Design

The application uses 5 PostgreSQL schemas:

#### 1. users Schema (17 tables)
- User accounts and authentication
- User profiles and preferences
- Roles and permissions (RBAC)
- Subscriptions and payments
- Notifications and preferences

#### 2. predictions Schema (16 tables)
- Predictions with source tracking
- Matches and fixtures
- Teams and leagues
- Betting markets and odds
- Prediction history and results

#### 3. ml_models Schema (12 tables)
- ML model registry
- Training runs and hyperparameters
- Model deployments and versions
- A/B testing framework
- Model explainability (SHAP, LIME)

#### 4. analytics Schema (13 tables)
- User performance metrics
- Prediction analytics
- Expert performance tracking
- Model performance comparison
- Revenue and engagement metrics

#### 5. audit Schema (8 tables)
- Comprehensive audit logging
- Data access tracking
- GDPR compliance logs
- Security monitoring
- 7-year retention policy

### Database Connection

```python
# Connection string format
DATABASE_URL = "postgresql://user:password@host:port/database"

# Example
DATABASE_URL = "postgresql://postgres:postgres123@localhost:5432/soccer_predictions"

# SQLAlchemy engine
engine = create_engine(DATABASE_URL, poolclass=NullPool)
```

### Migration Strategy

Using Alembic for database migrations:
- Version-controlled schema changes
- Automatic migration generation
- Rollback support
- Multi-schema support

## 🗄️ Caching Strategy

### Redis Database Allocation

```python
# DB 0: User sessions and authentication
- Session tokens
- JWT blacklist
- Login attempts tracking

# DB 1: Prediction caching
- Prediction results
- Match predictions
- Prediction analytics

# DB 2: Expert tools cache
- Expert analysis data
- Override history
- Expert performance metrics

# DB 3: ML model predictions cache
- ML baseline predictions
- Model outputs
- Feature vectors

# DB 4: Real-time match data
- Live match updates
- Real-time odds
- Match events

# DB 5: API rate limiting
- Request counters
- Rate limit tracking
- IP-based throttling

# DB 6-15: Reserved for future use
```

### Cache Patterns

```python
# Cache-aside pattern
def get_prediction(prediction_id):
    # Try cache first
    cached = redis.get(f"prediction:{prediction_id}")
    if cached:
        return json.loads(cached)
    
    # Fetch from database
    prediction = db.query(Prediction).get(prediction_id)
    
    # Store in cache
    redis.setex(
        f"prediction:{prediction_id}",
        300,  # 5 minutes TTL
        json.dumps(prediction)
    )
    
    return prediction
```

## 🔐 Security

### Authentication Flow

```
1. User Login
   ├─ Validate credentials
   ├─ Generate access token (7 days)
   ├─ Generate refresh token (30 days)
   └─ Return tokens

2. API Request
   ├─ Extract Bearer token
   ├─ Validate JWT signature
   ├─ Check expiration
   ├─ Load user from token
   └─ Check permissions

3. Token Refresh
   ├─ Validate refresh token
   ├─ Generate new access token
   └─ Return new token
```

### Security Headers

All responses include:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000`
- `Content-Security-Policy: default-src 'self'`
- `Referrer-Policy: strict-origin-when-cross-origin`

### CORS Configuration

```python
BACKEND_CORS_ORIGINS = [
    "http://localhost:3000",  # React dev server
    "http://localhost:5173",  # Vite dev server
]

# In production, restrict to actual domain
BACKEND_CORS_ORIGINS = ["https://yourdomain.com"]
```

## 📡 API Design

### RESTful Principles

- Resource-based URLs
- HTTP methods (GET, POST, PUT, DELETE)
- Status codes (200, 201, 400, 401, 404, 500)
- JSON request/response format

### Versioning

API versioning via URL path:
- `/api/v1/*` - Version 1 (current)
- `/api/v2/*` - Version 2 (future)

### Response Format

```json
{
  "data": { ... },
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 100
  },
  "links": {
    "self": "/api/v1/predictions?page=1",
    "next": "/api/v1/predictions?page=2",
    "prev": null
  }
}
```

### Error Format

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ]
  }
}
```

## ⚠️ Error Handling

### Exception Hierarchy

```python
# Base exception
class APIException(Exception):
    pass

# Specific exceptions
class ValidationError(APIException):
    pass

class AuthenticationError(APIException):
    pass

class PermissionError(APIException):
    pass

class NotFoundError(APIException):
    pass
```

### Global Exception Handler

```python
@app.exception_handler(APIException)
async def api_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.to_dict()}
    )
```

## ⚡ Performance

### Optimization Strategies

1. **Database**
   - Connection pooling
   - Query optimization
   - Index usage (300+ indexes)
   - Pagination for large datasets

2. **Caching**
   - Redis for frequently accessed data
   - Cache invalidation strategies
   - TTL-based expiration

3. **API**
   - GZip compression
   - Response pagination
   - Async/await for I/O operations
   - Background tasks for heavy operations

4. **Monitoring**
   - Health check endpoints
   - Logging and metrics
   - Performance profiling

### Performance Targets

- API response time: <100ms (p95)
- Database query time: <50ms (p95)
- Cache hit rate: >80%
- Uptime: 99.9%

