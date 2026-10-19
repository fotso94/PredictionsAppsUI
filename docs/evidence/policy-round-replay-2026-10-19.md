# Replayed week: forecast refresh policies and the live-poll verdict

**A simulation, not a production observation.** Simulated clock from 2026-10-19 00:00 UTC for seven days, five-minute ticks, the real `SyncScheduler` and `ForecastService`, the test suite's fake Redis, a scripted forecast provider and a scripted fixture calendar; no network request is possible and no database is opened. Ceiling 8 requests per UTC day.

## The scripted week

| Day | Provider publishes its run at (UTC) | Kick-offs | Other |
|---|---|---|---|
| 1 (2026-10-19) | 05:00 | bundesliga 20:00, la_liga 20:00, premier_league 20:00, serie_a 20:00 |  |
| 2 (2026-10-20) | 14:00 | bundesliga 20:00, la_liga 11:00, premier_league 11:00, serie_a 20:00 | page-load refresh of serie_a at 20:01 |
| 3 (2026-10-21) | none | bundesliga 20:00, champions_league 20:00, la_liga 20:00, premier_league 20:00, serie_a 20:00 | serie_a calendar sync raises; bundesliga calendar stale; no run published |
| 4 (2026-10-22) | 09:00 | bundesliga 20:00, champions_league 20:00, la_liga 20:00, premier_league 20:00, serie_a 20:00 | restart at 06:00 |
| 5 (2026-10-23) | 11:30 | bundesliga 20:00, la_liga 11:00, ligue_1 20:00, premier_league 11:00, serie_a 20:00 | two callers at 12:30; ligue_1 listed at noon of day 4 |
| 6 (2026-10-24) | 03:30 | bundesliga 20:00, la_liga 20:00, ligue_1 20:00, premier_league 20:00, serie_a 20:00 | ligue_1 plays |
| 7 (2026-10-25) | 12:00 | bundesliga 20:00, la_liga 20:00, premier_league 20:00, serie_a 20:00 |  |

## Policy `elapsed-interval`

Out-of-band events: forced-refresh at 20 20:05 (serie_a, 1 request(s)); restart at 22 06:00; concurrent at 23 12:30 (0 request(s) by the two callers together).
Requests: **38** in the week — by day {"2026-10-19": 6, "2026-10-20": 7, "2026-10-21": 5, "2026-10-22": 6, "2026-10-23": 5, "2026-10-24": 5, "2026-10-25": 4}; by competition {"premier_league": 7, "la_liga": 7, "serie_a": 7, "bundesliga": 7, "champions_league": 8, "ligue_1": 2}; by provider window (03:12→03:12) {"2026-10-19T03:12": 6, "2026-10-20T03:12": 7, "2026-10-21T03:12": 5, "2026-10-22T03:12": 6, "2026-10-23T03:12": 5, "2026-10-24T03:12": 5, "2026-10-25T03:12": 4}.
Deferrals 0, re-checks 0, dormant turns 22, forecasts fetched before their fixture was listed 12.
Longest gap between two fetches of a competition (hours): {"premier_league": 24.0, "la_liga": 24.0, "serie_a": 39.9, "bundesliga": 24.0, "champions_league": 24.0, "ligue_1": 24.0}.

| Fixture | Competition | Kick-off | Run used | Latest run that existed | Model age at kick-off | Retrieval age |
|---|---|---|---|---|---|---|
| fx1 | premier_league | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx2 | la_liga | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx3 | serie_a | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx4 | bundesliga | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx5 | premier_league | 20 11:00 | 2026-10-19 | 2026-10-19 | 35.0 h | 23.0 h |
| fx6 | la_liga | 20 11:00 | 2026-10-19 | 2026-10-19 | 35.0 h | 23.0 h |
| fx7 | serie_a | 20 20:00 | 2026-10-19 | 2026-10-20 | 44.0 h | 8.0 h |
| fx8 | bundesliga | 20 20:00 | 2026-10-19 | 2026-10-20 | 44.0 h | 8.0 h |
| fx9 | premier_league | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 8.0 h |
| fx10 | la_liga | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 8.0 h |
| fx11 | serie_a | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 23.9 h |
| fx12 | bundesliga | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 8.0 h |
| fx13 | premier_league | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx14 | la_liga | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx15 | serie_a | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx16 | bundesliga | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx17 | premier_league | 23 11:00 | 2026-10-22 | 2026-10-22 | 35.0 h | 23.0 h |
| fx18 | la_liga | 23 11:00 | 2026-10-22 | 2026-10-22 | 35.0 h | 23.0 h |
| fx19 | serie_a | 23 20:00 | 2026-10-23 | 2026-10-23 | 20.0 h | 8.0 h |
| fx20 | bundesliga | 23 20:00 | 2026-10-23 | 2026-10-23 | 20.0 h | 8.0 h |
| fx21 | premier_league | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx22 | la_liga | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx23 | serie_a | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx24 | bundesliga | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx25 | premier_league | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx26 | la_liga | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx27 | serie_a | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx28 | bundesliga | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx29 | champions_league | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 8.0 h |
| fx30 | champions_league | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx31 | ligue_1 | 23 20:00 | 2026-10-23 | 2026-10-23 | 20.0 h | 8.0 h |
| fx32 | ligue_1 | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |

Served 32 of 32 fixtures; missing 0. Model age at kick-off: median 20.0 h, max 44.0 h; retrieval age: median 8.0 h, max 23.9 h. Fixtures served with an older run than the provider had at kick-off: 2.

## Policy `daily-slot`

Out-of-band events: forced-refresh at 20 20:05 (serie_a, 0 request(s)); restart at 22 06:00; concurrent at 23 12:30 (0 request(s) by the two callers together).
Requests: **42** in the week — by day {"2026-10-19": 6, "2026-10-20": 8, "2026-10-21": 8, "2026-10-22": 6, "2026-10-23": 5, "2026-10-24": 5, "2026-10-25": 4}; by competition {"premier_league": 8, "la_liga": 8, "serie_a": 8, "bundesliga": 8, "champions_league": 8, "ligue_1": 2}; by provider window (03:12→03:12) {"2026-10-19T03:12": 6, "2026-10-20T03:12": 8, "2026-10-21T03:12": 8, "2026-10-22T03:12": 6, "2026-10-23T03:12": 5, "2026-10-24T03:12": 5, "2026-10-25T03:12": 4}.
Deferrals 0, re-checks 4, dormant turns 22, forecasts fetched before their fixture was listed 12.
Longest gap between two fetches of a competition (hours): {"premier_league": 24.0, "la_liga": 24.0, "serie_a": 24.0, "bundesliga": 24.0, "champions_league": 24.0, "ligue_1": 24.0}.

| Fixture | Competition | Kick-off | Run used | Latest run that existed | Model age at kick-off | Retrieval age |
|---|---|---|---|---|---|---|
| fx1 | premier_league | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx2 | la_liga | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx3 | serie_a | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx4 | bundesliga | 19 20:00 | 2026-10-19 | 2026-10-19 | 20.0 h | 8.0 h |
| fx5 | premier_league | 20 11:00 | 2026-10-19 | 2026-10-19 | 35.0 h | 23.0 h |
| fx6 | la_liga | 20 11:00 | 2026-10-19 | 2026-10-19 | 35.0 h | 23.0 h |
| fx7 | serie_a | 20 20:00 | 2026-10-20 | 2026-10-20 | 20.0 h | 2.0 h |
| fx8 | bundesliga | 20 20:00 | 2026-10-20 | 2026-10-20 | 20.0 h | 2.0 h |
| fx9 | premier_league | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 2.0 h |
| fx10 | la_liga | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 2.0 h |
| fx11 | serie_a | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 8.0 h |
| fx12 | bundesliga | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 8.0 h |
| fx13 | premier_league | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx14 | la_liga | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx15 | serie_a | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx16 | bundesliga | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx17 | premier_league | 23 11:00 | 2026-10-22 | 2026-10-22 | 35.0 h | 23.0 h |
| fx18 | la_liga | 23 11:00 | 2026-10-22 | 2026-10-22 | 35.0 h | 23.0 h |
| fx19 | serie_a | 23 20:00 | 2026-10-23 | 2026-10-23 | 20.0 h | 8.0 h |
| fx20 | bundesliga | 23 20:00 | 2026-10-23 | 2026-10-23 | 20.0 h | 8.0 h |
| fx21 | premier_league | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx22 | la_liga | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx23 | serie_a | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx24 | bundesliga | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |
| fx25 | premier_league | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx26 | la_liga | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx27 | serie_a | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx28 | bundesliga | 25 20:00 | 2026-10-25 | 2026-10-25 | 20.0 h | 8.0 h |
| fx29 | champions_league | 21 20:00 | 2026-10-20 | 2026-10-20 | 44.0 h | 8.0 h |
| fx30 | champions_league | 22 20:00 | 2026-10-22 | 2026-10-22 | 20.0 h | 8.0 h |
| fx31 | ligue_1 | 23 20:00 | 2026-10-23 | 2026-10-23 | 20.0 h | 8.0 h |
| fx32 | ligue_1 | 24 20:00 | 2026-10-24 | 2026-10-24 | 20.0 h | 8.0 h |

Served 32 of 32 fixtures; missing 0. Model age at kick-off: median 20.0 h, max 44.0 h; retrieval age: median 8.0 h, max 23.0 h. Fixtures served with an older run than the provider had at kick-off: 0.

## Live polling: primary failures with and without a fallback answer

Forty-five two-minute ticks with a match in its live window; the primary times out on polls 5, 11 and 17; the fallback answers on 5 and 11 and times out on 17. Polls made: primary 43, fallback 3; requests charged {"livescore": 43, "api_football": 3}.

| Poll | At | New verdict | Outcome | Old rule (`not errors`) | Backoff after |
|---|---|---|---|---|---|
| 1 | 14:00 | ok | fresh | ok | — |
| 5 | 14:08 | ok | fresh | FAIL | — |
| 11 | 14:20 | ok | fresh | FAIL | — |
| 17 | 14:32 | FAIL | stale | FAIL | 300 |
| 43 | 15:28 | ok | fresh | ok | — |

Backoffs: new verdict 1 (the total failure only), about 4 min of polling lost; the old rule would have backed off 3 times (after every poll with any error in the chain, fallback answered or not), about 9 min lost (estimated by applying the old verdict to the same calls with its five-minute backoff, not by running the old code). Every poll that went out was charged, answered or not.

## Trade-offs and worse outcomes, as replayed

- `daily-slot` spent +4 request(s) over the week against `elapsed-interval`: its re-checks. A re-check on a day the provider publishes late buys the same-day run; a re-check on a day it publishes nothing buys nothing — on the scripted day without a run (day 3) it made 2 re-check(s), and each returned the run it already held. Both policies stayed within the ceiling of 8 every day.
- Under `daily-slot` the forced refresh at 20:05 on day 2 made 0 requests: that day's allowance was already spent (six fetches and two re-checks), and a forced refresh bypasses eligibility, never the budget. Under `elapsed-interval` the same forced refresh went out — and produced the 39.9-hour gap, because the noon pass on day 3 saw 15 h 55 min elapsed, the 18:00 pass saw 21 h 55 min (five minutes short of 22 h), and the next pass to qualify was noon on day 4.
- The two Nations Leagues and the dormant Ligue 1 days cost nothing under either policy here because the scripted calendar answered fresh every turn; on the day the serie_a calendar sync raised and the bundesliga calendar was stale, both competitions were fetched (treated as active), as the dormancy rule requires.
- Neither policy can serve a newer run than the provider has published: on the day without a run every fixture was served the previous day's run under both.
