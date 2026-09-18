"""
Remove everything the "sample" providers wrote (fixtures, teams, forecasts, provider refs) and the
predictions attached to those fake fixtures. Use it once before switching DATA_PROVIDER from
`sample` to a real provider on a database that was used for local development.

    cd backend && source venv/bin/activate && python scripts/purge_sample_data.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import or_

from app.db.session import SessionLocal
from app.models.predictions import Match, MatchResult, Prediction, Team
from app.models.provider_data import ProviderEntityRef, ProviderForecastRecord, ProviderForecastSnapshot


def purge() -> None:
    db = SessionLocal()
    try:
        matches = db.query(Match).filter(Match.external_api_source == "sample").all()
        match_ids = [m.id for m in matches]
        counts = {"matches": len(match_ids)}
        if match_ids:
            counts["predictions"] = db.query(Prediction).filter(Prediction.match_id.in_(match_ids)).delete(synchronize_session=False)
            counts["forecasts"] = db.query(ProviderForecastRecord).filter(ProviderForecastRecord.match_id.in_(match_ids)).delete(synchronize_session=False)
            counts["forecast_snapshots"] = db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.match_id.in_(match_ids)).delete(synchronize_session=False)
            counts["results"] = db.query(MatchResult).filter(MatchResult.match_id.in_(match_ids)).delete(synchronize_session=False)
            counts["match_refs"] = db.query(ProviderEntityRef).filter(ProviderEntityRef.entity_type == "match",
                                                                      ProviderEntityRef.entity_id.in_(match_ids)).delete(synchronize_session=False)
            db.query(Match).filter(Match.id.in_(match_ids)).delete(synchronize_session=False)
        counts["sample_forecasts_elsewhere"] = db.query(ProviderForecastRecord).filter(ProviderForecastRecord.provider == "sample").delete(synchronize_session=False)
        # the FK cascade only fires for deleted matches, so sample forecasts attached to real fixtures
        # need removing from the evidence table explicitly too
        counts["sample_snapshots_elsewhere"] = db.query(ProviderForecastSnapshot).filter(ProviderForecastSnapshot.provider == "sample").delete(synchronize_session=False)
        # sample teams that no remaining match references
        teams = db.query(Team).filter(Team.external_api_source == "sample").all()
        removed_teams = 0
        for team in teams:
            in_use = db.query(Match.id).filter(or_(Match.home_team_id == team.id, Match.away_team_id == team.id)).first()
            if in_use is None:
                db.query(ProviderEntityRef).filter(ProviderEntityRef.entity_type == "team", ProviderEntityRef.entity_id == team.id).delete(synchronize_session=False)
                db.delete(team)
                removed_teams += 1
        counts["teams"] = removed_teams
        counts["league_refs"] = db.query(ProviderEntityRef).filter(ProviderEntityRef.provider == "sample").delete(synchronize_session=False)
        db.commit()
        print("Removed sample data:", counts)
    finally:
        db.close()


if __name__ == "__main__":
    purge()
