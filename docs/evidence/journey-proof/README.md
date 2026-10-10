# Journey proof: fixture → forecast → suggestion → stored result → settlement

Each JSON file here is one run of `backend/scripts/prove_journey.py`, named by the UTC minute it
started (`yyyy-mm-ddTHHMMZ.json`). The tool opens files with "create only", so a file is never
overwritten and is not edited afterwards. Every run lists the earlier files it read under
`previous`.

The tool only reads. Its database connection and its transaction are both read-only, and the
database confirms this before the first query. Redis is read through a wrapper that refuses
writes. It makes HTTP requests only as GETs to five endpoints that return stored data
(`/health`, `/api/v1/data-providers/status`, `/api/v1/suggestions`, `/api/v1/matches/{uuid}`,
`/api/v1/matches/{uuid}/markets`). It never calls `/api/v1/matches` or `/matches/live`, because
both can trigger a provider request. It never calls `/api/v1/me/*`, because reading slips there
settles them and commits. The `guards` block lists every request the run sent. A spend check reads
every provider's counters before and after the run and subtracts what the scheduler itself sent in
that time. `spend_check.verdict: passed` means the run spent nothing.

## Runs so far

| File | What it covers | Result |
|---|---|---|
| `2026-10-07T0155Z.json` | The recorded slip, plus every fixture with kickoff from 2026-10-02T00:00Z to 2026-10-07T01:55:36Z (94 fixtures) | Match-data access **blocked**. 89 of 94 fixtures have no stored result. The journey slip is pending, and both its legs are blocked at `stored_result`. Spend check passed. |
| `2026-10-07T0156Z.json` | Fixtures with kickoff in the next 7 days (4 fixtures) | Each one's suggestion stage was **proven before kickoff**, which is the only time it can be observed. Give this file as `--previous` to later runs. |
| `2026-10-07T0221Z.json` | The recorded slip, plus every fixture with kickoff from 2026-10-02T00:00Z to 2026-10-07T02:21:39Z (95 fixtures), with both files above as `--previous` | Match-data access **blocked**, read with the corrected signal (b) (see below). 89 fixtures are blocked at `stored_result`. French Guiana v Belize (kickoff 02:00) passes its first three stages, the suggestion stage through `proven_earlier` from `0156Z`, and is `pending: inside result window`. The journey slip is still pending. Spend check passed. |
| `2026-10-07T0437Z.json` | The recorded slips, plus every fixture with kickoff from 2026-10-02T00:00Z to 2026-10-07T04:37:25Z (97 fixtures), with the files above as `--previous` | Match-data access **blocked**: 90 of 97 fixtures blocked at `stored_result`, 2 waiting for kickoff, 5 results stored (all from 2 October). The suggestion stage proven before kickoff for 2 fixtures and carried from `0156Z` for 1; settlement proven for 3 scored forecasts. Spend check passed. |
| `2026-10-09T0006Z.json` | The recorded slips, plus every fixture with kickoff from 2026-10-02T00:00Z to 2026-10-09T00:06:37Z, run straight after the not-answers repair, with every earlier file as `--previous` | Match-data access still **blocked**. The repair's marks now decide the attempt-count flag: one in-window fixture flagged (Congo v Uganda, kept `unverified`) instead of 58 by clock. Spend check passed; running code measured. |
| `2026-10-10T1716Z.json` | The recorded slips, plus every fixture with kickoff from 2026-10-02T00:00Z to 2026-10-10T17:16:25Z, with every earlier file as `--previous` | Match-data access **returned** (Live Score answering since 2026-10-09 01:15 UTC; 82 international results stored on the 9th between 02:06 and 03:37). Stored results: 97 `proven_current`, 6 `proven`, 10 in the recovery queue, 5 inside their result window. All five recorded slips read `pending: owner read` with a final dry run — one `won`, four `lost`. Spend check passed; running code measured. |

The first two files are `schema_version: journey-proof.v1`. Under v1, signal (b) accepted any
success of the fixtures or results task. From `journey-proof.v2` on, it accepts only a pass that
asked the primary and got an answer (see (b) below). The v1 files read the same either way: both
tasks had failed 15 and 19 times in a row, so (b) did not hold under either rule.

## How to read a run

- **`match_data_access`** is `returned`, `partial` or `blocked`. It is `returned` only when three
  signals all hold after `access_since` (by default 2026-10-02T14:53:28Z, Live Score's last
  success):
  - (a) the primary provider succeeded, its last transmission got an HTTP 200 answer, and it is
    not cooling down;
  - (b) the fixtures task or the results task succeeded on its last pass, and that pass sent the
    primary at least one request (`last_requests_sent`). For the fixtures task, a provider must
    also have answered at least one day's fixture list during that pass, not a cache. A results
    pass succeeds only when it records no error, so a successful one that asked the primary got
    its answer from the primary. A fixtures pass can succeed on a fallback's answer after the
    primary refused, which is why `returned` also needs (a);
  - (c) a fixture sync or a result row was stored.

  `missing` names the signals that do not hold. `signals[].evidence` shows what each task's last
  pass sent, per provider, and `why_not` gives the reason a task does not count. `providers` quotes
  each provider's last error.
  `app_reports` records the state the backend itself shows readers (the `match_data` block of
  `/status`), so a banner that disagrees with the evidence is visible. It never decides the
  verdict. The first two files above were written before the tool recorded it. In
  `2026-10-07T0221Z.json` it is `null`, because the running backend (201442e) does not publish the
  block yet.
  `ignored_signals` lists signals that look like recovery but are not:
  - the recovery task's success, which it records even on passes that stored nothing;
  - a success of the fixtures or results task that asked nobody. The scheduler records a success
    for a results pass with nothing due, which sends no request. On 2026-10-09 that is every
    results pass until about 21:00 UTC, because that day's only stored fixtures kick off at
    18:30–19:00. It also records a success for a fixtures pass served from the 24-hour stale
    copy. Such a success is listed here with its reason while the task reads as succeeding;
  - a fallback's HTTP 200: API-Football answers 200 with a plan error in the body, and its
    `last_success_at` moved to 01:35 today with nothing stored;
  - `matches.updated_at`, which recovery bookkeeping updates.
- **`fixtures[].stages`** holds five stages. Each has a `verdict`, an `at` time and `evidence`.

  | Stage | Passing verdicts | Other verdicts |
  |---|---|---|
  | `fixture_stored` | `proven`; `proven_current` when the row was created or synced after `access_since` | `not_found` |
  | `forecast_attached` | `proven`: a snapshot taken before kickoff | `failed` (forecast only after kickoff), `pending`, `blocked: forecast provider`, `absent` (nothing stored before kickoff) |
  | `suggestion` | `proven` (in a `default` or single-fixture `probe` call, with `min_probability=0` and `max_probability=1`); `proven_earlier` (an earlier file saw it before kickoff); `selection_evidence` (a slip leg was read from a prematch snapshot; shows markets → slip, not the suggestion service) | `excluded:<reason>`, `not_observed` |
  | `stored_result` | `proven`; `proven_current` when the result was stored after `access_since` | `pending: waiting for kickoff`, `pending: inside result window`, `blocked: no match-data source answering`, `blocked: match-data access partial`, `pending: recovery queue`, `failed` (asked after access returned, retry schedule exhausted), `unresolved: …` |
  | `settlement` | `proven`: a stored final leg agrees with a dry run of the settlement rule, or the forecast was scored | `pending: owner read`, `pending`, `pending: forecast scoring`, `unresolved:<basis>`, `failed` (stored final ≠ rule), `not_applicable` |

- **`chain`** gives the first stage that does not pass: `verdict` and `stage`. `later` lists any
  further stages that also fail. `passed_with` names any stage a `selection_evidence` stood in for.
  `current: true` means the fixture row itself dates from after `access_since`.
- **The suggestion stage** can only be observed before kickoff. Suggestions consider only
  scheduled fixtures that have not kicked off. So in a window that has already been played,
  `suggestion: not_observed` is expected unless an earlier run is passed as `--previous`. Read
  `later` to see what else holds that fixture back.
- **`flags`** can hold three flags:
  - `attempt_counts_unreliable`: until 201442e, results calls that a fallback could not make were
    recorded as answered attempts (see docs/known-limitations.md). A row that
    `scripts/repair_not_answers.py` has corrected carries its own mark, and the mark decides:
    `exact` is trusted, while `upper_bound` or `unverified` is flagged. A row with no mark is flagged
    when it counted any attempt after `access_since`.
  - `status_stale_live`: the row still reads LIVE long after its result was due.
  - `relisted`.
- **`slips[]`** shows each slip as stored, next to `dry_run_state`, the state its legs would reach
  under the settlement rule now. The owner appears only as `owner_is_qa`, and a slip's name is kept
  only for the QA account. No email, user id, note, recorded reference, stake, token, key or
  secret is written. Every configured credential value is removed from every string.
- **`backend`** records the process listening on the API port: when it started, and whether it
  runs the repository's HEAD. That last answer is inferred from when HEAD arrived and which files
  changed after the process started; no endpoint reports its commit.

What `2026-10-07T0155Z.json` shows:
- Every result stored since the window began is from 2 October. There are 5, three of them scored
  forecasts.
- Fixtures with no stored result, by day: 15 of 20 on 2 October, all 21 on the 3rd, 22 on the 4th,
  13 on the 5th and 18 on the 6th. By competition: UEFA Nations League 44, CONCACAF Nations League
  28, friendlies 17.
- 47 fixtures had a forecast before kickoff. Three got a forecast only two minutes after kickoff:
  Guatemala v Suriname, Grenada v Bonaire and Bermuda v Barbados, kickoff 2026-10-06 00:00. For
  the other 44 no forecast was stored at all.
- 58 fixtures carry attempt counts that cannot be trusted. Congo v Uganda and Kazakhstan v Moldova
  still read LIVE five days on.

## Settlement, proven on the isolated copy

`settlement-isolated-2026-10-10/` holds the one stage no run above can reach without a write: the
five recorded slips settled by the application's own read (`GET /api/v1/me/slips`) against a copy
of the live database taken at 17:14 UTC on 2026-10-10, then read a second time. The first read
settled them exactly as the dry run above predicts — `18724af2` won, the four of 7 October lost —
and the second read changed no row, no timestamp and no table. The same read against the live
backend is step 5 below, and still waits for the owner.

## Re-running once match-data access returns

From `backend/`:

```sh
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PGOPTIONS='-c default_transaction_read_only=on' ./venv311/bin/python scripts/prove_journey.py \
    --recorded-slips --window 2026-10-02T00:00:00Z "$NOW" \
    --previous ../docs/evidence/journey-proof/*.json --out ../docs/evidence/journey-proof/
```

The exit code is 0, or 2 when the spend check fails.

1. **Access.** Run the command above. `match_data_access` should read `returned`. If it reads
   `partial`, `missing` names what is still absent. None of these changes the verdict on its own:
   a fallback's 200, a recovery-task success, or a fixtures or results success whose pass never
   asked the primary (for example, a quiet day with no result due).
2. **Backlog.** Re-run every few hours. The fixtures from 2 to 6 October should move from
   `blocked` to `pending: recovery queue`, and then to `proven_current` once their results are
   stored. Results look back only one day. The recovery task reopens at most two competition-days
   per pass, oldest first, with 4 requests per pass and 40 per day, and the queue goes back to 24
   September. So the journey slip's fixtures (5 October) may take several passes. This is an
   estimate, not a measurement.
3. **A current fixture, before kickoff.** Once new fixtures are stored, run
   `--window "$NOW" <now + 7 days> --out ../docs/evidence/journey-proof/`. New fixtures read
   `fixture_stored: proven_current`, and the suggestion stage can only be captured in this run.
4. **The same fixture, after its result.** Run `--match <id> --previous <the file from step 3>`.
   The chain should read `proven` with `current: true`, and settlement should be `proven` once its
   forecast is scored.
5. **Settling the journey slip needs one write, and the owner's go-ahead.** Run
   `--slip 18724af2-1f5d-444e-98d4-d1f42fef9f5e`. Once both legs have results, stage 5 should read
   `pending: owner read` with a final `dry_run_state`. The stored legs do not change until the
   slip's owner reads the slip, because the scheduler's settle task scores forecasts and never
   touches slips. That read happens through GET `/api/v1/me/slips`, which settles the slip and
   commits to the live database. It is the only write in this procedure, so do it only after the
   owner explicitly agrees: one sign-in as the QA account in the app, or one authenticated GET
   `/api/v1/me/slips`. Then re-run step 5's command. The slip and its legs should read `proven`,
   with a stored `settled_at` that matches the dry run.
6. Commit each new file as it was written. Never edit one.

`--access-since` should stay at its default, the moment the outage began, so that `returned` and
`proven_current` keep meaning "after the outage". To verify a different provider, name it with
`--primary`.
