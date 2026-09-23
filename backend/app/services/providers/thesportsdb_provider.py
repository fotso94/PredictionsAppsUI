"""
TheSportsDB provider (https://www.thesportsdb.com) — RETAINED fallback, UNTESTED against live data.

Uses the v1 JSON API with the key from THESPORTSDB_KEY ("123" = free test key with truncated
results; a Patreon key is required for production use). Endpoints:
- eventsnextleague.php?id=   (next 15 events of a league)
- eventspastleague.php?id=   (last 15 events)
- lookuptable.php?l=&s=      (league table)
No live scores in v1 (v2 only). Statuses come from strStatus/strTimestamp.

No period breakdown: v1 supplies a single final score (intHomeScore/intAwayScore) and nothing
that separates 90 minutes from extra time or a shootout, so `ft_*`/`et_*`/`ps_*` on the fixtures
built here stay None. That is recorded rather than guessed at: a knockout tie from this provider
therefore settles on its only stored score, which is wrong for a tie decided in extra time.
Fixing it needs a v2 payload to read, not a field name invented here.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.core.config import settings
from app.services.providers import competitions as comps
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_LIVE, STATUS_POSTPONED, STATUS_CANCELLED, STATUS_SCHEDULED,
    MatchDataProvider, ProviderCompetition, ProviderFixture, ProviderNotConfiguredError,
    ProviderStanding, ProviderTeam, parse_utc,
)
from app.services.providers.budget import RequestBudget
from app.services.providers.http import ProviderHttpClient

logger = logging.getLogger(__name__)

PROVIDER_NAME = "thesportsdb"
BASE_URL = "https://www.thesportsdb.com/api/v1/json"


def _season_label(today: Optional[date] = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    start = today.year - 1 if today.month < 7 else today.year
    return f"{start}-{start + 1}"


def _status(item: Dict[str, Any], kickoff: datetime) -> str:
    text = str(item.get("strStatus") or "").lower()
    if "postpon" in text:
        return STATUS_POSTPONED
    if "cancel" in text or "abandon" in text:
        return STATUS_CANCELLED
    if "finished" in text or "ft" == text or item.get("intHomeScore") not in (None, ""):
        return STATUS_FINISHED
    if text in ("1h", "2h", "ht", "live", "in play"):
        return STATUS_LIVE
    return STATUS_SCHEDULED


class TheSportsDBProvider(MatchDataProvider):
    name = PROVIDER_NAME
    integration_status = "retained (v1 API, untested, no live scores)"

    def __init__(self, api_key: Optional[str] = None, transport=None, budget: Optional[RequestBudget] = None):
        self.api_key = api_key if api_key is not None else settings.THESPORTSDB_KEY
        self.client = ProviderHttpClient(PROVIDER_NAME, f"{BASE_URL}/{self.api_key or '123'}", transport=transport)
        self.budget = budget or RequestBudget(PROVIDER_NAME, 1000)

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, reason: str = "fetch", **params: Any) -> Dict[str, Any]:
        if not self.is_configured():
            raise ProviderNotConfiguredError("TheSportsDB key not configured (THESPORTSDB_KEY)", provider=self.name)
        self.budget.consume(1, reason=reason)
        payload = self.client.get_json(path, params)
        return payload if isinstance(payload, dict) else {}

    def _fixture(self, item: Dict[str, Any], key: str) -> ProviderFixture:
        canonical = comps.get(key)
        kickoff = parse_utc(item.get("strTimestamp")) or parse_utc(f"{item.get('dateEvent')} {item.get('strTime') or '00:00:00'}") \
            or datetime.now(timezone.utc)

        def score(value: Any) -> Optional[int]:
            try:
                return int(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return ProviderFixture(
            provider=PROVIDER_NAME,
            external_id=str(item.get("idEvent")),
            competition=ProviderCompetition(provider=PROVIDER_NAME, external_id=str(item.get("idLeague") or canonical.thesportsdb_id),
                                            name=item.get("strLeague") or canonical.name, key=key, country=canonical.country,
                                            is_cup=canonical.is_cup),
            home=ProviderTeam(provider=PROVIDER_NAME, external_id=str(item.get("idHomeTeam")), name=item.get("strHomeTeam", ""),
                              logo=item.get("strHomeTeamBadge")),
            away=ProviderTeam(provider=PROVIDER_NAME, external_id=str(item.get("idAwayTeam")), name=item.get("strAwayTeam", ""),
                              logo=item.get("strAwayTeamBadge")),
            kickoff_utc=kickoff,
            status=_status(item, kickoff),
            home_score=score(item.get("intHomeScore")), away_score=score(item.get("intAwayScore")),
            venue=item.get("strVenue"),
            round=str(item.get("intRound")) if item.get("intRound") not in (None, "") else None,
            raw=item,
        )

    def list_competitions(self, keys: Iterable[str]) -> List[ProviderCompetition]:
        result = []
        for key in keys:
            canonical = comps.get(key)
            if canonical.thesportsdb_id:
                result.append(ProviderCompetition(provider=PROVIDER_NAME, external_id=str(canonical.thesportsdb_id),
                                                  name=canonical.name, key=key, country=canonical.country, is_cup=canonical.is_cup))
        return result

    def _events(self, key: str, path: str) -> List[ProviderFixture]:
        canonical = comps.get(key)
        if not canonical.thesportsdb_id:
            return []
        payload = self._get(path, id=canonical.thesportsdb_id)
        return [self._fixture(item, key) for item in (payload.get("events") or [])]

    def get_fixtures(self, day: date, keys: Iterable[str]) -> List[ProviderFixture]:
        fixtures: List[ProviderFixture] = []
        for key in keys:
            for fixture in self._events(key, "eventsnextleague.php"):
                if fixture.kickoff_utc.date() == day:
                    fixtures.append(fixture)
        return fixtures

    def get_live(self, keys: Iterable[str]) -> List[ProviderFixture]:
        return []  # v1 has no livescores

    def get_results(self, date_from: date, date_to: date, keys: Iterable[str]) -> List[ProviderFixture]:
        results: List[ProviderFixture] = []
        for key in keys:
            for fixture in self._events(key, "eventspastleague.php"):
                if date_from <= fixture.kickoff_utc.date() <= date_to:
                    fixture.status = STATUS_FINISHED
                    results.append(fixture)
        return results

    def get_standings(self, key: str) -> List[ProviderStanding]:
        canonical = comps.get(key)
        if not canonical.thesportsdb_id:
            return []
        payload = self._get("lookuptable.php", l=canonical.thesportsdb_id, s=_season_label())
        standings = []
        for row in payload.get("table") or []:
            standings.append(ProviderStanding(
                position=int(row.get("intRank") or 0),
                team=ProviderTeam(provider=PROVIDER_NAME, external_id=str(row.get("idTeam")), name=row.get("strTeam", ""),
                                  logo=row.get("strBadge") or row.get("strTeamBadge")),
                played=int(row.get("intPlayed") or 0), won=int(row.get("intWin") or 0), drawn=int(row.get("intDraw") or 0),
                lost=int(row.get("intLoss") or 0), goals_for=int(row.get("intGoalsFor") or 0),
                goals_against=int(row.get("intGoalsAgainst") or 0), goal_difference=int(row.get("intGoalDifference") or 0),
                points=int(row.get("intPoints") or 0), form=list(row.get("strForm") or "")[-6:],
            ))
        return standings
