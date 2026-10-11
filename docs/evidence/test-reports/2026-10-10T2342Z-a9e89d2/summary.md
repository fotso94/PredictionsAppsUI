# Test evidence 2026-10-10T2342Z-a9e89d2

**CONTAMINATED**

- backend: exit 0, PASS
- mocked-desktop: exit 0, PASS
- mocked-mobile: exit 0, PASS
- mocked-mobile-360: exit 0, PASS
- live: exit 0, PASS
- live-isolated: exit 0, PASS

Contamination:
- 2026-10-10T23:44:22Z during mocked-desktop: foreign_runner, pid 70314 (pytest: Python '-m pytest')

## Run

- Run id: `2026-10-10T2342Z-a9e89d2`
- Started 2026-10-10T23:42:50Z, finished 2026-10-11T00:11:23Z (UTC)

| Suite | Started (UTC) | Finished (UTC) | Duration (s) | Exit code |
|---|---|---|---|---|
| backend | 2026-10-10T23:42:50Z | 2026-10-10T23:43:40Z | 50.6 | 0 |
| mocked-desktop | 2026-10-10T23:43:40Z | 2026-10-10T23:54:13Z | 632.8 | 0 |
| mocked-mobile | 2026-10-10T23:54:13Z | 2026-10-11T00:06:08Z | 714.9 | 0 |
| mocked-mobile-360 | 2026-10-11T00:06:08Z | 2026-10-11T00:08:46Z | 157.7 | 0 |
| live | 2026-10-11T00:08:46Z | 2026-10-11T00:11:19Z | 152.7 | 0 |
| live-isolated | 2026-10-11T00:11:19Z | 2026-10-11T00:11:23Z | 4.6 | 0 |

## Results

| Suite | Exit | Verdict | Planned | Passed | Failed | Flaky | Skipped | Did not run | Interrupted | Errors | xfailed | xpassed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| backend | 0 | PASS | - | 1685 | 0 | - | 0 | - | - | 0 | 0 | 0 |
| mocked-desktop | 0 | PASS | 453 | 451 | 0 | 0 | 2 | 0 | 0 | - | - | - |
| mocked-mobile | 0 | PASS | 453 | 453 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| mocked-mobile-360 | 0 | PASS | 140 | 140 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live | 0 | PASS | 56 | 55 | 0 | 0 | 1 | 0 | 0 | - | - | - |
| live-isolated | 0 | PASS | 2 | 2 | 0 | 0 | 0 | 0 | 0 | - | - | - |

### backend

The reporter's own final lines, verbatim:

```
1685 passed, 20 warnings in 49.47s
```

JUnit: 1685 testcases; passed or xpassed 1685, failed 0, errors 0, skipped 0, xfailed 0.

| Check | Result | Detail |
|---|---|---|
| pytest summary line present | ok | - |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit failed = pytest failed | ok | JUnit 0 / pytest 0 |
| JUnit errors = pytest errors | ok | JUnit 0 / pytest 0 |
| JUnit skipped = pytest skipped | ok | JUnit 0 / pytest 0 |
| JUnit xfailed = pytest xfailed | ok | JUnit 0 / pytest 0 |
| JUnit passed = pytest passed + xpassed | ok | JUnit 1685 / pytest 1685 |
| no skip says the test database or Redis is not reachable | ok | 0 such skip(s) |
| nothing deselected | ok | 0 deselected |
| at least one test ran | ok | 1685 test(s) |
| exit code agrees with the results | ok | exit 0, failed 0, errors 0, tests 1685 |
| not interrupted | ok | - |

### mocked-desktop

The reporter's own final lines, verbatim:

```
  2 skipped
  451 passed (10.5m)
```

JUnit: tests 453, passed 451, failures 0, errors 0, skipped 2. JSON (kept locally): 453 tests, buckets {'passed': 451, 'failed': 0, 'flaky': 0, 'skipped': 2, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 453 / buckets 453 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 451 / JSON 451 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 2 / JSON 2 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 451, 'unexpected': 0, 'flaky': 0, 'skipped': 2} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['mocked-desktop'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 453 / planned 453 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 2 / 2 |
| JUnit passed = passed + flaky | ok | JUnit 451 / 451 |
| JUnit holds exactly the requested project | ok | ['mocked-desktop'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### mocked-mobile

The reporter's own final lines, verbatim:

```
  453 passed (11.9m)
```

JUnit: tests 453, passed 453, failures 0, errors 0, skipped 0. JSON (kept locally): 453 tests, buckets {'passed': 453, 'failed': 0, 'flaky': 0, 'skipped': 0, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 453 / buckets 453 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 453 / JSON 453 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 0 / JSON 0 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 453, 'unexpected': 0, 'flaky': 0, 'skipped': 0} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['mocked-mobile'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 453 / planned 453 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 0 / 0 |
| JUnit passed = passed + flaky | ok | JUnit 453 / 453 |
| JUnit holds exactly the requested project | ok | ['mocked-mobile'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### mocked-mobile-360

The reporter's own final lines, verbatim:

```
  140 passed (2.6m)
```

JUnit: tests 140, passed 140, failures 0, errors 0, skipped 0. JSON (kept locally): 140 tests, buckets {'passed': 140, 'failed': 0, 'flaky': 0, 'skipped': 0, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 140 / buckets 140 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 140 / JSON 140 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 0 / JSON 0 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 140, 'unexpected': 0, 'flaky': 0, 'skipped': 0} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['mocked-mobile-360'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 140 / planned 140 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 0 / 0 |
| JUnit passed = passed + flaky | ok | JUnit 140 / 140 |
| JUnit holds exactly the requested project | ok | ['mocked-mobile-360'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### live

The reporter's own final lines, verbatim:

```
  1 skipped
  55 passed (2.5m)
```

JUnit: tests 56, passed 55, failures 0, errors 0, skipped 1. JSON (kept locally): 56 tests, buckets {'passed': 55, 'failed': 0, 'flaky': 0, 'skipped': 1, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 56 / buckets 56 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 55 / JSON 55 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 1 / JSON 1 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 55, 'unexpected': 0, 'flaky': 0, 'skipped': 1} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['live'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 56 / planned 56 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 1 / 1 |
| JUnit passed = passed + flaky | ok | JUnit 55 / 55 |
| JUnit holds exactly the requested project | ok | ['live'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### live-isolated

The reporter's own final lines, verbatim:

```
  2 passed (4.3s)
```

JUnit: tests 2, passed 2, failures 0, errors 0, skipped 0. JSON (kept locally): 2 tests, buckets {'passed': 2, 'failed': 0, 'flaky': 0, 'skipped': 0, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 2 / buckets 2 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 2 / JSON 2 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 0 / JSON 0 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 2, 'unexpected': 0, 'flaky': 0, 'skipped': 0} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['live-isolated'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 2 / planned 2 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 0 / 0 |
| JUnit passed = passed + flaky | ok | JUnit 2 / 2 |
| JUnit holds exactly the requested project | ok | ['live-isolated'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

## Skipped tests

| Project | Location | Test | Bucket | Reason |
|---|---|---|---|---|
| mocked-desktop | mocked/navigation-continuity.spec.ts:241 | the menu button is reachable and opens the menu | skipped | the full navigation is on the bar at this width |
| mocked-desktop | mocked/navigation-continuity.spec.ts:1013 | Escape closes the header menu and gives focus back to the menu button | skipped | there is no menu button at this width |
| live | live/detail-refresh.spec.ts:174 | a fixture in play keeps its running score under a running label across a return | skipped | no fixture is in play in the local database right now |

## Failures

None.

## Repository

- HEAD at start: `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`
- HEAD at end: `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`
- Branch: `main`
- origin/main: `a9e89d299ee6af19e6c25941151d2ae5a0997aa8` as of the last fetch, 2026-10-10T23:42:40Z
- Working tree: clean
- Working tree unchanged at the end: yes

## Servers under test

### frontend: http://localhost:3100

- PID 91426, started 2026-10-08T03:26:34Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3100 --strictPort`
- Checkout `<repo>` at `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend: http://127.0.0.1:8000

- PID 24525, started 2026-10-10T17:40:28Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Checkout `<repo>` at `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`: DIFFERENT; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:28Z', 'database': 'soccer_predictions'}
- Same process at the end: yes

Provider status at 2026-10-10T23:42:49.559028+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| match data | livescore | primary | True | 2026-10-10T23:36:05.047395+00:00 | 2026-10-10T21:09:25.183786+00:00 | - | False |
| match data | api_football | retained (free plan: current season restricted) | True | 2026-10-10T21:09:25.505724+00:00 | 2026-10-10T14:56:35.042058+00:00 | - | False |
| match data | thesportsdb | retained (v1 API, untested, no live scores) | True | 2026-10-05T21:39:12.435861+00:00 | 2026-10-10T14:56:35.321707+00:00 | http_400 | False |
| forecasts | gameforecast | primary | True | 2026-10-10T20:13:02.947179+00:00 | - | - | True |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | 2026-10-10T19:19:46.443539+00:00 | 2026-10-10T00:01:06.664583+00:00 | - |
| forecasts | 2026-10-10T06:48:54.547020+00:00 | 2026-10-10T20:13:02.948422+00:00 | allowance |
| live | 2026-10-10T23:42:07.047709+00:00 | 2026-10-10T21:09:25.512281+00:00 | - |
| recover | 2026-10-10T23:41:06.891190+00:00 | 2026-10-10T15:33:21.748006+00:00 | - |
| results | 2026-10-10T23:36:05.260206+00:00 | 2026-10-10T14:56:35.579242+00:00 | - |
| settle | 2026-10-10T23:40:06.514470+00:00 | - | - |

### frontend-isolated: http://localhost:3101

- PID 12765, started 2026-10-10T17:14:03Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3101 --strictPort --mode dev8001`
- Checkout `<repo>` at `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend-isolated: http://127.0.0.1:8001

- PID 24597, started 2026-10-10T17:40:30Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Checkout `<repo>` at `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `a9e89d299ee6af19e6c25941151d2ae5a0997aa8`: DIFFERENT; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:30Z', 'database': 'soccer_predictions_e2e'}
- Same process at the end: yes

Provider status at 2026-10-10T23:42:49.808559+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| forecasts | gameforecast | - | False | - | - | - | False |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | - | - | - |
| forecasts | - | - | - |
| live | - | - | - |
| recover | - | - | - |
| results | - | - | - |
| settle | - | - | - |

## Backend test database

- postgresql://localhost:5432/soccer_predictions_test (from conftest.py default); conftest.py reads TEST_DATABASE_URL: yes
- PostgreSQL: ok; Redis: ok

## Tools

| Tool | Version |
|---|---|
| node | v24.8.0 |
| npm | 11.6.0 |
| macos | 26.7.1 |
| playwright | 1.63.0 |
| chromium | 153.0.8010.12 (revision 1243) |
| backend python (venv311) | 3.11.9 |
| pytest | 7.4.3 |
| pytest-cov | 4.1.0 |
| pytest-asyncio | 0.21.1 |
| postgres image | postgres:15-alpine |
| redis image | redis:7-alpine |

## Commands

backend, in `<repo>/backend`, with PYTHONUNBUFFERED, TEST_DATABASE_URL set:

```
<repo>/backend/venv311/bin/python -m pytest -o addopts= -p no:cacheprovider -q -rfEs --junitxml=<repo>/.test-runs/2026-10-10T2342Z-a9e89d2/backend.junit.xml -o junit_suite_name=backend -o junit_family=xunit2 -o junit_logging=no
```

mocked-desktop, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-desktop --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T2342Z-a9e89d2/artifacts-mocked-desktop --reporter=list,json,junit
```

mocked-mobile, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T2342Z-a9e89d2/artifacts-mocked-mobile --reporter=list,json,junit
```

mocked-mobile-360, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile-360 --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T2342Z-a9e89d2/artifacts-mocked-mobile-360 --reporter=list,json,junit
```

live, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T2342Z-a9e89d2/artifacts-live --reporter=list,json,junit
```

live-isolated, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live-isolated --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T2342Z-a9e89d2/artifacts-live-isolated --reporter=list,json,junit
```

## Integrity

- Runner: `scripts/test_evidence.py`, SHA-256 `d7af93ea453b63ab4e066becadc48e8eabc7ba5286996003b3f9979278fcc33c`
- Concurrency guard at start: no other test run
- Lock acquired 2026-10-10T23:42:50Z; stale lock cleared: no
- Watcher: 112 sample(s) every 15 s; anomalies: 1
- Deny-list: 14 value(s) scanned, none found. Not scanned (shorter than 6 characters): SMTP_USER (backend/.env), hostname
- Published size: 495883 bytes

Scrub substitutions per file:

| File | ansi | repo-root | home | pytest-hostname | bearer-header | jwt | url-credentials | query-secret |
|---|---|---|---|---|---|---|---|---|
| backend.console-tail.txt | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| backend.junit.xml | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| playwright-live-isolated.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live-isolated.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-desktop.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-desktop.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile-360.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile-360.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| summary | 0 | 31 | 0 | 0 | 0 | 0 | 0 | 0 |

Raw files kept locally, with their SHA-256 before scrubbing:

| Published | Raw file | Raw SHA-256 |
|---|---|---|
| backend.console-tail.txt | .test-runs/2026-10-10T2342Z-a9e89d2/backend.console.log | f76983a71c94f01dfbd0ba97182e90f0d7bef2986c9ca61c258ddc89a7a33c25 |
| backend.junit.xml | .test-runs/2026-10-10T2342Z-a9e89d2/backend.junit.xml | a4f6fcbe0f8da5ee637332f48384861c00e71c47ff40b8dea64077960735e3b8 |
| playwright-live-isolated.console-tail.txt | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-live-isolated.console.log | cf572ee035c8eaa6ebd2825a66a78f180d0adc38714c94cfdcee1d0d610a84c5 |
| playwright-live-isolated.junit.xml | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-live-isolated.junit.xml | 47580abadde2fbd630338bc3c510167688968b34bfc1c0dc37faef8ecd7b54f5 |
| playwright-live.console-tail.txt | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-live.console.log | 580063a911d1ce391fd90a2e5b813fbbeea8c3a795502c92159381de20ccfb0d |
| playwright-live.junit.xml | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-live.junit.xml | 1950abca29998567806fcb4fcfc6aa17a15fb95ffde84f503325dfb67d590677 |
| playwright-mocked-desktop.console-tail.txt | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-mocked-desktop.console.log | abdee05f3a625a5bfa7f6a6bcfe5374b7974704c2dcb8055068beb59756aa8b3 |
| playwright-mocked-desktop.junit.xml | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-mocked-desktop.junit.xml | c6c027a4bec8f4530f3b68b8036dacf004b8d78befe0ef70a175f650ab2d8208 |
| playwright-mocked-mobile-360.console-tail.txt | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-mocked-mobile-360.console.log | 19c7ee0b73f4a0b2709a36a5a3a0ff2bb09820699507356fec9172a4137f2a78 |
| playwright-mocked-mobile-360.junit.xml | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-mocked-mobile-360.junit.xml | 3c1233926c872ee89f11ebd902dc7ab5211a839c94545248d8da38058ad7977f |
| playwright-mocked-mobile.console-tail.txt | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-mocked-mobile.console.log | bc2ed8d448bec0591c88eeb9353d53b2b25d2cb1be6e8d8aa5a71984d7c2f7b2 |
| playwright-mocked-mobile.junit.xml | .test-runs/2026-10-10T2342Z-a9e89d2/playwright-mocked-mobile.junit.xml | 4ffcc46d486db11a0ea22141ff23ed0d1242eb3ac4d33bb9ae89bf41717cffa1 |

## How to verify

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-10T2342Z-a9e89d2
```
