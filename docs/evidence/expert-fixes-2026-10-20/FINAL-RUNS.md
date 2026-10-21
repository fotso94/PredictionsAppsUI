# Final consolidated runs: expert-fixes at 2759f592 (2026-10-21)

Every suite was run once on HEAD of `expert-fixes`, strictly one runner at a time. Before each run,
`ps` was checked for other pytest or Playwright test runners and found none. Each runner wrote
straight to a file, with no pipe, and its exit code was taken from `$?`. The counts below are the
runners' own summary lines, copied from the logs listed.

**Result: no test failed in any run, and every exit code was 0.** The backend suite ran with
0 skipped. The 5 Playwright skips are the specs' own guards (2 on viewport width, 3 on the data in
the clone). None of them is an unreachable target.

## Isolated identity

| | |
|---|---|
| Branch / HEAD | `expert-fixes` at `2759f592` (`2759f592306ce70fd29d06e30935fd09797dac6d`); `git status` clean before the first run |
| Backend :8001 | pid 1692, cwd `<worktree>/backend`, `uvicorn app.main:app --host 127.0.0.1 --port 8001`. Restarted for this task with `scripts/local-servers.sh stop backend-isolated && … start backend-isolated`; it replaced pid 70388, which had been serving `34527e5c`. `backend/venv311` is a symlink to the main checkout's venv: only the interpreter and packages come from there, and `app/` is imported from the cwd. |
| `/health` | `database` `soccer_predictions_e2e`; `source.commit` `2759f592306c…` (= `git rev-parse HEAD`); `commit_dirty_app_files` `[]`; `app_tree_sha256` `7138445ead1da33f2c8ca9597a7a08c90d9ebdf6fbad5da0fb11256a20f75539` over 91 files, the same digest `app.core.source_identity.app_tree_digest` computes on the checkout; `started_at` `2026-10-21T07:04:21Z` |
| Backend env (non-secret) | `POSTGRES_DB=soccer_predictions_e2e`, `SYNC_SCHEDULER_ENABLED=false`, `EMAIL_ENABLED=false`, `REDIS_DB_SESSIONS/PREDICTIONS/EXPERT_TOOLS/ML_MODELS/MATCH_DATA/RATE_LIMIT = 10/11/12/13/14/15`, `BACKEND_CORS_ORIGINS` = :3101 only. The five provider credentials (`LIVESCORE_API_KEY`, `LIVESCORE_API_SECRET`, `GAMEFORECAST_API_KEY`, `API_FOOTBALL_KEY`, `THESPORTSDB_KEY`) are all **empty**. `ALLOW_TEST_DATA_CLASSIFICATION=true` comes from the gitignored `backend/.env`. |
| Frontend :3101 | pid 1982, cwd `<worktree>/frontend`, `vite --port 3101 --strictPort --mode dev8001` (`VITE_API_BASE_URL=http://localhost:8001`). Vite serves the working tree, which is HEAD. |
| After the last run | Same pids, same commit, same digest, same `started_at`: nothing restarted the backend mid-runs |
| Backend test services | test DB `soccer_predictions_test` on :5432, Redis `expert-fixes-test-redis` 127.0.0.1:6390, race DB `expert-fixes-race-pg` 127.0.0.1:5440 |

Recorded in [final-preflight.log](final-preflight.log).

## Runs

| # | Run (started, UTC) | Passed | Failed | Skipped | Flaky | Exit | Runner time | Log |
|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | Backend, full suite (`pytest -q -p no:cacheprovider -o addopts='' -rs tests`, explicit env, 07:05:13) | 1895 | 0 | 0 | n/a | 0 | 68.77 s | [final-backend-full-suite.log](final-backend-full-suite.log) |
| 2 | `npm run type-check` (07:06:43) | no errors | | | | 0 | | [final-frontend-type-check.log](final-frontend-type-check.log) |
| 3 | `npm run lint` (`--max-warnings 0`, 07:06:45) | no problems | | | | 0 | | [final-frontend-lint.log](final-frontend-lint.log) |
| 4 | `npm run build` (`tsc && vite build`, 07:06:47) | built | | | | 0 | 1.70 s (vite) | [final-frontend-build.log](final-frontend-build.log) |
| 5 | Mocked, `--project=mocked-desktop`, all 549 tests (07:07:06) | 547 | 0 | 2 | 0 | 0 | 13.6 m | [final-mocked-desktop.log](final-mocked-desktop.log) |
| 6 | Mocked, `--project=mocked-mobile`, all 549 tests (07:21:31) | 549 | 0 | 0 | 0 | 0 | 15.0 m | [final-mocked-mobile.log](final-mocked-mobile.log) |
| 7 | Mocked, `--project=mocked-mobile-360`, all 199 tests in its testMatch (07:36:46) | 199 | 0 | 0 | 0 | 0 | 4.5 m | [final-mocked-mobile-360.log](final-mocked-mobile-360.log) |
| 8 | Live-isolated, the whole project: 15 specs, 66 tests, `--workers=1` (07:41:29) | 63 | 0 | 3 | 0 | 0 | 3.5 m | [final-live-isolated-all.log](final-live-isolated-all.log) |
| 8b | Live-isolated, rerun of `parlay-journey` + `suggestion-journey` with the json reporter, only to record the skip reasons (07:45:40) | 2 | 0 | 3 | 0 | 0 | 4.7 s | [final-live-isolated-skip-reasons.log](final-live-isolated-skip-reasons.log) |
| 9 | Live-isolated, `expert-composer.spec.ts` + `expert-publishing.spec.ts` on their own, `--workers=1` (07:46:04) | 10 | 0 | 0 | 0 | 0 | 14.6 s | [final-live-isolated-expert-composer-publishing.log](final-live-isolated-expert-composer-publishing.log) |
| — | QA inventory, read-only SELECTs on `soccer_predictions_e2e` (07:47:47) | | | | | 0 | | [final-qa-inventory.log](final-qa-inventory.log) |

All Playwright runs used `E2E_BASE_URL=http://localhost:3101` and `--reporter=list`, from `frontend/`.

**Flaky.** `playwright.config.ts` sets `retries: 0`, so no test can be counted flaky. A flaky test
needs a retry, and no runner printed a flaky line. The json report of run 8b says `flaky=0`. Pytest
ran with no rerun plugin (`-o addopts=''`).

**Live-isolated, tests per spec in run 8:** account-profile 2, expert-composer-french 2,
expert-composer 3, expert-delete-idempotent 2, expert-drafts 1, expert-journey 1,
expert-management 2, expert-publishing 7, journey-proof 11, parlay-journey 2 (both skipped),
personal-controls 12, return-journey 7, revision-history 1, save-journey 10, suggestion-journey 3
(1 skipped). That makes 66 tests.

**The two existing expert suites report their own counts.** expert-composer passed 3 of 3 and
expert-publishing passed 7 of 7, both in run 9 on their own and inside run 8.

## Skips, with reasons

| Run | Test | Reason |
|---|---|---|
| 5 mocked-desktop | `navigation-continuity.spec.ts:241` the menu button is reachable and opens the menu | the spec's width gate: "the full navigation is on the bar at this width" (1440 px ≥ `MENU_BREAKPOINT`). It runs and passes in runs 6 and 7. |
| 5 mocked-desktop | `navigation-continuity.spec.ts:1013` Escape closes the header menu and gives focus back to the menu button | the spec's width gate: "there is no menu button at this width". It runs and passes in runs 6 and 7. |
| 8 live-isolated | `parlay-journey.spec.ts:58` a real fixture → a selection → a saved, recorded combination | "needs two upcoming fixtures with a stored forecast at http://127.0.0.1:8001; found 0" |
| 8 live-isolated | `parlay-journey.spec.ts:124` suggestions come from stored forecasts and add to the slip | "no qualifying combination at http://127.0.0.1:8001: none of the 57 fixtures in the window qualifies: 56 with only an out-of-date forecast (left out unless out-of-date forecasts are included); 1 without a stored forecast" |
| 8 live-isolated | `suggestion-journey.spec.ts:125` a suggested combination becomes a recorded slip through the page | "the page's own request (legs=3, min_probability=0.6) returned no combination at http://127.0.0.1:8001: (same shortfall as above)" |

The three live-isolated reasons are the runner's own skip annotations, taken from run 8b. The
list reporter does not print them. These are data guards: with the scheduler off and no provider
credentials, the clone's forecasts are never refreshed and have aged out of the suggestion window.
The guards do not point to a fault in this branch. Refreshing the clone (`reset-e2e-db`) was out of
scope for this task. The backend suite had **0 skips**, so no skip of the "target unreachable" kind
occurred.

## Failures and reproduction

**None.** No test failed in any run, so step 5 had nothing to rerun. No test or product code was
changed in this task.

## QA inventory (`soccer_predictions_e2e`, read-only)

"This round" means `created_at` after 2026-10-20 23:00 UTC. All statements were SELECTs, run
inside `BEGIN TRANSACTION READ ONLY … ROLLBACK` with `default_transaction_read_only=on`.

- **QA accounts created this round: 1.** `qa_account_forms` (REGULAR, ACTIVE, 2026-10-21 00:20:55
  UTC). The clone holds 4 QA accounts in all: `expert_phase1`, `qa_expert_local`,
  `qa_codex_expert_20261020` (created 2026-10-20 22:40, just before the cut-off) and
  `qa_account_forms`. None of them is soft-deleted.
- **Non-deleted predictions owned by QA accounts: 0.**
- **Predictions created this round: 303.** All belong to `qa_expert_local`, all are
  `EXPERT_MANUAL`, and **all 303 are soft-deleted**. 43 of them were created during these final
  runs, after 07:04:21Z.
  - 290 are classified `is_test_data = true`.
  - 13 carry no classification (NULL). All 13 have the reasoning `[e2e-qa] home side has the
    stron…`. That is the record `expert-publishing.spec.ts` "the QA label in the reasoning is a
    label, not a mechanism" creates on purpose with `is_test_data: false`, and the cleanup helper's
    legacy-label fallback removes it. That test makes one such record each time it runs.
  - No other account created a prediction this round.
- **Audit rows created this round:**

  | Table | Action | Rows |
  |---|---|---:|
  | `audit.audit_log` | CREATE | 303 |
  | `audit.audit_log` | DELETE | 303 |
  | `audit.audit_log` | UPDATE | 30 |
  | `audit.audit_log` | PUBLISH | 13 |
  | `audit.audit_log` | ARCHIVE | 13 |
  | `predictions.prediction_audit` | updated | 30 |
  | `predictions.prediction_audit` | publication_changed | 26 |
  | `audit.prediction_change_log`, `audit.user_action_log`, `audit.admin_action_log`, `audit.system_event_log`, `audit.data_access_log`, `audit.data_export_log`, `audit.gdpr_consent_log`, `users.user_activity_log`, `users.admin_activity_log` | — | 0 |

  Every `audit.audit_log` row has resource type `prediction` and a QA account as actor. Every
  `prediction_audit` row is on a QA-owned prediction. The 26 `publication_changed` rows are the
  13 ARCHIVE rows plus the 13 PUBLISH rows.

## Notes

- The expert journey ran inside run 8 and passed. It asserts that neither of its browser contexts
  sent a request to :8000 or :3100. It restored the QA expert's first name to "QA" and left 0 QA
  predictions behind.
- The journey logged two observations, which are not assertions: the preview does not show the BTTS
  conviction (65%) or the goal-line conviction (60%) typed in the composer. The earlier evidence run
  `journey-run-2.log` logged the same two.
- Not run, as the task rules require: `scripts/test_evidence.py`, `e2e:evidence`, `reset-e2e-db`.
  Nothing was sent to :8000 or :3100. None of these runs was configured to use the live database
  or live Redis:
  - **Run 1.** It passed the test database and the throwaway Redis :6390 literally on the command
    line.
  - **Runs 8, 8b and 9.** They went through the isolated backend :8001, which uses
    `soccer_predictions_e2e` and Redis databases 10–15 on the shared Redis server.
  - **What this rests on.** Those settings, not a capture of connections, and it covers these
    final runs only.

  (Narrowed on 2026-10-21. The environment slip of 2026-10-20 is in
  `redis-incident-2026-10-20.md`.)
- Logs write the worktree path as `<worktree>` and the home prefix as `~`. Terminal colour codes
  are stripped. The test database password is masked as `***` in the backend log header. The
  logs hold no tokens or passwords.
