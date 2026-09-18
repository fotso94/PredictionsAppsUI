# Morning handoff — 18 September 2026

Overnight run against the six priorities you set. Everything is local: nothing was deployed, no
AWS resource was touched, nothing was purchased, no branch was pushed, and no provider trial
allowance was spent on testing.

> **Corrections applied 18 September 2026, after the independent review.** Four claims in the
> original version of this handoff were wrong or unproven and have been rewritten in place. If you
> read the first version, re-read these:
>
> | Original claim | Correction |
> |---|---|
> | Ligue 1 "fills in automatically" once the allowance resets (§4, §8.1) | There is **no scheduler**. The reset restores budget, not work. Sync is request-driven: a page load hitting `GET /api/v1/matches?refresh=true`, or the admin `POST /api/v1/data-providers/sync`. See §4 |
> | A second full six-competition refresh fits in the day (§5, §8.4) | It does not. A pass costs 6 requests against a plan limit of 10 and a configured budget of **8**. 6 + 6 = 12. Only a partial second pass of two competitions fits. See §5 |
> | The 9 uncovered fixtures lack forecasts "because the provider published nothing" (§4) | Not established. A forecast can also be missing because it was never requested or was not matched. §4 lists what would tell them apart |
> | "No Champions League fixtures until 13 October" (§4, §8.2) | One provider's answer for one requested window, not a verified calendar. The Champions League GameForecast id is also still unresolved |
>
> One item has since been fixed in code and is marked as such: §8.10, public registration accepting
> `role=admin`. Test counts and the commit position in §9 are snapshots — re-run and re-check rather
> than quoting them.

---

## 1. What changed, and the commit IDs

Two commits on `main`, with `progress` fast-forwarded to match. Both are **local only** — the push
is yours to make.

| Commit | What it covers |
|---|---|
| `4ca601c` | Explicit provider probability scale, forecast evidence table and migration, request-budget accounting, sync rotation, measured coverage endpoint replacing the invented home-page figures |
| `f4b2d0c` | The full correctness pass: provider hardening, match identity, API and schema fixes, the whole frontend truthfulness chain, the eight failing backend tests, the Playwright suite |
| `0a988d7` | This handoff and Addendum E |
| `00c6e60` | Defects that only showed up in the rendered pages: anomaly severity, the deleted-prediction count, the Featured Predictions subtitle, mobile search, the footer |
| `d83edc8` | Defects raised by the independent review: fixture and forecast orientation, recycled provider ids, repair provenance, token expiry, daylight saving, unvalidated over/under pairs, dead footer links, the unearned "verified" claim, derived confidence badges, backend lint |

The story in one line each:

- **A genuine 1% was being read as 100%.** The parser inferred GameForecastAPI's 0-100 scale from
  whether a value exceeded 1. The scale is now the provider's documented contract, applied
  explicitly, in one shared converter that the API-Football path uses too — that path had the same
  bug and is fixed with it.
- **Forecast evidence was being destroyed.** Each sync overwrote the only record of what the model
  said before kickoff. `predictions.provider_forecast_snapshots` is now an append-only history;
  the current forecast is still a single indexed lookup.
- **The request counter was lying.** It counted refused reservations as spending, so it showed 9
  used against a limit of 8. It now records outbound requests only, counts refusals separately, and
  fails closed for a small plan when Redis is down.
- **Ligue 1 and the Champions League were being starved.** A fixed sync order spent the allowance on
  the same four leagues every day. Competitions are now synced least-recently-synced first.
- **The home page published numbers nobody measured.** An accuracy rate, a success rate, an active
  user count and a total prediction count, all invented, plus a dashboard of fabricated betting
  history backed by a random number generator. All replaced with counts measured from the database,
  or with an honest empty state.

Two application bugs surfaced on the way: `GET /api/v1/predictions/published?date=` always returned
HTTP 500, and an expert could never edit a prediction once it was published, which contradicted your
direct-publishing decision.

Full detail is in Addendum E of `CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md`.

---

## 2. Commands and results

Backend, from `backend/`:

```bash
./venv/bin/python -m pytest -o addopts="" -p no:cacheprovider -q
```

**362 passed, 0 failed** at the time this was written. The baseline was 213 passed with 8 failures
that had been red for about eleven months. Run twice to check for flakiness; identical both times.

> Tests have been added since, so this number has already moved (a re-run later the same day
> reported 380 passed, 4 xfailed). Treat 362 as the count for *this session*, not as the current
> total — run the command and read what it prints.

Frontend, from `frontend/`:

```bash
npm run type-check && npm run lint && npm run build
```

All three pass. `npm run lint` runs with `--max-warnings 0` and now reports **0 errors and 0
warnings**, down from 53 warnings; the gate was never satisfiable before. No rule was disabled, no
threshold was raised, no `eslint-disable` comment was added.

The eight backend failures were a test-setup defect, not an application one: the tests patched a
module attribute where a FastAPI dependency override was needed, so the real authentication ran and
correctly rejected their mock token. Fixed with `app.dependency_overrides`. Production
authentication is untouched and no test was skipped or deleted.

The backend lint baseline is also clean now: `./venv/bin/python -m pyflakes app/ scripts/` reports
**0 findings**, down from 78. One of those was a genuine undefined name in the authentication path;
the rest were unused imports.

## 2b. What the independent review found

A separate review ran against this work overnight and reported nine testable defects. Each was
reproduced before being fixed, and each now has a regression test that fails without the fix. The
three that mattered most:

- **A fixture listed away-first was accepted as the same match, with the probabilities written
  unswapped.** The away side's win probability would land on the home side. A matching pair of names
  is not enough, and in a two-legged tie the reverse fixture is a different match, so a reversed
  listing is now refused outright.
- **A match found by provider id had its teams and competition overwritten without being checked.**
  Provider ids are small integers and get recycled between seasons, so one could quietly repurpose
  an existing row and carry any expert prediction attached to it over to a different game.
- **The repair script stamped snapshots with the repair time.** A repair re-reads a payload already
  on disk and retrieves nothing, so this could turn a forecast obtained before kickoff into an
  apparent post-kickoff one. The 40 rows already written were corrected against a fresh backup.

Also fixed: token expiry was read as local time and compared against UTC, which rejects a freshly
issued thirty-minute token in New York; a local day was built by adding a fixed 24 hours, which
drops an hour on each daylight-saving transition; over/under pairs were unvalidated, so an expert
could publish 90% over and 90% under the same line; seven footer links pointed at `#`; "verified
experts" claimed a review that direct publishing does not perform; and a model forecast's confidence
badge is derived from the probability rather than published by the model, which it now says.

The review is in `CODEX_INDEPENDENT_REVIEW.md`. Two of its items are deliberately left for you:
the old public S3 deployment, and whether to add CI.

---

## 3. Browser tests

```bash
npm run e2e          # everything: 79 tests
npm run e2e:mocked   # 35 desktop + 35 mobile, deterministic
npm run e2e:live     # 9 against the local backend
```

**79 passed, 0 failed.** Artifacts: traces and screenshots on failure in `frontend/e2e/.artifacts/`,
HTML report in `frontend/e2e/.report/` (`npm run e2e:report`). Both are git-ignored.

The suite is deliberately split, because mixing the two kinds hides which one proved what:

- **Mocked** (`frontend/e2e/mocked/`) stubs every backend call from captured, sanitised payloads in
  `frontend/e2e/fixtures/`. Deterministic, spends nothing, and covers the states that are hard to
  produce on demand: the 1% regression, missing 1X2, BTTS-only, exact-score-only, no forecast at
  all, exhausted quota, expired trial, an empty day, a 503 from the backend, loading states, console
  errors, failed requests, dead links, broken images, a payload whose numbers do not add up, a
  harmless bookkeeping note that must NOT raise a caution, and timezone boundaries for viewers in
  New York, Auckland, Los Angeles and Lisbon. Every one runs at desktop width and on an iPhone 13.
- **Live** (`frontend/e2e/live/`) runs against the local backend and the data already in the local
  database. It signs in through the UI, publishes, confirms the prediction is public immediately
  with no approval step, edits it, confirms the edit is public, deletes it, confirms it is gone, and
  asserts that browsing spends no provider request. It creates and removes only its own records,
  marked `[e2e-qa]`, under a dedicated account.

Five real defects were found by looking at the rendered pages rather than by reading code:

- Search was unreachable on a phone. The box is hidden below 640px and was not in the mobile menu.
- The footer promised "accurate match predictions" on every page, with a copyright frozen at 2024.
- A forecast that had merely had a 0% scoreline tidied out of its list was shown under "this forecast
  did not pass our consistency checks", which made a sound forecast look suspect. Payload
  observations now carry a severity: a warning means the numbers genuinely do not hold together, a
  note is bookkeeping and reads as a quiet footnote.
- The home page claimed 27 expert predictions published while none were live. Deletion is a soft
  delete and the count only filtered on status, so removed predictions kept being credited.
- "Featured Predictions" was subtitled as expert predictions while showing model forecasts.

Screenshots of the final state, desktop and mobile, are in `frontend/e2e/screenshots/`.

---

## 4. Coverage, per competition

| Competition | Fixtures | Upcoming | Forecasts | Snapshots | State |
|---|---|---|---|---|---|
| Premier League | 10 | 10 | 9 | 21 | attached |
| La Liga | 10 | 10 | 5 | 12 | attached |
| Serie A | 10 | 10 | 10 | 24 | attached |
| Bundesliga | 9 | 9 | 6 | 13 | attached |
| Ligue 1 | 9 | 9 | 0 | 0 | **not attempted** — deferred, allowance spent |
| Champions League | 0 | 0 | 0 | 0 | no fixtures in the window, so nothing to forecast |

These are four different things and the table keeps them apart: a forecast attached, a competition
never attempted, and a competition with no fixtures.

The 30 forecasts cover 30 of the 39 upcoming fixtures in the four completed competitions. **The
remaining 9 have no attached forecast, and that is all that is established.** An earlier version of
this handoff said the provider "published nothing" for them. That was not verified and should not be
relied on: a forecast can be absent for at least three different reasons, and a missing row does not
distinguish them.

| Possible reason | Evidence that would establish it |
|---|---|
| The forecast arrived but was not matched to our fixture | The unmatched/ambiguous forecasts we already paid for are cached in Redis under `forecast:pending:gameforecast:<competition>` (`forecast_service.py`, `PENDING_KEY` / `_store_pending`). If a fixture's counterpart is sitting there, the provider *did* publish it |
| The fixture was never requested | It falls outside the requested window (`GAMEFORECAST_SYNC_DAYS_AHEAD`, 7 days) or beyond `MAX_PAGES` (4 pages × 50 events) of the paginated `/events` response |
| The provider genuinely published no forecast for it | Only provable from the provider's own response for that competition and window. We store `raw_payload` per *stored* forecast (`provider_data.py`) — so a fixture with no forecast has no payload of its own to inspect |

The cheapest first check costs nothing: the per-competition sync report kept in Redis
(`_record_status`, 7-day TTL) records `fetched`, `attached`, `ambiguous` and `unmatched` per
competition (`forecast_service.py`, `sync_competition`). If `fetched` equals `attached` for a competition, nothing
arrived that we failed to attach, which narrows the 9 to "not published, or not requested". If
`unmatched` is non-zero, matching is at least part of the answer.

Until someone runs those checks, record these 9 as **no forecast attached**, not as *the provider has
none*.

Markets supplied per forecast: 1X2, both teams to score, over/under 2.5, over/under 3.5, exact
scores with the provider's "other scorelines" remainder, its recommended markets, and its written
reasoning. Confidence is never shown for a model forecast, because the provider does not publish one
and deriving it would be an invention.

**Ligue 1 and the Champions League go first on the next sync.** That part is verified: the rotation
reports the order as `ligue_1 → champions_league → premier_league → la_liga → serie_a → bundesliga`.

**But there is no scheduler, so "the next sync" does not happen by itself.** An earlier version of
this handoff said Ligue 1 would "fill in automatically" once the allowance reset. It will not. The
project contains no cron job, no Celery worker and no APScheduler — a search of `backend/app` and
`backend/scripts` for any of them returns nothing. The UTC-midnight reset restores the *budget*; it
starts no work. Synchronisation is request-driven, and exactly two things trigger it:

1. **A page load that reaches the matches endpoint with refresh on.**
   `GET /api/v1/matches?refresh=true` — `refresh` defaults to `true` — returns the fixtures and then
   calls `ForecastService.ensure_synced()` when the day has matches
   (`backend/app/api/v1/endpoints/matches.py`, `list_matches`). Opening Today or Tomorrow in the browser
   after 00:00 UTC is enough. This path honours `GAMEFORECAST_SYNC_INTERVAL_HOURS` (24), so a
   competition synced in the last day is skipped.
2. **The admin sync endpoint.** `POST /api/v1/data-providers/sync` (admin authentication required)
   clears the provider cooldowns and calls `ensure_synced(force=True)`, which ignores the 24-hour
   interval (`backend/app/api/v1/endpoints/data_providers.py`, `force_sync`).

So: after 8pm local time, open the site (or call the admin sync endpoint) and *then* check that
Ligue 1 picked up forecasts. Nothing happens if nobody asks.

**On the Champions League:** one query against GameForecastAPI's window returned no Champions League
fixtures before 13 October. That is an observation from a single provider over a single requested
window, not a verified competition calendar — do not treat it as the fixture list. The Champions
League GameForecast league id also remains **unresolved**: it carries no `gameforecast_id` in
`backend/app/services/providers/competitions.py`, so every attempt to reach it first spends a
`/leagues` discovery request, and a failed discovery is remembered for 6 hours (`UNRESOLVED_TTL`) to
stop it draining the plan.

---

## 5. Provider usage and remaining allowance

Counters are keyed by UTC day and reset at 00:00 UTC, which is 8pm your time.

| Provider | Used today | Limit | Note |
|---|---|---|---|
| Live Score API | 91 | 1,200 local (1,500 plan) | plenty of headroom; the 14-day trial was activated on 17 September |
| GameForecastAPI | 9 | 8 local (10 plan) | spent; the 9th was recorded by the old buggy counter |
| API-Football | 3 | 90 | retained fallback |
| TheSportsDB | 3 | 1,000 | retained fallback, key currently invalid |

The GameForecast counter reads 9 against a local limit of 8 because it was inflated by the counting
bug before that bug was fixed. **I did not reset it.** At most 9 of the plan's 10 requests were
really spent today, and resetting a counter to manufacture allowance is exactly the thing you asked
me not to do. It costs us nothing beyond today: the allowance resets on its own.

### What a full pass really costs, and whether a second one fits

The league ids verified live are recorded in code (Premier League 15, La Liga 13, Serie A 3,
Bundesliga 14, Ligue 1 4 — `backend/app/services/providers/competitions.py`), so a Redis flush no
longer re-pays discovery for those five. The Champions League has no recorded id, so reaching it
costs a `/leagues` discovery request first.

| | Requests |
|---|---|
| `/events` for the five competitions with a recorded id | 5 |
| `/leagues` discovery for the Champions League (id still unresolved) | 1 |
| `/events` for the Champions League, once its id resolves | +1 |
| A competition whose results paginate | up to `MAX_PAGES` (4) instead of 1 |
| **One full pass today** | **6** (7 once the Champions League id resolves) |

The two limits it has to fit inside:

- **The plan:** 10 requests/day (GameForecastAPI free plan).
- **The application budget:** `GAMEFORECAST_DAILY_REQUEST_BUDGET` = **8**
  (`backend/app/core/config.py`; not overridden in `backend/.env`). This is the binding limit,
  and it is deliberately below the plan limit.

**A second full pass does not fit.** 6 + 6 = 12, which is over the plan's 10 and well over the
configured 8. After one full pass, **2 requests remain** against the configured budget — enough for
two more `/events` calls, i.e. a partial second pass covering at most two competitions, with no
margin for a retry or for pagination. An earlier version of this handoff said a second refresh "is
possible but leaves no margin"; that was wrong, and this replaces it.

Two further constraints make a same-day second pass unlikely even within budget:

- `GAMEFORECAST_SYNC_INTERVAL_HOURS` is **24**, so the request-driven path skips any competition
  synced in the last day. A same-day second pass needs the admin `force=True` sync.
- When the remaining budget drops below 1, the sync stops *before* reserving and pauses the provider
  until UTC midnight, leaving the unvisited competitions at the head of the next run
  (`forecast_service.py`, `ensure_synced`).

An affordable cadence within these numbers: **one full pass per UTC day**, triggered by the first
page load after the reset, with the 2 spare requests held back for a retry.

---

## 6. Forecast repair, and what happened to the expert data

```bash
cd backend
./venv/bin/python scripts/repair_forecasts.py --dry-run   # report only
./venv/bin/python scripts/repair_forecasts.py             # apply
```

It ran twice, once after each parser change:

| Pass | Examined | Corrected | Snapshots added | What changed |
|---|---|---|---|---|
| After the explicit scale landed | 30 | 30 | 30 | the "other scorelines" remainder, which had no column before |
| After zero-probability scorelines were dropped | 30 | 10 | 10 | one 0% scoreline removed from 10 forecasts, so it can never be picked as "most likely" |
| Verification re-run | 30 | 0 | 0 | already correct |

**No stored probability changed in either pass.** That is a useful result in itself: the explicit
scale reproduces exactly what the old inference produced for this data, while removing the case
where it would have been catastrophically wrong.

Nothing was lost. The database was dumped to `backups/` before any migration or repair (git-ignored,
because it contains password hashes). The 30 existing forecasts were backfilled into the new
evidence table before anything was rewritten, and each repair appended its corrected reading beside
the previous one rather than over it, which is why there are 70 snapshots for 30 matches. All 70 are
marked as prematch captures. Expert predictions were not touched by any of this: the repair writes
only the derived market columns, and provider timestamps, raw payloads and match links are left
exactly as they were.

---

## 7. Running it

Postgres and Redis are already up. If they are not:

```bash
cd ~/Documents/DevProjects/PredictionsAppsUI && docker compose -f docker/docker-compose.yml --project-directory . up -d postgres redis
```

Backend:

```bash
cd ~/Documents/DevProjects/PredictionsAppsUI/backend && BACKEND_CORS_ORIGINS="http://localhost:3100,http://127.0.0.1:3100,http://localhost:3000" ./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```bash
cd ~/Documents/DevProjects/PredictionsAppsUI/frontend && npx vite --port 3100 --strictPort
```

Open **http://localhost:3100**. Port 3000 is taken by another project on this machine, which is why
3100 is used.

Both are running right now. Worth looking at first: the Bayern Munich v Union Berlin page, which
shows the model forecast with its reasoning, the most likely score as "3-0 (14%) · other scorelines
38%", the three separate timestamps, markets the expert left blank marked unavailable, and the
paused-refresh notice.

A QA expert account exists for the browser tests: `qa.expert@predictions-local.dev`. Its password is
a local test fixture, not a secret, and this repository is public, so it is overridable with
`E2E_QA_PASSWORD` (the default is in `frontend/e2e/support/qa-account.ts`). The account holds no live
predictions, and it must never exist in a deployed database: it can publish as an expert.

---

## 8. Remaining issues, most consequential first

1. **Ligue 1 has no forecasts, and nothing will fetch them on its own.** The allowance resets at
   00:00 UTC, but there is no scheduler in this project — see §4. After 8pm your time, open the site
   (any page that loads `/api/v1/matches` with `refresh=true`, which is the default) or call the
   admin `POST /api/v1/data-providers/sync`, and *then* check that Ligue 1 picked up forecasts.
2. **The Champions League GameForecast id is still unresolved.** It has no `gameforecast_id` in
   `competitions.py`, so it must be discovered by name, which costs one `/leagues` request per
   attempt (remembered as unresolvable for 6 hours after a failure). The one query we ran returned no
   Champions League fixtures before 13 October, but that is a single provider's answer for a single
   requested window — not a verified competition calendar, and not a reason to assume the id would
   resolve if there were fixtures.
3. **TheSportsDB is not a usable fallback.** The stored key is rejected as invalid. It needs a valid
   key, or the fallback should be dropped from the chain so it stops being listed as available.
4. **Ten requests a day is tight — tighter than this handoff first said.** A full pass costs 6 today
   (7 once the Champions League id resolves) against a plan limit of 10 and a configured application
   budget of **8** (`GAMEFORECAST_DAILY_REQUEST_BUDGET`). A **second full pass does not fit**: it
   would need 12. Only a partial second pass of at most two competitions fits, with nothing left for
   a retry. See §5 for the arithmetic. If forecasts must update more than once a day across all six
   competitions, a paid plan is the only route. I did not purchase anything.
5. **No bookmaker odds feed.** Shown as unavailable everywhere, which is correct, but it is a visible
   gap on every match page.
6. **No results settlement, so no accuracy anywhere.** The evidence table now records prematch
   forecasts, which is the prerequisite. Scoring them is the natural next piece of work and would
   let the coverage endpoint report a real accuracy figure instead of refusing to.
7. **No CI.** The eight backend tests stayed red for eleven months because nothing ran them. The
   suite is fast and deterministic now, so a workflow running the three gates would stop that
   recurring. I did not add one, since it would run on your GitHub account without you asking.
8. **The main JavaScript bundle is 679 kB.** Route-level code splitting would fix it. Cosmetic today.
9. **The expert review queue still exists** alongside direct publishing. Left in place: removing
   admin tooling is a product decision, not mine.
10. ~~**Public registration accepts `role=admin`.**~~ **Fixed since this handoff was written.**
    `POST /api/v1/auth/register` now accepts only `regular` and `expert` and returns HTTP 400 for
    anything else, with `admin` deliberately excluded
    (`backend/app/api/v1/endpoints/auth.py`, `SELF_SELECTABLE_ROLES`; commit `91ed108`). Administrators are promoted
    by an existing administrator. Note what the remaining self-selectable `expert` role does and does
    not mean: it grants permission to publish, not reviewed credentials. The wider Phase 2 security
    review (session revocation, `SECRET_KEY` handling, rate limits, the old public bundle) is still
    outstanding.
11. **The support and social links in the footer have no pages behind them.** They now read as plain
    text marked "not published yet" rather than as links that go nowhere. Give each one a route and
    turn it back into a link.

---

## 9. One thing to check before you push

```bash
git push origin main progress
```

Commits have been added since this handoff was written, so the count below it originally gave
(`d83edc8`, five ahead) is out of date. Check the current position rather than trusting a number in
a document:

```bash
git log --oneline -5
git status -sb
git rev-list --left-right --count origin/main...main   # behind / ahead
```

The `backups/` directory holds the database dumps taken before each migration and repair. It is
git-ignored because it contains password hashes. Keep it until you are satisfied with the result,
then delete it.
