# Correction round on `fixture-cadence`: evidence for a replacement, request-timed re-checks, every reference, and the browser

Branch `fixture-cadence`, this round's commit on top of `3dc5710f`. **Isolated, verified in isolation. Not merged,
not deployed; the live duplicate is not repaired.** Live (`45c8b0cf`, pid 40159, started 2026-10-25T06:13:31Z),
`main`, `progress`, `origin/main` and the four ceilings (GameForecast 8, Live Score 1,200, API-Football 90,
TheSportsDB 1,000) are as they were; section 6 says how that was checked. The first round's report is one level up.

## 1. Fixture matching: a replacement needs evidence, and the record says what was observed

**The reviewer's reproduction.** An overdue SCHEDULED fixture with no result was accepted as superseded even when its
old provider id had just been named again, and the record then said the provider had "stopped listing" it. True:
`3dc5710f` took elapsed time plus a missing result as withdrawal. `tests/before-3dc5710f.log` shows it joining the
reviewer's case ("joined on elapsed time alone - the previous implementation's defect").

**What holds now** (`backend/app/services/match_registry.py`, `match_data_service.py`,
`providers/livescore_api.py`):

- The registry now **observes** what each fresh provider listing says (`MatchRegistry.observe_listing`, recorded
  under `match_metadata.listings.<provider>`): every stored row the listing names is marked `seen_at`; and when the
  listing is a **complete listing of one day's fixtures** - straight from the provider (`meta.source == "provider"`,
  never a cached or stale copy), every page read (Live Score now reports `truncated_keys` for a competition whose
  pages it stopped reading; a provider that cannot say records nothing) - every stored SCHEDULED or POSTPONED row of
  those competitions on that day that the provider links to under an id the listing does not name is marked
  `absent` (first `since`, `last`, `listings` count, `day`). The day sync calls it **before** storing a single
  fixture of the batch, so what it records does not depend on the order the fixtures come in. Live polls and
  calendars mark `seen` only. An outage, an incomplete page set, a cached or stale copy, a listing of another day or
  competition, and a day the provider could not be asked about record nothing about absence.
- A re-issued listing joins its earlier row **only when the earlier row's withdrawal was observed**: an absence
  recorded after the provider last named it, with nothing naming it since (`withdrawal_observed`). The provider
  naming the old id again - minutes before the new one, or both ids in one batch in either order - contradicts a
  replacement and the fixture is stored as a new row, the candidate written on it with the reason ("its withdrawal
  has not been observed: no complete listing of its date by livescore since it was last named (…) is recorded
  without it", or "…is contradicted: livescore named it again at … after a complete listing of its date had not").
  The other conditions stand (a league, identical clubs by row and by the provider's own names, another id, no
  result and the kickoff window closed or POSTPONED, a later kickoff within 14 days, the same round when both name
  one). An absence record is kept when the row is named again, so the contradiction can be stated; it no longer
  counts as an observation.
- The record on a joined row (`match_metadata.superseded_listing`) carries `evidence.basis = "observed"`, when the
  provider last named the earlier id and the absences since, and a reason written from those facts. "Stopped
  listing", "never played", "withdrawn" and "proven" are gone from every message; the tests assert their absence.

**The repair script** (`backend/scripts/repair_duplicate_matches.py`) applies the same standard: each pair prints
its evidence - "withdrawal observed: last named by livescore at …; absent from N complete listing(s) of its date
since (…)" or "withdrawal NOT observed: last named by livescore at …; no complete listing of its date recorded since
without it" - and a pair whose withdrawal was not observed folds only with `--fold-superseded <id>
--reviewed-evidence "<what the person reviewed>"`, which the record keeps (`evidence.basis = "reviewed"`,
`evidence.reviewed`). Nothing is folded by `--apply`. A fold without the required evidence is refused before anything
moves (`repair-rehearsal/03-fold-without-evidence.log`; no table changed).

**The PSG-Lyon repair is a reviewed one, distinct from the automatic rule.** The live rows predate the observation
record, so this installation observed nothing; the evidence a person reviewed, from the live backend log and the
stored row: Live Score's complete Ligue 1 listing of 2026-10-25 made at 23:11:00Z (`fixtures/list.json
date=2026-10-25&competition_id=5`, HTTP 200, one page) did not name fixture 1877019 - the row's `last_synced_at`
stayed at 2026-10-25T17:09:00Z, the 17:08:50Z listing that did name it; no live or results report reached it in 18
asks; Live Score listed 742799 (same clubs, same order, Ligue 1 round 8) on the 26th and it was played 2-0;
GameForecast kept its event 28930 and re-dated it to the 26th. That text was passed as `--reviewed-evidence` and is
in the survivor's record (`repair-rehearsal/07-rows-after.txt`, last block).

## 2. Re-check spacing from the request's own time, per competition

**The reviewer's two cases.** `3dc5710f` remembered only the previous pass's spending and placed inherited spending
at the recovery's completion. Case A (12:00 partial spends one; 12:05 lease-held retry spends zero; 12:15 completed
recovery spends zero): it scheduled 12:12, due at once, and forgot the 12:00 request. Case B (12:12 partial spends
one; the host sleeps; 18:05 completed recovery spends zero): it scheduled midnight and missed 18:12.

**What holds now.** The scheduler-level spacing is gone. The scheduler keeps the pure grid: the next ordinary pass is
the first slot after the pass began, and after a recovery episode the first slot after the interruption
(`_ordinary_due`). The spacing moved to where the request timing lives: the daily-slot policy
(`forecast_refresh_policy.py`, `RECHECK_MIN_GAP = 1 h`) re-checks no competition within an hour of the fetch it
would re-check, measured from that slot's own `fetched_at` - the request's real time, kept in Redis per competition,
which survives restarts, empty retries and the scheduler's timing. So: a slot minutes after a late pass runs and
costs nothing (its re-checks are "served an older run at …; its one re-check of the day waits until at least 60 min
after that fetch"); an owed re-check is made at the first slot an hour or more after its fetch and never disappears
within its day; a fetch at 17:12 permits the 18:12 re-check and 17:13 does not; one competition's fresh fetch never
holds up another's re-check. Case A now: the retry at 12:15 closes the episode, 12:12 is due at once and re-checks
nothing, 18:12 re-checks both competitions. Case B: the recovery at 18:05 spends nothing, leaves Serie A's re-check
to the ordinary pass (`recheck_skipped`), and the next slot is 18:12, where the re-check is made. A re-check blocked
by the gap at the day's last slot (a fetch after 23:12) is not made that day, as a pause outlasting a pass never was.
**This one-hour gap is new behaviour** of October 2026, documented as such in the policy, the setting's comment and
`tests/services/test_forecast_cadence.py`; the week replay keeps pinning the completion cadence it compares under.

## 3. Every reference, demonstrated

`tests/services/test_superseded_listings.py` now seeds, on the earlier listing, a saved match, a published expert
prediction with two audit rows, a settlement record for it (void, "no result stored for the listing"), a saved slip
with one leg on the 25 October snapshot, and a scored-forecast record for the first snapshot - and proves after the
fold that every one of them is on the survivor and otherwise byte for byte as it was (`to_jsonb(row) - match_id`),
that the leg's `snapshot_id` still names a snapshot that is itself on the survivor, that the nine snapshots keep ids,
`first_fetched_at`, `model_run_at`, `kickoff_at_capture` and `captured_before_kickoff` (the 26 October one stays
false), that the counts of `prediction_results` and `provider_forecast_results` do not change (no re-scoring), that
no provider ref is orphaned, that a bystander row is byte for byte unchanged, that the dry run changes no table, that
a second application changes nothing, and that a move which would break a unique key (a current forecast from the
same provider on both rows) is refused with every table as it was. The rehearsal on a fresh copy of live
(`repair-rehearsal/`, copy taken 2026-10-28T02:08Z) shows the same for the real rows: nine snapshots identical apart
from `match_id` (`10-snapshot-comparison.txt`), four refs on the survivor, orphan refs 0, four tables changed and no
other, a second application changing nothing.

## 4. The browser, on a disposable pair

A **disposable pair** - backend `127.0.0.1:8002` on the folded copy `psg_lyon_repair2` (throwaway PostgreSQL
`repair-pg`, 127.0.0.1:5441) and a throwaway Redis of its own (`disposable-redis`, 127.0.0.1:6391, databases 10-15),
frontend `localhost:3102` calling it - started by hand with every target on the command line, no provider credential
(`DATA_PROVIDER=livescore`, `PREDICTION_PROVIDER=gameforecast` as live, keys empty), scheduler off. The policy
(`backend/app/core/isolation_targets.json`) gained a `disposable-backend` role and a `browser.disposable` side, which
the backend's own guard approved before start (`python -m app.core.target_guard --role disposable-backend`) and
which the browser tests select with `E2E_ISOLATED_SIDE=disposable` (`frontend/e2e/support/target-policy.ts`, one
function). The shared isolated pair on :8001/:3101 and the live pair were not touched; the Playwright isolation
preflight passed (`browser/playwright-run.log`, policy sha256 b53f554c6514) and a first attempt that named the
disposable API as the main API was refused by it, as it should be (`browser/playwright-refused-same-origin.log`).
The code under test is identified by its application-tree digest (`browser/backend-identity.json`,
`app_tree_sha256 = 0b43b29a…`, 93 files, equal to the checkout's at the time of the run).

Representative local data written into the copy for the QA reader (the suite's documented local fixture account):
a saved match with a note, a published expert prediction dated 2026-10-25 10:00 (before either kickoff), a saved
slip with one leg on the 25 October snapshot, seeded PENDING.

`frontend/e2e/live-isolated/repaired-fixture.spec.ts`, **6 passed, 0 failed, 0 skipped**, proves exactly this:

- the API describes one row: kickoff `2026-10-26T19:30:00Z`, finished, 2-0 (0-0 at half-time), `livescore:742799`,
  provider refs livescore 742799 and 1877019 and gameforecast 28930, the gameforecast forecast for event 28930 with
  `forecast_state = kickoff_passed`, the published expert prediction; the folded id answers 404;
- the fixture page shows the scoreline 2-0, both clubs, under "Where this fixture came from" the kickoff
  `2026-10-26 19:30:00` and provider id 742799, and the model forecast "for reference" with its provenance; the
  folded id's page shows no scoreline and no forecast; no console error, failed request or failing API answer;
- the Ligue 1 day list for the 26th (viewer's day) carries exactly one card for the match, linking to the surviving
  id, scored 2-0; the list for the 25th carries none;
- signed in as the reader: the dashboard's saved matches show the match with its note; the fixture page shows the
  expert prediction's panel and byline, no late-publication mark, the saved state; the slip history shows this
  round's slip with one leg on the match whose state equals what the API stores for it;
- reloading the fixture page and the slip history changes nothing;
- on a phone viewport (390×844, touch), the fixture page has no horizontal overflow and the day list carries the one
  card, with no console or network failure.

**What the browser does not prove, and one thing to read with care.** It shows the pages against the copy, not
live. The slips endpoint settles every slip it returns against stored results and commits (its standing rule): the
first read settled the seeded leg from pending to **won** against the 2-0 the row now holds (`settled_at`
2026-10-28T02:17:39Z, written by the endpoint, not by this round) - which is exactly the consequence the repair
script prints for a person: a leg placed on the 25 October listing's forecast is scored against the match played on
the 26th. The spec asserts that the page shows the state the row holds; it did not manufacture that state. The
expert prediction's own settlement did not run (scheduler off), so it shows as published and unsettled. The forecast
is shown "for reference" because the match has been played; the 26 October snapshot keeps `captured_before_kickoff
= false`, and re-evaluating that flag stays outside this round. Screenshots: `browser/match-desktop.png`,
`match-mobile.png`, `list-2026-10-26-desktop.png`, `list-2026-10-26-mobile.png`.

## 5. Results, counted separately

| run | passed | failed | skipped | errors | log |
|---|---|---|---|---|---|
| **Before**: this round's two test files against `3dc5710f` (detached worktree, same files) | 46 | 22 | 0 | 0 | `tests/before-3dc5710f.log` - the reviewer's case "joined on elapsed time alone"; case B "18:12, not midnight: the grid counts from the interruption"; case A fails at the other worker's pass, which re-checked Serie A five minutes after its fetch (the spent re-check the gap now prevents); the observation tests fail because nothing was recorded |
| **After**: the affected suites (`test_superseded_listings` 37, `test_forecast_cadence` 30, `test_forecast_recovery`, `test_sync_scheduler`, `test_forecast_refresh_policy`, `test_relisted_fixtures`, `test_duplicate_fixtures`, `test_match_identity`, `test_scheduler_recovery`, `test_match_data_health`, `tests/providers`) | 560 | 0 | 0 | 0 | `tests/after-affected-suites.log` |
| **Full backend suite**, isolated targets, final code | **2086** | **0** | **0** | **0** | `tests/full-suite.log` |
| the same suite's first run | 2077 | 1 | 0 | 8 | `tests/full-suite-first-run.log` - the one failure was mine: a launch file I had written for the disposable pair had overwritten the tracked `.claude/launch.json` a guard test reads (restored with `git checkout`, never committed); the 8 errors were the real-Redis lease tests refusing a throwaway Redis that still held keys the disposable backend had written while it shared that server |
| the same suite's second run | 2078 | 0 | 0 | 8 | `tests/full-suite-second-run.log` - the leftover keys again; the disposable pair was moved to a Redis of its own and the throwaway test Redis emptied before the final run |
| Repeats: cadence, superseded listings, forecast recovery, sync lease, sync concurrency, real-Redis lease, scheduler recovery, 20 consecutive runs | **152 × 20** | **0** | **0** | 0 | `tests/repeats-summary.txt` |
| Browser: `repaired-fixture.spec.ts` on the disposable pair, desktop and phone | **6** | **0** | **0** | 0 | `browser/playwright-run.log` |

How every pytest run was isolated: the guarded runner names the test database `localhost:5432/soccer_predictions_test`,
the throwaway Redis `127.0.0.1:6390` and PostgreSQL `127.0.0.1:5440/forecast_race_test` on the command line, sets every
provider key empty and points `HTTP(S)_PROXY` at a closed local port; the guard's approval line heads every log. The
repair rehearsal ran against `127.0.0.1:5441/psg_lyon_repair2` only.

## 6. What did not change, and how that was checked

Live: `GET /health` on :8000 before and after this round reports `45c8b0cf`, tree `64b40006…`, started
2026-10-25T06:13:31Z, the one listener pid 40159; it was never restarted or signalled; live's PostgreSQL was read
once (`pg_dump`, for the copy) and its Redis not touched. `main` = `progress` = `origin/main` = `45c8b0cf` before and
after; the main checkout is clean; `.claude/launch.json` is as committed. The ceilings are settings no file on this
branch changes. No provider request was made: credentials empty everywhere, proxies closed, transports mocked.

## 7. Limitations and decisions for the owner

- The live duplicate stands until the fold is applied to live under its own authorisation - with the reviewed
  evidence above as `--reviewed-evidence`, after a dry run - and until then the recovery sweep keeps asking about the
  earlier listing every six hours. Applying it will make a reader's slip leg on the 25 October forecast settle
  against the 26 October result the next time it is read, as the rehearsal showed; whether that should stand is a
  separate decision, as is scoring the 26 October snapshot.
- The automatic rule can only join a re-issue once a complete listing of the earlier row's date has been observed
  without it; a provider that re-issues on the same day before any such listing leaves two rows for the script.
  The observation record starts now: nothing is known about rows listed before this round.
- The one-hour re-check gap is a policy change, simulated only. The cadence and recovery behaviour are simulated;
  nothing on live has run this code.
- The disposable pair and its containers (`repair-pg`, `disposable-redis`, `guard-test-redis`, `guard-race-pg`)
  are local throwaways; `repair-pg` holds copies of live data (users included) and should be removed when no longer
  wanted. The `.env.dev8002.local`, start scripts and launch entries for the pair are gitignored working files.
