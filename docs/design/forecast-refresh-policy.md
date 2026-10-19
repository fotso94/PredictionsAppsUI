# Forecast refresh policy — design for the isolated round of 2026-10-18

Branch `policy-round`, worktree `PredictionsAppsUI-policy-round`, from `310470a9`. Nothing here is
deployed; the live scheduler keeps running the committed rule until the owner approves a rollout.

## What is wrong with the committed rule (noon gate + 22 h interval)

- "Noon" is an inference from one week of fetch timing (same-day runs were obtained at 12:xx and
  18:xx UTC, never at 00:xx), not anything the provider promises. It must not be described as a
  publication guarantee.
- Elapsed-time eligibility, a time-of-day gate and a six-hour cadence that drifts produce
  missed-day gaps. Regression scenario: a competition refreshed at 20:01 on day D (a late-evening
  success) is not eligible at the noon pass on D+1 (16 h elapsed), still not eligible at an evening
  pass at 17:59 (21 h 58 min), and the next pass is gated until noon on D+2: a 40-hour gap.
- "Spare requests become second refreshes" was asserted, not designed.

## The policy: one refresh slot per competition per UTC day

State per competition, in Redis beside the existing keys: `forecast:refresh:{provider}:{key}` =
`{"day": "YYYY-MM-DD", "fetched_at", "model_run_at", "outcome"}` where `outcome` is one of
`same-day-run`, `older-run`, `empty`, `dormant`, `failed`. The UTC day is the slot; elapsed time is
not consulted for eligibility.

A competition K is **eligible for an automatic paid fetch** at time `now` (UTC day D) when all of:

1. **Active.** Dormancy is established only by sufficient calendar evidence (below); without it K
   is treated as active.
2. **Unfetched for D**, or fetched for D with `outcome = older-run` and no re-check made yet for D
   (one re-check per competition per day, paid from spare allowance only).
3. **Publication hour reached.** `now.hour >= earliest_publication_hour`, an **observed** value:
   the earliest UTC hour at which any fetch in the last 14 days obtained a same-day run, kept in
   `forecast:publication:{provider}` from every fetch's `model_run_at` against its own clock; 12
   until there is an observation. A fetch that returns an older run records "not yet published at
   H" for D and does not move the hour. Nothing guarantees newer predictions: the policy only
   avoids asking before any evidence says the run exists.

Morning kick-offs need no rule of their own: a match that kicks off before the publication hour
is served by the previous day's fetch, which is the latest run that exists; the day's fetch after
publication serves the matches still to come.

## Budget allocation within the UTC-day ceiling

The ceiling stays at 8 per UTC day (`GAMEFORECAST_DAILY_REQUEST_BUDGET`); the provider's own window
(observed reset 03:12 UTC) is a separate constraint already read from its headers. While the
publication hour stays at 12, every automatic fetch of a UTC day falls inside one provider window.
Nothing in the code keeps the observed hour after the provider's reset: a manual refresh between
00:00 and 03:12 UTC that found the day's run would bring the hour forward to before the reset, and
automatic fetches made then would count against the provider's previous window. The provider's
remaining count, read from its headers, still refuses a request before it leaves, so the
consequence is a refused fetch rather than an overage. A lower bound at the observed reset is a
possible follow-up; it is not on this branch.

Priority order for a pass, each step stopping when the remaining allowance cannot pay a full turn:

1. Active competitions unfetched for D, nearest kick-off first.
2. Re-checks: competitions whose fetch for D returned an older run, nearest kick-off first, at
   most one per competition per day — this is what spare requests buy.
3. Nothing else. Spare requests left after 1 and 2 are the margin and stay unspent: the provider
   publishes one dated run a day, so a second fetch of a same-day-fresh competition buys price
   changes, not fresher probabilities.

A turn that cannot be paid for in full defers the competition (recorded as `deferred`) and the pass
moves on to the next competition the allowance can serve; a dormant competition costs nothing and
is decided before any affordability check, so it can never block an affordable active one.

## Dormancy evidence

A competition is **dormant** for the window only when, in the same turn, the fixture sync for it
ran, answered from the provider or from a cache that is not stale, reported no error, covered the
whole window it was asked for, and the database then holds no fixture for the competition inside
the window. Any failed, disabled, stale or incomplete discovery leaves the competition active. The
fixture sync keeps running on every turn regardless, so a dormant competition resumes by itself the
day its calendar lists a match.

## Shared with every automatic path

`RefreshPolicy` is one object: `ensure_synced` consults it for eligibility and order, the
scheduler's cost estimate consults it for the keys a pass would fetch and re-check (priced with
discovery and pagination through `request_cost`, capped by the budget), and the page-load and
admin refresh paths share the same `RequestBudget`. A forced sync bypasses eligibility, never the
budget. Cache-only re-attachment runs on every pass, before and after fetching, and never consults
the policy or the budget.

## Outages, restarts, concurrency

State lives in Redis, so a restart neither repeats nor forgets a day's fetch. A pass that fails
leaves the slot unfetched; the next pass of the same day retries under the same budget and the
existing pause rules. The sync lock stays as it is (one worker spends; the others only re-attach).

## Compatibility switch

`GAMEFORECAST_REFRESH_POLICY = "daily-slot" | "elapsed-interval"`. `elapsed-interval` is the
committed behaviour (noon gate + 22 h interval) kept for the replay comparison and for rollback;
`daily-slot` is this policy. The rollout decides the default on the live service; this branch
defaults to `daily-slot` for its tests and replays.
