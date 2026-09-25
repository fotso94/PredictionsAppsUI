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

## 2. The history archive holds nothing dated 2026-09-18 or later — is that expected?

This is the one we would most like explained, and we have been careful not to assume the answer.

**The archive clearly works, for club and national-team competitions alike.** These all returned
finished fixtures with full scores:

| Query | Rows |
| --- | --- |
| `matches/history.json?competition_id=3&from=2026-09-16&to=2026-09-16` (La Liga) | 3 |
| `matches/history.json?competition_id=362&from=2026-06-10&to=2026-07-20` (FIFA World Cup) | 30 |
| `matches/history.json?competition_id=227&from=2026-01-01&to=2026-02-15` (Africa Cup of Nations) | 16 |
| `matches/history.json?competition_id=271&from=2024-06-15&to=2024-07-20` (Copa America) | 30 |
| `matches/history.json?competition_id=490&from=2023-07-15&to=2023-08-25` (Women's World Cup) | 30 |

**But nothing dated 2026-09-18 or later has ever come back, for any competition.** Asked on two
different days, several days apart:

| Asked on | Query | Rows |
| --- | --- | --- |
| 2026-09-22 | `competition_id=3&from=2026-09-15&to=2026-09-22` (La Liga) | 8 — every one dated 09-16 or 09-17 |
| 2026-09-22 | `competition_id=3&from=2026-09-18&to=2026-09-20` | 0 |
| 2026-09-22 | `from=2026-09-19&to=2026-09-19` (no competition filter) | 0 |
| 2026-09-25 | `competition_id=3&from=2026-09-16&to=2026-09-24` (La Liga) | 5 — every one dated 09-16 or 09-17 |
| 2026-09-25 | `competition_id=350&from=2026-09-24&to=2026-09-24` (UEFA Nations League) | 0 |
| 2026-09-25 | `competition_id=228&from=2026-09-24&to=2026-09-24` (AFCON Qualifications) | 0 |
| 2026-09-25 | `competition_id=371&from=2026-09-24&to=2026-09-24` (National Teams Friendlies) | 0 |
| 2026-09-25 | `competition_id=412&from=2026-09-24&to=2026-09-24` (Arabian Gulf Cup) | 0 |

Both La Liga answers are below the 30-row page size, so they are complete: the later days are
absent, not on a later page. A single-day query works (09-16 answers), so it is not the `from == to`
shape. It is not our competition ids, and it is not a club/national difference.

**What we have ruled out, and what we have not.** We wondered whether the archive simply lags by a
few days. The boundary sat between 09-17 and 09-18 when we asked on the 22nd, and it sat in exactly
the same place when we asked on the 25th — so it is not a lag of about five days. We have not ruled
out a longer lag, a restriction on our trial, or something upstream.

**Why it matters to us.** Our database holds finished fixtures from those dates whose scores reached
us through `matches/live.json` while they were being played. When a fixture is missed while live —
because our own connection dropped, say — the archive is the only way we know to recover it
afterwards. Several are waiting on it now, including UEFA Nations League, Andorra v Malta on
2026-09-24.

**Questions:**

1. Is there a known gap in the history archive from 2026-09-18 onward, or a delay before recent
   matches appear in it? If there is a delay, roughly how long?
2. Does our trial plan limit how recent the history data can be?
3. Is there anything about how we are querying `matches/history.json` that we have not spotted?

We are not asking for a backfill; we would mainly like to know what to expect, so we retry sensibly
rather than either giving up too early or asking every half hour for data that will not come.

---

## 3. How long does a finished match stay in `matches/live.json`?

Your documentation says finished matches remain in the live feed for a while after full time, but
we found the durations described in different places hard to reconcile, and we would rather ask
than guess.

What we observed on one evening, 2026-09-24:

- A poll at **21:06 UTC** carried seven UEFA Nations League fixtures that had kicked off at
  18:45–18:49, all shown as finished. It did not carry Andorra v Malta, which had kicked off at
  16:01.
- A poll at **23:08 UTC** returned three matches in total: two finished, one in play at minute 79.

Two observations on one evening tell us what the feed held at those moments, not your retention
rule, so we have not built anything on them.

**Question:** how long after full time does a finished match remain in `matches/live.json`, and does
it differ by competition? Knowing this would tell us how long a missed match stays recoverable from
the live feed before we have to rely on the archive.

---

## Account and volume, for context

Single trial account, well inside its daily allowance — our own ceiling is 1,200 requests a day and
our typical use is under 150. We are not asking for a limit increase.
