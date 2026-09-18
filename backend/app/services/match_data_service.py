"""
Match data orchestration: provider chain with fallbacks, Redis caching, request-budget aware
live polling, stale-data degradation, and persistence through the MatchRegistry.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.predictions import League, Match, MatchStatus
from app.services.match_cache import MatchCache
from app.services.match_registry import MatchRegistry
from app.services.providers import competitions as comps
from app.services.providers.base import (
    MatchDataProvider, ProviderError, ProviderFixture, ProviderNotConfiguredError,
    ProviderQuotaError, ProviderAuthError, ProviderStanding, ProviderUnavailableError,
)
from app.services.providers.registry import data_provider_chain

logger = logging.getLogger(__name__)

STATUS_KEY = "provider:status:{name}"
COOLDOWN_KEY = "provider:cooldown:{name}"
AUTH_COOLDOWN_SECONDS = 30 * 60        # rejected credentials: retry every 30 minutes, not on every page load
UNAVAILABLE_COOLDOWN_SECONDS = 2 * 60  # upstream errors / network problems


def _seconds_until_utc_midnight(now: datetime) -> int:
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - now).total_seconds()), 60)


@dataclass
class SyncMeta:
    provider: Optional[str] = None
    source: str = "database"          # provider | cache | stale-cache | database
    stale: bool = False
    fetched_at: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    live_polled: bool = False
    results_polled: bool = False
    #: Fixtures the registry refused to store because they could not be told apart from an existing
    #: match. Counted and reported rather than guessed into a duplicate row.
    ambiguous: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"provider": self.provider, "source": self.source, "stale": self.stale, "fetched_at": self.fetched_at,
                "errors": self.errors, "live_polled": self.live_polled, "results_polled": self.results_polled,
                "ambiguous": self.ambiguous}


def _fixture_to_dict(f: ProviderFixture) -> Dict[str, Any]:
    return {
        "provider": f.provider, "external_id": f.external_id,
        "competition": {"provider": f.competition.provider, "external_id": f.competition.external_id, "name": f.competition.name,
                        "key": f.competition.key, "country": f.competition.country, "country_code": f.competition.country_code,
                        "is_cup": f.competition.is_cup, "season_name": f.competition.season_name, "logo": f.competition.logo},
        "home": {"provider": f.home.provider, "external_id": f.home.external_id, "name": f.home.name, "logo": f.home.logo, "country": f.home.country},
        "away": {"provider": f.away.provider, "external_id": f.away.external_id, "name": f.away.name, "logo": f.away.logo, "country": f.away.country},
        "kickoff_utc": f.kickoff_utc.isoformat(), "status": f.status, "minute": f.minute,
        "home_score": f.home_score, "away_score": f.away_score, "ht_home_score": f.ht_home_score, "ht_away_score": f.ht_away_score,
        "venue": f.venue, "round": f.round,
    }


def _fixture_from_dict(d: Dict[str, Any]) -> ProviderFixture:
    from app.services.providers.base import ProviderCompetition, ProviderTeam, parse_utc
    c, h, a = d["competition"], d["home"], d["away"]
    return ProviderFixture(
        provider=d["provider"], external_id=d["external_id"],
        competition=ProviderCompetition(provider=c["provider"], external_id=c["external_id"], name=c["name"], key=c.get("key"),
                                        country=c.get("country"), country_code=c.get("country_code"), is_cup=bool(c.get("is_cup")),
                                        season_name=c.get("season_name"), logo=c.get("logo")),
        home=ProviderTeam(provider=h["provider"], external_id=h["external_id"], name=h["name"], logo=h.get("logo"), country=h.get("country")),
        away=ProviderTeam(provider=a["provider"], external_id=a["external_id"], name=a["name"], logo=a.get("logo"), country=a.get("country")),
        kickoff_utc=parse_utc(d["kickoff_utc"]), status=d["status"], minute=d.get("minute"),
        home_score=d.get("home_score"), away_score=d.get("away_score"), ht_home_score=d.get("ht_home_score"), ht_away_score=d.get("ht_away_score"),
        venue=d.get("venue"), round=d.get("round"),
    )


class MatchDataService:
    def __init__(self, db: Session, providers: Optional[List[MatchDataProvider]] = None, cache: Optional[MatchCache] = None,
                 now: Optional[datetime] = None, keys: Optional[List[str]] = None):
        self.db = db
        self.registry = MatchRegistry(db)
        self.cache = cache or MatchCache()
        self._providers = providers
        self._now = now
        self.keys = keys or comps.covered_keys(settings.COVERED_COMPETITIONS)

    # ------------------------------------------------------------------ helpers
    @property
    def now(self) -> datetime:
        return self._now or datetime.now(timezone.utc)

    @property
    def providers(self) -> List[MatchDataProvider]:
        if self._providers is None:
            self._providers = data_provider_chain()
        return self._providers

    @property
    def primary_name(self) -> Optional[str]:
        return self.providers[0].name if self.providers else None

    def _record_status(self, name: str, ok: bool, error: Optional[str] = None) -> None:
        payload = self.cache.get(STATUS_KEY.format(name=name)) or {}
        stamp = self.now.isoformat()
        if ok:
            payload.update({"last_success_at": stamp, "last_error": None})
        else:
            payload.update({"last_error_at": stamp, "last_error": error})
        self.cache.set(STATUS_KEY.format(name=name), payload, ttl=7 * 24 * 3600, stale_ttl=7 * 24 * 3600)

    def _cooldown(self, name: str) -> Optional[str]:
        payload = self.cache.get(COOLDOWN_KEY.format(name=name))
        return payload.get("reason") if isinstance(payload, dict) else None

    def clear_cooldowns(self) -> None:
        """Forget recent failures (used by the admin sync after credentials were fixed)."""
        for p in self.providers:
            self.cache.delete(COOLDOWN_KEY.format(name=p.name))

    def _set_cooldown(self, name: str, reason: str, seconds: int) -> None:
        self.cache.set(COOLDOWN_KEY.format(name=name), {"reason": reason, "until_seconds": seconds}, ttl=seconds, stale_ttl=seconds)

    def _call_chain(self, cache_key: str, ttl: int, meta: SyncMeta, fn):
        """Run `fn(provider)` on the first working provider, with fresh/stale cache around it."""
        cached = self.cache.get(cache_key)
        if cached is not None:
            meta.source, meta.provider, meta.fetched_at = "cache", cached.get("provider"), cached.get("fetched_at")
            return cached["data"]
        last_error: Optional[ProviderError] = None
        for provider in self.providers:
            cooling = self._cooldown(provider.name)
            if cooling:
                meta.errors.append(f"{provider.name}: skipped (recent failure: {cooling})")
                last_error = last_error or ProviderUnavailableError(cooling, provider=provider.name)
                continue
            try:
                data = fn(provider)
            except ProviderNotConfiguredError as exc:
                meta.errors.append(str(exc)); last_error = exc; continue
            except ProviderQuotaError as exc:
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), _seconds_until_utc_midnight(self.now)); continue
            except ProviderAuthError as exc:
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), AUTH_COOLDOWN_SECONDS); continue
            except ProviderError as exc:
                logger.warning("%s: %s", provider.name, exc)
                meta.errors.append(str(exc)); self._record_status(provider.name, False, str(exc)); last_error = exc
                self._set_cooldown(provider.name, str(exc), UNAVAILABLE_COOLDOWN_SECONDS); continue
            self._record_status(provider.name, True)
            meta.source, meta.provider, meta.fetched_at = "provider", provider.name, self.now.isoformat()
            self.cache.set(cache_key, {"provider": provider.name, "fetched_at": meta.fetched_at, "data": data}, ttl=ttl)
            return data
        stale = self.cache.get_stale(cache_key)
        # Only a copy produced by a provider that is still in the chain may be served: switching
        # DATA_PROVIDER must never resurrect data from a provider that is no longer configured.
        if stale is not None and stale.get("provider") in {p.name for p in self.providers}:
            meta.source, meta.provider, meta.fetched_at, meta.stale = "stale-cache", stale.get("provider"), stale.get("fetched_at"), True
            return stale["data"]
        if last_error is not None:
            raise last_error
        raise ProviderNotConfiguredError("No match-data provider is configured", provider="none")

    # ------------------------------------------------------------------ competitions
    def competitions(self) -> List[League]:
        """Internal league rows for the covered competitions (created on first use)."""
        leagues = [self.registry.ensure_canonical_league(k) for k in self.keys]
        self.db.commit()
        return leagues

    def league_ids(self) -> List:
        return [l.id for l in self.competitions()]

    # ------------------------------------------------------------------ fixtures
    def _store_fixtures(self, fixtures, meta: SyncMeta) -> int:
        """Persist fixtures, counting the ones the registry refused as too ambiguous to identify.

        `upsert_fixture` returns None when a provider fixture cannot be told apart from an existing
        match. Storing it anyway would create a second card for the same game and split the expert
        predictions across the two rows, so the refusal is recorded instead.
        """
        stored = 0
        for fixture in fixtures:
            if self.registry.upsert_fixture(fixture) is None:
                meta.ambiguous += 1
            else:
                stored += 1
        if meta.ambiguous:
            logger.warning("%d fixture(s) were not stored because they could not be identified unambiguously",
                           meta.ambiguous)
        return stored

    def sync_day(self, day: date) -> SyncMeta:
        meta = SyncMeta()
        key = f"matchdata:fixtures:{day.isoformat()}:{','.join(self.keys)}"
        try:
            payload = self._call_chain(key, settings.MATCH_CACHE_TTL_FIXTURES, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_fixtures(day, self.keys)])
        except ProviderError as exc:
            meta.errors.append(str(exc))
            meta.source = "database"
            return meta
        fixtures = [_fixture_from_dict(d) for d in payload]
        self._store_fixtures(fixtures, meta)
        self.db.commit()
        if day <= self.now.date():
            self._sync_results(day, meta)
        if day == self.now.date():
            self._sync_live(meta)
        return meta

    def _pending_results_exist(self, day: date) -> bool:
        cutoff = (self.now - timedelta(minutes=150)).replace(tzinfo=None)
        for m in self.registry.matches_for_day(day, self.league_ids()):
            if m.status in (MatchStatus.SCHEDULED, MatchStatus.LIVE) and m.match_date <= cutoff:
                return True
        return False

    def _sync_results(self, day: date, meta: SyncMeta) -> None:
        if not self._pending_results_exist(day):
            return
        key = f"matchdata:results:{day.isoformat()}:{','.join(self.keys)}"
        try:
            payload = self._call_chain(key, settings.MATCH_CACHE_TTL_RESULTS, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_results(day, day, self.keys)])
        except ProviderError as exc:
            meta.errors.append(f"results: {exc}")
            return
        meta.results_polled = True
        self._store_fixtures((_fixture_from_dict(d) for d in payload), meta)
        self.db.commit()

    def _live_window_open(self) -> bool:
        now_naive = self.now.replace(tzinfo=None)
        for m in self.registry.matches_for_day(self.now.date(), self.league_ids()):
            if m.status == MatchStatus.FINISHED or m.status in (MatchStatus.POSTPONED, MatchStatus.CANCELLED):
                continue
            if m.match_date - timedelta(minutes=15) <= now_naive <= m.match_date + timedelta(minutes=150):
                return True
        return False

    def _sync_live(self, meta: SyncMeta) -> None:
        if not self._live_window_open():
            return
        key = f"matchdata:live:{','.join(self.keys)}"
        try:
            payload = self._call_chain(key, settings.MATCH_CACHE_TTL_LIVE, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_live(self.keys)])
        except ProviderError as exc:
            meta.errors.append(f"live: {exc}")
            return
        meta.live_polled = True
        self._store_fixtures((_fixture_from_dict(d) for d in payload), meta)
        self.db.commit()

    def sync_upcoming(self, key: str, days_ahead: int = 14) -> SyncMeta:
        """Fill the calendar of one competition (used by league pages and the expert match picker)."""
        meta = SyncMeta()
        cache_key = f"matchdata:upcoming:{key}:{days_ahead}"
        try:
            payload = self._call_chain(cache_key, settings.MATCH_CACHE_TTL_FIXTURES * 4, meta,
                                       lambda p: [_fixture_to_dict(f) for f in p.get_upcoming(key, days_ahead)])
        except ProviderError as exc:
            meta.errors.append(str(exc))
            return meta
        self._store_fixtures((_fixture_from_dict(d) for d in payload), meta)
        self.db.commit()
        return meta

    def matches_for_day(self, day: date, refresh: bool = True) -> Tuple[List[Match], SyncMeta]:
        meta = self.sync_day(day) if refresh else SyncMeta()
        matches = self.registry.matches_for_day(day, self.league_ids())
        return matches, meta

    def live_matches(self) -> Tuple[List[Match], SyncMeta]:
        meta = SyncMeta()
        self._sync_live(meta)
        matches = [m for m in self.registry.matches_for_day(self.now.date(), self.league_ids()) if m.status == MatchStatus.LIVE]
        return matches, meta

    def match_by_id(self, match_id) -> Optional[Match]:
        return self.db.query(Match).filter(Match.id == match_id).first()

    # ------------------------------------------------------------------ standings
    def standings(self, key: str) -> Tuple[List[ProviderStanding], SyncMeta]:
        meta = SyncMeta()
        cache_key = f"matchdata:standings:{key}"

        def serial(p: MatchDataProvider):
            rows = p.get_standings(key)
            return [{"position": r.position, "team": {"provider": r.team.provider, "external_id": r.team.external_id, "name": r.team.name,
                                                       "logo": r.team.logo},
                     "played": r.played, "won": r.won, "drawn": r.drawn, "lost": r.lost, "goals_for": r.goals_for,
                     "goals_against": r.goals_against, "goal_difference": r.goal_difference, "points": r.points, "form": r.form}
                    for r in rows]

        try:
            payload = self._call_chain(cache_key, settings.MATCH_CACHE_TTL_STANDINGS, meta, serial)
        except ProviderError as exc:
            meta.errors.append(str(exc))
            return [], meta
        from app.services.providers.base import ProviderTeam
        rows = [ProviderStanding(position=r["position"], team=ProviderTeam(provider=r["team"]["provider"], external_id=r["team"]["external_id"],
                                                                            name=r["team"]["name"], logo=r["team"].get("logo")),
                                 played=r["played"], won=r["won"], drawn=r["drawn"], lost=r["lost"], goals_for=r["goals_for"],
                                 goals_against=r["goals_against"], goal_difference=r["goal_difference"], points=r["points"], form=r.get("form") or [])
                for r in payload]
        return rows, meta

    # ------------------------------------------------------------------ status
    def provider_status(self) -> Dict[str, Any]:
        chain = []
        for p in self.providers:
            status = self.cache.get(STATUS_KEY.format(name=p.name)) or {}
            budget = getattr(p, "budget", None)
            chain.append({"name": p.name, "integration_status": p.integration_status, "configured": p.is_configured(),
                          "budget": budget.snapshot() if budget else None, "cooling_down": self._cooldown(p.name), **status})
        return {
            "active_provider": settings.DATA_PROVIDER,
            "configured_fallbacks": [n.strip() for n in settings.DATA_PROVIDER_FALLBACKS.split(",") if n.strip()],
            "covered_competitions": self.keys,
            "cache_available": self.cache.available,
            "chain": chain,
        }
