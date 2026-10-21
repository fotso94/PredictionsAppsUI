#!/bin/zsh
# Unsafe Playwright configurations, each run once with the REAL playwright.config.ts, one after another.
# Every run carries the Node network tripwire (frontend/e2e/guard/net-tripwire.cjs via NODE_OPTIONS): any
# TCP connect Node makes in the runner or a worker is recorded and BLOCKED. Runs that name a live port
# select no test (--grep matching nothing), so nothing could run against live even without the preflight.
FE="$(cd "$(dirname "$0")/../../../../frontend" && pwd)"
TRIP=$FE/e2e/guard/net-tripwire.cjs
OUT=$(mktemp -d)
NOTEST='__the_isolation_guard_selects_no_test__'
SECRET='hunter2-not-real'
n=0; held=0
run() {
  n=$((n+1)); local title="$1"; local expect="$2"; shift 2
  local log=$OUT/net-$n.log; : > $log
  echo "================================================================ run $n: $title"
  if [[ "$*" == *"$SECRET"* ]]; then echo "\$ ${*//$SECRET/***}   (the URL password is written *** in this echo only)"; else echo "\$ $*"; fi
  local text
  text=$( cd $FE && env -i PATH="$PATH" HOME="$HOME" TMPDIR="$TMPDIR" LANG="${LANG:-en_US.UTF-8}" FORCE_COLOR=0 \
      NODE_OPTIONS="--require $TRIP" GUARD_NET_TRIPWIRE_LOG=$log "$@" --output=$OUT/artifacts-$n --reporter=line 2>&1 )
  local code=$?
  print -r -- "$text"
  echo "exit=$code"
  local guarded=$(grep -c '^installed' $log); local conns=$(grep -vc '^installed' $log)
  echo "node network tripwire: $guarded process(es) guarded; connections: $conns"
  grep -v '^installed' $log | sed 's/^/  /'
  local leak=no; [[ "$text" == *"$SECRET"* ]] && leak=YES
  local refused=no; [[ "$text" =~ "$expect" ]] && refused=yes
  local ran=no; [[ "$text" =~ "Running [0-9]+ tests? using" ]] && ran=YES
  echo "checks: exit non-zero $([ $code -ne 0 ] && echo yes || echo NO); expected refusal text /$expect/ $refused; a test started $ran; the URL password in the output $leak"
  if [ $code -ne 0 ] && [ "$refused" = yes ] && [ "$ran" = no ] && [ "$leak" = no ] && [ "$conns" = 0 ] && [ "$guarded" -ge 1 ]; then
    echo "NEGATIVE HOLDS"; held=$((held+1)); else echo "NEGATIVE FAILED"; fi
}
run "E2E_STACK=live-isolated with neither isolated URL set" 'missing:E2E_ISOLATED_API_URL' \
  env E2E_STACK=live-isolated ./node_modules/.bin/playwright test --project=live-isolated
run "the live pair named as the isolated pair (selects no test)" 'live-target' \
  env E2E_STACK=live-isolated E2E_ISOLATED_API_URL=http://127.0.0.1:8000 E2E_ISOLATED_BASE_URL=http://localhost:3100 ./node_modules/.bin/playwright test --project=live-isolated --grep $NOTEST
run "a mocked run on the live frontend :3100 (selects no test)" 'live-target' \
  env E2E_BASE_URL=http://localhost:3100 ./node_modules/.bin/playwright test --project=mocked-desktop --grep $NOTEST
run "an isolated API URL carrying a password (the password must never be printed)" 'REFUSED' \
  env E2E_STACK=live-isolated "E2E_ISOLATED_API_URL=http://qa:$SECRET@127.0.0.1:8001" E2E_ISOLATED_BASE_URL=http://localhost:3101 ./node_modules/.bin/playwright test --project=live-isolated
run "a port the policy does not list (nothing listens on 8002)" 'unapproved-target' \
  env E2E_STACK=live-isolated E2E_ISOLATED_API_URL=http://127.0.0.1:8002 E2E_ISOLATED_BASE_URL=http://localhost:3101 ./node_modules/.bin/playwright test --project=live-isolated
run "an isolated API that is also E2E_API_URL" 'conflict:same-origin' \
  env E2E_STACK=live-isolated E2E_ISOLATED_API_URL=http://127.0.0.1:8001 E2E_ISOLATED_BASE_URL=http://localhost:3101 E2E_API_URL=http://localhost:8001 ./node_modules/.bin/playwright test --project=live-isolated
run "a mocked run whose frontend URL is the isolated backend" 'conflict:frontend-is-backend' \
  env E2E_BASE_URL=http://127.0.0.1:8001 ./node_modules/.bin/playwright test --project=mocked-desktop
run "E2E_STACK naming both real stacks" 'E2E_STACK must be one of' \
  env E2E_STACK=live,live-isolated ./node_modules/.bin/playwright test
run "the live-isolated project asked for without E2E_STACK" 'not found' \
  ./node_modules/.bin/playwright test --project=live-isolated
run "the live project asked for without E2E_STACK (selects no test)" 'not found' \
  ./node_modules/.bin/playwright test --project=live --grep $NOTEST
rm -rf $OUT
echo "================================================================"
echo "$held of $n hold"
[ $held -eq $n ]
