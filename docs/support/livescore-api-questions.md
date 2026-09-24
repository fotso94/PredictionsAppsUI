# Questions for Live Score API support — PREPARED, NOT SENT

Status: **draft, awaiting the owner's decision to send.** Nothing here has been transmitted.

No credential appears in this document. The `key` and `secret` are request parameters; every query
below is written with them omitted, and the responses quoted carry none. Before sending, check that
nothing has been pasted in since.

Two unrelated questions, both measured against our own account on 2026-09-16 to 2026-09-23.

---

## 1. Is forward fixture coverage of national-team competitions expected on our current trial?

We are adding international coverage and are trying to tell "this competition has nothing scheduled"
apart from "this competition is not served to us". The two look identical from here: an empty list
and HTTP 200, with no error.

**These return fixtures, so access is clearly not the issue in general:**

| Query | Result |
| --- | --- |
| `fixtures/list.json?competition_id=350` (UEFA Nations League) | 30 fixtures, next 2026-09-24 |
| `fixtures/list.json?competition_id=371` (National Teams Friendlies) | 30 fixtures, next 2026-09-23 |
| `fixtures/list.json?competition_id=363` (World Cup UEFA Qualifiers) | 1 fixture, 2026-11-02 |

**These return an empty list, with no error:**

`fixtures/list.json?competition_id=` 362 (FIFA World Cup), 359 / 358 / 360 / 361 / 364 (the CAF,
AFC, CONCACAF, CONMEBOL and OFC World Cup qualifiers), 227 (Africa Cup of Nations), 271 (Copa
America), 490 (Women's World Cup).

We believe several of those are simply dormant right now, and we have confirmed the archive answers
for four of them — `matches/history.json?competition_id=362&from=2026-06-10&to=2026-07-20` returns 30
rows, `227` returns 16 for January–February 2026, `271` returns 30 for June–July 2024, and `490`
returns 30 for July–August 2023.

**The question:** when one of those competitions next has scheduled fixtures, will
`fixtures/list.json` return them on our plan, or is forward fixture data for national-team
competitions limited in a way we should design around? We would rather know now than discover it
during a tournament.

**A smaller related one:** `competitions/list.json` reports `national_teams_only` as `"0"` for
competition 271 (Copa America), 371 (National Teams Friendlies) and 490 (Women's World Cup). Every
other national-team competition we found reports `"1"`. Is that intentional, or are those three
mis-flagged? We have worked around it with an explicit list, but a fix upstream would be better for
everyone.

---

## 2. `matches/history.json` returns nothing for 2026-09-18 to 2026-09-20

This is the one we would most like explained.

**Working, same endpoint, same competition, same parameter shape:**

| Query | Result |
| --- | --- |
| `matches/history.json?competition_id=3&from=2026-09-16&to=2026-09-16` | **3 rows**, all `FINISHED` with full-time scores |
| `matches/history.json?competition_id=3&from=2026-09-15&to=2026-09-22` | **8 rows**, every one dated 09-16 or 09-17 |

Eight rows is below the 30-row page size, so that second answer is complete — there is no later page
holding the missing days.

**Returning nothing:**

| Query | Result |
| --- | --- |
| `matches/history.json?competition_id=3&from=2026-09-19&to=2026-09-19` | 0 rows |
| `matches/history.json?competition_id=3&from=2026-09-18&to=2026-09-20` | 0 rows |
| `matches/history.json?competition_id=2&from=2026-09-19&to=2026-09-19` | 0 rows |
| `matches/history.json?from=2026-09-19&to=2026-09-19` (no competition filter) | 0 rows |
| `matches/history.json?from=2026-09-15&to=2026-09-22` (no competition filter) | 30 rows, across many competitions |

So it is not the competition id, not the date format, and not a `from == to` range — a single-day
query works for 2026-09-16.

**Why it matters to us:** our own database holds 48 finished fixtures dated 2026-09-18 to 2026-09-20
in these same competitions, with scores that reached us through `matches/live.json` at the time. The
archive that ought to carry the same fixtures does not return them. That leaves us unable to recover
a result for any fixture that was missed while it was live on those dates.

**The question:** is there a known gap in the history archive over 2026-09-18 to 2026-09-20, or is
there something about how we are querying it that we have not spotted? We are not asking for a
backfill — we would mainly like to know whether to expect this to recur, because our recovery path
depends on that endpoint.

---

## Account and volume, for context

Single trial account, well inside its daily allowance — our own ceiling is 1,200 requests a day and
our typical use is under 150. We are not asking for a limit increase.
