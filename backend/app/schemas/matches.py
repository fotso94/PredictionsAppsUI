"""
Serializers for the match, league, team and provider endpoints.

Plain dictionaries are returned (documented here) so the frontend gets one stable shape whichever
provider produced the data. Probabilities are 0-1 floats; missing markets are null.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.models.predictions import League, Match, MatchStatus, Prediction, Team
from app.models.provider_data import ProviderEntityRef, ProviderForecastRecord
from app.services.providers.base import ProviderStanding


def _f(value) -> Optional[float]:
    return float(value) if value is not None else None


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """UTC ISO-8601 with an explicit Z.

    Stored datetimes are naive UTC. Serialising one without the Z makes the browser read it as
    local time, which moves a kickoff by the viewer's offset and can show the wrong day.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


#: Kept as the short internal spelling used throughout this module.
_iso = iso_utc


def status_label(match: Match) -> str:
    meta = match.match_metadata or {}
    provider_status = meta.get("provider_status")
    if match.status == MatchStatus.LIVE:
        return "halftime" if provider_status == "halftime" else "live"
    return {
        MatchStatus.SCHEDULED: "scheduled", MatchStatus.FINISHED: "finished",
        MatchStatus.POSTPONED: "postponed", MatchStatus.CANCELLED: "cancelled",
    }.get(match.status, "scheduled")


def serialize_team(team: Optional[Team]) -> Optional[Dict[str, Any]]:
    if team is None:
        return None
    return {"id": str(team.id), "name": team.name, "short_name": team.short_name, "logo": team.logo_url or "/teams/default.svg",
            "country": team.country}


def serialize_league(league: Optional[League], refs: Optional[Iterable[ProviderEntityRef]] = None) -> Optional[Dict[str, Any]]:
    if league is None:
        return None
    meta = league.league_metadata or {}
    providers = {r.provider: r.external_id for r in (refs or []) if r.provider != "canonical"}
    return {"id": str(league.id), "key": meta.get("canonical_key"), "name": league.display_name or league.name,
            "country": league.country, "country_code": league.country_code, "logo": league.logo_url or "/leagues/default.svg",
            "is_cup": bool(meta.get("is_cup")), "providers": providers}


def serialize_expert_prediction(prediction: Optional[Prediction]) -> Optional[Dict[str, Any]]:
    if prediction is None:
        return None
    return {
        "id": str(prediction.id), "source": prediction.source.value if hasattr(prediction.source, "value") else str(prediction.source),
        "priority_level": prediction.priority_level, "status": prediction.status.value if hasattr(prediction.status, "value") else str(prediction.status),
        "home_win_prob": _f(prediction.home_win_prob), "draw_prob": _f(prediction.draw_prob), "away_win_prob": _f(prediction.away_win_prob),
        "confidence_score": _f(prediction.confidence_score),
        "btts_yes_prob": _f(prediction.btts_yes_prob), "btts_no_prob": _f(prediction.btts_no_prob), "btts_confidence": _f(prediction.btts_confidence),
        "total_goals_over_25_prob": _f(prediction.total_goals_over_25_prob), "total_goals_under_25_prob": _f(prediction.total_goals_under_25_prob),
        "total_goals_over_35_prob": _f(prediction.total_goals_over_35_prob), "total_goals_under_35_prob": _f(prediction.total_goals_under_35_prob),
        "total_goals_confidence": _f(prediction.total_goals_confidence),
        "reasoning": prediction.reasoning, "published_at": _iso(prediction.published_at), "created_by": str(prediction.created_by),
    }


def serialize_forecast(record: Optional[ProviderForecastRecord], freshness: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if record is None:
        return None
    return {
        "provider": record.provider, "external_event_id": record.external_event_id,
        "home_win_prob": _f(record.home_win_prob), "draw_prob": _f(record.draw_prob), "away_win_prob": _f(record.away_win_prob),
        "btts_yes_prob": _f(record.btts_yes_prob), "btts_no_prob": _f(record.btts_no_prob),
        "total_goals_over_25_prob": _f(record.total_goals_over_25_prob), "total_goals_under_25_prob": _f(record.total_goals_under_25_prob),
        "total_goals_over_35_prob": _f(record.total_goals_over_35_prob), "total_goals_under_35_prob": _f(record.total_goals_under_35_prob),
        "exact_score": record.exact_score,
        # The provider's remainder bucket for every scoreline it does not list. Kept apart so it is
        # never rendered as a scoreline, and so the listed scores are never renormalised.
        "exact_score_other_prob": _f(record.exact_score_other_prob),
        "recommended_bets": record.recommended_bets, "reasoning": record.reasoning,
        "confidence": _f(record.confidence), "match_confidence": record.match_confidence, "matched_by": record.matched_by,
        # Three distinct times, never conflated: when the provider's model ran, when the provider last
        # touched the event, and when we retrieved it. model_run_at is null when the provider did not say.
        "model_run_at": _iso(record.model_run_at), "provider_updated_at": _iso(record.provider_updated_at),
        "fetched_at": _iso(record.fetched_at),
        "generated_at_known": record.model_run_at is not None,
        "anomalies": record.anomalies or [],
        "state": freshness.get("state"), "state_reason": freshness.get("reason"),
        # "we cannot refresh this right now" is a different statement from "this does not exist",
        # and only one of them is a reason to distrust the number on screen
        "refresh_blocked": bool(freshness.get("refresh_blocked")),
        "refresh_blocked_reason": freshness.get("refresh_blocked_reason"),
        # A market is available only when the provider supplied a value for it. Anything false must be
        # rendered as unavailable, never as 0%.
        "markets_available": {
            "match_result": all(v is not None for v in (record.home_win_prob, record.draw_prob, record.away_win_prob)),
            "btts": any(v is not None for v in (record.btts_yes_prob, record.btts_no_prob)),
            "over_under_25": any(v is not None for v in (record.total_goals_over_25_prob, record.total_goals_under_25_prob)),
            "over_under_35": any(v is not None for v in (record.total_goals_over_35_prob, record.total_goals_under_35_prob)),
            "exact_score": bool(record.exact_score),
        },
    }


def serialize_match(match: Match, teams: Dict, leagues: Dict, forecast: Optional[Dict[str, Any]] = None,
                    expert_prediction: Optional[Dict[str, Any]] = None, league_refs: Optional[Dict] = None) -> Dict[str, Any]:
    meta = match.match_metadata or {}
    home = teams.get(match.home_team_id)
    away = teams.get(match.away_team_id)
    league = leagues.get(match.league_id)
    score = None
    if meta.get("home_score") is not None and meta.get("away_score") is not None:
        score = {"home": meta.get("home_score"), "away": meta.get("away_score"),
                 "ht_home": meta.get("ht_home_score"), "ht_away": meta.get("ht_away_score")}
    forecast_state = (forecast or {}).get("state") or "unavailable"
    return {
        "id": str(match.id),
        "provider": match.external_api_source or meta.get("provider"),
        "external_id": match.external_api_id,
        "competition": serialize_league(league, (league_refs or {}).get(match.league_id)),
        "home": serialize_team(home), "away": serialize_team(away),
        "kickoff_utc": _iso(match.match_date), "status": status_label(match), "minute": meta.get("minute"),
        "score": score, "venue": match.venue, "round": match.round, "season": match.season,
        "expert_prediction": expert_prediction, "forecast": forecast, "forecast_state": forecast_state,
        "last_synced_at": meta.get("last_synced_at"),
    }


def serialize_standing(row: ProviderStanding, team_lookup: Optional[Dict[str, Team]] = None) -> Dict[str, Any]:
    internal = (team_lookup or {}).get(row.team.external_id)
    return {"position": row.position,
            "team": {"id": str(internal.id) if internal else None, "external_id": row.team.external_id, "name": row.team.name,
                     "logo": (internal.logo_url if internal and internal.logo_url else row.team.logo) or "/teams/default.svg"},
            "played": row.played, "won": row.won, "drawn": row.drawn, "lost": row.lost, "goals_for": row.goals_for,
            "goals_against": row.goals_against, "goal_difference": row.goal_difference, "points": row.points, "form": row.form}
