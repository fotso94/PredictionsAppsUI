# The isolated development pair

How to run a second frontend and backend beside the ones under observation, on a copy of the
data, with every provider door closed. Used for the multi-market and slip work on 2026-09-25
while the retry watcher was recording the backend on port 8000; nothing about that backend, its
Redis counters or its fixtures was touched.

## Database: a clone

```bash
docker exec soccer_predictions_postgres psql -U postgres -tAc "create database soccer_predictions_dev"
docker exec soccer_predictions_postgres sh -c "pg_dump -U postgres soccer_predictions | psql -q -U postgres soccer_predictions_dev"
# pg_dump does not carry the database-level search_path; alembic_version lives in the users schema
docker exec soccer_predictions_postgres psql -U postgres -tAc \
  "alter database soccer_predictions_dev set search_path = users, predictions, ml_models, analytics, audit, public"
```

Migrations run against the clone by pointing the settings at it:

```bash
cd backend && POSTGRES_DB=soccer_predictions_dev ./venv/bin/alembic upgrade head
```

## Backend on 8001: scheduler off, no credentials, its own Redis databases

```bash
cd backend && POSTGRES_DB=soccer_predictions_dev SYNC_SCHEDULER_ENABLED=false \
  LIVESCORE_API_KEY= LIVESCORE_API_SECRET= GAMEFORECAST_API_KEY= API_FOOTBALL_KEY= THESPORTSDB_KEY= \
  REDIS_DB_SESSIONS=10 REDIS_DB_PREDICTIONS=11 REDIS_DB_EXPERT_TOOLS=12 REDIS_DB_ML_MODELS=13 REDIS_DB_MATCH_DATA=14 REDIS_DB_RATE_LIMIT=15 \
  BACKEND_CORS_ORIGINS='["http://localhost:3101","http://127.0.0.1:3101"]' \
  ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Blank credentials make every provider "not configured": a page that asks for a refresh gets a
clean refusal and spends nothing. Redis databases 10–15 keep its sessions, caches and budget
counters apart from the live instance's 0–5.

## Frontend on 3101

`frontend/.env.dev8001.local` (gitignored) holds `VITE_API_BASE_URL=http://localhost:8001`;
the `frontend-isolated` entry in `.claude/launch.json` starts Vite with `--mode dev8001 --port 3101`.

## Browser tests against the pair

```bash
cd frontend && E2E_BASE_URL=http://localhost:3101 E2E_API_URL=http://127.0.0.1:8001 npx playwright test --project=live
```

The mocked projects need neither backend; they stub every `/api/v1` call.
