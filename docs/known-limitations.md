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

## The archive holds nothing dated 2026-09-18 or later — cause unknown

Measured on 2026-09-22 and again on 2026-09-25. Every observation, dated, is in
`docs/evidence/livescore-archive-observations.json`.

**The archive works, for club and national-team competitions alike.** `matches/history.json`
returned finished fixtures with full scores for La Liga on 2026-09-16 and -17, and for past
national-team tournaments: the FIFA World Cup (June–July 2026, 30 rows), the Africa Cup of Nations
(January–February 2026, 16), Copa America (2024, 30) and the Women's World Cup (2023, 30). A
single-day query works, so it is not the `from == to` shape, and it is not our competition ids.

**What it has never returned is anything dated 2026-09-18 or later, for any competition:**

| Asked on | Query | Rows |
| --- | --- | --- |
| 2026-09-22 | La Liga, 09-15 to 09-22 | 8 — all dated 09-16 or 09-17 |
| 2026-09-22 | La Liga, 09-18 to 09-20 | 0 |
| 2026-09-22 | no competition filter, 09-19 | 0 |
| 2026-09-25 | La Liga, 09-16 to 09-24 | 5 — all dated 09-16 or 09-17 |
| 2026-09-25 | UEFA Nations League, AFCON Qualifications, National Teams Friendlies, Arabian Gulf Cup — each 09-24 | 0 each |

Both La Liga answers are below the page size, so they are complete.

**What is known and what is not.** The boundary sat between 09-17 and 09-18 on the 22nd and in
exactly the same place on the 25th, so a lag of about five days is REFUTED. A longer lag, a
restriction on our trial and an upstream stall are all still open. **THIS IS UNRESOLVED**, and the
question is with provider support in `docs/support/livescore-api-questions.md`. Until it is
answered, a fixture dated in that range has not been recoverable from the archive *so far* — which
is a statement about what we have been told, not about what will ever exist.

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
and has answered for nothing dated 2026-09-18 or later — see the section above.

So what we can say about a missed result depends on its date, not on whether it is a club or a
national team:

| Missed result | Recovered so far? | What we know |
| --- | --- | --- |
| Still in the live feed when the next poll runs | **Yes**, observed | the ordinary live task collects it |
| Dated on a day the archive holds | **Yes**, observed by hand for 2026-09-16 | the results task can collect it |
| Dated 2026-09-18 or later | **Not yet** | the archive has returned no rows for these days so far; why, and whether it will, is unknown |

**Nothing here says a result cannot exist.** The application keeps asking under a retry *budget*,
and stopping is a decision about what we are willing to spend, not a finding about the provider. A
reader of such a fixture is told what happened — no result has arrived, and when we last asked — and
never shown a score nobody reported. As of 2026-09-25 eight national-team fixtures from 2026-09-24
are in this state, including UEFA Nations League, Andorra v Malta.

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
