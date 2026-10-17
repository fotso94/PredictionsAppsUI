# A suggested combination recorded as a QA slip on the live database, and settled — 2026-10-17

The one journey still to show on live data: a combination the **suggestion service** produced,
recorded as a slip by the QA account, carried through the stored regulation-time results to
settlement. Every earlier recorded slip had its legs taken from the forecast markets, not from
the suggestion service (`README.md`, step 5; `live-settlement-2026-10-10.md`).

**This is an API workflow demonstration.** Every step was made through the application's HTTP
API and read back from its database. No browser interaction was demonstrated: no page was opened,
no control was clicked, and what a reader would see on the suggestions page, in the slip dock or
on the slip history is not shown here.

## Authorization

The owner, in chat, on 2026-10-17: *"Yes, go ahead and record one suggested combination as a QA
slip"*, and later the same day: *"Continue the existing authorized demonstration for slip a0dce8dd
only. Once both regulation-time results are stored, capture them, settle the slip, verify each
outcome, and repeat the read to prove settlement is unchanged. Publish the final evidence and
report any missing result honestly. Do not create another slip or invent results."* One slip, on
the QA account, on the live database; one settlement read.

## Timeline (UTC)

| When | What |
|---|---|
| 14:15:51 | `GET /api/v1/suggestions?legs=2&min_probability=0.5` on the live backend — the suggestions page's own query — returned three combinations from a pool of 61 qualifying fixtures (68 in the window, 7 without a forecast). Saved as `suggestions-response-2026-10-17T1415Z.json`. |
| 14:16:16 | The **first** combination was created as a slip through `POST /api/v1/me/slips` and recorded through `POST /api/v1/me/slips/{id}/record` as the QA account, with the reference `suggested combination 1, generated 2026-10-17T14:15:51Z`. No odds were entered. |
| 14:16:28 | The read-only journey proof ran on the slip and its two fixtures before either kicked off: `2026-10-17T1416Z.json`. Suggestion stage **proven** from the service for both legs. |
| 15:15 / 16:00 | Kick-offs. |
| 17:11:13 | Strasbourg v Paris Saint Germain stored **1-3** (half-time 1-0, full-time 1-3, no extra time) by the live task at full time, provider Live Score, marker FT. |
| 17:56:17 | Bologna v Inter stored **1-3** (half-time 1-1, full-time 1-3, no extra time), the same way. |
| 18:07:33 | The proof before the read: `2026-10-17T1807Z.json` — `stored_result: proven_current` for both, `settlement: pending: owner read`, dry run **won** on each leg and on the slip. |
| 18:08:14 | **The settlement read**: the QA account signed in through `POST /api/v1/auth/login` and made one `GET /api/v1/me/slips`. The slip went `pending` → `won`, `settled_at` 18:08:14.477635, both legs `won`. |
| 18:08:1x | A second `GET /api/v1/me/slips` and a `GET /api/v1/me/slips/{id}`: no row and no timestamp changed. |
| 18:08:26 | The proof after the read: `2026-10-17T1808Z.json` — **every stage proven** for both fixtures; the slip `recorded/won`, stored state equal to the dry run on each leg. |

## The slip

`a0dce8dd-8b7b-466e-b1f2-77b41a860cc9`, `recorded`, now `won`, owner `qa.expert@predictions-local.dev`
(the repository's own local test account).

| Leg | Fixture | Selection | Published probability | Regulation-time score | Rule applied | Stored state |
|---|---|---|---|---|---|---|
| 1 | Strasbourg v Paris Saint Germain (Ligue 1, 15:15) | `away_team_goals:under@3.5` — PSG score fewer than 3.5 | 0.95 (GameForecast snapshot `6cd2c84a`, model run 2026-10-16) | **1-3**: PSG scored 3 | away team's regulation-time goals against the 3.5 line: 3 < 3.5 | **won** |
| 2 | Bologna v Inter (Serie A, 16:00) | `total_goals:over@0.5` — at least one goal | 0.95 (GameForecast snapshot `67b8ab45`, model run 2026-10-16) | **1-3**: 4 goals | regulation-time goals against the 0.5 line: 4 > 0.5 | **won** |

Slip state: every leg won → **won**. Combined probability as the service stated it before kick-off:
0.9025, "an approximation for orientation, not a calibrated prediction".

## Verification of the read (`suggested-slip-2026-10-17/summary.json`)

- Each leg's stored settlement carries the actual score (`1-3`, `1-3`) and its state agrees with
  the outcome recomputed from the stored scores and the rule: `agree: true` on both.
- The read touched only this slip: `other_slips_changed_by_the_read: []` — the five slips settled
  on 10 October are byte-identical before and after.
- The second read changed nothing: the `md5` over every slip and leg row is unchanged
  (`second_read_changed_rows: false`), no `updated_at` moved, and the single-slip read equals the
  slip's entry in the list.
- The `before.json`, `after-first-read.json` and `after-second-read.json` snapshots, the three API
  responses and the script are in the folder beside this page; no token or password is in them.

## Two things to read correctly

- **The proof's access signal read `partial`** at 18:07 and 18:08 ("missing:
  scheduler_fixtures_or_results_succeeding"). That signal looks only at the fixtures and results
  passes, and at those minutes neither had anything to ask — the results pass served its window
  from the database. The two results themselves were stored by the **live** task at full time
  (provider Live Score, marker FT, `beyond_regulation: false`), which the signal does not count.
  Nothing was missing from the data; the signal's definition is narrower than the path that
  delivered it, and that is noted here rather than hidden.
- **Nothing was invented.** Both scores are Live Score's, stored by the application before any
  read; the dry run in the 18:07 proof predicted both outcomes from those stored rows, and the
  stored settlement equals it.

## Files

- `suggestions-response-2026-10-17T1415Z.json` — the service's answer, verbatim.
- `2026-10-17T1416Z.json`, `2026-10-17T1807Z.json`, `2026-10-17T1808Z.json` — the proof before
  kick-off, before the read, after the read.
- `suggested-slip-2026-10-17/` — the read's snapshots, responses, summary and script.
