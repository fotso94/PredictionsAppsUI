# The five live slips settled on 2026-10-10 at 18:07:05 UTC — by a browser test, not by an authorized read

Found by the reviewer on 2026-10-11, against the account given the same evening that "the live
database was not written to". That account was wrong, and this page records what happened.

## What the database says

All five recorded slips on the QA account settled in one transaction:

| Slip | State | `settled_at` (UTC) | `updated_at` (UTC) |
|---|---|---|---|
| `18724af2` | won | 2026-10-10 18:07:05.629277 | 18:07:05.640541 |
| `63778783` | lost | 18:07:05.629277 | 18:07:05.640542 |
| `5d918730` | lost | 18:07:05.629277 | 18:07:05.640542 |
| `106adf89` | lost | 18:07:05.629277 | 18:07:05.640540 |
| `4e0a43fa` | lost | 18:07:05.629277 | 18:07:05.640541 |

All ten legs carry the same `settled_at`. The outcomes are exactly the dry run's and exactly the
isolated copy's (`settlement-isolated-2026-10-10/`): the read-only journey proof of
2026-10-11T0126Z reads every leg and every slip `proven` — stored state equal to the rule's.

## What the backend log says

`.local-run/backend.log` (SQL echo, local time UTC−4), the process started 17:40:28 UTC on
`dd1c857`; every parameter value is withheld by the echo itself:

```
14:07:05,022  UPDATE users.users SET last_login_at=…, updated_at=… WHERE …     ← the QA account signs in (API)
14:07:05,025  COMMIT
14:07:05,511  UPDATE users.users SET last_login_at=…, updated_at=… WHERE …     ← and signs in again (browser)
14:07:05,515  COMMIT
14:07:05,627  BEGIN (implicit)
14:07:05,630  SELECT users.selection_slips.user_id, users.selection_slips.name, …   ← GET /api/v1/me/slips
14:07:05,640  UPDATE users.selection_slips SET state=…, settled_at=…, updated_at=… WHERE …   ×5
14:07:05,643  UPDATE users.selection_slip_legs SET state=…, settled_at=…, settlement=… WHERE …   ×10
14:07:05,647  COMMIT
```

Sign-in, then 116 ms later the slip read, then the settlement, then the commit.

## Which test

The six-suite run `2026-10-10T1740Z-dd1c857` ran its live project from 18:06:46.948 UTC
(`playwright-live.junit.xml`). Its first spec, `detail-refresh.spec.ts`, is anonymous and took
17.5 s; the next, `expert-composer.spec.ts`, signs in as the QA account, and its first test —
"[live] an expert reaches the form without ever seeing a match id" — ran from +17.5 s to +19.3 s,
that is 18:07:04.4 to 18:07:06.2 UTC. The settlement at 18:07:05.6 falls inside it. Attribution is
by the clock, to the second; the backend writes no access log that would name the request.

## The mechanism

A signed-in reader's slips live on the server, and the slip dock loads them when the reader signs
in (`frontend/src/services/slips.service.ts`, `GET /api/v1/me/slips`). That read settles every
pending leg whose fixture has a result and commits (`backend/app/api/v1/endpoints/slips.py`). So
any browser test that signs in as the QA account against the live backend settles that account's
slips as a side effect of signing in — no test has to open the slip history for the write to
happen. Until 2026-10-11 six of the eight live specs signed in that way.

## What follows

- The first settlement on live data has happened, through the application's own read path, with
  the outcomes the rule predicts. It was not the deliberately controlled step described in
  `README.md` step 5, and that step is rewritten accordingly.
- Every later live-project run that evening (18:3x, 23:5x, 00:3x, 01:0x UTC) signed in again;
  `updated_at` did not move, which is the repeat-read stability the isolated run showed, on the
  live rows.
- Signed-in browser journeys now run only against the isolated pair (`e2e/live-isolated/`); the
  `live` project keeps the two anonymous specs. Recorded in `docs/isolated-dev-environment.md`.
