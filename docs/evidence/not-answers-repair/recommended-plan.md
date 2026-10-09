# Not-answers repair: the recommended plan — approved and executed

**Executed 2026-10-09 00:00 UTC** with every choice below as recommended; the owner's reviewer
note of 2026-10-08 approved proceeding. The execution record: backup
`soccer_predictions-before-not-answer-repair-20261008T235832Z.sql.gz` (verified by restoring it;
the plan derived from the copy matched the rehearsal), live report-only identical to the rehearsed
plan on every corrected field, apply wrote 13 observations and 66 fixtures, a second apply wrote 0,
all 311 untouched leagues/matches rows byte-identical to the backup, every table's row count
unchanged, marks served 57/6/3, and the restarted scheduler's first passes added nothing tainted.
The applied report is `applied.jsonl` beside this file; docs/known-limitations.md carries the same
record. The sections below are the plan as approved.

One plan, with the choices made. `rehearsal.md` holds the evidence behind each choice, the row-by-row
before and after, and the alternatives; this page is what to approve and what to run.

## What is wrong, in one paragraph

Until commit 201442e, whenever Live Score was out of the provider chain, the results and recovery
passes recorded API-Football or TheSportsDB as having answered for national-team competitions
although neither holds an id for them and no request was sent. Measured read-only on 2026-10-07,
**13 archive observations and 66 fixtures** carry what those not-answers wrote: `empty` archive
states with the wrong provider's name, attempts that never happened, retry clocks moved by them.
A reader is served those attempts, and a stop the retry budget makes on one of these fixtures would
quote a count that includes asks never made. Nothing in the live database has been changed.

## The recommendation

| Choice | Recommended | Why |
|---|---|---|
| Reconstruct the three observations whose record before the outage was itself a not-answer | **On** (`--reconstruct-from-synced-rows`) | Live Score's last real answer for each is read from the match rows that answer synced; the method agreed with the recorded row count on 18 of 18 genuine answers. Off, three national observations keep naming API-Football and six fixtures keep a retry clock set by a false ask. Every reconstructed value is flagged `reconstructed` and its count `upper_bound`; the API now says so. |
| Subtract the one not-answer of 2026-10-02 08:12/08:43 UTC that the 03:15 capture proves | **On** (the default) | It is proven for each of the 3 observations and 6 fixtures it touches; leaving it would keep a known false ask in counts the page quotes. |
| The closed second listing of Senegal v Mozambique (`9dbb3854`, POSTPONED) | **Correct it** (do not pass `--skip-closed-relistings`) | Nothing will ask about it again either way; corrected, its record stops naming API-Football and carries the same marks as every other row. |
| Congo v Uganda's five asks of 2026-10-02 | **Stay `unverified`** | They are probably real (Live Score answered that afternoon) but nothing records it; a count the page calls exact must be one the store can show. |

What the plan does NOT do: touch any status, score, result, kickoff or id; invent a count (every
count it cannot show is marked `upper_bound` or `unverified`, and the page words those "at most");
write to any row outside the 13 + 66 (the rehearsal hashed every other row identical).

## The window

- **Before Live Score answers again.** The script refuses as soon as Redis or the database records a
  Live Score success after the pinned instant, because real asks would then be mixed into the
  counters and the plan would have to be made again by a person. So: apply the repair before
  sending the Live Score support question, or at least before access is restored.
- **About five minutes with the main backend stopped**, any time of day. The script refuses while
  the scheduler recorded a task in the last two ticks, so stop the backend, wait two minutes, run
  the three commands below, restart. Only the backend stops (`stop backend`); the frontend stays
  up and serves stored data meanwhile.
- No other backend may be started against `soccer_predictions` during the window (the
  `strange-matsumoto-455cbe` worktree is still at d6f9a13, the code from before the fix).

## Exactly what runs

From the repository root, as the owner, with the choices above:

```bash
# 0. stop the main backend (the frontend stays up) and let the scheduler go quiet
scripts/local-servers.sh stop backend
sleep 130

# 1. the backup that is also the rollback (a plain pg_dump; never docker/scripts/backup-database.sh)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
docker exec soccer_predictions_postgres pg_dump -U postgres -d soccer_predictions \
  | gzip > backups/soccer_predictions-before-not-answer-repair-$STAMP.sql.gz

# 2. the plan, report-only, against the live database (a read-only transaction)
cd backend
PRIOR=../backups/soccer_predictions-before-relisting-repair-20261005T034608Z.sql.gz
PIN=2026-10-02T14:53:28.028159Z
./venv311/bin/python scripts/repair_not_answers.py --prior-dump $PRIOR --livescore-last-success $PIN \
  --reconstruct-from-synced-rows --report ../backups/not-answers-live-plan-$STAMP.jsonl
#    Expected: 13 observations (classes 8/2/3) and 66 fixtures (groups 57/3/6), 32 asks and 167 attempts
#    removed, 0 rows skipped. Deferral counters and next_ask_after will differ from the rehearsal;
#    the corrected fields must not. Stop here if the counts differ.

# 3. the apply, in one transaction, every target row locked and re-checked against the plan
./venv311/bin/python scripts/repair_not_answers.py --prior-dump $PRIOR --livescore-last-success $PIN \
  --reconstruct-from-synced-rows --apply --owner-approved --i-stopped-the-backend \
  --report ../backups/not-answers-live-apply-$STAMP.jsonl
#    Expected: "Written: 13 observations, 66 fixtures." Then the same command once more:
#    "Written: 0 observations, 0 fixtures" and 66 rows skipped as already corrected.

# 4. the checks (the SQL is in rehearsal.md, "Appendix"): 0 national observations naming
#    api_football or thesportsdb; 0 fixtures with a retry clock or archive stamped after the pin.

# 5. restart on the current code, which serves and words the marks
cd .. && scripts/local-servers.sh start backend
```

The script refuses on its own if any of these is not true: the database name is the live one and
`--owner-approved` is missing; `--i-stopped-the-backend` is missing; anything accepts connections
on 127.0.0.1:8000; a sync pass holds its lock; the scheduler recorded a task in the last two
minutes; Live Score is recorded answering after the pin; a target row changed between the plan
and the apply. It looks once more just before COMMIT and rolls back if another session is waiting
on a row it locked.

## Rollback

While the backend is still stopped, the backup from step 1 is the rollback, whole: drop and
recreate `soccer_predictions` from it (`dropdb`, `createdb`, `gunzip -c ... | psql -v
ON_ERROR_STOP=1`, then the `alter database ... set search_path` line from
`docs/isolated-dev-environment.md`). Nothing else writes to the database while the backend is
stopped, so nothing is lost. Once the backend has restarted and written again, a rollback is
row by row: every corrected row carries a `corrections` audit record with the values it replaced.

## After the apply

- `docs/known-limitations.md` and `docs/evidence/livescore-archive-observations.json` record that
  the repair was applied, when, and from which backup.
- The journey proof (`backend/scripts/prove_journey.py`) stops flagging the 66 fixtures as
  `attempt_counts_unreliable` by clock and flags only the 9 the repair marked `upper_bound` or
  `unverified`, by their mark.
- `soccer_predictions_rehearsal_notanswers` can be dropped.
