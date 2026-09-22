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
    It never polls for ever. A fixture still unsettled after `STALE_SWEEP_MAX_ATTEMPTS` attempts,
    or older than `STALE_SWEEP_MAX_AGE`, is given up on: `match_metadata.recovery` records
    `gave_up_at` and `gave_up_reason`, and the sweep never selects it again. Giving up changes
    nothing about the match itself. A score nobody reported is not a score, so the row keeps the
    status it has and says, on the row, why nobody is asking any more.

WHAT COUNTS AS AN ATTEMPT
    Only a pass where the provider was asked, answered, and had no result for the fixture -- that
    alone is evidence there is nothing to get, and "no result after N attempts" is a sentence
    about evidence. A pass whose providers all failed, and a pass served out of the cache, are
    recorded and reported but spend no attempt: neither put the question. See
    `RecoveryOutcome` in app/services/match_registry.py for the four outcomes and
    `classify_recovery_outcome` for how a day's `SyncMeta` decides between them. The per-pass
    report below breaks the fixtures down by outcome, so a provider that is down reads
    differently from a provider that has nothing to say.

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
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.predictions import Match  # noqa: E402
from app.services.match_data_service import MatchDataService, SyncMeta  # noqa: E402
from app.services.match_registry import (  # noqa: E402
    STALE_SWEEP_MAX_DAYS, MatchRegistry, RecoveryOutcome, classify_recovery_outcome, is_settled,
)
from app.services.providers.livescore_api import MAX_PAGES  # noqa: E402

#: How each outcome reads in the per-pass report, and what the reader is to make of it. The two
#: that spend nothing say so in as many words: a reader who cannot tell a dead provider from a
#: silent one reads "no result after 3 attempts" as a fact about the fixture when it may be a
#: fact about the outage, and the whole worth of the counter is that the two are different.
OUTCOME_REPORT = {
    RecoveryOutcome.RECOVERED: ("recovered", "came back settled; nothing left to retry"),
    RecoveryOutcome.FRESH_UNANSWERED: ("fresh, no result", "the provider was asked and had none: ATTEMPT SPENT"),
    RecoveryOutcome.CACHED: ("cached", "the day came from the store; this pass never asked, no attempt"),
    RecoveryOutcome.PROVIDER_ERROR: ("provider error", "the question was never put; no attempt"),
}


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
    """One stranded fixture, with every counter that bears on whether it is given up on."""
    state = registry.recovery_state(match)
    counts = [f"attempts={state.get('attempts', 0)}"]
    for key, label in (("provider_errors", "errors"), ("cached_passes", "cached")):
        if state.get(key):
            counts.append(f"{label}={state[key]}")
    parts = [f"    {match.id}  {match.match_date}  {match.status.value:<10}", " ".join(counts)]
    if state.get("last_outcome"):
        detail = state.get("last_outcome_detail")
        parts.append(f"{state['last_outcome']}" + (f" ({detail})" if detail else ""))
    if state.get("gave_up_at"):
        parts.append(f"GAVE UP: {state['gave_up_reason']}")
    return "  ".join(parts)


def _evidence_rank(meta: SyncMeta) -> int:
    """How much a day's results call can tell us about a fixture, most first.

    Only the ordering matters, and it is the same ordering `classify_recovery_outcome` reads the
    meta by: a provider asked and answered during this pass is evidence, a stored answer is not
    new, and a call that never reached anybody is not evidence at all.
    """
    if meta.source == "provider":
        return 2
    if meta.source in ("cache", "stale-cache"):
        return 1
    return 0


def sweep(service: MatchDataService, days: List[date], stranded: List[Match],
          now: datetime) -> Dict[RecoveryOutcome, List[Tuple[Match, str]]]:
    """
    Reopen each day, then record for each stranded fixture what that day's answer actually was.

    The outcome is decided per DAY by the `SyncMeta` `_sync_results` fills, and per FIXTURE by
    whether that fixture is settled now and was not before. Both halves are needed: the meta
    alone cannot say which fixture moved, and the status alone cannot say whether anyone asked --
    a fixture already FINISHED before the pass is not something this sweep recovered.

    The day each fixture is looked up under is read BEFORE any sync runs, because the sync can
    change it: `_sync_results` stores the provider's answer through `MatchRegistry._apply_fixture`,
    which moves the stored kickoff to the provider's. A fixture the provider rescheduled across a
    UTC midnight would otherwise be looked up under a day this pass never reopened, take no
    outcome at all, and be reported as untouched -- and when that same answer also settled it,
    the thrown-away outcome is a recovery.

    Each day gets its own `SyncMeta` and only `_sync_results` writes to it, so `source` here
    belongs to the results call and to nothing else. Inside `sync_day` the live and forward calls
    share one meta and overwrite each other's `source`, which is why this does not use it.
    """
    registry = service.registry
    settled_before = {m.id: is_settled(m.status) for m in stranded}
    swept_under = {m.id: m.match_date.date() for m in stranded}

    metas: Dict[date, SyncMeta] = {}
    for day in days:
        meta = metas[day] = SyncMeta()
        service._sync_results(day, meta)
        print(f"  {day}: source={meta.source} polled={meta.results_polled} "
              f"seen={meta.fixtures_seen} stored={meta.fixtures_stored} errors={meta.errors}")

    by_outcome: Dict[RecoveryOutcome, List[Tuple[Match, str]]] = {o: [] for o in RecoveryOutcome}
    for match in stranded:
        service.db.refresh(match)
        # TWO DAYS CAN HOLD THIS FIXTURE'S ANSWER, because a results call may MOVE it: the
        # provider's kickoff wins, and `_apply_fixture` will re-date a fixture within its
        # reschedule window. So a fixture swept under Monday can be sitting on Tuesday by the time
        # we look, and Tuesday's answer is the one that spoke about it. Reading only the day it
        # started on would file a fresh answer that moved it under whatever Monday happened to be
        # - a cache hit, or an outage - and spend no attempt on evidence we actually have.
        #
        # Both days are consulted and the strongest evidence wins, because the outcomes are
        # ordered by how much they tell us: a fresh answer beats a cached one, and a cached one
        # beats a provider that never spoke.
        candidates = [metas[d] for d in {swept_under[match.id], match.match_date.date()} if d in metas]
        if not candidates:  # this pass reopened no day this fixture has sat on
            continue
        meta = max(candidates, key=_evidence_rank)
        outcome, detail = classify_recovery_outcome(
            meta, settled_before=settled_before[match.id], settled_now=is_settled(match.status))
        registry.record_recovery_outcome(match, outcome, detail, now)
        by_outcome[outcome].append((match, detail))
    service.db.commit()
    return by_outcome


def report_outcomes(by_outcome: Dict[RecoveryOutcome, List[Tuple[Match, str]]], registry: MatchRegistry) -> None:
    """The pass in four numbers, then the fixtures behind each, so the numbers can be checked."""
    print("\noutcomes this pass:")
    for outcome in RecoveryOutcome:
        label, meaning = OUTCOME_REPORT[outcome]
        print(f"  {label:<16} {len(by_outcome[outcome]):>3}   {meaning}")

    for outcome in RecoveryOutcome:
        rows = by_outcome[outcome]
        if not rows:
            continue
        print(f"\n{OUTCOME_REPORT[outcome][0]}:")
        for match, _ in rows:
            print(describe(match, registry))


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
    report_outcomes(sweep(service, days, stranded, now), registry)

    print(f"\nbudget {provider} after:  {budget_now(provider)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
