# Test evidence 2026-10-08T0326Z-586b21a

**PASS**

- backend: exit 0, PASS
- mocked-desktop: exit 0, PASS
- mocked-mobile: exit 0, PASS
- mocked-mobile-360: exit 0, PASS
- live: exit 0, PASS
- live-isolated: exit 0, PASS

## Run

- Run id: `2026-10-08T0326Z-586b21a`
- Started 2026-10-08T03:26:46Z, finished 2026-10-08T03:54:45Z (UTC)

| Suite | Started (UTC) | Finished (UTC) | Duration (s) | Exit code |
|---|---|---|---|---|
| backend | 2026-10-08T03:26:46Z | 2026-10-08T03:27:35Z | 49.2 | 0 |
| mocked-desktop | 2026-10-08T03:27:35Z | 2026-10-08T03:38:05Z | 630.1 | 0 |
| mocked-mobile | 2026-10-08T03:38:05Z | 2026-10-08T03:49:54Z | 709.0 | 0 |
| mocked-mobile-360 | 2026-10-08T03:49:54Z | 2026-10-08T03:52:31Z | 157.3 | 0 |
| live | 2026-10-08T03:52:31Z | 2026-10-08T03:54:40Z | 129.3 | 0 |
| live-isolated | 2026-10-08T03:54:40Z | 2026-10-08T03:54:45Z | 4.8 | 0 |

## Results

| Suite | Exit | Verdict | Planned | Passed | Failed | Flaky | Skipped | Did not run | Interrupted | Errors | xfailed | xpassed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| backend | 0 | PASS | - | 1681 | 0 | - | 0 | - | - | 0 | 0 | 0 |
| mocked-desktop | 0 | PASS | 453 | 451 | 0 | 0 | 2 | 0 | 0 | - | - | - |
| mocked-mobile | 0 | PASS | 453 | 453 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| mocked-mobile-360 | 0 | PASS | 140 | 140 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live | 0 | PASS | 56 | 47 | 0 | 0 | 9 | 0 | 0 | - | - | - |
| live-isolated | 0 | PASS | 2 | 2 | 0 | 0 | 0 | 0 | 0 | - | - | - |

### backend

The reporter's own final lines, verbatim:

```
1681 passed, 20 warnings in 48.08s
```

JUnit: 1681 testcases; passed or xpassed 1681, failed 0, errors 0, skipped 0, xfailed 0.

| Check | Result | Detail |
|---|---|---|
| pytest summary line present | ok | - |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit failed = pytest failed | ok | JUnit 0 / pytest 0 |
| JUnit errors = pytest errors | ok | JUnit 0 / pytest 0 |
| JUnit skipped = pytest skipped | ok | JUnit 0 / pytest 0 |
| JUnit xfailed = pytest xfailed | ok | JUnit 0 / pytest 0 |
| JUnit passed = pytest passed + xpassed | ok | JUnit 1681 / pytest 1681 |
| no skip says the test database or Redis is not reachable | ok | 0 such skip(s) |
| nothing deselected | ok | 0 deselected |
| at least one test ran | ok | 1681 test(s) |
| exit code agrees with the results | ok | exit 0, failed 0, errors 0, tests 1681 |
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
  9 skipped
  47 passed (2.2m)
```

JUnit: tests 56, passed 47, failures 0, errors 0, skipped 9. JSON (kept locally): 56 tests, buckets {'passed': 47, 'failed': 0, 'flaky': 0, 'skipped': 9, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 56 / buckets 56 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 47 / JSON 47 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 9 / JSON 9 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 47, 'unexpected': 0, 'flaky': 0, 'skipped': 9} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['live'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 56 / planned 56 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 9 / 9 |
| JUnit passed = passed + flaky | ok | JUnit 47 / 47 |
| JUnit holds exactly the requested project | ok | ['live'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### live-isolated

The reporter's own final lines, verbatim:

```
  2 passed (4.5s)
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
| live | live/detail-refresh.spec.ts:110 | coming back to a match page reads it once, from stored data, and spends nothing | skipped | the local database holds no fixture for today |
| live | live/detail-refresh.spec.ts:174 | a fixture in play keeps its running score under a running label across a return | skipped | no fixture is in play in the local database right now |
| live | live/journey-proof.spec.ts:443 | LIVE: the personal journey, end to end, at 360px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/journey-proof.spec.ts:443 | LIVE: the personal journey, end to end, at 390px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/journey-proof.spec.ts:443 | LIVE: the personal journey, end to end, at 1440px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/real-data.spec.ts:64 | a stored forecast renders with the same numbers the API serves | skipped | no match with a 1X2 forecast in the local database today |
| live | live/real-data.spec.ts:81 | three distinct forecast timestamps reach the API | skipped | no forecast in the local database today |
| live | live/return-journey.spec.ts:174 | a saved match that has been played shows its result in the feed | skipped | no finished fixture carrying a result in the local database |
| live | live/return-journey.spec.ts:202 | the results group is reachable from the top of the feed without scrolling for it | skipped | no finished fixture carrying a result in the local database |

## Failures

None.

## Repository

- HEAD at start: `586b21a1551b2bea04db329f73f2db718477e650`
- HEAD at end: `586b21a1551b2bea04db329f73f2db718477e650`
- Branch: `main`
- origin/main: `e05cf10ceac38f5e7351d3b0bb4132c0c575d076` as of the last fetch, 2026-10-08T03:26:21Z
- Working tree: clean
- Working tree unchanged at the end: yes

## Servers under test

### frontend: http://localhost:3100

- PID 91426, started 2026-10-08T03:26:34Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3100 --strictPort`
- Checkout `<repo>` at `586b21a1551b2bea04db329f73f2db718477e650`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend: http://127.0.0.1:8000

- PID 91353, started 2026-10-08T03:26:33Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Checkout `<repo>` at `586b21a1551b2bea04db329f73f2db718477e650`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `a1cd7cbb95f1e29bebb3377ee0dc4c4eb9b301ee67026bdf3db67017db08f7b1`, on disk now `a1cd7cbb95f1e29bebb3377ee0dc4c4eb9b301ee67026bdf3db67017db08f7b1`: match; commit served `586b21a1551b2bea04db329f73f2db718477e650`, checkout HEAD `586b21a1551b2bea04db329f73f2db718477e650`: match; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-08T03:26:33Z', 'database': 'soccer_predictions'}
- Same process at the end: yes

Provider status at 2026-10-08T03:26:45.215190+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| match data | livescore | primary | True | 2026-10-02T14:53:28.028159+00:00 | 2026-10-08T03:26:37.788766+00:00 | http_401 | True |
| match data | api_football | retained (free plan: current season restricted) | True | 2026-10-08T03:26:38.288026+00:00 | 2026-10-08T02:55:43.168677+00:00 | - | False |
| match data | thesportsdb | retained (v1 API, untested, no live scores) | True | 2026-10-05T21:39:12.435861+00:00 | 2026-10-08T02:55:43.339051+00:00 | http_400 | False |
| forecasts | gameforecast | primary | True | 2026-10-08T02:56:00.538284+00:00 | - | - | False |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | 2026-10-02T13:07:44.765961+00:00 | 2026-10-08T02:55:43.350884+00:00 | http_400 |
| forecasts | 2026-10-07T01:04:55.692572+00:00 | 2026-10-08T02:56:00.539005+00:00 | connection |
| live | 2026-10-08T03:25:29.360402+00:00 | 2026-10-07T01:04:46.299217+00:00 | - |
| recover | 2026-10-08T03:26:39.248311+00:00 | 2026-10-05T02:53:20.858585+00:00 | - |
| results | 2026-10-02T14:53:28.332818+00:00 | 2026-10-08T02:55:44.019420+00:00 | connection |
| settle | 2026-10-08T03:26:39.264715+00:00 | - | - |

### frontend-isolated: http://localhost:3101

- PID 91513, started 2026-10-08T03:26:36Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3101 --strictPort --mode dev8001`
- Checkout `<repo>` at `586b21a1551b2bea04db329f73f2db718477e650`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend-isolated: http://127.0.0.1:8001

- PID 91454, started 2026-10-08T03:26:35Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Checkout `<repo>` at `586b21a1551b2bea04db329f73f2db718477e650`, 0 uncommitted path(s) under its directory
- Running code, measured from the backend's own source identity: app tree sha256 served `a1cd7cbb95f1e29bebb3377ee0dc4c4eb9b301ee67026bdf3db67017db08f7b1`, on disk now `a1cd7cbb95f1e29bebb3377ee0dc4c4eb9b301ee67026bdf3db67017db08f7b1`: match; commit served `586b21a1551b2bea04db329f73f2db718477e650`, checkout HEAD `586b21a1551b2bea04db329f73f2db718477e650`: match; uncommitted application files when it started: 0
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0', 'started_at': '2026-10-08T03:26:35Z', 'database': 'soccer_predictions_e2e'}
- Same process at the end: yes

Provider status at 2026-10-08T03:26:45.535398+00:00 (fields kept: status, times, error kind):

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
<repo>/backend/venv311/bin/python -m pytest -o addopts= -p no:cacheprovider -q -rfEs --junitxml=<repo>/.test-runs/2026-10-08T0326Z-586b21a/backend.junit.xml -o junit_suite_name=backend -o junit_family=xunit2 -o junit_logging=no
```

mocked-desktop, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-desktop --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-08T0326Z-586b21a/artifacts-mocked-desktop --reporter=list,json,junit
```

mocked-mobile, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-08T0326Z-586b21a/artifacts-mocked-mobile --reporter=list,json,junit
```

mocked-mobile-360, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile-360 --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-08T0326Z-586b21a/artifacts-mocked-mobile-360 --reporter=list,json,junit
```

live, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-08T0326Z-586b21a/artifacts-live --reporter=list,json,junit
```

live-isolated, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, E2E_ISOLATED_API_URL, E2E_ISOLATED_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live-isolated --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-08T0326Z-586b21a/artifacts-live-isolated --reporter=list,json,junit
```

## Integrity

- Runner: `scripts/test_evidence.py`, SHA-256 `d7af93ea453b63ab4e066becadc48e8eabc7ba5286996003b3f9979278fcc33c`
- Concurrency guard at start: no other test run
- Lock acquired 2026-10-08T03:26:46Z; stale lock cleared: no
- Watcher: 110 sample(s) every 15 s; anomalies: none
- Deny-list: 14 value(s) scanned, none found. Not scanned (shorter than 6 characters): SMTP_USER (backend/.env), hostname
- Published size: 496129 bytes

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
| backend.console-tail.txt | .test-runs/2026-10-08T0326Z-586b21a/backend.console.log | d226345cd109883bf2d915446b26893f1f1d648ec402a73506f5e5abac9c763d |
| backend.junit.xml | .test-runs/2026-10-08T0326Z-586b21a/backend.junit.xml | ac7a30f81b8e5cc1ba04ef68d0119fbd6be14f37de1e04bc427ed36dff640cb6 |
| playwright-live-isolated.console-tail.txt | .test-runs/2026-10-08T0326Z-586b21a/playwright-live-isolated.console.log | 45ec1233fc26a43e4fbdcbe1449cc30a4da5fdaa7064737631455fe543018992 |
| playwright-live-isolated.junit.xml | .test-runs/2026-10-08T0326Z-586b21a/playwright-live-isolated.junit.xml | d1f280af70f3ee62271460023b0d9989f3fcce3d162fdbd2883913fd4d8589dd |
| playwright-live.console-tail.txt | .test-runs/2026-10-08T0326Z-586b21a/playwright-live.console.log | 49287045b9686c88b6145be45460179b68af2c99ff801b7843893b8d6ef31e43 |
| playwright-live.junit.xml | .test-runs/2026-10-08T0326Z-586b21a/playwright-live.junit.xml | f2413acb71d7713915921ccaaa3df824e0a5b8080cf0fddcbe9001c2b7130b75 |
| playwright-mocked-desktop.console-tail.txt | .test-runs/2026-10-08T0326Z-586b21a/playwright-mocked-desktop.console.log | 70acbcbd4027af5c464220d961f1c35e0c4c95ea05a9c16d2e6316b769adcfed |
| playwright-mocked-desktop.junit.xml | .test-runs/2026-10-08T0326Z-586b21a/playwright-mocked-desktop.junit.xml | d7e9353d639b77df230be880f4119510973d04cc599908c498820463813f53c8 |
| playwright-mocked-mobile-360.console-tail.txt | .test-runs/2026-10-08T0326Z-586b21a/playwright-mocked-mobile-360.console.log | 2824d9fc4467fda288a3239cc028ddf752c1e4560ff5b4a789380151a0bb5a19 |
| playwright-mocked-mobile-360.junit.xml | .test-runs/2026-10-08T0326Z-586b21a/playwright-mocked-mobile-360.junit.xml | b15e3e8b90159483cbd1acfb00c2062a9168c962e5e1d954b056346b7c152181 |
| playwright-mocked-mobile.console-tail.txt | .test-runs/2026-10-08T0326Z-586b21a/playwright-mocked-mobile.console.log | ce597826d6eab7b891cb98b84adc77fb2e847e68fae954d051d7e210e9c14005 |
| playwright-mocked-mobile.junit.xml | .test-runs/2026-10-08T0326Z-586b21a/playwright-mocked-mobile.junit.xml | d00a14e0d4497a7089321153e4359f1541fc7f07b012fe79b6743b4baae1a40f |

## How to verify

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-08T0326Z-586b21a
```
