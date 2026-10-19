# Isolated round of 2026-10-18/19: matching, fallback and scheduling corrections — handoff

Everything on this page was done on branch `policy-round` in a separate working copy
(`PredictionsAppsUI-policy-round`, a git worktree), against fakes, the test database and the
isolated pair. **No live service was restarted, stopped or reconfigured; no live record, Redis key
or scheduler setting was changed; no provider request was made; no limit was raised.** The live
scheduler keeps running `310470a9`. Nothing here is deployed; a rollout needs the owner's explicit
approval.

## 1. Isolation record

| | |
|---|---|
| Starting commit | `310470a9` (main and progress, clean tree) at 20:47 UTC on 2026-10-18 |
| Live backend `:8000` | database `soccer_predictions`, started 2026-10-18T20:28:24Z, commit `310470a9`, tree `f0ecfef8d3f2`, no uncommitted application files — read from `GET /health`, unauthenticated |
| Isolated backend `:8001` | database `soccer_predictions_e2e`, started 20:28:26Z, same commit and tree |
| Working copy | `git worktree add ../PredictionsAppsUI-policy-round -b policy-round 310470a9`; `backend/venv311` symlinked to the project's interpreter and excluded from git; `backend/.env` and `frontend/.env.dev8001.local` copied (gitignored) |
| Provider clients in tests | the suite's fakes (`FakeRedis`, `LockingFakeRedis`, stub providers); HTTP goes through `httpx.MockTransport`, which cannot reach the network, and the new verdict tests' handlers raise on an unexpected path; the replay's providers raise on any unexpected call |
| Live reads made | none that write: no authentication against the live backend, no slip endpoint called |

## 2. Changes

Commits on `policy-round` only; `main` and `progress` are untouched at `310470a9`.

| Commit | Content |
|---|---|
| `a868f5fb` | Code and tests: the refresh policy, dormancy evidence, cost estimates, pending-forecast retention, the pass verdict |
| `a9dba58f` | The replay harness (`backend/scripts/replay_forecast_week.py`) and its six tests |
| `81b6a816` | Doc corrections, the design and decisions notes, the page-cap regression test, replay wording |
| `0149c89e` | This handoff, the replay report, the two run logs |
| `d7425d61` | Follow-up: the plan is built after the sync lock is taken, with nine concurrency tests (section 7) |
| the commit carrying section 7 | Section 7 and its run logs |

**Part 2 — pending forecasts are kept, not deleted** (`forecast_service.py`).
- The 150-minute drop is gone. A pending forecast is retried on every pass while its kick-off is
  within the last 30 days (`PENDING_RETRY_DAYS`); a retry is a database read, never a request.
- Past 30 days the item moves, payload untouched, to `forecast:retained:{provider}:{key}` with
  `retention: {retry: false, reason, retired_at}`, kept 180 days, and attaches on request through
  `reattach_pending(include_retained=True)`. An item with no usable market is retained with its own
  reason rather than dropped. The pending key's lifetime is 37 days instead of 48 h, so it cannot
  expire inside the retry window.
- Re-storing an item keeps its original retrieval time (`fetched_at`) and run date
  (`model_run_at`). A forecast retrieved after kick-off is never stored as prematch evidence, however
  late it attaches.
- Tests: `test_forecast_retention_db.py` (5, on the test database with a recorded GameForecast event
  payload) covers attachment days after the match, an alias correction long after kick-off, no
  duplicate snapshot on repeated attachment, a post-kick-off forecast never becoming prematch, and a
  past-window item retained intact and still attachable. `test_forecast_service.py` adds three:
  retained not deleted, retained attaches on request and spends nothing, re-storing keeps both times.

**Part 3 — fallback success for live and results** (`match_data_service.py`, `sync_scheduler.py`).
- Every call is classified by what answered it: `fresh`, `cache`, `stale`, `failed`, `deferred`
  (quota or cool-down refused it before it left), `not_asked` (no provider can take it). The pass
  fails when any call is `failed`, `stale` or `deferred`; its outcome is the common word, `partial`
  when calls differ, or `skipped`. A primary error the fallback covered is kept in
  `diagnostics.provider_errors`, not used as the verdict. The verdict does not rest on
  `request_failed` alone or on rows written.
- Results passes are judged per competition and day (`results_call_outcomes`); `prove_journey.py`
  and `sync_once.py` print the outcome.
- Tests: `test_sync_pass_verdict.py` (24). The brief's cases map to: a fallback answer avoids the
  backoff (including with the real Live Score and API-Football classes over a mock transport); a
  pass nobody answers still backs off; one competition answered does not hide another whose request
  failed; an empty answer is an answer; a request that went out and failed is still charged and
  reported; the live ceiling and the results cap still bind when the fallback answers. Also covered:
  stale-only is a failure, a quota or cool-down refusal is a deferral, a valid cache copy is a
  success, a competition no provider can take does not fail the pass.

**Part 4 — dormancy** (`forecast_refresh_policy.py`, `forecast_service.ensure_synced`).
- A competition is dormant only when, in the same turn, the fixture sync ran, answered from the
  provider or a non-stale cache, reported no error and covered the whole window; only then is the
  database counted, and it must hold no fixture in the window (`judge_calendar`).
- The order in a turn is calendar, dormancy, affordability, fetch. Under `daily-slot` an
  unaffordable competition is deferred and the pass moves on to one it can pay for; under
  `elapsed-interval` it stops, as before.
- The cost estimate mirrors the pass and prices provider-id discovery and the pages the last fetch
  read (`request_cost`, `provider:gameforecast:pages:{key}`).
- A Live Score calendar cut off at the page cap always holds fixtures, so it cannot produce a
  dormant verdict; the fallback's calendar either covers every day or raises (decisions note,
  item 12).
- Tests: every dormancy condition and the database counted only once the calendar qualifies; a
  dormant competition never blocks an affordable active one; a calendar that is not evidence leaves
  the competition active; a fresh cache copy counts as the provider's answer; a dormant competition
  wakes when its calendar lists a fixture. Estimated against actual: the estimate agrees with the
  pass on a deferral, a dormant competition and a fetch; discovery is priced the way the pass pays
  for it; a two-page competition is priced at two once a fetch has shown it, and back at one after a
  single-page fetch; the page-cap test above, shown to fail when the cap is loosened.

**Part 5 — scheduling** (`forecast_refresh_policy.py`, `sync_scheduler.py`, `config.py`;
`docs/design/forecast-refresh-policy.md` and `-decisions.md`).
- `GAMEFORECAST_REFRESH_POLICY` chooses `daily-slot` (this branch's default) or `elapsed-interval`
  (the committed noon gate and 22 h interval, kept for comparison and rollback). The ceiling stays 8.
- One refresh slot per competition per UTC day. The publication hour is observed: the earliest of
  12 and every hour at which a fetch in the last 14 days obtained a same-day run. Nothing guarantees
  a newer prediction.
- Spare-request allocation, in order: active competitions unfetched today, nearest kick-off first;
  one re-check per competition per day for a fetch that returned an older run; nothing else, so
  what is left stays unspent.
- Cache-only re-attachment runs on every pass, before and after fetching, and never consults the
  policy or the budget.
- Tests (22 in `test_forecast_refresh_policy.py`, plus scheduler tests): the 20:01 regression under
  both rules (refreshed again at noon the next day under `daily-slot`; a 40-hour gap reproduced under
  `elapsed-interval`); no fetch before the observed hour; an earlier observation brings the hour
  forward and a later one never pushes it back; an older run is re-checked once, from spare
  allowance only; a restart does not refetch a day already fetched; an exhausted allowance defers
  and the deferred competition leads the next pass; under `daily-slot` the scheduler offers the task
  every pass.

**Part 6 — the replayed week**: section 4.

**Docs corrected.** `docs/evidence/coverage-and-freshness-2026-10-18.md` and
`docs/known-limitations.md` no longer describe noon as a publication time, a daily refresh as
guaranteed, or any change as costing zero requests; change 2 is labelled as what was applied on
2026-10-18 and replaced on the branch; change 3 describes the per-call verdict. The design note no
longer claims automatic fetches can never fall before the provider's 03:12 reset.

## 3. Tests

| Run | Command, and where | Code | Result |
|---|---|---|---|
| Backend suite, final before the follow-up (section 7 has the later run) | `./venv311/bin/python -m pytest tests -q -p no:cacheprovider -o addopts="" -rs` in the worktree's `backend/` | `81b6a816` | **1,763 passed, 0 failed, 0 skipped**, 20 warnings, exit 0, 48 s, ended 00:53:44 UTC on 2026-10-19 |
| Backend suite, before the doc commit | the same | `a9dba58f` | 1,762 passed, 0 failed, 0 skipped, exit 0, ended 00:43:00 UTC |
| Starting commit, collection only | `pytest tests --collect-only -q` in the main checkout | `310470a9` | 1,691 collected |
| Isolated browser journeys | `npx playwright test --project=live-isolated` in the main checkout's `frontend/` (the branch changes no frontend file), against `:3101` → `:8001` serving the branch | backend `a9dba58f` | **55 passed, 0 failed, 0 skipped**, exit 0, 2.4 min, 00:44:32–00:46:54 UTC |
| Page-cap test, mutation check | cap loosened by one page in the client, then restored with `git checkout` | — | 1 failed while loosened; 34 of 34 passed restored |

- The 20 warnings are the existing Pydantic V1-validator and SQLAlchemy `Query.get` deprecations.
- Logs, with local paths redacted: `docs/evidence/policy-round-2026-10-18/backend-suite-final.txt`
  and `playwright-live-isolated.txt`.
- **How the isolated backend ran the branch.** The main checkout's isolated backend (pid 61022) was
  stopped with `scripts/local-servers.sh stop backend-isolated`. The worktree's backend was started
  on `:8001` with the same environment as the script's isolated pair: database
  `soccer_predictions_e2e`, scheduler off, every provider credential blank, Redis databases 10–15.
  `/health` reported `soccer_predictions_e2e`, commit `a9dba58f`, tree `b4df763f7753`, no dirty
  files, started 00:44:24Z. Its log names every provider as not configured, so no provider request
  was possible. Afterwards the branch backend (pid 48219, working directory the worktree) was
  stopped and the main checkout's isolated backend restarted: `310470a9`, tree `f0ecfef8d3f2`,
  started 00:47:29Z. The test clone was not reset.
- The suite's own cleanup removed one older QA record in the test clone that lacked the test-data
  classification; this is its standard message, and no test skipped.
- One trapped `passlib` warning about reading the bcrypt version appears in the branch backend's
  log; sign-in worked throughout.
- **Not run:** the `live` Playwright project, which reads the live pair; the mocked projects and the
  frontend unit tests, since no frontend file changed.
- **Lint:** no lint gate is enforced in this repository. The new policy module is clean under
  flake8 at 120 columns; long prose lines in the replay's report renderer and three indentation
  nits in the verdict tests remain.

## 4. Replayed week (simulation, not production observation)

Full report: `docs/evidence/policy-round-replay-2026-10-19.md`, regenerated by
`./venv311/bin/python scripts/replay_forecast_week.py --out <file>` and asserted by
`tests/simulations/test_replay_week.py`. A simulated clock runs seven days from 2026-10-19 in
five-minute ticks through the real `SyncScheduler` and `ForecastService`, with the suite's fake Redis,
a scripted forecast provider and a scripted calendar. Every provider client raises on an unexpected
call. The scripted week includes a late publication, a day with no run, a failed and a stale
calendar, a manual refresh at 20:01 (taken at the 20:05 tick), a restart, and two callers run one
after the other at the same simulated minute. That last event is sequential, not a concurrency
test; overlapping callers are tested in section 7.

| GameForecast, ceiling 8 a day | `elapsed-interval` (live today) | `daily-slot` (branch default) |
|---|---|---|
| Requests in the week | 38 | 42 |
| Requests by day | 6, 7, 5, 6, 5, 5, 4 | 6, 8, 8, 6, 5, 5, 4 |
| Requests by competition | PL, La Liga, Serie A, Bundesliga 7 each; Champions League 8; Ligue 1 2 | PL, La Liga, Serie A, Bundesliga 8 each; Champions League 8; Ligue 1 2 |
| Re-checks | 0 | 4 |
| Deferrals | 0 | 0 |
| Dormant turns, no request | 22 | 22 |
| Longest gap between fetches | Serie A 39.9 h, others 24.0 h | 24.0 h for every competition |
| Fixtures served, missing | 32 of 32, 0 missing | 32 of 32, 0 missing |
| Served an older run than existed | 2 | 0 |
| Model age at kick-off, median and max | 20.0 h, 44.0 h | 20.0 h, 44.0 h |
| Retrieval age at kick-off, median and max | 8.0 h, 23.9 h | 8.0 h, 23.0 h |
| Forced refresh at 20:05 on day 2 | 1 request, then the 39.9 h gap | 0 requests: the day's 8 were spent |
| Restart; two callers one after the other | 0 extra requests | 0 extra requests |

**Live polling** (same harness, 45 two-minute polls, primary failing three times, fallback answering
twice): the new verdict backed off once, after the poll nobody answered, losing about 4 minutes.
Applying the old verdict to the same calls gives 3 backoffs and about 9 minutes lost; that figure is
estimated, not produced by running the old code. Charged: Live Score 43, API-Football 3.

**Trade-offs the replay shows.**
- `daily-slot` spent 4 more requests in the week, all re-checks. Two of them, on the day without a
  run, returned the run already held.
- On a day whose allowance is spent, a manual refresh under `daily-slot` gets nothing. Under
  `elapsed-interval` it goes out and then causes the missed day.
- Neither rule serves a newer run than the provider has published.

**What the simulation does not establish.**
- The forecasts are synthetic objects in the provider's shape, not replayed raw payloads. Parsing
  of recorded payloads is covered by the provider and retention tests.
- Publication times, kick-offs and failures are scripted to stress the rules, not drawn from a
  measured week. Passes run exactly on the six-hour marks.
- No day ran short of allowance before every owed turn was paid, so the replay never exercises a
  deferral; the unit tests do.
- Calendar syncs are not charged. In production each walked turn costs at most one Live Score
  calendar request, as before (the fixture cache lasts two hours, passes run six hours apart). The
  branch walks a few more turns, re-checks and deferred competitions, so the Live Score count can
  rise by a few requests a day, inside its 1,200 ceiling.

## 5. Reviewer findings and their status

All "resolved" items are resolved on the branch, verified in isolation, and **not deployed**.

| Finding | Status | Evidence |
|---|---|---|
| "Noon" written up as the provider's publication time | Resolved | Observed hour in code; docs corrected (section 2) |
| The 22 h interval can miss a day (20:01 → 40 h) | Resolved under `daily-slot`; reproduced under `elapsed-interval` | 20:01 unit tests both ways; replay gap 39.9 h vs 24.0 h |
| "Spare requests become second refreshes" asserted, not designed | Resolved | Allocation defined (section 2, part 5); re-check tests; replay shows 4 re-checks, otherwise unspent |
| The 150-minute drop destroys pending forecasts | Resolved for new items | Retention, five database tests. The live entry dropped on 2026-10-18 is not restored (Stage 3) |
| Dormancy decided on the database alone | Resolved | `judge_calendar` and its tests; failed and stale calendars kept active in the replay |
| Affordability checked before the dormant decision | Resolved | Order in `ensure_synced`; "never blocks an affordable active one" test |
| Fallback success judged by `request_failed` or rows written | Resolved | Per-call classification, 24 tests, live replay |
| Estimated against actual requests, with discovery and pagination | Partly | Tests agree; the first fetch of a competition that turns out to need two pages costs one more than quoted, after which the quote is exact |
| Dormancy needs a *complete* calendar | Resolved for the dormant verdict | Page-cap reasoning and test; the cut-off still under-counts fixtures for other readers, without a flag |
| Docs claiming guaranteed noon, guaranteed daily refresh or zero additional requests | Resolved on the branch | Section 2. The same pages on `main` keep the old wording until a merge |
| The refresh plan was built before the sync lock, so a caller that waited could refetch what another had just fetched | Resolved in the follow-up | Section 7: six of nine new tests fail on the previous code, nine of nine pass now |
| A forwarded review is not authorization for a live rollout | Observed | No live change this round (section 1); rollout below awaits the owner |

**Uncertainties and behaviour changes a reviewer should weigh.**
- The publication hour can only move earlier than 12, and only after a manual fetch before 12 finds
  the day's run. A provider that publishes later than the day's last pass is seen at the next day's
  slot: one re-check a day, at the next six-hourly pass.
- Nothing bounds the observed hour below the provider's 03:12 reset. A manual refresh between 00:00
  and 03:12 that found the day's run would let automatic fetches count against the provider's
  previous window; the provider's remaining count refuses such a request before it leaves.
- A dormant verdict takes the day's slot. A fixture listed later the same day waits for the next
  day's slot.
- An unaffordable re-check is skipped, not deferred, and does not pause the provider.
- A live poll whose competitions no provider can take (`not_asked`) now counts as a success.
- Per-competition `deferred` against `not_asked` in results is read from the pass-wide record of
  what was not sent.
- The matches endpoint's `refresh=true` now follows the daily slot, so a refresh of a competition
  already fetched today buys nothing unless forced.
- `elapsed-interval` behaves as committed, including stopping a pass at the first unaffordable
  competition.

**Confirmation of no live change.** Between 20:47 UTC on 2026-10-18 and the end of this round the
live backend kept serving `310470a9`, tree `f0ecfef8d3f2`, started 20:28:24Z, read unauthenticated
from `/health` before and after. No live record, Redis key, scheduler setting or limit was changed;
no provider request was made by this round; nothing authenticated against `:8000` or called a slip
endpoint there. The only service restarted was the isolated backend on `:8001`, twice, and it ends
the round on `310470a9` as it began.

## 6. Staged rollout and rollback

Nothing below has been done. Each stage needs the owner's go-ahead.

1. **Stage 0 — review.** Read this page, the design note (`docs/design/forecast-refresh-policy.md`)
   and the branch diff. Decide the default for `GAMEFORECAST_REFRESH_POLICY` on the live service
   (`daily-slot`, or `elapsed-interval` to keep the committed rule while the rest lands).
2. **Stage 1 — merge and deploy, no data changes.** Merging is itself the rollout decision: the live
   backend runs from the main checkout without auto-reload, so the merged code goes live at the next
   backend restart by anyone, including another session. Merge `policy-round` into `main`,
   fast-forward `progress`, push; restart only the two backends through `scripts/local-servers.sh stop backend`
   / `start backend` and the isolated pair; verify `/health` serves the merged commit with no dirty
   files. No database record changes. In Redis the first pass re-stores the pending items with the
   37-day lifetime, moves any whose kick-off is more than 30 days past to `forecast:retained`, and
   creates the new keys, which all expire on their own (7 to 180 days). Expected effect on the
   first day: the forecasts task runs at the first pass after the observed publication hour (12
   until observed) and fetches the active competitions once each. The two Nations Leagues cost no
   GameForecast request if their calendar sync answers cleanly and lists nothing in the window. An
   older run is re-checked only with spare allowance.
3. **Stage 2 — watch a week, read-only.** Per competition: one fetch per UTC day with a same-day run
   where the provider published; `forecast:refresh` outcomes; the live task's `consecutive_failures`
   staying 0 across a primary timeout covered by the fallback; `used_today` ≤ 8; no deferral on a
   club-only day; the two aliases attaching what they should at the free re-try.
4. **Stage 3 — the pending store.** Only then, and only on the owner's say-so, consider restoring
   the one pending entry dropped on 2026-10-18 (Lask Linz v Liverpool, kick-off 14 Oct). It was
   dropped under the applied 150-minute rule by a re-attach run made in the previous round, before
   this brief; the restoration would use the provider's recorded payload. This round does not touch
   the live pending store.

**Rollback.**
- *Refresh rule only.* `GAMEFORECAST_REFRESH_POLICY=elapsed-interval` in `backend/.env` and a backend
  restart reinstate the noon gate and 22 h interval without a code change. Retention and the
  fallback verdict do not depend on this switch and stay in force.
- *Everything.* `git revert` of the merge commit and a backend restart. The previous code ignores the
  new Redis keys (`forecast:refresh`, `forecast:publication`, `forecast:calendar`,
  `forecast:retained`, `provider:gameforecast:pages`), which expire on their own. It also reinstates
  the 150-minute drop for the pending store on its first pass; items already moved to
  `forecast:retained` are outside that key and untouched by it.
- *Signals to roll back on.* `used_today` above 8, a deferral on a club-only day, a competition with
  no fetch on a UTC day after the publication hour, or the live task backing off while a fallback
  answered.

## 7. Follow-up of 2026-10-19: the overlapping-refresh race

Branch `policy-round` only, isolated as before. `main` and `progress` stay at `310470a9`.

**1. What changed** (`d7425d61`).
- `ForecastService.ensure_synced` now takes the sync lock first, then re-reads the provider pause,
  then builds the eligibility plan from the shared slots as they are at that moment. A worker that
  finds the lock taken still only re-attaches cached forecasts, now for every covered competition.
- The lock is released on every path that took it: a planning error, a provider error, any
  unexpected exception, a pause found under the lock, and the normal end of a pass.
- Unchanged: forced refreshes bypass eligibility and nothing else; budget enforcement; cache-only
  re-attachment on every path; the fallback verdict; the GameForecast ceiling of 8 and every other
  limit.
- The replay's two callers at 12:30 on day 5 are renamed `back-to-back`. They run one after the
  other and were never a concurrency test; the test that asserts on them says so.
- The design note's section on concurrency describes the corrected order.

**2. The interleaving tested** (`backend/tests/services/test_forecast_sync_concurrency.py`). Two
`ForecastService` instances run in two threads over one in-memory Redis (lock, slots, pause,
pending store) and one `RequestBudget`. The provider is a stub that dates its run today and refuses
any competition it was not told to expect; sockets and HTTP transports raise on contact. Events
force the order, and every wait is bounded at five seconds.
1. Caller A, with `force=False`, reaches the call that takes the lock and is held there. At that
   instant its own state says premier_league is due.
2. Caller B, with `force=False`, runs its whole pass on another thread: takes the lock, fetches
   premier_league, records the slot, releases the lock.
3. A is released, takes the now-free lock, and plans again.

The test asserts exactly one provider fetch and one request charged, both B's; the daily slot, or under the elapsed rule the last-sync time, recording
B's fetch; one pending item; A's walked plan empty with premier_league listed as skipped;
and the lock free afterwards. It runs under both refresh rules. A second version runs the same
interleaving over the test database: one snapshot, first and last retrieval both B's.

The same file also covers: a caller arriving while the first holds the lock inside its provider
call; an error while planning under the lock; an unexpected error mid-pass; a pause set by the lock
holder and honoured by the caller that waited; a forced refresh still fetching; and, on a
two-request allowance, the duplicate no longer costing another competition its turn.

**3. Failure before, success after.** The committed test file was run in a throwaway worktree at
`d7425d61`, first with `forecast_service.py` checked out from `0149c89e`, then with the fixed file.
Neither the main checkout nor the branch's working copy was modified, and the throwaway worktree was
removed afterwards.

| Code under test | Result | Log |
|---|---|---|
| Previous service, new test | 6 failed, 3 passed, exit 1 | `policy-round-2026-10-18/race-test-against-old-code.txt` |
| Fixed service, same test | 9 passed, exit 0 | `policy-round-2026-10-18/race-test-against-fixed-code.txt` |
| Fixed service, repeated | 30 runs of 30 passed | (command line only) |

Each failure on the previous code is the defect itself:
- under both rules A fetched premier_league a second time, at 13:00:10;
- on the two-request allowance la_liga was fetched twice instead of la_liga then premier_league;
- A asked a provider that B had just paused;
- planning ran without the lock held;
- over the database, a second fetch was made.

The three that pass on both versions cover behaviour that was already correct: the busy-lock
path, release after an error mid-pass, and forced refresh.

**4. Tests.**

| Run | Code | Passed | Failed | Skipped |
|---|---|---|---|---|
| Full backend suite, `pytest tests` | `d7425d61`, clean tree | 1,772 | 0 | 0 |
| Forecast policy, synchronization and budget suites, 11 files | working tree that became `d7425d61` | 249 | 0 | 0 |
| New concurrency tests | `d7425d61` | 9 | 0 | 0 |

The full-suite log is `policy-round-2026-10-18/backend-suite-after-race-fix.txt`; the 11-file run
is `related-suites-after-race-fix.txt`. The isolated browser journeys were not re-run: the change
is inside the provider sync, which the isolated backend never reaches because it has no provider
credentials and its scheduler is off.

**Residual, since closed.** The lock then expired after 300 seconds and was never renewed, so a
pass that outlived it could overlap the next holder. Sections 8 and 9 replace it with a renewed,
owner-checked lease and close the takeover gaps that remained.

**5. Live services untouched.** No live or isolated service was restarted, stopped or reconfigured
in this follow-up. `/health`, read unauthenticated at 02:13 UTC, shows the live backend on
`soccer_predictions`, commit `310470a9`, tree `f0ecfef8d3f2`, started 2026-10-18T20:28:24Z, as
before. No live record or Redis key was written, no provider request was made, and no limit was
changed. Nothing is merged or deployed.

## 8. Follow-up of 2026-10-19: the five-minute expiry - a renewed lease

Branch `policy-round` only; fix `a5aeec0e`, proof `d0c00a47`. Module `backend/app/services/sync_lease.py`.

**How it behaves.**
- **Renewal.** The pass takes a lease of one 300-second term and a daemon thread renews it every
  100 seconds, so a healthy pass keeps exclusive ownership however long it runs. Renewal and
  release are Lua scripts that compare the owner's random token, so a worker can extend or delete
  only its own lease, never a successor's.
- **Ownership loss.** A renewal that is refused, or that Redis cannot confirm, marks the lease lost
  for good. From then on the worker sends nothing, reserves nothing and writes nothing (section 9
  makes each of those checks indivisible from the act it guards), and the pass stops with
  `lease_lost` in its report.
- **Crash recovery.** A worker that dies leaves its key with nobody renewing it. The key lapses
  after one term and the next worker takes over.
- **Late responses.** A provider answer is applied only after the lease is confirmed again on its
  arrival; a late one is dropped. Writes made after that check are fenced (section 9), and the
  database never replaces a newer retrieval with an older one.
- **Clean stop.** The renewal thread stops and the lease is released on success, on any exception,
  on cancellation (a `BaseException` raised into the pass), on `SystemExit` and on
  `KeyboardInterrupt`.
- **Unchanged.** Forced refresh, both refresh policies, cache-only re-attachment, the fallback
  verdict, budget enforcement. The term stays 300 s; GameForecast stays at 8 requests a day.

**Proof.** The decisive test holds A inside its request, ticks one renewal at 200 s and starts B at
400 s, past the old expiry. On the previous code (`050d6f3e`) B fetched while A was still working,
under both refresh rules; on the fix both pass. Logs: `lease-proof-old.txt`, `lease-proof-fixed.txt`.

## 9. Follow-up of 2026-10-19: the remaining takeover gaps

Branch `policy-round` only. Fix `ad06218b`; this section and its logs in the commit after it.
Starting head `d0c00a47`, verified against `origin/policy-round` before editing.

### What changed, and why

1. **Ownership check and reservation, made indivisible.** `RequestBudget.consume` checked the lease
   and then reserved: a worker paused between the two could resume after a takeover and reserve,
   and send, one more request. Under a lease the reservation now runs `FENCED_RESERVE_LUA`, which
   reads the lease in its own Redis database and moves the counter in the budget's, in one script
   (the lease lives in the match-data database and the counter in the rate-limit database of the
   same server; the script selects each in turn). A stale owner is refused with `LeaseLost` and the
   counter does not move. Under a lease there is no unmetered or counting fallback: a reservation
   whose ownership cannot be established is not made.
2. **The provider's own bookkeeping.** Traced every shared write reachable from a pass and sorted it.
   - *Control state, only the lease's holder may change it, fenced in the same script as the token
     check:* GameForecast's page count (prices the next turn), its league-id map and its
     negative-discovery marker, the provider-reported rate-limit reading (refuses requests before
     they leave), and, as before, the forecast service's slots, last-sync times, pending and
     retained forecasts, per-competition status, pause, calendar evidence, publication observation
     and pass status. The provider writes through `control_set`, which fences under the active lease.
   - *Factual records, always written:* the usage counter, which only the owner-checked reservation
     moves; refusal counts, attribution and the scheduler ledger; the HTTP client's transmission
     records. A lost lease never erases evidence of a request that was reserved or sent.
   - *Not forecast state, left to their own pipeline:* what the calendar sync writes for match data
     (fixtures, the fixture cache, provider status and cool-downs, Live Score competition ids). The
     match-data pipeline writes these outside any forecast lease as well.
3. **Redis failure is not permission.** A cache whose Redis failed to initialise used to yield an
   unmanaged lease and an uncoordinated fetch. Now no Redis, or a Redis that fails while the lease
   is taken, refuses the provider-fetching pass, automatic or forced, with
   `coordination_unavailable` in the report. Cached data stays readable, and free re-attachment
   still runs as far as the cache can be read. Loss during execution stops the pass as in section 8.
4. **Concurrent first insertion.** `SELECT ... FOR UPDATE` cannot lock a row that does not exist. The
   forecast row is now claimed with `INSERT ... ON CONFLICT DO NOTHING` on
   `uq_provider_forecasts_match_provider`, then read back under `FOR UPDATE`. A second writer waits
   for the first's transaction and inserts nothing, then compares against the committed row: newer
   replaces it, older never does (kept in the snapshot history), and an equal retrieval applies in
   the order the lock serialises them, matching the creation-order tie-break of `SNAPSHOT_ORDER`
   used by repairs. The match's provider reference had the same race on
   `uq_provider_entity_refs_provider_external` and gets the same treatment in `MatchRegistry.set_ref`.

### Regression proof

The two new test files were run in disposable worktrees: once with the previous application code
(`d0c00a47`), once with the fix (`ad06218b`). Logs: `takeover-gaps-against-previous-code.txt` and
`takeover-gaps-against-fixed-code.txt`.

| Test | Previous code | Fix |
|---|---|---|
| A paused after its check, before reserving; B takes over and finishes | fails: counter 2, not 1 | passes |
| The same while B still holds the lease | fails: counter 2, not 1 | passes |
| A's late answer against B's page count and window reading | fails: page count 1 replaced B's 2 | passes |
| A's late empty discovery answer after B found the league | fails: league marked unresolved | passes |
| Cache Redis fails at start-up, automatic and forced pass | fails: an uncoordinated fetch was made | passes |
| First forecast row, older-first, newer-first and tied | fails: unique violation on the forecast row | passes |
| Same new event attached by two workers, both orders | fails: unique violation on the provider reference | passes |
| Redis fails while the lease is taken | fails only on the new report field: the old code also refused to fetch | passes |
| Reservation script fails; budget store on another server | not applicable: new machinery, cannot import on the old code | passes |

### Verification on the committed code

| Run | Code | Result |
|---|---|---|
| Full backend suite, `pytest tests` | `ad06218b`, clean tree | 1,811 passed, 0 failed, 0 skipped, exit 0 |
| Lease and concurrency group, five files, 30 repeats | `ad06218b`, clean tree | 30 of 30 runs: 48 passed, 0 failed, 0 skipped, exit 0 |
| Service, provider and simulation suites | the same code before its commit | 1,292 passed, 0 skipped |

Every run had the real-Redis and real-PostgreSQL cases enabled and the defaults pointed at isolated
targets (`test-targets-identity.txt`):
- The app's fallback Redis was the throwaway server on 127.0.0.1:6390 (Redis 7.4.11). The lease
  tests used its databases 9 to 11. No key remained in any of its databases after the full suite.
- The app's fallback database was `soccer_predictions_test`, the suite's own test database.
- The independent-session tests used a throwaway PostgreSQL 15 on 127.0.0.1:5440, database
  `forecast_race_test`. Each test refuses the application's databases and ports.
- Provider networking was closed in every new test: sockets except the isolated Redis, and HTTP
  transports, raise on contact.
- Time was controlled throughout: a fake clock for expiry, a ticker for renewal, and real Redis
  expiry produced by `PEXPIRE 1` rather than waiting five minutes.

### Remaining limitations

- **Not exactly-once.** What is protected: no request is reserved except by the lease's holder at
  the instant of the reservation script, none is sent without a reservation, and no answer is
  applied without a fresh ownership check. What remains uncertain:
  - A worker that stalls for longer than a term after its reservation succeeds, and then sends,
    sends one request after a takeover. It was counted, so the daily ceiling still holds, and its
    answer is discarded.
  - A worker that dies after reserving and before sending has counted a request nothing sent. That
    over-counts, which is the safe direction.
  - A connection that fails after the request left, by timeout or reset, leaves unknown whether the
    provider processed and charged it. The HTTP layer never retries, but a later pass that re-asks
    for the same competition may duplicate a request the provider did process.
  - A request in flight when its worker loses the lease is paid for and discarded, and the new
    holder fetches that competition again. That is at most one extra request per loss.
- **One Redis server.** Fencing needs every fenced store on the lease's Redis server. That holds in
  deployment, where everything comes from one `REDIS_URL`; otherwise the write or reservation is
  refused, never made unfenced. The scripts use `SELECT` inside Lua, which standalone Redis allows
  and Redis Cluster does not.
- **Match-data writes during the calendar sync** are not fenced by the forecast lease, as listed
  above. A stale worker's late Live Score answer can still update fixtures, idempotently by provider
  id, or set a Live Score cool-down.
- **Pending store.** The free re-attachment a worker runs without the lease (busy or refused path)
  can still race the holder's pending-store write: a lost update of the pending list. This existed
  before and is not changed here.
- **Not validated:**
  - separate processes, which these tests approximate with threads in one process;
  - real network partitions and slow providers, which are injected as errors and holds;
  - Redis 6 or earlier, though the scripts end in the target database for that reason;
  - Redis Cluster;
  - the isolated browser journeys, not re-run because no frontend or API surface changed.

### Live untouched, limits unchanged

`/health` on the live backend, read unauthenticated at the end of this round, shows
`soccer_predictions`, commit `310470a9`, tree `f0ecfef8d3f2`, started 2026-10-18T20:28:24Z, as at the
start of every round. `main` and `progress` are at `310470a9` on the remote. No live service was
restarted, stopped or reconfigured. No live database row or live Redis key was written, and no
provider request was made. The isolated pair was not touched this round. `backend/app/core/config.py`
differs from `310470a9` only in the refresh-policy switch and comments: no numeric limit changed,
and GameForecast stays at 8 requests a day. The two throwaway containers were stopped at the end.
Nothing is merged or deployed.
