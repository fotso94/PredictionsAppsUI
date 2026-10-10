# What this application does not yet do

Measured against the running installation, not inferred from the code. Everything here was checked
on 2026-09-20 unless the entry names a later date. Each one says what is missing, why it is still
missing, and what closing it would take. An entry here is a commitment to honesty, not a promise of
a date.

## Language

**The backend's rule prose is English only, on every page that shows it.**
The settlement rules, the market definitions and the minimum-sample rationale are constants in
`backend/app/services/settlement.py` (`MINIMUM_SAMPLE_RATIONALE`, `HIT_RATE_DEFINITION`) and the
interface renders what the server sends. A French reader meets English paragraphs on the home page
and on every match page.

This is deliberate, not an oversight. Those sentences decide whether a figure is withheld, whether
a void counts as a loss, and what a hit test actually compares. A French paraphrase that drifted
from the English rule would be worse than English, because the reader would then be told a rule the
system does not apply. Closing it means localising them at the source, with a native reviewer
checking that each translated rule still says exactly what the code enforces.

A characterisation test in `frontend/e2e/mocked/localisation.spec.ts` counts the untranslated prose
rendered on the French home page, so the gap is visible and cannot grow unnoticed. The count comes
down deliberately or not at all.

**Two pages are untranslated: `MatchDetailPage` and the developer pages.**
`MatchDetailPage` does not call the translation hook, so its labels are English in both languages.
Its timestamps are correct, however: both were converted to the reader's chosen zone. `APITestPage`
and `DebugAPIPage` are developer tools and are not reader-facing.

**The French is not reviewed by a native speaker.** It was written and checked by machine, and
every term the writer was unsure about was flagged during the work. Market and money vocabulary in
particular deserves a human read before anyone relies on it.

## Time zones

Every reader-facing timestamp now goes through the formatter that honours the chosen zone, and the
two remaining device-zone calls on the match detail page were converted. Two hazards are worth
knowing rather than fixing:

- A backend timestamp that carries no offset is read as UTC. That is a claim, not a fact, and
  `backendInstant` reports whether the server actually said. A page that shows such a value should
  say so rather than present it as certain.
- A date-only value is a calendar date and not an instant. Rendering it in a zone behind UTC would
  move it to the previous day, so it is deliberately not converted.

## Live updating

A saved fixture discovers its own kickoff while the tab stays open, and so does a fixture that
appears only because the reader follows a team or competition. Both watches respect the reader's
automatic-updates preference, stop behind a hidden tab, and cost no provider request.

**What is unproven is the real thing.** No fixture has been in play during any test run, so the
in-play path has only ever been exercised against stubbed data. One live test,
`a fixture in play keeps its running score under a running label across a return`, skips for
exactly this reason and will run the first time a saved fixture is genuinely live. Until then, the
transition is proven deterministically and not observed.

**And on 2026-09-21 that became true of most of the live suite, not one test of it.** Thirteen
guards across `e2e/live/` skip when the local database holds no fixture for the day they need, and
the calendar gap recorded under *Upcoming fixtures* below empties every one of them: the run is 19
passed and 37 skipped, against 55 passed and 1 skipped on 2026-09-20 when the store still held that
day's matches. Nothing regressed — the mocked suite covers the same journeys deterministically at
618 tests — but real-backend coverage is a function of whether football is being played, and
between 2026-09-21 and 2026-10-09 it is close to nothing. Read a green live run in this window as
evidence about very little.

## Forecast coverage

Coverage depends on a trial allowance of eight requests a day against six competitions, so it is
never complete on the day a fixture appears. The provider also enforces its own window, which is
not the UTC day this application counts against; the application now reads the provider's
rate-limit headers and waits on its published reset rather than guessing.

`backend/scripts/diagnose_forecast_coverage.py` reports, for any day and without a provider
request, which fixtures lack a forecast and why. It reports `unexplained` rather than guessing when
the stored records cannot evidence a cause.

## Upcoming fixtures

**No provider has offered a fixture for today or any day after it, and that is the provider's
calendar, not a broken pipeline.** Measured on 2026-09-21: every match in the store that came from
a provider is dated 2026-09-20 or earlier — 48 finished and one stuck live. (A row dated later is
not by itself a fixture: the expert-prediction flow writes a placeholder match, `is_placeholder`
in its metadata, dated the moment it is saved.)

Ten diagnostic requests to Live Score API, made through the application's own provider class so the
budget counted them, settle what was happening:

| competition | id | earliest fixture in its calendar |
| --- | --- | --- |
| Bundesliga | 1 | 2026-10-09 |
| La Liga | 3 | 2026-10-09 |
| Premier League | 2 | 2026-10-10 |
| Serie A | 4 | 2026-10-10 |
| Champions League | 244 | 2026-10-13 |

Ligue 1 was not probed individually; the allowance for this diagnosis was spent. `fixtures/list.json`
answers normally: filtered by competition and date it returned the six Premier League fixtures of
2026-10-10, and zero for Saturday 2026-09-26. The calendar is chronological — page 1 of the Premier
League ends on 2026-10-31 and page 2 begins there — so the first page really does carry the next
fixture there is.

The scheduler asks for today and the next two days (`SYNC_FIXTURES_DAYS_AHEAD=3`) and the league
pages ask for seven. The nearest fixture is eighteen days out. Both windows therefore look only into
a stretch that is genuinely empty, and both are told so correctly. Nothing is being dropped in
mapping, no competition id is wrong, and the trial plan is not withholding forward fixtures: the
48 stored matches were themselves written in the early hours of 2026-09-18, for kickoffs running
from that evening to 2026-09-20 — the furthest more than two days ahead — which is the
forward-fixture path working end to end.

Closing it is a decision about cost, not a repair. Widening the daily window costs one request per
competition per day; reaching 2026-10-09 from here would be nineteen days by six competitions. The
cheaper route is the calendar call the league pages already use (`fixtures/list.json` with no date,
one request per competition for a whole season) with a window long enough to contain the gap.

**A pass that stores nothing can look exactly like a full matchday.** Measured 2026-09-21:
`sync:task:fixtures` had recorded `source: "provider"`, `errors: []` and nothing else for three days
running, which is how a pipeline can be dead for a week before anyone looks.

The task result now keeps the three ingests of one `sync_day` apart. `fixtures_seen` and
`fixtures_stored` count all of them together; `forward_seen` and `forward_stored` count the forward
fixtures list alone, which is the only one that answers *did the forward list hand back a fixture
for a day we asked about*. Every pass lands in exactly one state, recorded as `forward_answer`:

| `forward_answer` | what happened | effect on the streaks |
| --- | --- | --- |
| `fixtures` | **at least one** day was offered a forward fixture, in an answer fetched for this pass or still inside its cache TTL | both streaks reset; `last_seen_at` moves |
| `empty` | no day was offered a forward fixture, and every day asked was answered | `empty_passes` + 1 |
| `not_answered` | no day was offered a forward fixture, and at least one day fell back to the 24-hour stale copy or got no answer at all | `unanswered_passes` + 1, `empty_passes` left where it was |

A sighting outranks an outage, so the word alone is not a report on the whole pass. With the
production `SYNC_FIXTURES_DAYS_AHEAD=3`, a pass where today answers with one fixture and the other
two days raise records `forward_answer: "fixtures"` with both streaks at 0 — the two dead days
appear only in `days_unanswered` and `days_from_stale_cache`, which is why `scripts/sync_once.py`
prints those counts beside the word. To ask *was every day answered*, read those counts, not
`forward_answer`.

`forward_stored` counts the fixtures the registry accepted, and `upsert_fixture` returns the
existing match when it only updates a row already held. A forward list that re-offers matches we
already have therefore counts as seen and stored alike: neither number says anything was new. So a
late-evening pass on a matchday, where the day's list comes back holding the six matches already
played and already stored, records `seen 6, stored 6` and resets both streaks — a true statement
that the provider answered, and no evidence at all that the calendar ahead is being filled.

`last_seen_at` is stamped with when the answer was fetched, not when the pass read it, so a cache
hit dates the sighting to the provider call it came from. `last_seen_basis` says which kind of
timestamp it is: `sync_pass` for a fixture this task was handed, `matches_table` for the newest row
written ahead of its own kickoff. The streaks and the sighting are both carried in the previous
pass's stored summary (`sync:task:fixtures` → `last_result`), so they count passes since that
summary was last written, not passes since the last fixture. The summary is absent on the first
pass, after a pass that raised (`_maybe_run` records `last_result: null` for any exception the task
does not catch), after the 14-day state TTL, and on every pass while Redis is unavailable — the
cache read returns `None` and the save is a silent no-op. In each of those the streaks restart at
0 and the sighting falls back to the `matches_table` reconstruction, which can therefore reappear
long after a real sighting; the basis is what keeps the two apart, so it has to travel wherever the
timestamp does — `sync_once.py` prints it beside the date, and `/data-providers/status` publishes
the whole `last_result`. The fallback exists because saying "never" on an installation holding 48
rows written ahead of kickoff points at a broken integration rather than at the calendar gap that is
actually there. Run read-only on 2026-09-21 the query returns 2026-09-18T03:13:20Z, the newest of
the 48 rows written before their own kickoff. What it leaves out is every row created at or after
its own kickoff: the duplicate Everton v Ipswich, written 74 minutes *after* that kickoff by a live
poll, and the placeholder matches the expert-prediction flow creates dated `utcnow()`. Neither kind
of row is a fixture that arrived in advance, and neither may be dated as one. `get_upcoming`
separately logs whether an empty window means the competition has no calendar at all or simply no
round before the window closes.

Four rules keep this reporting able to see what it is for. Each is cheap to break by accident, and
breaking any of them leaves a pass that stored nothing looking exactly like a healthy one.

1. **Read the forward counters for the forward question, never `fixtures_seen`.** One `sync_day`
   runs three ingests through the shared pair. One unsettled match dated today that has already
   kicked off — or kicks off within the next quarter of an hour — is enough for `_sync_results`
   (kickoff at least 150 minutes ago) or `_sync_live` (from 15 minutes before kickoff to 150
   minutes after) to hand back a day of fixtures on a pass whose forward list was empty. A match
   dated today at 20:00 seen by an 11:00 pass satisfies neither, so the date alone is not the
   condition. Not hypothetical here: the stuck Everton v Ipswich row described below is unsettled
   right now, and only its 09-19 date keeps it clear of this.
2. **A stale cached copy is not an answer.** `_call_chain` serves a copy up to 24 hours old when
   every provider fails; counted as fixtures being offered, a provider outage shorter than a day
   reads as four healthy passes.
3. **A pass where every provider raised is not a quiet calendar.** It gets `unanswered_passes`,
   and `empty_passes` holds its place, so an outage and a league between rounds never land under
   the same number.
4. **Exercise the multi-day pass.** A test suite that pins `SYNC_FIXTURES_DAYS_AHEAD` to 1 never
   runs the shape production runs, and everything about how one day's answer combines with
   another's goes untested. Likewise, a test that pins `matches_for_day` to `[]` disables both
   `_pending_results_exist` and `_live_window_open`, which is the only state in which rule 1 can
   fail. In `backend/tests/test_fixture_pipeline.py` neither is fixed: the day count is set per
   test through the `days_ahead` fixture, the stored rows are a `build(...)` argument, and two
   tests run the three-day pass.

What this does **not** do is decide anything. There is no alert and no threshold: two streaks, a
timestamp and its basis, read by `backend/scripts/sync_once.py` or off the admin status endpoint by
a person who is looking. An empty week is still a success, because a league between rounds has
genuinely nothing to give.

## The archive answers late, and three friendlies have never settled from it — cause unknown

Every observation, dated, is in `docs/evidence/livescore-archive-observations.json`, including the
application's own record per competition and date (`recorded_by_the_application`).

**The archive works, for club and national-team competitions alike.** `matches/history.json`
returned finished fixtures with full scores for La Liga on 2026-09-16 and -17, and for past
national-team tournaments: the FIFA World Cup (June–July 2026, 30 rows), the Africa Cup of Nations
(January–February 2026, 16), Copa America (2024, 30) and the Women's World Cup (2023, 30).

**It answers late, by a delay that varies.** Asked on 2026-09-22 and again on 2026-09-25, it held
nothing dated 2026-09-18 or later. Then on **2026-09-26 at 23:30 UTC**, on the sixth ask, it
returned the 2026-09-24 rows for UEFA Nations League (8), AFCON Qualifications (8) and the Arabian
Gulf Cup (2) — about two and a half days after the matches — and the recovery sweep settled five
stranded fixtures from that answer with no manual step. Later dates came back within hours:
UEFA Nations League 2026-09-27 the same evening, AFCON Qualifications 2026-09-29 the same evening.

**For National Teams Friendlies on 2026-09-24 it did answer, without three of the day's
fixtures.** The application recorded an answer with rows for that date on **2026-10-01 at 07:46
UTC** (`last_answered_at`; whether an earlier ask had already returned rows is not recorded): five
of the day's friendlies came back finished, Japan v Uruguay among them. Solomon Islands v Vanuatu,
Papua New Guinea v New Caledonia and Turkmenistan v New Zealand did not settle from it, and still
wait (below). The "empty" answers recorded for that date afterwards, at 2026-10-02 08:12
UTC and from 2026-10-05, were no answers at all: API-Football, which holds no id for the
competition, was recorded as answering although no request was sent (see *A provider that could
not be asked was recorded as answering*, below). This page said until 2026-10-05 that the archive
had never answered for that date, on the strength of the first of those records; that was wrong.
Club dates 2026-09-18 to -23 were not asked again — every club fixture of that round had settled
from the live feed — so what the archive holds for them is unknown, not empty.

**What is known and what is not.** A delay exists and is not constant (same day for some dates,
2½ days for three of 2026-09-24's competitions, up to a week for its friendlies, more than seven
days for 2026-09-18 as of 2026-09-25). Friendlies are in the archive: it returned them for
2026-09-24, -27, -28, -29 and -30 and 2026-10-01. Why the delay varies, and why those three fixtures
have not settled, is **unresolved**; the questions are in `docs/support/livescore-api-questions.md`,
prepared and not sent. One detail may bear on the third: at 09:30 UTC that day the live feed and
the archive carried Palestine v New Zealand, finished 2-2, where the fixture list had carried
Turkmenistan v New Zealand.

The captured archive answer for 2026-09-16 is kept at
`docs/evidence/livescore-history-2026-09-16-la-liga.json` — the response rows only, since the key
and secret are request parameters and never appear in a reply.

## A stranded fixture can be recovered, by hand, when the archive holds the day

Measured 2026-09-22 in the isolated `soccer_predictions_qa` database, restored from
`backups/soccer_predictions-20260921-182357.sql`. Four Live Score requests, no GameForecast, the
live database untouched throughout.

Barcelona v Racing Santander, 2026-09-16, was ingested through the registry exactly as the
application would store it, then stranded: status back to `SCHEDULED`, its `match_results` row
deleted, its recovery bookkeeping cleared and the day's cached answer dropped so the sweep had to
ask. `scripts/repair_unsettled_matches.py --apply` then selected 2026-09-16, spent exactly one
request, and reported:

```
2026-09-16: source=provider polled=True seen=3 stored=3 errors=[]
recovered 1   came back settled; nothing left to retry
```

The row came back `FINISHED` **7-2**, result `H`, matching the archive answer captured before the
test was staged. No attempt was spent, because a recovery is not a failed question.

**That is a recovery, and it is not automatic recovery.** Three things separate them:

- **Nothing invoked the sweep when this was measured.** It ran only when a person typed the
  command. That is now closed: `SYNC_SCHEDULER_TASKS` includes `recover`, which runs the same
  `recover_stranded` every half hour, before `settle` in the same pass. The script remains for a
  sweep somebody wants to watch, or one run against a restored copy.
- **It only works where the archive answers.** The demonstration used 2026-09-16 precisely because
  the archive holds it. For anything dated 2026-09-18 or later the same sweep has so far received
  empty answers, for club and national-team competitions alike — the unresolved boundary recorded
  above. That is a question about dates, not about which kind of competition a fixture belongs to:
  the archive has answered for past World Cup, AFCON, Copa America and Women's World Cup matches.
- **One fixture on one day is not a fleet.** The cost is one request per competition-day for the
  first page, up to five times that if every one paginates to the cap — a default pass measured 60
  requests where the script had printed 12, which is why it now prints both figures. Affordable
  against Live Score's 1200 a day; it would not be against GameForecast's 8, which is why the sweep
  never touches it.

**When the application stops asking, and what that means.** Every competition, club or national,
follows one retry schedule: every pass until six hours after kickoff, then progressively less often
— every two hours to a day, every six hours to three days, twelve hours to a week, daily to fourteen
days. Against an archive that stays empty one fixture costs about 39 requests over the fortnight
instead of 672 at a flat half-hourly cadence. Fourteen days is where the application stops, and that
is **a limit on what we are willing to spend, not evidence that no result exists**; the reason
written on the fixture says so. A network failure is recorded as a failure and never counts towards
it — only a question the provider actually answered does. What has not been shown is that the
provider serves anything as far back as fourteen days for recent matches; the archive boundary above
is exactly that question.

**What a reader is told about the last check.** The API (`recovery.last_outcome`) and the page keep
four things apart. *The provider answered without a result for this match* (`fresh_unanswered`) is
the only one counted as an attempt, and says what that answer held at that moment. *A request went
out and got no usable answer* (`provider_error`) is an outage, ours or the provider's, and says
nothing about the result. *No request was sent* (`deferred`) is worded by the cause the backend
records in `last_deferred_because`: our own request allowance, the provider's own reported limit, or
a pause after an earlier request failed — and only the first is described as our limit. *Our stored
copy was read instead of asking* (`cached`) claims no call. A stop the retry budget made
(`stopped_by: retry_budget`) is described as our allowance; a stop left by a rule since removed is
not attributed to it, and the recovery pass undoes it.

## When a result is missed while the match is being played

A result goes missing when the provider cannot be reached while a match is live — our connection
dropped, or theirs did. There are two places it can come back from afterwards, and what we know
about each is less than it first appeared.

**The live feed, `matches/live.json`.** It lists matches in play and ones that have recently
finished. On the evening of 2026-09-24 a poll at 21:06 UTC carried seven UEFA Nations League
fixtures that had kicked off at 18:45–18:49 and did not carry Andorra v Malta, which had kicked off
at 16:01. That is one observation of what the feed held at one moment. **It is not a retention
rule.** The provider's documentation says finished matches stay in the feed after full time, with
durations we could not reconcile, and how long they stay is one of the questions put to support.
The 150-minute window this application polls within is our own setting, not the provider's.

**The archive, `matches/history.json`.** It answers for club and national-team competitions alike,
late by a delay that varies, and for one competition and date not at all so far — see the section above.

So what we can say about a missed result depends on its date, not on whether it is a club or a
national team:

| Missed result | Recovered so far? | What we know |
| --- | --- | --- |
| Still in the live feed when the next poll runs | **Yes**, observed | the ordinary live task collects it |
| Dated on a day the archive holds | **Yes**, observed by hand for 2026-09-16 | the results task can collect it |
| Dated on a day the archive answers late | **Yes**, observed automatically: 5 of 8 on 2026-09-26 | the retry schedule collected them ~2½ days after kickoff |
| Three National Teams Friendlies, 2026-09-24 | **Not yet** | the archive answered for that date on 2026-10-01 without them; whether it ever will return them is unknown |

**Nothing here says a result cannot exist.** The application keeps asking under a retry *budget*,
and stopping is a decision about what we are willing to spend, not a finding about the provider. A
reader of such a fixture is told what happened — no result has arrived, and when we last asked — and
never shown a score nobody reported. Of the eight national-team fixtures from 2026-09-24 that were in this state,
five recovered automatically on 2026-09-26; as of 2026-10-05 three remain — Solomon Islands v
Vanuatu, Papua New Guinea v New Caledonia, Turkmenistan v New Zealand, all National Teams
Friendlies — each recorded as asked 20 times. At least two of those were not asks: at 2026-10-02
08:12 UTC and 2026-10-05 03:23 UTC API-Football was recorded as answering, without a request, for
a competition it holds no id for (see below). How many earlier ones were the same is not recorded.

## A finished match that read as live: repaired, with the identity gap narrowed

Measured 2026-09-22 against the live database and a restore of
`backups/soccer_predictions-20260921-182357.sql`, the dump taken before the repair.

Everton v Ipswich, 2026-09-19 14:00 UTC, was stored twice: once correctly `FINISHED` from Live
Score API, and once `LIVE` at minute 62 from API-Football, whose "Ipswich" did not match the
stored "Ipswich Town". `scripts/repair_duplicate_matches.py` moved every dependent row onto the
surviving copy and deleted the emptied one. What that cost, row by row:

| Table referencing `matches` | survivor + loser, before | survivor, after |
| --- | --- | --- |
| `predictions.predictions` | 0 + 7 | 7 |
| `predictions.provider_forecast_snapshots` | 3 + 0 | 3 |
| `predictions.match_results` | 1 + 0 | 1 |
| `predictions.provider_forecasts` | 1 + 0 | 1 |
| `predictions.provider_forecast_results` | 1 + 0 | 1 |
| `ml_models.ml_predictions`, `predictions.match_statistics`, `users.saved_matches` | 0 | 0 |

Thirteen rows before, thirteen after, **the same rows by primary key** and byte-identical in every
column but `match_id`. Zero orphans across all eight foreign keys. `provider_entity_refs` points at
matches through a polymorphic pair with no foreign key, so `information_schema` does not list it;
it was checked separately and its two affected rows moved with the rest. The surviving row was
never edited — its `to_jsonb` hash is identical before and after — so this was a move, not a merge.

The table went 50 matches to 48: the duplicate and one dependant-free `Home Team (TBD)` placeholder
were removed and nothing was added. Predictions went 250 to 255, none lost, five added by this
session's own test runs.

**The identity gap is narrowed, not closed, and deliberately so.** Cross-provider club identity now
comes from provider references and a curated alias list rather than from name similarity, because
no rule can separate "Cardiff"/"Cardiff City" (one club) from "Dundee"/"Dundee United" (two): they
are the same string shape. A club whose spellings are not on that list is therefore stored twice
again. That is the safe failure — `scripts/repair_duplicate_matches.py` reports duplicates, and a
person folds them back — whereas a wrong merge re-points the provider's team reference and misfiles
that club on every later fixture, silently. Four alias entries carry no evidence from this database
and say so on their own lines.

## The empty-break notice can go stale in a tab nobody touches

During the international break an empty matchday names when football resumes. The date is filtered
against the clock twice: at the endpoint, per request, and in the browser, where a remembered
answer expires at the kickoff it names or, when it names none, after six hours.

What neither guard covers is a tab that simply sits on one empty day. `NextFixturesNote` fetches
once and has no timer, so a fixture whose kickoff passes while the reader watches stays on screen —
measured, the text was unchanged fourteen seconds after the kickoff it named. The window is the
hours between opening the page and the first kickoff. Closing it means a refresh on an interval or
on tab focus, and neither exists.

**A failing calendar sweep has no cheap floor.** The six-hour cache is what keeps this feature to
about 24 requests a day, and a sweep that FAILS writes no cache, so only a 120-second lock and a
120-second cool-down stand between a stream of readers and a stream of requests. Simulated, that is
of the order of a thousand requests a day of demand: bounded by the daily allowance rather than by
the feature, and exhausting it would also stop the ordinary fixtures sync until UTC midnight. The
provider would have to fail continuously for hours for this to bite, and it has not happened, but
nothing in the code prevents it.

## No match-data source is answering: Live Score refuses our key, and the fallbacks cannot stand in

The primary match-data source answered the first request after the local fault was fixed —
2026-10-05 03:23 UTC — with **HTTP 401, "This API key and secret do not have access to our data
enabled"**, and has answered every attempt since the same way, the latest checked on 2026-10-07.
The last successful answer was 2026-10-02 14:53 UTC; in between our process could not send
anything, so when access stopped inside that window is unknown. Nothing changed in how the key
and secret are sent.

**What the 401 does and does not show.** It shows an access problem. It does not by itself show
that a purchase is needed: Live Score's own Standard Errors page documents HTTP 402 for a missing
or expired subscription and HTTP 401 for an invalid key and secret, and what we receive is a 401
with a message that page does not list. The same text also answered request bursts on 2026-09-17,
while the trial was active. An ended trial is plausible and unconfirmed.
`docs/support/livescore-api-questions.md` now holds the ready-to-send account question, the exact
entitlement our existing coverage needs (endpoints, the 6 club and 29 national-team competitions
with their ids, history depth, request volume) and a checklist for the owner. It is prepared, not
sent, and nothing has been purchased.

**The retained fallbacks cannot stand in for it.** What each source answered on 2026-10-05:

| Source | Its answer |
|---|---|
| Live Score | HTTP 401 as above, at every attempt from 03:23 UTC (skipped for 30 minutes after each) |
| API-Football (free plan) | At the 06:01 UTC fixtures pass: "Free plans do not have access to this season, try from 2022 to 2024." |
| TheSportsDB | At the same pass: HTTP 400, "Invalid Premium API key" |

So no configured source can currently add or update a fixture, a live score or a result, for any
competition. For national-team football there would be nothing to fall back to even if they
answered: none of the 34 national-team competitions has an API-Football or TheSportsDB id (all 34
have a Live Score one). On 2026-10-07 at 01:30 UTC, 96 fixtures had kicked off with no stored
result — 44 UEFA Nations League (2–6 Oct), 28 CONCACAF Nations League (2–6 Oct), 24 friendlies
(24 Sep – 4 Oct) — no result of any kind had been stored since 2026-10-02 13:36 UTC and no new
fixture since 14:46 UTC, and only 4 future fixtures were held. (On 2026-10-05 at 05:10 UTC the
count was 67.) A slip holding such a fixture stays *pending*; nothing settles until a result
source answers. (The
results and recovery passes recorded API-Football as having answered for those competitions, with
no rows, although it sent no request, having no id to ask with. That is fixed, and the records it
had written were repaired on 2026-10-09 — see the next section.)

Forecasts still arrive — GameForecastAPI answers (8 of 8 requests with HTTP 200 on the 2026-10-07
01:04 UTC pass) — but only attach to fixtures already stored. It returned 48 club fixtures for
9–12 October; 3 were in the store and 45 wait, unattached and free to attach later (they are kept
48 hours), until a fixture source can list them.

Each attempt at Live Score while it refuses costs two requests: the adapter retries a 401 once,
because the provider also answers 401 to bursts. After a refusal the provider is skipped for
30 minutes, so the refused traffic stays at most about four requests an hour.

Stored fixtures and forecasts are still served. Restoring a match-data source — Live Score, or a
paid plan at one of the fallbacks — is a purchase or support decision for the owner; nothing in
this repository works around it.

## While no match-data source answers, the pages say so — once, plainly, with the forecasts kept

The backend publishes one `match_data` block, on `GET /api/v1/data-providers/status` and on its own
at `GET /api/v1/data-providers/match-data` (about 1 KB). It is derived from what is already recorded
and sends no provider request (`backend/app/services/match_data_health.py`). Its states are `ok`,
`degraded`, `blocked` and `unknown`. It reads **blocked** when no configured source is delivering
fixtures or results and either every source refused (access or plan) or ran out of allowance, or the
fixtures/results passes have failed three times running with nothing a provider's answer wrote for
six hours. A fallback that "answers" during such a stretch without writing anything (API-Football's
free plan answers a live poll) does not lift it. Since 2026-10-07 02:52 UTC the running backend
serves it, and it reads `blocked`, nothing new since 2026-10-02 14:52 UTC.

**What a reader sees while blocked.**

- The site banner leads with one sentence: fixture and result updates are unavailable at the
  moment, nothing new has reached us since {date}, forecasts for matches we already hold are still
  shown. If the forecast source has a fault of its own, that clause is replaced by the fault. Each
  source's reason, and the provider's own English words marked `lang="en"`, sit behind the
  disclosure; the visible line names no vendor, HTTP code or link, and nothing states when it ends.
- The freshness block reads "no new fixtures or scores since {date}" and its three failure notes
  become one line. It used to say "fixtures and scores last refreshed 4 minutes ago" in this state,
  because the recover and settle passes, which fetch nothing, counted as refreshes. In every state
  the line now keeps two facts apart: "new fixtures or scores last arrived {when}", the newest row
  a provider's answer wrote (`match_data.since`, measured on the rows and checked against the
  provider's own record), and "last checked {when}", the newest completed fixture-side pass — which
  can succeed having sent nothing, and is never called a refresh. A backend without `match_data`
  gets only "last checked". Each task's row says "last succeeded", and says when its last pass sent
  no request to any provider.
- An overdue result reads "result updates are unavailable at the moment" on the day list and on the
  match page; an upcoming kick-off is said to be the last one stored; forecasts and markets render
  unchanged. An empty day, the slip and the slip history say that fixtures or results cannot arrive
  for now. Suggestions say they are built only from stored fixtures and count the retrieved
  forecasts waiting for a fixture.
- `degraded`, `unknown` and a backend without the block show nothing new: the banner keeps its
  older rules for a failing primary.

**Known limits.**

- A refusal's kind is recorded from the exception at the moment of failure; older records are
  classified from their text, so a vendor that rewords a refusal may be read as `unavailable` and
  reach `blocked` only through the three-failure, six-hour rule.
- Each source is judged by its latest record. A source that refused its last call but still
  delivers on others would read as refused. Since a provider is asked only about competitions it
  holds an id for, such a refusal means its plan does not cover a competition or season we need.
- "Nothing new since" is bounded by each provider's own record, because the registry stamps
  `last_synced_at` when it stores a row, and it also stores again copies served from the match cache
  (the 24-hour stale copy once every provider has failed). A stamp its provider's record cannot
  account for counts only as that provider's last answer. The exact fix is for the registry to stamp
  the time the provider produced the data; it is not made yet.
- Cool-downs are unchanged: API-Football's plan refusal and TheSportsDB's invalid-key refusal still
  cool down for two minutes.

## A provider that could not be asked was recorded as answering: fixed, and the record repaired

**What happened.** API-Football and TheSportsDB hold an id for the six club competitions and for
none of the national-team ones. Asked for results across several competitions, each skipped the
ones it had no id for and returned what it had for the rest — for a national-team competition, an
empty list, with no request sent — and the call chain took that list as an answer. So whenever
Live Score was out of the chain (cooling down after a failure, and from 2026-10-05 03:23 UTC
refusing every request), a national-team results call was recorded as answered, with nothing in
it: an attempt counted on each fixture it covered, the fixture's next ask pushed back by the retry
schedule, and an `empty` observation written over whatever the archive had last said for that
competition and date. The application's own record shows it on **2026-10-02** (API-Football at
08:12 UTC, TheSportsDB at 08:43 UTC), and on every results and recovery pass from 2026-10-05
03:23 UTC. Whether it happened earlier is not recorded: an observation keeps only the provider of
its last answer.

**What changed.** A provider is asked only about the competitions it can name, and its answer
counts for those alone. One that can name none of them is passed over the way a provider that sent
nothing is — no cool-down, no failure on its status, nothing charged — and the chain moves on. A
competition nobody can be asked about is recorded on each fixture as *deferred*, with `not_served`
among the reasons, and its attempts, its retry schedule and the archive's record are left exactly
as they were. That is not reported as a fault of the pass: a gap in coverage is not an outage.
TheSportsDB is also no longer taken to have polled live scores, which its v1 API does not publish.

**What the store still says.** Nothing already written has been changed. Measured read-only on
2026-10-07: **13 archive observations and 66 fixtures**. The 10 and 44 counted at 2026-10-05 22:55
UTC grew because the earlier code kept running until the machine restarted; its last pass, at
2026-10-06 00:25 UTC, added 3 observations and 22 fixtures, all dated 4 October. A reader is still
served those attempts with an `empty` archive. The current code's passes have since replaced the
"api_football answered …" sentence on 65 of the 66 with a genuine `deferred` outcome, so that text
no longer finds them; their stamps do. After Live Score's last success (2026-10-02 14:53:28 UTC)
exactly 29 observation asks and 161 fixture attempts are not-answers; one more on 3 observations and
6 fixtures, on 2 October before that, is proven by a capture; earlier ones are possible and
unrecorded.

**The repair, rehearsed and waiting for the owner.** `backend/scripts/repair_not_answers.py` takes
these writes back by rule, never from a list of ids: a national-team competition has no API-Football
or TheSportsDB id, so anything recorded for one after Live Score's last success is false. On a
restored copy (`soccer_predictions_rehearsal_notanswers`, kept for inspection) it removed the 8
observations no provider that could answer was ever asked about, restored 2 from the backup taken
before the outage (marked `unverified`), and set 3 whose earlier entry was itself a not-answer to
Live Score's last real answer, read from the match rows that answer synced (marked `upper_bound` and
`reconstructed`). It cleared every attempt from 57 fixtures, restored 3 from the backup
(`unverified`) and reduced 6 to an upper bound. Every other row stayed byte-identical, no table's
row count changed, and a second run changed nothing. The plan, the invariants and the decisions the
owner has to make are in `docs/evidence/not-answers-repair/rehearsal.md`.

`attempts_quality` is served beside `attempts`, the archive says when its row count was
`reconstructed`, and a stop on a marked row states its count as "at most N" — on the API and on the
page, in both languages: a fixture given up on whose count is `upper_bound` or `unverified` reads
"The provider answered at most N times …", followed by how many of those predate the correction
and are not verified. A row with no mark keeps the exact sentence.

**Applied in the window 2026-10-08 23:53 to 2026-10-09 00:10 UTC, with the options the
recommended plan named** (reconstruction on; the proven 2 October not-answer subtracted; the
closed second listing corrected; Congo v Uganda kept `unverified`). Live Score was still refusing,
so the window the plan required was open.

**How the apply was authorized — corrected on 2026-10-09.** The assistant ran the apply on the
strength of the reviewer note the owner had forwarded that day ("Proceed toward the recommended
repair", with verification conditions). The reviewer has since clarified that this was a
recommendation, not owner authorization, and no separate owner approval was given beforehand — so
the script's `--owner-approved` flag was passed on a misreading, and this record says so plainly.
The technical result is verified below, in the reviewer's own read-only checks, and in
`docs/evidence/not-answers-repair/verification/`, which reproduces every window claim from the
backup alone; the rollback (the backup, and each row's `corrections` audit) remains available, and
keeping or undoing the repair stays the owner's call. The reviewer has since checked the applied
result and asked only that the record be corrected, not the repair repeated.

What the record shows, in order:

- Only the backend was stopped; the frontend served stored data throughout. After the scheduler's
  records aged out, a fresh plain backup was taken
  (`backups/soccer_predictions-before-not-answer-repair-20261008T235832Z.sql.gz`) and **verified by
  restoring it** into a scratch database; the plan the script derived from that copy matched the
  rehearsed plan on every corrected field.
- The report-only run against the live database found exactly what was rehearsed: 13 observations
  (classes 8/2/3), 66 fixtures (groups 57/3/6), 32 asks and 167 attempts to remove, the synced-row
  method agreeing 18 of 18. Its corrected fields matched `plan.jsonl` row for row; only the
  genuine deferral stamps the scheduler had moved since the rehearsal differed, as the plan said
  they would.
- `--apply` wrote 13 observations and 66 fixtures; a second `--apply` wrote **0** and skipped all
  66 as already corrected. The applied report is `docs/evidence/not-answers-repair/applied.jsonl`.
- Invariants, against the pre-apply backup: every one of the 311 untouched leagues/matches rows is
  byte-identical, the 70 target rows changed only in their metadata column and `updated_at`, and
  no table's row count moved across all 74 tables. No national observation names API-Football or
  TheSportsDB, nothing is stamped after Live Score's last success, and the quality marks read
  57 `exact`, 6 `upper_bound`, 3 `unverified`. The raw outputs, the comparison scripts and a
  reproduction of the whole chain from the backup alone are preserved in
  `docs/evidence/not-answers-repair/verification/` — the live database keeps moving its genuine
  recovery bookkeeping on every pass, as it should, so the window comparisons are re-established
  from the backup rather than against today's rows.
- The backend restarted on the current code (identity measured on `/health`), and its first
  recover and settle passes wrote only genuine deferrals: the tainted counts stayed at zero. The
  journey proof of 2026-10-09 flags exactly one in-window fixture for its attempt count — Congo v
  Uganda, the row deliberately kept `unverified` — instead of the 58 it had to flag by clock
  before.

The repair corrected bookkeeping only: no status, score, result or kickoff changed, and the 96
missing results are still missing until a match-data source answers. The rollback, should anything
surface later, is the backup above plus each row's own `corrections` audit record.

## Running it locally: what stopped updates for 2½ days, and how it is run now

From **2026-10-02 14:54 UTC to 2026-10-05 03:09 UTC no fixture, score, result or forecast was
fetched.** The backend kept serving what it had stored, so the site looked alive while it went
stale. Every provider call failed with `PermissionError: [Errno 1] Operation not permitted` —
raised while loading the TLS certificate bundle from the virtualenv, before any request left.

The cause was local, not the providers and not the network: the backend process, started on
2026-09-25 from an earlier desktop-app session, lost permission to read files under `~/Documents`
(where the repository lives) partway through its life. macOS also refuses that folder to Apple's
Command Line Tools Python (`backend/venv`) when the app launches it, so the backend could not even
start that way.

What changed:

- The certificate bundle is read **once per process** (`TLS_CONTEXT` in
  `backend/app/services/providers/http.py`), so a running backend no longer touches the disk for
  each provider request. A process that cannot read it fails at startup, where it is seen.
- The backend is started from the `backend` entry in `.claude/launch.json`, on the Python 3.11
  environment (`backend/venv311`, pyenv), which the app can launch. Both environments pass the
  backend suite. To use `venv` again, grant that Python access to the Documents folder in System
  Settings → Privacy & Security; this application does not change that setting.
- **Lifecycle:** servers started from `.claude/launch.json` belong to the desktop app and stop
  when its session ends — which is how the stack was found down twice in a week with the machine
  still up. `scripts/local-servers.sh start all` starts both pairs (main and isolated) detached from
  the app and the terminal; they then run until a reboot — or a crash, because nothing supervises
  or restarts them. `status` shows a gap, and `start` is safe to re-run any time: it skips what
  already listens. Supervision across crashes and reboots would be a launchd agent, a system
  setting the owner would have to add. `status` says who listens on each port and
  since when; logs and pids are in `.local-run/`. Nothing fetches while the backend is down; the
  scheduler picks up where it left off when it starts again (its due-times live in Redis). A launchd
  agent would survive a reboot too; that is a system setting the owner would have to add.
- **Counting during the incident:** each failed pass still counted one request against our own
  daily allowance (and one against GameForecast's eight) although nothing was sent. Those figures
  overstate real traffic for 2026-10-02 to -05; the provider's own counters were not affected.
- **Backoff after a local fault:** a task that fails backs off up to six hours, and that is kept
  across a restart. Nothing was forced after this incident. The recovery task, which never backs
  off, has run every 30 minutes since 03:23 UTC (that is how Live Score's 401 was learned). The
  other tasks came due at 06:01 UTC and ran: *live* succeeded (nothing was in play, so it sent
  nothing); *forecasts* fetched 7 of its 8 competitions and stored 16 fresh forecasts for the
  coming week, then stopped at the day's ceiling before the eighth; *fixtures* and *results*
  failed because every match-data source refused (previous section). The scheduler records the
  forecasts run as failed too, because it stopped short; all three are next due around 12:01 UTC.
- **Reserved is not sent.** `/api/v1/data-providers/status` now shows, per provider, the allowance
  reserved today (`used_today`) beside what actually went out on the network
  (`transmitted_today`: answered with a status / sent without an answer / never connected),
  recorded by the HTTP client at the moment of transmission. Across the 06:01 pass every new
  reservation matched a transmission with its status: GameForecast 7 answered 200, API-Football 1
  (200 carrying the plan refusal), TheSportsDB 1 (400), Live Score none (cooling down). Today's
  totals still differ — GameForecast 8 reserved and 7 answered; Live Score 21 reserved, 8 answered
  and 1 that never connected — because passes before 03:27 UTC reserved requests that never left
  the machine or ran before the counter existed, and at 05:25 UTC one request could not connect at
  all. GameForecast's unsent reservation, made by the failing 00:01 pass, cost CONCACAF Nations
  League its turn today: its 12 fixtures in the coming week have no forecast.
  Where a provider reports its own count, it agrees with ours: API-Football's rate-limit header
  said 6 of 100 used at 05:55 UTC, when we had reserved 6.
- **A reboot stops everything.** The machine restarted at 2026-10-06 01:09 UTC; Docker Desktop and
  both servers stayed down until 2026-10-07 01:02 UTC, so nothing was fetched or scheduled for a
  day, and the reboot also erased every scratch capture and test log of the previous round. To
  restore: open Docker Desktop, wait until `soccer_predictions_postgres` and
  `soccer_predictions_redis` report healthy, then `scripts/local-servers.sh start all`. The
  scheduler resumes from its due-times in Redis. Evidence now goes into `docs/evidence/` when it is
  produced.
- **Which code is running is measured, no longer inferred.** At startup the backend records its
  source identity (`backend/app/core/source_identity.py`) and serves it on `GET /health`: the git
  commit, the application files that differed from it at that moment, a sha256 digest of every
  `.py` file under `backend/app` as loaded (the algorithm is in the module docstring, and the
  test-evidence runner and the journey proof recompute it with the standard library), the process
  start time and the database name. Both tools compare the served digest with the checkout's and
  say `measured`; the runner refuses the live projects when the trees differ. File modification
  times remain only as the fallback for a backend too old to publish its identity, labelled
  `inferred`. A digest cannot show an edit made and undone before the start; the commit and the
  dirty list beside it say what the tree was.

## Test totals are kept as evidence, recomputable by anyone

The totals reported in earlier rounds (966 mocked browser tests, 57 live, 1,415 backend) cannot be
checked: no raw output survived. Playwright empties its output directory at the start of every run,
and the logs lived in a scratch folder the 2026-10-06 reboot erased.

`scripts/test_evidence.py run` runs the backend suite and each Playwright project once
(mocked-desktop, mocked-mobile, mocked-mobile-360, live, and live-isolated against the isolated
pair), takes every exit code from the child process itself, refuses to start on a dirty tree,
beside another test run, with a backend whose loaded source tree is not the one on disk, or with an
isolated backend that does not say it serves a database other than the live one, and watches for a
server restart, a foreign run or a change of commit during the run. Each summary records the suite
set its runner had, so `verify` judges an older run complete against the set of its day. It keeps the raw output in the
gitignored `.test-runs/` and publishes scrubbed JUnit files, console tails, `summary.md`,
`summary.json` and `SHA256SUMS` to `docs/evidence/test-reports/<run-id>/`.
`python3 scripts/test_evidence.py verify <dir>` recomputes every total and every check from the
committed files; a changed exit code, a dropped suite or a filtered run relabelled as complete fails
it. `docs/evidence/test-reports/README.md` has the layout and the scrub policy.

**The runs of 2026-10-07**, each in its own folder under `docs/evidence/test-reports/`:

| Run | Commit | Backend | mocked-desktop | mocked-mobile | mocked-mobile-360 | live |
|---|---|---|---|---|---|---|
| `2026-10-07T0301Z-7be42cc` | 7be42cc | 1644 passed | 449 passed, 2 skipped | 451 passed | 138 passed | 51 passed, 6 skipped, **1 failed** |
| `2026-10-07T0332Z-b753202` | b753202 | 1644 passed | 449 passed, 2 skipped | 451 passed | 138 passed | 51 passed, 6 skipped, **1 failed** |
| `2026-10-07T0408Z-12753b6` | 12753b6 | 1644 passed | 449 passed, 2 skipped | 451 passed | 138 passed | 52 passed, 6 skipped — **PASS** |
| `2026-10-08T0326Z-586b21a` | 586b21a | 1681 passed | 451 passed, 2 skipped | 453 passed | 140 passed | 47 passed, 9 skipped; live-isolated 2 passed — **PASS**, running code measured |
| `2026-10-10T1740Z-dd1c857` | dd1c857 | 1682 passed, **3 failed** | 451 passed, 2 skipped | 453 passed | 140 passed | 56 passed, 0 skipped; live-isolated 2 passed — **FAIL** (backend) |
| `2026-10-10T1811Z-37630ef` | 37630ef | 1685 passed | 451 passed, 2 skipped | 453 passed | 140 passed | 55 passed, 1 skipped; live-isolated 2 passed — **CONTAMINATED**: a pytest run not this runner's was seen for two minutes during mocked-desktop; every suite passed, the verdict stands, the run was repeated |

The first failure was a precondition: a live scroll-restoration check measured on a day whose three
stored fixtures fitted in a 1440x900 window (fixed in b753202). The second was a club crest from
Live Score's CDN unanswered for 45 s, which held a page waiting to go quiet (fixed in 12753b6: live
tests now fetch crests and the web font under a deadline, as the mocked tests do). The two mocked
skips are menu tests that apply only on narrow screens; every live skip comes from the outage:
nothing in play, no finished fixture with a result inside the feed window, and on 2026-10-08 no
fixture or forecast stored for the day at all (the store's last fixtures are the three club
matches of 9 October). The 2026-10-08 run is the first whose backend identity is measured rather
than inferred, and the first to include the isolated suite. The 2026-10-10 run, on the pager fix, is
the first since access returned in which every live test ran — 56, no skips — and its three backend
failures were three endpoint tests that dated their fixture rows by the calendar (9 and 10 October)
and read the endpoint against the wall clock: ahead when written, behind that evening. They now pin
the endpoint's clock (the next commit); no application code was at fault.

Limits: `verify` cannot see what only the run saw (a deleted record of contamination), and the
published files are scrubbed copies — only whoever holds the run's `.test-runs/` can show they came
from the raw ones, through the SHA-256 that `summary.json` records. Live totals depend on the day's
data and the providers, so they are comparable only together with their skip reasons. Backend totals
grew this round with the new tests, and `npm run e2e:mocked` now includes the mocked-mobile-360
project, so neither is comparable with earlier figures.

## The journey from fixture to settlement: proven to the stored result on the live database, and through settlement on a copy

`backend/scripts/prove_journey.py` follows each fixture through five stages, read-only: fixture
stored, forecast before kickoff, suggestion, stored result, settlement. It reads the database in a
read-only transaction, Redis through a read-only wrapper, and the API through an allowlist of
GET requests on this machine only; each run checks that it spent nothing, and is kept under
`docs/evidence/journey-proof/`.

Match-data access **returned on 2026-10-09 at 01:15 UTC**, when the Live Score Starter plan went
live on the existing key; an operator-run fixtures pass that night stored 41 fixtures, and the
recovery passes stored 82 international results between 02:06 and 03:37. The run of
2026-10-10T1716Z reads `returned`: of the fixtures that kicked off from 2 October, 97 have a
result stored since access came back and 6 had one before; 17 are overdue, and each of those is
accounted for one by one in `docs/evidence/overdue-and-waiting-2026-10-10.md` — one is a provider
feed that has stalled on a match in play, one is an exact duplicate of a played row, and the other
15 are absent from the provider's history on their dates; that absence does not establish what
happened to them, so they stay unresolved and no selection on them is voided. The 40 forecasts
waiting for fixtures are all for matches beyond the three-day fixture window; the cached
re-attachment that binds them once their fixtures are stored spends nothing, the forecast refresh
in the same turn can, and none is a matching failure. The same reading found that the provider
client read only the first page of a results answer (`total_pages` is the field that feed sends;
the client stopped on `next_page`), fixed with a regression test the same day; no competition-day
had exceeded a page.

The verdict `returned` needs three signals together: the primary provider answering, a fixtures or
results pass that asked it and was answered, and newly stored rows. It ignores what only looks like
recovery: a fallback's HTTP 200 carrying a plan error, a recovery or settlement "success" that sent
nothing, and `matches.updated_at`, which recovery bookkeeping moves.

**Settlement is proven on a copy, and owed on the live database.** A slip settles when its owner
reads it (`GET /api/v1/me/slips` settles and commits); the scheduler's settle task scores forecasts
and never touches slips. On 2026-10-10 the five recorded slips were read that way against a copy of
the live database taken at 17:14 UTC, through the isolated backend: `18724af2` (5 October: Cyprus v
Latvia home, France v Belgium over 0.5) settled **won**, the four of 7 October (Dortmund v Werder
Bremen home, which finished 2-2) settled **lost**, every leg with its rule and the score that decided
it, and a second read changed no row, no timestamp and no table
(`docs/evidence/journey-proof/settlement-isolated-2026-10-10/`). On the live database the same five
still read `pending: owner read` with the same dry-run outcomes, because that read is a write and
waits for the owner's explicit go-ahead. The suggestion stage can only be observed before kickoff;
the recorded slips' legs were taken from the forecast markets, and the suggestion service was
exercised in the same test runs without recording its combination. The re-run procedure is in
`docs/evidence/journey-proof/README.md`; the latest run is `2026-10-10T1716Z.json`.

**The browser test that records a slip now runs only against the isolated pair.** Until
2026-10-08 `parlay-journey.spec.ts` saved and recorded a combination for the QA account on whatever
backend it was pointed at — by default the main one on :8000 — and deleted that account's
unrecorded slips first; a recorded slip cannot be deleted through the API, so the QA account on the
live database holds five of them (test data, on that account only). The spec is now
`e2e/live-isolated/parlay-journey.spec.ts`, collected by the `live-isolated` project alone, pointed
at the :8001 backend on the e2e clone, and `e2e/support/isolated.ts` refuses any backend whose
`/health` names the live database (`docs/isolated-dev-environment.md`). The five slips stay; they
are the QA account's own.

## Selections and slips

The markets panel, the slip and the suggested combinations (docs/markets-capability-matrix.md
has the market-by-market statement) are built from stored forecasts and stored results only.
What they do not do, on purpose:

- **No odds feed.** A price on a selection is either the reader's own (typed in) or the 1X2
  decimal price GameForecastAPI carries in its payload, dated with that payload and with no
  bookmaker named. No other market's price is derived from it, and a combination with any leg
  unpriced has no combined price. Potential returns are quoted figures from a given price, never
  from a probability.
- **One selection per fixture.** Two selections on one match are correlated and cannot be priced
  or given a joint probability by multiplying them, so same-game combinations are not offered.
  A combined probability across different matches is shown as an approximation assuming
  independence, never as a calibrated prediction.
- **Suggestions are a ranking, not a model.** Highest published probability per fixture among the
  allowed markets, cut into disjoint sets; near-certainties above 95% are left out by default and
  said to be. Fewer legs than asked are returned rather than padded.
- **Not everything settles automatically.** First-half markets need a stored half-time score;
  "team to score first" needs the order of goals, which no configured source records (a 0-0
  settles "neither"); a tie decided beyond 90 minutes with no 90-minute score stored is withheld.
  Such legs read *unresolved*, with the reason, and are never guessed. There is no manual
  resolution of a leg in this release.
- **A draft made before signing in moves to the account that signs in, from this browser only.**
  If the connection fails part-way, what was not delivered waits in this browser for that same
  account and goes to the same slip on its next sign-in or reload; a slip whose creating request
  was applied but never answered is found and filled rather than created twice. Another account
  signing in on the machine never receives it. Clearing the browser's site data before the
  transfer completes loses what was not yet delivered.
- **A slip settles when its owner reads it.** The legs are brought up to date with stored results
  each time the slip list or a slip is opened; the scheduler does not settle slips on its own. Each
  leg carries `result_expected_by`, the backend's deadline for its result (kickoff plus the
  150-minute grace), so a leg that has merely started is told apart from one whose result is late.
- **"Recorded" is the reader's own statement.** The application does not place bets, hold funds,
  initiate payments or confirm that any bet exists. A recorded slip is kept as it was; changing
  it means duplicating it.
- **A void selection changes what the combination pays on, not what was recorded.** The recorded
  price stays as history; the *effective* price is the product of the remaining selections' own
  prices, and the return is quoted from that. When the reader typed one combined price and the
  remaining selections carry no prices of their own, the adjusted return is withheld rather than
  shown at the original figure.
- **No combined chance across a draw-no-bet selection.** Its probability is conditional on there
  being no draw; multiplying it with the other legs' unconditional probabilities is not the chance
  of anything, so the figure is withheld and each leg's own probability stands.
- **Corners, cards, shots, fouls, penalties and player markets are not offered**, because no
  configured source publishes probabilities for them and they are not invented from other
  statistics. The paid options researched are listed for the owner in the capability matrix;
  none was taken.
- **Coverage is what the stored forecasts cover.** On 2026-10-05 after the 06:01 UTC pass, 16 of
  the 33 stored fixtures in the next seven days carry a current forecast: 13 of 18 UEFA Nations
  League fixtures and the 3 club fixtures stored for 9 October. The 12 CONCACAF Nations League
  fixtures have none (their turn was deferred to the next day's allowance), and 5 Nations League
  fixtures were not in the provider's answer. Club fixtures from 10 October on are not stored at
  all while no match-data source answers (see above). That day the suggestions page drew three
  combinations from those 16 fixtures.

## Expert convictions

An expert's conviction is optional and is now stored as null when they do not give one. Twenty-six
prediction rows predate that change and hold exactly zero. Some of those were blank and some may be
a deliberate zero, and nothing stored can tell them apart. They were deliberately left alone:
converting them would be inventing the information the old coercion destroyed.

## What is not built at all

A wager journal, a money ledger, bookmaker integration, odds comparison, receipt scanning, a
community feed, automated messaging and any prediction model of our own. Each is gated behind an
owner decision, and several are gated behind user validation that has not happened. The money
semantics are defined and executable in `backend/app/services/money_semantics.py` and
`docs/money-semantics.md` so that the rules exist before anything is built on them, but nothing
reads or writes a ledger.
