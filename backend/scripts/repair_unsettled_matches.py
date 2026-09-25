#!/usr/bin/env python
"""
Re-ask the provider about fixtures that no refresh reaches any more, within a hard budget.

WHY THIS EXISTS
    A fixture whose final score never arrived falls out of every refresh. The live poll considers
    a match for 150 minutes after kickoff; the results task only looks back
    SYNC_RESULTS_LOOKBACK_DAYS days. A row left unfinished older than that is never asked about again, so it sits on the site
    reading LIVE for ever -- which is what Everton v Ipswich did for two days at minute 62. That is
    a defect in its own right, independent of the duplicate row that caused it.

WHAT IT DOES
    Exactly what the scheduler's `recover` task does, through the same
    `MatchDataService.recover_stranded`: stops recorded by a rule this installation no longer
    applies are undone, given-up fixtures a later results call has shown the archive to have moved
    past are reopened, one `matches/live.json` poll is made if anything is due, and the due
    competition-days behind the results lookback are asked about through the ordinary results path.
    Every provider request is counted and attributed like any other, answered or not.

    WHEN A FIXTURE IS ASKED ABOUT is the one retry schedule every caller shares
    (`RETRY_SCHEDULE` in app/services/match_registry.py): every pass for six hours after kickoff,
    then ever more rarely, up to 14 days. It is a budget policy. Nothing is assumed about a
    competition from its type: the archive has answered for national-team competitions, and has
    also gone days returning nothing recent for club and national ones alike
    (docs/evidence/livescore-archive-observations.json).

    NOBODY NEEDS TO RUN THIS. `SYNC_SCHEDULER_TASKS` includes `recover` and it sweeps every half
    hour on its own. This remains for a sweep somebody wants to watch happen, or to run against a
    restored copy of the database, and it is the same code either way.

HOW IT STOPS
    A fixture is given up on only straight after an ask the provider ANSWERED, when the schedule's
    next ask would fall past 14 days from kickoff. `match_metadata.recovery` then records
    `gave_up_at`, `stopped_by = "retry_budget"` and a reason saying how many times it was asked and
    when last. That is a decision to stop spending, not a finding that no result exists. Nothing
    asks about a stopped fixture on its own account afterwards: it is reopened only if a results
    request made later for another unsettled fixture in the same competition returns results dated
    on or after its date. Giving up changes nothing about the match itself; the row keeps its
    status, because a score nobody reported is not a score.

    A stop that carries no `stopped_by` was made by a rule since removed (the three-attempts rule,
    and the six-hour stop for national-team fixtures). The pass undoes it rather than attributing
    it to the retry budget, and the fixture goes back on the schedule.

WHAT COUNTS AS AN ATTEMPT
    Only an ask the provider answered without a result for the fixture. A request that went out
    and was not answered (provider error), a cached day, a due ask for which no request was made
    (deferred: an allowance refused it, or the provider was cooling down) and a fixture nothing was
    due for (not asked) are reported apart and spend no attempt: see
    `RecoveryOutcome` in app/services/match_registry.py. What the archive returned per competition
    and date is recorded too, as answered, empty, or unknown when never asked.

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
from datetime import date, datetime
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.predictions import Match  # noqa: E402
from app.services.match_data_service import MatchDataService  # noqa: E402
from app.services.match_registry import (  # noqa: E402
    STALE_SWEEP_MAX_DAYS, MatchRegistry, RecoveryOutcome, next_ask_after,
)
from app.services.providers.livescore_api import MAX_PAGES  # noqa: E402

#: How each outcome reads in the per-pass report, and what the reader is to make of it. Only one
#: of them spends anything, and each of the others says so, because "the provider had nothing" and
#: "nobody reached the provider" are different facts and only the first is evidence.
OUTCOME_REPORT = {
    RecoveryOutcome.RECOVERED: ("recovered", "came back settled; nothing left to retry"),
    RecoveryOutcome.FRESH_UNANSWERED: ("fresh, no result", "the provider answered without a result for it: ATTEMPT SPENT"),
    RecoveryOutcome.CACHED: ("cached", "the day came from the store; this pass never asked, no attempt"),
    RecoveryOutcome.PROVIDER_ERROR: ("provider error", "a request went out and nobody answered; no attempt"),
    RecoveryOutcome.DEFERRED: ("deferred", "due, but no request was made (allowance spent, or provider cooling down); still due, no attempt"),
    RecoveryOutcome.NOT_ASKED: ("not asked", "nothing was due for it this pass; no attempt"),
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


def describe(match, registry: MatchRegistry, now: datetime) -> str:
    """One stranded fixture, with every counter that bears on when it is next asked about."""
    state = registry.recovery_state(match)
    counts = [f"attempts={state.get('attempts', 0)}"]
    for key, label in (("provider_errors", "errors"), ("cached_passes", "cached"),
                       ("deferrals", "deferred")):
        if state.get(key):
            counts.append(f"{label}={state[key]}")
    parts = [f"    {match.id}  {match.match_date}  {match.status.value:<10}", " ".join(counts)]
    if state.get("last_outcome"):
        detail = state.get("last_outcome_detail")
        parts.append(f"{state['last_outcome']}" + (f" ({detail})" if detail else ""))
    if state.get("gave_up_at") and not state.get("stopped_by"):
        parts.append("STOPPED BY A REMOVED RULE (no stopped_by recorded): the pass undoes this stop "
                     "and puts the fixture back on the retry schedule")
    elif state.get("gave_up_at"):
        parts.append(f"STOPPED ASKING ({state['stopped_by']}): {state.get('gave_up_reason')}")
    else:
        upcoming = next_ask_after(match, now)
        parts.append("due now" if upcoming is None or upcoming <= now
                     else f"next ask after {upcoming.isoformat()}")
    return "  ".join(parts)


def sweep(service: MatchDataService, days: List[date], stranded: List[Match],
          now: datetime) -> Dict[str, object]:
    """One pass, through the same `MatchDataService.recover_stranded` the scheduler runs.

    The selection is passed in rather than made again, so what is swept is exactly what the plan
    above printed and priced. Everything else -- which endpoints are asked, how a day's answer is
    turned into one outcome per fixture, and what is written on the row -- belongs to
    the service, because a sweep somebody watches and a sweep nobody watches must not be two
    different sweeps.
    """
    report = service.recover_stranded(days=days, stranded=stranded)
    for day, entry in report["days"].items():
        print(f"  {day}: source={entry['source']} polled={entry['results_polled']} "
              f"seen={entry['fixtures_seen']} stored={entry['fixtures_stored']} errors={entry['errors']}")
    live = report.get("live") or {}
    print(f"  live: source={live.get('source')} polled={live.get('live_polled')} "
          f"seen={live.get('fixtures_seen')} stored={live.get('fixtures_stored')} "
          f"errors={live.get('errors')}")
    return report


def report_outcomes(report: Dict[str, object]) -> None:
    """The pass in six numbers, then the fixtures behind each, so the numbers can be checked."""
    counts = report["outcomes"]
    fixtures = report["fixtures"]
    print("\noutcomes this pass:")
    for outcome in RecoveryOutcome:
        label, meaning = OUTCOME_REPORT[outcome]
        print(f"  {label:<16} {counts[outcome.value]:>3}   {meaning}")

    for outcome in RecoveryOutcome:
        rows = [f for f in fixtures if f["outcome"] == outcome.value]
        if not rows:
            continue
        print(f"\n{OUTCOME_REPORT[outcome][0]}:")
        for row in rows:
            line = [f"    {row['match_id']}  {row['match_date']}  {row['status']:<10}",
                    f"attempts={row['attempts']}"]
            if row["provider_errors"]:
                line.append(f"errors={row['provider_errors']}")
            if row["cached_passes"]:
                line.append(f"cached={row['cached_passes']}")
            line.append(f"{row['outcome']} ({row['detail']})" if row["detail"] else row["outcome"])
            if row["overdue"]:
                line.append(f"OVERDUE {row['minutes_since_kickoff']}m since kickoff")
            if row["unresolved"]:
                line.append(f"STOPPED ASKING: {row['reason']}")
            print("  ".join(line))

    if report.get("archive"):
        print("\nwhat the archive returned this pass (competition@date):")
        for where, seen in sorted(report["archive"].items()):
            print(f"  {where:<40} {seen['state']:<9} rows={seen['rows']}  asked {seen['asked_at']}")
    if report.get("stops_undone"):
        print(f"\nstops made by a removed rule, undone and back on the retry schedule: "
              f"{', '.join(report['stops_undone'])}")
    if report.get("reopened"):
        print(f"\nreopened because a later results call returned results dated on or after their "
              f"date: {', '.join(report['reopened'])}")
    print(f"\nrequests this pass: {report['results_requests']} results + "
          f"{report['live_requests']} live")
    if report.get("live_note"):
        print(f"live poll: {report['live_note']}")
    if report["deferred"]:
        print(f"deferred by the pass's allowance: {', '.join(report['deferred'])}")
    if report.get("failed_calls"):
        print(f"REQUESTS NOBODY ANSWERED (an outage, not an empty archive): "
              f"{'; '.join(report['failed_calls'])}")


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
    print("note:      the scheduler's `recover` task does this unattended every "
          f"{settings.SYNC_RECOVERY_INTERVAL_SECONDS}s; this is the same pass, run by hand")
    # Resolving the covered competitions can CREATE a canonical league row for a key this database
    # does not hold yet (MatchDataService.league_ids -> competitions -> ensure_canonical_league),
    # and it does so before the report/apply branch below. "No provider request" is therefore not
    # the same promise as "no write", and saying only the first would let someone run this against
    # a database they were protecting.
    print("note:      resolving competitions may add a canonical league row if one is missing;")
    print("           no other write happens without --apply")
    print(f"budget {provider} before: {budget_now(provider)}\n")

    plan = service.recovery_plan(max_days=args.max_days)
    stranded, days = plan["stranded"], plan["days"]
    if not stranded:
        print("no stranded fixture; nothing to sweep")
        print(f"budget {provider} after:  {budget_now(provider)}")
        return 0

    print(f"stranded: {len(stranded)}, due an ask now under the retry schedule: {len(plan['due'])}")
    if plan.get("superseded"):
        print(f"stops made by a removed rule, to undo: {[str(m.id) for m in plan['superseded']]}")
    if plan["reopenable"]:
        print(f"to reopen (a later results call returned results dated on or after their date): "
              f"{[str(m.id) for m in plan['reopenable']]}")
    print(f"days to reopen: {[d.isoformat() for d in days]}")
    # One request per competition-day is the FIRST page only. matches/history.json paginates, and
    # `_paginate` will follow up to MAX_PAGES while the provider keeps advertising another one, so
    # the honest ceiling is that figure times MAX_PAGES. Printing the first-page number alone
    # understates a real sweep by up to five times, and a cost estimate that reads low is worse
    # than none at all: it is the number someone budgets against.
    first_pages = plan["results_requests"]
    print(f"estimated cost: {first_pages} results request(s) for the first page of each "
          f"competition-day, up to {first_pages * MAX_PAGES} if every one paginates to the "
          f"{MAX_PAGES}-page cap, plus {plan['live_requests']} live poll")
    print(f"               bounded by SYNC_RECOVERY_MAX_REQUESTS_PER_PASS="
          f"{settings.SYNC_RECOVERY_MAX_REQUESTS_PER_PASS} and by what is left of "
          f"SYNC_RECOVERY_MAX_REQUESTS_PER_DAY={settings.SYNC_RECOVERY_MAX_REQUESTS_PER_DAY}")
    print("stranded fixtures:")
    for match in stranded:
        print(describe(match, registry, now))

    if not args.apply:
        print("\nreport only; no provider request was made. Re-run with --apply to sweep.")
        return 0

    print()
    report_outcomes(sweep(service, days, stranded, now))

    print(f"\nbudget {provider} after:  {budget_now(provider)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
