# Coverage and freshness with the providers we have — measured on 2026-10-18

Read between 19:51 and 20:10 UTC from the running backend (`GET /api/v1/data-providers/status`
and `/match-data`), the live database (read-only transactions), Redis (reads only) and the code
at `5332cf15`. Nothing was synced, reset, altered or re-scheduled for this reading. Where a
number is inferred rather than measured, it says so.

## A. The actual limits, provider by provider

| Provider | Our ceiling (setting) | What the provider itself has reported | Today (UTC day) | What access we actually have |
|---|---|---|---|---|
| **Live Score** (primary match data) | 1,200 requests/day (`LIVESCORE_DAILY_REQUEST_BUDGET`, `backend/app/core/config.py`) | **Nothing**: it has never sent a rate-limit header, so the application knows nothing of its window (`provider_reported.detail`) | 331 reserved = 331 counted; 329 answered, 2 unanswered, 0 refused; by task: live 3,807 / fixtures 1,393 / recover 537 / results 164 / forecasts 136 since the 11 Oct restart | The Starter plan bought on 9 Oct: **14,500 requests/day** as its pricing page states (read 2026-10-09; not confirmed by any header). The 1,200 ceiling is ours, from the 1,500-a-day trial; a self-imposed limit |
| **GameForecast** (forecasts, free plan via RapidAPI) | **8/day** (`GAMEFORECAST_DAILY_REQUEST_BUDGET`) keyed to the UTC day | **Limit 10, remaining 7**, observed 18:29:38 UTC on the last answer; **window resets 03:12:10 UTC**, not at midnight (`provider_reported`; `window_matches_utc_day: false`) | 8 reserved = 8 transmitted = 8 answered, 0 refused | The provider's own headers say 10 per window starting 03:12 UTC. Our 8 per UTC day is not the provider's entitlement: it is a cushion against the misaligned window. The code comment "free plan: 10 requests/day" (`backend/.env.example`) is supported by the header's limit of 10, but the window is not a day |
| **API-Football** (fallback) | 90/day (`API_FOOTBALL_DAILY_REQUEST_BUDGET`) | **Limit 100, remaining 97**, observed 17:38 UTC; no reset time reported | 3 reserved = 3 answered (live polls while Live Score timed out) | Free plan, 100/day confirmed by header. It answers live scores and results; its fixtures feed refuses the current season ("Free plans do not have access to this season, try from 2022 to 2024") |
| **TheSportsDB** (fallback) | 1,000/day | Nothing (no header) | 0 | The key is refused as an invalid premium key (last success 5 Oct). Mapped, configured, unusable |

Reserved and transmitted are the same numbers today for every provider: no request was charged
without going out. The one structural mismatch is GameForecast's window: the provider counts from
03:12 UTC, we count from 00:00 UTC, so a day in our books straddles two of theirs.

## B. Coverage and freshness by competition

Upcoming fixtures from the live database at 19:55 UTC; forecast age from the newest snapshot per
fixture, model generation (`model_run_at`) and retrieval (`last_fetched_at`) separately; freshness
as the newest fixture row actually created and the newest result row actually stored, not a task's
success. The national-team competitions have no fixture inside seven days (the next is 2 November)
and are listed for their open items.

| Competition | Next 3 d | Next 7 d | With forecast | Without | Oldest model | Oldest retrieval | Newest fixture row | Newest result | Overdue | The gap, measured |
|---|---|---|---|---|---|---|---|---|---|---|
| UEFA Champions League | 18 | 18 | 17 | **1** | 44 h | 19 h | 10-15 00:04 | 10-14 20:58 | 0 | Sporting CP v LASK (21 Oct): GameForecast names the club "Lask Linz", the fixture says "LASK"; `normalize_team_name` gives `lask linz` vs `lask`, no alias joins them, so the forecast sits in the pending store (`forecast:pending:gameforecast:champions_league`, 2 entries) — **unmatched identity**. The same mismatch left Lask Linz v Liverpool (14 Oct) without a forecast; that entry is still pending for a match already played |
| Serie A | 2 | 12 | 12 | 0 | 44 h | 19 h | 10-18 00:27 | 10-18 17:57 | 0 | none |
| Premier League | 1 | 11 | 11 | 0 | 44 h | 19 h | 10-18 00:27 | 10-18 17:26 | 0 | none |
| La Liga | 2 | 10 | 10 | 0 | 44 h | 19 h | 10-18 00:27 | 10-18 18:26 | 1 | Rayo Vallecano v Athletic Bilbao (10 Oct): Live Score's feed never closed it — **provider failure**, asked 29 times, stops at the horizon |
| Bundesliga | 0 | 9 | 9 | 0 | 44 h | 19 h | 10-18 00:27 | 10-18 17:26 | 0 | none |
| Ligue 1 | 0 | 9 | 9 | 0 | 20 h | 1 h | 10-18 18:29 | 10-18 17:24 | 1 | "Estac Troyes" v Marseille (11 Oct, `api_football:1552782`): a second row for the same match, created by the API-Football live fallback under its own club name while Live Score's row Troyes v Marseille finished 0-2 — **unmatched identity**; `estac troyes` ≠ `troyes`, so neither the matcher nor the relisting rule (which closes only swapped pairings) joins them; 30 asks so far |
| UEFA Nations League | 0 | 0 | – | – | – | – | 09-29 00:09 | 10-09 03:36 | 1 | Croatia v Spain (6 Oct): absent from the provider's history — **unsupported/unreported by the provider** |
| CONCACAF Nations League | 0 | 0 | – | – | – | – | 09-30 06:02 | 10-09 03:36 | 4 | four League C games the provider never reported — **unreported** |
| National Teams Friendlies | 0 | 0 | – | – | – | – | 10-09 03:06 | 10-09 03:06 | 11 | listings absent from the provider's history on their dates — **unreported**; whether they were played is not established, so they stay unresolved |
| Africa Cup of Nations Qualifications, Arabian Gulf Cup | 0 | 0 | – | – | – | – | 09-28/29 | 09-30/10-01 | 0 | **no scheduled matches** inside the window |

Pending forecasts awaiting fixtures: 2, both Champions League, both the LASK mismatch above; the
other five club competitions have none. No fixture inside the 3-day fetch window is missing, and no
forecast is stale by the service's own rule (`include_stale: false` excludes none today).

**Forecast freshness has a daily pattern that costs a day.** Over the last eight days, 306 of 495
snapshots were fetched at the 00:0x UTC pass and every one of them carried the *previous* day's
model run (24 h old at retrieval); the 189 fetched at 12:xx–20:xx UTC carried the *same* day's run.
The provider's daily run appears between 00:27 and 12:24 UTC (its allowance window also starts at
03:12 UTC). The club competitions are all refreshed at the first pass after our UTC-midnight
allowance reset, so five of six club competitions hold a model a day older than the one the
provider already has, for the same request.

## C. Where capacity is lost, and what is deliberate

| Observation | Evidence | Deliberate or defect |
|---|---|---|
| Two of the day's eight GameForecast requests went to competitions with no fixture until 2 November | last pass 18:29 UTC: `uefa_nations_league` fetched 0, `concacaf_nations_league` fetched 0, while `champions_league`, `premier_league`, `la_liga`, `serie_a`, `bundesliga` were skipped for the day | The rotation is deliberate (every covered competition gets a daily turn); spending a turn on a competition the fixture calendar shows empty for two weeks is a defect of the rotation, not of the allowance |
| Club forecasts fetched a day stale | the 00:0x pattern above | Not deliberate: a consequence of the per-competition 24 h interval and the allowance resetting at UTC midnight together |
| One Champions League fixture without a forecast | `lask` vs `lask linz` | Defect: a missing alias line in `backend/app/services/match_matching.py` `_ALIASES` |
| GameForecast ceiling 8 against a reported 10 | headers at 18:29 UTC | Deliberate cushion for the misaligned window; the two unused requests per day are real but spending them safely needs the counter keyed to the provider's window, not more ceiling |
| Live Score ceiling 1,200 against a 14,500 plan | pricing page; no headers | Deliberate from the trial; now a self-imposed limit far below the plan, with 331 used on a full Sunday |


### From the code-path review (verified against the code and the running system)

| Observation | Evidence | Deliberate or defect |
|---|---|---|
| The 3-day fixture window does not starve the club six | the forecast task's own turn calls `_ensure_fixtures(key, 7)` → `sync_upcoming(key, 7)` (`forecast_service.py:529-538`): club fixture rows are created a median 4.9–6.7 days before kick-off; 68 of 69 upcoming fixtures carry a snapshot | Deliberate; the window binds only for the 27 national competitions outside the forecast rotation |
| A live poll the primary fails and a fallback answers still counts as a failed pass | `_run_live`: `ok = not out["errors"]` (`sync_scheduler.py:759`); the chain appends the primary's error before falling through (`match_data_service.py:692-706`); the task then backs off `BACKOFF_MIN_SECONDS = 300` (`:93`). Measured today: the live task's `last_error_at` 17:38:36.500 is 62 ms after API-Football's `last_success_at` 17:38:36.438 | Defect: five minutes without a live poll on a matchday, each time Live Score times out once |
| The free fallback forks identities | the API-Football live poll of 11 Oct created a club "Estac Troyes" and a second fixture for Troyes v Marseille; 30 asks since | Defect in the fallback's identity handling; its fixtures and results feeds refuse the current season anyway |
| The per-competition refresh slips | interval 24 h on a 6 h cadence: a key due seconds after a pass waits for the next; measured gaps 24–43 h (Bundesliga 43, 31.9, 27.9, 24.8…) | Fragile design |
| Pending forecasts never expire | `_retry_pending` re-stores each item with a fresh 48 h TTL (`forecast_service.py:667→620`); the Lask Linz v Liverpool entry (kick-off 14 Oct) is still retried daily | Minor defect, no request cost |
| Champions League has no `gameforecast_id` in code | `competitions.py:186-189`; the id (8) lives only in the 30-day Redis store | Latent: after an expiry its turn costs two requests, and `_unaffordable` can halt a pass with one left |
| GameForecast's "(10/hour)" | stated in `gameforecast.py:16` and `config.py:201`; nothing stored evidences it; the daily limit of 10 is in every answered header | Unevidenced comment, harmless |
| Reservations before transmission | `consume(1)` precedes the HTTP call (`gameforecast.py:386-387`); today 8 reserved, 8 answered; yesterday the same | Deliberate; no loss at present |
| National calendar head | one 30-row page per competition (`get_calendar_head`); in an international break page 1 may cover 1–2 days | Inferred limit, not measured as a loss |

## D. The three highest-value improvements with the providers we have

### 1. Fetch forecasts after the provider's run has been observed, with one refresh slot per day

- **Evidence and root cause.** GameForecast's run is a date stamp. In the week to 18 October, every fetch made at the first pass after UTC midnight (306 of 495 snapshots) carried the previous day's run, and every fetch at 12:xx–20:xx UTC carried the same day's; at kick-off the median model age over 21 days was 37.5 h, maximum 43. That is an **observation of one week, not a publication time the provider promises**. The club competitions all came due at the first pass after our UTC-midnight allowance reset, because eligibility was elapsed time (24 h) on a 6 h cadence that drifts.
- **What was first applied, and why it was not enough.** A noon gate plus a 22 h interval (commit `ca9c0584`). The reviewer showed it does not guarantee a daily refresh: a competition refreshed at 20:01 is not eligible at the next noon (16 h), narrowly misses an evening pass at 17:59 (21 h 58 min), and waits for the following noon — a 40-hour gap from elapsed-time scheduling. "Noon" was also written up as the provider's publication time, which the evidence does not establish.
- **Change (branch `policy-round`, not deployed).** One refresh slot per competition per UTC day, with eligibility from an **observed** earliest publication hour, re-checks of an older run paid only from spare allowance, and the elapsed-interval rule kept behind a switch for comparison and rollback — `docs/design/forecast-refresh-policy.md`.
- **Expected benefit.** Forecasts fetched after the run is observed to exist rather than before it; no missed days from elapsed time. Nothing guarantees newer predictions when the provider has not published.
- **Cost and trade-offs.** No more than the 8-a-day ceiling; a re-check costs one request and happens at most once per competition per day; spare allowance stays unspent by design.
- **Acceptance.** The replayed week in the handoff, then, after a rollout the owner approves, a week of `forecast:refresh` records showing one fetch per competition per day with same-day runs where the provider published.

### 2. Spend no forecast request on a competition with nothing to forecast, and close the identity gaps

- **Evidence and root cause.** Two of today's eight requests went to the UEFA and CONCACAF Nations Leagues, which have no fixture until November (both answered 0 events); the rotation admits any national key with a verified id and never looks at the calendar first. Separately, one Champions League fixture has no forecast because the provider writes "Lask Linz" where the fixture says "LASK", and one Ligue 1 match is counted overdue because the fallback wrote "Estac Troyes" beside Live Score's "Troyes".
- **Change (as applied on 2026-10-18; the branch replaces its dormancy test and its pending drop, see the trade-offs below and the correction after section D).** `forecast_service.py:443-448`: after `_ensure_fixtures` returns without error, count the league's `Match` rows with `match_date` inside the window; if none, record `skipped: no fixture in window`, mark the key synced and continue — no fetch; keep fetching when the fixture sync itself failed. Mirror it in the scheduler's cost estimate. In `match_matching.py` `_ALIASES`: `"lask linz": "lask"` and `"estac troyes": "troyes"`. Pin `gameforecast_id=8` for `champions_league` in `competitions.py`. Drop a pending item whose kick-off is more than 150 min past instead of re-storing it.
- **Benefit.** The two requests are not spent; under the refresh policy they stay unspent as margin unless a re-check of an older run needs them — they do not become a second daily refresh, which would buy price changes, not fresher probabilities. The LASK fixture's forecast attaches at the next free re-try; the Troyes duplicate stops being asked about once its twin is recognised (closing the row itself is a live-data decision, the owner's — `relisting_of` closes only swapped pairings by design, so either extend it to same-way duplicates with a finished twin, or run the repair script the module names).
- **Cost and trade-offs.** No request is spent on a dormant turn. A competition is dormant only on sufficient calendar evidence — a fixture sync this turn that answered fresh or from a non-stale cache, without error, covering the window — never merely because the database holds no fixture; a failed, disabled or stale discovery keeps the competition active, and a forecast fetched before its fixture is stored is kept for later attachment. The dormant keys resume by themselves the day their calendar lists a fixture.
- **Acceptance.** `forecasts.last_sync` shows no `fetched: 0` fetch; `by_reason.fetch` ≤ 6 on a club-only day; `forecasts_waiting_for_fixtures` 0 after the next pass; matcher tests for both aliases; the UEFA Nations League refreshes unaided before its 12 November fixtures.

### 3. A live poll answered by a fallback is a success

- **Evidence and root cause.** `_run_live` fails the task whenever any provider in the chain errored, even when the fallback then answered and the scores were stored, and backs off five minutes; today's 17:38 timeout cost exactly that on a Sunday afternoon with five matches in play.
- **Change (branch `policy-round`, not deployed).** In `_run_live` and `_run_results`, classify every call by what answered it — fresh from a provider, a valid cache, only the stale copy, a failed request, a request deferred by quota or cool-down, or a competition no provider can take — and judge the pass on all of its calls: it fails only when a call was answered by nobody, by the stale copy alone, or was deferred. A primary error the fallback covered stays in the report as a diagnostic. The verdict does not rest on `request_failed` alone or on rows written: an empty answer is an answer, and one competition answered does not hide another whose request failed.
- **Benefit.** No five-minute live gap on a single Live Score timeout; the fallback already covers the poll, and the primary is asked again two minutes later as normal.
- **Cost and trade-offs.** No new kind of request, but not zero: the polls a five-minute backoff would have skipped are now made, about two per avoided backoff at the two-minute cadence, and they count against the same live ceiling, which still binds. A transient primary error becomes visible in the report instead of the failure counter, so the status page must still show it (it does, as the provider's `last_error`). A poll that only the stale copy answered still fails and backs off.
- **Acceptance.** Unit test: primary timeout + fallback answer → `ok` true, no backoff; live: `tasks.live.consecutive_failures` stays 0 across a primary timeout, `backoff_seconds` unset, polls every 120 s through it.

### Applied on 2026-10-18 (changes 1 and 2)

Committed the same evening, with the backend suite at 1,691 passed: `SYNC_FORECASTS_NOT_BEFORE_UTC_HOUR = 12`
read in the scheduler's `due()` for the forecasts task; `GAMEFORECAST_SYNC_INTERVAL_HOURS` 24 → 22;
in `ensure_synced`, a turn whose fixture sync ran and succeeded and whose window holds no fixture is
taken without a request (`dormant` in the report; the scheduler's cost estimate prices it at 0) —
narrowed after two database-backed tests showed why: with no fixture sync, an empty window says
nothing, and a forecast fetched before its fixture is stored is what the pending store exists to
attach; the aliases `lask linz → lask` and `estac troyes → troyes`; and a pending forecast whose
kick-off is more than 150 minutes past is dropped instead of re-stored. The Champions League id
was pinned and then withdrawn: eight tests document provider-id discovery with the Champions
League as their example, and the pin is not what these changes are for; it stays a proposal.
Verification: the first forecasts pass after 12:00 UTC on 2026-10-19.

**Corrected on the `policy-round` branch (2026-10-18, isolated, not deployed).** The reviewer's
findings on the applied version: the noon gate was described as the provider's publication time,
which only one week of observation supports; the 22 h interval can still miss a day; the 150-minute
drop destroyed pending forecasts that a delayed fixture or a later alias could still attach as
genuine prematch evidence; a competition was priced dormant on the database alone, and the
affordability check ran before the dormant decision. The branch replaces each of these — a daily
refresh slot with an observed publication hour, retention instead of deletion, dormancy only on
sufficient calendar evidence decided before affordability — and adds the fallback-success fix for
live polling and results. The live scheduler keeps running `310470a9` until the owner approves a
rollout; the handoff is `docs/evidence/policy-round-2026-10-18.md`.

### Configuration to re-base only after the owner verifies the allowance

- **GameForecast ceiling 8 → 10.** The provider's own headers say 10 on every answered response, and the budget already refuses before the network once the provider's remaining runs short. Worth doing with change 1 (which keeps every request inside the provider's window); without it, a day straddling the 03:12 reset can over-count.
- **Live Score ceiling 1,200 → 3,000, in stages.** Every cap in the installation is derived from the trial's 1,500 (`config.py:247-275`); the Starter plan is documented at 14,500/day on the pricing page but Live Score sends no header, so the number is not observable from the system. Step 0 is the owner reading the allowance on the account page; then `LIVESCORE_DAILY_REQUEST_BUDGET=3000`, `SYNC_LIVE_MAX_REQUESTS_PER_DAY=720`, `SYNC_RECOVERY_MAX_REQUESTS_PER_DAY=80`, `SYNC_RESULTS_MAX_REQUESTS_PER_PASS=16`, `SYNC_FIXTURES_DAYS_AHEAD=5`, with the budget test and the comment updated; gate: a week with `refused_today` 0 and no quota error. Benefit: national-team fixtures stored 4–5 days ahead instead of 2 (the window binds only for them), and no live-poll ceiling on an international-break day. Typical spend rises from ~330 to ~400 a day.

## E. What genuinely needs a paid upgrade, and why

- **Results for the national-team listings Live Score never reports** (16 of the 18 overdue). No Live Score tier documents more data: every plan lists the same feature lines. That gap needs a second match-data provider with verified national-team ids — API-Football paid (its free plan refuses the current season) or another provider — and the ids verified competition by competition before entering `competitions.py`.
- **Forecasts for the 27 national competitions, or more than ten a day.** Every competition with fixtures costs at least one request a day on the free plan; ten covers the club six and at most four national competitions in an international window, and each new national competition costs a one-request discovery first. Covering all 35 daily is GameForecast Pro territory (5,000 a month, about 166 a day).
- **Fresher-than-daily probabilities.** The provider publishes one dated run a day; after change 1 the floor is ~12 h at retrieval, and more requests buy price changes, not fresher probabilities. A paid plan does not change the run cadence.
- **A fallback that can serve fixtures and results.** API-Football's free plan is historical-only; TheSportsDB's key is refused. Both are configured; neither can take over if Live Score fails for a day.

## F. Recommendation, in plain words

Do change 1 first, in its corrected form on the `policy-round` branch: one refresh slot per
competition per UTC day, taken after the provider's run has been observed (12:00 UTC until earlier
evidence; an observation of one week, not a promised publication time). It stays inside the same
8-a-day ceiling, may spend spare requests on one re-check of an older run per competition per day,
and buys a fresher run only where the provider has published by then; nothing guarantees newer
predictions. In the replayed week (a simulation) the median model age at kick-off was 20 h,
against 37.5 h measured over the 21 days to 18 October. Do change 2 with it: stop paying for competitions that have no
matches and add the two missing name aliases; that frees a quarter of the daily forecast allowance
and fills the one uncovered Champions League fixture. Then change 3, so a single Live Score
timeout no longer costs five minutes of live scores. Verify each over a week with the acceptance
checks above before touching live behaviour further.

We do not need to spend money for what the product does today: the six club competitions are
fully covered — every upcoming fixture has a forecast, results arrive within minutes of full time,
and the only gaps are a handful of national-team listings the provider never reports. The paid
frontier is national-team coverage: results for those listings need a second match-data provider,
and forecasts for them need GameForecast Pro at $19 a month. That decision can wait for the
November international window, and should be taken only if national-team forecasts matter to the
product.
