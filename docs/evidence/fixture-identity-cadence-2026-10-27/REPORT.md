# Fixture identity and forecast cadence: two isolated fixes (branch `fixture-cadence`)

Branch `fixture-cadence`, from the live release `45c8b0cf`. **Isolated fix, verified in isolation. Not merged, not
deployed.** Live (`45c8b0cf`, pid 40159, started 2026-10-25T06:13:31Z), `main`, `progress`, `origin/main` and every
request ceiling (GameForecast 8, Live Score 1,200, API-Football 90, TheSportsDB 1,000) are exactly as they were;
section 7 says how that was checked. The live duplicate is **not** repaired; the repair was rehearsed on a copy.

Two defects, both observed on live during the forecast-recovery observation (2026-10-25 → 10-27):

1. **Paris Saint-Germain v Lyon stored twice.** Live Score dropped fixture 1877019 (10-25 19:45 UTC) and issued the
   match again as 742799 (10-26 19:30 UTC). The registry stored a second row, so nine forecast snapshots stayed on a
   listing that never kicked off and the result sat on a row with no forecast.
2. **The forecasts cadence drifted after every host sleep.** The next ordinary pass was scheduled six hours after
   the previous one *completed*; a pass that ran late after a sleep moved every later pass with it (00:12/06:12/12:12/18:12
   became 02:51/08:51/14:51, then 03:34/09:34/15:34/21:34).

## 1. Defect 1: one match, two rows

### 1.1 The facts, verified on the saved evidence and on an isolated copy of live

The copy: `pg_dump` of `soccer_predictions` taken read-only at 2026-10-27T22:04Z and restored into a throwaway
PostgreSQL (`repair-pg`, 127.0.0.1:5441, database `psg_lyon_repair`). The rows as found (`repair-rehearsal/03-rows-before.txt`):

| | row A `1adf0e7d-e682-42e2-bbb2-e5a5ad365752` | row B `93bc3d08-e713-4336-9747-e5e9eb5e00a1` |
|---|---|---|
| kickoff, status | 2026-10-25 19:45 UTC, SCHEDULED | 2026-10-26 19:30 UTC, FINISHED 2-0 (HT 0-0) |
| competition, round | Ligue 1, "8" | Ligue 1, "Regular Season - 8" (API-Football's label, written by the recovery path) |
| created | 2026-10-18 18:29:32Z by the fixtures sync | 2026-10-26 20:56:08Z by the live poll, after kick-off |
| provider refs | livescore 1877019 (provider_id, exact); gameforecast 28930 (name_kickoff) | livescore 742799 (20:56:09Z); api_football 1552800 (21:07:03Z) |
| forecasts | 9 snapshots 10-18 → 10-26 12:14:31Z (the last one the 10-26 model); 1 current forecast | none |
| result | none; `match_metadata.recovery`: 18 asks since 10-25 22:18Z, "fresh_unanswered", next ask 10-27 22:07Z | `match_results` 2-0, H |
| last listed by Live Score | 2026-10-25 17:09:00Z (`last_synced_at`), i.e. dropped before its own kickoff | maintained |

Why they are one match, from the rows alone: the identical two clubs by row id, the same way round, in the same
competition and the same matchday (round 8 under both labels); A was never reported started and never got a result
(the archive for 10-25 answered six rows, none for it); Live Score stopped listing 1877019 before its kickoff and
listed the pairing again a day later under a new id; and the forecast provider kept its event 28930 and re-dated it
(the 10-26 fetch, whose window began on 10-26, returned it and attached the 10-26 model to row A).

### 1.2 Root cause (`backend/app/services/match_registry.py`, `upsert_fixture`)

`candidates_for` looks a fortnight either side, so A surfaced for 742799; `find_match` answered "ambiguous
(rescheduled?)" because the kickoffs are 23 h 45 min apart; and the ambiguous branch then applied the rule *a
provider never gives one fixture two live ids*: every candidate was Live Score's other fixture, so a new row was
written. The rule is right for two live ids and wrong for a dead one, and nothing afterwards reconciles a stale
SCHEDULED listing with a same-orientation successor (`relisting_of` handles only the other-way-round case of
2026-09-25). The recovery sweep then asked results providers about the dead listing every six hours.

### 1.3 Fix A: ingestion (`MatchRegistry.superseded_listing_for`, `_not_superseded_because`, `_note_superseded`)

When every candidate for a new id is this provider's other id, the registry now asks whether **exactly one** stored
row is a listing the provider dropped and re-issued. Every condition is read from stored rows, never inferred from
names or nearby dates:

- the row is in this competition, and the competition is a **league** (`comps.COMPETITIONS[key].is_cup` and
  `is_national_team` both false): only a league meets once a season per venue; a cup replays at the same ground and
  a national-team window can hold two friendlies the same way round, so there two listings may be two meetings;
- it holds the identical two clubs **in this order by row id**, and the provider's own names for them have the
  same team identity as the stored rows' names (a youth, reserve or women's side that resolves to its club's row is
  still another squad);
- it is listed by this provider under **another** id;
- it was **never played**: no `match_results` row, and either SCHEDULED with its kickoff plus `UNSETTLED_GRACE`
  (150 min, the live poll's window) in the past, or POSTPONED; and not closed as the second listing of a played row;
- the new listing kicks off **after** it and within `SUPERSEDED_LISTING_WINDOW` (14 days);
- when both listings name a round, it is the same matchday (`round_number`: "8" and "Regular Season - 8" are 8).

Then the fixture is applied to that row (`matched_by = superseded_listing`): the kickoff follows the provider even
when another provider created the row (`_apply_fixture(..., rekeyed=True)`), the result lands on it, forecasts,
snapshots, predictions and refs **stay where they are**, the dead ref is kept and marked `superseded_by`, the legacy
id column follows the live id, and `match_metadata.superseded_listing` records the previous kickoff, status, legacy
id, last sync and the reason. Two qualifying rows, or none, decide nothing: the fixture is stored as a new row, as
before, with `match_metadata.superseded_listing_candidates` naming each stored listing and why it was not proven
(for the repair script and a person). A dead id the provider sends again with its old kickoff is **refused** (nothing
written, a refusal recorded) rather than dragging the match back to a date it was not played on.

### 1.4 Fix B: repair of a split already stored (`backend/scripts/repair_duplicate_matches.py`)

A new section, *listings dropped and issued again under a new id*, finds pairs by the same conditions from SQL and
plans the fold: the **successor is always the survivor** - it is the listing the provider maintains, with the kickoff
the match was played at, its own refs and its result; the dropped row's dependents (read from the catalogue on every
run, plus the polymorphic refs table) move onto it with their timestamps untouched; the dead ref is kept and marked;
the dropped row's own record (kickoff, status, legacy id, source, round, created_at, the whole `match_metadata`
including its recovery history) is written on the survivor under `superseded_listing.previous`; and the emptied row
is deleted after a recount proves nothing points at it. Blockers that abandon a pair untouched: the dropped listing
holds a result; the rounds differ; two successors or two dropped listings; a unique key the move would break (a
current forecast from the same provider on both rows); a cup or national-team competition. A fold is never implied
by `--apply`: each dropped listing is named with `--fold-superseded <match id>`, a person's decision per pair.

Two consequences are printed for a decision, never resolved by the script: predictions, slip legs and saved matches
made for the dropped listing's date move to a match played on another date (the next settle pass would score them);
and a snapshot retrieved after the dropped kickoff but before the match was played keeps `captured_before_kickoff
= false` as captured, so settlement will not score it unless re-evaluated - no timestamp is moved to make it prematch.

### 1.5 The isolated repair, as rehearsed (`repair-rehearsal/`)

| step | what happened | file |
|---|---|---|
| dry run | 2 pairs found: PSG-Lyon (safe: move 9 snapshots, 1 forecast, 2 refs; one consequence) and Kyrgyzstan v Lebanon, National Teams Friendlies (**refused**: not a league competition, a person decides); nothing folded without a name; the pre-existing sections report their own findings (a duplicate club, two duplicate fixtures, one clash) untouched | `01-dry-run.log` |
| dry run changed nothing | per-table row counts and digests identical before and after | `checksums.sh` |
| the fold, `--fold-superseded 1adf0e7d-…` | moved {snapshots 9, provider_forecasts 1, provider_entity_refs 2}; deleted 1 row; exit 1 because the other sections still report things for a person | `04-fold.log` |
| what changed | exactly four tables: `predictions.matches` (594 → 593), `provider_entity_refs`, `provider_forecast_snapshots`, `provider_forecasts` (match_id only) | `checksums-diff-before-vs-after-fold.txt` |
| every reference | the 9 snapshots on B with `first_fetched_at`, `model_run_at`, `kickoff_at_capture`, `captured_before_kickoff` and ids identical to before (diff empty apart from `match_id`); the current forecast on B; refs on B: gameforecast 28930, livescore 1877019 (marked `superseded_by` 742799), livescore 742799, api_football 1552800; B's kickoff, status, result and legacy id untouched; A gone; orphan refs 0 | `03-rows-before.txt`, `06-rows-after.txt` |
| second application | "no dropped listing with this id was found; nothing done"; no table changed | `07-second-application.log`, `checksums-diff-after-fold-vs-second-application.txt` |

The 10-26 12:14:31Z snapshot (the day's model, retrieved seven hours before the real kick-off) is now on the played
row but still `captured_before_kickoff = false`, as the script said it would be: a separate decision.

## 2. Defect 2: the cadence drifted

### 2.1 Root cause (`backend/app/services/sync_scheduler.py`, `_record` and `_record_skip`)

`next_due_at = now + interval` on every completed pass, `now` being completion. On live: the host slept across the
10-26 18:14 pass; it ran at the wake, 20:51, and the next one at 02:51 - then 08:53 - and after a second sleep on
10-27 the day's first post-noon pass ran at 15:18 (interrupted; retried 15:34), the next at 21:34. Nothing ever
moved the cadence back, and a fixture kicking off between the 12:00 UTC publication hour and a pass that had
drifted to 15:34 would have missed the day's model.

### 2.2 Fix: ordinary passes on a fixed UTC grid

- **Anchor** `SYNC_FORECASTS_SLOT_ANCHOR_UTC = "12:12"` (new setting, `backend/app/core/config.py`), slots every
  `SYNC_FORECASTS_INTERVAL_SECONDS` (6 h): 00:12, 06:12, 12:12, 18:12 UTC. Why 12:12: twelve minutes past the
  observed publication hour (`SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR = 12`; every same-day run since 10-22 was obtained at
  12:09-12:14 UTC), so the day's first eligible pass follows the gate closely, and it is the cadence live kept from
  the deployment until the first sleep. An interval that does not divide a day, or an empty anchor, falls back to the
  interval from completion.
- **After a completed pass**, `next_due_at` is the first grid slot after the pass **began** (`_ordinary_due`). A
  pass that ran late keeps the grid where it was: a sleep across any number of slots costs exactly one catch-up pass
  (the one due when the host slept), after which the slots stand. A pass that **spent requests** is followed by the
  first slot at least `FORECASTS_SLOT_SPACING_SECONDS` (1 h) after it ended instead: a slot minutes after a fetch
  could only re-check what was just fetched, and the policy allows one re-check a day per competition. A pass that
  spent nothing and crossed a slot (a long pass, a pre-gate catch-up at 11:58) is followed by that slot at once, once.
- **Recovery retries are not slots.** `_schedule_forecast_retry` is untouched (5, 10, 20 minutes; `paused_until`
  floor; episode persisted in Redis across midnight and restarts). When a pass closes an episode the grid resumes
  from the interruption (the episode's `started_at`), inheriting the interrupted pass's spending.
- **A spent allowance** (`_record_skip`) waits for the next slot, at most six hours away and twelve minutes after
  the budget reset. **A failed pass** keeps the existing backoff (6 h, clamped to the reset, floored by a pause) and
  is never a refresh (`last_success_at` untouched); the pass that succeeds after it returns to the grid.
- Nothing else changed: the publication gate, one slot per UTC day per competition, the re-check rule, pauses, held
  leases, the lock and the other five tasks' intervals are as they were. The cadence decides only *when* the policy
  is offered a pass, never what it may buy.

### 2.3 Expected behaviour on live (simulated, not observed)

Passes at 00:12 / 06:12 / 12:12 / 18:12 UTC; the two before noon buy nothing, 12:12 buys the day's run for the five
leagues (5 GameForecast requests), 18:12 re-checks only slots that were served an older run. The 10-27 incident on
the grid: the 12:12 slot runs at the wake (15:18, interrupted), the retry runs when the host is awake (15:34, one
request), the next ordinary pass is **18:12** - not 21:34. Requests per day are unchanged by the cadence (the policy
spends them; the grid never adds a fetch). None of this has been observed on live: the branch is not deployed.

## 3. Regression tests (decisive against the previous code)

`backend/tests/services/test_superseded_listings.py` (26 tests, PostgreSQL): the incident reproduced with its public
values through the real registry; the join (one row, re-dated, result on it, nine snapshots with their timestamps,
both livescore refs with the dead one marked, the note); repeated ingestion; the dead id re-sent (refused); a
POSTPONED listing re-issued; and what stays two rows: the return leg, another competition, a played listing, a
listing still to be played (and the grace boundary), a different round / the same round in another provider's words,
an earlier kickoff, a fortnight (boundary to the minute), two dropped listings, another squad (by name, and resolved
to the club's row), a cup and a national-team fixture, two live ids of two meetings. The repair: the plan and every
reference, the dry run changing nothing, the fold (timestamps, refs, prediction and saved match moved, the record on
the survivor, no orphan), a second application changing nothing, a bystander row untouched, and the refusals (a
played dropped listing is not even a pair, rounds differ, a forecast collision, a non-league pair, two successors).

`backend/tests/services/test_forecast_cadence.py` (23 tests, fake Redis and clock, no sleeps): the grid; a late pass
followed by the grid not by six hours after itself; a sleep across one slot and across several (one catch-up);
waking before noon, after noon, across UTC midnight; a restart after a delayed pass; a long pass crossing a slot; a
catch-up before the publication hour buying nothing and the noon slot still buying (real `ForecastService` over the
policy harness); already-served competitions ineligible on a catch-up; a fetching pass not followed by a slot
minutes away, a non-fetching one followed by the slot it crossed; a spent allowance; a failed pass; a provider pause;
a concurrent worker; recovery retries keeping their timing and the grid resuming from the interruption, inside a
late pass, and a slot crossed during an episode; the fallback without an anchor; the other tasks.

Two assertions in `test_forecast_recovery.py` that encoded the drifting cadence were updated (the grid after a
retry; the slots after an interruption just before midnight); every other test of that file is unchanged.

| run | result | log |
|---|---|---|
| **Before**: the two new files against `45c8b0cf` (detached worktree, same files) | **30 failed, 9 passed, 3 skipped, 10 errors** - every cadence test fails on the task's state ("next due 2026-10-27 02:51:07; the previous implementation scheduled 2026-10-27 02:51:07, six hours after the delayed completion"), the incident test fails on the rows ("the forecast and the result are on one row - the previous code made a second"), the repair tests error because the previous registry has no `superseded_listing_for` and the previous script no such section; the 3 skips are the grid's own unit tests | `tests/before-new-tests.log` |
| **After**: the two files plus `test_forecast_recovery`, `test_sync_scheduler`, `test_duplicate_fixtures`, `test_relisted_fixtures`, `test_match_identity` | **198 passed** | `tests/after-new-tests.log` |
| Full backend suite, isolated targets (final code) | **2070 passed, 0 failed, 0 skipped**, 72 s | `tests/full-suite.log` |
| The same suite's first run, before two corrections of the round | 2062 passed, 2 failed, 6 errors: six race tests refused the throwaway PostgreSQL because its server listened on 5432 behind host port 5440 (my container, recreated with `-c port=5440`), one test asserted the same port, and `tests/simulations/test_replay_week.py` found the elapsed-interval rule's 39.9-hour gap gone because the replay's scheduler had moved to the grid (the replay now pins the completion cadence it compares under; see section 6) | `tests/full-suite-first-run.log` |
| Repeats: cadence, superseded listings, forecast recovery, sync lease, sync concurrency, real-Redis lease, 20 consecutive runs | **101 passed × 20, no failure** | `tests/repeats-summary.txt` |

## 4. How it was run

- Checkout `../PredictionsAppsUI-fixture-cadence` (git worktree, branch `fixture-cadence` from `45c8b0cf`); the main
  checkout was not edited. `venv311` is a link to the main checkout's; `backend/.env` is a **sanitized** file written
  for the worktree: no provider credential, no live target, a random `SECRET_KEY`, placeholder passwords.
- Every pytest run went through a guarded runner that names every target on the command line: test database
  `localhost:5432/soccer_predictions_test`, throwaway Redis `127.0.0.1:6390` (whole server; lease databases 9-11),
  throwaway PostgreSQL `127.0.0.1:5440/forecast_race_test`; provider keys set empty; `HTTP(S)_PROXY` pointed at a
  closed local port so a stray external request fails at once. The target guard's approval line is at the top of every
  log (`policy sha256 e2abbcc34d12`). The conftest forces the sample providers and blanks every credential as well.
- The repair rehearsal ran the script with `--database-url` against `127.0.0.1:5441/psg_lyon_repair` (the copy);
  no process was pointed at live, live's PostgreSQL and Redis were only read (one `pg_dump`, two `/health` reads).
- No browser check was run: the isolated browser pair (:8001/:3101 over `soccer_predictions_e2e` on the shared
  server) is shared infrastructure already running from another session, and showing the repaired fixture there
  would have meant replacing that database and restarting that backend; no frontend file changed in this round.

## 5. Limitations and decisions for the owner

- **Live is unrepaired.** Until the fold is applied to live (a separate authorisation; the command is
  `scripts/repair_duplicate_matches.py --fold-superseded 1adf0e7d-e682-42e2-bbb2-e5a5ad365752`, dry run first),
  the recovery sweep keeps asking results providers about the dead listing every six hours, the played row has no
  forecast, and the forecasts sit on a row dated 10-25. The fold's consequence (the 10-26 12:14 snapshot not scored
  unless re-evaluated) stands either way.
- **Kyrgyzstan v Lebanon** (National Teams Friendlies, 09-28 listing never played, 10-04 listing played 1901226) is
  the same shape and is refused by design: friendlies can repeat the same way round. Whether to fold it is a
  person's decision; the script will not.
- **The ingestion rule joins only the late case** (the new id arrives after the dropped listing's kickoff window
  closed). A re-issue that arrives while the dropped listing is still in the future is stored as a new row with the
  candidate noted; the repair script catches the pair once the dropped listing goes stale. Nothing at runtime
  retires such a listing or stops the sweep asking about it; that is the repair script's job on a person's say-so.
- **Cadence**: simulated only. The grid cannot run a sleeping scheduler; the one catch-up still depends on the host
  being awake at some point, and the publication hour the policy has learned (12 UTC) is what the anchor follows.
  If the provider's publication moves later than 12:12 on a day, the 12:12 pass is served the previous run and the
  18:12 pass makes the one re-check, as the policy always did.
- Pre-existing findings the dry run listed (a duplicate club "Troyes"/"Estac Troyes", two duplicate fixtures, one
  unreconciled clash) are outside this round and untouched.

## 6. Exact changes

`backend/app/services/match_registry.py` (+241): `SUPERSEDED_LISTING_WINDOW`, `SUPERSEDED_KEY`,
`SUPERSEDED_CANDIDATES_KEY`, `round_number`; in `upsert_fixture` the dead-id refusal and the superseded branch;
`superseded_listing_for`, `_not_superseded_because`, `_note_superseded`, `_record_superseded_candidates`;
`_apply_fixture(..., rekeyed)`. `backend/app/services/sync_scheduler.py` (+82): `FORECASTS_SLOT_SPACING_SECONDS`,
`parse_slot_anchor`, `forecast_slot_after`, `slot_anchor`, `_ordinary_due`; `_record` and `_record_skip` use them.
`backend/app/core/config.py` (+13): `SYNC_FORECASTS_SLOT_ANCHOR_UTC`. `backend/scripts/repair_duplicate_matches.py`
(+303): the section, `Supersession`, `superseded_listings`, `plan_supersession`, `apply_supersession`,
`--fold-superseded`. `backend/scripts/replay_forecast_week.py` (+6): the week replay pins
`SYNC_FORECASTS_SLOT_ANCHOR_UTC = ""`, the completion-anchored cadence the two policies were compared under, so its
comparison keeps its meaning. Tests as in section 3. No frontend file, no migration, no setting that changes a ceiling.

## 7. What did not change, and how that was checked

- Live: `GET /health` before and after the round reports `45c8b0cf`, tree `64b40006…`, started 2026-10-25T06:13:31Z,
  one :8000 listener (pid 40159); the ceilings 8 / 1200 / 90 / 1000 are the application's settings, which no file
  on this branch touches, and live's process was never restarted or signalled.
- `main` = `progress` = `origin/main` = `45c8b0cf` before and after; the main checkout is clean. The branch is pushed
  as `origin/fixture-cadence` and nothing is merged.
- Live's Redis was not written: every test and rehearsal used `127.0.0.1:6390`; the script ran against `:5441`.
- No provider request was made: credentials absent, proxies closed, transports mocked.

## 8. Files

`REPORT.md`; `tests/before-new-tests.log`, `tests/after-new-tests.log`, `tests/full-suite.log`, `tests/full-suite-first-run.log`,
`tests/repeats-summary.txt`; `repair-rehearsal/01-dry-run.log`, `03-rows-before.txt`, `04-fold.log`,
`06-rows-after.txt`, `07-second-application.log`, `checksums.sh`, `checksums-diff-before-vs-after-fold.txt`,
`checksums-diff-after-fold-vs-second-application.txt`; `SHA256SUMS`. Two configuration e-mail addresses that a
traceback printed were replaced by `<email>` in the test logs; nothing else was edited.
