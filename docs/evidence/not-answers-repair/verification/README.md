# The apply of 2026-10-09, verified twice: in the window, and again from the backup alone

The repair was applied to `soccer_predictions` between 2026-10-08 23:53 and 2026-10-09 00:10 UTC
(`../recommended-plan.md` carries the execution record and the authorization correction;
`../applied.jsonl` is the applied report). This folder preserves the raw verification outputs the
reviewer asked for, and — because the live database has legitimately moved on since (its scheduler
keeps writing genuine deferral bookkeeping on every pass) — a **reproduction of the entire chain
from the preserved backup alone**, so every window claim can be re-established today without the
live database.

Console files are scrubbed only of local paths (`~`, `<scratch>`); nothing else was altered.

## What was run in the window (2026-10-08 23:53 – 2026-10-09 00:10 UTC)

| Step | Files | Result |
|---|---|---|
| Backup `soccer_predictions-before-not-answer-repair-20261008T235832Z.sql.gz` (local `backups/`, gitignored): gzip intact, 75 `COPY` blocks, no `CREATE`/`DROP DATABASE`, restored cleanly into a scratch copy | — | 345 matches, 36 leagues, 5 slips in the copy |
| Backup validation: report-only against the restored copy, compared with the rehearsed `../plan.jsonl` on every corrected field | `window-backup-validation.out.txt`, `window-backup-comparator.out.txt` | identical: 13 observations (8/2/3), 66 fixtures (57/3/6), 32 asks / 167 attempts, synced-row method 18 of 18 |
| Report-only against the live database, same comparison | `window-report-only.jsonl`, `window-report-only.out.txt`, `window-report-comparator.out.txt` | identical on every corrected field |
| `--apply` | `window-apply.out.txt`, `../applied.jsonl` | written: 13 observations, 66 fixtures |
| Second `--apply` | `window-second-apply.out.txt`, `window-second-apply.jsonl` | written: 0 and 0; 66 rows skipped as already corrected |
| Invariants and preservation against the scratch copy of the backup | console capture below | all held |

The two comparator outputs were regenerated after the window from the saved `.jsonl` reports (the
comparison is a pure function of those files); everything else is the window's own console output.

**The preservation run's console output, as captured in the session.** Its scratch copy
(`soccer_predictions_preapply_check`) was dropped after the window, so this exact run cannot be
repeated against today's moved database; the reproduction below re-establishes the same result
from the backup:

```
national observations naming api_football/thesportsdb: 0
observations stamped after the cut: 0
fixtures with retry clock after the cut: 0
fixtures whose archive stamp is after the cut: 0
fixtures still reading 'api_football/thesportsdb answered': 0
attempts_quality served: exact|57 unverified|3 upper_bound|6
row counts compared on 74 tables
predictions.leagues: 32 untouched rows identical, 4 target rows metadata-only
predictions.matches: 279 untouched rows identical, 66 target rows metadata-only
preservation exit=0
```

(The backup holds 75 `COPY` blocks but the preservation check compares 74 tables: the 75th is
`public.db_init_log`, the Docker init script's own log, outside the five application schemas.)

## The reproduction (2026-10-09, after the window), from preserved artifacts only

Inputs: the backup above, the prior dump of 2026-10-05, the pinned cut
`2026-10-02T14:53:28.028159Z`, and `backend/scripts/repair_not_answers.py` at HEAD. The backup was
restored twice — a pristine copy and a copy to repair — and the whole chain was run against them:

| Step | File | Result |
|---|---|---|
| Report-only on the restored copy | `repro-report-only.out.txt` | 13 / 66, classes 8/2/3, groups 57/3/6, 32 / 167 |
| Compared with the rehearsed `../plan.jsonl` | `repro-comparator.out.txt` | identical on every corrected field |
| `--apply` on the copy | `repro-apply.out.txt` | written: 13 and 66 |
| Second `--apply` | `repro-apply-2.out.txt` | written: 0 and 0; 66 skipped |
| Preservation, repaired copy against pristine copy | `repro-preservation.out.txt` | 311 untouched leagues/matches rows byte-identical; 70 target rows metadata-only; 74 tables' row counts unchanged |
| The repaired copy's rows against the live apply's `../applied.jsonl` | `repro-cross-check.out.txt` | identical corrected fields: the live apply wrote exactly what the backup and the script produce |

Anyone holding the backup can repeat this: restore it twice, run the script with the options
above, and run `check_preservation.py` (here) between the two copies.

## The checkers

- `compare_plans.py` — compares two repair reports on the **corrected** fields only. Deferral
  counters, next-ask times and audit stamps move between runs by design (the scheduler keeps
  writing genuine bookkeeping), and the plan said they would; the corrected fields must not.
- `check_preservation.py` — row counts for every table in the five application schemas, and
  per-row `md5(to_jsonb(...))` for leagues and matches: untouched rows must be byte-identical,
  target rows may differ only in their metadata column and `updated_at`.

Both read with `PGOPTIONS='-c default_transaction_read_only=on'` and write nothing.
