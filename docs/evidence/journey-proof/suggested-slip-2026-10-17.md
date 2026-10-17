# A suggested combination recorded as a QA slip on the live database, 2026-10-17

The one journey still to show on live data: a combination the **suggestion service** produced,
recorded as a slip by the QA account, carried through the stored results to settlement. Every
earlier recorded slip had its legs taken from the forecast markets, not from the suggestion
service (`README.md`, step 5; `live-settlement-2026-10-10.md`).

## Authorization

The owner, in chat, on 2026-10-17: *"Yes, go ahead and record one suggested combination as a QA
slip"* — given in answer to the standing description of this demonstration as "a slip built from a
suggested combination carried to settlement on live data", and to the reviewer's note of
2026-10-11 that this one new QA record was the owner's to authorize. One slip, on the QA account,
on the live database.

## Timeline (UTC)

| When | What |
|---|---|
| 14:15:51 | `GET /api/v1/suggestions?legs=2&min_probability=0.5` on the live backend — the suggestions page's own query — returned three combinations from a pool of 61 qualifying fixtures (68 in the window, 7 without a forecast). Saved as the response below. |
| 14:16:16 | The **first** combination, as a reader sees it first, was created as a slip through `POST /api/v1/me/slips` and recorded through `POST /api/v1/me/slips/{id}/record` as the QA account, with the reference `suggested combination 1, generated 2026-10-17T14:15:51Z`. No odds were entered. |
| 14:16:28 | The read-only journey proof ran on the slip and its two fixtures, before either kicked off: `2026-10-17T1416Z.json`. |

## The slip

`a0dce8dd-8b7b-466e-b1f2-77b41a860cc9`, `recorded`, `pending`, owner `qa.expert@predictions-local.dev`
(the repository's own local test account).

| Leg | Fixture | Kick-off | Selection | Published probability | Forecast snapshot |
|---|---|---|---|---|---|
| 1 | Strasbourg v Paris Saint Germain (Ligue 1) | 2026-10-17 15:15 | `away_team_goals:under@3.5` — PSG score fewer than 3.5 | 0.95 (GameForecast, model run 2026-10-16, retrieved 2026-10-16 18:10) | `6cd2c84a` |
| 2 | Bologna v Inter (Serie A) | 2026-10-17 16:00 | `total_goals:over@0.5` — at least one goal | 0.95 (GameForecast, model run 2026-10-16, retrieved 2026-10-17 00:24) | `67b8ab45` |

Combined probability as the service states it: 0.9025, "the product of the legs' published
probabilities, assuming the matches are independent of each other; an approximation for
orientation, not a calibrated prediction". Both selections settle on the regulation-time score.

## What the proof read before kick-off (`2026-10-17T1416Z.json`)

| Stage | Strasbourg v PSG | Bologna v Inter |
|---|---|---|
| `fixture_stored` | proven_current (Live Score) | proven_current (Live Score) |
| `forecast_attached` | proven, captured before kick-off | proven, captured before kick-off |
| `suggestion` | **proven** — observed from the service before kick-off | **proven** |
| `stored_result` | pending: waiting for kickoff | pending: waiting for kickoff |
| `settlement` | pending | pending |

The slip's legs read `stored pending, dry run pending`. `match_data_access` read `partial` at that
minute: the live task had timed out twice against Live Score in the preceding half hour, so the
"a fixtures or results pass asked the primary and was answered" signal did not hold; access
itself had answered at 13:59 and answered again at 14:3x. Spend check passed; running code
measured.

## What follows

1. Both matches play this afternoon; the live task stores their regulation-time scores at full
   time, and the results and recovery passes are the backstop.
2. Once both results are stored, the proof should read `stored_result: proven_current` and
   `settlement: pending: owner read` with a final `dry_run_state` for each leg.
3. The settlement read — `GET /api/v1/me/slips` as the QA account against the live backend — is the
   last step of the demonstration the owner authorized above, and will be made once, recorded here
   with its time; then the proof once more, which should read `settlement: proven` with the stored
   states equal to the dry run, and a second read that changes nothing.

## Files

- `suggestions-response-2026-10-17T1415Z.json` beside this page: the service's answer, verbatim.
- `2026-10-17T1416Z.json`: the proof before kick-off.
