# The isolated pair

A second frontend and backend beside the ones under observation, on a copy of the data, with every
provider door closed. First used for the multi-market and slip work on 2026-09-25 while the retry
watcher was recording the backend on port 8000; since 2026-10-08 it is also where the browser tests
that write something they cannot remove are run (the Playwright project `live-isolated`).

| | main pair | isolated pair |
|---|---|---|
| backend | :8000, database `soccer_predictions`, scheduler on, provider credentials from `backend/.env` | :8001, database `soccer_predictions_e2e`, scheduler **off**, every provider credential **blank**, Redis databases 10–15 |
| frontend | :3100 | :3101 (`--mode dev8001`, reads `frontend/.env.dev8001.local`) |
| browser tests | `live` (reads; removes what it adds) | `live-isolated` (records slips that cannot be deleted) |

## Starting and stopping

```bash
scripts/local-servers.sh start all        # or: start main / start isolated
scripts/local-servers.sh status
scripts/local-servers.sh stop isolated    # or: stop main / stop all
```

The script starts each server detached from the terminal and from the desktop app (`nohup`,
disowned), so they outlive the app's session; only a reboot stops them. Logs and pids are in
`.local-run/` (gitignored). The `backend-isolated` and `frontend-isolated` entries in
`.claude/launch.json` start the same processes from the app, which stops them when its session ends.

Blank credentials make every provider "not configured": a page that asks for a refresh gets a
clean refusal and spends nothing. Redis databases 10–15 keep the isolated backend's sessions,
caches and budget counters apart from the live instance's 0–5. `GET /health` on either backend
says which database it serves (`database`), and `frontend/e2e/support/isolated.ts` refuses to run
a write-producing test against a backend that answers `soccer_predictions`.

## The e2e database is a copy, and is refreshed as one

`soccer_predictions_e2e` is a plain `pg_dump` of the live database piped into a fresh database:

```bash
scripts/local-servers.sh stop isolated     # the isolated backend holds the database open
scripts/local-servers.sh reset-e2e-db
scripts/local-servers.sh start isolated
```

`reset-e2e-db` drops a database of exactly that name and nothing else, and can never write to the
live one. Refresh it whenever the write-producing tests need current fixtures: `parlay-journey`
skips, saying so, when the clone holds no two scheduled fixtures with a forecast in the next seven
days. Nothing in the clone is evidence about the live database — a count, a row or a timestamp
read from `_e2e` says what the live database held when the clone was taken, and its slips are the
tests' own.

`soccer_predictions_dev` is an older copy with hand-staged rows (see the memory note of 2026-10-05);
it is not used by anything in the repository any more and can be dropped.

Migrations run against the clone by pointing the settings at it:

```bash
cd backend && POSTGRES_DB=soccer_predictions_e2e ./venv311/bin/alembic upgrade head
```

## Browser tests against the pair

```bash
cd frontend && npm run e2e:live-isolated
# the URLs, when they differ from the defaults:
E2E_ISOLATED_BASE_URL=http://localhost:3101 E2E_ISOLATED_API_URL=http://127.0.0.1:8001 npx playwright test --project=live-isolated
```

The `live` project keeps using `E2E_BASE_URL` / `E2E_API_URL` (default :3100 / :8000). The mocked
projects need neither backend; they stub every `/api/v1` call. The test-evidence runner
(`scripts/test_evidence.py run`) runs all six suites and refuses to start unless both pairs are up.
