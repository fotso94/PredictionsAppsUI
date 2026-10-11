# Settlement proven on the isolated copy, 2026-10-10

The five recorded slips on the QA account, settled by the application's own read path against a
copy of the live database taken that afternoon — and read a second time to show the second read
changes nothing. The live database was not touched: the same read against the live backend is the
one write still owed, and it waits for the owner's go-ahead (`../README.md`, step 5).

## What was run

- **The copy.** `scripts/local-servers.sh reset-e2e-db` recreated `soccer_predictions_e2e` from
  the live database at 2026-10-10 17:14:01 UTC: 392 matches, the QA account's 5 recorded slips, all
  `pending`, and their 10 legs' fixtures `FINISHED` with regulation-time results that reached the
  live database through Live Score on 9 October.
- **The backend.** The isolated one on :8001, serving that database (its `/health` said so, and the
  script refuses any other), commit `16b328b`, scheduler off, every provider credential blank.
- **The reads.** `prove_settlement_isolated.py` (here) signed in as the QA account — the
  repository's own local fixture, `frontend/e2e/support/qa-account.ts` — and called
  `GET /api/v1/me/slips`, which settles on read, then called it again, then read each slip singly.
  Between the calls it snapshotted both slip tables and every table's row count, reading with
  `default_transaction_read_only=on`.

## What it showed

| Slip | Legs | Before | After the first read | After the second read |
|---|---|---|---|---|
| `18724af2` (recorded 2026-10-05 06:08) | Cyprus v Latvia home (2-1), France v Belgium over 0.5 (4-1) | pending | **won**, settled 17:19:44 | won, unchanged |
| `63778783` (2026-10-07 03:27) | Dortmund v Werder Bremen home (2-2), Lens v Lyon over 0.5 (2-1) | pending | **lost** (home leg lost, totals leg won) | lost, unchanged |
| `5d918730` (2026-10-07 03:59) | the same two legs | pending | **lost** | lost, unchanged |
| `106adf89` (2026-10-07 04:06) | the same two legs | pending | **lost** | lost, unchanged |
| `4e0a43fa` (2026-10-07 04:34) | the same two legs | pending | **lost** | lost, unchanged |

Every leg carries its rule and its evidence in `settlement` (`regulation-time result`, actual
`2-2`, actual outcome `draw`; `regulation-time goals against the 0.5 line`, goals 3), as
`response-first-read.json` shows.

**The second read changed nothing.** `summary.json`:

- `second_read_changed_rows: false` — the `md5` over every slip row and every leg row is the same
  after the second read as after the first;
- `updated_at_moved_on_second_read: []` and `second_read_changed_any_table: false` — no timestamp
  moved and no table in the five application schemas gained or lost a row;
- `single_reads_match_list: true` — each slip read on its own is byte-identical to its entry in
  the list;
- `first_response_equals_second_response: false`, and only in the **order** of the five slips: the
  list is ordered by `updated_at` descending, the first read listed them in their pre-settlement
  order (by `recorded_at`) before stamping them, and the second by the five settlement stamps,
  written microseconds apart. Sorted by id the two responses are equal.

The rule that makes this so is in `backend/app/services/slip_settlement.py`: a leg already
`won`, `lost` or `void` is never reopened, and a slip's `settled_at` is set once.

## Files

| File | What |
|---|---|
| `before.json` | both slip tables and every table's row count before any read |
| `after-first-read.json`, `after-second-read.json` | the same after each read |
| `response-first-read.json`, `response-second-read.json` | the API's two answers |
| `summary.json` | the comparisons above |
| `prove_settlement_isolated.py` | the script; it prints no token and refuses a backend not serving the e2e clone |

## What this does and does not show

It shows the settlement rule and its idempotency on these five slips and this data. It did not
touch the live database; when it was written (about 17:30 UTC) the five live slips still read
`pending` with `settled_at` null, and the journey proof of the same afternoon
(`../2026-10-10T1716Z.json`) read each leg as `pending: owner read` with a final dry-run state that
matches this table. **Added 2026-10-11:** at 18:07:05 UTC that evening the five live slips settled
with exactly these outcomes, through the live browser suite's sign-in as the QA account
(`../live-settlement-2026-10-10.md`) — so this copy's result was confirmed on the live rows, by a
read nobody had authorized.
