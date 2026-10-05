#!/usr/bin/env python
"""
Close the second listings of played matches, exactly as the sync now does, after showing the evidence.

WHY THIS EXISTS
    Live Score listed the AFCON qualifier Senegal v Mozambique for 2026-09-25 19:00 UTC in Dakar
    (fixture 1899816), then listed the same match again as Mozambique v Senegal, 13:01 UTC in
    Maputo (1902057), which finished 1-1. The old id was never listed again. The sync stored both,
    so the old row read "scheduled" from then on and the recovery sweep kept asking a results
    provider about it. `MatchRegistry.relisting_of` states the shape, and the sync and the recovery pass
    now close such a row on their own. This script does the same thing by hand, against any
    database, and prints what it found first.

WHAT --apply DOES
    Exactly `MatchRegistry.retire_relisted`: the stale listing becomes POSTPONED and
    `match_metadata.relisted_as` names the played row, with the evidence. Nothing is moved and
    nothing is deleted. Every row pointing at the stale listing stays on it, because it is the
    fixture those rows were made for, and that includes its provider ref. No provider request is
    made.

USAGE
    ./venv/bin/python scripts/repair_relisted_fixtures.py                      # report only
    ./venv/bin/python scripts/repair_relisted_fixtures.py --apply              # close them
    ./venv/bin/python scripts/repair_relisted_fixtures.py --database-url ...   # a restored copy
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.models.predictions import Match, MatchResult  # noqa: E402
from app.services.match_registry import RELISTED_KEY, MatchRegistry, recovery_state_of  # noqa: E402
from repair_duplicate_matches import Dependent, dependents, redacted  # noqa: E402


def pointing_at(db: Session, match_id, deps: Sequence[Dependent]) -> Dict[str, int]:
    """Rows in every table that points at matches, for this one row; tables with none left out."""
    counts = {}
    for dep in deps:
        n = db.execute(text(f"SELECT count(*) FROM {dep.qualified} WHERE {dep.filter_sql('mid')}"),
                       {"mid": str(match_id)}).scalar() or 0
        if n:
            counts[dep.qualified] = n
    return counts


def describe(db: Session, registry: MatchRegistry, match: Match, marker: str) -> str:
    teams = registry.team_names([match])
    home, away = teams.get(match.home_team_id), teams.get(match.away_team_id)
    result = db.query(MatchResult).filter(MatchResult.match_id == match.id).first()
    status = match.status.value + (f" {result.home_score}-{result.away_score}" if result else "")
    refs = {r.provider: r.external_id for r in registry.refs_for("match", match.id)}
    return (f"    {marker:<6} {match.id}  {home.name if home else '?'} v {away.name if away else '?'}  "
            f"{match.match_date:%Y-%m-%d %H:%M} UTC  {status}  {refs}  venue={match.venue!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="close the stale listings (default: report only)")
    parser.add_argument("--database-url", default=None,
                        help="database to work on; defaults to the application's own")
    args = parser.parse_args()

    if args.database_url:
        url = args.database_url
    else:
        from app.core.config import settings
        url = settings.DATABASE_URL

    db = sessionmaker(autocommit=False, autoflush=False, bind=create_engine(url, echo=False))()
    registry = MatchRegistry(db)
    now = datetime.now(timezone.utc)
    print(f"database: {redacted(str(url))}")
    print(f"mode:     {'APPLY - stale listings will be closed' if args.apply else 'report only'}")
    print(f"now:      {now.isoformat()}\n")

    deps = dependents(db)
    pairs = registry.relisted_fixtures(now)
    print(f"second listings of a played match: {len(pairs)}")
    for stale, played in pairs:
        leagues = registry.leagues_by_id([stale])
        league = leagues.get(stale.league_id)
        state = recovery_state_of(stale)
        print(f"  {league.name if league else stale.league_id}")
        print(describe(db, registry, stale, "STALE"))
        print(f"           last listed {(stale.match_metadata or {}).get('last_synced_at')}, "
              f"asked about {state.get('attempts') or 0} time(s) by the recovery sweep")
        print(describe(db, registry, played, "PLAYED"))
        print(f"    staying on the stale listing: {pointing_at(db, stale.id, deps) or 'nothing'}")
    print()

    if not args.apply:
        print("report only; nothing was changed. Re-run with --apply to close them.")
        return 0

    try:
        closed = registry.retire_relisted(now)
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"FAILED, rolled back: {exc}")
        return 1
    for match in closed:
        note = (match.match_metadata or {}).get(RELISTED_KEY) or {}
        print(f"closed {match.id}: {match.status.value}, relisted_as {note.get('match_id')}")
        print(f"    {note.get('reason')}")
    print(f"\nclosed: {len(closed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
