# Soccer Predictions Platform - Backend API

FastAPI-based backend for the Soccer Predictions Platform with multi-schema PostgreSQL, Redis caching, and ML/AI integration.

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (running via Docker)
- Redis 7+ (running via Docker)
- Docker & Docker Compose (for infrastructure)

### 1. Start Infrastructure

```bash
# Start PostgreSQL, Redis, and Adminer
cd docker
docker-compose up -d
```

### 2. Setup Python Environment

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings (defaults work for local development)
```

### 4. Run Database Migrations

```bash
# Run Alembic migrations
alembic upgrade head
```

### 5. Start Development Server

```bash
# Start with hot reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use the start script
chmod +x scripts/start.sh
./scripts/start.sh
```

### 6. Access API Documentation

- **Swagger UI**: http://localhost:8000/api/v1/docs
- **ReDoc**: http://localhost:8000/api/v1/redoc
- **OpenAPI JSON**: http://localhost:8000/api/v1/openapi.json

## 📁 Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry point
│   ├── api/                    # API routes
│   │   └── v1/
│   │       ├── api.py          # API router
│   │       └── endpoints/      # Endpoint modules
│   │           └── health.py   # Health check endpoints
│   ├── core/                   # Core functionality
│   │   ├── config.py           # Settings and configuration
│   │   ├── security.py         # Security utilities
│   │   ├── logging.py          # Logging configuration
│   │   └── redis.py            # Redis client
│   ├── db/                     # Database
│   │   ├── base.py             # SQLAlchemy base
│   │   ├── session.py          # Database session
│   │   └── init_db.py          # Database initialization
│   ├── models/                 # SQLAlchemy models
│   ├── schemas/                # Pydantic schemas
│   ├── services/               # Business logic
│   └── middleware/             # Custom middleware
│       └── security_headers.py # Security headers
├── alembic/                    # Database migrations
│   ├── versions/               # Migration files
│   ├── env.py                  # Alembic environment
│   └── script.py.mako          # Migration template
├── tests/                      # Tests
│   ├── conftest.py             # Pytest configuration
│   └── test_health.py          # Health check tests
├── scripts/                    # Utility scripts
│   ├── start.sh                # Start script
│   └── test.sh                 # Test script
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Poetry configuration
├── Dockerfile                  # Docker image
├── .env                        # Environment variables
├── .env.example                # Environment template
└── README.md                   # This file
```

## 🔧 Configuration

### Environment Variables

Key environment variables (see `.env.example` for full list):

```bash
# Application
PROJECT_NAME="Soccer Predictions Platform API"
ENVIRONMENT="development"
DEBUG=true

# Database
POSTGRES_SERVER="localhost"
POSTGRES_PORT=5432
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="postgres123"
POSTGRES_DB="soccer_predictions"

# Redis
REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_DB=0

# Security
SECRET_KEY="your-secret-key"
ACCESS_TOKEN_EXPIRE_MINUTES=10080  # 7 days
```

### Redis Database Allocation

The application uses multiple Redis databases for different purposes:

- **DB 0**: User sessions and authentication
- **DB 1**: Prediction caching
- **DB 2**: Expert tools cache
- **DB 3**: ML model predictions cache
- **DB 4**: Real-time match data
- **DB 5**: API rate limiting

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_health.py

# Run with verbose output
pytest -v
```

## 📊 Database

### Multi-Schema Architecture

The application uses a multi-schema PostgreSQL database:

- **users**: User accounts, profiles, roles, permissions
- **predictions**: Predictions, matches, teams, leagues
- **ml_models**: ML models, training runs, deployments
- **analytics**: Performance metrics, user analytics
- **audit**: Audit logs, data access logs, GDPR compliance

### Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

## 🔒 Security

### CORS

CORS is configured to allow requests from the frontend:

```python
BACKEND_CORS_ORIGINS = [
    "http://localhost:3000",  # React frontend
    "http://localhost:5173",  # Vite dev server
]
```

### Security Headers

The following security headers are automatically added to all responses:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000`
- `Content-Security-Policy: default-src 'self'`
- `Referrer-Policy: strict-origin-when-cross-origin`

## 🐳 Docker

### Build Image

```bash
docker build -t soccer-predictions-api .
```

### Run Container

```bash
docker run -p 8000:8000 \
  -e DATABASE_URL=postgresql://postgres:postgres123@host.docker.internal:5432/soccer_predictions \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  soccer-predictions-api
```

### Docker Compose

The backend service is pre-configured in `docker/docker-compose.yml` (currently commented out).

## 📚 API Documentation

### Health Check Endpoints

- `GET /` - Root endpoint with API information
- `GET /health` - Basic health check
- `GET /api/v1/health` - API v1 health check
- `GET /api/v1/health/detailed` - Detailed health check (database + Redis)
- `GET /api/v1/health/database` - Database health check
- `GET /api/v1/health/redis` - Redis health check

### Future Endpoints

- `/api/v1/auth/*` - Authentication endpoints
- `/api/v1/users/*` - User management
- `/api/v1/predictions/*` - Predictions
- `/api/v1/matches/*` - Match data
- `/api/v1/leagues/*` - League data
- `/api/v1/teams/*` - Team data
- `/api/v1/expert/*` - Expert tools
- `/api/v1/admin/*` - Admin endpoints

## 🛠️ Development

### Code Quality

```bash
# Format code with Black
black app/

# Sort imports with isort
isort app/

# Lint with flake8
flake8 app/

# Type check with mypy
mypy app/
```

### Hot Reload

The development server automatically reloads when code changes:

```bash
uvicorn app.main:app --reload
```

## 📝 Logging

Logs are output to stdout in JSON format (configurable via `LOG_FORMAT`):

```json
{
  "timestamp": "2024-01-01T12:00:00.000000",
  "level": "INFO",
  "logger": "app.main",
  "message": "Starting Soccer Predictions Platform API",
  "module": "main",
  "function": "startup_event",
  "line": 65
}
```

## 🚀 Deployment

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set `DEBUG=false`
- [ ] Generate secure `SECRET_KEY`
- [ ] Configure production database
- [ ] Configure production Redis
- [ ] Set up SSL/TLS
- [ ] Configure allowed hosts
- [ ] Set up monitoring and logging
- [ ] Configure backup strategy
- [ ] Set up CI/CD pipeline

## 📖 Additional Documentation

See the `api/` folder for comprehensive documentation:

- `api/README.md` - Main API documentation
- `api/API_ARCHITECTURE.md` - Architecture details
- `api/QUICK_REFERENCE.md` - Command cheat sheet
- `api/IMPLEMENTATION_SUMMARY.md` - Implementation summary

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Write tests
4. Run tests and linting
5. Submit a pull request

## 📄 License

Copyright © 2024 Soccer Predictions Platform

