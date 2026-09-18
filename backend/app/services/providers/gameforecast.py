"""
GameForecastAPI provider (https://www.gameforecastapi.com) — PRIMARY forecast source.

Spec: https://gameforecastapi.com/specs/game-forecast-api.json (OpenAPI 3.1, fetched 2026-09-17).
- Server: https://game-forecast-api.p.rapidapi.com (RapidAPI)
- Headers: X-RapidAPI-Key, X-RapidAPI-Host
- GET /leagues?name=&country_code=&page_size=     -> data[] {id, sport_id, country_code, name, type, women}
- GET /events?league_id=&start_at_start=&start_at_end=&status_code=&page&page_size (<=50)
      -> data[] {id, league{id,name}, team_home{id,name}, team_away{id,name}, status_code,
                 round, start_at (ISO), score{...}, odds[], predictions[], updated_at}
  predictions[i] = {match_result{home,draw,away}, total_goals{over_2_5, under_2_5, ...},
                    both_teams_score{yes,no}, exact_score{...}, recommended_bets{}, reasoning{en,...}, run_at}
  Probabilities are published on a 0-100 scale (verified live 2026-09-17); exact_score keys look like "3_0"
  plus an "other" remainder bucket; extra markets (over/under 0.5/1.5, first_half_winner, team_to_score_first,
  home/away_team_goals) exist and are not used yet.
Free plan: 10 requests/day (10/hour); Pro: 5,000 requests/month.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings
from app.services.providers import competitions as comps
from app.services.providers.base import (
    ForecastProvider, ProviderCompetition, ProviderForecast, ProviderNotConfiguredError,
    ProviderUnavailableError, parse_utc, to_probability,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.http import ProviderHttpClient
from app.services.match_cache import MatchCache

logger = logging.getLogger(__name__)

PROVIDER_NAME = "gameforecast"
PAGE_SIZE = 50
MAX_PAGES = 4
LEAGUE_STORE_KEY = "provider:gameforecast:leagues"
LEAGUE_STORE_TTL = 30 * 24 * 3600

# GameForecast uses ISO country codes; our competitions use football federations' names
COUNTRY_CODES = {"premier_league": "GB", "la_liga": "ES", "serie_a": "IT", "bundesliga": "DE", "ligue_1": "FR"}


def _bucket(pred: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = pred.get(name)
    return value if isinstance(value, dict) else {}


def _snapshot_is_percent(latest: Dict[str, Any]) -> bool:
    """Live payloads (verified 2026-09-17) publish probabilities on a 0-100 scale: home 85 / draw 10 / away 5.
    A snapshot is treated as percent when any headline market value exceeds 1."""
    for name in ("match_result", "total_goals", "both_teams_score"):
        for value in _bucket(latest, name).values():
            try:
                if float(value) > 1:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _converter(percent: bool):
    def conv(value: Any) -> Optional[float]:
        if value is None or isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if percent:
            number = number / 100.0
        if number < 0 or number > 1:
            return None
        return round(number, 4)
    return conv


_SCORE_KEY = re.compile(r"^(\d+)[_\-:](\d+)$")


def parse_event(event: Dict[str, Any], competition_key: Optional[str] = None) -> Optional[ProviderForecast]:
    """Translate one /events item into a ProviderForecast (None when no prediction snapshot exists)."""
    predictions = event.get("predictions") or []
    if not predictions:
        return None
    # The API returns the latest snapshot first unless include_all_history=true; take the most recent run_at
    latest = max(predictions, key=lambda p: str(p.get("run_at") or ""))
    conv = _converter(_snapshot_is_percent(latest))
    result = _bucket(latest, "match_result")
    totals = _bucket(latest, "total_goals")
    btts = _bucket(latest, "both_teams_score")
    exact = _bucket(latest, "exact_score")
    league = event.get("league") or {}
    home = event.get("team_home") or {}
    away = event.get("team_away") or {}
    reasoning = latest.get("reasoning")
    if isinstance(reasoning, dict):
        reasoning = reasoning.get("en") or next(iter(reasoning.values()), None)
    # exact scores arrive as {"3_0": 14, ..., "other": 38}: keep real scorelines as "3-0", drop the remainder bucket
    exact_scores: Optional[Dict[str, float]] = None
    if exact:
        exact_scores = {}
        for score, prob in exact.items():
            key_match = _SCORE_KEY.match(str(score))
            p = conv(prob)
            if key_match and p is not None:
                exact_scores[f"{key_match.group(1)}-{key_match.group(2)}"] = p
        exact_scores = exact_scores or None
    return ProviderForecast(
        provider=PROVIDER_NAME,
        external_event_id=str(event.get("id")),
        home_name=str(home.get("name") or ""),
        away_name=str(away.get("name") or ""),
        kickoff_utc=parse_utc(event.get("start_at")),
        competition_name=league.get("name"),
        competition_external_id=str(league.get("id")) if league.get("id") is not None else None,
        competition_key=competition_key,
        home_external_id=str(home.get("id")) if home.get("id") is not None else None,
        away_external_id=str(away.get("id")) if away.get("id") is not None else None,
        home_prob=conv(result.get("home")),
        draw_prob=conv(result.get("draw")),
        away_prob=conv(result.get("away")),
        btts_yes_prob=conv(btts.get("yes")),
        btts_no_prob=conv(btts.get("no")),
        over_25_prob=conv(totals.get("over_2_5")),
        under_25_prob=conv(totals.get("under_2_5")),
        over_35_prob=conv(totals.get("over_3_5")),
        under_35_prob=conv(totals.get("under_3_5")),
        exact_score=exact_scores,
        recommended_bets=latest.get("recommended_bets") if isinstance(latest.get("recommended_bets"), dict) else None,
        reasoning=reasoning if isinstance(reasoning, str) else None,
        confidence=None,  # not published by the provider; never derived
        model_run_at=parse_utc(latest.get("run_at")),
        provider_updated_at=parse_utc(event.get("updated_at")),
        raw=event,
    )

class GameForecastProvider(ForecastProvider):
    name = PROVIDER_NAME
    integration_status = "primary"

    def __init__(self, api_key: Optional[str] = None, api_host: Optional[str] = None,
                 base_url: Optional[str] = None, transport=None, budget: Optional[RequestBudget] = None,
                 league_overrides: Optional[Dict[str, str]] = None, store: Optional[MatchCache] = None):
        self.api_key = api_key if api_key is not None else settings.GAMEFORECAST_API_KEY
        self.api_host = api_host or settings.GAMEFORECAST_API_HOST
        headers = {"X-RapidAPI-Key": self.api_key or "", "X-RapidAPI-Host": self.api_host}
        self.client = ProviderHttpClient(PROVIDER_NAME, base_url or settings.GAMEFORECAST_API_BASE_URL,
                                         headers=headers, transport=transport)
        self.budget = budget or RequestBudget(PROVIDER_NAME, settings.GAMEFORECAST_DAILY_REQUEST_BUDGET)
        self._overrides = league_overrides if league_overrides is not None \
            else comps.parse_id_overrides(settings.GAMEFORECAST_LEAGUE_IDS)
        self._league_cache: Dict[str, ProviderCompetition] = {}
        # League ids never change: keep them in Redis so the 10-requests/day free plan is spent on events
        self._store = store if store is not None else MatchCache()

    def _load_store(self) -> None:
        data = self._store.get(LEAGUE_STORE_KEY) or {}
        for key, item in data.items():
            if key in self._league_cache or not isinstance(item, dict) or not item.get("external_id"):
                continue
            self._league_cache[key] = ProviderCompetition(
                provider=PROVIDER_NAME, external_id=str(item["external_id"]), name=item.get("name") or key, key=key,
                country_code=item.get("country_code"), is_cup=bool(item.get("is_cup")))

    def _save_store(self) -> None:
        data = {key: {"external_id": c.external_id, "name": c.name, "country_code": c.country_code, "is_cup": c.is_cup}
                for key, c in self._league_cache.items()}
        if data:
            self._store.set(LEAGUE_STORE_KEY, data, ttl=LEAGUE_STORE_TTL, stale_ttl=LEAGUE_STORE_TTL)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, **params: Any) -> Dict[str, Any]:
        if not self.is_configured():
            raise ProviderNotConfiguredError("GameForecastAPI key not configured (GAMEFORECAST_API_KEY)", provider=self.name)
        self.budget.consume(1)
        payload = self.client.get_json(path, {k: v for k, v in params.items() if v is not None})
        if not isinstance(payload, dict) or "data" not in payload:
            raise ProviderUnavailableError("GameForecastAPI returned an unexpected payload", provider=self.name)
        return payload

    def resolve_league(self, key: str) -> Optional[ProviderCompetition]:
        if key in self._league_cache:
            return self._league_cache[key]
        self._load_store()
        if key in self._league_cache:
            return self._league_cache[key]
        canonical = comps.get(key)
        external_id = self._overrides.get(key) or (
            str(canonical.gameforecast_id) if canonical.gameforecast_id else None)
        if external_id:
            comp = ProviderCompetition(provider=PROVIDER_NAME, external_id=external_id, name=canonical.name, key=key,
                                       country=canonical.country, is_cup=canonical.is_cup)
        else:
            comp = None
            payload = self._get("/leagues", name=canonical.aliases[0], country_code=COUNTRY_CODES.get(key), page_size=PAGE_SIZE)
            for item in payload.get("data") or []:
                if item.get("women"):
                    continue
                matched = comps.match_competition_name(item.get("name", ""), keys=[key])
                if matched == key:
                    comp = ProviderCompetition(provider=PROVIDER_NAME, external_id=str(item.get("id")),
                                               name=item.get("name", ""), key=key,
                                               country_code=item.get("country_code"),
                                               is_cup=(item.get("type") == "cup"), raw=item)
                    break
        if comp:
            self._league_cache[key] = comp
            self._save_store()
        else:
            logger.warning("GameForecastAPI: league id for %s could not be resolved", key)
        return comp

    def get_forecasts(self, key: str, date_from: date, date_to: date) -> List[ProviderForecast]:
        league = self.resolve_league(key)
        if not league:
            return []
        forecasts: List[ProviderForecast] = []
        page = 1
        while page <= MAX_PAGES:
            payload = self._get("/events", league_id=league.external_id,
                                start_at_start=date_from.strftime("%Y-%m-%d"),
                                start_at_end=date_to.strftime("%Y-%m-%d"),
                                page=page, page_size=PAGE_SIZE)
            for event in payload.get("data") or []:
                forecast = parse_event(event, competition_key=key)
                if forecast and forecast.has_any_market():
                    forecasts.append(forecast)
            pagination = payload.get("pagination") or {}
            if not pagination.get("hasMore"):
                break
            page += 1
        return forecasts
