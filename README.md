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

## Data providers (Phase 1)

Fixtures, live scores, results, standings and model forecasts are fetched **server-side** by the
backend and served to the UI through `/api/v1/matches`, `/api/v1/leagues`, `/api/v1/teams` and
`/api/v1/data-providers/status`. Credentials never reach the browser. Everything is keyed by
canonical competitions (`premier_league`, `la_liga`, `serie_a`, `bundesliga`, `ligue_1`,
`champions_league`) and cross-provider fixture identity is resolved by competition + team names +
UTC kickoff, never by numeric ids (`backend/app/services/match_matching.py`).

| Role | Provider | Setting | Status |
|---|---|---|---|
| Match data (primary) | [Live Score API](https://live-score-api.com) — 14-day trial, 1,500 requests/day | `DATA_PROVIDER=livescore` + `LIVESCORE_API_KEY` / `LIVESCORE_API_SECRET` | verified live (fixtures, calendar, competition ids 2/3/4/1/5/244); calls are spaced 1 s apart because bursts get HTTP 401 |
| Model forecasts (primary) | [GameForecastAPI](https://www.gameforecastapi.com) via RapidAPI — free plan 10 requests/day | `PREDICTION_PROVIDER=gameforecast` + `GAMEFORECAST_API_KEY` (the account must be subscribed to the API's Basic plan on RapidAPI) | verified live: 1X2, BTTS, over/under 2.5 and 3.5, exact scores, reasoning; one sync of six competitions costs 6 requests |
| Match data (retained fallback) | API-Football (free plan, current season restricted) | `DATA_PROVIDER=api_football` or in `DATA_PROVIDER_FALLBACKS` | retained integration, limited |
| Match data (retained fallback) | TheSportsDB v1 | `DATA_PROVIDER=thesportsdb` + `THESPORTSDB_KEY` | retained integration; the stored key is rejected as invalid, so it needs a valid key before it can serve as a fallback |
| Forecasts (retained fallback) | API-Football `/predictions` (1X2 only) | `PREDICTION_PROVIDER=api_football` | retained integration |
| Local development | deterministic sample data (clearly labelled "not real") | `DATA_PROVIDER=sample`, `PREDICTION_PROVIDER=sample` | for running the UI without any key |

### Probabilities

GameForecastAPI publishes every probability on a fixed **0-100 percentage scale**. That scale is
applied explicitly and unconditionally (`PROBABILITY_SCALE` in
`backend/app/services/providers/gameforecast.py`), never inferred from whether a value happens to
exceed 1 — inferring it turns a genuine 1% into 100% certainty. Values that are not finite numbers
inside the published range are dropped, and a market whose values are all zero is treated as
unavailable rather than shown as 0%. Complementary pairs (yes/no, over/under) and the 1X2 outcomes
are checked against a tolerance; a payload that fails the check is flagged in `anomalies` and shown
with a caution, never silently corrected. Exact scores keep the provider's own "other scorelines"
remainder in a separate field, so a partial list is never renormalised to imply certainty.

A market the provider did not supply is `null` end to end and renders as **Unavailable**. Nothing in
the real-data path generates, interpolates or derives a probability.

### Quota protection

Every provider call goes through a per-day request budget in Redis
(`LIVESCORE_DAILY_REQUEST_BUDGET`, `GAMEFORECAST_DAILY_REQUEST_BUDGET`). The counter records
**outbound requests only**: a reservation refused because the allowance is already spent never
reaches the provider and is counted separately under `refused_today`, so it cannot silently steal a
real request. A request that was sent and then failed still counts, because the provider charged it.
Counters are keyed by UTC day, which is when both plans reset, and are never reset by hand.
For a small plan (100 requests/day or fewer) the budget **fails closed**: if Redis is unavailable the
backend refuses to call the provider rather than spending blind.

Responses are cached (`MATCH_CACHE_TTL_*`), live scores are only polled while a covered match is
within its live window, and a stale cached copy is served (and flagged) when a provider fails.
Forecasts are synced at most once per `GAMEFORECAST_SYNC_INTERVAL_HOURS` per competition, and the
competitions are visited **least-recently-synced first**, so an allowance too small for all six
stops starving the tail of the list. Competitions that did not get their turn are reported under
`deferred` and lead the next run. A Redis lock stops two workers paying for the same competition.

A forecast older than `FORECAST_MAX_AGE_HOURS` or for a match that already kicked off is reported as
`stale` / `kickoff_passed`, never as current. A spent allowance is reported separately, as
`refresh_blocked`: "we cannot refresh this right now" is a different statement from "this does not
exist", and only one of them is a reason to distrust what is on screen.

### Forecast evidence

A forecast is the record of what a model said **before** a match was played, so updating a row in
place would destroy the only evidence. `predictions.provider_forecasts` holds the current forecast
per match and provider (one indexed lookup for a page render);
`predictions.provider_forecast_snapshots` is an append-only history, one row per distinct forecast
content, with the provider's own model-run time, the provider's update time, our retrieval time, the
kickoff known at capture, and whether the capture really was prematch (`NULL` when the kickoff was
not known — a stored `false` would assert something we cannot know). Re-fetching unchanged content
only moves `last_fetched_at`. Forecasts are stored separately from expert predictions throughout.

No accuracy figure is published anywhere. Scoring a forecast needs settled results, none have been
scored, and `/api/v1/data-providers/coverage` reports `accuracy_available: false` with the reason
rather than a number. The home page shows counts measured from that endpoint.

After a parser fix, `python backend/scripts/repair_forecasts.py --dry-run` reports what would change
and `python backend/scripts/repair_forecasts.py` applies it, re-deriving every stored forecast from
the raw payload saved with it. It makes no provider request, is idempotent, preserves provider
timestamps and expert data, appends the corrected reading to the history rather than overwriting it,
and clears the caches that held the old numbers.

Failures back off automatically: rejected credentials pause a provider for 30 minutes, an exhausted
quota until UTC midnight, other errors 2 minutes (`cooling_down` in `/api/v1/data-providers/status`).
After fixing credentials, an admin `POST /api/v1/data-providers/sync` clears the pauses and retries.
Before switching a development database from `sample` to a real provider, run
`python backend/scripts/purge_sample_data.py` to drop the sample fixtures.

Switching providers: change `DATA_PROVIDER` / `PREDICTION_PROVIDER` (and the fallback list) in
`backend/.env` and restart the backend. Expert predictions stay attached to the internal match
records because every provider's fixture id is recorded in `predictions.provider_entity_refs`.

Frontend: `VITE_DATA_SOURCE=backend` (default) uses the endpoints above; `VITE_DATA_SOURCE=api-football`
re-enables the legacy browser-side API-Football path (retained). Randomized placeholder predictions are
gone from the real-data path; missing markets are shown as "Unavailable".

Product decision recorded for Phase 1: experts publish directly (`EXPERT_DIRECT_PUBLISH=true`); set it
to `false` to restore the review queue and admin verification.

## Tests and checks

- Backend: `cd backend && ./venv/bin/python -m pytest -o addopts="" -q` — most tests are pure unit
  tests; `tests/test_cache_services.py` needs Redis and the database-backed tests need PostgreSQL
  (`TEST_DATABASE_URL`, default `soccer_predictions_test`). No test makes a real provider request:
  `tests/conftest.py` blanks every provider credential and providers are driven through
  `httpx.MockTransport`.
- Frontend: `npm run type-check`, `npm run lint`, `npm run build`.
- Browser: `npm run e2e:mocked` runs the deterministic Playwright suite (desktop and mobile) against
  captured, sanitised payloads in `frontend/e2e/fixtures` — it stubs every backend call, so it spends
  no provider allowance and covers the edge cases that are hard to produce on demand (missing
  markets, 1% probabilities, exhausted quota, expired trial, empty days, backend failures, timezone
  boundaries). `npm run e2e:live` runs the expert publishing flow against the local backend, creating
  and removing only its own clearly-marked QA records and never triggering a provider refresh.
  Both need the local stack running (see below).

## Secrets

Never commit keys or passwords. `backend/.env` and `frontend/.env` are git-ignored and the
`.env.example` files list every setting. The API-Football key is read by the Vite dev proxy from
`API_FOOTBALL_KEY` (no `VITE_` prefix) so it never reaches the browser bundle; production builds
must call API-Football through a backend proxy, which is not built yet. Keys that were committed
before 2026-09-17 must be treated as compromised and rotated.

## Deployment

Only a static frontend demo is deployed (an S3 website bucket in `us-east-1`); no backend
deployment exists or is recorded. See the status report (sections 13-15 and 23) for the
current cloud state and the deployment plan.
