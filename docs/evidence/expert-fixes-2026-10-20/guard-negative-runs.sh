#!/bin/zsh
# Unsafe Playwright configurations, each run once with the real playwright.config.ts, one after another.
# Every run carries the Node network tripwire (net-tripwire.cjs via NODE_OPTIONS): any TCP connect Node
# makes is recorded and blocked. Runs that name a live port select no test (--grep matching nothing), so
# that even without the preflight nothing could run against live.
FE="$(cd "$(dirname "$0")/../../../frontend" && pwd)"
TRIP=$FE/e2e/guard/net-tripwire.cjs
OUT=$(mktemp -d)
NOTEST='__the_isolation_guard_selects_no_test__'
n=0
run() {
  n=$((n+1)); local title="$1"; shift
  local log=$OUT/net-$n.log; : > $log
  echo "================================================================ run $n: $title"
  echo "\$ $*" | sed "s#--output=$OUT/[^ ]*#--output=<tmp>#"
  ( cd $FE && env -i PATH="$PATH" HOME="$HOME" TMPDIR="$TMPDIR" LANG="${LANG:-en_US.UTF-8}" FORCE_COLOR=0 \
      NODE_OPTIONS="--require $TRIP" GUARD_NET_TRIPWIRE_LOG=$log "$@" --output=$OUT/artifacts-$n --reporter=line 2>&1 )
  local code=$?
  echo "exit=$code"
  echo "node network tripwire: $(grep -c '^installed' $log) process(es) guarded; connections: $(grep -vc '^installed' $log)"
  grep -v '^installed' $log | sed 's/^/  /'
}
run "live-isolated asked for without E2E_STACK" \
  ./node_modules/.bin/playwright test --project=live-isolated
run "E2E_STACK=live-isolated with neither isolated URL set" \
  env E2E_STACK=live-isolated ./node_modules/.bin/playwright test --project=live-isolated
run "the live pair named as the isolated pair (selects no test)" \
  env E2E_STACK=live-isolated E2E_ISOLATED_API_URL=http://127.0.0.1:8000 E2E_ISOLATED_BASE_URL=http://localhost:3100 ./node_modules/.bin/playwright test --project=live-isolated --grep $NOTEST
run "an isolated API that is also E2E_API_URL" \
  env E2E_STACK=live-isolated E2E_ISOLATED_API_URL=http://127.0.0.1:8001 E2E_ISOLATED_BASE_URL=http://localhost:3101 E2E_API_URL=http://localhost:8001 ./node_modules/.bin/playwright test --project=live-isolated
run "a port the policy does not list (nothing listens on 8002)" \
  env E2E_STACK=live-isolated E2E_ISOLATED_API_URL=http://127.0.0.1:8002 E2E_ISOLATED_BASE_URL=http://localhost:3101 ./node_modules/.bin/playwright test --project=live-isolated
run "a mocked run whose frontend URL is the isolated backend" \
  env E2E_BASE_URL=http://127.0.0.1:8001 ./node_modules/.bin/playwright test --project=mocked-desktop
run "E2E_STACK naming both real stacks" \
  env E2E_STACK=live,live-isolated ./node_modules/.bin/playwright test
run "the live project asked for without E2E_STACK (selects no test)" \
  ./node_modules/.bin/playwright test --project=live --grep $NOTEST
rm -rf $OUT
