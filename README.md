# Soccer Predictions Platform (PredictionsAppsUI)

A soccer match-predictions web application: a React 18 / Vite / TypeScript frontend and a
FastAPI / SQLAlchemy 2 backend on PostgreSQL 15 (five schemas) and Redis 7, with regular,
expert and admin roles, JWT authentication and an expert prediction workflow (1X2,
both-teams-to-score, over/under goals). Fixtures, live scores and results come from
[Live Score API](https://live-score-api.com) and model forecasts from
[GameForecastAPI](https://www.gameforecastapi.com); both are called **server-side** by the backend.
API-Football and TheSportsDB are retained as fallback integrations. See
[Data providers](#data-providers-phase-1) for the full table.

> **Project status.** The latest working session and the open items are in
> [`MORNING_HANDOFF_2026-09-18.md`](MORNING_HANDOFF_2026-09-18.md); an independent audit of that work
> is in [`CODEX_INDEPENDENT_REVIEW.md`](CODEX_INDEPENDENT_REVIEW.md).
> [`CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md`](CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md) holds the
> GitHub and AWS inventory and the dated implementation record in its **Addenda A–E** — but its
> sections 1–27 describe the repository as found on 2026-09-17 and are marked HISTORICAL; do not work
> from them. Product requirements live in [`docs/requirements/`](docs/requirements/).

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

Docker Desktop and Node.js 18+ (tested with 24).

Python: `backend/pyproject.toml` declares `^3.11`, and 3.11 is the supported runtime — create the
virtualenv with `python3.11` explicitly, not with a bare `python`. Note that the virtualenv currently
checked into this working tree is **3.9.6** (the macOS system Python), and the recorded backend test
baseline of 362 passed was produced on it. `backend/README.md` covers the interpreter setup and how
the two compare.

Provider keys (all read by the backend, never by the browser): `LIVESCORE_API_KEY` /
`LIVESCORE_API_SECRET` for fixtures and `GAMEFORECAST_API_KEY` for model forecasts. An
`API_FOOTBALL_KEY` is only needed for the retained API-Football integration.

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
   cp .env.example .env        # then set SECRET_KEY, SMTP_*, LIVESCORE_API_KEY,
                               # LIVESCORE_API_SECRET, GAMEFORECAST_API_KEY, ...
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```

   Interactive API docs: <http://localhost:8000/api/v1/docs>.

3. **Frontend**

   ```bash
   cd frontend
   npm install
   cp .env.example .env        # defaults are fine: VITE_DATA_SOURCE=backend needs no key
   npm run dev                 # http://localhost:3000
   ```

   With the default `VITE_DATA_SOURCE=backend` the browser only talks to the FastAPI backend, so no
   provider key belongs in `frontend/.env`. `API_FOOTBALL_KEY` (no `VITE_` prefix) is read by the
   Vite **dev server** proxy and is only needed for the retained `VITE_DATA_SOURCE=api-football`
   path.

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
| Model forecasts (primary) | [GameForecastAPI](https://www.gameforecastapi.com) via RapidAPI — free plan 10 requests/day | `PREDICTION_PROVIDER=gameforecast` + `GAMEFORECAST_API_KEY` (the account must be subscribed to the API's Basic plan on RapidAPI) | verified live: 1X2, BTTS, over/under 2.5 and 3.5, exact scores, reasoning. A pass over all six competitions currently costs **6 requests** — one `/events` request for each of the five leagues whose GameForecast id is recorded in `competitions.py`, plus one `/leagues` discovery request for the Champions League, whose id is still unresolved. A paginated competition costs up to `MAX_PAGES` (4) requests instead of one |
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

**There is no scheduler.** The project has no cron job, Celery worker or APScheduler: forecast
synchronisation is request-driven and happens only when something calls one of these two paths:

- `GET /api/v1/matches?refresh=true` (the default) returns fixtures and then calls
  `ForecastService.ensure_synced()` when the day has matches
  (`backend/app/api/v1/endpoints/matches.py`, `list_matches`). Competitions synced within
  `GAMEFORECAST_SYNC_INTERVAL_HOURS` (24) are skipped, so this path refreshes a given competition at
  most once a day.
- `POST /api/v1/data-providers/sync` (admin only) clears the cooldowns and calls
  `ensure_synced(force=True)`, which ignores the interval
  (`backend/app/api/v1/endpoints/data_providers.py`, `force_sync`).

A daily allowance resetting at 00:00 UTC restores the *budget*; it does not start a sync. Nothing
is fetched until one of the two requests above arrives.

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

### Expert publishing and the `EXPERT_DIRECT_PUBLISH` flag

Product decision recorded for Phase 1: experts publish directly (`EXPERT_DIRECT_PUBLISH=true`,
`backend/app/core/config.py`). Publishing directly grants **permission to publish**; it is not a
review of anyone's credentials.

Setting the flag to `false` does **not**, on its own, put an administrator in the loop. This is what
actually happens with the flag off, in the code as it stands:

| With `EXPERT_DIRECT_PUBLISH=false` | Behaviour | Where |
|---|---|---|
| A new expert's profile at sign-up | Created **unverified** | `auth.py`, `ensure_expert_profile(..., verified=bool(settings.EXPERT_DIRECT_PUBLISH))` |
| An unverified expert calling an expert endpoint | `403 Expert verification required` | `deps.py`, `get_current_verified_expert_user` |
| Verifying that expert | Admin-only and functional: `POST /api/v1/admin/experts/{user_id}/verify` really sets `is_verified` | `admin.py`, `verify_expert` |
| A new prediction | Created `PENDING` instead of `PUBLISHED`, so it is not public | `expert_prediction.py`, `_initial_status` |
| Publishing that pending prediction | **Not admin-gated.** `POST /api/v1/expert/predictions/{id}/approve` depends on `get_current_expert_user`, which admits any expert *or* admin, and neither the route nor the service checks ownership — an expert can approve their own prediction. Same for `/reject`. | `expert.py`, `approve_prediction` / `reject_prediction`; `expert_prediction.py`, same names |
| Experts already verified while the flag was on | Stay verified; the flag is not applied retroactively | `deps.py`, `get_current_verified_expert_user` |

So the flag off restores the **pending queue** and admin verification of expert *accounts*, but it
does not add administrator review of prediction *content*. The two endpoints carry explicit
`TODO: Change this to require admin user` comments saying exactly that. Enforcing admin review means
changing those dependencies to `get_current_admin_user`, not only flipping the flag.

(The independent review described the approval handler as a "success-only stub". That part is not
accurate: `approve_prediction` does real work — it rejects a non-pending prediction, sets
`PUBLISHED`, records `approved_by`/`approved_at`/`published_at`, writes audit entries and
invalidates the cache. The defect is the missing admin restriction, not a no-op handler.)

## Tests and checks

The backend suite and the three frontend gates below were re-run and are green; the Playwright suite
was last recorded green on 2026-09-18 and was not re-run here. **No test count is quoted on
purpose** — tests are still being added, so any number written down goes stale; run the command and
read the number it prints.

- Backend: `cd backend && ./venv/bin/python -m pytest -o addopts="" -q` — `-o addopts=""` drops the
  coverage flags that `pyproject.toml` sets by default. Most tests are pure unit
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
  Both need the local stack running (see **Local development** above).

## Secrets

Never commit keys or passwords. `backend/.env` and `frontend/.env` are git-ignored and the
`.env.example` files list every setting.

The server-side path is the one that is built and is the default. Every provider credential
(`LIVESCORE_*`, `GAMEFORECAST_API_KEY`, and `API_FOOTBALL_KEY` when the retained API-Football
provider is selected) is read by the backend from `backend/.env` and never reaches the browser;
the UI receives data through `/api/v1/matches`, `/leagues`, `/teams` and `/data-providers/*`
(`backend/app/services/providers/registry.py`, `backend/app/api/v1/api.py`).

The one path that has no production story is the **legacy browser-side** one,
`VITE_DATA_SOURCE=api-football`. It relies on the `/api/football` proxy defined in
`frontend/vite.config.ts`, which exists only while `vite dev` is running; a static production build
has no such proxy, so that data source works in development only. Use `VITE_DATA_SOURCE=backend`
(the default) for anything deployed. Never set `VITE_API_FOOTBALL_KEY`: a `VITE_`-prefixed value is
embedded in the public bundle.

Keys that were committed before 2026-09-17 must be treated as compromised and rotated.

## Deployment

Only a static frontend demo is deployed (two public S3 website buckets in `us-east-1`, serving a
build from October 2025 that predates the current backend); **no backend deployment exists or is
recorded**, and there is no CloudFront, RDS, ElastiCache, ECS or IaC for this project.

`CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md` §13-15 hold the AWS resource inventory. Its §23 phased
plan is part of the range marked HISTORICAL there — read it as the plan proposed on 2026-09-17, not
as an agreed deployment plan.
