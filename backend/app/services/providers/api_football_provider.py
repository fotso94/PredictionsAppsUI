"""
API-Football provider (https://www.api-football.com) — RETAINED fallback.

Wraps the pre-existing `APIFootballService` (kept unchanged for the expert flow) with the common
provider interface. Verified on 2026-09-17: the configured account is on the FREE plan
(100 requests/day, historical seasons only), so current-season fixtures may be empty; treat this
provider as "retained, not a tested working fallback" until the plan is upgraded.

Endpoints: /leagues?id=, /fixtures?date=&league=&season=, /fixtures?live=all, /fixtures?id=,
/standings?league=&season=, /predictions?fixture= (1X2 percentages only).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings
from app.services.providers import competitions as comps
from app.services.providers.base import (
    STATUS_CANCELLED, STATUS_FINISHED, STATUS_HALFTIME, STATUS_LIVE, STATUS_POSTPONED,
    STATUS_SCHEDULED, STATUS_UNKNOWN,
    ForecastProvider, MatchDataProvider, ProviderCompetition, ProviderFixture, ProviderForecast,
    ProviderNotConfiguredError, ProviderStanding, ProviderTeam, ProviderUnavailableError,
    parse_utc, to_probability,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.http import ProviderHttpClient

logger = logging.getLogger(__name__)

PROVIDER_NAME = "api_football"
BASE_URL = "https://v3.football.api-sports.io"

STATUS_MAP = {
    "TBD": STATUS_SCHEDULED, "NS": STATUS_SCHEDULED,
    "1H": STATUS_LIVE, "2H": STATUS_LIVE, "ET": STATUS_LIVE, "P": STATUS_LIVE, "BT": STATUS_LIVE,
    "LIVE": STATUS_LIVE, "INT": STATUS_LIVE, "SUSP": STATUS_POSTPONED,
    "HT": STATUS_HALFTIME,
    "FT": STATUS_FINISHED, "AET": STATUS_FINISHED, "PEN": STATUS_FINISHED, "AWD": STATUS_FINISHED, "WO": STATUS_FINISHED,
    "PST": STATUS_POSTPONED, "CANC": STATUS_CANCELLED, "ABD": STATUS_CANCELLED,
}


def current_season(today: Optional[date] = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    return today.year - 1 if today.month < 7 else today.year


class _APIFootballBase:
    def __init__(self, api_key: Optional[str] = None, transport=None, budget: Optional[RequestBudget] = None):
        self.api_key = api_key if api_key is not None else settings.API_FOOTBALL_KEY
        self.client = ProviderHttpClient(PROVIDER_NAME, BASE_URL, headers={"x-apisports-key": self.api_key or ""},
                                         transport=transport)
        self.budget = budget or RequestBudget(PROVIDER_NAME, 90)  # free plan: 100/day

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, **params: Any) -> List[Dict[str, Any]]:
        if not self.is_configured():
            raise ProviderNotConfiguredError("API-Football key not configured (API_FOOTBALL_KEY)", provider=PROVIDER_NAME)
        self.budget.consume(1)
        payload = self.client.get_json(path, {k: v for k, v in params.items() if v is not None})
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("API-Football returned a non-object payload", provider=PROVIDER_NAME)
        errors = payload.get("errors")
        if errors:
            raise ProviderUnavailableError(f"API-Football errors: {errors}", provider=PROVIDER_NAME)
        return payload.get("response") or []


def _fixture_from_payload(item: Dict[str, Any], key: Optional[str]) -> ProviderFixture:
    fx = item.get("fixture") or {}
    league = item.get("league") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    score = item.get("score") or {}
    ht = score.get("halftime") or {}
    status_short = (fx.get("status") or {}).get("short", "NS")
    return ProviderFixture(
        provider=PROVIDER_NAME,
        external_id=str(fx.get("id")),
        competition=ProviderCompetition(provider=PROVIDER_NAME, external_id=str(league.get("id")),
                                        name=league.get("name", ""), key=key, country=league.get("country"),
                                        logo=league.get("logo"), season_name=str(league.get("season") or "")),
        home=ProviderTeam(provider=PROVIDER_NAME, external_id=str((teams.get("home") or {}).get("id")),
                          name=(teams.get("home") or {}).get("name", ""), logo=(teams.get("home") or {}).get("logo")),
        away=ProviderTeam(provider=PROVIDER_NAME, external_id=str((teams.get("away") or {}).get("id")),
                          name=(teams.get("away") or {}).get("name", ""), logo=(teams.get("away") or {}).get("logo")),
        kickoff_utc=parse_utc(fx.get("date")) or datetime.now(timezone.utc),
        status=STATUS_MAP.get(status_short, STATUS_UNKNOWN),
        minute=str((fx.get("status") or {}).get("elapsed")) if (fx.get("status") or {}).get("elapsed") else None,
        home_score=goals.get("home"), away_score=goals.get("away"),
        ht_home_score=ht.get("home"), ht_away_score=ht.get("away"),
        venue=(fx.get("venue") or {}).get("name"),
        round=league.get("round"),
        raw=item,
    )


class APIFootballProvider(_APIFootballBase, MatchDataProvider):
    name = PROVIDER_NAME
    integration_status = "retained (free plan: current season restricted)"

    def _league_id(self, key: str) -> Optional[int]:
        return comps.get(key).api_football_id

    def list_competitions(self, keys: Iterable[str]) -> List[ProviderCompetition]:
        result = []
        for key in keys:
            canonical = comps.get(key)
            if canonical.api_football_id:
                result.append(ProviderCompetition(provider=PROVIDER_NAME, external_id=str(canonical.api_football_id),
                                                  name=canonical.name, key=key, country=canonical.country,
                                                  is_cup=canonical.is_cup))
        return result

    def get_fixtures(self, day: date, keys: Iterable[str]) -> List[ProviderFixture]:
        season = current_season(day)
        fixtures: List[ProviderFixture] = []
        for key in keys:
            league_id = self._league_id(key)
            if not league_id:
                continue
            items = self._get("/fixtures", date=day.strftime("%Y-%m-%d"), league=league_id, season=season)
            fixtures.extend(_fixture_from_payload(item, key) for item in items)
        return fixtures

    def get_live(self, keys: Iterable[str]) -> List[ProviderFixture]:
        ids = {str(self._league_id(k)): k for k in keys if self._league_id(k)}
        items = self._get("/fixtures", live="-".join(ids.keys()) if ids else "all")
        return [_fixture_from_payload(item, ids.get(str((item.get("league") or {}).get("id")))) for item in items]

    def get_results(self, date_from: date, date_to: date, keys: Iterable[str]) -> List[ProviderFixture]:
        results: List[ProviderFixture] = []
        for key in keys:
            league_id = self._league_id(key)
            if not league_id:
                continue
            items = self._get("/fixtures", league=league_id, season=current_season(date_to),
                              **{"from": date_from.strftime("%Y-%m-%d"), "to": date_to.strftime("%Y-%m-%d")})
            results.extend(f for f in (_fixture_from_payload(item, key) for item in items) if f.status == STATUS_FINISHED)
        return results

    def get_standings(self, key: str) -> List[ProviderStanding]:
        league_id = self._league_id(key)
        if not league_id:
            return []
        items = self._get("/standings", league=league_id, season=current_season())
        rows = []
        if items:
            rows = ((items[0].get("league") or {}).get("standings") or [[]])[0]
        standings = []
        for row in rows:
            team = row.get("team") or {}
            allv = row.get("all") or {}
            goals = allv.get("goals") or {}
            standings.append(ProviderStanding(
                position=int(row.get("rank") or 0),
                team=ProviderTeam(provider=PROVIDER_NAME, external_id=str(team.get("id")), name=team.get("name", ""), logo=team.get("logo")),
                played=int(allv.get("played") or 0), won=int(allv.get("win") or 0), drawn=int(allv.get("draw") or 0),
                lost=int(allv.get("lose") or 0), goals_for=int(goals.get("for") or 0), goals_against=int(goals.get("against") or 0),
                goal_difference=int(row.get("goalsDiff") or 0), points=int(row.get("points") or 0),
                form=list(row.get("form") or "")[-6:],
            ))
        return standings

    def get_fixture(self, external_id: str) -> Optional[ProviderFixture]:
        items = self._get("/fixtures", id=external_id)
        if not items:
            return None
        league_id = str((items[0].get("league") or {}).get("id"))
        key = next((k for k, c in comps.COMPETITIONS.items() if str(c.api_football_id) == league_id), None)
        return _fixture_from_payload(items[0], key)


class APIFootballForecastProvider(_APIFootballBase, ForecastProvider):
    """API-Football /predictions: 1X2 percentages only. BTTS and Over/Under are NOT supplied (kept None)."""

    name = PROVIDER_NAME
    integration_status = "retained (1X2 only; one request per fixture)"

    def get_forecasts(self, key: str, date_from: date, date_to: date) -> List[ProviderForecast]:
        data_provider = APIFootballProvider(api_key=self.api_key, transport=self.client.transport, budget=self.budget)
        forecasts: List[ProviderForecast] = []
        day = date_from
        while day <= date_to:
            for fixture in data_provider.get_fixtures(day, [key]):
                if fixture.status != STATUS_SCHEDULED:
                    continue
                items = self._get("/predictions", fixture=fixture.external_id)
                if not items:
                    continue
                pred = (items[0].get("predictions") or {})
                percent = pred.get("percent") or {}
                forecasts.append(ProviderForecast(
                    provider=PROVIDER_NAME, external_event_id=fixture.external_id,
                    home_name=fixture.home.name, away_name=fixture.away.name, kickoff_utc=fixture.kickoff_utc,
                    competition_name=fixture.competition.name, competition_external_id=fixture.competition.external_id,
                    competition_key=key, home_external_id=fixture.home.external_id, away_external_id=fixture.away.external_id,
                    home_prob=to_probability(percent.get("home")), draw_prob=to_probability(percent.get("draw")),
                    away_prob=to_probability(percent.get("away")),
                    reasoning=pred.get("advice"), model_run_at=datetime.now(timezone.utc), raw=items[0],
                ))
            day += timedelta(days=1)
        return forecasts
