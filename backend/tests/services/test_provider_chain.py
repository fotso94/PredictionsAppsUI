"""Provider chain (fallbacks, cache, stale data) and forecast freshness — no database or network."""

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.models.predictions import Match, MatchStatus
from app.models.provider_data import ProviderForecastRecord
from app.services.forecast_service import ForecastService
from app.services.match_cache import MatchCache
from app.services.match_data_service import MatchDataService, SyncMeta
from app.services.providers.base import (
    MatchDataProvider, ProviderAuthError, ProviderCompetition, ProviderError, ProviderFixture, ProviderNotConfiguredError,
    ProviderQuotaError, ProviderStanding, ProviderTeam, ProviderUnavailableError, STATUS_SCHEDULED,
)
from app.services.providers.registry import build_data_provider, build_forecast_provider, data_provider_chain
from tests.providers.support import FakeRedis

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


class FakeProvider(MatchDataProvider):
    integration_status = "test"

    def __init__(self, name, fixtures=None, error=None, configured=True):
        self.name = name
        self._fixtures = fixtures or []
        self._error = error
        self._configured = configured
        self.calls = 0

    def is_configured(self):
        return self._configured

    def _serve(self):
        self.calls += 1
        if self._error:
            raise self._error
        return list(self._fixtures)

    def list_competitions(self, keys):
        return [ProviderCompetition(provider=self.name, external_id=f"{self.name}-{k}", name=k, key=k) for k in keys]

    def get_fixtures(self, day, keys):
        return self._serve()

    def get_live(self, keys):
        return self._serve()

    def get_results(self, date_from, date_to, keys):
        return self._serve()

    def get_standings(self, key):
        return []


def fixture(provider, ext_id="1"):
    comp = ProviderCompetition(provider=provider, external_id=f"{provider}-pl", name="Premier League", key="premier_league")
    return ProviderFixture(provider=provider, external_id=ext_id, competition=comp,
                           home=ProviderTeam(provider=provider, external_id="h", name="Liverpool"),
                           away=ProviderTeam(provider=provider, external_id="a", name="Everton"),
                           kickoff_utc=NOW + timedelta(hours=3), status=STATUS_SCHEDULED)


def service(providers, cache=None):
    return MatchDataService(MagicMock(), providers=providers, cache=cache or MatchCache(client=FakeRedis()), now=NOW,
                            keys=["premier_league"])


def call(svc, meta=None, key="k"):
    meta = meta or SyncMeta()
    data = svc._call_chain(key, 60, meta, lambda p: [f.external_id for f in p.get_fixtures(date(2026, 9, 20), svc.keys)])
    return data, meta


def test_primary_used_when_healthy():
    primary, fallback = FakeProvider("livescore", [fixture("livescore")]), FakeProvider("api_football", [fixture("api_football", "af")])
    data, meta = call(service([primary, fallback]))
    assert data == ["1"] and meta.provider == "livescore" and meta.source == "provider" and not meta.stale
    assert fallback.calls == 0


@pytest.mark.parametrize("error", [ProviderAuthError("bad key", provider="livescore"),
                                   ProviderQuotaError("quota", provider="livescore"),
                                   ProviderUnavailableError("down", provider="livescore"),
                                   ProviderNotConfiguredError("no creds", provider="livescore")])
def test_fallback_used_when_primary_fails(error):
    primary, fallback = FakeProvider("livescore", error=error), FakeProvider("api_football", [fixture("api_football", "af")])
    data, meta = call(service([primary, fallback]))
    assert data == ["af"] and meta.provider == "api_football" and meta.source == "provider"
    assert meta.errors and str(error) in meta.errors[0]


def test_fresh_cache_short_circuits_providers():
    redis = FakeRedis()
    primary = FakeProvider("livescore", [fixture("livescore")])
    svc = service([primary], MatchCache(client=redis))
    call(svc)
    data, meta = call(svc)
    assert data == ["1"] and meta.source == "cache" and meta.provider == "livescore" and primary.calls == 1


def test_stale_cache_served_and_flagged_when_all_providers_fail():
    redis = FakeRedis()
    healthy = FakeProvider("livescore", [fixture("livescore")])
    call(service([healthy], MatchCache(client=redis)))
    redis.store.pop("k")  # fresh copy expired, stale copy remains
    broken = FakeProvider("livescore", error=ProviderQuotaError("quota", provider="livescore"))
    data, meta = call(service([broken], MatchCache(client=redis)))
    assert data == ["1"] and meta.source == "stale-cache" and meta.stale is True and meta.errors


def test_error_raised_when_nothing_available():
    broken = FakeProvider("livescore", error=ProviderAuthError("bad key", provider="livescore"))
    with pytest.raises(ProviderAuthError):
        call(service([broken]))
    with pytest.raises(ProviderNotConfiguredError):
        call(service([]))


def test_provider_status_reports_budget_and_last_error():
    redis = FakeRedis()
    broken = FakeProvider("livescore", error=ProviderQuotaError("quota", provider="livescore"))
    svc = service([broken], MatchCache(client=redis))
    with pytest.raises(ProviderQuotaError):
        call(svc)
    status = svc.provider_status()
    assert status["chain"][0]["name"] == "livescore" and status["chain"][0]["last_error"] == "quota"
    assert status["covered_competitions"] == ["premier_league"]


def test_registry_builds_configured_chain(monkeypatch):
    monkeypatch.setattr(settings, "LIVESCORE_API_KEY", "")
    monkeypatch.setattr(settings, "LIVESCORE_API_SECRET", "")
    monkeypatch.setattr(settings, "API_FOOTBALL_KEY", "")
    monkeypatch.setattr(settings, "THESPORTSDB_KEY", "")
    assert [p.name for p in data_provider_chain("livescore", "api_football,thesportsdb,sample")] == ["sample"]
    monkeypatch.setattr(settings, "LIVESCORE_API_KEY", "k")
    monkeypatch.setattr(settings, "LIVESCORE_API_SECRET", "s")
    monkeypatch.setattr(settings, "API_FOOTBALL_KEY", "af")
    assert [p.name for p in data_provider_chain("livescore", "api_football,thesportsdb")] == ["livescore", "api_football"]
    assert build_data_provider("thesportsdb").integration_status.startswith("retained")
    assert build_data_provider("api_football").integration_status.startswith("retained")
    assert build_forecast_provider("none") is None
    assert build_forecast_provider("api_football").name == "api_football"
    with pytest.raises(ValueError):
        build_data_provider("unknown")


def _match(status=MatchStatus.SCHEDULED, kickoff=None):
    return Match(match_date=(kickoff or NOW + timedelta(hours=3)).replace(tzinfo=None), status=status)


def forecasts(now=NOW):
    return ForecastService(MagicMock(), provider=None, cache=MatchCache(client=FakeRedis()), now=now, keys=["premier_league"],
                           use_default_provider=False)


def test_forecast_freshness_states():
    svc = forecasts()
    assert svc.freshness(None, _match())["state"] == "unavailable"
    fresh = ProviderForecastRecord(model_run_at=(NOW - timedelta(hours=5)).replace(tzinfo=None))
    assert svc.freshness(fresh, _match())["state"] == "available"
    old = ProviderForecastRecord(model_run_at=(NOW - timedelta(hours=settings.FORECAST_MAX_AGE_HOURS + 1)).replace(tzinfo=None))
    assert svc.freshness(old, _match())["state"] == "stale"
    assert svc.freshness(fresh, _match(status=MatchStatus.FINISHED))["state"] == "kickoff_passed"
    assert svc.freshness(fresh, _match(kickoff=NOW - timedelta(hours=4)))["state"] == "kickoff_passed"


def test_forecast_sync_without_provider_reports_error():
    report = forecasts().ensure_synced()
    assert report["error"] == "no prediction provider configured" and report["competitions"] == {}
