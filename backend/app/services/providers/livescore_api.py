"""
Live Score API provider (https://live-score-api.com) — PRIMARY match-data source.

Documentation used (verified 2026-09-17):
- GET /api-client/competitions/list.json         -> data.competition[]
- GET /api-client/fixtures/list.json?date=&competition_id=   -> data.fixtures[] (30 per page, next_page)
- GET /api-client/matches/live.json[?competition_id=]        -> data.match[]
- GET /api-client/matches/history.json?from=&to=&competition_id= -> data.match[] (30 per page)
- GET /api-client/competitions/table.json?competition_id=&include_form=1 -> standings rows
Authentication: `key` and `secret` query parameters. All dates/times are UTC.

Period breakdown: the payloads recorded from this provider carry `scores.score`, `scores.ht_score`
and `scores.ft_score`, and none of them is from a tie that went past 90 minutes -- so which of
`score` and `ft_score` excludes extra time is not something the recorded evidence settles.
`ft_*`/`et_*`/`ps_*` are therefore left None here rather than mapped from a guess, and a knockout
tie from this provider settles on its single stored score, as it did before. Mapping them needs
one real extra-time payload to read. See `_fixture_from_payload` in `api_football_provider.py`
for the shape this takes once the periods are actually known.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings
from app.services.providers import competitions as comps
from app.services.providers.base import (
    STATUS_CANCELLED, STATUS_FINISHED, STATUS_HALFTIME, STATUS_LIVE, STATUS_POSTPONED,
    STATUS_SCHEDULED, STATUS_UNKNOWN,
    MatchDataProvider, ProviderAuthError, ProviderCompetition, ProviderFixture,
    ProviderNotConfiguredError, ProviderQuotaError, ProviderStanding, ProviderTeam,
    ProviderUnavailableError, parse_score, parse_utc,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.http import ProviderHttpClient
from app.services.match_cache import MatchCache

logger = logging.getLogger(__name__)

PROVIDER_NAME = "livescore"

LIVE_STATUS_MAP = {
    "NOT STARTED": STATUS_SCHEDULED,
    "IN PLAY": STATUS_LIVE,
    "ADDED TIME": STATUS_LIVE,
    "HALF TIME BREAK": STATUS_HALFTIME,
    "HALF TIME": STATUS_HALFTIME,
    "FINISHED": STATUS_FINISHED,
    "INSUFFICIENT DATA": STATUS_UNKNOWN,
    "POSTPONED": STATUS_POSTPONED,
    "CANCELLED": STATUS_CANCELLED,
    "CANCELED": STATUS_CANCELLED,
    "ABANDONED": STATUS_CANCELLED,
    "SUSPENDED": STATUS_POSTPONED,
}

#: Page ceiling for the fixture reads: the default `_paginate` uses, and the bound `get_upcoming`'s
#: own loop counts against. At 30 rows a page that is at most 5 requests and 150 rows for one call.
#: It is a ceiling, not a target — every loop below also stops as soon as the answer is complete —
#: and because the page counter only ever increases towards it, no loop here can run away even if
#: the provider keeps advertising a next page.
#:
#: It is NOT the ceiling on every read: a caller that must have the whole of a longer list passes
#: its own, and `list_competitions` does (COMPETITION_LIST_MAX_PAGES below). Budget a paginated
#: read against the ceiling that read actually passes.
MAX_PAGES = 5
COMPETITION_STORE_KEY = "provider:livescore:competitions"

#: Page ceiling for the competition list, the one read here that may cost far more than MAX_PAGES:
#: up to 40 requests and 1,200 rows in a single call. The provider lists every competition it
#: covers, 30 to a page, and the whole list has to be walked to find the covered ones in it. What
#: keeps that off the request path is the Redis store (`_load_store`): the resolved ids are kept
#: fresh for MATCH_CACHE_TTL_COMPETITIONS and stale-kept for 30 days, so this ceiling is paid on a
#: cold store, not per page load.
COMPETITION_LIST_MAX_PAGES = 40
MIN_REQUEST_INTERVAL = 1.0   # seconds between calls (bursts are answered with HTTP 401)
BURST_RETRY_DELAY = 2.5
_last_request_at = 0.0
_throttle_lock = threading.Lock()


class LiveScoreAPIProvider(MatchDataProvider):
    name = PROVIDER_NAME
    integration_status = "primary"

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 base_url: Optional[str] = None, transport=None, budget: Optional[RequestBudget] = None,
                 competition_overrides: Optional[Dict[str, str]] = None, store: Optional[MatchCache] = None,
                 use_default_ids: bool = True):
        self.api_key = api_key if api_key is not None else settings.LIVESCORE_API_KEY
        self.api_secret = api_secret if api_secret is not None else settings.LIVESCORE_API_SECRET
        self.client = ProviderHttpClient(PROVIDER_NAME, base_url or settings.LIVESCORE_API_BASE_URL, transport=transport)
        self.budget = budget or RequestBudget(PROVIDER_NAME, settings.LIVESCORE_DAILY_REQUEST_BUDGET)
        self._overrides = competition_overrides if competition_overrides is not None \
            else comps.parse_id_overrides(settings.LIVESCORE_COMPETITION_IDS)
        self._competition_cache: Dict[str, ProviderCompetition] = {}
        self._use_default_ids = use_default_ids
        # Resolved competition ids are kept in Redis so a new provider instance (one per request)
        # does not re-download the paginated competition list every time.
        self._store = store if store is not None else MatchCache()

    def _load_store(self) -> None:
        # The fresh copy expires after MATCH_CACHE_TTL_COMPETITIONS while a 30-day stale copy is
        # kept alongside it. Competition ids are immutable, so once the fresh copy has expired the
        # stale one is still exactly right - and reading it is what stops a new provider instance
        # from re-downloading up to 40 pages of the competition list.
        data = self._store.get(COMPETITION_STORE_KEY)
        if not data:
            data = self._store.get_stale(COMPETITION_STORE_KEY) or {}
        for key, item in data.items():
            if key in self._competition_cache or not isinstance(item, dict) or not item.get("external_id"):
                continue
            self._competition_cache[key] = ProviderCompetition(
                provider=PROVIDER_NAME, external_id=str(item["external_id"]), name=item.get("name") or key, key=key,
                country=item.get("country"), country_code=item.get("country_code"), is_cup=bool(item.get("is_cup")),
                season_name=item.get("season_name"), logo=item.get("logo"))

    def _save_store(self) -> None:
        data = {key: {"external_id": c.external_id, "name": c.name, "country": c.country, "country_code": c.country_code,
                      "is_cup": c.is_cup, "season_name": c.season_name, "logo": c.logo}
                for key, c in self._competition_cache.items()}
        if data:
            self._store.set(COMPETITION_STORE_KEY, data, ttl=settings.MATCH_CACHE_TTL_COMPETITIONS, stale_ttl=30 * 24 * 3600)

    # ------------------------------------------------------------------ plumbing
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def _params(self, **extra: Any) -> Dict[str, Any]:
        if not self.is_configured():
            raise ProviderNotConfiguredError("Live Score API key/secret not configured (LIVESCORE_API_KEY / LIVESCORE_API_SECRET)", provider=self.name)
        params = {"key": self.api_key, "secret": self.api_secret}
        params.update({k: v for k, v in extra.items() if v is not None})
        return params

    def _throttle(self) -> None:
        """Live Score API answers HTTP 401 to bursts: keep at least MIN_REQUEST_INTERVAL between calls."""
        global _last_request_at
        with _throttle_lock:
            wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
            if wait > 0:
                time.sleep(wait)
            _last_request_at = time.monotonic()

    def _get(self, path: str, reason: str = "fetch", **params: Any) -> Dict[str, Any]:
        params = self._params(**params)
        attempts = 0
        while True:
            attempts += 1
            self._throttle()
            # The burst retry below is a second outbound request: the provider charges it, so it
            # is consumed and attributed as a retry rather than hidden inside the first one.
            self.budget.consume(1, reason=reason if attempts == 1 else "retry")
            try:
                payload = self.client.get_json(path, params)
                break
            except ProviderAuthError:
                # A rejected call right after other calls is usually the burst limit, not the credentials:
                # pause once and retry before reporting an authentication problem.
                if attempts >= 2:
                    raise
                logger.info("Live Score API: 401 after a burst of requests, retrying once after %.1fs", BURST_RETRY_DELAY)
                time.sleep(BURST_RETRY_DELAY)
        if not isinstance(payload, dict):
            raise ProviderUnavailableError("Live Score API returned a non-object payload", provider=self.name)
        if payload.get("success") is False or "error" in payload and not payload.get("success"):
            message = str(payload.get("error") or "unknown error")
            lowered = message.lower()
            if "key" in lowered or "secret" in lowered or "access" in lowered or "expired" in lowered:
                raise ProviderAuthError(f"Live Score API: {message}", provider=self.name)
            if "limit" in lowered or "quota" in lowered or "too many" in lowered:
                raise ProviderQuotaError(f"Live Score API: {message}", provider=self.name)
            raise ProviderUnavailableError(f"Live Score API: {message}", provider=self.name)
        return payload.get("data") or {}

    def _paginate(self, path: str, list_key: str, max_pages: int = MAX_PAGES, reason: str = "fetch",
                  **params: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            data = self._get(path, reason=reason if page == 1 else "page",
                             page=page if page > 1 else None, **params)
            chunk = data.get(list_key) or []
            items.extend(chunk)
            if not data.get("next_page") or not chunk:
                break
            page += 1
        return items

    # ------------------------------------------------------------------ mapping
    @staticmethod
    def _competition_from_payload(item: Dict[str, Any]) -> ProviderCompetition:
        countries = item.get("countries") or []
        country = countries[0].get("name") if countries else None
        country_code = countries[0].get("fifa_code") if countries else None
        federations = item.get("federations") or []
        if not country and federations:
            country = federations[0].get("name")
        season = item.get("season") or {}
        return ProviderCompetition(
            provider=PROVIDER_NAME,
            external_id=str(item.get("id")),
            name=str(item.get("name") or ""),
            key=None,
            country=country,
            country_code=country_code,
            is_cup=str(item.get("is_cup")) in ("1", "True", "true"),
            season_name=season.get("name"),
            raw=item,
        )

    @staticmethod
    def _team(payload: Dict[str, Any]) -> ProviderTeam:
        payload = payload or {}
        return ProviderTeam(
            provider=PROVIDER_NAME,
            external_id=str(payload.get("id")),
            name=str(payload.get("name") or "Unknown"),
            logo=payload.get("logo"),
        )

    def _competition_for_fixture(self, payload: Dict[str, Any], keys: Iterable[str]) -> ProviderCompetition:
        comp_payload = payload.get("competition") or {}
        external_id = str(comp_payload.get("id"))
        for key, comp in self._competition_cache.items():
            if comp.external_id == external_id:
                return comp
        country = (payload.get("country") or {}).get("name")
        key = comps.match_competition_name(comp_payload.get("name", ""), country=country, keys=keys)
        return ProviderCompetition(
            provider=PROVIDER_NAME, external_id=external_id, name=comp_payload.get("name", ""),
            key=key, country=country, is_cup=bool(comp_payload.get("is_cup")), raw=comp_payload,
        )

    def _fixture_from_scheduled(self, item: Dict[str, Any], keys: Iterable[str]) -> ProviderFixture:
        kickoff = parse_utc(f"{item.get('date')} {item.get('time') or '00:00:00'}") or datetime.now(timezone.utc)
        return ProviderFixture(
            provider=PROVIDER_NAME,
            external_id=str(item.get("id")),
            competition=self._competition_for_fixture(item, keys),
            home=self._team(item.get("home")),
            away=self._team(item.get("away")),
            kickoff_utc=kickoff,
            status=STATUS_SCHEDULED,
            venue=item.get("location"),
            round=str(item.get("round")) if item.get("round") not in (None, "") else None,
            raw=item,
        )

    def _fixture_from_match(self, item: Dict[str, Any], keys: Iterable[str]) -> ProviderFixture:
        """Live and history payloads share the `match` shape."""
        scores = item.get("scores") or {}
        home_score, away_score = parse_score(scores.get("score") or scores.get("ft_score"))
        ht_home, ht_away = parse_score(scores.get("ht_score"))
        status_text = str(item.get("status") or "").upper()
        status = LIVE_STATUS_MAP.get(status_text, STATUS_UNKNOWN)
        if status == STATUS_UNKNOWN and str(item.get("time") or "").upper() in ("FT", "AET", "AP"):
            status = STATUS_FINISHED
        day = item.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        kickoff = parse_utc(f"{day} {item.get('scheduled') or '00:00'}") or datetime.now(timezone.utc)
        fixture_id = item.get("fixture_id") or item.get("id")
        return ProviderFixture(
            provider=PROVIDER_NAME,
            external_id=str(fixture_id),
            competition=self._competition_for_fixture(item, keys),
            home=self._team(item.get("home")),
            away=self._team(item.get("away")),
            kickoff_utc=kickoff,
            status=status,
            minute=str(item.get("time")) if item.get("time") not in (None, "") else None,
            home_score=home_score, away_score=away_score,
            ht_home_score=ht_home, ht_away_score=ht_away,
            venue=item.get("location"),
            round=str(item.get("round")) if item.get("round") not in (None, "") else None,
            raw=item,
        )

    # ------------------------------------------------------------------ interface
    def list_competitions(self, keys: Iterable[str]) -> List[ProviderCompetition]:
        keys = list(keys)
        self._load_store()
        missing = [k for k in keys if k not in self._competition_cache]
        # Overrides and static defaults never need a network call
        for key in list(missing):
            override = self._overrides.get(key) or (
                str(comps.get(key).livescore_id) if self._use_default_ids and comps.get(key).livescore_id else None)
            if override:
                canonical = comps.get(key)
                self._competition_cache[key] = ProviderCompetition(
                    provider=PROVIDER_NAME, external_id=override, name=canonical.name, key=key,
                    country=canonical.country, country_code=canonical.country_code, is_cup=canonical.is_cup)
                missing.remove(key)
        if missing:
            # The full competition list is fetched at most once a day (persisted in Redis), so a deep
            # pagination cap is affordable here even though the endpoint may return many pages.
            items = self._paginate("competitions/list.json", "competition", reason="discovery",
                                   max_pages=COMPETITION_LIST_MAX_PAGES)
            parsed = [self._competition_from_payload(item) for item in items]
            resolved = comps.resolve_competitions(
                [(i, c.name, c.country, c.is_cup or None) for i, c in enumerate(parsed)], missing)
            for key, index in resolved.items():
                comp = parsed[index]
                comp.key = key
                self._competition_cache[key] = comp
                logger.info("Live Score API: resolved %s -> id %s (%s, %s)", key, comp.external_id, comp.name, comp.country)
        # Persist unconditionally, not only after a network lookup: ids that came from the static
        # defaults or from LIVESCORE_COMPETITION_IDS belong in the store too. Without them a key
        # this provider cannot resolve sends the next instance back through the paginated list.
        self._save_store()
        unresolved = [k for k in keys if k not in self._competition_cache]
        if unresolved:
            logger.warning("Live Score API: could not resolve competition ids for %s", unresolved)
        return [self._competition_cache[k] for k in keys if k in self._competition_cache]

    def _check_competition_name(self, comp: ProviderCompetition, items: List[Dict[str, Any]]) -> None:
        """Warn when a configured/recorded competition id returns fixtures of a different competition."""
        for item in items[:1]:
            raw_name = (item.get("competition") or {}).get("name")
            if raw_name and comp.key and comps.match_competition_name(raw_name, keys=[comp.key]) is None:
                logger.warning("Live Score API: competition id %s configured for %s returned '%s'; check LIVESCORE_COMPETITION_IDS",
                               comp.external_id, comp.key, raw_name)

    def get_fixtures(self, day: date, keys: Iterable[str]) -> List[ProviderFixture]:
        keys = list(keys)
        fixtures: List[ProviderFixture] = []
        for comp in self.list_competitions(keys):
            items = self._paginate("fixtures/list.json", "fixtures", date=day.strftime("%Y-%m-%d"),
                                   competition_id=comp.external_id)
            self._check_competition_name(comp, items)
            for item in items:
                fixture = self._fixture_from_scheduled(item, keys)
                fixture.competition = comp
                fixtures.append(fixture)
        return fixtures

    def get_upcoming(self, key: str, days_ahead: int = 14) -> List[ProviderFixture]:
        """fixtures/list.json without a date returns the competition calendar going forward (30/page)."""
        comps_found = self.list_competitions([key])
        if not comps_found:
            return []
        comp = comps_found[0]
        limit = datetime.now(timezone.utc).date() + timedelta(days=days_ahead)
        # The calendar is chronological and paginated (30 per page, whole season): stop as soon as a
        # page reaches past the window instead of downloading every remaining round.
        fixtures = []
        next_in_calendar: Optional[date] = None
        page = 1
        while page <= MAX_PAGES:
            data = self._get("fixtures/list.json", reason="fetch" if page == 1 else "page",
                             page=page if page > 1 else None, competition_id=comp.external_id)
            chunk = data.get("fixtures") or []
            if page == 1:
                self._check_competition_name(comp, chunk)
            past_window = False
            for item in chunk:
                fixture = self._fixture_from_scheduled(item, [key])
                fixture.competition = comp
                if fixture.kickoff_utc.date() <= limit:
                    fixtures.append(fixture)
                else:
                    past_window = True
                    day = fixture.kickoff_utc.date()
                    if next_in_calendar is None or day < next_in_calendar:
                        next_in_calendar = day
            if past_window or not data.get("next_page") or not chunk:
                break
            page += 1
        if not fixtures:
            # "The provider has no calendar for this competition" and "its next round is three
            # weeks out and we only looked seven days" arrive here as the same empty list, and on
            # 2026-09-21 it was the second: every covered league had fixtures, none before 9 October.
            # Those two want opposite responses - one is a broken integration, the other is just
            # September - so the answer says which, at the only place that still knows.
            logger.info("Live Score API: no %s fixture within %d day(s) of today (window ends %s); "
                        "the competition calendar's next fixture is %s",
                        key, days_ahead, limit.isoformat(),
                        next_in_calendar.isoformat() if next_in_calendar else "not listed at all")
        return fixtures

    def get_calendar_head(self, key: str, limit: int = 5) -> Optional[List[ProviderFixture]]:
        """The next fixtures of one competition, from ONE page of the dateless calendar.

        fixtures/list.json with no `date` answers with the competition's remaining calendar in
        kickoff order, 30 rows to a page. The earliest fixtures are therefore all on page one and
        no later page can hold an earlier one, so this reads page one and stops. Exactly one
        request, whatever the answer — which is the contract `MatchDataProvider.get_calendar_head`
        states and the reason a caller may afford it once per competition. It must not grow a
        pagination loop: `get_upcoming` is the method for a window that can span several pages.

        (Resolving `key` to a provider competition id is free for the covered competitions: those
        ids come from the static defaults or from the Redis store, never from the network.)

        A fixture is only offered when its kickoff can actually be read off the payload and is
        still ahead. A row whose date will not parse is dropped rather than carried: the fixture
        mapper dates such a row `now`, and a row dated `now` by a parsing failure would be
        presented to a reader as the very next match.
        """
        comps_found = self.list_competitions([key])
        if not comps_found:
            # The competition could not be identified, so nothing was asked and nothing is known.
            # An empty list here would claim the calendar is empty, which is a different fact.
            return None
        comp = comps_found[0]
        # Attributed as "calendar" rather than "fetch": this is the only spending a reader can
        # start by opening an empty day, and it is worth being able to read off the day's
        # `by_reason` counters on its own.
        data = self._get("fixtures/list.json", reason="calendar", competition_id=comp.external_id)
        items = data.get("fixtures") or []
        self._check_competition_name(comp, items)
        now = datetime.now(timezone.utc)
        fixtures: List[ProviderFixture] = []
        for item in items:
            kickoff = parse_utc(f"{item.get('date')} {item.get('time') or '00:00:00'}")
            if kickoff is None or kickoff <= now:
                continue
            fixture = self._fixture_from_scheduled(item, [key])
            fixture.competition = comp
            fixtures.append(fixture)
        fixtures.sort(key=lambda f: f.kickoff_utc)
        return fixtures[:max(int(limit), 0)]

    def get_live(self, keys: Iterable[str]) -> List[ProviderFixture]:
        keys = list(keys)
        wanted = {c.external_id: c for c in self.list_competitions(keys)}
        data = self._get("matches/live.json")
        result: List[ProviderFixture] = []
        for item in data.get("match") or []:
            comp_id = str((item.get("competition") or {}).get("id"))
            if comp_id not in wanted:
                continue
            fixture = self._fixture_from_match(item, keys)
            fixture.competition = wanted[comp_id]
            result.append(fixture)
        return result

    def get_results(self, date_from: date, date_to: date, keys: Iterable[str]) -> List[ProviderFixture]:
        keys = list(keys)
        results: List[ProviderFixture] = []
        for comp in self.list_competitions(keys):
            items = self._paginate("matches/history.json", "match", **{
                "from": date_from.strftime("%Y-%m-%d"), "to": date_to.strftime("%Y-%m-%d"),
                "competition_id": comp.external_id})
            for item in items:
                fixture = self._fixture_from_match(item, keys)
                fixture.competition = comp
                if fixture.status == STATUS_UNKNOWN:
                    fixture.status = STATUS_FINISHED
                results.append(fixture)
        return results

    def get_standings(self, key: str) -> List[ProviderStanding]:
        comp = self.list_competitions([key])
        if not comp:
            return []
        data = self._get("competitions/table.json", competition_id=comp[0].external_id, include_form=1)
        rows: List[Dict[str, Any]] = []
        if isinstance(data.get("table"), list):
            rows = data["table"]
        else:
            # cup competitions: one table per group
            for group in (data.get("tables") or data.get("groups") or []):
                if isinstance(group, dict):
                    rows.extend(group.get("table") or group.get("standings") or [])
        standings: List[ProviderStanding] = []
        for row in rows:
            team = row.get("team") or {}
            standings.append(ProviderStanding(
                position=int(row.get("rank") or len(standings) + 1),
                team=ProviderTeam(provider=PROVIDER_NAME, external_id=str(team.get("id")),
                                  name=str(team.get("name") or ""), logo=team.get("logo")),
                played=int(row.get("matches") or 0), won=int(row.get("won") or 0),
                drawn=int(row.get("drawn") or 0), lost=int(row.get("lost") or 0),
                goals_for=int(row.get("goals_scored") or 0), goals_against=int(row.get("goals_conceded") or 0),
                goal_difference=int(row.get("goal_diff") or 0), points=int(row.get("points") or 0),
                form=[str(f) for f in (row.get("form") or [])][-6:],
            ))
        return standings

    def get_fixture(self, external_id: str) -> Optional[ProviderFixture]:
        # Only live matches can be fetched by fixture id; scheduled fixtures come from the daily lists.
        try:
            data = self._get("matches/live.json", fixture_id=external_id)
        except ProviderUnavailableError:
            return None
        for item in data.get("match") or []:
            return self._fixture_from_match(item, list(comps.COMPETITIONS.keys()))
        return None

    # helpers used by the data service to decide whether polling live scores is worthwhile
    @staticmethod
    def live_window(kickoff_utc: datetime, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return kickoff_utc - timedelta(minutes=15) <= now <= kickoff_utc + timedelta(minutes=150)
