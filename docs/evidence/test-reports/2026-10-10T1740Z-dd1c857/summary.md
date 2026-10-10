# Test evidence 2026-10-10T1740Z-dd1c857

**FAIL**

- backend: exit 1, FAIL
- mocked-desktop: exit 0, PASS
- mocked-mobile: exit 0, PASS
- mocked-mobile-360: exit 0, PASS
- live: exit 0, PASS
- live-isolated: exit 0, PASS

## Run

- Run id: `2026-10-10T1740Z-dd1c857`
- Started 2026-10-10T17:40:47Z, finished 2026-10-10T18:09:37Z (UTC)

| Suite | Started (UTC) | Finished (UTC) | Duration (s) | Exit code |
|---|---|---|---|---|
| backend | 2026-10-10T17:40:47Z | 2026-10-10T17:41:37Z | 49.8 | 1 |
| mocked-desktop | 2026-10-10T17:41:37Z | 2026-10-10T17:52:12Z | 635.6 | 0 |
| mocked-mobile | 2026-10-10T17:52:12Z | 2026-10-10T18:04:08Z | 715.6 | 0 |
| mocked-mobile-360 | 2026-10-10T18:04:08Z | 2026-10-10T18:06:46Z | 158.3 | 0 |
| live | 2026-10-10T18:06:46Z | 2026-10-10T18:09:32Z | 165.5 | 0 |
| live-isolated | 2026-10-10T18:09:32Z | 2026-10-10T18:09:37Z | 5.6 | 0 |

## Results

| Suite | Exit | Verdict | Planned | Passed | Failed | Flaky | Skipped | Did not run | Interrupted | Errors | xfailed | xpassed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| backend | 1 | FAIL | - | 1682 | 3 | - | 0 | - | - | 0 | 0 | 0 |
| mocked-desktop | 0 | PASS | 453 | 451 | 0 | 0 | 2 | 0 | 0 | - | - | - |
| mocked-mobile | 0 | PASS | 453 | 453 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| mocked-mobile-360 | 0 | PASS | 140 | 140 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live | 0 | PASS | 56 | 56 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live-isolated | 0 | PASS | 2 | 2 | 0 | 0 | 0 | 0 | 0 | - | - | - |

### backend

The reporter's own final lines, verbatim:

```
3 failed, 1682 passed, 20 warnings in 48.73s
```

JUnit: 1685 testcases; passed or xpassed 1682, failed 3, errors 0, skipped 0, xfailed 0.

| Check | Result | Detail |
|---|---|---|
| pytest summary line present | ok | - |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit failed = pytest failed | ok | JUnit 3 / pytest 3 |
| JUnit errors = pytest errors | ok | JUnit 0 / pytest 0 |
| JUnit skipped = pytest skipped | ok | JUnit 0 / pytest 0 |
| JUnit xfailed = pytest xfailed | ok | JUnit 0 / pytest 0 |
| JUnit passed = pytest passed + xpassed | ok | JUnit 1682 / pytest 1682 |
| no skip says the test database or Redis is not reachable | ok | 0 such skip(s) |
| nothing deselected | ok | 0 deselected |
| at least one test ran | ok | 1685 test(s) |
| exit code agrees with the results | ok | exit 1, failed 3, errors 0, tests 1685 |
| not interrupted | ok | - |

### mocked-desktop

The reporter's own final lines, verbatim:

```
  2 skipped
  451 passed (10.6m)
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
  56 passed (2.8m)
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
  2 passed (5.3s)
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
| backend | - | tests.test_upcoming_fixtures::test_the_endpoint_names_the_next_fixtures_and_when_football_resumes | failure | assert False is True |
| backend | - | tests.test_upcoming_fixtures::test_the_endpoint_caps_the_list_but_not_the_date_football_resumes | failure | assert 0 == 3 |
| backend | - | tests.test_upcoming_fixtures::test_the_endpoint_names_the_competitions_its_answer_does_not_speak_for | failure | assert False is True |

## Repository

- HEAD at start: `dd1c857d21b82aa89337183cf38b2bdff54c1272`
- HEAD at end: `dd1c857d21b82aa89337183cf38b2bdff54c1272`
- Branch: `main`
- origin/main: `dd1c857d21b82aa89337183cf38b2bdff54c1272` as of the last fetch, 2026-10-10T17:40:14Z
- Working tree: clean
- Working tree unchanged at the end: yes

## Servers under test

### frontend: http://localhost:3100

- PID 91426, started 2026-10-08T03:26:34Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3100 --strictPort`
- Checkout `<repo>` at `dd1c857d21b82aa89337183cf38b2bdff54c1272`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend: http://127.0.0.1:8000

- PID 24525, started 2026-10-10T17:40:28Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Checkout `<repo>` at `dd1c857d21b82aa89337183cf38b2bdff54c1272`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `dd1c857d21b82aa89337183cf38b2bdff54c1272`: match; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:28Z', 'database': 'soccer_predictions'}
- Same process at the end: yes

Provider status at 2026-10-10T17:40:46.500489+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| match data | livescore | primary | True | 2026-10-10T17:35:32.385598+00:00 | 2026-10-10T17:37:49.185298+00:00 | timeout | False |
| match data | api_football | retained (free plan: current season restricted) | True | 2026-10-10T17:37:49.421429+00:00 | 2026-10-10T14:56:35.042058+00:00 | - | False |
| match data | thesportsdb | retained (v1 API, untested, no live scores) | True | 2026-10-05T21:39:12.435861+00:00 | 2026-10-10T14:56:35.321707+00:00 | http_400 | False |
| forecasts | gameforecast | primary | True | 2026-10-10T14:12:03.707729+00:00 | - | - | False |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | 2026-10-10T13:18:44.352757+00:00 | 2026-10-10T00:01:06.664583+00:00 | - |
| forecasts | 2026-10-10T06:48:54.547020+00:00 | 2026-10-10T14:12:03.709103+00:00 | timeout |
| live | 2026-10-10T17:35:32.802889+00:00 | 2026-10-10T17:37:49.508636+00:00 | timeout |
| recover | 2026-10-10T17:35:33.585541+00:00 | 2026-10-10T15:33:21.748006+00:00 | - |
| results | 2026-10-10T17:30:25.059824+00:00 | 2026-10-10T14:56:35.579242+00:00 | - |
| settle | 2026-10-10T17:32:29.084007+00:00 | - | - |

### frontend-isolated: http://localhost:3101

- PID 12765, started 2026-10-10T17:14:03Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3101 --strictPort --mode dev8001`
- Checkout `<repo>` at `dd1c857d21b82aa89337183cf38b2bdff54c1272`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend-isolated: http://127.0.0.1:8001

- PID 24597, started 2026-10-10T17:40:30Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Checkout `<repo>` at `dd1c857d21b82aa89337183cf38b2bdff54c1272`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`, on disk now `cd47cdef6213fe573915fbe41a7cdc66754fe5c73854848174a11b815abe199c`: match; commit served `dd1c857d21b82aa89337183cf38b2bdff54c1272`, checkout HEAD `dd1c857d21b82aa89337183cf38b2bdff54c1272`: match; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-10T17:40:30Z', 'database': 'soccer_predictions_e2e'}
- Same process at the end: yes

Provider status at 2026-10-10T17:40:46.818009+00:00 (fields kept: status, times, error kind):

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
<repo>/backend/venv311/bin/python -m pytest -o addopts= -p no:cacheprovider -q -rfEs --junitxml=<repo>/.test-runs/2026-10-10T1740Z-dd1c857/backend.junit.xml -o junit_suite_name=backend -o junit_family=xunit2 -o junit_logging=no
```

mocked-desktop, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-desktop --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1740Z-dd1c857/artifacts-mocked-desktop --reporter=list,json,junit
```

mocked-mobile, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1740Z-dd1c857/artifacts-mocked-mobile --reporter=list,json,junit
```

mocked-mobile-360, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile-360 --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1740Z-dd1c857/artifacts-mocked-mobile-360 --reporter=list,json,junit
```

live, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1740Z-dd1c857/artifacts-live --reporter=list,json,junit
```

live-isolated, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live-isolated --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-10T1740Z-dd1c857/artifacts-live-isolated --reporter=list,json,junit
```

## Integrity

- Runner: `scripts/test_evidence.py`, SHA-256 `d7af93ea453b63ab4e066becadc48e8eabc7ba5286996003b3f9979278fcc33c`
- Concurrency guard at start: no other test run
- Lock acquired 2026-10-10T17:40:47Z; stale lock cleared: no
- Watcher: 113 sample(s) every 15 s; anomalies: none
- Deny-list: 14 value(s) scanned, none found. Not scanned (shorter than 6 characters): SMTP_USER (backend/.env), hostname
- Published size: 497635 bytes

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
| backend.console-tail.txt | .test-runs/2026-10-10T1740Z-dd1c857/backend.console.log | 9548c843a8d6ade48f4857152ad146419ea839d1ab427a0ce732c64431af7da1 |
| backend.junit.xml | .test-runs/2026-10-10T1740Z-dd1c857/backend.junit.xml | 0e92181d8e72a812bde309b1266ce2cdfc07c789fef3492cc7d7d41929d25244 |
| playwright-live-isolated.console-tail.txt | .test-runs/2026-10-10T1740Z-dd1c857/playwright-live-isolated.console.log | ebad13e2ca18ad70eb6b92376130dc66d869683c28b4e3a9a9f6e112d8459be1 |
| playwright-live-isolated.junit.xml | .test-runs/2026-10-10T1740Z-dd1c857/playwright-live-isolated.junit.xml | c209644199dcff3fad5653a1db7dde4a2a46b75fa644b72db4347e86cafacc27 |
| playwright-live.console-tail.txt | .test-runs/2026-10-10T1740Z-dd1c857/playwright-live.console.log | c2c03ec4db9c678a02fbd560d6519f0f3c948d28d863e262979a8e77d5ec2921 |
| playwright-live.junit.xml | .test-runs/2026-10-10T1740Z-dd1c857/playwright-live.junit.xml | 16959217ad5271f03f886ef5a0eb4a560cf30eebabf5999745ec7f341719e4d3 |
| playwright-mocked-desktop.console-tail.txt | .test-runs/2026-10-10T1740Z-dd1c857/playwright-mocked-desktop.console.log | 18a4405da59bd6f32e2f4feb46f8cdc9a9c2fed1cedc6728659fec7e5b994436 |
| playwright-mocked-desktop.junit.xml | .test-runs/2026-10-10T1740Z-dd1c857/playwright-mocked-desktop.junit.xml | 0e63c8cf0a5a988dcbf41e81c21f13597cb0de507d5410d9397804daf3df3fc6 |
| playwright-mocked-mobile-360.console-tail.txt | .test-runs/2026-10-10T1740Z-dd1c857/playwright-mocked-mobile-360.console.log | 7bce12d533b0ff6b563f90035d00f1b964743ab82453d54fd0cc2f44c3832767 |
| playwright-mocked-mobile-360.junit.xml | .test-runs/2026-10-10T1740Z-dd1c857/playwright-mocked-mobile-360.junit.xml | 067d0ab0b368ce959afe3dc4764a6296aaf88941f8ce458e8c254d02af82c584 |
| playwright-mocked-mobile.console-tail.txt | .test-runs/2026-10-10T1740Z-dd1c857/playwright-mocked-mobile.console.log | 358debdb8f5dcf7371f3bedb94cf4749c2bc55f6758295c2443fe6b1a5ac0f66 |
| playwright-mocked-mobile.junit.xml | .test-runs/2026-10-10T1740Z-dd1c857/playwright-mocked-mobile.junit.xml | a53ed480fe36a7e3eb1822f1a5f69b4241332c9fa11794a5ac354c5f4cf715f9 |

## How to verify

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-10T1740Z-dd1c857
```
