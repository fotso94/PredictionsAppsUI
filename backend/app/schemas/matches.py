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
from app.services.providers import competitions as comps
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
    """One team row, carrying the scope that says WHICH squad it is.

    ``country`` cannot answer that, and not because it is absent. ``upsert_team`` refuses to write
    a competition's confederation territory onto a squad, so a national team's country is the one
    the PROVIDER spelled for it, or ``"Unknown"`` -- which means Spain's men and Spain's women carry
    the SAME country, and a Spanish club may carry it too. The field a reader would reach for is
    precisely the field that cannot separate the three, and a follow list would show the same word
    twice with nothing to choose between the rows.

    ``team_scope`` is that answer, served as the stored ``TeamScope`` value rather than as a
    phrase: it is a stable identifier the caller maps to whatever its own reader reads, in whatever
    language, and the wording never has to agree across two codebases. Rows written before the
    column existed carry the server default, which is the club scope they were always read as.
    """
    if team is None:
        return None
    return {"id": str(team.id), "name": team.name, "short_name": team.short_name, "logo": team.logo_url or "/teams/default.svg",
            "country": team.country,
            "team_scope": team.team_scope or comps.DEFAULT_TEAM_SCOPE.value}


def _classification(key: Optional[str]) -> Dict[str, Any]:
    """Club-or-country, confederation and squad category for a canonical competition key.

    These three are written down once per competition in
    :mod:`app.services.providers.competitions` and cannot be derived from a competition's name
    without guessing, which is exactly why they are carried here rather than left to the caller:
    "National Teams Friendlies", "UEFA Nations League" and "Premier League" are three names with
    no shared shape, and a reader asking to see only national-team football is asking a question
    only this table can answer.

    A league we hold no canonical key for -- one stored straight from a provider -- is REPORTED AS
    A CLUB COMPETITION, which is the same reading :meth:`MatchRegistry._scope_for` gives it when it
    decides which scope to store its teams under. The two must agree: a fixture filed under a club
    scope and served as national-team football would put a country in the club list and a club in
    the country list at once. Its confederation and squad category stay null, because those are not
    known and a default would be an invention rather than a reading.
    """
    canonical = comps.COMPETITIONS.get(key or "")
    if canonical is None:
        return {"is_national_team": False, "confederation": None, "squad_category": None}
    return {
        "is_national_team": canonical.is_national_team,
        "confederation": canonical.confederation.value if canonical.confederation else None,
        "squad_category": canonical.squad_category.value,
    }


def serialize_league(league: Optional[League], refs: Optional[Iterable[ProviderEntityRef]] = None) -> Optional[Dict[str, Any]]:
    if league is None:
        return None
    meta = league.league_metadata or {}
    providers = {r.provider: r.external_id for r in (refs or []) if r.provider != "canonical"}
    return {"id": str(league.id), "key": meta.get("canonical_key"), "name": league.display_name or league.name,
            "country": league.country, "country_code": league.country_code, "logo": league.logo_url or "/leagues/default.svg",
            "is_cup": bool(meta.get("is_cup")), "providers": providers,
            **_classification(meta.get("canonical_key"))}


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


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Stored datetimes are naive UTC; an aware one is converted rather than compared across kinds."""
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def serialize_prediction_revision(revision, index: int, kickoff: Optional[datetime] = None) -> Dict[str, Any]:
    """One preserved earlier version of an expert prediction.

    ``values`` is the published view as it stood before the edit, with the ``published_at`` it
    carried, so a reader can see what was on screen and when - not merely that something changed.
    Revisions are append-only, so ``revision`` 1 is always the original and stays readable however
    many corrections follow, including corrections made after kickoff.
    """
    values = revision.old_values or {}
    recorded, kicked_off = _naive_utc(revision.created_at), _naive_utc(kickoff)
    return {
        "id": str(revision.id),
        "prediction_id": str(revision.prediction_id),
        "revision": index,
        # When this version stopped being the published one.
        "replaced_at": _iso(revision.created_at),
        "edited_by": str(revision.user_id) if revision.user_id else None,
        "changes_summary": revision.changes_summary,
        # None when the kickoff is unknown: a stored False would assert "before kickoff".
        "edited_after_kickoff": (recorded > kicked_off) if (recorded and kicked_off) else None,
        "published_at": values.get("published_at"),
        "values": values,
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


def serialize_score(meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Every period of a tie the source supplied, each one kept apart from the others.

    A knockout tie has more than one scoreline and they answer different questions, so all of them
    travel and none of them is merged into another:

    * ``home``/``away``     the football that was played, extra time included and penalties never.
    * ``ht_home``/``ht_away``   half time.
    * ``ft_home``/``ft_away``   REGULATION time, 90 minutes plus stoppage. This is the only period
      :mod:`app.services.settlement` settles a market on.
    * ``et_home``/``et_away`` and ``ps_home``/``ps_away``   extra time and the shoot-out. They
      settle nothing and they are what lets a reader be shown "0-0 (4-3 pens)" instead of a 0-0
      that loses the half of the result everybody who watched it remembers.

    Every period but ``home``/``away`` is null when the source did not supply it. Null is "not
    supplied" and is not zero: a caller that cannot tell those apart must render neither.

    Returns None when there is no score at all, which is the state of every fixture that has not
    been played and of a played one whose result the source never sent.
    """
    if meta.get("home_score") is None or meta.get("away_score") is None:
        return None
    return {
        "home": meta.get("home_score"), "away": meta.get("away_score"),
        "ht_home": meta.get("ht_home_score"), "ht_away": meta.get("ht_away_score"),
        "ft_home": meta.get("ft_home_score"), "ft_away": meta.get("ft_away_score"),
        "et_home": meta.get("et_home_score"), "et_away": meta.get("et_away_score"),
        "ps_home": meta.get("ps_home_score"), "ps_away": meta.get("ps_away_score"),
    }


def serialize_match(match: Match, teams: Dict, leagues: Dict, forecast: Optional[Dict[str, Any]] = None,
                    expert_prediction: Optional[Dict[str, Any]] = None, league_refs: Optional[Dict] = None) -> Dict[str, Any]:
    meta = match.match_metadata or {}
    home = teams.get(match.home_team_id)
    away = teams.get(match.away_team_id)
    league = leagues.get(match.league_id)
    score = serialize_score(meta)
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
