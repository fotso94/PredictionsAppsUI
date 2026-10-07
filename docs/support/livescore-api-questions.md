# Questions for Live Score API support — PREPARED, NOT SENT

Status: **draft, awaiting the owner's decision to send.** Nothing here has been transmitted, and
nothing here commits to a purchase: whether to buy a plan, ask for an extension or do neither is the
owner's decision, made after Live Score has answered.

No credential appears in this document. The `key` and `secret` are request parameters; every query
below is written with them omitted, and the responses quoted carry none. Before sending, check that
nothing has been pasted in since.

Revised 2026-10-07 at 01:35 UTC. Our own figures were re-measured then, read-only: the backend's
`GET /api/v1/data-providers/status`, the per-day request counters in Redis, and SQL against the
application database. At 01:49 UTC the request-volume figures were corrected: the 546-a-day
average covers the background scheduler only, not all our traffic. Facts about Live Score's own pages are marked with their URL and with how
they were read; see [the source list](#facts-taken-from-live-scores-public-pages).

---

## What a 401 tells us, and what it does not

A 401 establishes that **we have an access problem. It does not, by itself, prove that buying a
plan is necessary.**

- Live Score's Standard Errors page documents **HTTP 402** for an account with no subscription and
  for an expired subscription. It documents **HTTP 401** for an invalid key and secret combination
  (https://live-score-api.com/documentation/reference/7/standard_errors — read 2026-10-07 through
  an automated page summary; confirm on the page before quoting).
- What we receive is **HTTP 401**, the code that page gives for an invalid key and secret
  combination, but with a message the page does not list: *"This API key and secret do not have
  access to our data enabled"*. We have never received the 402 the page gives for a missing or
  expired subscription (same source and caveat).
- We have seen this exact message before. On 2026-09-17, Live Score sent it in answer to requests
  we had sent less than a second apart, while the trial was plainly active. It went away once we
  spaced requests at least one second apart (`CLAUDE_PROJECT_STATUS_AND_NEXT_STEPS.md`, Addendum D).

An ended trial is a plausible reading, and so are an account flag, a plan change or something on
Live Score's side. If the key was first used on 17 September and the trial started then, its
14 days (the length given on the FAQ and pricing pages, [S2] and [S3] in the source list) end
around 1–2 October. Data was still served on 2 October at 14:53 UTC. That timing fits
an ended trial give or take a day, but it does not prove one. **Ask first, then decide.**

**Why it matters now (2026-10-07 01:30 UTC, read-only SQL):**

- 96 fixtures have kicked off but have no result: 44 in the UEFA Nations League, 28 in the
  CONCACAF Nations League and 24 National Teams Friendlies. The earliest kicked off on
  2026-09-24 at 04:00.
- No result has been stored since 2026-10-02 13:36, and no new fixture since 2026-10-02 14:46.
- Only 4 future fixtures are stored.
- Slips holding a stranded fixture stay pending.
- Forecasts still arrive from GameForecastAPI, but they only attach to fixtures already stored.
- The fallbacks cannot stand in. API-Football's free plan refuses the current season. TheSportsDB
  answers HTTP 400, "Invalid Premium API key". Neither holds an id for any national-team
  competition.

---

## Before sending: the owner's checklist

1. **Look for an answer that may already exist.** Check the inbox (including spam) of the address
   registered with Live Score for a trial-end, payment or account notice. Then check the Live Score
   dashboard for the subscription status and the trial dates. If either one answers question 1,
   shorten the message to what is still open.
2. **Fill in the placeholders.**
   - `[ACCOUNT E-MAIL OR USERNAME]`: the account identifier as Live Score knows it.
   - `[NAME]`: your name.
   - The trial start date. If the dashboard shows one other than 17 September, correct "from
     17 September 2026" in the message's opening paragraph. If it shows none, leave the sentence
     as written.
3. **Refresh the latest refusal.** In `GET /api/v1/data-providers/status`, find the `livescore`
   entry in `chain`.
   - Copy its `last_error_at` over both "2026-10-07 01:34" in the message.
   - If that time has moved, recount the requests from the `answered` field of the Redis hashes
     `provider:budget:livescore:<YYYYMMDD>:transmitted` (db 5) and update every place that quotes
     them together: the total and the per-day breakdown in the message, the "Since the refusals
     began" row of the Account and volume table, and the matching row of the sources table. If
     you prefer not to recount, write "about 70 requests" and delete the per-day breakdown.
   - Check that `last_success_at` is still 2026-10-02T14:53:28Z. If it is later, access has come
     back and the message needs rewriting.
4. **Confirm every quoted page fact by eye.** Open each URL in
   [the source list](#facts-taken-from-live-scores-public-pages) and check the wording. Those pages
   were read through an automated page summary, and the site refused several of the reads (HTTP 429).
5. **Never paste the key or the secret.** Search the final text for both before sending.
6. **Delete the `[S1]`–`[S5]` markers.** Keep the URLs. The markers only point into the source list.
7. **Send it yourself.** Use your own mailbox to support@livescore-api.com (the address on the FAQ,
   [S2]) or the support channel in the dashboard. Do not buy, upgrade or start anything until they
   have answered.
8. **Record that it was sent.** Change this file's banner to SENT, with the date. When the reply
   comes, add its answers under each question.

---

## 0. The message (ready to send once the checklist is done)

**To:** support@livescore-api.com [S2], or the support channel in the account dashboard

**Subject:** HTTP 401 "do not have access to our data enabled" since 5 October 2026: why, and what
restores access?

> Hello,
>
> Account: [ACCOUNT E-MAIL OR USERNAME]. We are deliberately not including the API key or the
> secret.
>
> Since 5 October 2026, every request from this account has been answered with HTTP 401 and the
> message "This API key and secret do not have access to our data enabled". The same key and
> secret had worked normally from 17 September 2026 until 2 October 2026.
>
> What we know (all times UTC):
>
> - The last successful response was at 2026-10-02 14:53.
> - Our server sent nothing between 2026-10-02 14:54 and 2026-10-05 03:09 because of a fault on
>   our side, now fixed. So we cannot tell when within that window access stopped.
> - The first request after that, at 2026-10-05 03:23, received HTTP 401 with the message above.
>   Every request since has received the same answer. The most recent was at 2026-10-07 01:34.
> - We have changed nothing:
>   - the same key and secret;
>   - the same host, https://livescore-api.com/api-client/;
>   - sent the same way, as the `key` and `secret` query parameters.
> - These are not bursts. We always leave at least one second between requests. While we are
>   refused, we send one request, retry it once 2.5 seconds later, and then send nothing for
>   30 minutes.
>   - In total, 65 requests reached you between 2026-10-05 03:23 and 2026-10-07 01:34: 59 on
>     5 October, 2 on 6 October and 4 on 7 October. Our server was off for most of 6 October.
>   - We mention bursts because on 17 September the same 401 message answered requests we had
>     sent less than a second apart. It stopped once we spaced them.
> - Your Standard Errors page
>   (https://live-score-api.com/documentation/reference/7/standard_errors) [S1] lists:
>   - HTTP 402 for an account with no subscription or an expired one;
>   - HTTP 401 for an invalid key and secret combination.
>
>   We receive HTTP 401, the code your page gives for an invalid key and secret combination, but
>   with a message the page does not list, and never the 402 your page gives for a missing or
>   expired subscription. So we would rather ask than assume.
>
> About the account:
>
> 1. Why is data access disabled for this key? Did the trial end, is there a flag or restriction on
>    the account, did the plan change, or is it something else?
> 2. If it is the trial, on what dates did it start and end? Your FAQ (https://live-score-api.com/faq)
>    [S2] says the trial runs 14 days from the day it is started, which need not be the
>    registration date.
> 3. What exactly must we do to restore access? If a subscription is needed, which plan covers
>    everything listed below? Once it is active, will our existing key and secret work again, or
>    must we create a new pair from the profile?
> 4. Is a short extension of the trial possible while we decide? Your pricing page
>    (https://live-score-api.com/prices) [S3] mentions an extra week.
> 5. Your FAQ [S2] says every request is counted, errors included. While access is disabled, is
>    there anything we should stop doing? We currently try about twice an hour, and each try is one
>    request plus one retry. Could the refused requests affect the account once access is restored?
>
> What we need to keep. Please confirm that the plan you recommend includes all of the following,
> and tell us if anything is restricted by plan:
>
> 6. All 35 competitions in the table below: 6 club and 29 national-team competitions, with the ids
>    from your competitions/list.json. We use them on fixtures/list.json, matches/live.json,
>    matches/history.json and competitions/table.json.
>    - Is national-team football included on every paid plan? That means the World Cup and its
>      qualifiers, both Nations Leagues, the continental championships and their qualifiers,
>      National Teams Friendlies, the Women's World Cup and Olympic football.
>    - Does that include forward fixtures for competitions that have nothing scheduled today?
> 7. How far back does matches/history.json answer on that plan? In normal operation we ask about
>    results up to 14 days after kickoff. We would like at least 30 days of history, and a one-off
>    catch-up of results from 2026-09-24 onwards.
> 8. Our own hard ceiling is 1,200 requests a day, enforced in our code. Our busiest recorded day
>    used 683 (2026-09-20, before we added national teams; daily totals since then were not kept),
>    and we never send more than 60 a minute.
>    - Apart from the daily count, is there a per-second, per-minute or hourly limit we must stay
>      under? Your Standard Errors page [S1] mentions an hourly quota.
>    - Does the daily count reset at 00:00 UTC?
>    - Is "do not have access to our data enabled" also your answer to requests sent too close
>      together?
> 9. Our pages display the team `logo` images from cdn.live-score-api.com, using the URLs your
>    responses carry. Is that permitted on the plan, and does it depend on the account being
>    active?
> 10. Your history endpoint accepts several comma-separated competition_id values
>     (https://live-score-api.com/documentation/reference/15/football_data_history_matches) [S4].
>     Does one such request count as one request?
>
> Thank you,
> [NAME]

### Entitlement specification (paste below the message)

| Need | Specification |
| --- | --- |
| API host | `https://livescore-api.com/api-client`, authenticated by the `key` and `secret` query parameters. Note there is no hyphen in the API host; the website and documentation are on live-score-api.com. |
| Endpoints | `fixtures/list.json`: `competition_id` with `date=YYYY-MM-DD` for a day, or `competition_id` alone for the calendar; `page`. · `matches/live.json`: unfiltered; one poll covers every competition. · `matches/history.json`: `from`, `to`, `competition_id`, `page`. · `competitions/table.json`: `competition_id`, `include_form=1`. · `competitions/list.json`: rarely, and only to identify a competition not listed below. |
| Club competitions (6) | Premier League 2 · La Liga 3 · Serie A 4 · Bundesliga 1 · Ligue 1 5 · UEFA Champions League 244 |
| National-team competitions, FIFA and worldwide (6) | FIFA World Cup 362 · World Cup Inter-Confederation Play-Off 365 · Arab Cup 452 · National Teams Friendlies 371 · Women's World Cup 490 · Olympic Games Football Tournament 385 |
| National-team competitions, UEFA (3) | World Cup UEFA Qualifiers 363 · UEFA Nations League 350 · UEFA EURO Qualification 274 |
| National-team competitions, OFC (1) | World Cup OFC Qualifiers 364 |
| National-team competitions, CAF (6) | World Cup CAF Qualifiers 359 · African Cup of Nations 227 · Africa Cup of Nations Qualifications 228 · African Nations Championship 226 · African Nations Championship Qualification 403 · COSAFA Cup 225 |
| National-team competitions, AFC (6) | World Cup AFC Qualifiers 358 · Asian Cup 240 · Asian Cup Qualification 241 · AFF Suzuki Cup 246 · SAFF Championship 247 · Arabian Gulf Cup 412 |
| National-team competitions, CONCACAF (5) | World Cup CONCACAF Qualifiers 360 · Gold Cup 266 · Gold Cup Qualifiers 435 · CONCACAF Nations League 391 · CONCACAF Nations League Qualification 269 |
| National-team competitions, CONMEBOL (2) | World Cup CONMEBOL Qualifiers 361 · Copa America 271 |
| Kept for when they return (5, not requested today) | FIFA Confederations Cup 270 · King's Cup 373 · Kirin Cup 374 · Southeast Asian Games 248 · Toulon 377 |
| History depth | Routine: results for up to 14 days after kickoff. Asked for: at least 30 days. One-off: back to 2026-09-24. |
| Request volume | Our hard ceiling is 1,200 a day, enforced in code; our per-task caps add up to about that before pagination and retries. The heaviest measured day was 683 (2026-09-20, before national-team coverage; daily totals since then were not kept). Our background scheduler alone averaged about 546 a day from 2026-09-25 to 2026-10-02. Requests made by page loads are not in that figure, and daily totals for those days were not kept. |
| Peak rate | At most 60 a minute: one process, at least 1 second between calls. The fixtures pass sends a burst of 18 to about 60 requests every 6 hours, more if a list runs to several pages, still at least 1 second apart. |
| Live polling | One unfiltered `matches/live.json` every 120 seconds, only while a covered match is between 15 minutes before kickoff and 150 minutes after it; plus, while a result is overdue, one poll per 30-minute recovery pass. At most 420 a day in all. |
| Crest images | The browser loads `https://cdn.live-score-api.com/teams/<id>.png` from the `logo` field. 282 of our 284 stored teams use it: 96 of 98 clubs and all 186 national teams. |
| Not needed | Match events, lineups, statistics, pre-match and live odds, commentary, head-to-head, top scorers, translations (`lang`), countries and flags, the teams list. |

### Facts taken from Live Score's public pages

Every row was **read 2026-10-07 through an automated page summary; confirm on the page before
quoting**. Paraphrased unless in quotation marks. Prices are as the page rendered them to the
reader, and may be shown in another currency.

| Mark | Page | What it says |
| --- | --- | --- |
| S1 | https://live-score-api.com/documentation/reference/7/standard_errors | HTTP 401: "Invalid API key and secret combination". HTTP 402: no subscription, or an expired subscription. 400, 500 and 501 cover malformed requests. The page mentions an "hourly quota" in passing, while explaining why the key and secret are used together. It documents no quota error. The message we receive does not appear on it. |
| S2 | https://live-score-api.com/faq | The trial lasts 14 days from the day it is started, which can be long after registration. It is granted once per account, and may be extended in special cases, for example after following them on social media and telling them. After it ends, a paid plan is needed. Every request that reaches their servers counts toward the daily quota, errors included. Cancelling a subscription ends data access immediately, with no refunds. A key and secret pair is issued at registration, and a new pair can be created from the profile. Support: support@livescore-api.com. Nothing is said about per-minute limits or logo use. |
| S3 | https://live-score-api.com/prices | Trial: 14 days, 1,500 requests a day. Starter: €11 a month, 14,500 a day. Professional: €26, 50,000 a day. Premium: €69, 75,000 a day. Commentary: €190, 100,000 a day, with 92 years of historical data. Custom: on enquiry. Every plan, the trial included, lists the same feature lines (live scores, fixtures, standings, historical data, competitions, teams and more). Nothing ties national-team competitions, particular competitions or logo use to a plan, and only Commentary states a history depth. The page offers one extra trial week for following them on social media. |
| S4 | https://live-score-api.com/documentation/reference/15/football_data_history_matches | Parameters: `competition_id` (several ids, comma-separated), `from`, `to`, `team_id`, `page`, `lang`. 30 rows a page. No history depth, publication delay or plan dependency is stated. This page was read in the 2026-10-07 survey; a re-read the same morning was refused (HTTP 429). |
| S5 | https://live-score-api.com/documentation/reference/6/getting_livescores | A finished match stays in the live feed "for up to 3 hours more". The same page also gives shorter figures: 1 hour 15 minutes after a 90-minute finish, and 45 minutes after extra time. Nothing ties the feed to a plan. (Used in section 3.) |

### Where our own figures come from

| Figure | Source |
| --- | --- |
| Last success 2026-10-02 14:53:28. Latest refusal 2026-10-07 01:34:59. The message text. | `GET /api/v1/data-providers/status`, `chain[livescore]`: `last_success_at`, `last_error_at`, `last_error` |
| Local fault from 2026-10-02 14:54 to 2026-10-05 03:09; first refusal 03:23 | `docs/known-limitations.md`, the sections on the local fault and on no match-data source answering |
| 65 requests reached Live Score from 2026-10-05 03:23 to 2026-10-07 01:34: 59 on 10-05, 2 on 10-06, 4 on 10-07. A further 4 did not connect. | Redis db 5, `provider:budget:livescore:<YYYYMMDD>:transmitted`. These keys expire after 2 days, so per-day history from before 10-05 is gone. |
| One request, one retry after 2.5 s, then a 30-minute skip. At least 1 s between calls. | `backend/app/services/providers/livescore_api.py` (`MIN_REQUEST_INTERVAL`, `BURST_RETRY_DELAY`, `_get`); rejected-credential cool-down of 30 minutes |
| One process holds the key | At 2026-10-07 01:30 UTC only one backend was listening (127.0.0.1:8000, started 01:02:40 UTC). The 1 s spacing is per process, so a second backend using the same key would not share it. |
| Ceiling 1,200 (per-task caps sum to about that; the 1,182 in the code comment leaves out the fixtures pass's own results requests) | `backend/app/core/config.py` (`LIVESCORE_DAILY_REQUEST_BUDGET` and the worst-case sum above `SYNC_FIXTURES_MAX_NATIONAL_REQUESTS_PER_PASS`), asserted by `backend/tests/services/test_coverage_budget.py` |
| Heaviest day 683 (2026-09-20, club competitions only, before national-team coverage) | `backend/tests/test_calendar_budget.py`, `backend/app/services/match_data_service.py` (calendar ceiling note) |
| About 546 a day, background scheduler only | The scheduler ledger (`scheduler_sent` on the status endpoint) held 3,746 Live Score requests at 2026-10-07 01:49 UTC: live 2,501, fixtures 789, recover 251, results 131, forecasts 74. It has counted since commit 52495f7, so since about 2026-09-25 18:15 UTC at the earliest. Divided by the 6.86 days from then to the last success (2026-10-02 14:53), that is about 546 a day. **It counts the scheduler and nothing else.** A request started by a page load or an admin sync (a test run against the running backend included) moves the day's usage counter but not this ledger (`backend/app/services/providers/budget.py`, module docstring). Those per-day usage counters expire after 2 days, so the whole-day totals for 2026-09-25 to 10-02 are gone, and so is any way to say how much the page loads added. Nor is 546 a bound in either direction for the scheduler itself. The ledger also holds requests reserved during the local fault that never left our machine, and the refused attempts since 2026-10-05, which push it up. If the ledger began counting later than 18:15 UTC, the true average is higher. |
| 14-day routine history need | `backend/app/services/match_registry.py`, `RETRY_SCHEDULE` / `RETRY_HORIZON` |
| 35 competitions and their ids | `backend/app/services/providers/competitions.py`. `COVERED_COMPETITIONS` and `COVERED_NATIONAL_TEAM_COMPETITIONS` are at their defaults, and the status endpoint reports 35 covered. |
| Crest counts | Read-only SQL on `predictions.teams.logo_url` |

---

## Follow-up questions

Send these once access is settled, or append them to the message if the owner prefers a single
e-mail. They are still open; none depends on the account question.

## 1. Will forward fixtures for national-team competitions be served on our plan?

Since 2026-09-24 we cover 29 national-team competitions. We are trying to tell "this competition
has nothing scheduled" apart from "this competition is not served to us". From here the two look
identical: an empty list and HTTP 200, with no error.

**When we asked on 2026-09-23, before access stopped, these returned fixtures:**

| Query (2026-09-23) | Result then |
| --- | --- |
| `fixtures/list.json?competition_id=350` (UEFA Nations League) | 30 fixtures, the first on 2026-09-24 |
| `fixtures/list.json?competition_id=371` (National Teams Friendlies) | 30 fixtures, the first on 2026-09-23 |
| `fixtures/list.json?competition_id=363` (World Cup UEFA Qualifiers) | 1 fixture, 2026-11-02 |

Between 2026-09-24 and 2026-10-02, `fixtures/list.json` gave us fixtures for five of our
competitions:

- UEFA Nations League: 104 fixtures
- CONCACAF Nations League: 71
- National Teams Friendlies: 60
- Africa Cup of Nations Qualifications: 49
- Arabian Gulf Cup: 10

**These returned an empty list, with no error, on 2026-09-23:**

`fixtures/list.json?competition_id=` followed by:

- 362 (FIFA World Cup);
- 359, 358, 360, 361 and 364 (the CAF, AFC, CONCACAF, CONMEBOL and OFC World Cup qualifiers);
- 227 (Africa Cup of Nations);
- 271 (Copa America);
- 490 (Women's World Cup).

We believe several of those are simply dormant right now, and we have confirmed that the archive
answers for four of them:

| Query | Rows |
| --- | --- |
| `matches/history.json?competition_id=362&from=2026-06-10&to=2026-07-20` | 30 |
| `competition_id=227`, January to February 2026 | 16 |
| `competition_id=271`, June to July 2024 | 30 |
| `competition_id=490`, July to August 2023 | 30 |

**The question:** when one of those competitions next has scheduled fixtures, will
`fixtures/list.json` return them on our plan? Or is forward fixture data for national-team
competitions limited in a way we should design around? We would rather know now than discover it
during a tournament.

**A smaller related one:** `competitions/list.json` reports `national_teams_only` as `"0"` for three
competitions: 271 (Copa America), 371 (National Teams Friendlies) and 490 (Women's World Cup). Every
other national-team competition we found reports `"1"`. Is that intentional, or are those three
mis-flagged? We have worked around it with an explicit list, but a fix upstream would be better for
everyone.

---

## 2. How long does a finished match take to reach the history archive, and why are three friendlies missing?

The archive clearly works, for club and national-team competitions alike. These all returned
finished fixtures with full scores:

| Query | Rows |
| --- | --- |
| `matches/history.json?competition_id=3&from=2026-09-16&to=2026-09-16` (La Liga) | 3 |
| `matches/history.json?competition_id=362&from=2026-06-10&to=2026-07-20` (FIFA World Cup) | 30 |
| `matches/history.json?competition_id=227&from=2026-01-01&to=2026-02-15` (Africa Cup of Nations) | 16 |
| `matches/history.json?competition_id=271&from=2024-06-15&to=2024-07-20` (Copa America) | 30 |
| `matches/history.json?competition_id=490&from=2023-07-15&to=2023-08-25` (Women's World Cup) | 30 |

**What we see is a delay that varies, and one gap that has not filled.**

| Matches played | When the archive first returned them |
| --- | --- |
| 2026-09-18 (La Liga) | Not by 2026-09-25. Seven days later it still returned only 09-16 and 09-17. |
| 2026-09-24 (UEFA Nations League, AFCON Qualifications, Arabian Gulf Cup) | 2026-09-26 at about 23:30 UTC, roughly two and a half days later |
| 2026-09-27 (UEFA Nations League) | The same evening |
| 2026-09-29 (AFCON Qualifications) | The same evening |
| 2026-09-24 (National Teams Friendlies, `competition_id=371`) | By 2026-10-01 at about 07:46 UTC (we keep only the latest answer with rows), with five of the day's matches but not the three below |

Three friendlies from 2026-09-24 are missing:

- Solomon Islands v Vanuatu (04:00 UTC)
- Papua New Guinea v New Caledonia (07:00)
- Turkmenistan v New Zealand (09:30)

Our queries were single-day: `matches/history.json?competition_id=371&from=2026-09-24&to=2026-09-24`.
For the 09:30 slot, your live feed and the archive returned Palestine v New Zealand (finished 2-2),
while `fixtures/list.json` had listed Turkmenistan v New Zealand (fixture id 1899617).

**Questions:**

1. Is there an expected delay before a finished match appears in `matches/history.json`, and what
   determines it? We saw anything from the same evening to more than a week.
2. National Teams Friendlies are in the history archive, but three of 2026-09-24's matches have not
   appeared in it. Is there a reason they would not? Was fixture 1899617 replaced by the
   Palestine v New Zealand match?
3. Is there anything about single-day queries that we should do differently?

We are not asking you to backfill anything. We would like to know what to expect, so that we retry
sensibly instead of either giving up too early or asking repeatedly for data that will not come.

---

## 3. How long does a finished match stay in `matches/live.json`?

Your documentation says finished matches remain in the live feed for a while after full time. But
the same page gives "up to 3 hours", 1 hour 15 minutes after a 90-minute finish, and 45 minutes
after extra time (https://live-score-api.com/documentation/reference/6/getting_livescores [S5],
read 2026-10-07 through an automated page summary; confirm on the page before quoting). We would
rather ask than guess which applies.

What we observed on one evening, 2026-09-24:

- A poll at **21:06 UTC** carried seven UEFA Nations League fixtures that had kicked off between
  18:45 and 18:49, all shown as finished. It did not carry Andorra v Malta, which had kicked off at
  16:01.
- A poll at **23:08 UTC** returned three matches in total: two finished, one in play at minute 79.

Two observations on one evening tell us what the feed held at those moments, not your retention
rule, so we have not built anything on them.

**Question:** how long after full time does a finished match remain in `matches/live.json`, and does
it differ by competition? Knowing this would tell us how long a missed match stays recoverable from
the live feed before we have to rely on the archive.

---

## Account and volume, for context

| Item | Figure |
| --- | --- |
| Account | One Live Score account, used from one installation. Whether it is still a trial account, and when that trial started, are questions 1 and 2. |
| Our daily ceiling | 1,200 requests. The trial allowance was 1,500 a day, and every paid plan allows at least 14,500 [S3]. |
| Scheduled caps | About 1,200 a day before pagination and retries; the hard ceiling of 1,200 is what binds. (The code comment's 1,182 omits up to 32 results requests made by the fixtures passes.) |
| Measured | Heaviest day 683 (2026-09-20, club competitions only). Our background scheduler alone averaged about 546 a day from 2026-09-25 to 2026-10-02, and live polling was two thirds of what it sent. Requests made by page loads are not in that ledger, and daily totals for those days were not kept, so the average for all our traffic in that period is not known. |
| Since the refusals began | 65 requests in two days. Most of 2026-10-06 sent nothing because the server was off. |

We are not asking for a limit increase. Volume is not what decides the plan; coverage and history
depth are.
