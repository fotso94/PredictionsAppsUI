# Release readiness runs: expert-fixes, 2026-10-21

These runs check that `expert-fixes` is ready for a separate, controlled live rollout. This is
preparation only: nothing here merged, deployed or restarted anything live. Live `:8000` served
`96c22edd` (app tree `f70e8f85…6c41`, 91 files, started 2026-10-20T01:01:47Z) before and after.

**Result: every check that the later changes affected has passed.**
- One defect turned up, and it was in a test helper, not the app (see below).
- After the fix, the whole live-isolated project passed: 63 passed, 0 failed, 3 skipped, exit 0.
- The 3 skips are the specs' own data guards.
- All other evidence is reused. This page names its basis.

## What was under test

| | |
|---|---|
| Release candidate | `expert-fixes`, fast-forward from live `96c22edd`. App tree (`backend/app`) `02195dc15f1d73967cbe01b0b004bb258be82528f7268425109ae4152a94bb8b`, 93 files. This is the same digest at `2a82f16e`, at `e567022f` (the helper fix) and at the commit that adds this page. Neither of those two commits touches `backend/app` or `frontend/src`. |
| Isolated backend | `http://127.0.0.1:8001`, pid 41147, cwd `<worktree>/backend`, started 2026-10-21T22:09:49Z. Its `/health` reported database `soccer_predictions_e2e`, Redis databases 10-15, `scheduler_enabled` false, `source.commit` `2a82f16e`, `commit_dirty_app_files` `[]`, and the app tree above. It read the same just before R2. |
| Isolated frontend | `http://localhost:3101`, Vite pid 1982, `--mode dev8001`, serving `<worktree>/frontend/src`. `frontend/src` has not changed since `8c779e7b`. |
| Runner rules | One runner at a time. Each wrote straight to a file with no pipe. Each exit code is the runner's own `$?`, and each count is copied from the runner's own summary line. |

## The defect: a time-dependent test helper

R1, the first whole-project run at 22:10Z, failed three tests:
- `expert-delete-idempotent.spec.ts:103`
- `expert-management.spec.ts:192`
- `revision-history.spec.ts:71`

An unchanged rerun at 22:15Z failed the same three in the same way.

All three attach their prediction to `anyUpcomingMatch()` in `frontend/e2e/support/qa-account.ts`. That helper took the first fixture stored as `scheduled` on today's UTC date. The isolated clone runs with the scheduler off, so its fixtures stay `scheduled` after kick-off. By 22:10Z, all ten 2026-10-21 fixtures had kicked off (16:45-19:00Z). The backend was right to mark each new prediction `published_after_kickoff`, and the specs that assert the prematch case failed. The diagnosis is in [release-readiness-r1-failure-diagnosis.log](release-readiness-r1-failure-diagnosis.log).

The helper is older than this branch: it is the same at `96c22edd`. The fault was the test's dependence on the clock, not the product. Waiting for the UTC date to roll over would only have hidden it until the next day's first kick-off.

**Fix** (`e567022f`, test-only): the helper also requires a kick-off more than 30 minutes ahead.

The same three tests, on the same data, 14 seconds apart:

| Run | Helper | Started (UTC) | Passed | Failed | Exit | Log |
|---|---|---|---:|---:|---:|---|
| R2-before | old (as at `2a82f16e`) | 23:30:23 | 0 | 3 | 1 | [release-readiness-r2-before-old-helper-three.log](release-readiness-r2-before-old-helper-three.log) |
| R2-after | fixed | 23:30:37 | 3 | 0 | 0 | [release-readiness-r2-after-fixed-helper-three.log](release-readiness-r2-after-fixed-helper-three.log) |

## Runs in this round

| # | Run | Started (UTC) | Passed | Failed | Skipped | Exit | Runner time | Log |
|---|---|---|---:|---:|---:|---:|---|---|
| P | Preflight: git state, no other runner, live and isolated `/health` identity | 22:09:47 | | | | | | [release-readiness-preflight.log](release-readiness-preflight.log) |
| R1 | Live-isolated, whole project, old helper | 22:10:09 | 60 | 3 | 3 | 1 | 3.7 m | [release-readiness-r1-live-isolated-all.log](release-readiness-r1-live-isolated-all.log) |
| R1-rerun | The 3 failures, unchanged | 22:15:51 | 0 | 3 | 0 | 1 | | [release-readiness-r1-rerun-failed-three.log](release-readiness-r1-rerun-failed-three.log) |
| R2-before / R2-after | See the table above | 23:30 | | | | | | |
| **R2** | **Live-isolated, whole project (15 specs, 66 tests), fixed helper** | 23:31:12 | **63** | **0** | **3** | **0** | 3.6 m | [release-readiness-r2-live-isolated-all.log](release-readiness-r2-live-isolated-all.log) |
| R2-skips | `parlay-journey` + `suggestion-journey`, json reporter, to record the skip reasons | 23:35:59 | 2 | 0 | 3 | 0 | | [release-readiness-r2-skip-reasons.log](release-readiness-r2-skip-reasons.log) |
| R2-tc | `npm run type-check` (the fix touched `e2e/support`) | 23:35:28 | no errors | | | 0 | | [release-readiness-r2-type-check.log](release-readiness-r2-type-check.log) |
| R2-lint | `npm run lint` (`--max-warnings 0`) | 23:35:30 | no problems | | | 0 | | [release-readiness-r2-lint.log](release-readiness-r2-lint.log) |
| R2-guard | Browser guard specs, `playwright.guard.config.ts` | 23:35:32 | 45 | 0 | 0 | 0 | 6.9 s | [release-readiness-r2-guard-specs.log](release-readiness-r2-guard-specs.log) |
| R2-refusal | Refusal runs, `node --test e2e/guard/refusal-runs.test.mjs` | 23:35:39 | 18 | 0 | 0 | 0 | | [release-readiness-r2-refusal-runs.log](release-readiness-r2-refusal-runs.log) |

Every live-isolated run sent its traffic only to `:3101` and `:8001`. Its preflight made one
`GET :8001/health` and confirmed the e2e database, Redis 10-15 and the scheduler off.

Command for R1 and R2, from `<worktree>/frontend`:
`E2E_STACK=live-isolated E2E_ISOLATED_BASE_URL=http://localhost:3101 E2E_ISOLATED_API_URL=http://127.0.0.1:8001 ./node_modules/.bin/playwright test --project=live-isolated --workers=1 --reporter=list`.
This is `npm run e2e:live-isolated` plus the list reporter.

### The three skips (R2-skips; the runner's own annotations)

| Test | Reason |
|---|---|
| `parlay-journey.spec.ts:58` | "needs two upcoming fixtures with a stored forecast at http://127.0.0.1:8001; found 0" |
| `parlay-journey.spec.ts:124` | "no qualifying combination … none of the 47 fixtures in the window qualifies: 47 with only an out-of-date forecast" |
| `suggestion-journey.spec.ts:125` | "the page's own request (legs=3, min_probability=0.6) returned no combination … (same shortfall)" |

These are data guards. With the scheduler off and no provider keys, the clone's forecasts never
refresh, so they have aged out of the suggestion window. The branch changes no parlay, suggestion
or slip code (`96c22edd..HEAD`). Clearing the skips would need `reset-e2e-db`, which copies the live
database, or provider requests. Both are outside this round.

## Evidence reused, and why it is still valid

The basis is in [release-readiness-reuse-basis.log](release-readiness-reuse-basis.log).
- `b6c35b28..2a82f16e` changes nothing outside `docs/`.
- `e567022f` changes only `frontend/e2e/support/qa-account.ts`.
- No mocked spec imports `qa-account.ts`; the mocked specs import `api-stub`, `auth`, `live-stack` and `vocabulary`.
- The backend suite does not read it.

| Check | Reused run | Commit | Result |
|---|---|---|---|
| Backend, full suite | FOLLOWUP run 3 | `1a6109fe` | 2003 passed, 0 skipped, exit 0 |
| Backend guard and `/health` tests | FOLLOWUP 1a | `1a6109fe` | 114 passed, exit 0 |
| Evidence-runner tests | FOLLOWUP 1b | `1a6109fe` | 94 passed, exit 0 |
| Negative demonstrations | FOLLOWUP 2a, 2b | `1a6109fe` | 14 of 14 and 10 of 10 hold |
| Mocked desktop / mobile / mobile-360 | FINAL runs 5-7 | `2759f592` | 547 + 2 width-gate skips / 549 / 199, each exit 0 |
| Frontend build | FINAL | `2759f592` | exit 0 |

The mocked runs are still valid at HEAD:
- `frontend/src`, the mocked specs, their fixtures and support files, and every build input are unchanged since `2759f592`.
- `live-stack.ts` changed only in comments.
- `playwright test --list` at HEAD selects the same 1297 tests, matched by project, file:line:col and title, with 0 differences ([release-readiness-mocked-list.log](release-readiness-mocked-list.log)).
- The run-wide parts added since then (the global preflight and the worker token) passed in all three mocked projects in FOLLOWUP 4b and 4c.

## Limitations

- The 3 data-guard skips above. Parlay and suggestion journeys are not exercised end to end on the isolated pair.
- The clone's last future fixture kicks off 2026-10-25 at 20:00Z. After about 19:30Z that day, `anyUpcomingMatch` finds nothing, and the expert specs that need a fixture skip, saying so. They do not pass falsely. A rerun after then needs a refreshed clone.
- `npm run type-check` covers `src/` only, so `e2e/` and `playwright.config.ts` are linted and executed but never type-checked.
- The journey screenshots in `journey/` were taken on frontend `8c779e7b`, the same `src` as HEAD, against the backend of that time. The journey test itself passed again in R2 against the release backend.
- These runs are isolated. Live behaviour after a deployment can only be checked by the post-deploy checks in the rollout runbook, which is kept outside Git.
