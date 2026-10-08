#!/usr/bin/env bash
#
# The local servers, detached from any terminal or desktop-app session.
#
#   scripts/local-servers.sh start  [main|isolated|all]   start whatever is not already listening
#   scripts/local-servers.sh stop   [main|isolated|all]   stop what this script (or anyone) started on those ports
#   scripts/local-servers.sh status                       who listens on each port, since when, from where
#   scripts/local-servers.sh reset-e2e-db                 recreate the e2e clone from the live database
#
# WHY. Servers started from .claude/launch.json belong to the desktop app and stop when its session
# ends; twice in a week the stack was found down for that reason alone. Started here they are
# children of launchd (nohup, disowned) and outlive the app; only a reboot stops them. Logs and
# pids go to .local-run/ (gitignored).
#
# THE TWO PAIRS.
#   main      backend :8000 on the live database, scheduler on; frontend :3100.
#   isolated  backend :8001 on the e2e clone, scheduler OFF, every provider credential blank, its
#             own Redis databases; frontend :3101 (reads frontend/.env.dev8001.local). The browser
#             tests that write something they cannot remove run only here (Playwright project
#             live-isolated), and e2e/support/isolated.ts refuses a backend that serves the live
#             database. The clone is a copy: `reset-e2e-db` refreshes it, and nothing in it is
#             evidence about the live database.
#
# Python: backend/venv311 (pyenv 3.11). The venv/ interpreter is Apple's Command Line Tools
# Python, which macOS refuses access to the Documents folder when the desktop app launches it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN="$ROOT/.local-run"
mkdir -p "$RUN"
E2E_DB="${E2E_DATABASE:-soccer_predictions_e2e}"
LIVE_DB="soccer_predictions"
CONTAINER="soccer_predictions_postgres"

listener_pid() { lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1 || true; }

describe() {
  local name="$1" port="$2" pid
  pid="$(listener_pid "$port")"
  if [ -z "$pid" ]; then
    printf '%-18s :%-5s not listening\n' "$name" "$port"
    return
  fi
  local started cwd
  started="$(ps -o lstart= -p "$pid" | sed 's/^ *//')"
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
  printf '%-18s :%-5s pid %-6s started %s  cwd %s\n' "$name" "$port" "$pid" "$started" "${cwd:-?}"
}

# start_one <name> <port> <cwd> <log> -- <command...>   (environment is passed via `env` in the command)
start_one() {
  local name="$1" port="$2" cwd="$3" log="$4"; shift 4; [ "$1" = "--" ] && shift
  local pid
  pid="$(listener_pid "$port")"
  if [ -n "$pid" ]; then
    echo "$name: already listening on :$port (pid $pid)"
    return
  fi
  # `exec` so no wrapper shell outlives the start holding this script's own stdout open, and every
  # descriptor the server inherits is a file or /dev/null: a caller that captures this script's
  # output (a tool, a pipe) would otherwise wait for the server to exit.
  ( cd "$cwd" && exec nohup "$@" >"$log" 2>&1 </dev/null ) >/dev/null 2>&1 &
  echo $! >"$RUN/$name.pid"
  disown 2>/dev/null || true
  local i
  for i in $(seq 1 60); do
    [ -n "$(listener_pid "$port")" ] && break
    sleep 0.5
  done
  if [ -z "$(listener_pid "$port")" ]; then
    echo "$name: did not start listening on :$port within 30 s; see $log" >&2
    tail -20 "$log" >&2 || true
    return 1
  fi
  echo "$name: started on :$port (pid $(listener_pid "$port"), log $log)"
}

ISOLATED_ENV=(
  "POSTGRES_DB=$E2E_DB"
  "SYNC_SCHEDULER_ENABLED=false"
  "LIVESCORE_API_KEY=" "LIVESCORE_API_SECRET=" "GAMEFORECAST_API_KEY=" "API_FOOTBALL_KEY=" "THESPORTSDB_KEY="
  "REDIS_DB_SESSIONS=10" "REDIS_DB_PREDICTIONS=11" "REDIS_DB_EXPERT_TOOLS=12"
  "REDIS_DB_ML_MODELS=13" "REDIS_DB_MATCH_DATA=14" "REDIS_DB_RATE_LIMIT=15"
  'BACKEND_CORS_ORIGINS=["http://localhost:3101","http://127.0.0.1:3101"]'
)

start_main() {
  start_one backend 8000 "$ROOT/backend" "$RUN/backend.log" -- \
    ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
  start_one frontend 3100 "$ROOT/frontend" "$RUN/frontend.log" -- \
    npx vite --port 3100 --strictPort
}

start_isolated() {
  if ! docker exec "$CONTAINER" psql -U postgres -tAc "select 1 from pg_database where datname='$E2E_DB'" 2>/dev/null | grep -q 1; then
    echo "the e2e database $E2E_DB does not exist yet; creating it from $LIVE_DB"
    reset_e2e_db
  fi
  start_one backend-isolated 8001 "$ROOT/backend" "$RUN/backend-isolated.log" -- \
    env "${ISOLATED_ENV[@]}" ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
  start_one frontend-isolated 3101 "$ROOT/frontend" "$RUN/frontend-isolated.log" -- \
    npx vite --port 3101 --strictPort --mode dev8001
}

stop_port() {
  local name="$1" port="$2" pid cwd
  pid="$(listener_pid "$port")"
  if [ -z "$pid" ]; then
    echo "$name: nothing listening on :$port"
    return
  fi
  # Only a process working inside this repository is ours to stop.
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
  case "$cwd" in
    "$ROOT"/*|"$ROOT") ;;
    *) echo "$name: pid $pid on :$port runs from ${cwd:-?}, not this repository; leaving it alone" >&2; return 1 ;;
  esac
  kill "$pid"
  local i
  for i in $(seq 1 40); do
    [ -z "$(listener_pid "$port")" ] && break
    sleep 0.5
  done
  echo "$name: stopped (was pid $pid)"
  rm -f "$RUN/$name.pid"
}

reset_e2e_db() {
  # A plain pg_dump piped into psql: nothing here can touch the live database. The clone is
  # dropped by its exact name and nothing else.
  [ "$E2E_DB" != "$LIVE_DB" ] || { echo "refusing: E2E_DATABASE is the live database" >&2; exit 2; }
  if [ -n "$(listener_pid 8001)" ]; then
    echo "stop the isolated backend first (it holds $E2E_DB open): scripts/local-servers.sh stop isolated" >&2
    exit 2
  fi
  docker exec "$CONTAINER" psql -U postgres -tAc "select 1 from pg_database where datname='$E2E_DB'" | grep -q 1 \
    && docker exec "$CONTAINER" dropdb -U postgres "$E2E_DB"
  docker exec "$CONTAINER" createdb -U postgres "$E2E_DB"
  docker exec "$CONTAINER" sh -c "pg_dump -U postgres $LIVE_DB | psql -q -U postgres -v ON_ERROR_STOP=1 $E2E_DB"
  # pg_dump does not carry the database-level search_path; alembic_version lives in the users schema.
  docker exec "$CONTAINER" psql -U postgres -tAc \
    "alter database $E2E_DB set search_path = users, predictions, ml_models, analytics, audit, public" >/dev/null
  echo "$E2E_DB recreated from $LIVE_DB at $(date -u +%Y-%m-%dT%H:%M:%SZ): $(docker exec "$CONTAINER" psql -U postgres -d "$E2E_DB" -tAc 'select count(*) from predictions.matches') matches"
}

cmd="${1:-status}"; which="${2:-all}"
case "$cmd" in
  start)
    case "$which" in
      main) start_main ;;
      isolated) start_isolated ;;
      all) start_main; start_isolated ;;
      *) echo "usage: $0 start [main|isolated|all]" >&2; exit 2 ;;
    esac ;;
  stop)
    case "$which" in
      main) stop_port backend 8000; stop_port frontend 3100 ;;
      isolated) stop_port backend-isolated 8001; stop_port frontend-isolated 3101 ;;
      all) stop_port backend 8000; stop_port frontend 3100; stop_port backend-isolated 8001; stop_port frontend-isolated 3101 ;;
      *) echo "usage: $0 stop [main|isolated|all]" >&2; exit 2 ;;
    esac ;;
  status)
    describe backend 8000; describe frontend 3100; describe backend-isolated 8001; describe frontend-isolated 3101 ;;
  reset-e2e-db) reset_e2e_db ;;
  *) echo "usage: $0 {start|stop|status|reset-e2e-db} [main|isolated|all]" >&2; exit 2 ;;
esac
