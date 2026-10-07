# Test evidence 2026-10-07T0301Z-7be42cc

**FAIL**

- backend: exit 0, PASS
- mocked-desktop: exit 0, PASS
- mocked-mobile: exit 0, PASS
- mocked-mobile-360: exit 0, PASS
- live: exit 1, FAIL

## Run

- Run id: `2026-10-07T0301Z-7be42cc`
- Started 2026-10-07T03:01:09Z, finished 2026-10-07T03:29:22Z (UTC)

| Suite | Started (UTC) | Finished (UTC) | Duration (s) | Exit code |
|---|---|---|---|---|
| backend | 2026-10-07T03:01:09Z | 2026-10-07T03:02:06Z | 57.2 | 0 |
| mocked-desktop | 2026-10-07T03:02:06Z | 2026-10-07T03:12:37Z | 630.2 | 0 |
| mocked-mobile | 2026-10-07T03:12:37Z | 2026-10-07T03:24:15Z | 698.8 | 0 |
| mocked-mobile-360 | 2026-10-07T03:24:15Z | 2026-10-07T03:26:52Z | 156.7 | 0 |
| live | 2026-10-07T03:26:52Z | 2026-10-07T03:29:22Z | 149.9 | 1 |

## Results

| Suite | Exit | Verdict | Planned | Passed | Failed | Flaky | Skipped | Did not run | Interrupted | Errors | xfailed | xpassed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| backend | 0 | PASS | - | 1644 | 0 | - | 0 | - | - | 0 | 0 | 0 |
| mocked-desktop | 0 | PASS | 451 | 449 | 0 | 0 | 2 | 0 | 0 | - | - | - |
| mocked-mobile | 0 | PASS | 451 | 451 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| mocked-mobile-360 | 0 | PASS | 138 | 138 | 0 | 0 | 0 | 0 | 0 | - | - | - |
| live | 1 | FAIL | 58 | 51 | 1 | 0 | 6 | 0 | 0 | - | - | - |

### backend

The reporter's own final lines, verbatim:

```
1644 passed, 20 warnings in 56.26s
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
  1 failed
    [live] › e2e/live/journey-proof.spec.ts:602:3 › LIVE: Back restores the previous list, its filters and its position at 1440px 
  6 skipped
  51 passed (2.5m)
```

JUnit: tests 58, passed 51, failures 1, errors 0, skipped 6. JSON (kept locally): 58 tests, buckets {'passed': 51, 'failed': 1, 'flaky': 0, 'skipped': 6, 'did_not_run': 0, 'interrupted': 0}.

| Check | Result | Detail |
|---|---|---|
| human summary present | ok | the list reporter's 'Running N tests' line and its final bucket lines |
| planned = sum of the human buckets | ok | planned 58 / buckets 58 |
| JSON report present | ok | - |
| human passed = JSON | ok | human 51 / JSON 51 |
| human failed = JSON | ok | human 1 / JSON 1 |
| human flaky = JSON | ok | human 0 / JSON 0 |
| human skipped = JSON | ok | human 6 / JSON 6 |
| human did not run = JSON | ok | human 0 / JSON 0 |
| human interrupted = JSON | ok | human 0 / JSON 0 |
| JSON stats agree with the recomputed buckets | ok | stats {'expected': 51, 'unexpected': 1, 'flaky': 0, 'skipped': 6} |
| JSON outcomes match their results | ok | 0 disagreement(s) |
| JSON holds exactly the requested project | ok | ['live'] |
| JUnit report present and parseable | ok | - |
| JUnit totals match its own testcases | ok | - |
| JUnit tests = planned | ok | JUnit 58 / planned 58 |
| JUnit failures + errors = failed | ok | JUnit 1 / failed 1 |
| JUnit skipped = skipped + did not run + interrupted | ok | JUnit 6 / 6 |
| JUnit passed = passed + flaky | ok | JUnit 51 / 51 |
| JUnit holds exactly the requested project | ok | ['live'] |
| exit code agrees with the results | ok | exit 1, failed 1, interrupted 0, errors outside tests 0 |
| not interrupted | ok | - |

## Skipped tests

| Project | Location | Test | Bucket | Reason |
|---|---|---|---|---|
| mocked-desktop | mocked/navigation-continuity.spec.ts:241 | the menu button is reachable and opens the menu | skipped | the full navigation is on the bar at this width |
| mocked-desktop | mocked/navigation-continuity.spec.ts:1013 | Escape closes the header menu and gives focus back to the menu button | skipped | there is no menu button at this width |
| live | live/detail-refresh.spec.ts:173 | a fixture in play keeps its running score under a running label across a return | skipped | no fixture is in play in the local database right now |
| live | live/journey-proof.spec.ts:420 | LIVE: the personal journey, end to end, at 360px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/journey-proof.spec.ts:420 | LIVE: the personal journey, end to end, at 390px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/journey-proof.spec.ts:420 | LIVE: the personal journey, end to end, at 1440px | skipped | this database holds no finished fixture with a result inside the feed window |
| live | live/return-journey.spec.ts:173 | a saved match that has been played shows its result in the feed | skipped | no finished fixture carrying a result in the local database |
| live | live/return-journey.spec.ts:201 | the results group is reachable from the top of the feed without scrolling for it | skipped | no finished fixture carrying a result in the local database |

## Failures

| Project | Location | Test | Kind | First line of the error |
|---|---|---|---|---|
| live | live/journey-proof.spec.ts:602 | LIVE: Back restores the previous list, its filters and its position at 1440px | failed | Error: the whole day must be taller than a 1440px window for this to mean anything |

## Repository

- HEAD at start: `7be42cc6355c466a353dbabf1fadb7cc17ea99ed`
- HEAD at end: `7be42cc6355c466a353dbabf1fadb7cc17ea99ed`
- Branch: `main`
- origin/main: `201442e1da4a51ad7d636983b13a74c131cde8f8` as of the last fetch, 2026-10-07T03:00:38Z
- Working tree: clean
- Working tree unchanged at the end: yes

## Servers under test

### frontend: http://localhost:3100

- PID 44833, started 2026-10-07T01:02:46Z, working directory `<repo>/frontend`
- Command: `node <repo>/frontend/node_modules/.bin/vite --port 3100 --strictPort`
- Checkout `<repo>` at `7be42cc6355c466a353dbabf1fadb7cc17ea99ed`, 0 uncommitted path(s) under its directory
- Same process at the end: yes

### backend: http://127.0.0.1:8000

- PID 38897, started 2026-10-07T02:51:55Z, working directory `<repo>/backend`
- Command: `<repo>/backend/venv311/bin/python3.11 ./venv311/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Checkout `<repo>` at `7be42cc6355c466a353dbabf1fadb7cc17ea99ed`, 0 uncommitted path(s) under its directory
- Newest app/**/*.py change 2026-10-07T02:48:04Z; process newer than the code: yes
- /health: {'http_status': 200, 'status': 'healthy', 'environment': 'development', 'version': '0.1.0'}
- Same process at the end: yes

Provider status at 2026-10-07T03:01:09.406888+00:00 (fields kept: status, times, error kind):

| Role | Provider | Integration | Configured | Last success | Last error | Error kind | Cooling down |
|---|---|---|---|---|---|---|---|
| match data | livescore | primary | True | 2026-10-02T14:53:28.028159+00:00 | 2026-10-07T02:35:10.228629+00:00 | http_401 | True |
| match data | api_football | retained (free plan: current season restricted) | True | 2026-10-07T02:35:10.429963+00:00 | 2026-10-07T01:04:45.927317+00:00 | - | False |
| match data | thesportsdb | retained (v1 API, untested, no live scores) | True | 2026-10-05T21:39:12.435861+00:00 | 2026-10-07T01:04:46.105929+00:00 | http_400 | False |
| forecasts | gameforecast | primary | True | 2026-10-07T01:04:55.691782+00:00 | - | - | False |

| Scheduler task | Last success | Last error | Error kind |
|---|---|---|---|
| fixtures | 2026-10-02T13:07:44.765961+00:00 | 2026-10-07T01:04:46.116357+00:00 | http_401 |
| forecasts | 2026-10-07T01:04:55.692572+00:00 | 2026-10-05T06:02:08.012716+00:00 | - |
| live | 2026-10-05T21:26:49.937540+00:00 | 2026-10-07T01:04:46.299217+00:00 | http_401 |
| recover | 2026-10-07T02:35:11.357193+00:00 | 2026-10-05T02:53:20.858585+00:00 | - |
| results | 2026-10-02T14:53:28.332818+00:00 | 2026-10-07T01:04:46.639394+00:00 | http_401 |
| settle | 2026-10-07T02:55:56.614024+00:00 | - | - |

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
<repo>/backend/venv311/bin/python -m pytest -o addopts= -p no:cacheprovider -q -rfEs --junitxml=<repo>/.test-runs/2026-10-07T0301Z-7be42cc/backend.junit.xml -o junit_suite_name=backend -o junit_family=xunit2 -o junit_logging=no
```

mocked-desktop, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-desktop --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0301Z-7be42cc/artifacts-mocked-desktop --reporter=list,json,junit
```

mocked-mobile, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0301Z-7be42cc/artifacts-mocked-mobile --reporter=list,json,junit
```

mocked-mobile-360, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=mocked-mobile-360 --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0301Z-7be42cc/artifacts-mocked-mobile-360 --reporter=list,json,junit
```

live, in `<repo>/frontend`, with E2E_API_URL, E2E_BASE_URL, FORCE_COLOR, PLAYWRIGHT_JSON_OUTPUT_FILE, PLAYWRIGHT_JUNIT_INCLUDE_PROJECT_IN_TEST_NAME, PLAYWRIGHT_JUNIT_OUTPUT_FILE, PLAYWRIGHT_JUNIT_STRIP_ANSI, PLAYWRIGHT_JUNIT_SUITE_NAME set:

```
<repo>/frontend/node_modules/.bin/playwright test --project=live --forbid-only --retries=0 --output=<repo>/.test-runs/2026-10-07T0301Z-7be42cc/artifacts-live --reporter=list,json,junit
```

## Integrity

- Runner: `scripts/test_evidence.py`, SHA-256 `514f19adc6a4e05a4109537865a142389ea19b65e24bd24eba4ed7ebcbc65a75`
- Concurrency guard at start: no other test run
- Lock acquired 2026-10-07T03:01:09Z; stale lock cleared: no
- Watcher: 112 sample(s) every 15 s; anomalies: none
- Deny-list: 14 value(s) scanned, none found. Not scanned (shorter than 6 characters): SMTP_USER (backend/.env), hostname
- Published size: 489483 bytes

Scrub substitutions per file:

| File | ansi | repo-root | home | pytest-hostname | bearer-header | jwt | url-credentials | query-secret |
|---|---|---|---|---|---|---|---|---|
| backend.console-tail.txt | 0 | 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| backend.junit.xml | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |
| playwright-live.console-tail.txt | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| playwright-live.junit.xml | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
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
| backend.console-tail.txt | .test-runs/2026-10-07T0301Z-7be42cc/backend.console.log | f96915f72c5fdc5a801886ed9d33ddc89af949532ec91afc5d3bcb8c8c0d1ad3 |
| backend.junit.xml | .test-runs/2026-10-07T0301Z-7be42cc/backend.junit.xml | a399b26756fd36e18ec73ed7f1ac0f23ae2467088803099605f0cbd8cee85268 |
| playwright-live.console-tail.txt | .test-runs/2026-10-07T0301Z-7be42cc/playwright-live.console.log | ac13c8465c4d7d9e7a59408fd44ca61ff50b72200656ceecaa2a7d7507f4ad6b |
| playwright-live.junit.xml | .test-runs/2026-10-07T0301Z-7be42cc/playwright-live.junit.xml | b611fa654902a4600bbaba87191545c314efaab4ac74fce437c471bd0884e9b4 |
| playwright-mocked-desktop.console-tail.txt | .test-runs/2026-10-07T0301Z-7be42cc/playwright-mocked-desktop.console.log | bf5813d36f41a8f658526ac272c0b4c6b94fb9cc97016073d96e48423489f293 |
| playwright-mocked-desktop.junit.xml | .test-runs/2026-10-07T0301Z-7be42cc/playwright-mocked-desktop.junit.xml | 80ec3dc92ba659ce021ef2bfe3909326c4c45ed82268eda2103938a334153957 |
| playwright-mocked-mobile-360.console-tail.txt | .test-runs/2026-10-07T0301Z-7be42cc/playwright-mocked-mobile-360.console.log | 30dfdb96c7c67cf00e9f735a67f369f95edb21477420482ac2c57693d82a5945 |
| playwright-mocked-mobile-360.junit.xml | .test-runs/2026-10-07T0301Z-7be42cc/playwright-mocked-mobile-360.junit.xml | 8bdddb928f7f18662c8f63075e5a7212fe145191a6648d52b83392937bcd77b4 |
| playwright-mocked-mobile.console-tail.txt | .test-runs/2026-10-07T0301Z-7be42cc/playwright-mocked-mobile.console.log | 3a14c5828bd0b1039166b5bb0e1ae8ae0f33a53754041b08a74a5a926e67ec20 |
| playwright-mocked-mobile.junit.xml | .test-runs/2026-10-07T0301Z-7be42cc/playwright-mocked-mobile.junit.xml | f55b5de3a4b2c30a7e91caebb019317c000ce7e2e0a47180df3cf6ecda904222 |

## How to verify

```
python3 scripts/test_evidence.py verify docs/evidence/test-reports/2026-10-07T0301Z-7be42cc
```
