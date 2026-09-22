"""Provider status and manual synchronisation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin_user
from app.db.session import get_db
from app.models.predictions import Match, MatchStatus, Prediction, PredictionStatus
from app.models.provider_data import ProviderForecastRecord, ProviderForecastSnapshot
from app.models.users import User
from app.services import settlement as settlement_service
from app.services.forecast_service import ForecastService
from app.services.match_data_service import MatchDataService
from app.services.providers import competitions as comps
from app.services.sync_scheduler import scheduler_status
from app.core.config import settings

router = APIRouter()

#: The three honest answers to "is there an accuracy figure?". They are kept apart on purpose:
#: "nothing has been scored" and "something has been scored, but not enough to publish a rate" are
#: different facts about this installation, and collapsing them into one boolean is how the reason
#: string this replaced went on claiming nothing had been scored long after scoring had started.
ACCURACY_NOTHING_SCORED = "nothing_scored"
ACCURACY_BELOW_MINIMUM_SAMPLE = "below_minimum_sample"
ACCURACY_AVAILABLE = "available"


@router.get("/status", summary="Active data/prediction providers, budgets, scheduler state and last errors")
async def provider_status(db: Session = Depends(get_db)):
    """What the providers are doing and when each kind of data was last refreshed.

    The `scheduler` block is what lets a page say "last updated ..." honestly. A task that has never
    run reports `never_run: true` with null timestamps rather than borrowing another task's time, and
    a task that is skipping because the daily allowance is spent says so in `last_skip_reason`.

    Every `budget` block - one per data provider in `chain`, and one under `forecasts` - now
    carries TWO accountings side by side, because they are not the same thing and on 2026-09-19
    they disagreed:

      - ours: `daily_limit`, `used_today`, `remaining_today`, keyed to the UTC day. Unchanged.
      - the provider's: `provider_reported`, which is whatever its rate-limit headers last said -
        its ceiling, what it says is left, and when it says its window resets. Its `known` flag is
        part of the answer: `known: false` means no such header has ever reached us, and it must
        be read as "unknown", never as zero and never as a full allowance.
      - `effective_remaining_today` is the smaller of the two - what the next request is actually
        measured against - and `limited_by` names which side is binding.

    On the night this was added ours read "3 of 8 used, 5 left" while the provider's read "0
    left": the divergence is the finding, so both are published rather than reconciled.
    """
    data = MatchDataService(db).provider_status()
    data["forecasts"] = ForecastService(db).status()
    data["scheduler"] = scheduler_status()
    data["checked_at"] = datetime.now(timezone.utc).isoformat()
    return data


def _accuracy_state(db: Session, now: datetime) -> Dict[str, Any]:
    """Whether an accuracy figure exists, measured from the database rather than assumed.

    This block used to be two constants: ``"accuracy_available": False`` and a reason reading "no
    settled results have been scored yet". Both were true the day they were written, and both went
    on being returned unchanged once settlement started writing scores, because a constant cannot
    notice that the database moved.

    The counts come from ``settlement.measurement`` - the same call that backs
    /performance/sources - and not from a second count written here, so the coverage figures and
    the performance page can never disagree about how much has been scored. The minimum-sample
    rule is not re-decided here either: whether a rate may be published is read off the per-market
    ``hit_rate_available`` / ``brier_available`` flags the performance module itself sets. This
    endpoint therefore publishes counts and a state, and never a percentage.

    Cost, because this is called on a page load: one ``measurement`` call, which is a fixed five to
    seven indexed queries (terminal matches by ``idx_matches_match_date`` over the default 90-day
    kickoff window, then predictions, snapshots and score rows keyed by those match ids). There is
    no scan of unbounded history - the window bounds every query - but the work does grow with the
    number of terminal matches inside the window, so the window is published with the counts.
    """
    measured = settlement_service.measurement(db, now=now)
    sources = measured["sources"]
    totals = {key: sum(source[key] for source in sources)
              for key in ("eligible", "scored", "pending", "void", "not_scored")}
    # A figure "exists" exactly when the performance module was willing to publish one; asking it
    # is what keeps the minimum-sample decision in the single place that owns it.
    published_figures = sum(1 for source in sources for market in source["markets"]
                            if market["hit_rate_available"] or market["brier_available"])
    window = measured["window"]
    scoring: Dict[str, Any] = {
        "window": window,
        "sources": len(sources),
        "sources_measured": measured["sources_measured"],
        "minimum_sample": measured["minimum_sample"],
        "published_figures": published_figures,
        "counted_by": "app.services.settlement.measurement, the counts /performance/sources publishes",
        "detail": "/api/v1/performance/sources",
        **totals,
    }
    span = f"{window['start']} to {window['end']}"

    if published_figures:
        return {"accuracy_state": ACCURACY_AVAILABLE, "accuracy_available": True,
                "accuracy_unavailable_reason": None, "scoring": scoring}
    if totals["scored"]:
        return {
            "accuracy_state": ACCURACY_BELOW_MINIMUM_SAMPLE,
            "accuracy_available": False,
            "accuracy_unavailable_reason": (
                f"{totals['scored']} of {totals['eligible']} eligible prediction(s) with a kickoff "
                f"in {span} have been scored, but no single source and market has reached the "
                f"minimum of {measured['minimum_sample']} scored predictions an accuracy figure is "
                "published from. The counts are published; the rate is not."),
            "scoring": scoring,
        }
    detail = (measured["not_measured_reason"] or "nothing is eligible for scoring") if not sources else (
        f"none of the {totals['eligible']} eligible prediction(s) carries a score yet "
        f"({totals['pending']} pending, {totals['void']} void, {totals['not_scored']} not scorable)")
    return {
        "accuracy_state": ACCURACY_NOTHING_SCORED,
        "accuracy_available": False,
        "accuracy_unavailable_reason": f"no settled result with a kickoff in {span} has been scored yet: {detail}",
        "scoring": scoring,
    }


@router.get("/coverage", summary="Measured coverage of the data actually held")
async def coverage(db: Session = Depends(get_db)):
    """Counts of what this installation actually holds right now.

    Every number is measured from the database, including the scoring state: ``accuracy_state``
    says whether nothing has been scored, something has been scored but too little to publish a
    rate, or a figure exists, and ``scoring`` carries the counts behind that answer. No accuracy
    percentage, success rate or user count is published here - a rate belongs to
    /performance/sources, which publishes it with its sample and its definition. Anything
    unavailable is reported as such, with the measured reason, rather than estimated.
    """
    now = datetime.now(timezone.utc)
    keys = comps.covered_keys(settings.COVERED_COMPETITIONS)
    upcoming = (db.query(Match)
                .filter(Match.match_date >= now.replace(tzinfo=None),
                        Match.status.in_([MatchStatus.SCHEDULED, MatchStatus.LIVE]))
                .count())
    forecasts = db.query(ProviderForecastRecord).count()
    upcoming_with_forecast = (db.query(ProviderForecastRecord)
                              .join(Match, Match.id == ProviderForecastRecord.match_id)
                              .filter(Match.match_date >= now.replace(tzinfo=None))
                              .count())
    # deleted_at is a soft delete: an unpublished or removed prediction must not keep being counted
    published = (db.query(Prediction)
                 .filter(Prediction.status == PredictionStatus.PUBLISHED,
                         Prediction.deleted_at.is_(None))
                 .count())
    return {
        "competitions_covered": len(keys),
        "competition_keys": keys,
        "upcoming_matches": upcoming,
        "matches_stored": db.query(Match).count(),
        "model_forecasts": forecasts,
        "upcoming_matches_with_forecast": upcoming_with_forecast,
        "forecast_snapshots": db.query(ProviderForecastSnapshot).count(),
        "expert_predictions_published": published,
        # Deliberately absent: any accuracy percentage, success rate or active-user count. The
        # first belongs to /performance/sources, which publishes it with its sample; the other two
        # would have to be invented. What IS reported here is the measured scoring state.
        **_accuracy_state(db, now),
        "measured_at": now.isoformat(),
    }


@router.post("/sync", summary="Force a synchronisation (admin)")
async def force_sync(days: int = Query(2, ge=1, le=7), forecasts: bool = Query(True),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    service = MatchDataService(db)
    # An admin-triggered sync retries providers even after recent failures, and the competition
    # calendar's own backoff is forgotten with them: it is keyed separately from the per-provider
    # cool-downs, so without this an operator who has just fixed credentials would get the days
    # below back at once and the empty-state calendar only when its wait ran out.
    service.clear_cooldowns()
    today = datetime.now(timezone.utc).date()
    report = {"days": {}}
    for offset in range(days):
        day = today + timedelta(days=offset)
        report["days"][day.isoformat()] = service.sync_day(day).to_dict()
    if forecasts:
        forecast_service = ForecastService(db)
        forecast_service.clear_cooldown()
        report["forecasts"] = forecast_service.ensure_synced(force=True)
    return report
