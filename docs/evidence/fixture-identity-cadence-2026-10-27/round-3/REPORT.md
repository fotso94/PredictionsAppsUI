# Narrow correction round on `fixture-cadence`: every answer is named before it is stored; a listing is as complete as its pages were read

Branch `fixture-cadence`, this round's commit on top of `7e3bac4f`. **Isolated, verified in isolation. Not merged,
not deployed; the live duplicate is not repaired.** Live (`45c8b0cf`, tree `64b40006…`, pid 40159, started
2026-10-25T06:13:31Z), `main`, `progress`, `origin/main` and the four ceilings (GameForecast 8, Live Score 1,200,
API-Football 90, TheSportsDB 1,000) are as they were; section 5 says how that was checked. The recovery-scheduling
changes of the previous round were not touched. Rounds 1 and 2 are reported one level up and in `round-2/`.

## 1. The two defects and the two fixes

**Defect 1 - answers stored before they were named.** Of the ingestion paths, only the day listing and the live poll
told the registry what the answer named before storing it; the calendar (`sync_upcoming`) and the results import
(`_sync_results`, which the results task, the fixtures task's way out of `sync_day`, a reader's refresh and the
recovery sweep all go through) stored first. With an absence recorded against the earlier listing, an answer that
carried the new id before the old one let the new id join the earlier row on an absence the very same answer
contradicted, and then refused the old id as superseded. **Fix** (`backend/app/services/match_data_service.py`,
+13 lines): both paths now call `_observe_seen` before `_store_fixtures`. The audit of every path that stores
provider fixtures: `sync_day` (day listing: `_observe_day_listing`, presence and - from a fresh, complete listing
- absence), `_sync_live` (`_observe_seen`), `_sync_results` (`_observe_seen`, this round), `sync_upcoming`
(`_observe_seen`, this round); no other caller of `_store_fixtures` or `upsert_fixture` exists in the application
or the scripts. `_observe_seen` marks presence only, attributed to the provider that answered (`meta.provider`),
and only for a fresh answer (`meta.source == "provider"`): a cached or stale copy, a failed round and an incomplete
page set name nothing new, and no calendar, live or results answer ever creates absence evidence because an id is
missing from it.

**Defect 2 - an empty page taken for the end of the list.** `LiveScoreAPIProvider._paginate` stopped at an empty
page even when the provider advertised another (`next_page` or `total_pages`), left its truncation flag false, and
the day observer took the answer for a complete listing: a fixture on page two was never read and its absence was
recorded. **Fix** (`backend/app/services/providers/livescore_api.py`, one condition): the loop ends where the
provider says the list ends, or at `MAX_PAGES` (5, unchanged), which marks the answer cut and keeps it from being
absence evidence. No page cap, request limit or retry count was raised; an empty page with nothing further
advertised is still a complete listing and a valid observation.

## 2. Regressions, through the real paths (`backend/tests/services/test_listing_observation_paths.py`, 11 tests)

Every test drives the real `MatchDataService` over the real `LiveScoreAPIProvider` with a mock transport that
answers in Live Score's shapes and records every request, so each asserts the calls made as well as the state left.

| case | calls asserted | state asserted |
|---|---|---|
| calendar names both ids, old first / new first | one `fixtures/list.json` page | two rows; the earlier row keeps its kickoff, nine snapshots, both its refs and no `superseded_by`; its `seen_at` is the answer's time and no withdrawal stands; the new row carries the new id and nothing of the earlier row; no refusal |
| results answer names both ids finished, old first / new first | one `matches/history.json` call for the 25th | two rows; the earlier row FINISHED 2-0 with its snapshots and refs, the new row its own 2-0 and no snapshot; no refusal, no withdrawal standing |
| calendar names only the new id after an observed absence | one page | the re-issue joins the earlier row with everything on it (the passing replacement) |
| empty first page with `next_page`, old id on page two | pages 1, 2 | seen; absences unchanged at 1; a later re-issue does not join; the earlier row as it was |
| empty page in the middle, more advertised | pages 1, 2, 3 | seen; absences unchanged |
| `total_pages` form of an empty first page | pages 1, 2 | seen; absences unchanged |
| every page up to the cap empty and advertising more; old id beyond the cap | pages 1-5 only | answer cut; absences unchanged; not seen |
| page two answers HTTP 500 | pages 1, 2 | an error, no observation either way |
| one empty page, nothing further advertised | page 1 | absence observed again (2); the re-issue then joins |

**Before / after.** The same file against `7e3bac4f` (detached worktree): **9 failed, 2 passed, 0 skipped** -
the calendar cases with one row instead of two ("the new id was merged onto the earlier row on an absence the same
answer contradicted"), the results cases with a merge in one order and the absence still standing after the answer
named the id in the other, the pagination cases with only page 1 requested (page two "never read"), the cap case
with one page asked and an absence recorded, the failing-page case with no error raised (`tests/before-7e3bac4f.log`).
Against the fix: **11 passed, 0 failed, 0 skipped** (`tests/after-new-tests.log`).

## 3. Results, counted separately

| run | passed | failed | skipped | errors | log |
|---|---|---|---|---|---|
| Before: the new file against `7e3bac4f` | 2 | 9 | 0 | 0 | `tests/before-7e3bac4f.log` |
| After: the new file | 11 | 0 | 0 | 0 | `tests/after-new-tests.log` |
| Affected ingestion, provider and matching suites (the new file, `test_superseded_listings`, `tests/providers`, `test_match_data_health`, `test_relisted_fixtures`, `test_duplicate_fixtures`, `test_match_identity`, `test_match_matching`, `test_scheduler_recovery`, `test_sync_scheduler`, `test_forecast_recovery`, `test_forecast_cadence`, `test_recovery_real_payload`, `test_provider_chain`, `test_fixture_pipeline`) | 672 | 0 | 0 | 0 | `tests/affected-suites.log` |
| Full backend suite, isolated targets, once after the final edits | **2097** | **0** | **0** | 0 | `tests/full-suite.log` (exit 0) |
| Browser, API and desktop checks (5 tests) on the round's own disposable pair | 5 | 0 | 0 | 0 | `browser/playwright-run.log` |
| Browser, phone viewport (1 test) on the same pair | 1 | 0 | 0 | 0 | the same log |

No concurrency campaign was repeated: this round changes no lock, lease, budget or scheduler code.

Every pytest run went through the guarded runner (test database `localhost:5432/soccer_predictions_test`, throwaway
Redis `127.0.0.1:6390` emptied beforehand, throwaway PostgreSQL `127.0.0.1:5440/forecast_race_test`, provider keys
empty, `HTTP(S)_PROXY` on a closed local port); the guard's approval line heads each log.

## 4. The browser, with care about what it proves

The pair is this round's own: backend `127.0.0.1:8002` on the folded copy `psg_lyon_repair2` (throwaway
`repair-pg` :5441) with its own throwaway Redis (`disposable-redis` :6391), frontend `localhost:3102`, no provider
credential, scheduler off; its source identity was checked before the run - `GET /health` published
`app_tree_sha256 = 31adf8b2…` (93 files), equal to the checkout's digest computed by
`app.core.source_identity.app_tree_digest` (`browser/backend-identity.json`); the isolation preflight passed
(policy sha256 b53f554c6514). The shared isolated pair on :8001/:3101 and the live pair were not touched.

What the six checks of `frontend/e2e/live-isolated/repaired-fixture.spec.ts` show is the **seeded post-repair data
on the copy** as a reader sees it - API and desktop: one row with the played kickoff, the 2-0, both provider ids
and the forecast shown for reference, 404 for the folded id; one card on the 26th and none on the 25th; the QA
reader's saved match, the expert prediction's panel and byline, this round's slip with its leg on the row in the
state the endpoint stores for it (settled "won" by the slips endpoint's own read-time rule, as documented in round
2); reloads unchanged; phone: the fixture page without horizontal overflow and the day list with its one card, no
console or network failure. **That the repair preserved every reference is proven by the backend tests of round 2**
(`test_superseded_listings`: dependent rows compared as `to_jsonb(row) - match_id - updated_at`, i.e. every column
except the moved key and `updated_at`; snapshots compared by id, `first_fetched_at`, `model_run_at`,
`kickoff_at_capture` and `captured_before_kickoff`; settlement and audit rows compared whole), not by the browser.

## 5. What did not change, and how that was checked

Live: `GET /health` on :8000 before and after reports `45c8b0cf`, tree `64b40006…`, started 2026-10-25T06:13:31Z,
the one listener pid 40159; never restarted or signalled; its PostgreSQL and Redis were not read or written this
round (the copy was taken in round 2). `main` = `progress` = `origin/main` = `45c8b0cf`; the main checkout is clean.
The ceilings are settings no file on this branch changes; live's provider status reports 8 / 1200 / 90 / 1000. No
provider request was made: credentials empty everywhere, proxies closed, transports mocked.

## 6. Limitations, and readiness

- The observation record starts with this code: rows listed before it carry nothing, and the automatic rule can
  join a re-issue only once a complete listing of the earlier row's date has been observed without it. The
  PSG-Lyon fold stays a reviewed repair, rehearsed in round 2, not applied to live.
- Reading on past empty pages costs up to `MAX_PAGES` requests for a provider that advertises pages it does not
  fill; the cap is the one that always applied.
- Everything is simulated or on a copy; nothing of this code has run on live.

**Readiness.** The branch is ready for the owner's review and, on their own instruction, for a rollout prepared
with the private rollout tool re-pinned to its head: the two reviewer-found defects of this round and the two of the
previous one each have a reproduction that fails on the implementation before them and passes after, the full
backend suite passes on isolated targets, and the repaired fixture is verified in the browser on a pair of this
round's own. Not ready for anything else: no deployment, merge or live repair is scheduled or authorised here.
