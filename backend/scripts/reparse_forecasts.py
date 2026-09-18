"""
Re-parse the raw payload stored with every provider forecast and rewrite the derived fields.
Use after a parser fix; makes no provider requests.

    cd backend && source venv/bin/activate && python scripts/reparse_forecasts.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

from app.db.session import SessionLocal
from app.models.provider_data import ProviderForecastRecord
from app.services.providers.gameforecast import parse_event


def dec(value):
    return Decimal(str(value)) if value is not None else None


def main() -> None:
    db = SessionLocal()
    updated = skipped = 0
    try:
        for record in db.query(ProviderForecastRecord).filter(ProviderForecastRecord.provider == "gameforecast").all():
            if not record.raw_payload:
                skipped += 1
                continue
            forecast = parse_event(record.raw_payload)
            if forecast is None:
                skipped += 1
                continue
            record.home_win_prob, record.draw_prob, record.away_win_prob = dec(forecast.home_prob), dec(forecast.draw_prob), dec(forecast.away_prob)
            record.btts_yes_prob, record.btts_no_prob = dec(forecast.btts_yes_prob), dec(forecast.btts_no_prob)
            record.total_goals_over_25_prob, record.total_goals_under_25_prob = dec(forecast.over_25_prob), dec(forecast.under_25_prob)
            record.total_goals_over_35_prob, record.total_goals_under_35_prob = dec(forecast.over_35_prob), dec(forecast.under_35_prob)
            record.exact_score = forecast.exact_score
            record.recommended_bets = forecast.recommended_bets
            record.reasoning = forecast.reasoning
            updated += 1
        db.commit()
        print(f"re-parsed {updated} forecasts, skipped {skipped}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
