# Forecast lease loss and the six-hour retry: cause, correction and evidence (2026-10-24)

Branch `forecast-recovery`, from the live release `69ac15f8`. **Isolated fix, verified, in two rounds. Not merged,
not deployed.** A rollout is a separate owner instruction. Everything below was read from the live machine
without a provider request, and every test ran in a separate checkout against approved test targets and
throwaway services.

- Round 1 (`6b086063`, evidence `4ee18890`): the interrupted pass is retried within minutes, not after six hours.
- Round 2 (this commit): the retry buys only the turns the interrupted pass owed, leaving the day's re-check
  of an older model to the ordinary pass; and recovery timing is separated from the budget reset — the
  five-minute minimum and a provider's pause hold across midnight, and an episode survives midnight and
  a restart without losing its count.

## 1. What happened (verified)

| When (UTC) | What | Source |
|---|---|---|
| 11:33:40 → 11:51:34, 11:51:39 → 12:09:25 | The Mac slept, dark-waking for seconds in between. | `pmset -g log` ([redis-clock-vs-host-sleep-2026-10-24.txt](redis-clock-vs-host-sleep-2026-10-24.txt)) |
| 12:09:25 | Dark wake, 30 s. The forecast pass started at once. | pmset; the backend log's first lines of the wake |
| 12:09:29 | Serie A fetched (GameForecast `events?league_id=3`, HTTP 200). | backend log |
| 12:09:30.46 | Serie A's daily slot recorded (`same-day-run`), through the fenced cache. | `sync:task:forecasts` → `plan.ineligible.serie_a` |
| 12:09:32 | "gameforecast forecast sync lease lost: a write was refused: the lease is no longer this worker's". The pass stopped. | backend log |
| 12:09:32 | The scheduler recorded a failure: `consecutive_failures` 1, backoff 21 600 s, next due 18:09:32. | `sync:task:forecasts` (`last_error_at`, `failures` 21) |
| 12:09:32.309 | Redis logged an RDB save, "1 changes in 900 seconds". | Redis container log |
| 13:30 … 16:30 | Eleven fixtures kicked off (Bundesliga 6, Premier League 3, La Liga 2) with the previous day's forecast as their newest prematch snapshot. | PostgreSQL ([incident-timeline-2026-10-24.txt](incident-timeline-2026-10-24.txt) §7) |
| 18:10:22 → 18:10:41 | The next pass fetched Ligue 1, La Liga, the Premier League and the Bundesliga; Serie A ineligible ("one slot per UTC day"). | backend log; task state |

Also verified: the two fixtures at 11:30Z and 12:00Z kicked off before the noon publication gate and are
not part of this failure; GameForecast usage for the day was 5 of 8 (`by_reason: fetch 5`); every scored
row of the day used a snapshot captured before kick-off (§8 of the timeline file), so post-kick-off
snapshots were excluded from scoring as designed. The whole pass ran within seven seconds (lines per
second in the log, §3 of the timeline), inside the first eight seconds of the wake.

## 2. The cause of the lost lease

**Proven from the records.**

- The refusal came from a fenced write answered by Redis with "not the owner" (the Lua script returned 0):
  the lease key did not hold this worker's token. It was not an exception, a timeout or an unconfirmed
  renewal: those produce different messages (`sync_lease.py`), and none appears in the log.
- The lease had been renewed successfully for Bundesliga's turn one to two seconds earlier (the turn
  starts with `_confirm_lease`, which renews; a refused renewal has its own message). The key existed at
  12:09:30 and was gone by 12:09:32.
- Nobody else held it. One backend process ran (pid 93218, since 2026-10-23); the isolated backend on
  :8001 runs with the scheduler off and Redis databases 10–15; `scripts/sync_once.py` leaves a log, and
  there is none. A takeover would have required a second worker in that two-second window.
- The pass ran seven seconds into a 300-second term, after an 18-minute sleep preceded by another.

**Inferred — not observed directly — and strongly supported: the Redis server's clock, not the lease's
logic.** Redis runs in Docker Desktop's Linux VM. Redis's own clock is visible in its RDB-save log, because
a "1 change in 900 seconds" save fires exactly when Redis's clock reads `lastsave + 900` with a change
pending:

- With the host awake all afternoon on 2026-10-23, saves fired every 301 s like clockwork.
- During the dark-wake regime, saves fired only in the first seconds of *some* wakes, more than 900 s
  after the previous one, although the application had written to Redis at earlier wakes once 900 s had
  passed by the host's clock. Example: after the 10:00:24Z save the live pass wrote at 10:16:03Z (939 s
  later by the host's clock) and no save fired; the next save came at 11:03:37Z, five seconds into that
  wake. After the 11:21:06Z save the pass of 11:51:37Z wrote and no save fired; the next save fired at
  12:09:32.309Z, seven seconds into the wake — the second the lease was lost.
- The simplest account of all of it: the VM's clock stood still while the host slept and was stepped
  forward some seconds after each wake. At 12:09:25 the pass took its lease, `SET … EX 300`, under a
  clock about 35 minutes behind; Redis computed the expiry from that clock; at 12:09:32 the clock was
  stepped forward by more than 300 s, and the key had expired. Renewal cannot protect against this:
  `PEXPIRE` is relative to the same clock.

**What remains unknown.** The VM's clock was not observed directly, and no Docker Desktop log line
records the step (the host and VM logs under `~/Library/Containers/com.docker.docker/Data/log` carry no
clock or time-sync message for the day). The size of the lag is inferred from the sleep durations. The
five-minute-expiry defect fixed on 2026-10-18 did not return: renewal ran and succeeded; the term was
cut short — by that inference — by the server's clock, not by the lack of renewal. Every mention of the
clock step in the code comments and tests carries the same label.

**The six-hour delay is established in the code.** `SyncScheduler._record` treated every forecasts pass
that reports an `error` as a failure; its backoff is `max(interval, 300 s) × 2^(n−1)`, and the task's
interval is 21 600 s. The first failure therefore waited six hours (clamped only to the next UTC reset).
The retry at 18:10:22Z is the first scheduler tick after 18:09:32Z at which the Mac was awake.

## 3. The correction

Two files, no migration, no setting, no change to the lease, its term, its renewal, its fencing, the
budget, the slots, the publication gate, force-refresh or scoring.

**`app/services/forecast_service.py`** — the pass says how it ended. `report["outcome"]` is one of
`completed` (every eligible turn taken), `partial` (interrupted by the lost lease; `unfinished` lists
the eligible competitions not reached), `deferred` (another worker holds the lease → `lease_held`; the
provider is paused → `paused`, with `paused_until`; or turns were deferred to the allowance's reset) or
`failed` (a provider refused or errored; no coordination at all). The cooldown payload records `until`
beside `reason`. **Round 2:** `ensure_synced(recovery=True)` — the scheduler's retry of an interrupted
pass — walks only the plan's fetch list, the turns the interrupted pass owed, and records each re-check
of an older run as `recheck_skipped` ("left to the ordinary pass"). The re-check itself, its allowance and
its eligibility are untouched: the ordinary pass that follows makes it.

**`app/services/sync_scheduler.py`** — an interrupted pass is retried soon, within bounds.

- A `partial` pass, or a `deferred` one because the lease is held by another worker, opens a *recovery
  episode* (state key `recovery` in `sync:task:forecasts`, in Redis) and schedules the next pass after
  `FORECASTS_RECOVERY_RETRY_SECONDS × 2^attempts`: **5, 10, then 20 minutes**. The first wait is one
  lease term, so a lease nobody renews has lapsed by then.
- Each pass inside the episode counts as an attempt, whatever it meets. One that finds the provider
  paused waits until the pause ends (`paused_until`) and no less than its scheduled delay. One that finds
  the allowance spent is skipped exactly as any pass is (`_record_skip`, unchanged).
- After **`FORECASTS_RECOVERY_MAX_RETRIES` = 3** attempts the episode is spent and the ordinary failure
  backoff applies. A completed pass closes the episode (`last_recovery.ended = completed`); a provider
  failure closes it too and keeps the backoff it always had — a retry after a provider failure is a
  request nobody asked for, and may fail again.
- During an episode `consecutive_failures` and `backoff_seconds` are untouched (no failure streak); the
  `failures` count, `last_error` and `last_error_at` are recorded as before. `last_outcome`, `recovery`
  and `last_recovery` are published by `status()` and the pass report.
- **Round 2:** a retry's due time is **not** pulled forward to the budget reset (the ordinary waits still
  are): an interruption at 23:59 is retried at 00:04, and a pause that outlasts midnight is waited for in
  full. The ordinary failure path, for the forecasts task, also never schedules before a `paused_until`
  the pass reported. An episode is no longer keyed to a UTC day: it stays open across midnight and
  restarts until a pass completes or fails or its attempts are spent, so the count is never reset by the
  date. What a pass may buy after the reset is decided by the eligibility rules as ever — before the
  publication hour, nothing — so a budget reset alone never causes a fetch. The retry pass is run with
  `recovery=True` while an episode is open.

**Maximum retry frequency:** one recovery retry per 300 s at most; at most three per episode (worst
case 35 minutes of retries after an interruption, then the regular 6 h backoff); an episode ends on
completion or failure, whatever the date. Each retry buys only competitions the daily-slot policy still
finds eligible for a *fetch*, so no competition is bought twice in a day because of a retry, and no
re-check is spent by one.

## 4. Tests

`tests/services/test_forecast_recovery.py`, 15 tests (11 from round 1, 4 from round 2). Time is simulated
with two clocks: the application's, and the Redis stand-in's own, started 2 140 s behind and stepped to real
time at the moment the incident's is inferred to have been.

| Test | Pins |
|---|---|
| the incident, reproduced | Serie A fetched and its slot kept; the lease renewed for Bundesliga's turn; the turn's first write refused with the live log's message; one request spent. Passes before and after: the lease behaves as designed. |
| **retried within fifteen minutes and finishes what it owed** (decisive, round 1) | next due ≤ 15 min and ≥ one term; no busy loop before it; the retry buys exactly the four remaining, each before its kick-off; Serie A once; 5 requests. **Before: "the retry waits 6:00:00".** |
| repeated interruptions, bounded | waits 300, 600, 1200 s, then the 21 600 s backoff; nothing spent by any retry; Serie A's slot stands. |
| competing worker holds the lease at retry time | deferred without a request; the other lease untouched; not a failure; completes after it is released. |
| provider cooldown at retry time | the retry waits for the pause, then completes. |
| exhausted allowance at retry time | skipped like any pass, no refused reservation, resumes on the new day. |
| restart between interruption and retry | a fresh scheduler over the same Redis keeps the schedule and the finished slot. |
| late answer from the previous owner | a stalled hand-run worker's answer overwrites nothing after the scheduler's retry; the request it had already sent stays charged. |
| the report and the task state say how the pass ended | completed / partial / deferred / failed, the episode's attempts, the provider failure's unchanged backoff. |
| against the real registry (PostgreSQL) | no duplicate snapshot; the fixture that kicked off inside the gap gets a snapshot flagged after kick-off; `prematch_snapshots` keeps the prematch one; original retrieval times untouched. |
| on a real, isolated Redis | the same interruption and retry with the real Lua scripts and the real budget counter. |
| **a recovery retry leaves an older-model re-check to the ordinary pass** (decisive, round 2) | 12:00 Serie A served yesterday's run (slot `older-run`); interrupted before Bundesliga; 12:05 the retry buys Bundesliga and nothing else, Serie A's re-check still owed; today's run published at 13:00; 18:05 the ordinary pass re-checks and gets it (Bundesliga too, served the same old run at 12:05); 4 requests in the day, none wasted. **Before: the 12:05 retry re-checked Serie A.** |
| **an interruption just before midnight still waits the recovery minimum** (decisive, round 2) | 23:59 interrupted → retry at 00:04, not 00:01; at 00:04 nothing is eligible before the publication hour and nothing is bought; the new day's slots are bought at 12:04. **Before: "the retry waits 0:02:00".** |
| **a provider pause that outlasts midnight is waited for in full** (decisive, round 2) | pause until 01:30 set before the 23:55 retry → next due 01:30, not 00:01; at 01:30 the gate still applies, nothing bought. **Before: 00:01.** |
| **an episode crosses midnight and a restart without losing count, and ends in completion** (decisive, round 2) | 23:52 interrupted; 23:57 and, after a restart, 00:07 and 00:27 the lease is another worker's; the third attempt is the last (`attempts` 3, `exhausted_at`), then the ordinary backoff; nothing spent; after the release, the next pass after the hour completes. **Before: the 00:07 retry was scheduled for 00:01 and the day change opened a new episode.** |

**Results** (logs beside this file; targets approved by the isolation guard, line quoted in each log):

| Run | Result | Log |
|---|---|---|
| Round 1: the file's 11 tests against the original code `69ac15f8` (same file, throwaway detached worktree) | **7 failed, 4 passed** — decisive failure: "the retry waits 6:00:00" | [before-new-tests.log](before-new-tests.log) |
| Round 1: against the fix `6b086063` | 11 passed | [after-new-tests.log](after-new-tests.log) |
| Round 1: 13 related suites | 312 passed | [after-related-suites.log](after-related-suites.log) |
| Round 1: full backend suite | 2014 passed, 0 failed, 0 skipped, exit 0 | [after-backend-full-suite.log](after-backend-full-suite.log) |
| Round 1: lease / concurrency / recovery / scheduler group, 20 consecutive runs | 20 × 114 passed | [after-lease-group-repeated-20.log](after-lease-group-repeated-20.log) |
| **Round 2: the final file's 15 tests against `4ee18890`** (same file, throwaway detached worktree) | **4 failed, 11 passed** — the four round-2 regressions fail with the reported symptoms | [before-round2-new-tests.log](before-round2-new-tests.log) |
| Round 2: against the correction | 15 passed | [after-round2-new-tests.log](after-round2-new-tests.log) |
| Round 2: 13 related suites | 312 passed | [after-round2-related-suites.log](after-round2-related-suites.log) |
| **Round 2: full backend suite**, explicit approved targets, real isolated Redis and race PostgreSQL included, after the final application edits | **2018 passed, 0 failed, 0 skipped, exit 0** (67 s) | [after-round2-backend-full-suite.log](after-round2-backend-full-suite.log) |
| Round 2: lease / concurrency / recovery / scheduler group, 20 consecutive runs | 20 × 118 passed, 0 failing iterations | [after-round2-lease-group-repeated-20.log](after-round2-lease-group-repeated-20.log) |

No browser suite was run: the frontend is unchanged. The round-1 logs were missing from `4ee18890`
(`.gitignore` ignores `*.log`); every log is now force-added to the branch, sanitized (the test database
password is masked before it is written), and listed in `SHA256SUMS`.

## 5. Isolation

- Checkout `../PredictionsAppsUI-forecast-recovery` (git worktree, branch `forecast-recovery`); the main
  checkout was not edited. `venv311` and `backend/.env` are links to the main checkout's, as in earlier
  rounds; the guard refuses any value that only `.env` supplies.
- Targets, approved by `app.core.target_guard` before every run: PostgreSQL `localhost:5432/soccer_predictions_test`
  and the throwaway `127.0.0.1:5440/forecast_race_test`; the throwaway Redis `127.0.0.1:6390` (application
  databases 0–5, lease tests 9–11). Both throwaways were started empty for each round and stopped after it.
- Live, read-only throughout, unchanged at the end of each round: `/health` `69ac15f8`, tree `02195dc1…`,
  pid 93218 started 2026-10-23T00:05:22Z, scheduler enabled; ceilings GameForecast 8, Live Score 1200,
  API-Football 90, TheSportsDB 1000; no live record, Redis key or configuration touched; no provider
  request made.

## 6. Limitations

- The cause is an inference from Redis's own clock as seen in its save log, not a direct observation of
  the VM's clock. It is environmental: a Redis whose clock keeps time through host sleep would not lose
  the lease this way. The correction makes the pass recover from any interruption of this kind; it does
  not stop the clock from stepping.
- A provider failure mid-pass still backs the task off its full interval, by design. If that is also
  to be retried sooner, it is a separate decision with its own spending risk.
- Recovery is rehearsed in isolation only, on the fake and on a real isolated Redis; it has not run on live.
- "Within 15 minutes" holds when the scheduler ticks: on a sleeping Mac the retry fires at the first
  dark wake after it is due, which on 2026-10-24 came every 15–20 minutes.
- A recovery retry that spans midnight buys nothing before the publication hour, like any pass; the
  previous day's unfinished turns are then moot, and the new day's slots are bought at the ordinary hour.
- A hand-run `scripts/sync_once.py` pass shares the scheduler's state (the script calls
  `SyncScheduler.run_once()`), so it counts toward an open episode like any pass.

## 7. Files

`SHA256SUMS` beside this file covers the three source files (paths relative to the repository root) and
every log and extract in this folder, as of the final round-2 commit.
