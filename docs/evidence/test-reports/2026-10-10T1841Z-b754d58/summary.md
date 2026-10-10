# Test evidence 2026-10-10T1841Z-b754d58

**FAIL**

- backend: exit 0, PASS
- mocked-desktop: exit 1, FAIL
- mocked-mobile: exit 0, PASS
- mocked-mobile-360: exit 0, PASS
- live: exit 0, PASS
- live-isolated: exit 0, PASS

## Run

- Run id: `2026-10-10T1841Z-b754d58`
- Started 2026-10-10T18:41:25Z, finished 2026-10-10T19:10:18Z (UTC)

| Suite | Started (UTC) | Finished (UTC) | Duration (s) | Exit code |
|---|---|---|---|---|
| backend | 2026-10-10T18:41:25Z | 2026-10-10T18:42:16Z | 51.1 | 0 |
| mocked-desktop | 2026-10-10T18:42:16Z | 2026-10-10T18:53:04Z | 647.6 | 1 |
| mocked-mobile | 2026-10-10T18:53:04Z | 2026-10-10T19:04:53Z | 709.5 | 0 |
| mocked-mobile-360 | 2026-10-10T19:04:53Z | 2026-10-10T19:07:31Z | 157.6 | 0 |
| live | 2026-10-10T19:07:31Z | 2026-10-10T19:10:13Z | 162.0 | 0 |
| live-isolated | 2026-10-10T19:10:13Z | 2026-10-10T19:10:18Z | 4.7 | 0 |

## Results

| Suite | Exit | Verdict | Planned | Passed | Failed | Flaky | Skipped | Did not run | Interrupted | Errors | xfailed | xpassed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| backend | 0 | PASS | - | 1685 | 0 | - | 0 | - | - | 0 | 0 | 0 |
| mocked-desktop | 1 | FAIL | 453 | 450 | 1 | 0 | 2 | 0 | 0 | - | - | - |
| mocked-mobile | 0 | PASS | 453 | 453 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| mocked-mobile-360 | 0 | PASS | 140 | 140 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live | 0 | PASS | 56 | 56 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live-isolated | 0 | PASS | 2 | 2 | 0 | 0 | 0 | 0 | 0 | - | - | - |

### backend

The reporter's own final lines, verbatim:

```
1685 passed, 20 warnings in 50.04s
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
  1 failed
    [mocked-desktop] › e2e/mocked/expert-localisation.spec.ts:392:3 › an unscored accuracy and an unclaimed conviction are sentences, not zeros, in fr 
  2 skipped
  450 passed (10.8m)
```

JUnit: tests 453, passed 450, failures 1, errors 0, skipped 2. JSON (kept locally): 453 tests, buckets {'passed': 450, 'failed': 1, 'flaky': 0, 'skipped': 2, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 453 / buckets 453 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 450 / JSON 450 |
| human failed = JSON | ok | human 1 / JSON 1 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 2 / JSON 2 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 450, 'unexpected': 1, 'flaky': 0, 'skipped': 2} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['mocked-desktop'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 453 / planned 453 |
| JUnit failures + errors = failed | ok | JUnit 1 / failed 1 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 2 / 2 |
| JUnit passed = passed + flaky | ok | JUnit 450 / 450 |
| JUnit holds exactly the requested project | ok | ['mocked-desktop'] |
| exit code agrees with the results | ok | exit 1, failed 1, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### mocked-mobile

The reporter's own final lines, verbatim:

```
  453 passed (11.8m)
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
  56 passed (2.7m)
```

JUnit: tests 56, passed 56, failures 0, errors 0, skipped 0. JSON (kept locally): 56 tests, buckets {'passed': 56, 'failed': 0, 'flaky': 0, 'skipped': 0, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 56 / buckets 56 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 56 / JSON 56 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 0 / JSON 0 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 56, 'unexpected': 0, 'flaky': 0, 'skipped': 0} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['live'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 56 / planned 56 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 0 / 0 |
| JUnit passed = passed + flaky | ok | JUnit 56 / 56 |
| JUnit holds exactly the requested project | ok | ['live'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### live-isolated

The reporter's own final lines, verbatim:

```
  2 passed (4.4s)
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

## Failures

| Project | Location | Test | Kind | First line of the error |
|---|---|---|---|---|
| mocked-desktop | mocked/expert-localisation.spec.ts:392 | an unscored accuracy and an unclaimed conviction are sentences, not zeros, in fr | failed | Error: expect(locator).toContainText(expected) failed |

## Repository

- HEAD at start: `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`
- HEAD at end: `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`
- Branch: `main`
- origin/main: `b754d58d13a37dc461813e0a233a1d3ecf3bac1e` as of the last fetch, 2026-10-10T18:41:12Z
- Working tree: clean
- Working tree unchanged at the end: yes

## Servers under test

### frontend: http://localhost:3100

- PID 91426, started 2026-10-08T03:26:34Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3100 --strictPort`
- Checkout `<repo>` at `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend: http://127.0.0.1:8000

- PID 24525, started 2026-10-10T17:40:28Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Checkout `<repo>` at `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`: DIFFERENT; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:28Z', 'database': 'soccer_predictions'}
- Same process at the end: yes

Provider status at 2026-10-10T18:41:24.734514+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| match data | livescore | primary | True | 2026-10-10T18:40:34.602650+00:00 | 2026-10-10T18:37:31.227698+00:00 | - | False |
| match data | api_football | retained (free plan: current season restricted) | True | 2026-10-10T18:37:31.400427+00:00 | 2026-10-10T14:56:35.042058+00:00 | - | False |
| match data | thesportsdb | retained (v1 API, untested, no live scores) | True | 2026-10-05T21:39:12.435861+00:00 | 2026-10-10T14:56:35.321707+00:00 | http_400 | False |
| forecasts | gameforecast | primary | True | 2026-10-10T14:12:03.707729+00:00 | - | - | False |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | 2026-10-10T13:18:44.352757+00:00 | 2026-10-10T00:01:06.664583+00:00 | - |
| forecasts | 2026-10-10T06:48:54.547020+00:00 | 2026-10-10T14:12:03.709103+00:00 | timeout |
| live | 2026-10-10T18:40:34.814669+00:00 | 2026-10-10T18:35:15.595723+00:00 | - |
| recover | 2026-10-10T18:37:32.183736+00:00 | 2026-10-10T15:33:21.748006+00:00 | - |
| results | 2026-10-10T18:31:55.788706+00:00 | 2026-10-10T14:56:35.579242+00:00 | - |
| settle | 2026-10-10T18:35:16.072594+00:00 | - | - |

### frontend-isolated: http://localhost:3101

- PID 12765, started 2026-10-10T17:14:03Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3101 --strictPort --mode dev8001`
- Checkout `<repo>` at `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend-isolated: http://127.0.0.1:8001

- PID 24597, started 2026-10-10T17:40:30Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Checkout `<repo>` at `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `b754d58d13a37dc461813e0a233a1d3ecf3bac1e`: DIFFERENT; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:30Z', 'database': 'soccer_predictions_e2e'}
- Same process at the end: yes

Provider status at 2026-10-10T18:41:24.988087+00:00 (fields kept: status, times, error kind):

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
<repo>/backend/venv311/bin/python -m pytest -o addopts= -p no:cacheprovider -q -rfEs --junitxml=<repo>/.test-runs/2026-10-10T1841Z-b754d58/backend.junit.xml -o junit_suite_name=backend -o junit_family=xunit2 -o junit_logging=no
```

mocked-desktop, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-desktop --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1841Z-b754d58/artifacts-mocked-desktop --reporter=list,json,junit
```

mocked-mobile, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1841Z-b754d58/artifacts-mocked-mobile --reporter=list,json,junit
```

mocked-mobile-360, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile-360 --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1841Z-b754d58/artifacts-mocked-mobile-360 --reporter=list,json,junit
```

live, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1841Z-b754d58/artifacts-live --reporter=list,json,junit
```

live-isolated, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live-isolated --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1841Z-b754d58/artifacts-live-isolated --reporter=list,json,junit
```

## Integrity

- Runner: `scripts/test_evidence.py`, SHA-256 `d7af93ea453b63ab4e066becadc48e8eabc7ba5286996003b3f9979278fcc33c`
- Concurrency guard at start: no other test run
- Lock acquired 2026-10-10T18:41:25Z; stale lock cleared: no
- Watcher: 113 sample(s) every 15 s; anomalies: none
- Deny-list: 14 value(s) scanned, none found. Not scanned (shorter than 6 characters): SMTP_USER (backend/.env), hostname
- Published size: 496185 bytes

Scrub substitutions per file:

| File | ansi | repo-root | home | pytest-hostname | bearer-header | jwt | url-credentials | query-secret |
|---|---|---|---|---|---|---|---|---|
| backend.console-tail.txt | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| backend.junit.xml | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| playwright-live-isolated.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live-isolated.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-desktop.console-tail.txt | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-desktop.junit.xml | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile-360.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile-360.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| summary | 0 | 31 | 0 | 0 | 0 | 0 | 0 | 0 |

Raw files kept locally, with their SHA-256 before scrubbing:

| Published | Raw file | Raw SHA-256 |
|---|---|---|
| backend.console-tail.txt | .test-runs/2026-10-10T1841Z-b754d58/backend.console.log | 1419661dca03e695dcb88acb03e5a25b07eb8398962a1ec6b5a502855a95ff54 |
| backend.junit.xml | .test-runs/2026-10-10T1841Z-b754d58/backend.junit.xml | 4b87edc986d17ebd990c9874cc72aea5bbf3bfefd96e580a3b6e4399a782b1bb |
| playwright-live-isolated.console-tail.txt | .test-runs/2026-10-10T1841Z-b754d58/playwright-live-isolated.console.log | 7f38af29ecb9fe84d098a842aef32214412a3f1221f4495e2398108ce4a29264 |
| playwright-live-isolated.junit.xml | .test-runs/2026-10-10T1841Z-b754d58/playwright-live-isolated.junit.xml | 1b57c40abf734168bd16cd0e4137812485193c7748faa7cff692b458853d772a |
| playwright-live.console-tail.txt | .test-runs/2026-10-10T1841Z-b754d58/playwright-live.console.log | 65a0c2685c0e9e961984b9614f5c8c9c764d8d6ab69a88a620794f52ee422fdf |
| playwright-live.junit.xml | .test-runs/2026-10-10T1841Z-b754d58/playwright-live.junit.xml | ef1e1e6350c6b9ea039d5cfba05450b97397301a51cb45e9df1337278193bc9e |
| playwright-mocked-desktop.console-tail.txt | .test-runs/2026-10-10T1841Z-b754d58/playwright-mocked-desktop.console.log | 67f4ace4a92935996af0009b0efdd80f864a0a94b8ba359ab736a7e889603ffe |
| playwright-mocked-desktop.junit.xml | .test-runs/2026-10-10T1841Z-b754d58/playwright-mocked-desktop.junit.xml | b5a20133f177e5002c37643faa0a11fc099343f57acc55383bfe39a9bfd4ce3e |
| playwright-mocked-mobile-360.console-tail.txt | .test-runs/2026-10-10T1841Z-b754d58/playwright-mocked-mobile-360.console.log | c2e6c308716d10081fb1475527697b0394140f4dbe5b285e145bd5cd04880a20 |
| playwright-mocked-mobile-360.junit.xml | .test-runs/2026-10-10T1841Z-b754d58/playwright-mocked-mobile-360.junit.xml | 5b090318dec55db447d8b7b71017ea37c8793112a41ab78759b2c83752810ba8 |
| playwright-mocked-mobile.console-tail.txt | .test-runs/2026-10-10T1841Z-b754d58/playwright-mocked-mobile.console.log | a6f14261779c814ca1c8244bdd4c0da41b2b429404f5c1cff8ca39efa442d433 |
| playwright-mocked-mobile.junit.xml | .test-runs/2026-10-10T1841Z-b754d58/playwright-mocked-mobile.junit.xml | f556780f16391868e5f224206afe4a2dc4c29ad67c7300210078224dbc14abd4 |

## How to verify

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-10T1841Z-b754d58
```
