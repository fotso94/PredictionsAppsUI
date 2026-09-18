"""Provider selection from settings."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.core.config import settings
from app.services.providers.base import ForecastProvider, MatchDataProvider

logger = logging.getLogger(__name__)

DATA_PROVIDER_NAMES = ("livescore", "api_football", "thesportsdb", "sample")
FORECAST_PROVIDER_NAMES = ("gameforecast", "api_football", "sample", "none")


def build_data_provider(name: str, **kwargs) -> MatchDataProvider:
    name = (name or "").strip().lower()
    if name == "livescore":
        from app.services.providers.livescore_api import LiveScoreAPIProvider
        return LiveScoreAPIProvider(**kwargs)
    if name == "api_football":
        from app.services.providers.api_football_provider import APIFootballProvider
        return APIFootballProvider(**kwargs)
    if name == "thesportsdb":
        from app.services.providers.thesportsdb_provider import TheSportsDBProvider
        return TheSportsDBProvider(**kwargs)
    if name == "sample":
        from app.services.providers.sample import SampleDataProvider
        return SampleDataProvider(**kwargs)
    raise ValueError(f"Unknown DATA_PROVIDER '{name}'. Valid values: {', '.join(DATA_PROVIDER_NAMES)}")


def build_forecast_provider(name: str, **kwargs) -> Optional[ForecastProvider]:
    name = (name or "none").strip().lower()
    if name in ("none", ""):
        return None
    if name == "gameforecast":
        from app.services.providers.gameforecast import GameForecastProvider
        return GameForecastProvider(**kwargs)
    if name == "api_football":
        from app.services.providers.api_football_provider import APIFootballForecastProvider
        return APIFootballForecastProvider(**kwargs)
    if name == "sample":
        from app.services.providers.sample import SampleForecastProvider
        return SampleForecastProvider(**kwargs)
    raise ValueError(f"Unknown PREDICTION_PROVIDER '{name}'. Valid values: {', '.join(FORECAST_PROVIDER_NAMES)}")


def data_provider_chain(primary: Optional[str] = None, fallbacks: Optional[str] = None) -> List[MatchDataProvider]:
    """Active provider followed by the configured fallbacks (unconfigured ones are skipped with a warning)."""
    names = [(primary or settings.DATA_PROVIDER).strip().lower()]
    names += [n.strip().lower() for n in (fallbacks if fallbacks is not None else settings.DATA_PROVIDER_FALLBACKS).split(",") if n.strip()]
    chain: List[MatchDataProvider] = []
    seen: Dict[str, bool] = {}
    for name in names:
        if name in seen:
            continue
        seen[name] = True
        try:
            provider = build_data_provider(name)
        except ValueError as exc:
            logger.error(str(exc))
            continue
        if not provider.is_configured():
            logger.warning("Match-data provider '%s' is not configured; skipped", name)
            continue
        chain.append(provider)
    return chain


def forecast_provider() -> Optional[ForecastProvider]:
    provider = build_forecast_provider(settings.PREDICTION_PROVIDER)
    if provider and not provider.is_configured():
        logger.warning("Prediction provider '%s' is not configured; forecasts disabled", provider.name)
        return None
    return provider
