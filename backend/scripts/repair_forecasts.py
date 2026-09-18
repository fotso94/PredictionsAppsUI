"""
Re-derive every stored provider forecast from the raw payload that was saved with it.

Use after a parser fix. Makes NO provider requests: the evidence needed is already in
predictions.provider_forecasts.raw_payload, so a repair costs nothing against the trial quota.

What it does
  - re-parses raw_payload with the current parser
  - rewrites only the derived market values, leaving provider timestamps (model_run_at,
    provider_updated_at), the raw payload, the match link and every expert prediction untouched
  - appends a corrected snapshot to predictions.provider_forecast_snapshots when the corrected
    values differ from the latest snapshot, so the history keeps both what was stored and what
    the corrected reading is
  - clears the cached match payloads that embedded the wrong numbers

It is idempotent: running it twice changes nothing the second time.

    cd backend
    ./venv/bin/python scripts/repair_forecasts.py --dry-run     # report only, no writes
    ./venv/bin/python scripts/repair_forecasts.py               # apply
    ./venv/bin/python scripts/repair_forecasts.py --provider gameforecast --verbose
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.db.session import SessionLocal
from app.models.predictions import Match
from app.models.provider_data import ProviderForecastRecord
from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.providers.gameforecast import parse_event as parse_gameforecast

#: provider name -> function turning a stored raw payload back into a ProviderForecast
PARSERS = {"gameforecast": parse_gameforecast}

#: (record attribute, forecast attribute) for every derived market value
FIELDS: Tuple[Tuple[str, str], ...] = (
    ("home_win_prob", "home_prob"), ("draw_prob", "draw_prob"), ("away_win_prob", "away_prob"),
    ("btts_yes_prob", "btts_yes_prob"), ("btts_no_prob", "btts_no_prob"),
    ("total_goals_over_25_prob", "over_25_prob"), ("total_goals_under_25_prob", "under_25_prob"),
    ("total_goals_over_35_prob", "over_35_prob"), ("total_goals_under_35_prob", "under_35_prob"),
    ("exact_score_other_prob", "exact_score_other_prob"),
)


def _dec(value: Optional[float]) -> Optional[Decimal]:
    return Decimal(str(round(value, 4))) if value is not None else None


def _same(stored: Any, fresh: Optional[float]) -> bool:
    if stored is None or fresh is None:
        return stored is None and fresh is None
    return abs(float(stored) - float(fresh)) <= 1e-6


def _describe(record: ProviderForecastRecord, forecast) -> List[str]:
    changes = []
    for column, attribute in FIELDS:
        stored, fresh = getattr(record, column), getattr(forecast, attribute)
        if not _same(stored, fresh):
            changes.append(f"{column}: {stored} -> {fresh}")
    if (record.exact_score or None) != (forecast.exact_score or None):
        before = len(record.exact_score or {})
        after = len(forecast.exact_score or {})
        top_before = max((record.exact_score or {}).items(), key=lambda kv: kv[1], default=("-", 0))
        top_after = max((forecast.exact_score or {}).items(), key=lambda kv: kv[1], default=("-", 0))
        changes.append(f"exact_score: {before} scores (top {top_before[0]} {top_before[1]}) "
                       f"-> {after} scores (top {top_after[0]} {top_after[1]})")
    if (record.reasoning or None) != (forecast.reasoning or None):
        changes.append("reasoning rewritten")
    if list(record.anomalies or []) != list(forecast.anomalies or []):
        changes.append(f"anomalies: {record.anomalies or []} -> {forecast.anomalies or []}")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    parser.add_argument("--provider", default=None, help="limit to one provider (default: every provider with a parser)")
    parser.add_argument("--verbose", action="store_true", help="print every changed field")
    args = parser.parse_args()

    providers = [args.provider] if args.provider else list(PARSERS)
    unknown = [name for name in providers if name not in PARSERS]
    if unknown:
        print(f"No raw-payload parser for: {', '.join(unknown)}")
        return 2

    db = SessionLocal()
    cache = MatchCache()
    now = datetime.now(timezone.utc)
    service = ForecastService(db, use_default_provider=False, now=now, sync_fixtures=False)
    counts: Dict[str, int] = {"examined": 0, "no_raw_payload": 0, "unparseable": 0,
                              "already_correct": 0, "corrected": 0, "snapshots_added": 0}
    touched_matches = set()

    try:
        for name in providers:
            parse = PARSERS[name]
            records = (db.query(ProviderForecastRecord)
                       .filter(ProviderForecastRecord.provider == name)
                       .order_by(ProviderForecastRecord.fetched_at.asc()).all())
            for record in records:
                counts["examined"] += 1
                if not record.raw_payload:
                    counts["no_raw_payload"] += 1
                    continue
                forecast = parse(record.raw_payload)
                if forecast is None:
                    counts["unparseable"] += 1
                    continue
                # A repair re-reads a payload we already hold; it retrieves nothing. Stamping the
                # snapshot with "now" would move a forecast fetched before kickoff to after it, which
                # is precisely the prematch evidence this history exists to preserve.
                forecast.fetched_at = (record.fetched_at.replace(tzinfo=timezone.utc)
                                       if record.fetched_at and record.fetched_at.tzinfo is None
                                       else record.fetched_at)
                changes = _describe(record, forecast)
                if not changes:
                    counts["already_correct"] += 1
                    continue
                counts["corrected"] += 1
                touched_matches.add(record.match_id)
                if args.verbose or args.dry_run:
                    print(f"  {record.match_id} ({record.external_event_id})")
                    for change in changes:
                        print(f"      {change}")
                if args.dry_run:
                    continue
                for column, attribute in FIELDS:
                    setattr(record, column, _dec(getattr(forecast, attribute)))
                record.exact_score = forecast.exact_score
                record.recommended_bets = forecast.recommended_bets
                record.reasoning = forecast.reasoning
                record.anomalies = forecast.anomalies or None
                # provider timestamps, raw_payload, match link, match_confidence and every expert
                # prediction are deliberately left as they are
                match = db.query(Match).filter(Match.id == record.match_id).first()
                if match is not None:
                    before = service.snapshots_for_match(match.id, name)
                    service._record_snapshot(match, forecast, record.match_confidence, record.matched_by)
                    db.flush()
                    if len(service.snapshots_for_match(match.id, name)) > len(before):
                        counts["snapshots_added"] += 1

        if args.dry_run:
            db.rollback()
        else:
            db.commit()
            cache.delete_pattern("matchdata:*")
    finally:
        db.close()

    print()
    print("dry run - nothing was written" if args.dry_run else "applied")
    for label, value in counts.items():
        print(f"  {label.replace('_', ' '):18} {value}")
    print(f"  {'matches affected':18} {len(touched_matches)}")
    if not args.dry_run and touched_matches:
        print("  cached match payloads cleared so the corrected values are served immediately")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
