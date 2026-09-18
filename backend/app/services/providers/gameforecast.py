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
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.services.providers import competitions as comps
from app.services.providers.base import (
    ForecastProvider, ProviderCompetition, ProviderForecast, ProviderNotConfiguredError,
    ProviderUnavailableError, parse_utc,
)
from app.services.providers.base import to_probability as _to_probability
from app.services.providers.budget import RequestBudget
from app.services.providers.http import ProviderHttpClient
from app.services.match_cache import MatchCache

logger = logging.getLogger(__name__)

PROVIDER_NAME = "gameforecast"
PAGE_SIZE = 50
MAX_PAGES = 4
LEAGUE_STORE_KEY = "provider:gameforecast:leagues"
LEAGUE_STORE_TTL = 30 * 24 * 3600
#: A competition the /leagues search cannot resolve is remembered as unresolvable for this long.
#: Each discovery attempt costs one of the 10 free requests a day, so retrying it on every sync
#: burns the whole plan on a lookup that is already known to fail.
UNRESOLVED_TTL = 6 * 3600

# GameForecast uses ISO country codes; our competitions use football federations' names
COUNTRY_CODES = {"premier_league": "GB", "la_liga": "ES", "serie_a": "IT", "bundesliga": "DE", "ligue_1": "FR"}


def _bucket(pred: Dict[str, Any], name: str) -> Dict[str, Any]:
    value = pred.get(name)
    return value if isinstance(value, dict) else {}


# GameForecastAPI publishes every probability on a fixed 0-100 percentage scale. This is the
# provider's documented contract (specs/game-forecast-api.json) and was confirmed against live
# responses on 2026-09-17 (match_result home 85 / draw 10 / away 5, exact_score "3_0": 14).
# The scale is applied explicitly and unconditionally: a provider value of 1 means 1%, never 100%.
# Inferring the scale from whether values exceed 1 silently turns a genuine 1% into certainty.
PROBABILITY_SCALE = 100.0

#: Complementary pairs (yes/no, over/under) should sum to 100%; 1X2 outcomes should too.
#: Integer rounding by the provider makes small deviations normal, so only report beyond this.
SUM_TOLERANCE = 0.02


#: Values are compared against zero with a tolerance because they arrive rounded to 4 decimals.
ZERO_TOLERANCE = 1e-9


def to_probability(value: Any) -> Optional[float]:
    """Convert one GameForecastAPI percentage (0-100) to a 0-1 probability.

    This is base.to_probability with this provider's documented scale bound explicitly; there is
    exactly one conversion implementation (in base.py) and this only supplies PROBABILITY_SCALE.
    Returns None - meaning "market unavailable" - for anything that is not a finite number inside
    the published range. Nothing is guessed, clamped or rescaled.
    """
    return _to_probability(value, PROBABILITY_SCALE)


def _check_sum(anomalies: List[str], label: str,
               fields: Sequence[Tuple[str, Optional[float]]], expected: int) -> None:
    """Report a market whose probabilities do not add up - or say plainly that it is partial.

    `expected` is how many outcomes the market has (3 for 1X2, 2 for a complementary pair). A
    market the provider supplied only partially is NOT summed: two of three outcomes legitimately
    add up to less than 100%, and reporting that as an inconsistency is a false alarm.
    """
    present = [(name, value) for name, value in fields if value is not None]
    if not present:
        return  # the provider supplied nothing for this market; it renders as unavailable
    if len(present) < expected:
        missing = [name for name, value in fields if value is None]
        noun = "probability" if len(missing) == 1 else "probabilities"
        anomalies.append(f"{label} incomplete: {', '.join(missing)} {noun} not supplied")
        return
    total = sum(value for _, value in present)
    if abs(total - 1.0) > SUM_TOLERANCE:
        anomalies.append(f"{label} probabilities sum to {round(total * 100, 1)}%")


def _all_zero(anomalies: List[str], label: str, values: Sequence[Optional[float]]) -> bool:
    """True when the market was supplied but every value in it is zero.

    A provider that publishes 0 for every outcome of a market has not forecast that market: it
    is unavailable, and rendering it as a genuine 0% would present a non-forecast as a forecast.
    """
    present = [v for v in values if v is not None]
    if not present or sum(present) > ZERO_TOLERANCE:
        return False
    anomalies.append(f"{label} values were all zero; treated as unavailable")
    return True


_SCORE_KEY = re.compile(r"^(\d+)[_\-:](\d+)$")
_OTHER_KEYS = {"other", "others", "any_other", "rest"}


def _parse_exact_scores(exact: Dict[str, Any], anomalies: List[str]):
    """Return (scorelines, other_bucket_probability).

    Real scorelines are keyed "3-0". The provider's remainder bucket ("other") is kept apart so
    it is never displayed as a scoreline, and the listed scores are never renormalised: a list
    covering 62% of the outcome space keeps summing to 62%.
    """
    if not exact:
        return None, None
    scores: Dict[str, float] = {}
    other: Optional[float] = None
    dropped = 0
    zeroed = 0
    for raw_key, raw_value in exact.items():
        key = str(raw_key).strip().lower()
        probability = to_probability(raw_value)
        if key in _OTHER_KEYS:
            other = probability
            continue
        key_match = _SCORE_KEY.match(key)
        if not key_match:
            dropped += 1
            continue
        if probability is None:
            dropped += 1
            continue
        if probability <= ZERO_TOLERANCE:
            # A 0% scoreline is not a forecast of that scoreline. Keeping it would let the
            # "most likely score" pick a 0% entry when the provider zeroed the whole market.
            zeroed += 1
            continue
        scores[f"{key_match.group(1)}-{key_match.group(2)}"] = probability
    if dropped:
        anomalies.append(f"{dropped} exact-score entries were unreadable and were dropped")
    if zeroed:
        anomalies.append(f"{zeroed} exact-score entries were 0% and were dropped")
    if not scores:
        # Nothing survived: the market is unavailable. A remainder bucket on its own is not a
        # scoreline forecast, so it is not carried either.
        return None, None
    total = sum(scores.values()) + (other or 0.0)
    if total > 1.0 + SUM_TOLERANCE:
        anomalies.append(f"exact-score probabilities sum to {round(total * 100, 1)}%")
    return scores, other


def parse_event(event: Dict[str, Any], competition_key: Optional[str] = None) -> Optional[ProviderForecast]:
    """Translate one /events item into a ProviderForecast (None when no prediction snapshot exists)."""
    predictions = event.get("predictions") or []
    if not predictions:
        return None
    # The API returns the latest snapshot first unless include_all_history=true; take the most recent run_at
    latest = max(predictions, key=lambda p: str(p.get("run_at") or ""))
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

    anomalies: List[str] = []
    home_prob, draw_prob, away_prob = (to_probability(result.get(k)) for k in ("home", "draw", "away"))
    btts_yes, btts_no = to_probability(btts.get("yes")), to_probability(btts.get("no"))
    over_25, under_25 = to_probability(totals.get("over_2_5")), to_probability(totals.get("under_2_5"))
    over_35, under_35 = to_probability(totals.get("over_3_5")), to_probability(totals.get("under_3_5"))
    # A market the provider published as all zeros is a market it did not forecast. It must be
    # reported as unavailable, never rendered as a genuine 0%.
    if _all_zero(anomalies, "match result", (home_prob, draw_prob, away_prob)):
        home_prob = draw_prob = away_prob = None
    if _all_zero(anomalies, "both teams to score", (btts_yes, btts_no)):
        btts_yes = btts_no = None
    if _all_zero(anomalies, "over/under 2.5", (over_25, under_25)):
        over_25 = under_25 = None
    if _all_zero(anomalies, "over/under 3.5", (over_35, under_35)):
        over_35 = under_35 = None
    _check_sum(anomalies, "match result",
               (("home", home_prob), ("draw", draw_prob), ("away", away_prob)), expected=3)
    _check_sum(anomalies, "both teams to score",
               (("yes", btts_yes), ("no", btts_no)), expected=2)
    _check_sum(anomalies, "over/under 2.5",
               (("over", over_25), ("under", under_25)), expected=2)
    _check_sum(anomalies, "over/under 3.5",
               (("over", over_35), ("under", under_35)), expected=2)
    exact_scores, exact_other = _parse_exact_scores(exact, anomalies)
    if anomalies:
        logger.warning("GameForecastAPI event %s: %s", event.get("id"), "; ".join(anomalies))

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
        home_prob=home_prob,
        draw_prob=draw_prob,
        away_prob=away_prob,
        btts_yes_prob=btts_yes,
        btts_no_prob=btts_no,
        over_25_prob=over_25,
        under_25_prob=under_25,
        over_35_prob=over_35,
        under_35_prob=under_35,
        exact_score=exact_scores,
        exact_score_other_prob=exact_other,
        recommended_bets=latest.get("recommended_bets") if isinstance(latest.get("recommended_bets"), dict) else None,
        reasoning=reasoning if isinstance(reasoning, str) else None,
        confidence=None,  # not published by the provider; never derived
        model_run_at=parse_utc(latest.get("run_at")),
        provider_updated_at=parse_utc(event.get("updated_at")),
        anomalies=anomalies,
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
        #: Keys whose negative marker this instance has already reported, so the short-circuit
        #: logs once instead of once per competition per sync.
        self._unresolved_logged: set = set()

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

    # -------------------------------------------------- negative league-discovery cache
    @staticmethod
    def unresolved_key(key: str) -> str:
        return f"{LEAGUE_STORE_KEY}:unresolved:{key}"

    def _is_unresolved(self, key: str) -> bool:
        """True while a recent discovery attempt for this competition is known to have failed."""
        if not self._store.get(self.unresolved_key(key)):
            return False
        if key not in self._unresolved_logged:
            self._unresolved_logged.add(key)
            logger.info("GameForecastAPI: %s is marked unresolvable for %dh; skipping the /leagues "
                        "lookup to preserve the daily request budget", key, UNRESOLVED_TTL // 3600)
        return True

    def _mark_unresolved(self, key: str) -> None:
        self._store.set(self.unresolved_key(key),
                        {"key": key, "at": datetime.now(timezone.utc).isoformat()},
                        ttl=UNRESOLVED_TTL, stale_ttl=UNRESOLVED_TTL)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, reason: str = "fetch", **params: Any) -> Dict[str, Any]:
        if not self.is_configured():
            raise ProviderNotConfiguredError("GameForecastAPI key not configured (GAMEFORECAST_API_KEY)", provider=self.name)
        self.budget.consume(1, reason=reason)
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
            # Discovery is the only path that can fail, and it costs one of the 10 free requests
            # a day. A failure that is not remembered is repeated on every sync, forever.
            if self._is_unresolved(key):
                return None
            comp = None
            payload = self._get("/leagues", reason="discovery", name=canonical.aliases[0],
                                country_code=COUNTRY_CODES.get(key), page_size=PAGE_SIZE)
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
            self._mark_unresolved(key)
            logger.warning("GameForecastAPI: league id for %s could not be resolved; not retrying for %dh",
                           key, UNRESOLVED_TTL // 3600)
        return comp

    def get_forecasts(self, key: str, date_from: date, date_to: date) -> List[ProviderForecast]:
        league = self.resolve_league(key)
        if not league:
            return []
        forecasts: List[ProviderForecast] = []
        page = 1
        while page <= MAX_PAGES:
            payload = self._get("/events", reason="fetch" if page == 1 else "page",
                                league_id=league.external_id,
                                start_at_start=date_from.strftime("%Y-%m-%d"),
                                start_at_end=date_to.strftime("%Y-%m-%d"),
                                page=page, page_size=PAGE_SIZE)
            # Retrieval time is stamped here, once per HTTP response, while the payload is being
            # parsed - not when the forecast is later attached to a match. Stamping it at attach
            # time presents an hours-old forecast as freshly retrieved.
            fetched_at = datetime.now(timezone.utc)
            for event in payload.get("data") or []:
                forecast = parse_event(event, competition_key=key)
                if forecast and forecast.has_any_market():
                    forecast.fetched_at = fetched_at
                    forecasts.append(forecast)
            pagination = payload.get("pagination") or {}
            if not pagination.get("hasMore"):
                break
            page += 1
        return forecasts
