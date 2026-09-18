# Soccer Predictions Platform (PredictionsAppsUI)

A soccer match-predictions web application: a React 18 / Vite / TypeScript frontend and a
FastAPI / SQLAlchemy 2 backend on PostgreSQL 15 (five schemas) and Redis 7, with regular,
expert and admin roles, JWT authentication and an expert prediction workflow (1X2,
both-teams-to-score, over/under goals). Fixture data comes from API-Football.

> **Project status:** [`CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md`](CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md)
> holds the verified state of the code, GitHub and AWS, the prioritized backlog and the open
> decisions. Product requirements live in [`docs/requirements/`](docs/requirements/).

## Repository layout

| Path | Contents |
|---|---|
| `frontend/` | Vite + React + TypeScript single-page app (Tailwind, React Router, Axios) |
| `backend/` | FastAPI application (`app/`), Alembic migrations (`alembic/`), tests (`tests/`) |
| `docker/` | Docker Compose for PostgreSQL, Redis and Adminer; DB init/config; backup scripts |
| `docs/` | Requirements, feature notes, database design docs, archived session notes (`docs/archive/`) |
| `api/` | Backend API architecture notes from the initial scaffold (historical) |
| `*_PLAN.md`, `FRONTEND_ARCHITECTURE_ANALYSIS.md` | Architecture plans; partly aspirational, see the status report |

## Prerequisites

Docker Desktop, Node.js 18+ (tested with 24), Python 3.11 (the project targets 3.11), and an
API-Football key.

## Local development

1. **Infrastructure** (PostgreSQL on 5432, Redis on 6379, Adminer on <http://localhost:8081>).
   Run from the repository root with `--project-directory .` so the config and init-script bind
   mounts in `docker/docker-compose.yml` resolve to `docker/postgres/...` and `docker/redis/...`:

   ```bash
   docker compose -f docker/docker-compose.yml --project-directory . up -d
   ```

2. **Backend**

   ```bash
   cd backend
   python3.11 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env        # then set SECRET_KEY, SMTP_*, API_FOOTBALL_KEY, ...
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```

   Interactive API docs: <http://localhost:8000/api/v1/docs>.

3. **Frontend**

   ```bash
   cd frontend
   npm install
   cp .env.example .env        # set API_FOOTBALL_KEY (used only by the dev proxy)
   npm run dev                 # http://localhost:3000
   ```

## Tests and checks

- Backend: `cd backend && pytest` — most tests are pure unit tests; `tests/test_cache_services.py`
  needs Redis and `tests/test_health.py` needs PostgreSQL (`soccer_predictions_test`).
- Frontend: `npm run type-check`, `npm run lint`, `npm run build`.

## Secrets

Never commit keys or passwords. `backend/.env` and `frontend/.env` are git-ignored and the
`.env.example` files list every setting. The API-Football key is read by the Vite dev proxy from
`API_FOOTBALL_KEY` (no `VITE_` prefix) so it never reaches the browser bundle; production builds
must call API-Football through a backend proxy, which is not built yet. Keys that were committed
before 2026-09-17 must be treated as compromised and rotated.

## Deployment

Only a static frontend demo has ever been deployed (an S3 website bucket in `us-east-1`); the
backend has not been deployed anywhere. See the status report (sections 13-15 and 23) for the
current cloud state and the deployment plan.
