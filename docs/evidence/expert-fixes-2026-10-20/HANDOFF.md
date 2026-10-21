# Expert-profile corrections: isolated handoff (2026-10-21)

Branch `expert-fixes`, from live `96c22edd`. Implemented and tested **only** on the isolated pair:
- frontend :3101 and backend :8001, run from this worktree;
- database `soccer_predictions_e2e`, Redis DBs 10–15;
- scheduler off, email off, provider keys blank.

Not merged into `main` or `progress`, not deployed, and live was never restarted.

## Status per issue

**1. Profile editing (P1): Fixed.**
- **Behaviour.** Edit opens the form and sends nothing; this is true for mouse, Enter and Space.
  Cancel restores the original values and sends nothing. Save sends exactly one PUT, and a double
  click still sends one.
- **Header.** It updates without a reload, through `refreshUser`, and the change survives a reload.
- **Names.** A blank optional name is sent as null and clears the field. An account with no names
  can still change its username.
- **Labels and errors.** Every field is labelled. A failed save keeps the edits, and a retry sends
  exactly one more PUT.
- **Tests.** `account-forms.spec.ts` (mocked), `account-profile.spec.ts` (live-isolated) and
  `test_users_me.py`.

**2. Lost drafts (P1): Fixed.**
- **Storage.** Drafts are kept per expert and per fixture, and the old single key is migrated.
- **Opening another fixture.** It never overwrites another draft and never carries values across.
- **Removal.** A draft is removed only by a confirmed discard or by publishing it; publishing clears
  only that fixture's draft.
- **No writes.** Draft operations send no write request.
- **Accounts.** One account never sees another account's draft.
- **Tests.** `expert-drafts.spec.ts`, mocked and live-isolated.

**3. Deletion history (P1): Fixed.**
- **Deletion.** The service takes a row lock and does a compare-and-set, so `deleted_at` is written
  once. A repeat returns 200 with `already_deleted: true` and the original time. The audit entry is
  written once.
- **Deleted rows.** They can no longer be edited or have their publication switched (404).
- **Scoring.** A deletion before kickoff that is retried after kickoff keeps the original time and
  stays unscored.
- **Before the fix.** An old-code behavioural run showed a win withdrawn before kickoff being scored
  WON after a retried delete. The race test failed before the fix and passed 20 of 20 after.
- **Through the isolated backend.** Repeated and concurrent DELETEs through :8001 are covered by
  `expert-delete-idempotent.spec.ts` and the journey.

**4. Dashboard and pagination (P2): Fixed.**
- **Counts.** "Not published" = total − published. A separate "Archived" tile is shown, and the
  dashboard counts add up after publish, unpublish and republish.
- **Heading.** It is now "Recent predictions", because the list holds every status.
- **Paging.** `X-Total-Count` drives the paging. Previous stays on an emptied later page. Deleting
  the 21st row steps back to page 1. A filter change resets to page 1.
- **Tests.** Exactly 20 and exactly 21 records are both tested.

**5. Revision history (P2): Fixed.**
- **Markets.** Every market of every earlier version is shown: 1X2, BTTS, 2.5 and 3.5 goals, and
  the convictions.
- **States.** 0 %, "not set" and "not recorded" are kept distinct.
- **Changes.** Readable, translated change sentences replace the raw field strings, built from a
  new structured `changes` payload.
- **Checked.** The journey compares the shown values against the stored revision.

**6. French and forecast labels (P2): Fixed on the expert surfaces.**
- **French.** The picker, editor, validation, preview and evidence panels are French in French,
  with French number formatting.
- **Kickoff times.** They are shown in the chosen time zone (Douala checked).
- **Forecast badge.** It tells current, out of date, kept for reference and none apart.
- **Sizes.** Checked at 1440, 390 and 360 px.
- **Still English.** Remaining English on reader pages is listed under limitations.

**7. Password change (P2): Fixed (copy and session).**
- **This browser.** A successful change signs this browser out: tokens are cleared, its refresh
  token is blacklisted, and the user lands on a working login page.
- **Copy.** It promises only what happens. Other browsers and devices already signed in are not
  signed out; this was observed and tested, not claimed.
- **Tests.** Wrong current password, mismatched confirmation, a successful change, a login with the
  new password, and a login with the old password failing.

**8. Consistent expert management (P2): Fixed within scope; the profile page is a proposal.**
- **My Predictions.** Unpublish and Publish are now on My Predictions as well as the dashboard,
  with a confirmation and an after-kickoff note.
- **Public byline.** Public cards say "By {username}". Email, names and avatar are never served.
- **Not-scored labels.** A prediction published at or after kickoff is labelled "not scored". So is
  one withdrawn before kickoff and republished after it. Each label follows settlement's own rule
  and appears both publicly and in the expert's own views.
- **Public profile.** The smallest public expert profile is written up separately in
  `docs/design/public-expert-profile-proposal.md` and not implemented.

## Proof that each fix was needed

Every defect has a regression that failed on the previous code and passes on the fix. The logs are
in this folder.
- `*-before-*.log`: the failing runs.
- `*-after-*.log`: the passing runs.
- `review-fix-before-*` and `review-fix-after-*`: the 21 findings that survived the skeptics in the
  independent five-lens review (two skeptics per finding).

## Final runs on the finished tree

All runs are on the finished tree; see `FINAL-RUNS.md` and `final-*.log`.

| Run | Passed | Failed | Skipped | Exit |
|---|---:|---:|---:|---:|
| Backend, full suite (isolated targets, explicit env) | 1895 | 0 | 0 | 0 |
| Type-check / lint / build | – | – | – | 0 / 0 / 0 |
| Mocked desktop (1440 px), all | 547 | 0 | 2 | 0 |
| Mocked mobile (390 px), all | 549 | 0 | 0 | 0 |
| Mocked 360 px, all | 199 | 0 | 0 | 0 |
| Live-isolated, whole project | 63 | 0 | 3 | 0 |
| Existing expert-composer + expert-publishing | 10 | 0 | 0 | 0 |
| Real UI journey (2 runs, 24 screenshots in `journey/`) | 1 + 1 | 0 | 0 | 0 |

**Baseline at 96c22edd.**

| Run | Result |
|---|---|
| Backend | 1811 passed |
| Gates | exit 0 |
| The two expert suites | 10 passed |

**Skips.**
- Desktop: 2. These are menu-button tests that cannot run at 1440 px; they pass at 390 and 360.
- Live-isolated: 3. These are parlay and suggestion journeys that need fresh stored forecasts. The
  e2e clone holds only out-of-date ones, because its scheduler is off and it has no provider keys.

**The journey.** Every journey step was taken through the UI:

1. Wrong-password refusal, then sign-in.
2. Profile edit.
3. Choose a fixture.
4. Invalid input blocked.
5. Draft restored after a reload.
6. Preview.
7. Publish (exactly one create request).
8. Anonymous public view, then a reload.
9. Edit.
10. History checked against the payload.
11. Unpublish.
12. Republish, with the original time kept.
13. Delete, plus a repeated DELETE through :8001 with the same `deleted_at`.
14. Empty filter page.

API checks only supplemented the UI steps. Neither browser context sent any request to :8000 or
:3100.

## Isolated runtime identity (measured)

**Backend :8001.**
- Working directory: this worktree's `backend`.
- `/health` commit `2759f592`, `app_tree_sha256 7138445e…` over 91 files, none dirty. This matches
  the checkout.
- Database `soccer_predictions_e2e`.
- Environment: `SYNC_SCHEDULER_ENABLED=false`, `EMAIL_ENABLED=false`, provider keys empty, Redis DBs
  10–15.

**Frontend :3101.** Working directory: this worktree's `frontend`, `--mode dev8001`.

The isolated pair is **left running on this branch** so the fixes can be checked in isolation. To
return it to the main checkout:
1. `<worktree>/scripts/local-servers.sh stop isolated`
2. `scripts/local-servers.sh start isolated`, from the main checkout.

## Live runtime and limits: unchanged

The live state was read only, before (`live-before.txt`, 2026-10-20 23:03 UTC) and after
(`live-after.txt`, 2026-10-21 07:51 UTC). The two are identical:
- **Identity:** `96c22edd`, the same process started 2026-10-20 01:01:47 UTC (pid unchanged).
- **Frontend :3100:** the same pid.
- **Refs:** `main`, `origin/main` and `origin/progress` are all `96c22edd`.
- **Checkout:** clean.
- **Data containers:** not restarted.
- **Ceilings:** GameForecast 8, Live Score 1,200, API-Football 90, TheSportsDB 1,000.
- **Provider counters:** the 2026-10-20 counters are unchanged.
- **Vite cache:** the live dependency cache is untouched.

No provider request was made by this work.

**One environment slip, disclosed.**
- **What happened.** In two intermediate backend before-runs, an unquoted shell variable dropped the
  test settings. That left the Redis target at the `.env` default, which is live.
- **The code reading.** The tests in those runs reach no Redis command: client construction is
  lazy, cache invalidation is log-only, and authentication was overridden. Their database fixtures
  used `soccer_predictions_test`.
- **The conclusion.** Nothing reached live. This is established by reading the code, not by
  observation.
- **The logs.** Both were re-run and replaced with explicit settings.

## QA data left on the e2e clone

The only data this work wrote is on the clone; the inventory was taken with read-only SELECTs.
- **Accounts.** One new QA account, `qa_account_forms` (regular user). Accounts cannot be deleted
  through the API.
- **Predictions.** 303 QA predictions, all owned by the QA expert and all soft-deleted. 0
  non-deleted QA predictions remain.
- **Audit history.** These rows are intentionally kept as evidence:
  - `audit.audit_log`: CREATE 303, DELETE 303, UPDATE 30, PUBLISH 13, ARCHIVE 13;
  - `predictions.prediction_audit`: updated 30, publication_changed 26.

## Limitations and decisions for the owner

1. **Public username.**
   - Cards show the username, which the measured record already publishes. But registration
     auto-generates a username from the email's local part when none is given.
   - The frontend hides any username containing "@", but the backend still serves it.
   - Decision: require an explicit public username, or add a display name (see the proposal).
2. **Session hardening is not done, as scoped.**
   - Access tokens stay valid until they expire (7 days).
   - `/auth/refresh` checks only the blacklist, so a password change or reset signs out no other
     browser or device. The copy now says so.
3. **Late posting policy is unchanged.** Kicked-off fixtures are still offered and accepted, and are
   labelled "not scored". Refusing them as overrides do is a decision.
4. **Deleted rows elsewhere.** Admin approve/reject, override and test-data classification can still
   act on deleted rows. They cannot move `deleted_at`, so scoring is unaffected. There is no
   database-level write-once guard.
5. **Live rows may already be harmed.** Predictions whose `deleted_at` an old repeated DELETE already
   moved past kickoff are not checked or repaired. A read-only check, and any repair, need your
   approval.
6. **English left on reader pages.** The match-detail expert panel title and badge, the forecast
   badge suffix and the evidence statements are still English, as is "Venue to be confirmed".
7. **French review.** The new French strings have not been reviewed by a native speaker.
8. **Smaller items.**
   - '55 %' is still rejected as a number.
   - The locked-market hint says deletion is needed, although a null now withdraws the market.
   - The preview does not show the per-market convictions for BTTS and goals.
   - The header still shows only the first word of a multi-word first name.
   - The password-reset email templates are not found at runtime, so the built-in text is sent.
     That text makes no logout claim.
9. **Drafts.**
   - Two tabs on the same fixture are last-writer-wins.
   - A tab still running the old bundle could overwrite that same fixture's draft during a deploy.
   - Drafts stay in the browser after logout, keyed to the account.
10. **Not measured.** The tablet range (640–1023 px), and physical devices or Safari.

## Isolation preflight: the bypass review of 2026-10-21

Three reviewers looked for runs that get past the preflight (commit 4f0a2388). The fix is
b6c35b28. Each real bypass has a regression that fails on a84affd3 and passes on b6c35b28. Every
regression runs behind tripwires, aimed at ports nothing listens on.

| Bypass | Outcome | Evidence |
| --- | --- | --- |
| `pytest --noconftest` (or `--confcutdir=scripts`) on `scripts/test_connections.py`, or any collectable file outside `tests/` | Fixed. `app/core/config.py` runs the guard under pytest. The six scripts are now `check_*.py`, with no `test_*` functions. | `bypass-*-backend.log`, `bypass-*-reviewer-commands.log` |
| `--import-mode=importlib` with `--confcutdir=tests --rootdir=..`, or `--noconftest -c /dev/null` (`tests/__init__.py` becomes a placeholder and never runs) | Fixed. The guard is the first statement of `tests/conftest.py` and also runs from the settings module. `redis_url_for` moved to `app/core/redis_urls.py`, so the check can no longer end in an ImportError. | same |
| `backend-isolated` in launch.json runs no guard, and `/health` names a database the driver does not use (`#` or `?` in the password, `?dbname=`) | Fixed. The entry runs the guard before uvicorn. `/health` reports the database the driver actually uses, or `null`, which Stage B refuses. | `bypass-*-backend.log`, `bypass-after-isolated-entry.log` |
| Mocked runs load their pages from the live frontend :3100 by default (reported twice) | Fixed. Stage A refuses :3100 for mocked runs. Mocked runs default to :3101 and are not defined beside `live`. The evidence runner sends mocked runs to the isolated frontend. | `bypass-*-browser-specs.log`, `bypass-*-test-evidence.log`, `bypass-after-mocked-defaults.log` |
| `playwright test -c e2e/live`, or specs named from the repository root (default config, no globalSetup) | Fixed. A PASS issues a run token. Workers check it when they load the config, in `live-test.ts` and in both API helpers. | `bypass-*-browser-refusal-runs.log` |
| Watch mode (`PWTEST_WATCH`) and UI mode run tests after a failed global setup | Fixed by the same token, which is shown with a configuration that drops globalSetup. Watch and UI mode themselves were not run, as instructed. | same |
| A checkout whose directory ends in `mocked` or `live` (testMatch is matched against the absolute path) | Fixed. Each project now selects only its own `testDir`. | same, the `--list` cases |

Not done here: the isolated backend :8001 (pid 13053) was not restarted, so it still runs the
pre-fix code. For its configuration the fixed `/health` gives the same answer,
`soccer_predictions_e2e`. Its next start through local-servers.sh or launch.json runs the guard.
