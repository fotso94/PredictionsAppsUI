# Not-answers repair: rehearsal on an isolated copy

Rehearsed 2026-10-07 02:53 UTC by `backend/scripts/repair_not_answers.py` (sha256 prefix
`609a153ad52b93de`, recorded in every row of `plan.jsonl`). **The live database was not written to.**
It was read only with `pg_dump` and read-only `psql` sessions. The repair ran against
`soccer_predictions_rehearsal_notanswers`, a copy restored from a dump taken one second earlier.
That copy is **kept** so the owner can inspect it.

This is the sixth run. Runs 1–3 (01:49–01:56 UTC) used an earlier version of the script. A review
found two flaws in that version:

- its `--apply` guard trusted an empty `pg_stat_activity`, which says nothing while the backend runs;
- it took the cut from Redis, which moves as soon as Live Score answers again.

Both are fixed (see [The guards, exercised](#the-guards-exercised)). Run 4 (02:33) used the fixed
version before two docstring edits. Run 5 (02:34, sha256 prefix `0cca42d8ec934a4d`) used it before
its last change: it gave the closed second listing `9dbb3854` (Senegal v Mozambique, POSTPONED,
`relisted_as` set) a `next_ask_after` in its planned state, although the stored row has none.
Run 6 uses the final version, in which a closed relisting advertises no next ask, as
`MatchRegistry._retire_relisted` already does. That field, and its entry in the row's record of
replaced values, is the only difference in the corrected fields. Every other corrected field is
identical, row for row, to run 5, and so to run 3. The deferral bookkeeping that a recovery pass
moved between runs 5 and 6 (below) shows in `before` and is carried into `after` unchanged.

What is being repaired is described in `docs/known-limitations.md`, section "A provider that could not
be asked was recorded as answering". In short: until 201442e, API-Football and TheSportsDB were
recorded as answering for national-team competitions they hold no id for, without sending any
request. Each such not-answer did three things:

- overwrote the archive observation with `empty`, 0 rows, its own stamp and its own provider name;
- added one to `times_asked`;
- counted one attempt on every pending fixture of that competition-day, which also moved the retry clock.

## Files

| File | What it is |
| --- | --- |
| `plan.jsonl` | The applied plan, one line per row: `before`, `after`, class or group, quality, evidence, audit. The first line holds the options, the cut and where it came from, and the synced-row check. |
| `plan-without-reconstruction.jsonl` | The same plan without `--reconstruct-from-synced-rows`, for the owner's first decision below. Report-only; not applied. |
| `evidence-snapshot.json` | Evidence outside the repository that decays: Live Score's last success, the synced rows used for reconstruction, the Redis budget counters for 2026-10-05 and 2026-10-06, and what the `--apply` guard saw on the running backend. No credential values. |

## Live counts, re-measured immediately before the rehearsal

Read-only, at **2026-10-07 02:53:44 UTC** (the SQL is in the appendix). These are the same counts the
survey measured at 01:08–01:18 UTC, run 3 at 01:56 and run 5 at 02:34.

- **Observations.** 34 national-team archive observations. **13 are false by rule**, all naming
  API-Football (0 TheSportsDB). None names Live Score after its last success.
- **Fixtures.** 147 national-team fixtures carry recovery bookkeeping.
  - **66 are affected** (`last_attempt_at` or `archive.asked_at` after the cut). For 57 of them,
    even `first_attempt_at` is after the cut.
  - None was given up on.
- **Last stamps.** The latest false stamp is 2026-10-06 00:25:19.84 (observation) and 00:25:19.89
  (fixture). The latest outcome written, 02:35:11, is a genuine `deferred` from the current code.
- **What moved since run 5 (02:34:48).** Only the current code's deferral bookkeeping: `deferrals`,
  `last_deferred_at`, `last_outcome_at` and `next_ask_after` on 65 of the 66 fixtures (all but the
  closed relisting `9dbb3854`), written by the 02:35:06–02:35:11 recovery pass. No observation and
  no field the repair corrects moved.

The cut is Live Score's last success, `2026-10-02T14:53:28.028159Z`. It is passed with
`--livescore-last-success`, and the script checked that Redis `provider:status:livescore` records the
same instant. The script allows a 1 s margin, so anything stamped after `2026-10-02T14:53:29.028159Z`
counts as after the cut.

## What was run

The password is shown as `***`. The working directory is `backend/`.

```sh
# 0. live counts, read-only
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' soccer_predictions_postgres \
  psql -U postgres -d soccer_predictions -At < measure.sql

# 1. fresh plain backup (pg_dump only reads; not docker/scripts/backup-database.sh, which uses --clean --create)
docker exec soccer_predictions_postgres pg_dump -U postgres -d soccer_predictions \
  | gzip > ../backups/soccer_predictions-before-not-answer-repair-20261007T025344Z.sql.gz
#    + ../backups/not-answers-before-repair-20261007T025344Z.jsonl  (the 13 observations and 66 recovery objects, read-only psql)

# 2. the isolated copy (dropped first only because a database of exactly this name existed from run 5)
docker exec soccer_predictions_postgres dropdb -U postgres soccer_predictions_rehearsal_notanswers
docker exec soccer_predictions_postgres createdb -U postgres soccer_predictions_rehearsal_notanswers
gunzip -c ../backups/soccer_predictions-before-not-answer-repair-20261007T025344Z.sql.gz \
  | docker exec -i soccer_predictions_postgres psql -U postgres -d soccer_predictions_rehearsal_notanswers -v ON_ERROR_STOP=1 -q

# 3. report only (read-only transaction), then the variants the owner chooses between
URL=postgresql://postgres:***@localhost:5432/soccer_predictions_rehearsal_notanswers
PRIOR=../backups/soccer_predictions-before-relisting-repair-20261005T034608Z.sql.gz
PIN=2026-10-02T14:53:28.028159Z
S="./venv311/bin/python scripts/repair_not_answers.py --database-url $URL --prior-dump $PRIOR"
$S --livescore-last-success $PIN --reconstruct-from-synced-rows --report report-only.jsonl
$S --livescore-last-success $PIN --report no-reconstruction.jsonl
$S --livescore-last-success $PIN --reconstruct-from-synced-rows --no-subtract-proven-pre-window --report no-subtract.jsonl
$S --livescore-last-success $PIN --reconstruct-from-synced-rows --skip-closed-relistings --report skip-relisting.jsonl
$S --reconstruct-from-synced-rows --report unpinned-report.jsonl                        # cut from Redis, labelled "not pinned"

# 4. the cut guards
$S --reconstruct-from-synced-rows --apply                                               # no pinned cut
$S --livescore-last-success 2026-10-08T10:00:00Z --reconstruct-from-synced-rows         # a moved cut
#    + plan_repair() with the moved cut, and with a row synced by Live Score after the cut (rolled back)

# 5. the last look before COMMIT: commit_plan() while another session waits on a locked target row (rolled back)
# 6. the connected-client guard: --apply while another psql session holds the copy open
$S --livescore-last-success $PIN --reconstruct-from-synced-rows --apply

# 7. apply, then 8. apply again
$S --livescore-last-success $PIN --reconstruct-from-synced-rows --apply --report apply-1.jsonl   # = plan.jsonl
$S --livescore-last-success $PIN --reconstruct-from-synced-rows --apply --report apply-2.jsonl

# 9. every target fixture written back as a stale pass would, then planned again (in one transaction, rolled back)
# 10. what serialize_recovery serves for the 66 rows
```

| Step (UTC) | Result | Time |
| --- | --- | --- |
| 02:53:44 live counts | read-only `psql` exit 0; 13 / 66 (above) | — |
| 02:53:44 backup | `pg_dump \| gzip` exit 0; 796,752 bytes; 75 COPY blocks; no CREATE/DROP DATABASE. The before-repair `.jsonl` (read-only `psql` exit 0): 13 observations, 66 fixtures | 0.17 s |
| 02:53:44 restore | `dropdb` exit 0, `createdb` exit 0, restore exit 0 with `ON_ERROR_STOP`; the copy measures the same 13 / 66 | 0.75 s |
| 02:53:45 report only | exit 0. The synced-row method agrees on **18 of 18** genuine answers. Classes 1/2/3: **8/2/3**. Groups A/B/C: **57/3/6**. 32 asks and 167 attempts to remove. | 0.51 s |
| report variants | exit 0 each. Without reconstruction: same counts. Without subtracting the proven ask: 29 asks, 161 attempts. Skipping the closed relisting: group C 5, 165 attempts. Unpinned (cut from Redis): same plan, labelled "not pinned: --apply needs it given". | 0.50–0.52 s each |
| 02:53:48 cut guards | exit 2 both times: `--apply` without `--livescore-last-success`; a report given 2026-10-08 10:00 (Redis says 10-02 14:53:28) | 0.36 s each |
| 02:53:49 last look | **ABORTED, rolled back**: "just before COMMIT: 1 other session(s) waiting on rows this repair locked"; every leagues/matches row unchanged | — |
| 02:53:50 client guard | exit 2: "refusing to write while 1 other client is connected" | 0.35 s |
| 02:53:58 `--apply` | exit 0. **Written: 13 observations, 66 fixtures.** | 0.58 s |
| 02:53:59 `--apply` again | exit 0. **Written: 0 observations, 0 fixtures**; 66 rows skipped as already corrected. | 0.53 s |
| 02:53:59 stale write-back | 66 fixtures planned again (A/B/C 57/3/6), 0 observations, 0 skipped; rolled back, copy unchanged | — |

The report-only plan and the applied plan are identical once their `now` is normalised. The
refusal of `soccer_predictions` itself (without `--owner-approved`, or without
`--i-stopped-the-backend`, or while the backend looks alive) is covered by the unit tests and by
the read-only check of the running backend below. It was not exercised with `--apply` against the
live database.

## The guards, exercised

### The backend's database: `pg_stat_activity` is empty while the scheduler runs

In development the backend's engine uses `NullPool` (`app/db/session.py`). It opens a connection
only while a pass runs and closes it afterwards, so between passes `pg_stat_activity` lists no
client at all. The earlier guard ("refuse while other clients are connected") therefore let an
apply go ahead with the backend up, and a pass that read rows before the commit would have
written the false JSONB back after it.

What the script now does with `--apply`:

- It refuses `soccer_predictions`, and the database the application is configured with, unless
  `--i-stopped-the-backend` is given, whatever `pg_stat_activity` shows.
- It checks that claim, and refuses even with the flag while any of these holds:
  - something accepts connections on the backend's address (127.0.0.1:8000, or `--backend-address`).
    The scheduler runs inside the backend process. Only a TCP connection is opened and closed; no
    request is sent.
  - a sync pass holds a `sync:lock:*` key;
  - the scheduler recorded a task in the last two ticks (2 minutes);
  - Redis cannot be read.
- Just before COMMIT, with every target row locked and written, it looks again. It rolls back if
  any of the above changed, or if another session is waiting on a row it locked: that session would
  write its own copy the moment the repair commits.

Seen read-only on the running backend at 02:56:04 UTC (`evidence-snapshot.json`, `backend_guard`):

- `pg_stat_activity` listed **0** other clients on `soccer_predictions`.
- At the same moment, 127.0.0.1:8000 accepted connections (a backend restarted at 02:51:55 by
  another session), and its scheduler had written `settle` 8 s earlier.
- The script's refusal on that state, with `--owner-approved` and `--i-stopped-the-backend`:
  "refusing to write to soccer_predictions while the backend looks alive, whatever
  --i-stopped-the-backend says: 127.0.0.1:8000 accepts connections …; the scheduler recorded
  sync:task:settle … 8 s ago".

On the copy, the last look was exercised for real: another session asked for a target row
`FOR UPDATE` while the repair held it, and the repair rolled back and wrote nothing.
`pg_stat_activity` is read once per transaction and then kept. So the script clears that snapshot
before each look; without that, the late look would have listed the sessions of the first one.

### A row written back anyway is found again

If a pass wrote a fixture back after all, that fixture carries no record of the correction. Its
competition-day, though, is already corrected and no longer reads as false. The earlier version
skipped such a fixture ("its day has no false observation this run accounts for"), so a re-run
could not repair it.

Each observation's audit record in `archive_corrections` now keeps what planning that day's
fixtures needs. A re-run rebuilds the day from it and plans the fixture again. On the copy, all
66 fixtures were written back to their `before` in one transaction. The re-run planned all 66
again (57/3/6), each against its day's earlier correction, and every corrected field came out
exactly as in the first apply. Only the `now`-dependent fields differ (`attempts_quality_as_of`,
`next_ask_after`, the `corrections` stamp). The transaction was rolled back, and the copy's hashes
are unchanged.

A false observation on a corrected day is also planned again, unless it carries that correction's
own stamp (`count_quality_as_of`). The only such case is a class-3 entry kept without
reconstruction.

### The cut is pinned, and the records check it

Redis's `last_success_at` is right only while the outage lasts. Live Score's first success of any
kind once access returns overwrites it, for example a club fixtures call. Planned with that later
instant, every not-answer before it reads as genuine. The earlier version then exited 0 with a
partial plan (3 observations and 5 fixtures instead of 13 and 66) and would have applied it.

Now:

- `--apply` needs `--livescore-last-success`, the instant the owner approved in this report.
  Without it the script refuses. A report without it uses Redis's value, and says it is not pinned.
- Redis is then a check, not a source. When it records any other last success, the script makes no
  plan in either mode: later means the outage has ended, earlier means the instant given is wrong.
- The database's own records are checked too, whatever Redis holds. The script refuses if Live
  Score is recorded answering after the cut (an observation of any competition, or a match row it
  synced), or if a not-answer still stored was stamped before the cut. A cut moved past the start of
  the outage reads all of those as genuine.

On the copy:

- given 2026-10-08 10:00, the run was refused on Redis;
- planned directly with that instant, it was refused on the records ("Africa Cup of Nations
  Qualifications 2026-09-25: the not-answer stored there (api_football) was stamped 2026-10-05
  03:23:35 …, before the 2026-10-08T10:00:00 given");
- with one match row marked as synced by Live Score on 10-08 (rolled back), it was refused with
  "1 match row livescore synced after …".

## Invariants checked after the first apply

| Check | Result |
| --- | --- |
| National observations naming `api_football` or `thesportsdb` (all 29 national leagues) | **0** |
| National observations stamped after the cut | **0** |
| National fixtures with `last_attempt_at` or `archive.asked_at` after the cut | **0** |
| National fixtures whose last outcome still reads "api_football/thesportsdb answered…" | **0** (was 1) |
| Each target row's stored value equals the plan's `after` (13 observations, 66 recovery objects) | **all equal** |
| `md5(to_jsonb(row))` of every leagues/matches row outside the target set (32 leagues, 279 matches) | **all identical** |
| Inside the target set (4 leagues, 66 matches): hash with `league_metadata`/`match_metadata` and `updated_at` removed | **all identical**: nothing else changed (status, scores, kickoff, ids) |
| Exact `count(*)` of all 78 tables | **unchanged** (also after the second apply) |
| Rows the second `--apply` wrote | **0** observations, **0** fixtures (66 skipped as already corrected) |
| Every leagues/matches row after the second apply | **identical** to after the first |
| Corrected fixtures carrying a `next_ask_after` | **65**; the one without is the closed relisting `9dbb3854`, and no row with `relisted_as` carries one |
| What `serialize_recovery` serves for the 66 rows | quality `exact` 57, `upper_bound` 6, `unverified` 3; no archive and no `last_attempt_at` after the cut |

Belgium v Turkey (`54f0d0cf`) is the row the API served as "3 attempts, archive empty at 2026-10-05
16:35:46". On the copy it is now served as no attempts, no archive, `attempts_quality: exact` and due now.

Solomon Islands v Vanuatu (`aecec855`) kicked off 2026-09-24 04:00. From about 2026-10-07 04:00,
its age plus the 24-hour retry gap passes 14 days, so the first answered ask after that would stop
it. Stopped at 2026-10-08 05:00, for example, the sentence would read:

> We asked the results provider at most 19 times, most recently 2026-10-08 05:00 UTC, and each answer
> it gave held no result for this match. The 18 counted before 2026-10-07 02:53 UTC may include asks
> recorded as answered when no request was sent, so that part is an upper bound; the 1 since is exact.

## Row by row

The full detail is in `plan.jsonl`.

### Observations

| Competition | Date | Class | Before: state/rows/provider, ×asked, stamp | After | Quality |
| --- | --- | --- | --- | --- | --- |
| CONCACAF Nations League | 10-02 | 1 | empty/0/api_football, ×3, 10-05 16:35 | removed: the date reads `unknown` | 3 asks removed |
| CONCACAF Nations League | 10-03 | 1 | ×4, 10-05 22:54 | removed | 4 removed |
| CONCACAF Nations League | 10-04 | 1 | ×1, 10-06 00:25 | removed | 1 removed |
| UEFA Nations League | 10-02 | 1 | ×3, 10-05 16:35 | removed | 3 removed |
| UEFA Nations League | 10-03 | 1 | ×4, 10-05 22:54 | removed | 4 removed |
| UEFA Nations League | 10-04 | 1 | ×1, 10-06 00:25 | removed | 1 removed |
| National Teams Friendlies | 10-03 | 1 | ×4, 10-05 22:54 | removed | 4 removed |
| National Teams Friendlies | 10-04 | 1 | ×1, 10-06 00:25 | removed | 1 removed |
| National Teams Friendlies | 09-30 | 2 | empty/0/api_football, ×31, 10-05 16:04 | answered/6/livescore, ×29, 10-02 12:16:17 (from the dump) | **unverified**, 2 removed |
| National Teams Friendlies | 10-02 | 2 | empty/0/api_football, ×8, 10-05 22:24 | empty/0/livescore, ×5, 10-02 14:53:28 (from the dump) | **unverified**, 3 removed |
| AFCON Qualifications | 09-25 | 3 | empty/0/api_football, ×31, 10-05 03:23 | answered/**14**/livescore, ×29, 10-01 07:46:53 | **upper_bound**, reconstructed, 2 removed |
| National Teams Friendlies | 09-24 | 3 | empty/0/api_football, ×17, 10-05 03:23 | answered/**5**/livescore, ×15, 10-01 07:46:51 | **upper_bound**, reconstructed, 2 removed |
| National Teams Friendlies | 09-28 | 3 | empty/0/api_football, ×25, 10-05 03:54 | answered/**4**/livescore, ×23, 10-01 07:16:22 | **upper_bound**, reconstructed, 2 removed |

Where the script read each entry as it stood at the cut:

- **The dump** (`backups/soccer_predictions-before-relisting-repair-20261005T034608Z.sql.gz`) for
  Friendlies 09-28, 09-30 and 10-02.
- **The 03:15 capture** in `docs/evidence/livescore-archive-observations.json` for AFCON-Q 09-25 and
  Friendlies 09-24. The dump already holds a later not-answer for these two (03:23:35).

Where the dump and the capture both hold an entry, the script checks that they agree. Every removed
entry is kept whole in `league_metadata.archive_corrections` of its competition, together with
what a later run needs to plan that day's fixtures again.

### Fixtures

| Group | Fixture | Kickoff (UTC) | Status | Attempts | `last_attempt_at` | `archive` | Quality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B | Papua New Guinea v Solomon Islands (`8295ac2c`) | 09-30 04:00 | scheduled | 31 → 29 | 10-05 16:04:55 → 10-02 12:16:17 | empty/0 → answered/6 | unverified |
| B | Mauritius v Djibouti (`8816e353`) | 09-30 12:00 | live | 22 → 20 | 10-05 16:04:55 → 10-02 12:16:17 | empty/0 → answered/6 | unverified |
| B | Congo v Uganda (`7e976555`) | 10-02 10:00 | live | 8 → 5 | 10-05 22:24:42 → 10-02 14:53:28 | empty/0 → empty/0 @ 14:53:28 | unverified |
| C | Solomon Islands v Vanuatu (`aecec855`) | 09-24 04:00 | scheduled | 20 → 18 | 10-05 03:23:35 → 10-01 07:46:51 | empty/0 → answered/5 (reconstructed) | upper_bound |
| C | Papua New Guinea v New Caledonia (`1b4073e5`) | 09-24 07:00 | scheduled | 20 → 18 | same | same | upper_bound |
| C | Turkmenistan v New Zealand (`f0b594b7`) | 09-24 09:30 | scheduled | 20 → 18 | same | same | upper_bound |
| C | Senegal v Mozambique (`9dbb3854`, closed second listing) | 09-25 19:00 | postponed | 31 → 29 | 10-05 03:23:35 → 10-01 07:46:53 | empty/0 → answered/14 (reconstructed) | upper_bound |
| C | Kyrgyzstan v Lebanon (`535ea78d`) | 09-28 12:00 | scheduled | 25 → 23 | 10-05 03:54:23 → 10-01 07:16:22 | empty/0 → answered/4 (reconstructed) | upper_bound |
| C | Tajikistan v Palestine (`dc2cbc24`) | 09-28 12:00 | scheduled | 25 → 23 | same | same | upper_bound |

**Group A: 57 fixtures, 148 attempts, every one false.** Their `attempts`, `first_attempt_at`,
`last_attempt_at` and false `archive` are removed. Their genuine deferrals (`deferrals`,
`last_deferred_*`) and the `deferred` outcome the current code wrote are kept.

| Competition | Date | Fixtures | Attempts before |
| --- | --- | --- | --- |
| UEFA Nations League | 10-02 | 10 | 3 each |
| UEFA Nations League | 10-03 | 8 | 4 each |
| UEFA Nations League | 10-04 | 8 | 1 each |
| CONCACAF Nations League | 10-02 | 3 | 3 each |
| CONCACAF Nations League | 10-03 | 5 | 4 each |
| CONCACAF Nations League | 10-04 | 7 | 1 each |
| National Teams Friendlies | 10-02 (15:00 kickoff) | 1 | 3 |
| National Teams Friendlies | 10-03 | 8 | 4 each |
| National Teams Friendlies | 10-04 | 7 | 1 each |

**Applies to every fixture:**

- `next_ask_after` is recomputed with the application's own schedule (`_next_ask_from`) for 65
  fixtures; all 65 are due now. The closed second listing `9dbb3854` gets none, as it has none
  stored: nothing asks about it again, and `MatchRegistry._retire_relisted` removes the field for
  the same reason.
- Each row gets `attempts_quality`, `attempts_at_correction` and `attempts_quality_as_of`, plus a
  `corrections` audit record (`by`, `script_sha256`, `group`, `removed_attempts`, the replaced
  values, `restored_from`).
- One last outcome was still the not-answer's sentence: `9dbb3854`. It is replaced by the reconstructed
  Live Score answer of 10-01 07:46:53, worded as reconstructed.
- No status, score, result or stop was touched.

## How far each count can be trusted

- **Exact.**
  - The 8 class-1 removals: no entry existed at the cut, so every recorded ask was a not-answer.
  - The 57 group-A fixtures, now carrying no attempts: their first attempt came after the cut.
  - The 29 observation increments and 161 fixture attempts after the cut. These are counter
    differences against the record at the cut. Each fixture's difference was checked against its
    competition-day's difference, and against the dump where it holds the fixture.
- **Unverified** (class 2 and group B: Friendlies 09-30 and 10-02; `8295ac2c`, `8816e353`, `7e976555`).
  - The values are restored from the record at the cut.
  - Not-answers before 2026-10-02 14:53 were possible: the fallbacks have been in the chain since
    2026-09-22, and Live Score cooled down at other times. Nothing records them.
  - Congo v Uganda's 5 asks of 10-02 (12:50–14:53) are probably real, because Live Score answered at
    12:16, 13:47 and 14:53 that day. That is not proven.
- **Upper bound** (class 3 and group C). The entry at the cut was itself a not-answer: API-Football
  at 10-02 08:12, TheSportsDB at 08:43, both recorded in the 03:15 capture.
  - That one proven not-answer is subtracted. More may remain in the count.
  - The 3 rows from before `first_attempt_at` existed (Friendlies 09-24) were first asked before
    7380242 introduced it. The observations that prove the 08:12 not-answer were introduced in the
    same commit, so these rows are treated as asked at 08:12 too.
- **Reconstructed** (class 3 state and group C clock):
  - **Row counts.** The 14, 5 and 4 rows are read from the match rows synced 0.008–0.33 s before
    `last_answered_at`. The method agreed on 18 of 18 genuine answered observations. The rows are
    listed in `evidence-snapshot.json`.
  - **What it cannot exclude.** A real Live Score ask between that answer and the 10-02 08:12
    not-answer that returned 0 rows. The next ask may therefore come a little earlier than the old
    record would have allowed, which errs towards asking.

## Decisions the owner has to make before any live apply

1. **Reconstruction on or off.** On (rehearsed): 3 observations read `answered` with 14/5/4 rows,
   flagged `reconstructed`, and the 6 group-C fixtures take their clock and archive from that answer.
   Off (`plan-without-reconstruction.jsonl`): only the counts change on those 9 rows. They keep the
   not-answer's `empty`, its provider name `api_football` and its 10-05 stamps, so three national
   observations still name API-Football. The retry clock of the 6 fixtures stays on a false ask, and
   `9dbb3854` loses its false last outcome with nothing in its place.
2. **Subtract the proven 2026-10-02 not-answer** (default on). Off would remove 3 asks and 6
   attempts fewer: ×30/×16/×24, and fixtures 19/19/19/30/24/24.
3. **The closed relisting `9dbb3854`** (Senegal v Mozambique, POSTPONED, `relisted_as` the played
   row). It is corrected by rule. With `--skip-closed-relistings` it would be left exactly as it is:
   31 attempts and "api_football answered…" as its last outcome. Nothing asks about it again either
   way, and either way it advertises no next ask.
4. **Who stops the backend on :8000 for the live apply, and keeps it stopped until the apply
   commits.** Other sessions restart it. The `strange-matsumoto-455cbe` worktree is at d6f9a13,
   the code from before the fix, and a backend started from it would write not-answers again. The
   script now checks the claim (see above), but it cannot stop a backend started elsewhere a second
   after its last look. Only a person can keep it stopped.
5. Whether Congo v Uganda's 5 asks should stay `unverified` (as rehearsed) or be accepted as exact.

**Proposed live apply, once approved:**

1. Stop :8000, check who owns the port, and wait two minutes: the script refuses while the
   scheduler has recorded a task within the last two ticks.
2. Take a fresh plain backup and `backups/not-answers-immediately-before-apply-<UTC>.jsonl`.
3. Run the script report-only against `soccer_predictions` with
   `--livescore-last-success 2026-10-02T14:53:28.028159Z` and the chosen options, and compare it with
   this plan. Deferral counters and `next_ask_after` will have moved since; the corrected fields
   should not.
4. Run the same command with `--apply --owner-approved --i-stopped-the-backend` added.
5. Re-run the checks above.
6. Restart from main with this change, which is required for the markers to be served and worded.
   After the next pass, confirm that no national observation names API-Football or TheSportsDB.

**If Live Score answers first, this plan no longer holds.** Real asks would then be mixed into the
counters, and a person has to make the plan again. What the script does in that case:

- With the pinned instant, it refuses as soon as Redis records a later success. Live Score's first
  success of any kind once access returns writes that.
- Whatever Redis holds, it also refuses when that answer left a trace in the database: an
  observation, or a synced match row.
- Given the newer Redis instant instead, it refuses while any not-answer is still stored with a
  stamp before that instant. Today all 13 are.

The script cannot see a success that left no trace in the database once Redis no longer holds it,
because the key expired or was cleared. Such a success touched no recovery counter, so the pinned
plan still holds then.

## The copy, kept for inspection

`soccer_predictions_rehearsal_notanswers` on the same server holds the repaired state. For example:

```sql
SELECT l.name, o.key, o.value FROM predictions.leagues l, jsonb_each(l.league_metadata->'archive_observations') o
 WHERE l.league_metadata ? 'archive_corrections' ORDER BY 1, 2;
SELECT id, match_metadata->'recovery' FROM predictions.matches
 WHERE match_metadata->'recovery'->'corrections' @> '[{"by": "backend/scripts/repair_not_answers.py"}]';
```

## Evidence that decays

- **Synced rows.** The `last_synced_at` stamps that give 14/5/4 rows move when Live Score re-lists
  those fixtures.
- **Live Score status in Redis.** `provider:status:livescore` expires 7 days after its last write,
  and its `last_success_at` changes on the first success. From then on the script refuses the
  pinned plan (see above).
- **Budget counters.** The Redis budget keys for 2026-10-05 and 2026-10-06 expire between about
  03:20 UTC on 2026-10-07 and 01:00 UTC on 2026-10-08 (TTLs of 1.4–23 h at 01:57).
- **The prior dump.** The 10-05 03:46 dump exists only in the local, gitignored `backups/`.
- **Earlier scratch captures.** The machine restart at 2026-10-06 01:09 UTC erased
  `status-0410.json`, `status-0603.json` and `sched-watch3-*` with `/private/tmp`. The survey's own
  copies from 2026-10-07 01:05–01:23 UTC sit in session scratch, which is not durable either.

That is why `evidence-snapshot.json` copies the values the repair rests on.

## Appendix: the measurement SQL

`$KEYS` stands for the 34 national-team keys of `app/services/providers/competitions.py`.

```sql
\set cut '''2026-10-02T14:53:29.028159+00:00'''
WITH national AS (
  SELECT l.id, l.name FROM predictions.leagues l
  JOIN predictions.provider_entity_refs r ON r.entity_type = 'league' AND r.provider = 'canonical' AND r.entity_id = l.id
  WHERE r.external_id IN ($KEYS)
), obs AS (
  SELECT n.name, o.key AS day, o.value AS entry FROM national n
  JOIN predictions.leagues l ON l.id = n.id, jsonb_each(coalesce(l.league_metadata->'archive_observations', '{}'::jsonb)) o
), tainted AS (
  SELECT * FROM obs WHERE entry->>'provider' IN ('api_football', 'thesportsdb') OR (entry->>'asked_at')::timestamptz > :cut
), fx AS (
  SELECT m.id, m.match_metadata->'recovery' AS rec FROM predictions.matches m JOIN national n ON n.id = m.league_id
  WHERE m.match_metadata ? 'recovery'
)
SELECT 'false observations', count(*) FROM tainted
UNION ALL SELECT 'affected fixtures', count(*) FROM fx
  WHERE (rec->>'last_attempt_at')::timestamptz > :cut OR (rec->'archive'->>'asked_at')::timestamptz > :cut;
```

The row-hash checks compared `md5(to_jsonb(t)::text)` and
`md5((to_jsonb(t) - '<metadata column>' - 'updated_at')::text)` for every row of `predictions.leagues`
and `predictions.matches`, before and after each apply. The row counts are `count(*)` of every table
in every non-system schema.
