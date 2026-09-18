# Morning handoff — 18 September 2026

Overnight run against the six priorities you set. Everything is local: nothing was deployed, no
AWS resource was touched, nothing was purchased, no branch was pushed, and no provider trial
allowance was spent on testing.

---

## 1. What changed, and the commit IDs

Two commits on `main`, with `progress` fast-forwarded to match. Both are **local only** — the push
is yours to make.

| Commit | What it covers |
|---|---|
| `4ca601c` | Explicit provider probability scale, forecast evidence table and migration, request-budget accounting, sync rotation, measured coverage endpoint replacing the invented home-page figures |
| `f4b2d0c` | The full correctness pass: provider hardening, match identity, API and schema fixes, the whole frontend truthfulness chain, the eight failing backend tests, the Playwright suite |

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

**340 passed, 0 failed.** The baseline was 213 passed with 8 failures that had been red for about
eleven months. Run twice to check for flakiness; identical both times.

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

---

## 3. Browser tests

```bash
npm run e2e          # everything: 75 tests
npm run e2e:mocked   # 33 desktop + 33 mobile, deterministic
npm run e2e:live     # 9 against the local backend
```

**75 passed, 0 failed.** Artifacts: traces and screenshots on failure in `frontend/e2e/.artifacts/`,
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

These are four different things and the table keeps them apart: a forecast attached, a provider that
returned nothing for a fixture, a competition never attempted, and a competition with no fixtures.
The 30 forecasts cover 30 of the 39 upcoming fixtures in the four completed competitions; the
provider simply published nothing for the other 9.

Markets supplied per forecast: 1X2, both teams to score, over/under 2.5, over/under 3.5, exact
scores with the provider's "other scorelines" remainder, its recommended markets, and its written
reasoning. Confidence is never shown for a model forecast, because the provider does not publish one
and deriving it would be an invention.

**Ligue 1 and the Champions League go first on the next sync.** That is verified, not hoped for —
the rotation now reports the order as `ligue_1 → champions_league → premier_league → la_liga →
serie_a → bundesliga`. The Champions League has no fixtures until 13 October, so expect Ligue 1 to
fill in and the Champions League to stay empty until then.

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

A full six-competition sync now costs 6 requests, down from 11. The league ids verified live are
recorded in code (Premier League 15, La Liga 13, Serie A 3, Bundesliga 14, Ligue 1 4), so a Redis
flush no longer re-pays discovery. Only the Champions League id is still unknown and will cost one
lookup the first time it resolves.

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

A QA expert account exists for the browser tests: `qa.expert@predictions-local.dev` /
`QaExpertLocal!2026`. Local only, and it holds no live predictions.

---

## 8. Remaining issues, most consequential first

1. **Ligue 1 has no forecasts until the allowance resets.** Automatic, nothing to do. Worth one look
   after 8pm your time to confirm the rotation ran.
2. **The Champions League GameForecast id is still unverified.** No fixtures until 13 October, so it
   could not be confirmed without spending requests on an empty window. It will resolve by name on
   the first sync that reaches it.
3. **TheSportsDB is not a usable fallback.** The stored key is rejected as invalid. It needs a valid
   key, or the fallback should be dropped from the chain so it stops being listed as available.
4. **Ten requests a day is tight.** Six competitions cost 6 requests, so a second refresh in a day is
   possible but leaves no margin for a retry. If forecasts should update more than once daily, the
   paid plan is the only route. I did not purchase anything.
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

---

## 9. One thing to check before you push

```bash
git push origin main progress
```

Both branches are at `f4b2d0c`, two commits ahead of the remote.
