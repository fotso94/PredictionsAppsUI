# Test evidence 2026-10-07T0408Z-12753b6

**PASS**

- backend: exit 0, PASS
- mocked-desktop: exit 0, PASS
- mocked-mobile: exit 0, PASS
- mocked-mobile-360: exit 0, PASS
- live: exit 0, PASS

## Run

- Run id: `2026-10-07T0408Z-12753b6`
- Started 2026-10-07T04:08:04Z, finished 2026-10-07T04:36:00Z (UTC)

| Suite | Started (UTC) | Finished (UTC) | Duration (s) | Exit code |
|---|---|---|---|---|
| backend | 2026-10-07T04:08:04Z | 2026-10-07T04:08:56Z | 52.0 | 0 |
| mocked-desktop | 2026-10-07T04:08:56Z | 2026-10-07T04:19:24Z | 628.3 | 0 |
| mocked-mobile | 2026-10-07T04:19:24Z | 2026-10-07T04:31:05Z | 701.3 | 0 |
| mocked-mobile-360 | 2026-10-07T04:31:05Z | 2026-10-07T04:33:40Z | 155.0 | 0 |
| live | 2026-10-07T04:33:40Z | 2026-10-07T04:36:00Z | 139.3 | 0 |

## Results

| Suite | Exit | Verdict | Planned | Passed | Failed | Flaky | Skipped | Did not run | Interrupted | Errors | xfailed | xpassed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| backend | 0 | PASS | - | 1644 | 0 | - | 0 | - | - | 0 | 0 | 0 |
| mocked-desktop | 0 | PASS | 451 | 449 | 0 | 0 | 2 | 0 | 0 | - | - | - |
| mocked-mobile | 0 | PASS | 451 | 451 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| mocked-mobile-360 | 0 | PASS | 138 | 138 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live | 0 | PASS | 58 | 52 | 0 | 0 | 6 | 0 | 0 | - | - | - |

### backend

The reporter's own final lines, verbatim:

```
1644 passed, 20 warnings in 50.98s
```

JUnit: 1644 testcases; passed or xpassed 1644, failed 0, errors 0, skipped 0, xfailed 0.

| Check | Result | Detail |
|---|---|---|
| pytest summary line present | ok | - |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit failed = pytest failed | ok | JUnit 0 / pytest 0 |
| JUnit errors = pytest errors | ok | JUnit 0 / pytest 0 |
| JUnit skipped = pytest skipped | ok | JUnit 0 / pytest 0 |
| JUnit xfailed = pytest xfailed | ok | JUnit 0 / pytest 0 |
| JUnit passed = pytest passed + xpassed | ok | JUnit 1644 / pytest 1644 |
| no skip says the test database or Redis is not reachable | ok | 0 such skip(s) |
| nothing deselected | ok | 0 deselected |
| at least one test ran | ok | 1644 test(s) |
| exit code agrees with the results | ok | exit 0, failed 0, errors 0, tests 1644 |
| not interrupted | ok | - |

### mocked-desktop

The reporter's own final lines, verbatim:

```
  2 skipped
  449 passed (10.5m)
```

JUnit: tests 451, passed 449, failures 0, errors 0, skipped 2. JSON (kept locally): 451 tests, buckets {'passed': 449, 'failed': 0, 'flaky': 0, 'skipped': 2, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 451 / buckets 451 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 449 / JSON 449 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 2 / JSON 2 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 449, 'unexpected': 0, 'flaky': 0, 'skipped': 2} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['mocked-desktop'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 451 / planned 451 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 2 / 2 |
| JUnit passed = passed + flaky | ok | JUnit 449 / 449 |
| JUnit holds exactly the requested project | ok | ['mocked-desktop'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### mocked-mobile

The reporter's own final lines, verbatim:

```
  451 passed (11.7m)
```

JUnit: tests 451, passed 451, failures 0, errors 0, skipped 0. JSON (kept locally): 451 tests, buckets {'passed': 451, 'failed': 0, 'flaky': 0, 'skipped': 0, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 451 / buckets 451 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 451 / JSON 451 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 0 / JSON 0 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 451, 'unexpected': 0, 'flaky': 0, 'skipped': 0} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['mocked-mobile'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 451 / planned 451 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 0 / 0 |
| JUnit passed = passed + flaky | ok | JUnit 451 / 451 |
| JUnit holds exactly the requested project | ok | ['mocked-mobile'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### mocked-mobile-360

The reporter's own final lines, verbatim:

```
  138 passed (2.6m)
```

JUnit: tests 138, passed 138, failures 0, errors 0, skipped 0. JSON (kept locally): 138 tests, buckets {'passed': 138, 'failed': 0, 'flaky': 0, 'skipped': 0, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 138 / buckets 138 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 138 / JSON 138 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 0 / JSON 0 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 138, 'unexpected': 0, 'flaky': 0, 'skipped': 0} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['mocked-mobile-360'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 138 / planned 138 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 0 / 0 |
| JUnit passed = passed + flaky | ok | JUnit 138 / 138 |
| JUnit holds exactly the requested project | ok | ['mocked-mobile-360'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

### live

The reporter's own final lines, verbatim:

```
  6 skipped
  52 passed (2.3m)
```

JUnit: tests 58, passed 52, failures 0, errors 0, skipped 6. JSON (kept locally): 58 tests, buckets {'passed': 52, 'failed': 0, 'flaky': 0, 'skipped': 6, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 58 / buckets 58 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 52 / JSON 52 |
| human failed = JSON | ok | human 0 / JSON 0 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 6 / JSON 6 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 52, 'unexpected': 0, 'flaky': 0, 'skipped': 6} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['live'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 58 / planned 58 |
| JUnit failures + errors = failed | ok | JUnit 0 / failed 0 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 6 / 6 |
| JUnit passed = passed + flaky | ok | JUnit 52 / 52 |
| JUnit holds exactly the requested project | ok | ['live'] |
| exit code agrees with the results | ok | exit 0, failed 0, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

## Skipped tests

| Project | Location | Test | Bucket | Reason |
|---|---|---|---|---|
| mocked-desktop | mocked/navigation-continuity.spec.ts:241 | the menu button is reachable and opens the menu | skipped | the full navigation is on the bar at this width |
| mocked-desktop | mocked/navigation-continuity.spec.ts:1013 | Escape closes the header menu and gives focus back to the menu button | skipped | there is no menu button at this width |
| live | live/detail-refresh.spec.ts:174 | a fixture in play keeps its running score under a running label across a return | skipped | no fixture is in play in the local database right now |
| live | live/journey-proof.spec.ts:443 | LIVE: the personal journey, end to end, at 360px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/journey-proof.spec.ts:443 | LIVE: the personal journey, end to end, at 390px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/journey-proof.spec.ts:443 | LIVE: the personal journey, end to end, at 1440px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/return-journey.spec.ts:174 | a saved match that has been played shows its result in the feed | skipped | no finished fixture carrying a result in the local database |
| live | live/return-journey.spec.ts:202 | the results group is reachable from the top of the feed without scrolling for it | skipped | no finished fixture carrying a result in the local database |

## Failures

None.

## Repository

- HEAD at start: `12753b60e821ccc7f5d71377ea9f98115e92c802`
- HEAD at end: `12753b60e821ccc7f5d71377ea9f98115e92c802`
- Branch: `main`
- origin/main: `201442e1da4a51ad7d636983b13a74c131cde8f8` as of the last fetch, 2026-10-07T03:00:38Z
- Working tree: clean
- Working tree unchanged at the end: yes

## Servers under test

### frontend: http://localhost:3100

- PID 44833, started 2026-10-07T01:02:46Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3100 --strictPort`
- Checkout `<repo>` at `12753b60e821ccc7f5d71377ea9f98115e92c802`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend: http://127.0.0.1:8000

- PID 38897, started 2026-10-07T02:51:55Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Checkout `<repo>` at `12753b60e821ccc7f5d71377ea9f98115e92c802`, 0 uncommitted path(s) under its directory
- Newest app/**/*.py change 2026-10-07T02:48:04Z; process newer than the code: yes
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0'}
- Same process at the end: yes

Provider status at 2026-10-07T04:08:03.840475+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| match data | livescore | primary | True | 2026-10-02T14:53:28.028159+00:00 | 2026-10-07T04:07:11.782814+00:00 | http_401 | True |
| match data | api_football | retained (free plan: current season restricted) | True | 2026-10-07T04:07:11.943231+00:00 | 2026-10-07T01:04:45.927317+00:00 | - | False |
| match data | thesportsdb | retained (v1 API, untested, no live scores) | True | 2026-10-05T21:39:12.435861+00:00 | 2026-10-07T01:04:46.105929+00:00 | http_400 | False |
| forecasts | gameforecast | primary | True | 2026-10-07T01:04:55.691782+00:00 | - | - | False |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | 2026-10-02T13:07:44.765961+00:00 | 2026-10-07T01:04:46.116357+00:00 | http_401 |
| forecasts | 2026-10-07T01:04:55.692572+00:00 | 2026-10-05T06:02:08.012716+00:00 | - |
| live | 2026-10-05T21:26:49.937540+00:00 | 2026-10-07T01:04:46.299217+00:00 | http_401 |
| recover | 2026-10-07T04:07:12.549884+00:00 | 2026-10-05T02:53:20.858585+00:00 | - |
| results | 2026-10-02T14:53:28.332818+00:00 | 2026-10-07T01:04:46.639394+00:00 | http_401 |
| settle | 2026-10-07T04:07:12.562618+00:00 | - | - |

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
<repo>/backend/venv311/bin/python -m pytest -o addopts= -p no:cacheprovider -q -rfEs --junitxml=<repo>/.test-runs/2026-10-07T0408Z-12753b6/backend.junit.xml -o junit_suite_name=backend -o junit_family=xunit2 -o junit_logging=no
```

mocked-desktop, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-desktop --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0408Z-12753b6/artifacts-mocked-desktop --reporter=list,json,junit
```

mocked-mobile, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0408Z-12753b6/artifacts-mocked-mobile --reporter=list,json,junit
```

mocked-mobile-360, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile-360 --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0408Z-12753b6/artifacts-mocked-mobile-360 --reporter=list,json,junit
```

live, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0408Z-12753b6/artifacts-live --reporter=list,json,junit
```

## Integrity

- Runner: `scripts/test_evidence.py`, SHA-256 `514f19adc6a4e05a4109537865a142389ea19b65e24bd24eba4ed7ebcbc65a75`
- Concurrency guard at start: no other test run
- Lock acquired 2026-10-07T04:08:04Z; stale lock cleared: no
- Watcher: 110 sample(s) every 15 s; anomalies: none
- Deny-list: 14 value(s) scanned, none found. Not scanned (shorter than 6 characters): SMTP_USER (backend/.env), hostname
- Published size: 489062 bytes

Scrub substitutions per file:

| File | ansi | repo-root | home | pytest-hostname | bearer-header | jwt | url-credentials | query-secret |
|---|---|---|---|---|---|---|---|---|
| backend.console-tail.txt | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| backend.junit.xml | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| playwright-live.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-desktop.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-desktop.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile-360.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile-360.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile.console-tail.txt | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-mocked-mobile.junit.xml | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| summary | 0 | 22 | 0 | 0 | 0 | 0 | 0 | 0 |

Raw files kept locally, with their SHA-256 before scrubbing:

| Published | Raw file | Raw SHA-256 |
|---|---|---|
| backend.console-tail.txt | .test-runs/2026-10-07T0408Z-12753b6/backend.console.log | c5442b03029f4bd69de4924edf1b61ef91176d984b8b9dd30b73da65455a2d56 |
| backend.junit.xml | .test-runs/2026-10-07T0408Z-12753b6/backend.junit.xml | 76390fbde6654ebe0824bd0138d470bb183e8dc7febf78287cb2af610e9a6e07 |
| playwright-live.console-tail.txt | .test-runs/2026-10-07T0408Z-12753b6/playwright-live.console.log | c7b2769855fc11db25a4880838821ab36ddaa07738fc4f63d92d7178ddfaa4bc |
| playwright-live.junit.xml | .test-runs/2026-10-07T0408Z-12753b6/playwright-live.junit.xml | 00b6ff5a604f0e762d580c5252cf775f057eabc600ef1c0a6604583311a5d6a7 |
| playwright-mocked-desktop.console-tail.txt | .test-runs/2026-10-07T0408Z-12753b6/playwright-mocked-desktop.console.log | 0e7f8850828cba74edc2edd88408133b17f1bb092350aadb57052e1450a557b9 |
| playwright-mocked-desktop.junit.xml | .test-runs/2026-10-07T0408Z-12753b6/playwright-mocked-desktop.junit.xml | cd062bc5837ec1a13ed52290b1baf1421567e63589f7eb498504db936490321c |
| playwright-mocked-mobile-360.console-tail.txt | .test-runs/2026-10-07T0408Z-12753b6/playwright-mocked-mobile-360.console.log | ce6c42562b35fd463a539d6c2ea482136a3914f91709d2f9d606a6f00eeb34e1 |
| playwright-mocked-mobile-360.junit.xml | .test-runs/2026-10-07T0408Z-12753b6/playwright-mocked-mobile-360.junit.xml | 926bffeb00165b318db5697e340dff45e202d32f4405ff872e961beac65c8f71 |
| playwright-mocked-mobile.console-tail.txt | .test-runs/2026-10-07T0408Z-12753b6/playwright-mocked-mobile.console.log | 621b5d1f62cc60ed48af33eae6461ad4b991ad804691347d8f83eb449caa02f7 |
| playwright-mocked-mobile.junit.xml | .test-runs/2026-10-07T0408Z-12753b6/playwright-mocked-mobile.junit.xml | 337363d49c075590c19c7d60ae6454832ed95c8ef61903531bbc598926707420 |

## How to verify

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-07T0408Z-12753b6
```
