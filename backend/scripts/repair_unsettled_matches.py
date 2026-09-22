#!/usr/bin/env python
"""
Re-ask the provider about fixtures that no refresh reaches any more, within a hard budget.

WHY THIS EXISTS
    A fixture whose final score never arrived falls out of every refresh. The live poll only
    considers matches dated today; the results task only looks back SYNC_RESULTS_LOOKBACK_DAYS
    days. A row left unfinished older than that is never asked about again, so it sits on the site
    reading LIVE for ever -- which is what Everton v Ipswich did for two days at minute 62. That is
    a defect in its own right, independent of the duplicate row that caused it.

WHAT IT DOES
    `MatchRegistry.stale_unsettled_days` picks the days behind the lookback that still hold a
    recoverable fixture, oldest first and capped, and each one is then put through the ordinary
    results path -- the same `MatchDataService._sync_results` the scheduler calls, so every
    provider request is counted and attributed like any other.

HOW IT STOPS
    It never polls for ever. Each pass counts an attempt against every fixture it asked about, and
    a fixture that is still unsettled after `STALE_SWEEP_MAX_ATTEMPTS` passes, or older than
    `STALE_SWEEP_MAX_AGE`, is given up on: `match_metadata.recovery` records `gave_up_at` and
    `gave_up_reason`, and the sweep never selects it again. Giving up changes nothing about the
    match itself. A score nobody reported is not a score, so the row keeps the status it has and
    says, on the row, why nobody is asking any more.

USAGE
    ./venv/bin/python scripts/repair_unsettled_matches.py                    # report, no requests
    ./venv/bin/python scripts/repair_unsettled_matches.py --apply            # ask the provider
    ./venv/bin/python scripts/repair_unsettled_matches.py --database-url ... # a restored copy
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.match_data_service import MatchDataService, SyncMeta  # noqa: E402
from app.services.match_registry import STALE_SWEEP_MAX_DAYS, MatchRegistry  # noqa: E402
from app.services.providers.livescore_api import MAX_PAGES  # noqa: E402


def redacted(url: str) -> str:
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url)


def budget_now(provider: str) -> str:
    """The provider's own counter for today, read straight from where the app keeps it."""
    try:
        from app.services.providers.budget import budget_key
        from app.core.redis import get_rate_limit_redis
        value = get_rate_limit_redis().get(budget_key(provider))
        return (value.decode() if isinstance(value, bytes) else value) or "0"
    except Exception as exc:  # the report must never fail the run it is reporting on
        return f"unavailable ({exc})"


def describe(match, registry: MatchRegistry) -> str:
    state = registry.recovery_state(match)
    gave_up = f" GAVE UP: {state['gave_up_reason']}" if state.get("gave_up_at") else ""
    return (f"    {match.id}  {match.match_date}  {match.status.value:<10} "
            f"attempts={state.get('attempts', 0)}{gave_up}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="make the provider requests (default: report the plan and its cost)")
    parser.add_argument("--database-url", default=None, help="database to work on")
    parser.add_argument("--max-days", type=int, default=STALE_SWEEP_MAX_DAYS,
                        help=f"days behind the lookback to reopen (default {STALE_SWEEP_MAX_DAYS})")
    args = parser.parse_args()

    url = args.database_url or settings.DATABASE_URL
    db = sessionmaker(autocommit=False, autoflush=False, bind=create_engine(url, echo=False))()
    service = MatchDataService(db)
    registry = service.registry
    now = service.now
    provider = settings.DATA_PROVIDER

    print(f"database:  {redacted(str(url))}")
    print(f"now:       {now.isoformat()}")
    print(f"lookback:  {settings.SYNC_RESULTS_LOOKBACK_DAYS} day(s); the sweep reopens what is behind it")
    print(f"mode:      {'APPLY - provider requests will be made' if args.apply else 'report only, no request'}")
    # Resolving the covered competitions can CREATE a canonical league row for a key this database
    # does not hold yet (MatchDataService.league_ids -> competitions -> ensure_canonical_league),
    # and it does so before the report/apply branch below. "No provider request" is therefore not
    # the same promise as "no write", and saying only the first would let someone run this against
    # a database they were protecting.
    print("note:      resolving competitions may add a canonical league row if one is missing;")
    print("           no other write happens without --apply")
    print(f"budget {provider} before: {budget_now(provider)}\n")

    league_ids = service.league_ids()
    days = registry.stale_unsettled_days(now, settings.SYNC_RESULTS_LOOKBACK_DAYS,
                                         league_ids=league_ids, max_days=args.max_days)
    if not days:
        print("no stranded fixture behind the lookback; nothing to sweep")
        print(f"budget {provider} after:  {budget_now(provider)}")
        return 0

    cutoff = now - timedelta(days=max(int(settings.SYNC_RESULTS_LOOKBACK_DAYS), 0))
    stranded = [m for m in registry.unsettled_before(cutoff, league_ids, now=now) if m.match_date.date() in days]
    print(f"days to reopen: {[d.isoformat() for d in days]}")
    # One request per competition-day is the FIRST page only. matches/history.json paginates, and
    # `_paginate` will follow up to MAX_PAGES while the provider keeps advertising another one, so
    # the honest ceiling is that figure times MAX_PAGES. Printing the first-page number alone
    # understates a real sweep by up to five times, and a cost estimate that reads low is worse
    # than none at all: it is the number someone budgets against.
    first_pages = len(service.keys) * len(days)
    print(f"estimated cost: {len(service.keys)} competition(s) x {len(days)} day(s) "
          f"= {first_pages} request(s) for the first page of each, "
          f"up to {first_pages * MAX_PAGES} if every one paginates to the {MAX_PAGES}-page cap")
    print("stranded fixtures:")
    for match in stranded:
        print(describe(match, registry))

    if not args.apply:
        print("\nreport only; no provider request was made. Re-run with --apply to sweep.")
        return 0

    print()
    for day in days:
        meta = SyncMeta()
        service._sync_results(day, meta)
        print(f"  {day}: source={meta.source} polled={meta.results_polled} "
              f"seen={meta.fixtures_seen} stored={meta.fixtures_stored} errors={meta.errors}")

    print("\nafter the sweep:")
    for match in stranded:
        db.refresh(match)
        registry.record_recovery_attempt(match, now)
        print(describe(match, registry))
    db.commit()

    print(f"\nbudget {provider} after:  {budget_now(provider)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
