# PredictionsAppsUI — Project Status and Next Steps (Takeover Assessment)

**Prepared by:** Claude (Fable 5.1) acting as Principal Architect / Senior Full-Stack / AWS Cloud Architect / DevOps / Technical Reviewer
**Assessment date:** 2026-09-17
**Mode:** strict read-only. No application code, documentation, dependency, Git, or AWS state was changed. This file is the only project file created.
**Report location note:** the brief referenced `~/Documents/PredictionsAppsUI/`; that path does not exist. The repository lives at `~/Documents/DevProjects/PredictionsAppsUI/`, so the report was written there.

> # ⚠️ Read this first: sections 1–27 are HISTORICAL
>
> **Sections 1–27 describe the repository as found on 2026-09-17, *before* any change was made.**
> They are an accurate record of the starting point and a wrong description of the project today.
> Several of their instructions — create a `develop` branch, build the server-side data proxy, delete
> TheSportsDB, impose an admin approval gate — are **done or deliberately reversed**; do not act on
> them. §1 and §27 carry their own detailed notices.
>
> **For the current state, read in this order:**
>
> 1. The root [`README.md`](README.md) — what the system is, how to run it, the provider
>    architecture, how the tests are run.
> 2. [`MORNING_HANDOFF_2026-09-18.md`](MORNING_HANDOFF_2026-09-18.md) — the latest working session and
>    §8's list of open items in priority order.
> 3. [`CODEX_INDEPENDENT_REVIEW.md`](CODEX_INDEPENDENT_REVIEW.md) — an independent audit of that work.
> 4. **Addenda A–E at the end of this file** — the dated record of every implementation phase since
>    2026-09-17. These are current; sections 1–27 are not.
>
> Addendum summary: **A** (docs scrubbed/archived, BTTS work committed, frontend build fixed, `main`
> carries the real application), **B** (credentials removed from code, migration made portable,
> README added), **C** (owner decisions: experts publish directly, security hardening deferred to
> Phase 2), **D** (Phase 1 data and prediction integrations — Live Score API and GameForecastAPI,
> called server-side), **E** (Phase 1 correctness pass).
>
> Sections 9–12, 16 and 17 in particular record Git, AWS and test state at a single moment and have
> since moved. Re-run the commands rather than quoting the numbers.

### How to read the labels

| Label | Meaning |
|---|---|
| **VERIFIED** | Confirmed first-hand (file read, command output, HTTP probe, AWS API). |
| **PARTIALLY VERIFIED** | Core of the claim confirmed; some part could not be checked. |
| **NOT VALIDATED** | Could not be checked in read-only mode (needs a running DB/Redis, external account, or owner knowledge). |
| **CONTRADICTED** | Evidence disagrees with the claim. |
| **NOT IMPLEMENTED** | Documented/planned but no code or resource exists. |

Source tags: `[DOC]` documentation-derived · `[CODE]` code-derived · `[GITHUB]` GitHub-derived · `[AWS]` AWS-derived · `[INFERENCE]` my technical inference · `[RECOMMENDATION]` my recommendation.

Secrets policy: every key, password, token, or personal e-mail found is referenced by **file and line only**; no value is reproduced here.

---

## 1. Executive summary

> # ⚠️ HISTORICAL — describes the repository as found on **2026-09-17**, before any change
>
> **Do not act on this section.** It describes a frozen, unbuildable prototype with leaked
> credentials and no server-side data path. Most of what it lists as urgent has since been done, and
> some of it has been deliberately reversed by owner decision. It is kept as the record of the
> starting point, not as instructions.
>
> **For the current state, read instead:**
>
> | Question | Where the current answer is |
> |---|---|
> | What the system is and how to run it | the root [`README.md`](README.md) |
> | What changed overnight and what is still open | [`MORNING_HANDOFF_2026-09-18.md`](MORNING_HANDOFF_2026-09-18.md) |
> | What an independent audit found | [`CODEX_INDEPENDENT_REVIEW.md`](CODEX_INDEPENDENT_REVIEW.md) |
> | The detail of the work done since | Addenda A–E at the end of this file |
>
> **What has changed since this summary was written** (each verifiable in the code today):
>
> - The frontend **builds**. `type-check`, `lint` (`--max-warnings 0`) and `build` all pass.
> - The **server-side data path exists**: `/api/v1/matches`, `/leagues`, `/teams` and
>   `/data-providers/*` are implemented, and provider credentials are read by the backend only.
> - **The data providers changed.** Live Score API (fixtures) and GameForecastAPI (model forecasts)
>   are primary. API-Football and TheSportsDB were **retained as fallbacks by owner decision** — the
>   instruction further down to delete TheSportsDB is reversed; do not follow it.
> - **Credentials were removed from application code** (Addendum B). Rotation of the exposed keys
>   remains an owner action.
> - **Public registration no longer accepts `role=admin`** (`backend/app/api/v1/endpoints/auth.py`).
> - **Experts publish directly** (`EXPERT_DIRECT_PUBLISH=true`, Addendum C). The instruction below to
>   impose an admin approval gate is superseded; see the root README for what the flag actually does
>   when switched off.
> - There is a **backend test baseline of 362 passing tests** (recorded on Python 3.9.6) and a
>   **79-test Playwright suite**, where this summary found the suite unrunnable.
>
> **What remains true from this summary:** no backend has ever been deployed; the only cloud
> footprint is the two stale public S3 buckets; there is no CI; the exposed keys still need rotating;
> and no accuracy figure is published anywhere because nothing has been settled or scored.

---

### Original summary, as written on 2026-09-17 (historical)

**Where the project stands.** PredictionsAppsUI is a soccer-predictions web platform: a React 18 / Vite / TypeScript frontend and a FastAPI / SQLAlchemy 2 / PostgreSQL 15 (5 schemas, 66 tables) / Redis 7 backend, with three user profiles (regular, expert, admin), JWT auth, an expert manual-prediction workflow, and API-Football as the live fixtures source. AugmentCode worked on it from 2025-09-22 to about 2025-10-16 in a single burst; nothing has changed since. The work is substantial and the technical direction is sound, but the project is **not in a releasable or reproducible state** today.

**What is actually deployed.** The only cloud footprint is two public S3 static-website buckets in `us-east-1` (`soccer-predictions-app-7787` serving a frontend build from 2025-10-07, and `predictions-app-778778324` serving a one-page API-Football widget test). Both are live over HTTP only. No CloudFront, Route 53, RDS, ElastiCache, ECS, Lambda, or IaC exists for this project, so **the backend has never been deployed anywhere** [AWS, VERIFIED]. The deployed frontend predates authentication and the expert features and calls API-Football directly from the browser with an embedded key.

**Most urgent findings (all VERIFIED).**
1. **Leaked credentials in a public GitHub repo.** An API-Football Pro key is committed in `frontend/vite.config.ts` and `frontend/src/services/api-football.service.ts` (since commit `e07b2b2`, 2025-10-08), appears in a tracked doc, in the built bundle and source map, and in the live S3 site. A TheSportsDB premium key, an SMTP password (`backend/test_smtp_connection.py`), a test expert password (`backend/create_expert_user.py`), and a dev DB URL (`backend/alembic.ini`) are also committed. These must be rotated before any other work.
2. **The frontend does not build.** `tsc --noEmit` reports 10 errors (7 already at HEAD, 3 from uncommitted work) and `npm run lint` aborts on a broken ESLint config, so `npm run build` fails.
3. **Backend security defects.** Self-registration accepts `role="admin"`; "revoke all sessions" on password change/reset does not actually invalidate refresh tokens; `SECRET_KEY` defaults to a per-process random value while the production Dockerfile runs 4 workers.
4. **Broken or stubbed backend paths.** Expert override always fails (wrong ORM kwargs), audit metadata is silently dropped, the public `date` filter crashes, and 10 of 54 API routes are stubs (ML baseline, admin audit/config/approve, subscriptions are mock data).
5. **Uncommitted, undocumented-in-git work.** 16 modified tracked files (+1,183/−106) and 68 untracked paths, including the only Alembic migration for the BTTS/Total-Goals feature. Committing the modified files without the migration would ship model columns with no schema change.
6. **Local dev environment is not reproducible on this machine.** The Docker Compose file's relative bind-mounts resolve to `docker/docker/...` (empty dirs, and `redis.conf` becomes a directory), the backend service is commented out, the Python venv is 3.9.6 while the project requires 3.11, and no project containers or volumes currently exist.

**Recommendation in one line.** Keep the architecture and the bulk of the code; spend the first phase on rotation of secrets, restoring a green build/test baseline, and committing the WIP correctly, then finish the MVP feature gaps, and only then deploy with a lean AWS footprint (S3+CloudFront, one container service, small RDS/Redis) rather than the documented $1,050–2,100/month design.

---

## 2. Main project goal and supporting document references

**Documented goal** [DOC, VERIFIED against `COMPREHENSIVE_REQUIREMENTS_DOCUMENT.md` v1.0, 2025-10-09, §1]:

> "The Soccer Predictions Platform is a sophisticated web application that provides AI-powered soccer match predictions through a hybrid system combining machine learning algorithms with expert human analysis. The platform serves three distinct user profiles with varying levels of access and capabilities, ensuring prediction quality through a multi-layered validation process."

Primary goals as written: accurate data-driven predictions; ML baseline plus expert judgment; a scalable subscription-based revenue model; a trusted brand. In scope for Phase 1: multi-profile users (Regular/Expert/Admin), hybrid engine (ML → expert override → admin approval), external match-data APIs (API-Football primary, TheSportsDB fallback), subscription tiers (Free/Basic/Premium/Pro), audit trail, React + FastAPI, "Local development environment and AWS cloud deployment". Explicitly out of scope for Phase 1: mobile apps, live betting, social features, i18n, payment processing, chat.

**Intended final outcome** [DOC]: a production deployment on AWS (S3+CloudFront frontend, ECS Fargate backend, RDS PostgreSQL Multi-AZ, ElastiCache Redis, Route 53, ALB) per `AWS_PRODUCTION_DEPLOYMENT_PLAN.md` (2025-09-24) and `REQUIREMENTS_SUMMARY.md` (16-week roadmap ending in production deployment), with success metrics of 99.9% uptime, <500 ms API responses, 70%+ prediction accuracy, and 10k users in six months.

**Supporting documents (authoritative for intent):**
- `COMPREHENSIVE_REQUIREMENTS_DOCUMENT.md` — requirements v1.0 (untracked).
- `REQUIREMENTS_SUMMARY.md` — quick reference and roadmap (untracked; roadmap checkboxes stale).
- `USER_ROLES_AND_PERMISSIONS_MATRIX.md` — RBAC and tier matrix (untracked).
- `LOCAL_DEVELOPMENT_ARCHITECTURE_PLAN.md` — local architecture (tracked, 2025-09-24).
- `AWS_PRODUCTION_DEPLOYMENT_PLAN.md` — target cloud architecture (tracked, 2025-09-24; plan only, never executed).
- Concept origin: `🎯 Backend Integration Task List.txt` (2025-09-24, Node/Express plan superseded the same night by the FastAPI plan).

I did not find any document that replaces or narrows this goal; the goal statement is taken as-is.

---

## 3. Documentation inventory and authoritative files

**Counts** [CODE, VERIFIED]: 107 Markdown files (46,018 lines) plus 2 root `.txt` files. Root level: 52 `.md` + 2 `.txt`, of which only 3 `.md` are git-tracked. Sub-directories: 55 files (`api/` 5, `backend/` 3 + `backend/docs/` 10 + `backend/alembic/README`, `docker/` 10, `docs/` 8 + `docs/database/` 16, `frontend/` 3); all tracked except the five newest (`docs/BTTS_TOTAL_GOALS_*` ×4 and `docs/EXPERT_PREDICTION_FORM_GUIDE.md`, mtime 2025-10-16).

**Quality caveats** [DOC, VERIFIED by the inventory]: most root docs are per-session status notes; ten docs dated 2025-10-03 carry a wrong "2025-01-03 / January 2025" stamp; `api/IMPLEMENTATION_SUMMARY.md` says "2024-01-08". File mtimes and git dates are the reliable timeline. Four mutually inconsistent database table inventories exist across `docs/database/*`, `docker/postgres/README.md`, and `backend/docs/DATABASE_MODELS_IMPLEMENTATION.md`; **only the implemented models and migrations are ground truth**.

**Authoritative for current state (use these first):**

| File | Why |
|---|---|
| `backend/docs/KAN-26_IMPLEMENTATION_SUMMARY.md` (2025-10-13) | Latest backend feature status (expert API, aggregator, priority migration). |
| `docs/BTTS_TOTAL_GOALS_DISPLAY_FIX_SUMMARY.md` + `docs/BTTS_TOTAL_GOALS_IMPLEMENTATION.md` (2025-10-16, untracked) | Describe the uncommitted working-tree changes. |
| `EXPERT_MATCH_SELECTION_IMPROVEMENTS.md` (2025-10-13, untracked) | Last frontend feature snapshot ("4 of 5 done"). |
| `FINAL_API_CONFIGURATION.md` (2025-10-07, untracked) | Operative external-API decision: API-Football direct via `x-apisports-key`, Vite dev proxy, production proxy deferred. |
| `DEPLOYMENT_SUMMARY.md` (2025-10-07, untracked) | The only AWS deployment record (S3 static site). |
| `backend/docs/DATABASE_MODELS_IMPLEMENTATION.md`, `backend/docs/JWT_AUTHENTICATION_IMPLEMENTATION.md`, `docs/ROLE_BASED_PERMISSIONS.md`, `docs/REDIS_CACHING_LAYER.md`, `backend/EMAIL_SERVICE_IMPLEMENTATION_SUMMARY.md`, `frontend/docs/FRONTEND_AUTHENTICATION_GUIDE.md` | Subsystem designs as implemented (Oct 8–11). |
| `docker/README.md`, `docker/DATA_PERSISTENCE_*.md`, `docker/TROUBLESHOOTING.md`, `docker/redis/README.md` | Local infra runbooks (Adminer port is 8081 in compose; several docs still say 8080). |
| `KAN-28_IMPLEMENTATION_SUMMARY.md`, `FORGOT_PASSWORD_IMPLEMENTATION_SUMMARY.md`, `JIRA_UPDATE_SUMMARY.md`, `READY_FOR_TESTING.md`, `TEST_SESSION_PERSISTENCE.md`, `EXPERT_DASHBOARD_FIXES_SUMMARY.md` | Narrow but current status notes. |

**Latest decision on paper but NOT IMPLEMENTED:** `backend/docs/KAN-26_BRIEF_SUMMARY.md` and `KAN-26_STORAGE_AND_TRACKING_RECOMMENDATIONS.md` (v2.0, "store only Expert and LLM predictions, cache API-Football in Redis") — the implementation followed the v1.0 "store all" schema; the v2.0 checklist has 9 unchecked items.

**Superseded / historical (do not act on):** all 2025-10-02/03 API-Football-free-tier docs; all TheSportsDB docs and `v2apt.txt`; Sportradar/StatPal/alternative-API research; RapidAPI-era `CORS_FIX_SUMMARY.md` and `API_AUTHENTICATION_VERIFICATION.md`; `api/*.md` (pre-auth scaffold era); `backend/README.md`; `frontend/README.md` and `frontend/test-checklist.md` (mock-data era; claim a passing build that no longer passes); `docs/database/*` ER diagrams and summaries (design drafts); `KAN-26_EXECUTIVE_SUMMARY.md`, `KAN-26_MULTI_SOURCE_..._ANALYSIS.md`, `KAN-26_STORAGE_STRATEGY_ANALYSIS.md` (design references); `FRONTEND_ARCHITECTURE_ANALYSIS.md` (tracked; accurate for the data layer but calls the app "production-ready" and lists auth/backend as future).

**Secrets inside documentation** [DOC, VERIFIED by pattern search; values not reproduced]: API-Football key in `FRONTEND_ARCHITECTURE_ANALYSIS.md` (tracked, pushed) and in `API_AUTHENTICATION_VERIFICATION.md`, `API_FOOTBALL_MIGRATION_SUMMARY.md`, `API_INTEGRATION_GUIDE.md`, `API_INTEGRATION_SUMMARY.md`, `CORS_FIX_SUMMARY.md`, `FINAL_API_CONFIGURATION.md`; TheSportsDB premium key in four `THESPORTSDB_*.md`; Sportradar and StatPal trial keys in `SPORTRADAR_TEST_GUIDE.md` / `STATPAL_TEST_SUMMARY.md`; test-user e-mails and passwords in `EXPERT_USER_TESTING_SUMMARY.md`, `EXPERT_DASHBOARD_FIXES_SUMMARY.md`, `SESSION_PERSISTENCE_FIX.md`, `TEST_SESSION_PERSISTENCE.md`; personal e-mail addresses in several email/expert docs; default DB password in eleven tracked docker/api docs.

---

## 4. Current application architecture

**As implemented** [CODE, VERIFIED]:

```
Browser (React SPA, Vite build, base './')
 ├─ calls API-Football v3 DIRECTLY (browser → https://v3.football.api-sports.io, key embedded)
 │    dev: Vite proxy /api/football injects the key; prod: direct call from the bundle
 ├─ calls backend at VITE_API_BASE_URL (default http://localhost:8000) under /api/v1/*
 │    auth, users, subscriptions (mock), expert/*, predictions/published*
 └─ mock data for MatchDetailPage and DashboardPage

FastAPI (backend/app, uvicorn :8000)
 ├─ middleware: CORS (localhost origins), TrustedHost (prod only), GZip, security headers
 ├─ routers under /api/v1: health, auth, predictions (public), users, expert, admin, subscriptions
 │    (matches/leagues/teams routers commented out — no backend fixtures API)
 ├─ services: expert_prediction, prediction_audit, prediction_cache, cache, session_cache (orphan),
 │    prediction_aggregator (orphan), subscription_tier (orphan), email_service (SMTP), api_football (fixture lookup)
 ├─ PostgreSQL 15 via SQLAlchemy 2 (sync) — schemas users/predictions/ml_models/analytics/audit, 66 tables
 └─ Redis 7 (sync redis-py) — DB0 sessions/refresh tokens/blacklist, DB1 predictions cache, DB2-5 allocated

Local infra: docker/docker-compose.yml → postgres:15-alpine, redis:7-alpine, adminer (8081); backend service commented out
```

**Divergences from the documented architecture** [INFERENCE from CODE vs DOC]:
- The documented "hybrid ML baseline → expert override → admin approval" pipeline exists only as data-model and enum scaffolding. There is no ML engine (ML baseline endpoint returns hard-coded numbers), experts approve their own predictions, and admin approval is a no-op stub.
- The documented "backend proxies external APIs, caches in Redis" flow is not built; the browser talks to API-Football directly.
- The documented microservice split (public/expert/admin/ML worker on ECS) is not built; the backend is one monolith and has never been containerised beyond a Dockerfile that has never been run in the cloud.
- Subscriptions are derived from `user_type`, not from the `user_subscriptions` table; no payments.

---

## 5. Technology stack

| Layer | Declared | Actually installed / used | Notes |
|---|---|---|---|
| Frontend | React ^18.2, TypeScript ^5.2, Vite ^4.5, Tailwind ^3.3, react-router-dom ^6.8, axios ^1.6, react-query ^3.39, framer-motion, heroicons, headlessui, react-hot-toast, react-helmet-async, recharts, date-fns | react 18.3.1, TS 5.9.2, vite 4.5.14, router 6.30.1, axios 1.12.2 (node_modules installed 2025-10-02) | `recharts`, `react-intersection-observer` unused; react-query only provides a provider (no `useQuery`). No test framework. [CODE, VERIFIED] |
| Backend | Python ^3.11, FastAPI 0.104.1, uvicorn 0.24, pydantic 2.5, SQLAlchemy 2.0.23, alembic 1.12.1, psycopg2-binary, redis 5.0.1, python-jose, passlib/bcrypt, httpx, jinja2, aiosmtplib | venv is **Python 3.9.6** with the pinned packages | `requirements.txt` and `pyproject.toml` drift (jinja2/aiosmtplib missing from pyproject; `requests` used by root scripts but declared nowhere). [CODE, VERIFIED] |
| Data | PostgreSQL 15 (5 schemas, 66 tables, 3 Alembic migrations), Redis 7 (16 DBs, 6 allocated) | docker-compose images postgres:15-alpine, redis:7-alpine, adminer | No containers/volumes/images present on this machine now. [CODE/VERIFIED] |
| External data | API-Football v3 Pro (primary), TheSportsDB (dead code fallback) | API-Football called from browser; backend uses it only to look up a fixture when an expert creates a prediction | [CODE, VERIFIED] |
| Email | SMTP via aiosmtplib (Mailtrap Live configured locally), SendGrid/SES stubs | | [CODE, VERIFIED] |
| Tooling | Trunk (`.trunk/trunk.yaml`: markdownlint, prettier, checkov, trufflehog, git-diff-check), ESLint 8, black/flake8/mypy/isort declared | ESLint config broken; no CI | [CODE, VERIFIED] |
| Toolchain on this Mac | Node 24.8.0, npm 11.6.0, Python 3.13.12 (system), Docker 29.0.1, no `psql` | | [VERIFIED] |

---

## 6. Features already implemented

Each item is **VERIFIED** by reading code and, where noted, by executing something safe.

**Backend (54 API routes + docs; app imports cleanly and registers 58 routes)** [CODE, VERIFIED by importing `app.main` with the project venv]:
- Auth: register, login, refresh (rotation + jti blacklist), logout, `/me`, change password, forgot/verify/reset password with hashed one-time tokens and e-mails (`backend/app/api/v1/endpoints/auth.py`).
- Users: get/update profile, change password, preferences, permission listing; admin list/role change/soft-delete.
- Expert manual-prediction lifecycle: create (auto-creates Match/Team/League from API-Football or placeholders), review queue, my-predictions, approve → published, reject, edit pending, soft delete, toggle publish/archive (the last is uncommitted).
- Public read API: `GET /api/v1/predictions/published` and `/published/by-match/{external_match_id}` with priority ordering.
- Admin basics: dashboard counts, pending experts, verify/reject expert, suspended users list/suspend.
- Static RBAC (27 permissions, 3 roles, verified-expert gate) and dependency chain.
- Data layer: 66 SQLAlchemy models across 5 schemas; Alembic chain `9b3c8646a52d → 2a4f8c9d1e3b → eb2ef2cf6caf` is linear with one head (the last revision is untracked).
- Redis cache services, health endpoints (basic/detailed/database/redis), JSON logging, security headers, CORS, gzip, multi-stage Dockerfile.
- SMTP e-mail with a working welcome template; password-reset templates fall back to inline bodies (see §18).
- Unit tests: 93 pure-unit tests pass (run during this assessment, see §17).

**Frontend** [CODE, VERIFIED]:
- Routing for 23 pages; auth context with localStorage tokens, 401 auto-refresh, role-based `ProtectedRoute`; login/register/forgot/reset/change-password pages.
- Profile and subscription pages wired to the backend.
- Expert pages: dashboard (metrics, recent predictions, publish/unpublish/delete), match selection (API-Football fixtures, search, manual id), create prediction (1X2 + optional BTTS/Over-Under, uncommitted), my-predictions (filter, paging, inline edit, delete), review queue (approve/reject, paging).
- Public pages: Home, Today, Tomorrow, Leagues, League detail (standings/teams/fixtures), Team detail (partial), header search (API-Football).
- Three-tier API-Football service layer with 5-minute in-memory cache and expert-prediction merging; source badges; live status/score utilities (uncommitted).
- Design system (Tailwind dark theme), Helmet titles on most public pages.

**Infrastructure / ops** [CODE, VERIFIED]:
- Docker Compose for Postgres/Redis/Adminer with tuned configs, init SQL (schemas, extensions), backup/restore scripts, a baseline schema-only dump.
- Frontend deployed once to S3 (`soccer-predictions-app-7787`) on 2025-10-07/08 [AWS, VERIFIED]; the object set is byte-identical to the local `frontend/dist`.

---

## 7. Features partially implemented

| Feature | State | Evidence |
|---|---|---|
| BTTS / Total Goals markets (uncommitted, 2025-10-16) | Model ↔ migration ↔ schemas ↔ service ↔ expert endpoints consistent; **missing** from public endpoints' hand-built dicts, aggregator, and audit; no sum validation on the update path or on over/under pairs; `toggle-publish` audit calls a non-existent `log_action`; 3 new TS errors; no tests | `backend/app/api/v1/endpoints/predictions.py:129-149,202-222`; `backend/app/api/v1/endpoints/expert.py:541`; `git diff` |
| Expert override | Endpoint + schema + audit exist, but the service constructs `PredictionOverride` with kwargs that are not columns → always HTTP 400 | `backend/app/services/expert_prediction.py:200-207` vs `backend/app/models/predictions.py:149-185` [VERIFIED] |
| Expert analytics | Counts and average confidence only; `accuracy_rate=None`, league breakdown `{}`, trend `[]` | `expert.py:568-640` |
| Admin | Dashboard counts real; audit-logs, system-config, approve-prediction are stubs; expert reject does not persist reason | `admin.py:204-254` |
| Audit trail | Rows written to `audit.audit_log`, but `metadata=` kwarg never reaches the `audit_metadata` column; no read endpoint | `prediction_audit.py:322-340` vs `models/audit.py:106` [VERIFIED] |
| Session revocation | `revoke_user_refresh_tokens` deletes stored keys but `/refresh` only checks the blacklist → revocation on password change/reset is ineffective | `backend/app/core/deps.py:233-243,280-298` [VERIFIED] |
| External data on the backend | `api_football.py` used only for fixture lookup; aggregator's API-Football branch is a TODO; matches/leagues/teams routers commented out | `backend/app/api/v1/api.py:25-28` |
| Public prediction display | Real API-Football predictions for the first 5 fixtures per page; every other fixture, all odds, H2H and team stats are randomized or zero placeholders shown without indication; BTTS/O-U defaults fabricated when no expert data | `frontend/src/services/api-mapper.service.ts:133-274,332-352` |
| Match detail page | Mock-only; shows "Match Not Found" for every real fixture | `frontend/src/pages/MatchDetailPage.tsx:1-26` [VERIFIED] |
| User dashboard | Fully mock ("John Doe") | `frontend/src/pages/DashboardPage.tsx` |
| Subscriptions | Static tier catalogue; tier derived from `user_type`; `PUT /subscriptions/me` persists nothing; three conflicting tier tables in code | `subscriptions.py:19-100,103-208`; `subscription_tier.py`; `prediction_aggregator.py:53-74` |
| Email | SMTP works; password-reset templates requested with a wrong relative path → inline fallback always used; SendGrid/SES stubs return False | `email_service.py:32-40,348-352,410-414` [VERIFIED] |
| Test suite | 121 test functions; 93 pure-unit pass; 17 need live Redis; 3 need live Postgres; 8 endpoint tests cannot pass as written (patched symbols already bound; wrong `get_db` overridden) | §17 |
| Local Docker environment | Compose validates, but relative bind-mounts resolve to `docker/docker/...` (empty; `redis.conf` created as a directory on 2025-10-08) and the backend service is commented out | `docker compose config` [VERIFIED] |
| Frontend tooling | strict TS + ESLint configured, but `tsc` fails (10 errors) and ESLint aborts on `extends: "@typescript-eslint/recommended"` (missing `plugin:` prefix) | `frontend/.eslintrc.cjs:6` [VERIFIED] |
| Hosting readiness | `base: './'` in `vite.config.ts` makes deep links load `./assets/...` relative to the route → blank page on any non-root URL on S3; S3 returns 404 status for SPA routes; HTTP only | Probed `/league/assets/index-48183f90.js` → HTML 404 [VERIFIED] |

---

## 8. Features not implemented

All **NOT IMPLEMENTED** [CODE vs DOC]:
- ML baseline engine and any model training/inference (`/expert/ml-baseline` returns constants; ML tables unused).
- Prediction settlement, results ingestion, accuracy computation, expert performance tracking (`prediction_results`, analytics tables never written).
- Admin approval workflow as specified (high-stakes flag, admin approve/reject with notes, notifications).
- Backend fixtures/leagues/teams API and Redis-cached API-Football proxy (FR-DATA-001/002).
- Rate limiting, email verification enforcement, MFA, OAuth, "remember me".
- Payments/Stripe, subscription persistence, tier enforcement middleware (KAN-139).
- LLM prediction source (enum value only), multi-source comparison view (Pro tier).
- Notifications, audit read API, GDPR export, data retention jobs, KAN-26 v2.0 storage strategy and `prediction_source_views` tracking.
- Admin UI in the frontend (admins land on the mock dashboard); generic predictions API used by the dead `prediction.service.ts` (`/predictions/today`, `/{id}`, `/{id}/feedback` do not exist in the backend) [VERIFIED].
- CI/CD (no `.github/` directory, no workflows on GitHub), IaC (no Terraform/CDK/CloudFormation), `.dockerignore`, backend container deployment, CloudFront/TLS/domain, monitoring, alarms, secrets management in AWS.
- Automated frontend tests of any kind; backend integration tests that actually run.
- PWA/service worker (claimed by the old `main` README), SEO assets (missing favicon/OG image, placeholder domain).

---

## 9. Local repository status

[CODE/GIT, VERIFIED on 2026-09-17]

| Item | Value |
|---|---|
| Path | `/Users/stephanefotso/Documents/DevProjects/PredictionsAppsUI` |
| Current branch | `progress` |
| HEAD | `918eabd49474ee01fde3b9bb8beef32d0b4fc77d` — "Fix league search navigation bug…" (2025-10-14 21:29 -0400, author "Stephan Money") |
| Local branches | `main` fdd40cb (2025-09-22) · `dev` b32cd9e (2025-09-22, local only, differs from `origin/dev`) · `progress` 918eabd · `progress-v1` 54cb0ad (2025-10-14) |
| Remote | `origin` = `https://github.com/fotso94/PredictionsAppsUI.git` |
| Remote-tracking refs | `origin/main` fdd40cb, `origin/dev` a5a283f, `origin/prod` 1b12b20, `origin/progress` 918eabd, `origin/progress-v1` 54cb0ad; `origin/HEAD → origin/main` |
| Tags / stash | none / none |
| Tracked files | 252 (on `progress`) |
| Root `.gitignore` | **absent** on `progress` (deleted relative to `main`); only `backend/.gitignore` and `frontend/.gitignore` exist, which is why 50+ root files show as untracked |
| Working tree | 16 modified tracked files (+1,183 / −106): 4 backend (`expert.py`, `models/predictions.py`, `schemas/predictions.py`, `services/expert_prediction.py`) and 12 frontend (expert pages, MatchCard, HomePage, TodayPredictionsPage, four services, `types/expert.ts`) |
| Untracked | 68 paths: 51 root `.md`, 2 `.txt`, `index.html`, `test.html`, `diagram.html`, `diagram2.html` (identical), `serve-test.py`, `.DS_Store`, `backend/alembic/versions/eb2ef2cf6caf_add_btts_and_total_goals_prediction_.py`, `frontend/src/utils/` (`matchFilters.ts`), `docs/BTTS_TOTAL_GOALS_*.md` ×4, `docs/EXPERT_PREDICTION_FORM_GUIDE.md`, 4 screenshots dated 2025-10-15 |
| Ignored build artefacts present | `frontend/dist` (2025-10-07 build), `frontend/node_modules`, `backend/venv` (Python 3.9.6), `backend/htmlcov` + `.coverage` + `.pytest_cache` (2025-10-13), `backend/.env`, `frontend/.env` |
| Reflog | shows cherry-picks between `progress` and `progress-v1` on Oct 9–14; no rebases or resets of `progress` itself |
| Commit history on `progress` | 18 commits from 2025-09-22 to 2025-10-14 (14 ahead of `main`, 0 behind) |

**Branch relationships** [VERIFIED]: `progress` is `main` + 14 commits. `progress-v1` diverges from `progress` at c65c86b and carries 3 cherry-picked equivalents (c772eae, 4a8ad97, 54cb0ad) of `progress` commits; `progress` is 70 files / +12,989 ahead of it. `origin/dev` is an **orphan** ("feat: Fresh start – copy all changes from progress branch", 2025-09-24) with 10,457 files of which 10,345 are committed `node_modules`; it is the only place holding the PowerShell AWS deployment scripts (`aws-deploy.sh`, `deploy-aws.ps1`, `setup-cloudfront.ps1`, `update-app.ps1`, `aws-setup-guide.md`, `deployment-info.txt`). `origin/prod` is a single README-only commit. `main` (the GitHub default branch) is the original Create-React-App prototype layout (`src/`, `public/`, root `package.json` with react-scripts) and does not contain `backend/`, `frontend/`, or `docker/` at all.

---

## 10. GitHub repository status

[GITHUB, VERIFIED via `gh` API on 2026-09-17; authenticated as `fotso94` with repo/workflow scopes]

| Item | Value |
|---|---|
| Repository | `fotso94/PredictionsAppsUI`, **public**, created 2025-09-22, description "UI for a predictions's website that predict the outcome of soccer games." |
| Default branch | `main` (fdd40cb, 2025-09-22) — the obsolete CRA prototype |
| Last push | 2025-10-15T01:29:48Z (progress branch) |
| Branches | `dev` a5a283f · `main` fdd40cb · `prod` 1b12b20 · `progress` 918eabd · `progress-v1` 54cb0ad; none protected |
| Compare `main...progress` | ahead 14, behind 0 |
| Pull requests | 0 (open or closed) |
| Issues | 0 |
| Releases / tags | 0 / 0 |
| Actions workflows / runs | 0 / 0 |
| Environments / deployments | 0 / 0 |
| GitHub Pages | not configured |
| Secret scanning alerts | empty list (cannot distinguish "none" from "feature not enabled" with current scopes) — NOT VALIDATED |
| Dependabot / code scanning | disabled / no analysis |
| Size / languages (default branch) | 41,871 KB; TypeScript 100,498, JavaScript 9,115, HTML 6,643, CSS 1,611 (this reflects `main`, not the real app) |
| Wiki / license | wiki enabled (unused); no license file |

**Documentation available only on GitHub**: `origin/dev` holds `aws-setup-guide.md` and `deployment-info.txt` (records bucket `soccer-predictions-app-7787`, us-east-1, deployed 2025-09-22 23:07 from a Windows machine). `origin/prod` README is a two-line placeholder. Nothing else exists on GitHub that is not local.

---

## 11. Local-versus-GitHub comparison

- **Heads match for every branch that exists on both sides** (`progress`, `progress-v1`, `main`): `git ls-remote` SHAs equal local SHAs. There is **no unpushed committed work**. [VERIFIED]
- **Local `dev` (b32cd9e) ≠ `origin/dev` (a5a283f)**; they share no history with each other beyond the root. The local `dev` is a stale September branch; the remote one is the orphan deployment-scripts branch. [VERIFIED]
- **`origin/prod` has no local branch.** [VERIFIED]
- **Unpushed, uncommitted work exists only locally**: the 16 modified files and 68 untracked paths (§9), including the BTTS migration and the newest docs. If this machine were lost, the BTTS/Total-Goals feature and 51 root documents would be lost. [VERIFIED]
- **GitHub visitors see the wrong project**: the default branch `main` shows a CRA prototype README claiming "89.9% accuracy" and PWA support; the real application is on `progress`. [VERIFIED, CONTRADICTED claim in `main` README]
- **Files on GitHub not present locally**: everything under `origin/dev` (deployment scripts, committed `node_modules`) and `origin/prod`. [VERIFIED]
- **Secrets are on GitHub**: `frontend/vite.config.ts`, `frontend/src/services/api-football.service.ts`, `frontend/src/services/thesportsdb.service.ts`, `FRONTEND_ARCHITECTURE_ANALYSIS.md`, `backend/create_expert_user.py`, `backend/update_expert_password.py`, `backend/test_smtp_connection.py`, `backend/alembic.ini`, `frontend/test-login.html` are all tracked on `progress`/`progress-v1` and public. [VERIFIED]

---

## 12. Branch, commit, tag, PR, issue, release, and Actions status

**Commit timeline on `progress`** [GIT, VERIFIED]:

| Date | Commit | Subject |
|---|---|---|
| 2025-09-22 | 553770c, 1b12b20, c7d38df, fdd40cb | Initial README, prod branch, CRA prototype, README merge (`main`) |
| 2025-09-22 | 915bdeb, 11baa49 | Vite frontend app, server/testing tools |
| 2025-09-24 | c65c86b, cc95ca8, 28f7105 | Logo fix; local + AWS architecture plans; frontend architecture analysis |
| 2025-10-08 | e07b2b2, b4857e2, 53e16c8 | API-Football integration + **key committed**; docs; DB migration system + Docker + backup infra (KAN-16..21, KAN-30) |
| 2025-10-09 | 9cfc8de | KAN-28 Redis caching, JWT auth (KAN-23/107-111), RBAC (KAN-24), frontend auth |
| 2025-10-10 | e52e152, 26c64c5 | KAN-25 public API, subscriptions, profile pages; session persistence |
| 2025-10-11 | 736ab2d | KAN-144 forgot/reset password |
| 2025-10-14 | d221f6f | KAN-26 expert API + multi-source priority (commit body claims "14/17 tasks, 82%") |
| 2025-10-14 | 918eabd | League search navigation fix + search dropdown + screenshots |

Claims in commit messages checked: d221f6f says routes `/expert/create-prediction`, `/expert/review-queue`, `/admin/approve-predictions` were created — the actual routes are `/expert/predictions/create`, `/expert/predictions/review-queue`, and **no admin route exists** [CONTRADICTED by `frontend/src/App.tsx`]. It claims "96% coverage, 35/35 tests" for the aggregator/permissions unit tests — consistent with the 2025-10-13 coverage report (aggregator 96%) [PARTIALLY VERIFIED].

**Tags:** none. **Releases:** none. **PRs:** none (all work pushed directly to branches). **Issues:** none (tracking happened in Jira `aztechsolutions.atlassian.net`, keys KAN-15…KAN-161 referenced in docs; Jira access NOT VALIDATED). **Actions:** no workflows ever existed; the `.github/` directory is absent. **Branch protection:** none.

---

## 13. AWS account, regions, and project-resource inventory

[AWS, VERIFIED via `aws --profile me` on 2026-09-17; read-only calls only]

| Item | Value |
|---|---|
| Account | `845667439863` (no account alias) |
| Caller identity | IAM user `superadmin` (`arn:aws:iam::845667439863:user/superadmin`) — attached `AdministratorAccess`, `Billing`, `AWSBillingConductorFullAccess`; **two active long-lived access keys** (created 2025-09-23 and 2025-10-08, matching the two deployment dates) |
| Profile `me` region | **not configured** (`aws configure get region --profile me` returns nothing); every command needs `--region`. Other profiles in `~/.aws/config` default to us-east-1 |
| Enabled regions scanned | all 17 default regions (us-east-1/2, us-west-1/2, ca-central-1, eu-west-1/2/3, eu-central-1, eu-north-1, ap-south-1, ap-northeast-1/2/3, ap-southeast-1/2, sa-east-1) plus global services |
| Services enumerated per region | CloudFormation, EC2 (instances/VPC/EIP/NAT/EBS/AMI/snapshots/SG/key pairs), ELB/ELBv2, ECS, ECR, Lambda, RDS (instances/clusters/snapshots), ElastiCache (+serverless), DynamoDB, API Gateway v1/v2, Amplify, App Runner, Elastic Beanstalk, Lightsail, ACM, Cognito, SES/SESv2, Secrets Manager, SSM Parameters, CloudWatch logs/alarms, EventBridge, SQS, SNS, CodePipeline/CodeBuild/CodeDeploy/CodeCommit, EFS, Step Functions, OpenSearch, Backup vaults, Resource Groups Tagging API; global: S3, CloudFront, Route 53 (zones + registrar), IAM (roles/users/policies/OIDC), Cost Explorer, Budgets, CloudTrail lookup |

**Project resources found (the complete list):**

| Resource | Details | Purpose | State |
|---|---|---|---|
| S3 bucket `soccer-predictions-app-7787` | us-east-1, created 2025-09-23T03:07:41Z; static website hosting (index/error = `index.html`); bucket policy `s3:GetObject` to `*`; Public Access Block all `false`; SSE-S3 (AES256); versioning off; no tags; 17 objects, last modified 2025-10-08T03:48Z (`index.html`, `assets/index-48183f90.js` 520,595 B, `.js.map` 2.1 MB, `.css`, 6 league SVGs, 7 team SVGs) | Frontend static site (first deployed 2025-09-22 from Windows; re-synced 2025-10-07/08) | **Live**: `http://soccer-predictions-app-7787.s3-website-us-east-1.amazonaws.com/` → HTTP 200, title "Soccer Predictions – Professional Football Analytics"; HTTPS times out (no CloudFront) |
| S3 bucket `predictions-app-778778324` | us-east-1, created 2025-10-08T00:27:22Z; same website/public config; 1 object `index.html` (7,317 B) byte-identical to the repo's root `index.html` ("API-Football Widget Test") | Throw-away widget test page | **Live**: HTTP 200 |

**Everything else in the account is unrelated to this project** [AWS, VERIFIED by name/tag/date]: `vprofile` CI/CD lab assets in us-east-1 (2 non-default VPCs `dev-vpc`/`prod-vpc`, 6 security groups, 3 key pairs, 8 AMIs, 9 EBS snapshots, tags "Java Home Cloud"), a `Vprofile-vpc` in us-east-2, the `zaynetechsolutions.com` website (S3 bucket, CloudFront `E3FVWV7K0JHWVZ`, Route 53 zone, ACM cert), `stephanefotso-portfolio` / `stephanefotso.zaynetechsolutions.com` buckets, `gha-static-website-237` / `gha-terraform-jhc-237` buckets (May 2026), IAM role `github-oidc` (created 2026-05-13, trusts `repo:fotso94/*` via the GitHub OIDC provider and carries **AdministratorAccess**), IAM user `aws_creds_user` (S3FullAccess), EKS service-linked roles (May 2026). No CloudFormation stacks anywhere. No CloudWatch log groups, alarms, Secrets Manager secrets, or SSM parameters for this project.

**Cost** [AWS Cost Explorer, VERIFIED]: account-wide spend is $1.5–2.5/month (Oct 2025 → Sep 2026), almost entirely "EC2 – Other" (EBS snapshots from the vprofile lab) and one Route 53 zone; S3 for this project is ≈$0.01/month; a one-off $11.20 in May 2026 came from EKS/ELB/VPC experiments. A cost budget "My Monthly Cost Budget" of $15 exists. CloudTrail shows no events on either project bucket in the last 90 days.

---

## 14. Current cloud deployment state

- **Frontend:** the S3 site is the Vite build of 2025-10-07 (assets hash `index-48183f90`), identical to local `frontend/dist`. It predates authentication (commit 9cfc8de, 2025-10-09), the public API integration, and all expert features: the deployed bundle contains **zero** `/api/v1/` references and no `localhost:8000`, but does contain one API-Football key and one `v3.football.api-sports.io` reference [VERIFIED by fetching the bundle]. Deep links fail (relative asset paths + 404 fallback) and there is no HTTPS.
- **Backend / database / cache:** **no deployment exists or is recorded**. No ECR repository, RDS or ElastiCache instance, or compute of any kind is attached to this project today, no document describes a backend deployment, and CloudTrail (90-day window) shows no related activity; an earlier, since-deleted deployment cannot be excluded. [AWS, VERIFIED for the current state]
- **DNS / TLS:** no hosted zone, certificate, or CloudFront distribution for this project. The `setup-cloudfront.ps1` script on `origin/dev` was never run (CloudFront list contains only the unrelated Zayne Tech distribution). [AWS, VERIFIED; doc claim "Consider CloudFront" → NOT IMPLEMENTED]
- **CI/CD-related resources:** the `github-oidc` role could be used by a future GitHub Actions workflow, but it currently grants AdministratorAccess to any repository under `fotso94/*` [AWS, VERIFIED] — over-privileged and not project-specific.
- **Deployment mechanism used so far:** manual `aws s3 sync` from a developer machine (PowerShell scripts on `origin/dev`; `DEPLOYMENT_SUMMARY.md`), using the `superadmin` long-lived keys. [DOC + AWS, PARTIALLY VERIFIED — the scripts and timestamps are consistent; the exact commands run are not logged]

---

## 15. Repository-to-AWS deployment mapping

| Repository artefact | AWS resource | Status |
|---|---|---|
| `frontend/dist` (built 2025-10-07 from commit ≈e07b2b2) | `s3://soccer-predictions-app-7787` | VERIFIED identical (index.html byte-equal; same asset hashes and sizes) |
| Root `index.html` (API-Football widget test) | `s3://predictions-app-778778324/index.html` | VERIFIED identical |
| `origin/dev:deployment-info.txt` (bucket name, region, date 2025-09-22) | bucket creation time 2025-09-23T03:07Z UTC | VERIFIED consistent |
| `DEPLOYMENT_SUMMARY.md` / `FRONTEND_ARCHITECTURE_ANALYSIS.md §8.4` ("17 files, 2.6 MiB, cache-control set") | 17 objects; total ≈2.7 MB | PARTIALLY VERIFIED (object count and size match; per-object Cache-Control headers not inspected) |
| `AWS_PRODUCTION_DEPLOYMENT_PLAN.md` (ECS Fargate, RDS, ElastiCache, ALB, Route 53, CloudFront, 5 named buckets, us-west-2 DR) | nothing | NOT IMPLEMENTED |
| `backend/Dockerfile` | no ECR repo, no ECS service | NOT IMPLEMENTED |
| `backend/app/core/config.py` AWS SES settings, `email_service.py` SES stub | no SES identities | NOT IMPLEMENTED |
| `docker/docker-compose.yml` | local only | n/a |
| `origin/dev:setup-cloudfront.ps1` | no distribution | NOT IMPLEMENTED |
| `.github/` workflows | none (repo) / `github-oidc` role (AWS, generic) | NOT IMPLEMENTED |

**Resources in AWS not represented in the repository:** `predictions-app-778778324` bucket (only implied by the root `index.html`), and the account-level `github-oidc` role/provider. **Resources referenced by code/docs but missing from AWS:** all of the production plan; the five planned bucket names; SES.

---

## 16. Local/GitHub/AWS consistency findings

1. **Source of truth is `progress` + the local working tree**, not the GitHub default branch. GitHub `main` is a different, obsolete codebase. [VERIFIED]
2. **Deployed frontend ≠ current frontend.** The S3 site is ~10 commits and all uncommitted work behind, and would not build today anyway. [VERIFIED]
3. **Docs claim "production-ready / live"** (`FRONTEND_ARCHITECTURE_ANALYSIS.md`, `ARCHITECTURE_UPDATE_SUMMARY.md`, `frontend/README.md`); reality: a static demo that fabricates most predictions, exposes a paid API key, has no backend, and cannot deep-link. [CONTRADICTED]
4. **Docs claim the local DB "migration applied successfully"** for BTTS (2025-10-16); no Postgres container, volume, or image exists on this machine now, so the local database state described in the docs is gone or lives elsewhere. [NOT VALIDATED]
5. **Docker Compose was run on this machine on 2025-10-08** (Docker auto-created `docker/docker/postgres/{init,conf}` and a `docker/docker/redis/redis.conf` directory), which means Redis started **without** the project's `redis.conf` and Postgres **without** the init SQL during those runs (schemas were still created by `alembic/env.py`). [VERIFIED by directory timestamps + `docker compose config`]
6. **Profile `me` has no region**, yet every doc/script assumes `us-east-1`. [VERIFIED]
7. **Two S3 buckets are publicly readable with Public Access Block disabled**; one of them serves the leaked key to anyone. [VERIFIED]
8. **The `superadmin` user with admin+billing rights and two long-lived keys is the deployment identity.** No project-scoped IAM role exists. [VERIFIED]
9. **Jira is the real backlog** (≈80 KAN keys referenced), but no GitHub issues/PRs exist and Jira state could not be read. [NOT VALIDATED]
10. **`origin/dev` carries 10,345 committed `node_modules` files** (41 MB repo), which will keep bloating clones until the branch is deleted or rewritten. [VERIFIED]

---

## 17. Test and build status with evidence

**Backend — executed during this assessment** (safe subset: no DB/Redis, no cache/coverage/bytecode written; verified `git status` unchanged afterwards):

```
venv/bin/python -m pytest -p no:cacheprovider -o addopts="" -q \
  tests/test_auth.py tests/test_permissions.py tests/core/test_expert_permissions.py \
  tests/services/test_prediction_aggregator.py tests/test_email_service.py
→ 93 passed in 1.62s
```
[VERIFIED]

**Backend — not executed (require live services):** `tests/test_cache_services.py` (17 tests, real Redis), `tests/test_health.py` (3 tests, real Postgres via app startup), `tests/api/test_expert_endpoints.py` (8 tests; cannot pass as written because `@patch` targets dependencies FastAPI already bound, and `conftest.py` overrides `app.db.session.get_db` while `auth/users/expert/admin` import `get_db` from `app.core.deps`) [VERIFIED by reading `tests/conftest.py:13,55` and endpoint imports]. Total test functions: 121.

**Last recorded run** [VERIFIED from artefacts]: `.pytest_cache/v/cache/nodeids` (2025-10-13) lists 110 tests from 6 files (health and endpoint tests were not collected); `htmlcov/index.html` "created at 2025-10-13 01:18 -0400", **TOTAL 64%** (models ≈100%, request handlers 21–36%). This predates commit d221f6f and the BTTS work, so it is stale.

**Backend — static checks** [VERIFIED]: all 72 `.py` files parse (AST check); `import app.main` succeeds under the 3.9.6 venv and registers 58 routes; one Pydantic warning (`convert_decimal_to_float` overrides an existing validator — the second definition is dead code, introduced by the uncommitted schema changes).

**Frontend** [VERIFIED by running the tools; nothing written]:
- `tsc --noEmit`: **10 errors** (`Header.tsx:6`, `MatchCard.tsx:9`*, `ExpertCreatePredictionPage.tsx:12`, `ExpertMatchSelectionPage.tsx:12`* and `:75`*, `ExpertMyPredictionsPage.tsx:9`, `LeagueDetailPage.tsx:36` string/number comparison, `ProfilePage.tsx:9`, `expert-prediction.service.ts:12`, `search.service.ts:42` wrong argument type). `*` = introduced by uncommitted changes; the other 7 exist at HEAD, so **the last commit does not build either**. `npm run build` (= `tsc && vite build`) therefore fails.
- `eslint`: aborts with "couldn't find the config `@typescript-eslint/recommended`" (`.eslintrc.cjs:6` needs `plugin:@typescript-eslint/recommended`). With the config corrected, a subagent run reported 9 errors / 53 warnings.
- No frontend unit or E2E tests exist; `frontend/test-checklist.md`'s "[x] build passes" is CONTRADICTED.

**Build artefacts:** `frontend/dist` (2025-10-07) is the only successful build evidence and matches the S3 deployment. `serve.js` cannot run (CommonJS `require` under `"type": "module"`) [VERIFIED by inspection].

**Docker:** `docker compose -f docker/docker-compose.yml config --quiet` validates (warns that `version` is obsolete) but resolves bind mounts to `docker/docker/...` [VERIFIED].

---

## 18. Issues, bugs, inconsistencies, and technical debt

### P0 — security and hard failures (all VERIFIED)
1. **Leaked secrets in a public repo and live site:** API-Football key (`frontend/vite.config.ts:31`, `frontend/src/services/api-football.service.ts:16`, `FRONTEND_ARCHITECTURE_ANALYSIS.md`, `frontend/dist`, S3); TheSportsDB premium key (`frontend/src/services/thesportsdb.service.ts:15-16`, `backend/app/core/config.py:146` default, `backend/.env.example`); SMTP password (`backend/test_smtp_connection.py:17`); expert test password (`backend/create_expert_user.py:152`, `backend/update_expert_password.py:48`); dev DB URL with password (`backend/alembic.ini:61`); test credentials (`frontend/test-login.html:22-23`). All present in git history since 2025-10-08/14.
2. **Privilege escalation:** `POST /api/v1/auth/register` accepts `role` ∈ {regular, expert, admin} from the client (`backend/app/api/v1/endpoints/auth.py:268-288`).
3. **Session revocation is a no-op** (`backend/app/core/deps.py:233-243, 280-298`).
4. **Per-process random `SECRET_KEY` default** (`config.py:26`) + `--workers 4` in the production Dockerfile → cross-worker token failures unless the env var is set.
5. **Expert override endpoint always fails** (`expert_prediction.py:200-207` passes non-existent columns to `PredictionOverride`).
6. **Audit metadata silently dropped** (`prediction_audit.py:332` uses `metadata=`; column is `audit_metadata`); `toggle-publish` calls non-existent `audit_service.log_action` (`expert.py:541`), swallowed.
7. **Placeholder-match replacement hard-deletes attached predictions** via `cascade="all, delete-orphan"` (`expert_prediction.py:995`; `models/predictions.py:402`) [PARTIALLY VERIFIED — read by the audit subagent, not re-executed].
8. **Public S3 buckets with Public Access Block disabled**; site serves the key; no TLS.

### P1 — functional bugs (VERIFIED unless noted)
9. Public `GET /predictions/published?date=` crashes (`db.func.date`, `predictions.py:91`).
10. `status` query param shadows `fastapi.status` → 500 on invalid filter (`expert.py:253,281`).
11. Password-reset e-mail templates never render (wrong relative path, `email_service.py:348-352,410-414`); fallback bodies used.
12. BTTS/Total-Goals fields omitted from public endpoints (`predictions.py:129-149,202-222`), aggregator, audit; no validation on update path or over/under pairs → DB CHECK violations surface as HTTP 500.
13. Frontend: `getPredictionSourceInfo` upper-cases the source while the lookup keys are lowercase → every badge shows "Randomized" (`frontend/src/types/expert.ts:236-300`); `MatchDetailPage` mock-only; dead links to `/expert/predictions/:id`; `search.service.ts:42` compile error; `TeamDetailPage` hardcodes Premier League 2024; queued requests retried with stale tokens (`api-client.ts:114-125`); `PasswordChangePage` navigates to login without clearing tokens; UTC/local date mixing; `prediction.service.ts` targets five endpoints that do not exist and is imported nowhere.
14. `key_factors` never returned (`expert_prediction.py:114,187,496` vs `679`); experts approve their own predictions; admin approve is a stub; API-registered experts never get an `ExpertProfile` so they can never be verified; O(n) bcrypt scan for reset tokens; registration sets `ACTIVE` with no email verification.
15. Backup script writes `pg_dump` stderr into the SQL file (`docker/scripts/backup-database.sh`, `2>&1` into the dump): the committed baseline dump contains 1,113 `pg_dump:` lines interleaved with SQL, so `restore-database.sh` will emit errors on every such line. [VERIFIED]
16. Docker Compose bind-mount paths (§16 item 5); backend service commented out; Adminer port documented as 8080 in several docs but mapped to 8081.
17. Test harness defects (§17).

### P2 — technical debt
- Three parallel external-data layers in the frontend (API-Football active; TheSportsDB ≈1,005 dead lines; mock data), three `generateMockOdds` copies, near-duplicate Today/Tomorrow pages, 135 `console.*` calls, unused deps, `base: './'`.
- Backend duplicates: two `get_db`; `session_cache.py` vs `deps.py` token stores with different key prefixes; three conflicting subscription-tier tables (BASIC missing in one); three priority tables (aggregator, model docstring, migration backfill) that disagree; static RBAC vs unused DB RBAC tables; unused tables (`prediction_audit`, `password_reset_tokens`, `user_sessions`, all ML/analytics tables); Docker-init enum types differ from SQLAlchemy enums; enum types physically created in schema `users` due to `search_path`.
- Sync SQLAlchemy/redis/httpx inside `async def` handlers; N+1 enrichment loops; `KEYS` scans; per-call Redis clients for non-default DBs; cache invalidation is a log statement; deprecated `@app.on_event`, pydantic v1 validators, `datetime.utcnow()`.
- Python 3.9 venv vs 3.11 requirement; `requirements.txt` vs `pyproject.toml` drift; no `.dockerignore`; no root `.gitignore`; credential-bearing helper scripts at `backend/` root; 50+ untracked status docs with keys inside; `origin/dev` with committed `node_modules`.
- Documentation drift: four incompatible table inventories; Swagger path `/api/docs` (KAN-26 docs) vs actual `/api/v1/docs`; register payload described three different ways; Redis key patterns documented three different ways; commit messages naming routes that do not exist.

---

## 19. Current blockers and dependencies

| Blocker | Type | Owner action needed |
|---|---|---|
| Leaked API-Football / TheSportsDB / SMTP / test credentials | Security | Rotate at the providers; decide on history rewrite vs. rotation-only (§25) |
| Frontend build broken (10 TS errors, ESLint config) | Engineering | None; fixable in code |
| Uncommitted BTTS work incl. untracked migration | Process | Decide whether to commit as-is (with fixes) or split; needs a working Postgres to test `alembic upgrade` |
| No reproducible local environment (compose paths, backend service, Python 3.11, test DB) | Engineering | None; fixable in code/config |
| No CI | Engineering | Enable GitHub Actions; optionally scope the `github-oidc` role |
| API-Football subscription status / quota (Pro plan claimed) | External | Owner confirms plan and provides a fresh key via env/Secrets Manager |
| Email provider for non-local use (Mailtrap Live currently) | External | Owner chooses SES/SendGrid/Mailtrap and provides credentials |
| Jira backlog state (KAN-25 "In Progress", KAN-144 "In Review", KAN-26 82%) | Process | Owner grants read access or exports the board |
| AWS budget/target architecture (documented $1,050–2,100/month vs. lean) | Decision | §25 |
| Database owner decisions (KAN-26 storage v1 vs v2; admin approval enforcement) | Product | §25 |

---

## 20. What should not be redone

Keep and build on (all VERIFIED working or structurally sound):
- The **five-schema data model and Alembic chain** (66 tables, linear migrations). Do not regenerate; add migrations.
- **JWT auth core** (login/refresh rotation/logout/password reset) and the **static RBAC** module; fix the listed bugs rather than replacing.
- **Expert manual-prediction service and endpoints**, the **public published-predictions endpoints**, and the frontend expert pages (dashboard, match selection, create, my-predictions, review queue).
- **Frontend auth context, API client, protected routes, profile/subscription pages, design system**, and the three-tier API-Football service layer (move the key server-side; keep the mapping/caching code).
- **Docker Compose stack, Postgres/Redis configs, backup/restore scripts** (fix paths and the stderr redirect).
- **Email service** (SMTP + Jinja templates) — fix the template path, keep the design.
- **Unit tests** (93 passing) and the test layout; fix the fixtures rather than rewriting.
- **Requirements, RBAC matrix, and architecture plans** as the product baseline; only their status sections are stale.
- The **S3 bucket** `soccer-predictions-app-7787` can be reused for the frontend once fronted by CloudFront (rename optional).

Do **not** invest further in: the TheSportsDB layer, `prediction.service.ts`, `subscription_tier.py` and `session_cache.py` (orphaned duplicates), the `origin/dev` and `progress-v1` branches, the PowerShell deploy scripts, the root-level session-summary docs, or the documented four-service ECS microservice split (premature).

---

## 21. Remaining work in priority order

1. **Rotate and remove secrets** (API-Football, TheSportsDB, SMTP, test users); move all keys to env/Secrets Manager; scrub docs; add root `.gitignore`; decide on history rewrite.
2. **Restore a green baseline**: fix 10 TS errors and the ESLint config; fix `conftest.py` `get_db` override and endpoint-test patching; add a Python 3.11 venv; fix compose bind-mount paths and enable the backend service; create the test database; commit the BTTS migration together with the model changes.
3. **Fix P0 backend defects**: registration role escalation; refresh-token revocation; `SECRET_KEY` requirement in non-dev; override kwargs; audit metadata; `log_action`; cascade delete on placeholder replacement.
4. **CI**: GitHub Actions running `tsc`, ESLint, `vite build`, `pytest` (unit + integration with service containers), Trunk/trufflehog secret scan; make `progress` (or a new `develop`) the default branch and protect it.
5. **Close the external-data gap**: backend `matches/leagues/teams` proxy endpoints with Redis caching and the API-Football key server-side; switch the frontend to them; delete the dead TheSportsDB layer; stop showing randomized predictions as if real (label or hide).
6. **Finish the prediction workflow**: BTTS/O-U in public endpoints and aggregator; real `MatchDetailPage`; admin approval (or an explicit decision that experts self-publish); expert onboarding creates `ExpertProfile`; audit read endpoint; fix P1 bugs.
7. **Subscriptions**: persist tier in `user_subscriptions`, one tier table, enforcement middleware (payments still out of scope).
8. **Deploy an MVP on AWS** (lean footprint, §24): CloudFront + S3 (with `base: '/'`), one backend container service, RDS PostgreSQL, ElastiCache Redis, Secrets Manager, CloudWatch, IaC, OIDC deploy role scoped to this repo; domain + TLS.
9. **Post-MVP**: settlement/accuracy pipeline, ML baseline, LLM source, analytics, notifications, e-mail verification, rate limiting, payments.

---

## 22. Recommended next implementation steps

[RECOMMENDATION]

1. **Immediately (before any coding):** rotate the API-Football key at api-sports.io, the TheSportsDB key, the SMTP token at Mailtrap, and change the test users' passwords. Consider putting `soccer-predictions-app-7787` behind Block Public Access (or emptying it) until a key-free build is deployed; delete `predictions-app-778778324` (test page).
2. **Branch hygiene:** create `develop` from `progress`; commit the WIP in two commits (backend BTTS incl. migration; frontend BTTS + filters) after fixing the 3 new TS errors; add a root `.gitignore` (`.DS_Store`, `*.html` test pages, screenshots, local docs or move docs into `docs/archive/`); open a PR `develop → main` to replace the CRA prototype; delete `progress-v1`, `prod`, and the orphan `dev` after confirming nothing else lives there (keep a tag of `origin/dev` if the PowerShell scripts matter).
3. **Green build:** fix `frontend/.eslintrc.cjs` (`plugin:@typescript-eslint/recommended`), the 7 pre-existing TS errors, `vite.config.ts` (`base: '/'`, remove the hardcoded key, read it from `process.env` for the dev proxy only), and delete `frontend/src/services/prediction.service.ts` and the TheSportsDB files.
4. **Local env:** change `docker/docker-compose.yml` bind mounts to `./postgres/...` / `./redis/redis.conf` (or move the file to the repo root), uncomment the backend service, recreate `backend/venv` with Python 3.11, create `soccer_predictions_test`, fix `conftest.py` to override `app.core.deps.get_db` too, and get all 121 tests running in CI with Postgres/Redis service containers.
5. **Security fixes in the backend** (items 2–7 of §18) with regression tests; make `SECRET_KEY` mandatory when `ENVIRONMENT != development`.
6. **Then** proceed to §21 items 5–8.

---

## 23. Proposed phased continuation plan

| Phase | Scope | Exit criteria | Effort [INFERENCE] |
|---|---|---|---|
| **0 — Secure & stabilise** | Secret rotation/scrub, root `.gitignore`, WIP committed, TS/ESLint fixed, P0 backend fixes, CI skeleton, branch cleanup | `npm run build` and `pytest` (unit) green in GitHub Actions; no secrets in tree; `develop` is default & protected | 3–5 engineer-days |
| **1 — Reproducible dev & tests** | Compose fix + backend service, Python 3.11, test DB, integration tests runnable, coverage baseline, `.dockerignore`, docs triage (archive superseded, fix ports/paths) | `docker compose up` gives a working stack from scratch; all 121+ tests pass in CI | 3–5 days |
| **2 — MVP feature completion** | Backend fixtures proxy + cache (key server-side), BTTS in public API/aggregator, real match detail, admin approval or explicit self-publish policy, expert onboarding, subscription persistence, SES/SendGrid provider, remove/label fabricated predictions, fix P1 bugs | Regular user can browse real fixtures and real published predictions end-to-end; expert flow works incl. override; no fake data shown as real | 2–3 weeks |
| **3 — Cloud MVP deployment** | IaC (Terraform or CDK), CloudFront+S3, backend container (ECS Express Mode / Fargate, single service; App Runner is closed to new customers since 2026-04-30), RDS PostgreSQL (single-AZ to start), ElastiCache (or Redis on the same task initially), Secrets Manager, CloudWatch logs/alarms, OIDC-scoped deploy role, domain + ACM TLS, migrations job | Public HTTPS URL serving the current build against a live backend; deploy from GitHub Actions; rollback documented | 1–2 weeks |
| **4 — Post-MVP** | Settlement/accuracy, ML baseline, LLM source, analytics dashboards, notifications, e-mail verification, rate limiting, payments, DR/backups per plan | Per requirements §4.2/4.5 | ongoing |

---

## 24. Risks, estimated effort, and likely AWS costs

**Risks**
- **Credential abuse** until rotation (paid API quota drain, SMTP abuse). Likelihood high (public repo, live site). [VERIFIED exposure]
- **Data loss of uncommitted work** if this machine fails. [VERIFIED]
- **Hidden runtime bugs**: only 21–36% handler coverage and no integration tests have run since 2025-10-13; several endpoints have never been exercised (override, date filter). Expect more defects when integration tests are enabled. [INFERENCE]
- **External dependency**: the product currently depends on API-Football Pro quotas and CORS behaviour from the browser; a server-side proxy is required for production. [INFERENCE from `api-football.service.ts:13-16`]
- **Scope creep**: the documented architecture (four ECS services, Multi-AZ RDS, DR region, ML workers) is far ahead of the product's maturity; building it now would burn budget without users. [INFERENCE]
- **Process**: no PRs, no reviews, no CI, docs written faster than code; keeping the "session summary" habit will keep drift growing. [INFERENCE]

**Effort (order of magnitude, one senior full-stack engineer)**: Phase 0 ≈ 1 week; Phase 1 ≈ 1 week; Phase 2 ≈ 2–3 weeks; Phase 3 ≈ 1–2 weeks → **≈6–8 weeks to a deployed MVP**, before ML/settlement work.

**Likely AWS costs** [INFERENCE, us-east-1 on-demand, no free tier — the account is past its first year]:

| Option | Components | Estimate |
|---|---|---|
| Today | 2 S3 website buckets | ≈ $0.01–0.05 / month |
| **Lean MVP (recommended)** | S3 + CloudFront (≈$1–5); ECS Fargate 0.5 vCPU/1 GB (≈$15) + ALB (≈$18) via ECS Express Mode (App Runner is closed to new customers since 2026-04-30); RDS `db.t4g.micro` single-AZ 20 GB (≈$13–16); ElastiCache `cache.t4g.micro` (≈$12, **required**: refresh tokens and the token blacklist live in Redis); Secrets Manager (≈$1–2); CloudWatch (≈$2–5); Route 53 zone ($0.50) | **≈ $60–110 / month** |
| Documented plan | ECS Fargate ×4 services, RDS `db.r6g.xlarge` Multi-AZ + replicas, ElastiCache Multi-AZ, NAT gateways, DR in us-west-2 | $1,050–2,100 / month (plan's own figure); not justified now |

Other costs: API-Football Pro (≈$25–50/month per its pricing docs), e-mail provider, domain registration.

---

## 25. Decisions that genuinely require owner input

1. **Secret rotation and history**: rotate the API-Football, TheSportsDB, Mailtrap SMTP, and test-user credentials now (only the owner can). Then choose: (a) rotation only, leaving history as-is (keys become useless), or (b) rewrite history / recreate the repo to remove them (destructive, breaks clones).
2. **Take down or keep the live S3 sites** while they still expose the old key (`soccer-predictions-app-7787`) and the widget test (`predictions-app-778778324`).
3. **Branch strategy**: make the real app the default branch (merge `progress` → `main` via PR, or rename); delete `progress-v1`, `prod`, and the orphan `dev`.
4. **Which uncommitted work to keep**: commit the BTTS/Total-Goals feature (recommended, after fixes) or park it; whether the 51 root docs should be committed (after scrubbing), archived under `docs/archive/`, or dropped.
5. **Product rule for approval**: keep "experts publish their own predictions" (current behaviour) or enforce admin approval as the requirements state.
6. **KAN-26 storage strategy**: v1 "store all sources" (implemented) vs v2 "store only expert/LLM, cache API-Football" (documented).
7. **Fake predictions**: continue showing randomized predictions/odds for fixtures without real data (current), label them clearly, or hide them.
8. **Deployment target and budget**: lean MVP (~$60–110/month) vs the documented architecture; ECS Express Mode/Fargate (App Runner is no longer available to new customers); single region `us-east-1` (matches existing buckets).
9. **Domain name and TLS** (none exists; docs mention Namecheap).
10. **External providers**: confirm the API-Football plan/quota; choose SES vs SendGrid vs Mailtrap for production e-mail.
11. **IAM**: create a project-scoped deploy role (scope the existing `github-oidc` trust to `repo:fotso94/PredictionsAppsUI:*` and least-privilege policies) and retire one of the two `superadmin` access keys.
12. **Jira**: provide access or an export so KAN ticket states can be reconciled with code.
13. **Python 3.11** as the local runtime (recreate venv) — trivial but changes the developer setup.

---

## 26. Commands and evidence used during the assessment

All commands were read-only. Representative list (full outputs were reviewed during the session):

```bash
# Local git
git branch -a; git rev-parse HEAD; git log --oneline -30; git status --porcelain
git remote -v; git tag -l; git stash list; git for-each-ref refs/heads refs/remotes
git log main..progress --oneline; git merge-base main progress; git diff --stat main progress
git diff --stat; git ls-files | wc -l; git ls-files '*.md'; git reflog -n 25
git show origin/dev:aws-deploy.sh (and deploy-aws.ps1, setup-cloudfront.ps1, update-app.ps1, deployment-info.txt, aws-setup-guide.md)
git ls-tree -r --name-only origin/dev | grep -c node_modules
git grep -nIE '<secret patterns>' progress -- . ':!*.md'   # locations only
git log -S'x-apisports-key' -- frontend/vite.config.ts

# GitHub (read-only)
git ls-remote origin; gh auth status; gh repo view fotso94/PredictionsAppsUI --json ...
gh pr list --state all; gh issue list --state all; gh release list; gh api repos/.../tags
gh api repos/.../actions/workflows; gh api repos/.../actions/runs; gh api repos/.../environments
gh api repos/.../deployments; gh api repos/.../branches; gh api repos/.../branches/main/protection
gh api repos/.../compare/main...progress; gh api repos/.../secret-scanning/alerts; gh api repos/.../pages

# AWS (profile me, read-only)
aws sts get-caller-identity --profile me; aws configure get region --profile me
aws ec2 describe-regions; per-region describe/list calls for ~45 services (script saved in the session scratchpad)
aws s3api list-buckets / get-bucket-website / get-bucket-policy / get-public-access-block / get-bucket-encryption / list-objects-v2
aws cloudfront list-distributions; aws route53 list-hosted-zones; aws acm list-certificates
aws iam list-roles/list-users/get-role github-oidc/list-attached-*-policies/list-access-keys
aws ce get-cost-and-usage (by SERVICE and REGION, Oct 2025 – Sep 2026); aws budgets describe-budgets
aws cloudtrail lookup-events --lookup-attributes AttributeKey=ResourceName,AttributeValue=<bucket>
curl http://soccer-predictions-app-7787.s3-website-us-east-1.amazonaws.com/ (+ deep routes, asset paths, bundle)

# Local validation (no writes to the project)
docker ps -a; docker volume ls; docker images; lsof -nP -iTCP -sTCP:LISTEN
docker compose -f docker/docker-compose.yml config --quiet
python3 -c "ast.parse(...)" over backend/**/*.py
PYTHONDONTWRITEBYTECODE=1 venv/bin/python -c "import app.main"   # 58 routes
venv/bin/python -m pytest -p no:cacheprovider -o addopts="" -q <5 pure-unit files>   # 93 passed
./node_modules/.bin/tsc --noEmit -p tsconfig.json   # 10 errors
./node_modules/.bin/eslint --ext ts,tsx src/App.tsx  # config error
gzip -dc docs/database/soccer_predictions_20251008_224941.sql.gz | grep -c '^pg_dump:'   # 1113
```

Subagents (read-only) produced the full inventories of the 109 documentation files, the backend code audit, and the frontend code audit; their highest-impact claims were re-verified by me against the source before inclusion.

---

## 27. START HERE — for the next implementation session

> # ⛔ HISTORICAL — this was the plan on **2026-09-17**. Do not work from it.
>
> This checklist was written before any implementation. Most of it is **done**, and several items are
> **reversed by owner decision**. Following it now would undo completed work. It is kept as the
> record of what was planned, not as a task list.
>
> **Item by item:**
>
> | Instruction below | Status today |
> |---|---|
> | `git switch -c develop progress` | **Do not.** No `develop` branch exists or is wanted; work is on `main` and `progress`. Branch strategy was settled without it |
> | Add a root `.gitignore` | **Done** — one exists at the repository root |
> | Remove hard-coded keys from code | **Done** (Addendum B). Rotating the exposed keys is still an **owner** action |
> | `delete frontend/src/services/thesportsdb.service.ts` | **Reversed.** TheSportsDB is a *retained fallback* by owner decision. The file stays. (Its stored key is currently rejected as invalid — that is a key problem, not a reason to delete the integration) |
> | Delete `frontend/src/services/prediction.service.ts` | **Not done, and no longer the plan.** The file is still present |
> | Fix `.eslintrc.cjs` and the 10 `tsc` errors; set `base: '/'` | **Done**, except `base`: `vite.config.ts` uses `base: './'` deliberately. `type-check`, `lint` and `build` pass |
> | Commit the BTTS work with its migration | **Done** |
> | Backend P0 fixes | **Partly done.** Registration no longer accepts `role=admin`; the rest of the Phase 2 security list (session revocation, `SECRET_KEY` handling, rate limits) is still open |
> | "approval policy" / admin approval gate (and Phase 2 "server-side data proxy") | **Superseded.** The server-side data path is **built** — `/api/v1/matches`, `/leagues`, `/teams`, `/data-providers/*` — do not rebuild it. Experts publish directly (`EXPERT_DIRECT_PUBLISH=true`, Addendum C); do not impose admin review unless the owner reverses that decision. What the flag actually does when switched off is documented in the root `README.md` |
> | Add `.github/workflows/ci.yml`; push; open PR | **Not done, and deliberately left to the owner** — it would run on their GitHub account. Still worth doing |
> | "Local run (after Phase 1 fixes)" | **Superseded.** The compose command given below is missing `--project-directory .` and does not work. The canonical command is in the root `README.md` and `docker/README.md` |
>
> **Where to start instead:** the root [`README.md`](README.md) for how to run and test the system,
> [`MORNING_HANDOFF_2026-09-18.md`](MORNING_HANDOFF_2026-09-18.md) §8 for the open items in priority
> order, and [`CODEX_INDEPENDENT_REVIEW.md`](CODEX_INDEPENDENT_REVIEW.md) for the independent audit's
> outstanding findings.

---

### Original START HERE, as written on 2026-09-17 (historical — see the notice above)

**Preconditions (owner):** rotate the four credential sets (§25 item 1); confirm the branch strategy (§25 item 3); answer items 5–8 of §25 or accept the defaults below.

**Defaults I will assume if not told otherwise:** keep expert self-publish for now (confirmed by the owner, Addendum C); keep the v1 "store all" storage; show "No prediction available" instead of fabricated values; lean MVP on `us-east-1` with ECS Express Mode/Fargate + RDS `t4g.micro` + ElastiCache `t4g.micro` + CloudFront.

**Session 1 checklist (Phase 0):**
1. `git switch -c develop progress`; add root `.gitignore`; move root status docs to `docs/archive/` (or delete) after scrubbing keys.
2. Remove hard-coded keys from `frontend/vite.config.ts`, `frontend/src/services/api-football.service.ts`, `frontend/src/services/thesportsdb.service.ts` (delete file), `backend/app/core/config.py:146`, `backend/alembic.ini:61`, `backend/test_smtp_connection.py`, `backend/create_expert_user.py`, `backend/update_expert_password.py`, `frontend/test-login.html`; read from env.
3. Fix `frontend/.eslintrc.cjs` and the 10 `tsc` errors; set `base: '/'`; delete `frontend/src/services/prediction.service.ts`.
4. Commit the BTTS work **with** `backend/alembic/versions/eb2ef2cf6caf_*.py`.
5. Backend P0 fixes: reject non-`regular` roles in register; blacklist on revoke (or check the stored-token map in `/refresh`); require `SECRET_KEY` outside development; fix `PredictionOverride` construction; `audit_metadata=`; replace `log_action`; guard the cascade delete.
6. Add `.github/workflows/ci.yml` (frontend build + backend unit tests); push; open PR `develop → main`.

**Files to read first:** `backend/app/api/v1/api.py`, `backend/app/api/v1/endpoints/expert.py`, `backend/app/services/expert_prediction.py`, `backend/app/core/{config,deps,security}.py`, `frontend/src/App.tsx`, `frontend/src/services/{api-client,football-data.service,api-mapper.service}.ts`, `docker/docker-compose.yml`, `backend/tests/conftest.py`, and the three authoritative status docs in §3.

**Local run (after Phase 1 fixes):** `docker compose -f docker/docker-compose.yml up -d` → `cd backend && alembic upgrade head && uvicorn app.main:app --reload` → `cd frontend && npm run dev`. Until then, expect the compose paths and Python version issues described in §16.

---

## Final recommendation

**Where it stands.** A well-scoped product with a solid data model, a working auth/RBAC core, an expert prediction workflow, and a modern frontend, frozen since mid-October 2025 with unmerged, uncommitted, and unbuildable work, leaked credentials, and no backend deployment. The only cloud asset is a stale static demo on S3.

**Is the technical direction sound?** Yes. React/Vite + FastAPI + PostgreSQL multi-schema + Redis on AWS is appropriate and should be kept. What is not sound is the gap between documentation and reality (docs describe a production-ready hybrid ML platform; code is an MVP scaffold with fabricated predictions), the browser-side use of a paid API key, the absence of CI, and the premature four-service cloud design.

**Highest-priority next task.** Rotate the leaked credentials and get the tree to a green, committed, CI-verified baseline (Phase 0). Nothing else should start before that.

**Exact order of remaining work.** Phase 0 (secure/stabilise) → Phase 1 (reproducible dev + tests) → Phase 2 (MVP features: server-side data proxy, real match detail, BTTS in public API, approval policy, subscriptions) → Phase 3 (lean AWS deployment with IaC and OIDC deploys) → Phase 4 (settlement, ML, analytics, payments).

**States to reconcile before implementation resumes.**
- *Local:* commit or park the 16 modified + 68 untracked paths (migration included); add a root `.gitignore`; recreate the venv on Python 3.11; fix compose paths.
- *GitHub:* make the real app the default branch; delete `progress-v1`, `prod`, orphan `dev`; enable branch protection, Actions, secret scanning/Dependabot; remove tracked secrets.
- *AWS:* rotate keys; scope or replace the `github-oidc` role and retire one `superadmin` key; either block public access on / empty `soccer-predictions-app-7787` until a key-free build ships, and delete `predictions-app-778778324`; set a default region for profile `me` (`us-east-1`) or always pass `--region`.

---

## Addendum A — Implementation phase 1 (2026-09-17, authorized by the owner)

Owner authorized two items from §25: **item 4** (commit the BTTS/Total-Goals work after fixes; scrub, archive or drop the root docs) and **item 3** (make `progress` the real `main`, retire `progress-v1`, `prod` and the orphan `dev`). Everything below was executed and verified; paths in §3, §9–§12 and §16 above describe the state *before* this addendum.

### A.1 Commits (all on `progress`, now also `main`)

| Commit | Content |
|---|---|
| `6a79723` chore(repo): add root .gitignore | OS/editor files, `node_modules`, `frontend/dist`, `backend/venv`, coverage/pytest caches, `.env*`, `.trunk/`. |
| `aa319fb` docs: scrub secrets and archive 2025-10 session notes | 48 root session notes + 2 txt → `docs/archive/session-notes-2025-10/`; 4 throw-away test pages → `docs/archive/legacy-test-pages/` (`diagram2.html` dropped as a byte-identical duplicate); requirements docs → `docs/requirements/`; `docs/archive/README.md` added. Redacted in 28 files: API-Football key ×21, TheSportsDB key ×20, Sportradar and StatPal trial keys, expert test password ×3, 14 password values, 33 personal e-mail addresses. |
| `c604737` feat(backend): add BTTS and Total Goals prediction markets | The uncommitted backend change set **including** migration `eb2ef2cf6caf`, plus fixes: public endpoints now return the eight market fields; `ExpertPredictionUpdate` gets the BTTS-sum validator and the update endpoint maps `IntegrityError` to 400; duplicate `convert_decimal_to_float` validator removed; `toggle-publish` audits through a new `log_prediction_status_toggled`; audit metadata now persists into `audit_metadata`; model declares the migration's five check constraints. |
| `1943c52` feat(frontend): BTTS and Total Goals markets, live-match filters | The uncommitted frontend change set + `utils/matchFilters.ts`, with the three unused-symbol errors it introduced removed. |
| `b5f8a0f` fix(frontend): make type-check, lint and build pass | ESLint config (`plugin:` prefix), seven pre-existing `tsc` errors, `getTeams()` optional league/season, unused proxy arg. |
| `5212e59` docs: BTTS/Total Goals implementation notes, expert form guide, screenshots | Five feature docs and three screenshots (the 15 MB duplicate screenshot was deliberately left untracked). |

### A.2 Verification evidence

- `tsc --noEmit`: 0 errors (was 10). ESLint: 0 errors, 53 warnings (`npm run lint` still fails because the script uses `--max-warnings 0`). `npm run build`: succeeds (bundle `index-b56d48dd.js`, 649 KB).
- Backend: 72 files parse; `import app.main` succeeds with warnings-as-errors (58 routes); 93 pure-unit tests pass.
- Alembic: `upgrade head` → `downgrade -1` → `upgrade head` round-trip succeeded on a fresh `postgres:15-alpine` **with the project init script mounted**; the eight columns and five constraints appear and disappear as expected. Temporary container removed.
- Post-scrub scan: the key values remain only in application code (`frontend/vite.config.ts`, `frontend/src/services/api-football.service.ts`, `frontend/src/services/thesportsdb.service.ts`, `backend/app/core/config.py`, `backend/.env.example`), in `backend/create_expert_user.py` / `update_expert_password.py`, and in the git-ignored `backend/.env`. **Rotation (item 1) is still required.**

### A.3 Branch and tag changes on GitHub

- `main` fast-forwarded from `fdd40cb` (CRA prototype) to `5212e59`; it is the default branch and now shows the real application. `progress` points at the same commit and is redundant; delete it once nobody depends on it.
- Deleted branches: `progress-v1`, `prod`, `dev` (remote) and `progress-v1`, `dev` (local). Nothing was lost: annotated tags `archive/main-cra-prototype-2025-09-22`, `archive/progress-v1-2025-10-14`, `archive/dev-orphan-deploy-scripts-2025-09-24` (holds the PowerShell S3/CloudFront scripts) and `archive/dev-local-2025-09-22` were pushed first. `prod`'s only commit is already part of `main`'s history.
- Local checkout switched to `main`. Working tree clean except the untracked 15 MB screenshot.

### A.4 New findings and follow-ups discovered during this phase

1. **Migration portability defect (pre-existing, not fixed):** `add_multi_source_prediction_priority.py` hard-codes `ALTER TYPE users.predictionsource`. On a bare PostgreSQL (no `docker/postgres/init/01-init-database.sql`), the enum types are created in `public` and the chain fails at revision `2a4f8c9d1e3b`. Fix in Phase 1 by resolving the enum's schema dynamically (or creating enums with an explicit schema) so CI can run migrations without the init script.
2. The repository root now has no `README.md` (the old one belonged to the CRA prototype). Add a short README pointing to `docs/requirements/`, this report and the run instructions.
3. `screenshots/screenshots_expert-match-selection-filtered_2025-10-15T19-37-28-037Z.png` (15 MB) is untracked; delete or shrink it.
4. Over/Under 2.5 and 3.5 pairs are still not validated for complementarity (documented behaviour: "no strict sum validation"); decide whether to enforce it.
5. Remaining P0/P1 items from §18 are untouched (registration role escalation, session revocation, `SECRET_KEY` default, expert override kwargs, `db.func.date`, `status` shadowing, email template path, source-badge case bug, mock match detail page).

---

## Addendum B — Implementation phase 2 (2026-09-17): credentials out of code, migration portability, README

Owner asked for follow-through on the three open items of Addendum A. Commits on `main` (mirrored to `progress`): `2534b55` security, `ceee14f` migration fix, `7501cc4` README.

### B.1 Credentials removed from application code (`2534b55`)

| Location (before) | Now |
|---|---|
| `frontend/vite.config.ts` hard-coded API-Football key in the dev proxy | Proxy reads `API_FOOTBALL_KEY` from `frontend/.env` via `loadEnv` (no `VITE_` prefix, so it is never bundled) and injects `x-apisports-key` server-side; the current key was written to the git-ignored `frontend/.env` so local development keeps working until rotation. |
| `frontend/src/services/api-football.service.ts` hard-coded key | `apiKey: import.meta.env.VITE_API_FOOTBALL_KEY ?? ''`; the header is only sent when a key is configured. `VITE_API_FOOTBALL_KEY` is documented (`.env.example`, `vite-env.d.ts`) as an insecure demo-only opt-in because anything `VITE_`-prefixed ships in the public bundle. Production builds therefore send no key until a backend proxy exists. |
| `frontend/src/services/thesportsdb*.ts` (3 files, ~1,000 lines, premium key in URL) | Deleted; nothing imported them. |
| `backend/app/core/config.py` default `THESPORTSDB_KEY` | `None`; `backend/.env.example` placeholder emptied. |
| `backend/alembic.ini` dev DB URL with password | Placeholder URL; `alembic/env.py` already overrides it from settings. |
| `backend/test_smtp_connection.py` Mailtrap token | Reads `SMTP_*`/`EMAILS_FROM_EMAIL` from settings, optional `SMTP_TEST_TO_EMAIL`. |
| `backend/create_expert_user.py`, `backend/update_expert_password.py` expert e-mail + password | `EXPERT_TEST_EMAIL` / `EXPERT_TEST_PASSWORD` env vars or interactive prompt; passwords no longer echoed. |
| Personal e-mail addresses in `backend/.env.example`, `test_email_manual.py`, `test_password_reset.py` | `example.com` placeholders. |

Verification: no tracked file contains any of the four secret values (API-Football key, TheSportsDB key, Mailtrap token, expert password); `tsc` 0 errors, ESLint 0 errors / 51 warnings, `vite build` succeeds and the bundle contains no 32-hex token and no TheSportsDB code; backend imports (58 routes) and 93 unit tests pass; helper scripts parse.

### B.2 What still has to happen for item 1 (owner actions)

1. **Rotate** at the providers: API-Football (api-sports.io dashboard → regenerate key), TheSportsDB (premium key; optional since the integration is deleted), Mailtrap (reset the Live SMTP token), and change the expert test user's password. Put the new values only in `frontend/.env` (`API_FOOTBALL_KEY`) and `backend/.env` (`SMTP_PASSWORD`, `API_FOOTBALL_KEY`); never in tracked files.
2. **History**: the old values remain in git history on `main`/`progress` (API-Football and TheSportsDB keys since `e07b2b2` 2025-10-08, 5 commits each, 3 file paths; Mailtrap token since `736ab2d` 2025-10-11; expert password since `d221f6f` 2025-10-14). The repository is public with **0 forks**. Options: (a) rotation only, history left as-is, values become useless; (b) rewrite history with `git filter-repo --replace-text` (not installed; `pip install git-filter-repo`) followed by a force-push of `main`, `progress` and the four `archive/*` tags and a fresh clone on every machine; GitHub may additionally need a support request to purge cached views. Recommendation: (a) is sufficient once rotation is done; choose (b) only if a clean public history matters.
3. GitHub already has secret scanning **and push protection enabled** (confirmed via API); "non-provider patterns" and "validity checks" are disabled and can be turned on in repository settings for broader coverage.
4. The live S3 site `soccer-predictions-app-7787` still serves the old key in its October bundle until it is emptied/blocked or redeployed from a key-free build (owner decision, §25 item 2).

### B.3 Migration portability (`ceee14f`)

`add_multi_source_prediction_priority.py` (`2a4f8c9d1e3b`) now resolves the schema of the `predictionsource` enum from `pg_type`/`pg_namespace` before adding values. Verified on `postgres:15-alpine`: bare database (enum in `public`) and database initialised by `docker/postgres/init/01-init-database.sql` (enum in `users`) both reach head `eb2ef2cf6caf`; `downgrade -1` / `upgrade head` round-trip works. Pre-existing limitation left as-is: `alembic downgrade base` drops the tables but not the 20 enum types created by the initial migration, so a subsequent `upgrade head` on the same database fails with "type already exists" (documented in `backend/docs/DATABASE_MODELS_IMPLEMENTATION.md`); recreate the database instead of downgrading to base.

### B.4 README and housekeeping

- `README.md` added at the root (`7501cc4`): overview, layout, prerequisites, local development steps, tests, secrets policy, deployment status. The Compose file needs no change: run it from the repository root with `docker compose -f docker/docker-compose.yml --project-directory . up -d` and the `docker/postgres/...` and `docker/redis/...` bind mounts resolve correctly (verified with `docker compose config`).
- The 15 MB duplicate screenshot was deleted from the working tree (it was never tracked).

---

## Addendum C — Owner priorities and corrections after external review (2026-09-17)

**Owner decisions (verbatim intent):** experts publish their predictions directly for now (no administrator approval gate); the only goal of the next phase is a *working* application; security hardening is deferred to a second phase and stays documented in §18 and Addendum B.2.

**Corrections accepted from an independent review of this report:**
1. AWS App Runner is closed to new customers since 2026-04-30 (service in maintenance); ECS Express Mode / Fargate is the container target. §15, §23–§25 and §27 were updated.
2. Redis is not optional in the lean deployment: refresh-token storage and the blacklist depend on it (`backend/app/core/deps.py`). Cost table updated.
3. "Never deployed" was stronger than the evidence; §14 now says no backend deployment exists or is recorded.
4. `npm run lint` still fails on warnings (`--max-warnings 0`) even though ESLint reports 0 errors; the build and type-check pass. This report never claimed lint passes.
5. Archive tags preserve old commits, including committed secrets and `node_modules`; they are a safety net, not history cleanup (already stated in A.3/B.2).
6. Fabricated predictions, odds, H2H and statistics should be replaced by an explicit "No prediction available" state rather than a label. Adopted as a Phase 1 requirement.
7. The review noted the migration failed on a clean database; that was fixed in `ceee14f` (Addendum B.3) after the review's snapshot.

**Phase 1 ("make it work") scope derived from these priorities:** backend proxy for fixtures/leagues/teams/standings with Redis caching (frontend stops calling API-Football directly, production builds become functional); fix the functional defects on the expert and public journeys (§18 P1 items: override kwargs, `status` shadowing, `date` filter, `key_factors`, source-badge case, mock match detail page, dead links, password-change logout); expert publish as a first-class action; BTTS/Over-Under shown wherever predictions are shown; "No prediction available" instead of random values; reproducible local environment and CI. Security items (§18 P0 1–5, 8; rate limiting; e-mail verification) move to Phase 2, except credential rotation, which remains an owner action at any time.

## Addendum D — Phase 1 data and prediction integrations (2026-09-17)

**Decisions implemented:** Live Score API (14-day trial) is the primary match-data provider; GameForecastAPI (RapidAPI, free plan) is the prediction provider; API-Football and TheSportsDB stay as retained fallbacks; experts publish directly; credentials stay server-side; no deployment, AWS change or purchase was made.

**Backend (new):** provider abstraction with normalized DTOs (`app/services/providers/`: `livescore_api.py`, `gameforecast.py`, `api_football_provider.py`, `thesportsdb_provider.py`, `sample.py`, `registry.py`, `budget.py`, `http.py`, `competitions.py`); cross-provider fixture identity (`match_matching.py`, `match_registry.py`) with `predictions.provider_entity_refs` and `predictions.provider_forecasts` (migration `d4e5f6a7b8c9`); orchestration with Redis cache, stale fallback and request budgets (`match_data_service.py`, `forecast_service.py`); public endpoints `/api/v1/matches`, `/matches/live`, `/matches/{id}`, `/leagues`, `/leagues/{id}/standings`, `/leagues/{id}/matches`, `/teams/search`, `/teams/{id}`, `/data-providers/status`, admin `POST /data-providers/sync`. Legacy prediction lookups and the expert creation flow resolve any supported match id through the registry first (legacy API-Football path retained). `EXPERT_DIRECT_PUBLISH=true`: expert predictions are created as PUBLISHED and an expert profile is created/treated as verified on first use (`app/core/deps.py`, `auth.py` registration). New settings documented in `backend/.env.example`.

**Frontend:** `footballDataService` is now a facade (`VITE_DATA_SOURCE=backend|api-football`) over the new backend client (`backend-match-data.service.ts`); `Match.predictions`/`odds` are nullable with provenance (`expertPrediction`, `providerForecast`, `provider`, `externalId`); MatchCard, MatchDetailPage (real data), TeamDetailPage (real data), league pages, search and the expert match picker use the new source; expert vs model forecasts are labelled separately; missing markets and odds show "Unavailable"; randomized placeholders are behind `VITE_ALLOW_FAKE_PREDICTIONS` (off); provider status banner and stale-data notices added; the three TheSportsDB services were restored with the key read from `VITE_THESPORTSDB_KEY`.

**Verification:** backend 195 passed / 8 failed (the 8 are pre-existing failures in `tests/api/test_expert_endpoints.py` that also fail on the untouched code: they use a mock bearer token the auth layer rejects); 80 new tests cover the providers (mocked HTTP), budgets, matching, provider chain/stale cache, freshness, provider switching with expert predictions preserved, ambiguous/rescheduled fixtures, forecasts fetched before fixtures, expert onboarding and the endpoints (PostgreSQL-backed). Alembic upgrade → downgrade → upgrade verified on the docker database and on a bare database. Frontend `tsc` and `vite build` pass; ESLint 0 errors, 53 warnings (baseline 51; the two extra are pre-existing `any` usages in the restored TheSportsDB files). Browser checks (desktop and 375px mobile) with the sample providers: today/tomorrow lists, match detail, leagues, league detail with standings, team page, header search, expert login → match selection → publish → prediction visible on public pages.

**Live verification (2026-09-17, later the same day, with the owner's trial credentials):** Live Score API works end to end: `competitions/list.json` (523 competitions, single page), fixtures per competition and the competition calendar returned real data; the six competition ids were confirmed from the live list and are now defaults (Premier League 2, La Liga 3, Serie A 4, Bundesliga 1, Ligue 1 5, UEFA Champions League 244, verified by its calendar showing Arsenal v Lille and Lens v Sporting CP on 2026-10-13). Two defects found and fixed during the run: substring matching had picked "Non Premier League" (487) and "2nd Bundesliga" (93) — matching is now exact-first with extra exclusions; and Live Score answers bursts of requests with HTTP 401 ("do not have access to our data enabled"), so calls are now spaced 1 s apart with one retry. The calendar fetch stops paginating once past the forecast window. Provider failures now trigger cool-downs (rejected credentials 30 min, quota until UTC midnight) and the status page shows the provider's own error text. GameForecastAPI still answers "You are not subscribed to this API." for the owner's RapidAPI key (subscription pending on the RapidAPI side), so forecasts remain unverified; TheSportsDB rejected the stored key ("Invalid Premium API key"), so that fallback is not usable with the current key; API-Football's free plan rejects the current season as expected. Sample fixtures were purged from the local database (`backend/scripts/purge_sample_data.py`). The UI now uses the viewer's local calendar day for "today"/"tomorrow".

**GameForecastAPI verified live (same evening, after the owner subscribed to the Basic plan on RapidAPI):** the first sync fetched forecasts for the Premier League, La Liga, Serie A and Bundesliga and attached 30 of 30 to Live Score fixtures with exact kickoff matches (one Bundesliga fixture needed a fix: Live Score writes "Borussia Moenchengladbach", GameForecast "Monchengladbach"; team-name normalisation now folds the German oe/ae/ue transliterations, and forecasts that were unmatched at fetch time are retried from a pending store without new requests, also while the provider is paused). Ligue 1 and the Champions League follow on the next day because the 8-request daily budget was reached (league-id lookups are now persisted, so a full day costs 6 requests). Real payload facts recorded from the run: probabilities are on a 0-100 scale (home 85 / draw 10 / away 5), `exact_score` is `{"3_0": 14, ..., "other": 38}` (parser now detects the scale per snapshot and keeps only real scorelines as "3-0"), `recommended_bets` are market keys such as `matchResult.homeWinProbability` (rendered as readable labels), every event carries an English reasoning text and `run_at`, and further markets exist that the app does not use yet (over/under 0.5 and 1.5, first-half winner, team to score first, team goals). `scripts/reparse_forecasts.py` rewrites stored forecasts from their raw payload after a parser change.

**Not verified:** the Champions League forecast feed (no matches inside the sync window until 13 October); TheSportsDB fallback (stored key rejected). Both integrations follow the published documentation/spec; the first live run must be watched (`/api/v1/data-providers/status` shows budgets and last errors). The data-source evaluation in `docs/research/` was corrected: football-data.co.uk prohibits commercial and AI-training use, so it is not a training source; no in-house model is built in this phase.

**Known gaps carried forward:** no bookmaker odds feed (shown as unavailable); GameForecast free plan (10 requests/day) only allows one forecast sync per day for six competitions; Champions League ids for Live Score API are resolved by name (id 244 recorded) and should be confirmed on the first live run; the legacy API-Football browser path is retained but limited by the free plan; `npm run lint` still fails on pre-existing warnings.

## Addendum E — Phase 1 correctness pass (2026-09-18, autonomous run)

Scope: the six priorities the owner set for the overnight run — correct forecast values and repair
stored data, complete coverage within trial limits, reliable match identity, finish the user
experience, preserve forecast evidence, and test/fix/retest. No deployment, AWS change, purchase or
remote push was made; the GameForecastAPI and Live Score API trial allowances were not spent on
testing (every test drives the providers through mocked transports, and the browser suite stubs the
backend or reads only what the local database already holds).

### Priority 1 — forecast values and stored data

The parser inferred GameForecastAPI's 0-100 scale from whether a value exceeded 1, so a genuine 1%
would have been read as 100% certainty. The scale is now the provider's documented contract, applied
explicitly and unconditionally (`PROBABILITY_SCALE`), with one shared implementation in
`providers/base.to_probability(value, scale)` that the API-Football path also uses with its own
documented scale — that path had the same inference bug and is fixed with it. Values that are not
finite numbers inside the published range are dropped rather than clamped; a market whose values are
all zero is reported as unavailable rather than as 0%; complementary pairs and the 1X2 outcomes are
checked against a tolerance only when the whole market is present, and a failure is recorded in a new
`anomalies` field rather than silently corrected. Exact scores keep the provider's "other scorelines"
remainder in its own column so a partial list is never renormalised, and zero-probability scorelines
can never be selected as the most likely.

`backend/scripts/repair_forecasts.py` replaces `reparse_forecasts.py`: it re-derives every stored
forecast from the raw payload saved with it, makes no provider request, is idempotent, has a
`--dry-run` that reports every field it would change, preserves provider timestamps and expert data,
appends the corrected reading to the evidence history rather than overwriting it, and clears the
caches that held the old numbers. Run against the 30 stored forecasts it reported 30 corrected
(the `exact_score_other_prob` remainder, absent before) and, on a second run, 30 already correct and
0 changed. No stored probability changed, which confirms the explicit scale reproduces what the
inference happened to produce for this data while removing the 1% failure mode.

### Priority 2 — coverage within the trial limits

The request budget counted reservations, not requests: `consume()` incremented and then raised, so a
refusal inflated the counter and silently stole a real request (live Redis showed 9 used against a
limit of 8). Reservation is now atomic in Redis and the counter only advances when the request is
actually allowed out; refusals are counted separately as `refused_today`; a request that was sent and
then failed still counts, because the provider charged it. For a plan of 100 requests/day or fewer the
budget fails closed when Redis is unavailable, rather than spending blind. Spending is attributed by
reason (discovery, fetch, page, retry). No counter was reset.

Competitions are now synced least-recently-synced first. With the previous fixed order, a daily
allowance too small for six competitions spent itself on the same leagues every day and never reached
the tail — which is exactly why Ligue 1 and the Champions League had no forecasts. Competitions that
did not get their turn are reported under `deferred` and lead the next run; verified from the live
database, the next run's order is Ligue 1, Champions League, then the four already done. A Redis lock
stops two workers paying for the same competition. GameForecast league ids verified live are now
recorded in code (Premier League 15, La Liga 13, Serie A 3, Bundesliga 14, Ligue 1 4), so a cache
flush no longer re-pays discovery; an unresolvable competition is remembered for six hours instead of
being retried on every sync. Live Score's competition store falls back to its 30-day stale copy and
persists ids derived from defaults. A measured test prices a full run: one events request per
competition plus discovery only for a competition whose id is not already known, which today is the
Champions League alone — six competitions for seven requests cold, six warm.

### Priority 3 — match identity

Legacy matches that predate the provider-reference table were invisible to the fixture upsert, so the
next sync created a duplicate and orphaned the expert prediction attached to the original; they are
now recovered by their `external_api_id` and only after the team names and kickoff are verified.
Team lookup normalised the search term but matched it against the raw column, so "Borussia
Moenchengladbach" and "FC Cologne" could never be found and a provider switch would have split them
across duplicate rows. Only the provider that owns a match may move its kickoff, and terminal
statuses no longer move backwards. An ambiguous or home/away-swapped fixture is refused rather than
duplicated, and the refusal is counted. The candidate window was widened so a fixture postponed by
more than 36 hours is recognised as a possible reschedule rather than silently duplicated, while the
thresholds that allow an attach are unchanged. A provider event id that no longer names the same
teams — these ids are small integers and get recycled between seasons — no longer moves a forecast to
the wrong match. Unmatched forecasts are retried from the pending store on every path, including the
one where the allowance ran out, which is exactly when the cache is all there is, and the pending
store now merges rather than replaces, so a shorter window no longer discards a forecast already paid
for. All 22 of the owner's named transliteration pairs behave correctly, including the false
positives that had to be refused.

### Priority 4 — user experience

The frontend fabricated a zero-filled 1X2 block whenever the source published none, which is where
"Home Win (0%)" came from; the market is now nullable end to end and renders as unavailable. An
expert prediction with no 1X2 market is no longer discarded whole. The mapper no longer invents the
missing half of a complementary pair. Exact scores are validated before display. The home page's
invented accuracy rate, success rate, active users and total predictions are replaced with counts
measured from a new `/api/v1/data-providers/coverage` endpoint, which reports
`accuracy_available: false` with a reason instead of a number, because no result has been scored. The
dashboard's mock user statistics and the random prediction generator behind them are gone, as are the
randomised probabilities and bookmaker odds in the TheSportsDB mapper (the integration itself is
retained as a fallback, as instructed). Provider-generated, provider-updated and locally-fetched
times are kept distinct, with an explicit unknown state. A spent allowance reads as a paused refresh,
never as an unavailable forecast. Today and tomorrow now send the viewer's UTC offset and the backend
selects the viewer's local calendar day.

Two application bugs were found and fixed along the way: `GET /api/v1/predictions/published?date=`
always returned HTTP 500, and an expert could never edit a prediction once it was published, which
contradicts the direct-publishing decision. Naive UTC timestamps were being serialised without a Z,
so a browser read them as local time and could show a kickoff on the wrong day.

### Priority 5 — forecast evidence

`predictions.provider_forecasts` was updated in place, so each sync destroyed the only record of what
the model had said before kickoff. `predictions.provider_forecast_snapshots` (migrations
`e5f6a7b8c9d0` and `f6a7b8c9d0e1`) is an append-only history, one row per distinct forecast content,
recording the provider's own model-run time, the provider's update time, our retrieval time, the
kickoff known at capture and whether the capture was prematch — left NULL when the kickoff was
unknown, because a stored false would assert something we cannot know. Re-fetching unchanged content
only moves `last_fetched_at`. The current forecast stays a single indexed lookup. The 30 existing
forecasts were backfilled as prematch snapshots before anything was rewritten, and the repair added
its corrected reading alongside rather than over them: 60 snapshots for 30 matches. Retrieval time is
now stamped when the provider response is parsed, not when the forecast is attached, so a forecast
replayed from the pending cache two days later is not mistaken for a fresh one. No accuracy claim is
published anywhere.

### Priority 6 — tests, lint, type-check, build

The eight long-standing backend failures were traced to a test that patched a module attribute where
a FastAPI dependency override was needed: the real authentication ran and rejected the mock token
exactly as it should. They are fixed with `app.dependency_overrides`, with no change to production
authentication and no test skipped or deleted. A test that slept three seconds and still failed
intermittently now asserts the TTL Redis actually recorded.

---

*End of report.*
