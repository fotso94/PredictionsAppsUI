# Environment slip in two delete-counts before-runs (2026-10-20)

Written 2026-10-21. This file replaces the conclusion that `HANDOFF.md` gave for this slip until
then ("Nothing reached live"). That conclusion went further than the evidence. What follows keeps
three things apart:
- what the agent transcript records;
- what reading the code supports, which is inference;
- what cannot be established from anything that survives.

## Summary

- **One Bash call made the slip.** It was issued at 2026-10-20T23:38:14Z (19:38 EDT) and held two
  pytest runs, A and B. Both passed the test settings through an unquoted shell variable,
  `env $ENVV`. zsh passes such a variable as one word, so the settings did not take effect as
  intended; run A's own skip message shows this for `RACE_TEST_DATABASE_URL`. Every other test
  run audited passed its settings literally (section 4).
- **The settings the processes resolved point at live.** Both the code defaults and
  `backend/.env`, which is a link to the live checkout's file, resolve Redis to `localhost:6379`.
  That is the live Redis container's published port.
- **What the outputs show.** Run A's race test skipped instead of failing. Every other outcome
  matched the corrected reruns.
- **What reading the code supports.** The code paths those tests run issue no Redis command and
  open no connection to the settings database. This is inference, not observation.
- **What cannot be established.** No connection, socket or server-side record was captured. So
  whether either process reached live Redis (:6379) or the live database is unknown.
- **What the reruns are.** They are separate processes with correct settings. They replaced the
  two logs. They show what the tests do when configured correctly, and nothing about what the
  earlier two processes connected to.

## Sources and sanitising

- **The transcript.** This is the area-1 implementation agent, labelled `impl:backend-delete-metrics`,
  in `~/.claude/projects/<project>/<session>/subagents/workflows/wf_041b039e-bb4/agent-aa1d0019a45605aba.jsonl`.
  It is outside the repository and is not committed.
- **The reconstruction.** The audit and reconstruction were made on 2026-10-21 by reading that
  transcript and the transcripts of the other agents (section 4).
- **Sanitising.** The worktree path is written `<worktree>`. No database password, key or token
  appears in the quoted commands. Apart from that path, the commands and outputs below are quoted
  exactly as the tool calls and tool results recorded them.
- **The code.** The runs were on branch `expert-fixes` at `6cfb1c22`. The product code was unchanged
  (`git diff --stat -- backend/app` was empty), and the new tests were not yet committed. They
  were committed with the fix in `549c072c`.

## Timeline of the agent's before-runs (UTC, 2026-10-20)

| Time | Run | Settings | Recorded summary | What happened to its log |
|---|---|---|---|---|
| 23:37:14 | delete-counts selection, `-rs` | literal | 19 failed, 4 passed, 62 deselected | overwritten at 23:37:38 |
| 23:37:38 | the same selection, `-rfEs` | literal | 19 failed, 4 passed, 62 deselected (the race test among the 19 FAILED) | overwritten by run A at 23:38:14 |
| 23:37:47 | history tests with the old-code clock shim | literal | 3 failed, 2 passed, 38 deselected | overwritten by run B at 23:38:14 |
| 23:38:03 | (edit) `test_expert_history.py`: asserts reordered so the scoring assert comes first | – | – | – |
| **23:38:14** | **run A**: the delete-counts selection | **`env $ENVV`** | **18 failed, 4 passed, 1 skipped, 62 deselected** | overwritten by the rerun at 23:38:52 |
| **23:38:14** | **run B**: the history tests with the shim | **`env PYTHONPATH=$EV $ENVV`** | **3 failed, 2 passed, 38 deselected** | overwritten by the rerun at 23:39:02 |
| 23:38:20 | (grep) the agent reads run A's log | – | the SKIPPED line, below | – |
| 23:38:28–38 | (grep) the agent reads `main.py`, the expert endpoints and services, `deps.py`, `prediction_cache.py`, `core/redis.py`, `services/cache.py` for Redis use | – | – | – |
| 23:38:52 | corrected rerun of A | literal | 19 failed, 4 passed, 62 deselected | committed as `delete-counts-before-all.log` |
| 23:39:02 | corrected rerun of B | literal | 3 failed, 2 passed, 38 deselected | committed as `delete-counts-before-history-behaviour.log` |

The misconfigured call also destroyed the two good logs from 23:37:38 and 23:37:47. Of those
four runs, only the transcript's excerpts survive.

## Original execution (from the agent transcript): the misconfigured call, runs A and B

Bash call issued at 2026-10-20T23:38:14.290Z; tool result at 23:38:17.758Z (`is_error=false`).

```
cd <worktree>/backend && EV=<worktree>/docs/evidence/expert-fixes-2026-10-20 && SEL="delete_retried or redelete or first_delete_after_kickoff or without_a_clock or test_expert_manage_db or simultaneous_deletes or reports_the_total or add_up or default_to_zero" && ENVV="POSTGRES_DB=soccer_predictions_test REDIS_HOST=127.0.0.1 REDIS_PORT=6390 SYNC_SCHEDULER_ENABLED=false EMAIL_ENABLED=false LEASE_TEST_REDIS_URL=redis://127.0.0.1:6390/9 RACE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5440/forecast_race_test" && { echo "# delete-counts BEFORE: the new regression tests against the unchanged product code"; echo "# branch expert-fixes at $(git rev-parse --short HEAD); product code unchanged (git diff --stat -- backend/app is empty: '$(git diff --stat -- app | tail -1)')"; echo "# run at $(date -u +%Y-%m-%dT%H:%M:%SZ); -rfEs (a superset of -rs) so every failure is named with its reason"; } > $EV/delete-counts-before-all.log && env $ENVV ./venv311/bin/python -m pytest tests/services/test_expert_history.py tests/api/test_expert_manage_db.py tests/services/test_expert_delete_race_pg.py tests/api/test_expert_endpoints.py -k "$SEL" -q -p no:cacheprovider -o addopts="" -rfEs >> $EV/delete-counts-before-all.log 2>&1; echo "exit=$?" | tee -a $EV/delete-counts-before-all.log; grep -E "passed|failed" $EV/delete-counts-before-all.log; { echo "# delete-counts BEFORE (behaviour): the clock-driven delete-retry tests against the unchanged product code"; echo "# the old constructor has no clock, so docs/evidence/expert-fixes-2026-10-20/delete_counts_old_code_clock_shim.py"; echo "# (loaded with -p) feeds the same clock to the OLD module's datetime.utcnow(); no product logic is changed"; echo "# branch expert-fixes at $(git rev-parse --short HEAD); git diff --stat -- backend/app: '$(git diff --stat -- app | tail -1)'; run at $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } > $EV/delete-counts-before-history-behaviour.log && env PYTHONPATH=$EV $ENVV ./venv311/bin/python -m pytest tests/services/test_expert_history.py -k "delete_retried or redelete or first_delete_after_kickoff or without_a_clock" -p delete_counts_old_code_clock_shim -q -p no:cacheprovider -o addopts="" -rfEs >> $EV/delete-counts-before-history-behaviour.log 2>&1; echo "exit=$?" | tee -a $EV/delete-counts-before-history-behaviour.log; grep -E "^(FAILED|ERROR|SKIPPED)|^E  |passed|failed" $EV/delete-counts-before-history-behaviour.log
```

Recorded output. The first `exit=1` and the first summary belong to run A; the rest belongs to run
B.

```
exit=1
18 failed, 4 passed, 1 skipped, 62 deselected, 18 warnings in 1.02s
exit=1
E       AssertionError: a win withdrawn before kickoff was scored (PredictionOutcome.WON) after a retried delete
E       assert <app.models.predictions.PredictionResult object at 0x10b9b4d50> is None
E       assert datetime.datetime(2025, 12, 24, 14, 0) == datetime.datetime(2025, 12, 24, 10, 0)
E        +  where datetime.datetime(2025, 12, 24, 14, 0) = <app.models.predictions.Prediction object at 0x10ba50990>.deleted_at
E       assert datetime.datetime(2026, 1, 23, 15, 0) == (datetime.datetime(2025, 12, 24, 15, 0) + datetime.timedelta(seconds=10800))
E        +  where datetime.datetime(2026, 1, 23, 15, 0) = <app.models.predictions.Prediction object at 0x10beba150>.deleted_at
E        +  and   datetime.timedelta(seconds=10800) = timedelta(hours=3)
FAILED tests/services/test_expert_history.py::test_a_delete_retried_after_kickoff_keeps_the_prematch_withdrawal
FAILED tests/services/test_expert_history.py::test_a_delete_retried_before_kickoff_keeps_the_first_deletion_time
FAILED tests/services/test_expert_history.py::test_a_first_delete_after_kickoff_is_still_scored_and_a_retry_changes_nothing
3 failed, 2 passed, 38 deselected, 18 warnings in 0.32s
```

### Original execution (from the agent transcript): the agent's look at run A's log

Issued at 2026-10-20T23:38:20.418Z; result at 23:38:20.454Z.

```
cd <worktree>/docs/evidence/expert-fixes-2026-10-20 && grep -n -B2 -A10 "SKIPPED\|short test summary" delete-counts-before-all.log | head -60
```

```
732-
733--- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
734:=========================== short test summary info ============================
735-FAILED tests/services/test_expert_history.py::test_a_delete_retried_after_kickoff_keeps_the_prematch_withdrawal
736-FAILED tests/services/test_expert_history.py::test_a_delete_retried_before_kickoff_keeps_the_first_deletion_time
737-FAILED tests/services/test_expert_history.py::test_another_expert_cannot_redelete_a_deleted_prediction
738-FAILED tests/services/test_expert_history.py::test_a_first_delete_after_kickoff_is_still_scored_and_a_retry_changes_nothing
739-FAILED tests/api/test_expert_manage_db.py::test_deleting_twice_answers_200_both_times_with_the_first_deletion_time
740-FAILED tests/api/test_expert_manage_db.py::test_a_repeated_delete_writes_one_audit_entry_carrying_the_stored_time
741-FAILED tests/api/test_expert_manage_db.py::test_a_deleted_prediction_cannot_be_edited
742-FAILED tests/api/test_expert_manage_db.py::test_a_deleted_prediction_cannot_be_publish_toggled[published]
743-FAILED tests/api/test_expert_manage_db.py::test_a_deleted_prediction_cannot_be_publish_toggled[archived]
744-FAILED tests/api/test_expert_manage_db.py::test_editing_or_toggling_a_missing_prediction_is_a_404_too
--
751-FAILED tests/api/test_expert_endpoints.py::TestExpertPerformance::test_the_counts_add_up_whatever_the_statuses
752-FAILED tests/api/test_expert_endpoints.py::TestExpertPerformance::test_the_new_count_fields_default_to_zero_for_an_older_payload
753:SKIPPED [1] tests/services/test_expert_delete_race_pg.py:162: RACE_TEST_DATABASE_URL is not set: no isolated PostgreSQL for independent sessions
754-18 failed, 4 passed, 1 skipped, 62 deselected, 18 warnings in 1.02s
755-exit=1
```

**Never displayed from run A.** These parts are lost with the overwritten file:
- lines 1–731: the header that recorded HEAD, the failure tracebacks and the warnings;
- lines 745–750.

### Original execution (from the agent transcript): the agent's own disclosure

The agent's final report, under `open_issues`, ends:
"So I believe nothing reached live Redis or the live database, but I cannot prove it."

## Corrected reruns (separate executions, with the settings literal on the command line)

These are new processes, started after the misconfigured ones had exited. They are what the
committed logs hold.

### Rerun of run A

Issued at 2026-10-20T23:38:52.122Z; result at 23:38:54.356Z. It overwrote run A's
`delete-counts-before-all.log`.

```
cd <worktree>/backend && EV=<worktree>/docs/evidence/expert-fixes-2026-10-20 && { echo "# delete-counts BEFORE: the new regression tests against the unchanged product code"; echo "# branch expert-fixes at $(git rev-parse --short HEAD); product code unchanged (git diff --stat -- backend/app is empty: '$(git diff --stat -- app | tail -1)')"; echo "# run at $(date -u +%Y-%m-%dT%H:%M:%SZ); -rfEs (a superset of -rs) so every failure is named with its reason"; } > $EV/delete-counts-before-all.log && env POSTGRES_DB=soccer_predictions_test REDIS_HOST=127.0.0.1 REDIS_PORT=6390 SYNC_SCHEDULER_ENABLED=false EMAIL_ENABLED=false LEASE_TEST_REDIS_URL=redis://127.0.0.1:6390/9 RACE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5440/forecast_race_test ./venv311/bin/python -m pytest tests/services/test_expert_history.py tests/api/test_expert_manage_db.py tests/services/test_expert_delete_race_pg.py tests/api/test_expert_endpoints.py -k "delete_retried or redelete or first_delete_after_kickoff or without_a_clock or test_expert_manage_db or simultaneous_deletes or reports_the_total or add_up or default_to_zero" -q -p no:cacheprovider -o addopts="" -rfEs >> $EV/delete-counts-before-all.log 2>&1; echo "exit=$?" | tee -a $EV/delete-counts-before-all.log; grep -E "^(SKIPPED)|passed|failed" $EV/delete-counts-before-all.log; grep -n "RACE\|skipped" $EV/delete-counts-before-history-behaviour.log | head
```

```
exit=1
19 failed, 4 passed, 62 deselected, 18 warnings in 1.20s
```

The last grep in that call searched run B's log, which had not yet been overwritten, for `RACE`
or `skipped`. It printed nothing.

### Rerun of run B

Issued at 2026-10-20T23:39:02.192Z; result at 23:39:03.528Z. It overwrote run B's
`delete-counts-before-history-behaviour.log`.

```
cd <worktree>/backend && EV=<worktree>/docs/evidence/expert-fixes-2026-10-20 && { echo "# delete-counts BEFORE (behaviour): the clock-driven delete-retry tests against the unchanged product code"; echo "# the old constructor has no clock, so docs/evidence/expert-fixes-2026-10-20/delete_counts_old_code_clock_shim.py"; echo "# (loaded with -p) feeds the same clock to the OLD module's datetime.utcnow(); no product logic is changed"; echo "# branch expert-fixes at $(git rev-parse --short HEAD); git diff --stat -- backend/app: '$(git diff --stat -- app | tail -1)'; run at $(date -u +%Y-%m-%dT%H:%M:%SZ)"; } > $EV/delete-counts-before-history-behaviour.log && env PYTHONPATH=$EV POSTGRES_DB=soccer_predictions_test REDIS_HOST=127.0.0.1 REDIS_PORT=6390 SYNC_SCHEDULER_ENABLED=false EMAIL_ENABLED=false LEASE_TEST_REDIS_URL=redis://127.0.0.1:6390/9 RACE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5440/forecast_race_test ./venv311/bin/python -m pytest tests/services/test_expert_history.py -k "delete_retried or redelete or first_delete_after_kickoff or without_a_clock" -p delete_counts_old_code_clock_shim -q -p no:cacheprovider -o addopts="" -rfEs >> $EV/delete-counts-before-history-behaviour.log 2>&1; echo "exit=$?" | tee -a $EV/delete-counts-before-history-behaviour.log; grep -E "^(FAILED|ERROR|SKIPPED)|^E  |passed|failed" $EV/delete-counts-before-history-behaviour.log
```

```
exit=1
E       AssertionError: a win withdrawn before kickoff was scored (PredictionOutcome.WON) after a retried delete
E       assert <app.models.predictions.PredictionResult object at 0x10ee51610> is None
E       assert datetime.datetime(2025, 12, 24, 14, 0) == datetime.datetime(2025, 12, 24, 10, 0)
E        +  where datetime.datetime(2025, 12, 24, 14, 0) = <app.models.predictions.Prediction object at 0x10eded3d0>.deleted_at
E       assert datetime.datetime(2026, 1, 23, 15, 0) == (datetime.datetime(2025, 12, 24, 15, 0) + datetime.timedelta(seconds=10800))
E        +  where datetime.datetime(2026, 1, 23, 15, 0) = <app.models.predictions.Prediction object at 0x10f332290>.deleted_at
E        +  and   datetime.timedelta(seconds=10800) = timedelta(hours=3)
FAILED tests/services/test_expert_history.py::test_a_delete_retried_after_kickoff_keeps_the_prematch_withdrawal
FAILED tests/services/test_expert_history.py::test_a_delete_retried_before_kickoff_keeps_the_first_deletion_time
FAILED tests/services/test_expert_history.py::test_a_first_delete_after_kickoff_is_still_scored_and_a_retry_changes_nothing
3 failed, 2 passed, 38 deselected, 18 warnings in 0.32s
```

The committed logs in `549c072c` come from these two reruns. Their headers read
`run at 2026-10-20T23:38:52Z` and `run at 2026-10-20T23:39:02Z`, both
`branch expert-fixes at 6cfb1c22`.

**What the reruns do and do not show.**
- **They show** the tests' outcomes on the unchanged product code when the settings are applied.
  That is what the before-evidence needs.
- **They do not show** what the two misconfigured processes connected to. A rerun cannot show
  that, so the reruns are not evidence that the earlier runs were harmless.

## 1. Directly observed (recorded in the transcript)

- **The call.** One Bash call (23:38:14.290Z–23:38:17.758Z) ran run A as `env $ENVV ...` and run B
  as `env PYTHONPATH=$EV $ENVV ...`. `ENVV` held all seven settings in one quoted string.
- **Run A's output.** Run A printed `18 failed, 4 passed, 1 skipped`. Its log named the skip as
  `RACE_TEST_DATABASE_URL is not set`, although `RACE_TEST_DATABASE_URL` was inside `$ENVV`. So
  that setting did not take effect.
- **Run A against the runs either side.** The correctly configured run just before it (23:37:38)
  and the corrected rerun (23:38:52) both printed `19 failed, 4 passed`, with the race test among
  the failures.
- **Run B's output.** Run B printed `3 failed, 2 passed`. Its E lines are the same as the corrected
  rerun's, apart from object addresses. No TypeError appears. Without the shim the old
  constructor raised one (the 23:37:14 run), so the shim was active: `PYTHONPATH=$EV` was a
  separate word and took effect.
- **What the agent did next.** It read the Redis-related code (23:38:28–38). It reran both runs
  with literal settings (23:38:52, 23:39:02) and disclosed the slip in its report, saying it could
  not prove that nothing reached live.
- **Listeners.** Earlier the same agent's `lsof` and `docker ps` output (23:29:14Z) showed the live
  Redis container on `*:6379` and the live PostgreSQL container on `*:5432` listening, together
  with the throwaway test Redis (127.0.0.1:6390) and race PostgreSQL (127.0.0.1:5440).
- **Nothing on the server side.** No transcript records a connection capture, a Redis `MONITOR`,
  `CLIENT LIST`, `INFO` or keyspace check, or a PostgreSQL server log for those three seconds.

## 2. Supported by code inspection (inference, not observation)

Read on 2026-10-21. The product code is read at `6cfb1c22`, the code that ran. The test files are
read at `549c072c`, which matches what ran except for one test, added at 23:41:33Z, after the
slip.

**What zsh did.**
- zsh does not split an unquoted `$ENVV`, so `env` received one argument.
- It set `POSTGRES_DB` to the whole 234-character string, beginning
  `soccer_predictions_test REDIS_HOST=127.0.0.1 ...`, and set none of the other six.
- `zsh -c 'V="A=1 B=2"; env -i /usr/bin/env $V'` prints the single line `A=1 B=2`. That is a
  reproduction made on 2026-10-21, not a record from the time.

**Where the other settings came from.**
- `backend/app/core/config.py` reads `env_file = ".env"` from the working directory, `backend/`.
- In this worktree `backend/.env` is a symbolic link to the live checkout's `backend/.env`. The
  link was created 2026-10-20 19:02 EDT; the target was last modified 2026-10-11.
- Read on 2026-10-21, that file sets `REDIS_HOST="localhost"`, `REDIS_PORT=6379`, `REDIS_DB=0`,
  `POSTGRES_SERVER="localhost"`, `POSTGRES_PORT=5432`, `POSTGRES_DB="soccer_predictions"` and
  `EMAIL_ENABLED=true`. It has no `REDIS_URL`, `DATABASE_URL` or `SYNC_SCHEDULER_ENABLED`.
- The code defaults are the same for Redis: `REDIS_HOST="localhost"`, `REDIS_PORT=6379`,
  `REDIS_DB_SESSIONS..RATE_LIMIT = 0..5`. `SYNC_SCHEDULER_ENABLED` defaults to `True`.

**What the two processes would have resolved.** This assumes the agent's shell exported none of
these variables, which was not recorded:
- `REDIS_URL=redis://localhost:6379/0` and Redis databases 0–5. That is the live Redis
  container's published port.
- A settings `DATABASE_URL` on `localhost:5432` whose database name is the whole 234-character
  string. No such database exists.
- The scheduler and email on, and no `LEASE_TEST_REDIS_URL` or `RACE_TEST_DATABASE_URL`.

**What runs at import.**
- `tests/conftest.py` imports `app.main`.
- The module-level `CacheService` objects in `app/services/cache.py` (lines 291–295) build Redis
  clients through `app/core/redis.py` `get_redis_client`, which calls `redis.from_url(...)`.
- `app/db/session.py` calls `create_engine`.
- redis-py and SQLAlchemy construct these lazily: neither connects until a command or a query is
  issued.

**The app lifespan was not entered.** `app/main.py` `lifespan` is where `init_db()` runs against
the settings database and where `start_background_scheduler()` starts the scheduler. The `client`
fixtures of `tests/api/test_expert_manage_db.py` and `tests/api/test_expert_endpoints.py` yield
`TestClient(app)` without `with`, so the lifespan does not run. The history tests use no client.

**Databases.**
- `test_expert_manage_db.py` and `test_expert_history.py` build their own engine from the
  `TEST_DATABASE_URL` default: `soccer_predictions_test` on `localhost:5432`, with the password
  masked here. `POSTGRES_DB` does not affect it.
- Both `get_db` callables (`app.core.deps.get_db` and `app.db.session.get_db`) are overridden in
  both endpoint modules; `test_expert_endpoints.py` uses a `MagicMock` session.
- `soccer_predictions_test` is on the same PostgreSQL server (:5432) as the live database. Every
  run, misconfigured or not, connected to that server for the test database.

**Redis on the paths that ran.**
- The tests override `get_current_expert_user`, and in `test_expert_endpoints.py` also
  `get_current_verified_expert_user`. The Redis calls in `app/core/deps.py` (the refresh-token
  blacklist) are not on these paths.
- `ExpertPredictionService` (`app/services/expert_prediction.py`) builds a `PredictionCacheService`
  but does not call it on these paths. Its `_invalidate_match_cache` only logs
  `Would invalidate cache key: ...`.
- No email path is exercised.

**The race module.** `tests/services/test_expert_delete_race_pg.py` has a module-level `skipif` on
`RACE_TEST_DATABASE_URL`. In run A the test therefore skipped before its engine fixture ran.

**What this supports.** The code reading supports this: the two processes issued no Redis command,
to live Redis or any other, and opened no connection to the settings database. Their only
behavioural difference was the skipped race test. This is an inference from the code. Nothing
from the time confirms it.

## 3. Cannot be established

- **Connections.** No capture of network connections or sockets exists for 23:38:14–23:38:17Z:
  no `tcpdump`, `lsof` or `netstat`. Whether either process opened a TCP connection to :6379, or
  to the settings database on :5432, is unobserved.
- **The servers' side.** There is no Redis `MONITOR`, `SLOWLOG`, `CLIENT LIST`, `INFO` counters or
  keyspace snapshot of :6379 from before or after. There is no PostgreSQL connection or
  authentication log for :5432, and no container logs were checked.
- **The live snapshots.** `live-before.txt` was taken at 23:03Z, before the slip, and
  `live-after.txt` at 07:51Z. They record the live process, refs, container start times and
  provider counters. They show that live was not restarted. They do not record connections,
  commands or key changes on live Redis or the live database between those times.
- **The logs.** Both misconfigured log files were overwritten. Run A's tracebacks, warnings and
  header, and its FAILED lines 745–750, were never displayed. That those six lines were FAILED
  names is inferred from the line numbers.
- **The environment at the time.** The environment the agent's shell inherited at 23:38Z is not
  recorded. The content of `backend/.env` at that moment is inferred from its present content and
  its 2026-10-11 modification time.
- **Library behaviour.** That redis-py and SQLAlchemy connect lazily is assumed from their
  documented behaviour and an offline check, not observed in these processes.
- **Other sessions.** Activity by other sessions on live Redis or the database in the same minute
  cannot be told apart.
- **Checking now.** Checking live Redis keys or live rows for changes at that time was not done. It
  would need the owner's go-ahead for read-only access to live Redis on :6379 and the live
  database.

## 4. Other runs: the audit

**The method.** Every Bash and Monitor command that invokes pytest was read in all 11 agents of
the three rounds that ran backend tests:
- the implementation round, `wf_041b039e-bb4`;
- the review-fix round, `wf_ca7938ae-498`;
- the final verification round, `wf_3c8b14f2-083`.

Each invocation was checked for literal `POSTGRES_DB`, `REDIS_HOST` and `REDIS_PORT` on its own
command line.

**The result.**
- **No other misconfigured run.** The two runs above are the only ones that used `env $VAR`, a
  variable-led command or `eval`.
- **`impl:backend-delete-metrics`.** Its other 13 invocations were literal; two of them are loops
  of 20.
- **`impl:backend-revisions-author-profile`.** Its 8 runs went through a scratchpad wrapper,
  `runpy.sh`, whose pytest line carries the settings literally.
- **`fix:backend` and `verify:suites`.** `fix:backend` made 9 runs and `verify:suites` 1, all with
  a literal prefix that includes `TEST_DATABASE_URL`. The `verify:suites` hit at 07:06:36Z is
  header text, not a run.
- **The other seven agents** ran Playwright only.

**A different slip, also found.**
- `fix:backend`'s first before-run (2026-10-21T05:42:49Z) passed `TEST_DATABASE_URL` literally but
  without its password. Its 17 database-backed tests skipped with `fe_sendauth: no password
  supplied`: 4 failed, 1 passed, 17 skipped.
- Its Redis and `POSTGRES_DB` settings were literal and correct.
- It was superseded at 05:43:14Z, and the reason is written in that evidence header.

**Outside those three rounds.**
- **The mapping and review rounds** (`wf_e741f8d2-a80`, `wf_1d18bc54-971`) issued no pytest
  command.
- **The parent session** made one pytest invocation after 2026-10-20 19:00Z (23:22:58Z), with the
  settings literal.
- **The later preflight-guard and bypass rounds** (`wf_da1c1f55-1cd`) use the `env $V` form only
  in two places:
  - in the deliberate replay of this slip, which runs inside the tripwire harness that records and
    blocks every connection (`guard-after-backend-refusals.log`, case 1);
  - in log-header text.
- **Since then.** The isolation preflight committed in `4f0a2388` and `b6c35b28` refuses this
  environment before anything connects.

## 5. Corrections made on 2026-10-21

- **`HANDOFF.md`.** The paragraph "One environment slip, disclosed" is rewritten. It separates what
  was observed, what the code supports and what cannot be established, and links here. It no
  longer says nothing reached live.
- **`FINAL-RUNS.md`.** The note "the live database and live Redis were not touched", which is about
  the final runs, is narrowed to what it rests on: settings passed literally, and no connection
  capture. It points here for the slip.
- **No log was edited.** The committed logs from the reruns are unchanged. No log's header or
  footer made the "nothing reached live" claim, so no log needed a correction note.
- **No history was rewritten.** The earlier wording was introduced in `b8b5f8bc`.
