# Soccer Predictions Platform - Backend API

FastAPI backend for the Soccer Predictions Platform: multi-schema PostgreSQL, Redis caching, JWT
authentication with regular/expert/admin roles, an expert prediction workflow, and server-side
integrations with external football data and model-forecast providers.

> **There is no ML or AI model in this codebase.** Earlier revisions of this file claimed "ML/AI
> integration"; that was never true. Forecast probabilities come from an external provider
> (GameForecastAPI) and are stored and displayed as that provider published them — nothing is
> generated, derived or interpolated here. A `ml_models` schema exists in the database as a
> placeholder; no model writes to it. A market the provider did not supply is reported as
> **unavailable**, never as 0%.

## 🚀 Quick Start

### Prerequisites

- **Python 3.11** — this is the version the project targets. `pyproject.toml` declares
  `python = "^3.11"`, `[tool.mypy] python_version = "3.11"` and `[tool.black] target-version = ['py311']`.
  Create the virtual environment with `python3.11` explicitly (see step 2); a bare `python` on macOS
  is frequently the system 3.9, and an environment built that way is **not** the version this project
  is configured for even though the test suite currently behaves the same on it.
- PostgreSQL 15+ (running via Docker)
- Redis 7+ (running via Docker)
- Docker & Docker Compose (for infrastructure)

### 1. Start Infrastructure

Run this from the REPOSITORY ROOT, not from `docker/`. The compose file's volume mounts are written
relative to the project directory, so `--project-directory .` is what makes them resolve to
`docker/postgres/` and `docker/redis/`. Running it from inside `docker/` looks for
`docker/docker/postgres/`, which does not exist.

```bash
# from the repository root: PostgreSQL, Redis and Adminer
docker compose -f docker/docker-compose.yml --project-directory . up -d
```

### 2. Setup Python Environment

```bash
# Navigate to backend directory
cd backend

# Confirm you have the targeted interpreter before creating anything
python3.11 --version    # expect: Python 3.11.x

# Create virtual environment — name the interpreter explicitly, do NOT use bare `python`
# On macOS/Linux:
python3.11 -m venv venv
# On Windows:
py -3.11 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies (runtime, test and lint deps are all in this one file;
# there is no separate requirements-dev.txt)
pip install -r requirements.txt

# Verify what you actually got
python --version        # expect: Python 3.11.x
```

`requirements.txt` fully pins every dependency, so a clean 3.11 environment installs without
conflicts (`pip check` reports none). Installing `email-validator==2.1.0` prints a "yanked version"
warning from PyPI; the release was yanked only because its `python_requires` still listed 3.7, and
it installs and works normally.

#### Which Python you end up with

| | Version |
|---|---|
| Version the project targets (`pyproject.toml`) | 3.11 |
| Version the commands above produce | 3.11 |
| Version the earlier `python -m venv venv` instruction produced here | 3.9.6 (macOS system Python) |

The suite has been checked on both interpreters back to back, from the same working tree, with

```bash
python -m pytest -o addopts="" -p no:cacheprovider -q
```

and the pass/fail set was identical on 3.11.9 and on 3.9.6 — there are no 3.11-only failures, and a
clean 3.11 environment built from `requirements.txt` reproduces the same result. That the suite also
happens to pass on 3.9 is not a supported configuration and is not guaranteed to keep holding; build
the environment with `python3.11`.

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
│   ├── main.py                 # FastAPI application entry point
│   ├── api/v1/
│   │   ├── api.py              # router that mounts every endpoint module below
│   │   └── endpoints/
│   │       ├── health.py       # health checks
│   │       ├── auth.py         # register, login, refresh, password reset
│   │       ├── users.py        # profile and account
│   │       ├── predictions.py  # public prediction reads
│   │       ├── expert.py       # expert prediction workflow
│   │       ├── admin.py        # admin dashboard, expert verification, audit logs
│   │       ├── subscriptions.py
│   │       ├── matches.py      # fixtures for a date, live, match detail
│   │       ├── leagues.py
│   │       ├── teams.py
│   │       └── data_providers.py  # provider status, coverage, admin sync
│   ├── core/                   # config, security, deps, logging, redis, permissions
│   ├── db/                     # SQLAlchemy base, session, init
│   ├── models/                 # SQLAlchemy models (incl. provider_data.py)
│   ├── schemas/                # Pydantic schemas
│   ├── services/               # business logic
│   │   ├── providers/          # livescore_api, gameforecast, api_football_provider,
│   │   │                       # thesportsdb_provider, sample, budget, competitions, registry
│   │   ├── match_data_service.py, match_matching.py, match_registry.py, match_cache.py
│   │   ├── forecast_service.py     # forecast sync, rotation, budget, pending retries
│   │   ├── expert_prediction.py, prediction_audit.py, prediction_aggregator.py
│   │   └── cache.py, session_cache.py, prediction_cache.py, email_service.py, …
│   ├── middleware/security_headers.py
│   └── templates/              # e-mail templates
├── alembic/versions/           # database migrations
├── tests/                      # pytest suite
│   ├── conftest.py             # blanks every provider credential; no test calls a provider
│   ├── api/ core/ providers/ scripts/ services/
│   └── test_auth.py, test_health.py, test_permissions.py, test_cache_services.py,
│       test_email_service.py
├── scripts/
│   ├── repair_forecasts.py     # re-derive stored forecasts from their saved raw payload
│   ├── purge_sample_data.py    # drop sample fixtures before switching to a real provider
│   ├── grant_admin.py, test_connections.py, start.sh, test.sh, test_api.sh
├── requirements.txt            # the dependency list actually used by the venv
├── pyproject.toml              # project metadata; also sets the default pytest addopts
├── Dockerfile
├── .env.example                # every setting, with no values
└── README.md                   # this file
```

`.env` is git-ignored and is not in the tree above; copy `.env.example` to create it.

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

`pyproject.toml` sets `addopts = "-v --cov=app --cov-report=html --cov-report=term-missing"`, so a
bare `pytest` always runs coverage and writes an HTML report. Override it with `-o addopts=""` for a
plain run — that is the canonical command:

```bash
# canonical: plain, quiet run
./venv/bin/python -m pytest -o addopts="" -q

# a single file
./venv/bin/python -m pytest -o addopts="" tests/test_health.py

# with coverage (the pyproject default)
./venv/bin/python -m pytest
```

The suite is green (re-run 2026-09-18). **No pass count is quoted here on purpose** — tests are
still being added, so a number written into a README goes stale; run the command and read what it
prints. Build the environment with `python3.11` as the setup section above describes.

What the suite needs:

- Most tests are pure unit tests and need nothing.
- `tests/test_cache_services.py` needs **Redis**.
- The database-backed tests need **PostgreSQL** (`TEST_DATABASE_URL`, default
  `soccer_predictions_test`).

**No test makes a real provider request.** `tests/conftest.py` blanks every provider credential and
the providers are driven through `httpx.MockTransport`. Keep it that way: the provider allowances are
small and a test that spends one is a defect.

Lint baseline:

```bash
./venv/bin/python -m pyflakes app/ scripts/
```

Do not disable a rule or raise a threshold to make a gate pass.

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

`BACKEND_CORS_ORIGINS` in `app/core/config.py` defaults to four development origins:

```python
BACKEND_CORS_ORIGINS = [
    "http://localhost:3000",   # React frontend (the Vite dev script's port)
    "http://localhost:5173",   # Vite's own default port
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
```

It is overridable from the environment and accepts either a JSON list or a comma-separated string
(`assemble_cors_origins`). If the frontend is served on another port, that origin must be added or
the browser will block every request — for example, running the UI on 3100:

```bash
BACKEND_CORS_ORIGINS="http://localhost:3100,http://127.0.0.1:3100,http://localhost:3000" \
  ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
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

The backend's service block in `docker/docker-compose.yml` is **commented out**, so Compose starts
only PostgreSQL, Redis and Adminer; the backend is run on the host against those containers. Compose
must be invoked from the repository root with both flags, or its relative bind mounts resolve to
non-existent `docker/docker/...` paths:

```bash
docker compose -f docker/docker-compose.yml --project-directory . up -d
```

See [`../docker/README.md`](../docker/README.md) for why.

## 📚 API Documentation

### Health Check Endpoints

- `GET /` - Root endpoint with API information
- `GET /health` - Basic health check
- `GET /api/v1/health` - API v1 health check
- `GET /api/v1/health/detailed` - Detailed health check (database + Redis)
- `GET /api/v1/health/database` - Database health check
- `GET /api/v1/health/redis` - Redis health check

### Implemented endpoint groups

These are **implemented and mounted**, not planned — see `app/api/v1/api.py`. An earlier revision of
this file listed them under "Future Endpoints".

| Prefix | Auth | What it serves |
|---|---|---|
| `/api/v1/auth/*` | public | register, login, refresh, logout, password reset |
| `/api/v1/users/*` | user | profile and account management |
| `/api/v1/predictions/*` | public | published expert predictions |
| `/api/v1/matches/*` | public | fixtures for a date, live matches, match detail |
| `/api/v1/leagues/*` | public | covered competitions |
| `/api/v1/teams/*` | public | teams |
| `/api/v1/data-providers/*` | public reads; `POST /sync` is **admin** | provider status, budgets, measured coverage, forced sync |
| `/api/v1/expert/*` | expert (or admin) | the expert prediction workflow |
| `/api/v1/admin/*` | **admin** | dashboard, expert verification, audit logs |
| `/api/v1/subscriptions/*` | user | subscription tiers |

Interactive documentation for all of them: <http://localhost:8000/api/v1/docs>.

Two notes on what these endpoints do *not* do:

- `/api/v1/data-providers/coverage` reports `accuracy_available: false` with a reason. **No accuracy
  figure is published anywhere**, because no forecast has been settled and scored.
- `POST /api/v1/expert/predictions/{id}/approve` and `/reject` are declared "Expert or Admin" and
  carry explicit `TODO` comments: they are **not** restricted to administrators and perform no
  ownership check, so an expert can approve their own prediction. See the root `README.md` for what
  `EXPERT_DIRECT_PUBLISH=false` does and does not change.

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

Current and authoritative:

- The repository root [`README.md`](../README.md) — providers, quota protection, forecast evidence,
  the expert publishing flag, and how to run the whole stack.
- [`../MORNING_HANDOFF_2026-09-18.md`](../MORNING_HANDOFF_2026-09-18.md) — the latest working
  session and the open items.

Historical, kept for reference — these describe the **initial scaffold** (2025) and do not match the
current provider architecture or endpoint set:

- `../api/README.md`, `../api/API_ARCHITECTURE.md`, `../api/QUICK_REFERENCE.md`,
  `../api/IMPLEMENTATION_SUMMARY.md`, `../api/TESTING_GUIDE.md`

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Write tests
4. Run tests and linting
5. Submit a pull request

## 📄 License

Copyright © Soccer Predictions Platform. No `LICENSE` file exists in this repository, so no licence
is currently granted; ask the owner before reusing this code.

