# Follow-up verification of the guard follow-up: expert-fixes at 1a6109fe (2026-10-21)

These runs check the isolation preflight's follow-up fix (`b6c35b28`) on HEAD of `expert-fixes`,
`1a6109fe`. The commits after `b6c35b28` change only files under `docs/`. Every run started from a
clean working tree and ran on its own: `ps` showed no other pytest, `playwright test` or
`node --test` runner before the first run or after the last one. Each runner wrote straight to a
file with no pipe, and its exit code is the runner's own `$?`. The counts below are copied from each
runner's own summary line in the log named.

**Result: every run gave the expected result.**
- No test failed in any run.
- No run skipped a test, so the backend suite had 0 skipped.
- Every positive run exited 0.
- Every negative demonstration was refused:
  - backend runs exited 78;
  - Playwright runs exited 1;
  - no run made a connection attempt.

## Isolated identity

| | |
|---|---|
| Branch / HEAD | `expert-fixes` at `1a6109fe37167275eb0a6d980b3ebc5162707fb4`. `git status --porcelain --untracked-files=all` was empty before the first run. |
| Backend :8001 before | pid 13053, cwd `<worktree>/backend`. Its `/health` reported `source.commit` `b8b5f8bc` with 4 dirty app files (`isolation_targets.json`, `redis.py`, `target_guard.py`, `main.py`) and `app_tree_sha256` `b4a1d04d…` over 92 files. That is the code from before the follow-up, not HEAD. |
| Restart | Only backend-isolated was restarted, with `scripts/local-servers.sh stop backend-isolated`, then `… start backend-isolated`. The start runs `python -m app.core.target_guard --role isolated-backend` over `ISOLATED_ENV` first, and the guard approved it. :8000 (pid 27221), :3100 (pid 91426) and :3101 (pid 1982) kept their pids and were sent nothing. |
| Backend :8001 after | pid 2407, cwd `<worktree>/backend`, `uvicorn app.main:app --host 127.0.0.1 --port 8001` (the `venv311` interpreter is a symlink to the main checkout's venv; `app/` is imported from the cwd). |
| `/health` after | `database` `soccer_predictions_e2e`; `redis_databases` 10-15 on loopback :6379; `scheduler_enabled` false; `source.commit` `1a6109fe…` (the same as `git rev-parse HEAD`); `commit_dirty_app_files` `[]`; `app_tree_sha256` `02195dc15f1d73967cbe01b0b004bb258be82528f7268425109ae4152a94bb8b` over 93 files. That digest is the one [followup-tools/tree_digest.py](followup-tools/tree_digest.py) computes on the checkout with the standard library. `started_at` `2026-10-21T16:10:26Z`. |
| Backend env (non-secret) | `POSTGRES_DB=soccer_predictions_e2e`, `SYNC_SCHEDULER_ENABLED=false`, `EMAIL_ENABLED=false`, `REDIS_HOST=localhost`, `REDIS_PORT=6379`, `REDIS_DB=10`, `REDIS_DB_SESSIONS/PREDICTIONS/EXPERT_TOOLS/ML_MODELS/MATCH_DATA/RATE_LIMIT = 10/11/12/13/14/15`, `BACKEND_CORS_ORIGINS` set to :3101 only. The five provider keys are all **empty**. |
| After the last run | The same pids, commit, digest and `started_at` as above, so nothing restarted the backend during the runs ([followup-postflight.log](followup-postflight.log)). |
| Throwaway services | `guard-test-redis` on 127.0.0.1:6390 and `guard-race-pg` on 127.0.0.1:5440. Both ports were free first, and both containers were started for this work. They were removed by name (`docker rm -f`) after run 3, and both ports were free again afterwards. No other container was touched. |

Recorded in [followup-preflight.log](followup-preflight.log) and [followup-postflight.log](followup-postflight.log).

## Runs

| # | Run (started, UTC) | Passed | Failed | Skipped | Exit | Runner time | Log |
|---|---|---:|---:|---:|---:|---|---|
| 1a | Backend guard and /health tests: `tests/core/test_target_guard.py tests/test_health.py`, with the approved env plus `LEASE_TEST_REDIS_URL` and `RACE_TEST_DATABASE_URL` (16:11:14) | 114 | 0 | 0 | 0 | 9.61 s | [followup-backend-guard.log](followup-backend-guard.log) |
| 1b | `scripts/tests`, the evidence runner (16:11) | 94 | 0 | 0 | 0 | 1.60 s | [followup-runner-tests.log](followup-runner-tests.log) |
| 1c | Browser guard specs, `playwright test --config=playwright.guard.config.ts` (16:11:49) | 45 | 0 | 0 | 0 | 7.2 s | [followup-browser-guard-specs.log](followup-browser-guard-specs.log) |
| 1d | Refusal runs of the real config, `node --test e2e/guard/refusal-runs.test.mjs` (16:12:02) | 18 | 0 | 0 | 0 | 10.8 s | [followup-browser-refusal-runs.log](followup-browser-refusal-runs.log) |
| 2a | Backend negative demonstrations: 13 unsafe cases plus 1 control (16:15:26) | 14 of 14 hold | | | 0 (harness); each case below | | [followup-negative-backend.log](followup-negative-backend.log) |
| 2b | Browser negative demonstrations: 10 unsafe Playwright configurations (16:16:56) | 10 of 10 hold | | | 0 (script); each run 1 | | [followup-negative-browser.log](followup-negative-browser.log) |
| 3 | Backend, the FULL suite (`pytest tests -q -p no:cacheprovider -o addopts="" -rs`, approved env, 16:17:44) | 2003 | 0 | 0 | 0 | 80.02 s | [followup-backend-full-suite.log](followup-backend-full-suite.log) |
| 4a | Live-isolated: `expert-composer.spec.ts` and `expert-publishing.spec.ts`, `--project=live-isolated --workers=1` (16:19:35) | 10 | 0 | 0 | 0 | 15.4 s | [followup-live-isolated-expert.log](followup-live-isolated-expert.log) |
| 4b | Mocked, the five mocked specs this branch added, `--project=mocked-desktop` (16:20:07) | 96 | 0 | 0 | 0 | 3.1 m | [followup-mocked-new-specs-desktop.log](followup-mocked-new-specs-desktop.log) |
| 4c | Mocked, one existing spec (`overdue-results.spec.ts`) on `mocked-desktop`, `mocked-mobile` and `mocked-mobile-360` (16:23:34) | 147 | 0 | 0 | 0 | 1.0 m | [followup-mocked-existing-per-project.log](followup-mocked-existing-per-project.log) |
| 5a | `npm run type-check` (16:24:45) | no errors | | | 0 | | [followup-frontend-type-check.log](followup-frontend-type-check.log) |
| 5b | `npm run lint` (`--max-warnings 0`, 16:24:47) | no problems | | | 0 | | [followup-frontend-lint.log](followup-frontend-lint.log) |

**Commands.**
- **Backend pytest (1a and 3).** Run from `<worktree>/backend`. Every variable is written literally on the command line in front of the interpreter, with no shell variable:
  `TEST_DATABASE_URL=postgresql://postgres:***@localhost:5432/soccer_predictions_test POSTGRES_DB=soccer_predictions_test REDIS_HOST=127.0.0.1 REDIS_PORT=6390 SYNC_SCHEDULER_ENABLED=false EMAIL_ENABLED=false LEASE_TEST_REDIS_URL=redis://127.0.0.1:6390/9 RACE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5440/forecast_race_test ./venv311/bin/python -m pytest … -q -p no:cacheprovider -o addopts="" -rs`.
  The line before each count is the guard's own approval line. It names every target, and every target is an approved one.
- **Mocked Playwright runs.** They used `E2E_BASE_URL=http://localhost:3101`. The preflight said "nothing was sent to any server" each time.
- **Live-isolated runs.** They used `E2E_STACK=live-isolated E2E_ISOLATED_BASE_URL=http://localhost:3101 E2E_ISOLATED_API_URL=http://127.0.0.1:8001`. The preflight sent its one GET to `:8001/health` and found the e2e database, Redis 10-15 and the scheduler off.

**Counts per file and per project.**
- 4b: account-forms 22, expert-composer-localisation 19, expert-drafts 15, expert-management 19, revision-history 21, a total of 96. These five files are every mocked spec that `git diff --diff-filter=A main...` lists for this branch.
- 4c: 49 per project (mocked-desktop 49, mocked-mobile 49, mocked-mobile-360 49), a total of 147. `overdue-results.spec.ts` has been on main since `7380242f`, and it is one of the files that `mocked-mobile-360` lists.
- 4a: expert-composer 3 and expert-publishing 7, the same as at the baseline, the final run and the guard round.

**The guard's browser tests in step 4 are runs 1c and 1d.** They ran once, after the isolated
backend was restarted on HEAD. The approved isolated-pair case in 1d therefore hit the HEAD code,
whereas in the bypass round :8001 still ran the code from before the fix.

**Flaky.** Both Playwright configurations set `retries: 0`, and pytest ran with no rerun plugin,
so no test could pass on a retry.

## Negative demonstrations

### Backend (2a): the real pytest entry point behind tripwires

**How each case was run.** Each case is a subprocess run from `<worktree>/backend`:
`python -c <harness> -q -p no:cacheprovider -o addopts= -rs tests`. That is the whole suite, as a
person would run it.

**The tripwire.** The harness is the guard tests' own `BOOT`, copied verbatim from
`tests/core/test_target_guard.py` up to its mode switch. After it, `runpy.run_module('pytest',
run_name='__main__')` runs exactly what `python -m pytest` runs. The tripwire:
- records and blocks every `socket.connect`, every `socket.getaddrinfo`, every `psycopg2.connect`
  and every httpx request;
- records each import of `app.main`, `tests.conftest` and `app.db.session`.

**The environment.** It is empty except for PATH, HOME, LANG and TMPDIR, plus an approved base:
- PostgreSQL is the throwaway :5440 database;
- Redis is the throwaway :6390 server;
- both switches are off;
- `TEST_DATABASE_URL` and `POSTGRES_PASSWORD` carry fake passwords.

Each case then changes one unsafe class. Every unsafe target is a port nothing listens on, or
TEST-NET-1 (192.0.2.1), and never a live service.

| Case | Unsafe class | Refusal codes (each run's own) | Exit | Attempts | App imports |
|---|---|---|---:|---:|---:|
| control | none (the canary, approved) | (approved) | 0 | 10, all blocked, all to :5440, :6390 or the canary's dead HTTP port | 2 |
| 1a | missing overrides: `TEST_DATABASE_URL`, `SYNC_SCHEDULER_ENABLED`, `EMAIL_ENABLED` unset | missing:TEST_DATABASE_URL, missing:SYNC_SCHEDULER_ENABLED, missing:EMAIL_ENABLED, flag:SYNC_SCHEDULER_ENABLED, flag:EMAIL_ENABLED | 78 | 0 | 0 |
| 1b | missing override: `REDIS_PORT` unset (it would come from backend/.env) | missing:redis, live-redis | 78 | 0 | 0 |
| 2a | live database name: `soccer_predictions` (TEST_DATABASE_URL and POSTGRES_DB) | live-database | 78 | 0 | 0 |
| 2b | live database name: `soccer_predictions_dev` through DATABASE_URL | live-database | 78 | 0 | 0 |
| 3 | live Redis target: REDIS_HOST/REDIS_PORT naming :6379 | live-redis | 78 | 0 | 0 |
| 4a | live Redis database by URL: `REDIS_URL=redis://192.0.2.1:6379/3` | live-redis, conflict:redis-url-vs-parts | 78 | 0 | 0 |
| 4b | live Redis databases for the lease tests: `LEASE_TEST_REDIS_URL=…:6379/0` (0-2) | live-redis | 78 | 0 | 0 |
| 4c | the isolated pair's Redis databases 10-15 | isolated-pair-redis | 78 | 0 | 0 |
| 5a | conflicting settings: TEST_DATABASE_URL is not the settings' database | conflict:test-vs-settings-database, unapproved-database | 78 | 0 | 0 |
| 5b | conflicting settings: REDIS_URL and REDIS_HOST/PORT disagree | conflict:redis-url-vs-parts, unapproved-redis | 78 | 0 | 0 |
| 5c | conflicting settings: a URL query that redirects host, port and database | conflict:postgres-url, conflict:test-vs-settings-database, live-database | 78 | 0 | 0 |
| 5d | conflicting settings: the unsplit shell variable | conflict:unsplit-value | 78 | 0 | 0 |
| 5e | conflicting settings: two Redis roles share a database, and the race database is the test database | conflict:redis-db-collision, conflict:race-same-as-test | 78 | 0 | 0 |

**What every negative case printed.**
- `REFUSED: the isolation preflight (role backend-tests, at backend/conftest.py)`;
- "Nothing has connected to any database, Redis server or HTTP service";
- the resolved targets and the approved list;
- no test collected and no CANARY line.

**No credential appeared in any output.** The harness checked for:
- the two injected fake passwords. Both were absent from every output, including 5d, where one of
  them sat inside the unsplit value.
- the 11 secret values of `backend/.env`. The settings fall back to that file, which is a link to
  the main checkout's configuration. The harness read it only to make this check, and never printed
  a value. None of the 11 appeared in any output.

**4a** also shows `conflict:redis-url-vs-parts`. That is correct: `REDIS_DB=3` was set beside
`REDIS_URL`, so the guard compared the URL with the parts, whose host comes from `.env`.

### Browser (2b): the real playwright.config.ts behind the Node network tripwire

**How each run was made.** Each run was made from `<worktree>/frontend`:
- with an empty environment plus the variables shown;
- with `e2e/guard/net-tripwire.cjs` in `NODE_OPTIONS`, so every TCP connect from the runner or a
  worker is recorded and blocked;
- with `--output` set to a temporary directory and `--reporter=line`;
- one run after another.

Runs that name a live port also pass a `--grep` that matches nothing, so no test could have run
against live even without the preflight.

Every run had the same outcome:
- exit 1;
- its refusal text;
- `Running N tests` never printed;
- `connections: 0`, with 1 process guarded.

| Run | Unsafe configuration | Refusal |
|---|---|---|
| 1 | `E2E_STACK=live-isolated`, no isolated URLs | missing:E2E_ISOLATED_BASE_URL, missing:E2E_ISOLATED_API_URL |
| 2 | the live pair (:8000, :3100) named as the isolated pair | live-target ×2, conflict:same-origin |
| 3 | a mocked run on the live frontend (`E2E_BASE_URL=http://localhost:3100`) | live-target |
| 4 | an isolated API URL with a password in it | malformed-url ("carries credentials in the URL; they are not shown"). The password does not appear in the output. |
| 5 | an isolated API port the policy does not list (8002) | unapproved-target |
| 6 | an isolated API that is also `E2E_API_URL` | conflict:same-origin |
| 7 | a mocked frontend URL that is a backend (:8001) | conflict:frontend-is-backend |
| 8 | `E2E_STACK=live,live-isolated` | "E2E_STACK must be one of…", raised when the config loads |
| 9 | `--project=live-isolated` without `E2E_STACK` | project not found, with a hint |
| 10 | `--project=live` without `E2E_STACK` | project not found, with a hint |

### The helpers, kept beside the logs

The scratchpad does not survive a reboot, so the helpers are kept in [followup-tools/](followup-tools/):
- [negative_backend.py](followup-tools/negative_backend.py), run as `SCRATCH_DIR=<dir> negative_backend.py <worktree>/backend`.
- [negative_browser.sh](followup-tools/negative_browser.sh). It is the script that ran, with one
  change: its `FE=` line now finds `frontend/` relative to itself instead of naming the absolute
  path.
- [tree_digest.py](followup-tools/tree_digest.py), run as `tree_digest.py <checkout>`.

## Limits of this evidence

- **`npm run type-check` checks `src/` only.** It is `tsc --noEmit` with `tsconfig.json`, whose `include` is `["src"]`.
  - `playwright.config.ts` and `e2e/` are not type-checked by any project script, and `@types/node` is not installed.
  - Lint (5b) parses those files, and every Playwright run above loads them, which transpiles them without type checking.
  - So the frontend config change is shown to lint clean and to run, but not to type-check.
- **What the tripwires cover.** The backend tripwire sees what Python does in the pytest process.
  The Node tripwire sees the runner and its workers, but not Chromium. Each refused run stopped
  before any browser or test process started, as its output shows.
- **The shared PostgreSQL server.** `scripts/local-servers.sh start backend-isolated` first checks
  that the e2e database exists. It does this with `docker exec soccer_predictions_postgres psql -U
  postgres -tAc "select 1 from pg_database where datname='soccer_predictions_e2e'"`. That is one
  catalog read on the shared server's `postgres` maintenance database. It is not a connection to
  `soccer_predictions`.

## Not touched

- My commands sent nothing to :8000 or :3100, and opened no connection to the live database
  `soccer_predictions` or to the live Redis on :6379.
- Only the isolated backend :8001 uses Redis databases 10-15 on that server and
  `soccer_predictions_e2e`, as configured.
- No provider request was made, no dependency was installed, and nothing under the main checkout
  was changed.
- Only backend-isolated was restarted.
- The scrubbing of every log is stated at its foot:
  - `<worktree>` for the worktree path;
  - `~` for the home prefix;
  - `***` for the test database password.
- The logs contain no secret and no personal data.
