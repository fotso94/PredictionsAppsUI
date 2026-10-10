# Test evidence 2026-10-10T1811Z-37630ef

**CONTAMINATED**

- backend: exit 0, PASS
- mocked-desktop: exit 0, PASS
- mocked-mobile: exit 0, PASS
- mocked-mobile-360: exit 0, PASS
- live: exit 0, PASS
- live-isolated: exit 0, PASS

Contamination:
- 2026-10-10T18:12:18Z during mocked-desktop: foreign_runner, pid 40471 (pytest: zsh 'bin/pytest')
- 2026-10-10T18:12:18Z during mocked-desktop: foreign_runner, pid 40473 (pytest: Python 'bin/pytest')

## Run

- Run id: `2026-10-10T1811Z-37630ef`
- Started 2026-10-10T18:11:17Z, finished 2026-10-10T18:40:07Z (UTC)

| Suite | Started (UTC) | Finished (UTC) | Duration (s) | Exit code |
|---|---|---|---|---|
| backend | 2026-10-10T18:11:17Z | 2026-10-10T18:12:05Z | 47.9 | 0 |
| mocked-desktop | 2026-10-10T18:12:05Z | 2026-10-10T18:22:47Z | 642.3 | 0 |
| mocked-mobile | 2026-10-10T18:22:47Z | 2026-10-10T18:34:41Z | 713.6 | 0 |
| mocked-mobile-360 | 2026-10-10T18:34:41Z | 2026-10-10T18:37:20Z | 158.6 | 0 |
| live | 2026-10-10T18:37:20Z | 2026-10-10T18:40:02Z | 162.5 | 0 |
| live-isolated | 2026-10-10T18:40:02Z | 2026-10-10T18:40:07Z | 4.9 | 0 |

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
1685 passed, 20 warnings in 46.70s
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
  451 passed (10.7m)
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
  55 passed (2.7m)
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
  2 passed (4.6s)
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

- HEAD at start: `37630ef37e701079ebc686a97e020107a18585fd`
- HEAD at end: `37630ef37e701079ebc686a97e020107a18585fd`
- Branch: `main`
- origin/main: `37630ef37e701079ebc686a97e020107a18585fd` as of the last fetch, 2026-10-10T18:11:05Z
- Working tree: clean
- Working tree unchanged at the end: yes

## Servers under test

### frontend: http://localhost:3100

- PID 91426, started 2026-10-08T03:26:34Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3100 --strictPort`
- Checkout `<repo>` at `37630ef37e701079ebc686a97e020107a18585fd`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend: http://127.0.0.1:8000

- PID 24525, started 2026-10-10T17:40:28Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Checkout `<repo>` at `37630ef37e701079ebc686a97e020107a18585fd`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `37630ef37e701079ebc686a97e020107a18585fd`: DIFFERENT; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:28Z', 'database': 'soccer_predictions'}
- Same process at the end: yes

Provider status at 2026-10-10T18:11:16.824199+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| match data | livescore | primary | True | 2026-10-10T18:04:20.871399+00:00 | 2026-10-10T18:06:36.433295+00:00 | timeout | False |
| match data | api_football | retained (free plan: current season restricted) | True | 2026-10-10T18:06:36.683367+00:00 | 2026-10-10T14:56:35.042058+00:00 | - | False |
| match data | thesportsdb | retained (v1 API, untested, no live scores) | True | 2026-10-05T21:39:12.435861+00:00 | 2026-10-10T14:56:35.321707+00:00 | http_400 | False |
| forecasts | gameforecast | primary | True | 2026-10-10T14:12:03.707729+00:00 | - | - | False |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | 2026-10-10T13:18:44.352757+00:00 | 2026-10-10T00:01:06.664583+00:00 | - |
| forecasts | 2026-10-10T06:48:54.547020+00:00 | 2026-10-10T14:12:03.709103+00:00 | timeout |
| live | 2026-10-10T18:04:20.926713+00:00 | 2026-10-10T18:06:36.719600+00:00 | timeout |
| recover | 2026-10-10T18:06:37.243932+00:00 | 2026-10-10T15:33:21.748006+00:00 | - |
| results | 2026-10-10T18:01:17.404575+00:00 | 2026-10-10T14:56:35.579242+00:00 | - |
| settle | 2026-10-10T18:03:18.845762+00:00 | - | - |

### frontend-isolated: http://localhost:3101

- PID 12765, started 2026-10-10T17:14:03Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3101 --strictPort --mode dev8001`
- Checkout `<repo>` at `37630ef37e701079ebc686a97e020107a18585fd`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend-isolated: http://127.0.0.1:8001

- PID 24597, started 2026-10-10T17:40:30Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Checkout `<repo>` at `37630ef37e701079ebc686a97e020107a18585fd`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `37630ef37e701079ebc686a97e020107a18585fd`: DIFFERENT; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:30Z', 'database': 'soccer_predictions_e2e'}
- Same process at the end: yes

Provider status at 2026-10-10T18:11:17.099386+00:00 (fields kept: status, times, error kind):

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
<repo>/backend/venv311/bin/python -m pytest -o addopts= -p no:cacheprovider -q -rfEs --junitxml=<repo>/.test-runs/2026-10-10T1811Z-37630ef/backend.junit.xml -o junit_suite_name=backend -o junit_family=xunit2 -o junit_logging=no
```

mocked-desktop, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-desktop --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1811Z-37630ef/artifacts-mocked-desktop --reporter=list,json,junit
```

mocked-mobile, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1811Z-37630ef/artifacts-mocked-mobile --reporter=list,json,junit
```

mocked-mobile-360, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile-360 --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1811Z-37630ef/artifacts-mocked-mobile-360 --reporter=list,json,junit
```

live, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1811Z-37630ef/artifacts-live --reporter=list,json,junit
```

live-isolated, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live-isolated --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1811Z-37630ef/artifacts-live-isolated --reporter=list,json,junit
```

## Integrity

- Runner: `scripts/test_evidence.py`, SHA-256 `d7af93ea453b63ab4e066becadc48e8eabc7ba5286996003b3f9979278fcc33c`
- Concurrency guard at start: no other test run
- Lock acquired 2026-10-10T18:11:17Z; stale lock cleared: no
- Watcher: 113 sample(s) every 15 s; anomalies: 2
- Deny-list: 14 value(s) scanned, none found. Not scanned (shorter than 6 characters): SMTP_USER (backend/.env), hostname
- Published size: 495896 bytes

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
| backend.console-tail.txt | .test-runs/2026-10-10T1811Z-37630ef/backend.console.log | a358fb35687b50a23d8e61cd1b72b3200383fa868232d55e659e51751417c344 |
| backend.junit.xml | .test-runs/2026-10-10T1811Z-37630ef/backend.junit.xml | 6797a770003fe4ff74cc913865953d04ecf9c127ce6dfa9fab8e7d33a336dc7d |
| playwright-live-isolated.console-tail.txt | .test-runs/2026-10-10T1811Z-37630ef/playwright-live-isolated.console.log | d4ad59641024f7018be29a6eecbbf045e752c4bef1c81c4f9d4b11f94815cbc2 |
| playwright-live-isolated.junit.xml | .test-runs/2026-10-10T1811Z-37630ef/playwright-live-isolated.junit.xml | 5faefddc54e881a5a9d84f114454fea69aef83c8a9a97c502e3c51d960d4b11c |
| playwright-live.console-tail.txt | .test-runs/2026-10-10T1811Z-37630ef/playwright-live.console.log | ed6f4f23e231878c6a16f48cf8fdee002b5451c2ec5a460aad19eb4285c642b4 |
| playwright-live.junit.xml | .test-runs/2026-10-10T1811Z-37630ef/playwright-live.junit.xml | df41be8d9ce0c878b4bcc0f6a26e182446b344b477e52dd56308f93fa062e5c7 |
| playwright-mocked-desktop.console-tail.txt | .test-runs/2026-10-10T1811Z-37630ef/playwright-mocked-desktop.console.log | 5e3e2c486060e2cfee30fe56d3537ed0ecfb24e587bd43f6c592da0d9fc5d3e5 |
| playwright-mocked-desktop.junit.xml | .test-runs/2026-10-10T1811Z-37630ef/playwright-mocked-desktop.junit.xml | 0ee104e63b460c56879f1641f4ef3abff1d6e6b768e78fa0a7b4d124c4207b90 |
| playwright-mocked-mobile-360.console-tail.txt | .test-runs/2026-10-10T1811Z-37630ef/playwright-mocked-mobile-360.console.log | 5266f07a6fe017e9553183fa61176f7e73e5ff2915cf705aa3fdc378430d07c4 |
| playwright-mocked-mobile-360.junit.xml | .test-runs/2026-10-10T1811Z-37630ef/playwright-mocked-mobile-360.junit.xml | 69094adceb2263a9034eec3c9005e43e285f9004de912d41567b6d3c34565881 |
| playwright-mocked-mobile.console-tail.txt | .test-runs/2026-10-10T1811Z-37630ef/playwright-mocked-mobile.console.log | a94a141bd71973d8cfa9e6f9360b7c94f07163354edd9e213f02aa8c2fa8b8e6 |
| playwright-mocked-mobile.junit.xml | .test-runs/2026-10-10T1811Z-37630ef/playwright-mocked-mobile.junit.xml | 82eea3a5121870766952468d77ddf288fe11688c063f4d6cafcda3cfc1b4c580 |

## How to verify

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-10T1811Z-37630ef
```
