"""
Deterministic sample providers for local development, automated tests and UI verification.

They never call the network and are only used when DATA_PROVIDER / PREDICTION_PROVIDER are set to
"sample". Everything they return is labelled provider="sample" so it can never be confused with
real data.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, List

from app.services.providers import competitions as comps
from app.services.providers.base import (
    STATUS_FINISHED, STATUS_LIVE, STATUS_SCHEDULED,
    ForecastProvider, MatchDataProvider, ProviderCompetition, ProviderFixture, ProviderForecast,
    ProviderStanding, ProviderTeam,
)

PROVIDER_NAME = "sample"

SAMPLE_TEAMS = {
    "premier_league": ["Arsenal", "Chelsea", "Liverpool", "Manchester City", "Tottenham Hotspur", "Newcastle United"],
    "la_liga": ["Real Madrid", "Barcelona", "Atletico Madrid", "Sevilla", "Real Sociedad", "Villarreal"],
    "serie_a": ["Inter Milan", "AC Milan", "Juventus", "Napoli", "Roma", "Atalanta"],
    "bundesliga": ["Bayern Munich", "Borussia Dortmund", "Bayer Leverkusen", "RB Leipzig", "Eintracht Frankfurt", "Stuttgart"],
    "ligue_1": ["Paris Saint-Germain", "Marseille", "Lyon", "Monaco", "Lille", "Nice"],
    "champions_league": ["Real Madrid", "Manchester City", "Bayern Munich", "Inter Milan", "Paris Saint-Germain", "Arsenal"],
}


def _team(key: str, name: str) -> ProviderTeam:
    external_id = f"{key}-{name.lower().replace(' ', '-')}"
    return ProviderTeam(provider=PROVIDER_NAME, external_id=external_id, name=name, logo="/teams/default.svg",
                        country=comps.get(key).country)


def _competition(key: str) -> ProviderCompetition:
    c = comps.get(key)
    return ProviderCompetition(provider=PROVIDER_NAME, external_id=f"sample-{key}", name=c.name, key=key,
                               country=c.country, country_code=c.country_code, is_cup=c.is_cup, logo="/leagues/default.svg")


def sample_fixtures(day: date, keys: Iterable[str], now: datetime = None) -> List[ProviderFixture]:
    """Two fixtures per competition per day: one at 15:00 UTC and one at 19:45 UTC."""
    now = now or datetime.now(timezone.utc)
    fixtures: List[ProviderFixture] = []
    for key in keys:
        teams = SAMPLE_TEAMS[key]
        offset = (day.toordinal() % 3)
        pairs = [(teams[offset % 6], teams[(offset + 1) % 6]), (teams[(offset + 2) % 6], teams[(offset + 3) % 6])]
        for index, (home, away) in enumerate(pairs):
            kickoff = datetime.combine(day, time(15, 0) if index == 0 else time(19, 45), tzinfo=timezone.utc)
            status = STATUS_SCHEDULED
            home_score = away_score = None
            minute = None
            if kickoff + timedelta(minutes=150) < now:
                status, home_score, away_score = STATUS_FINISHED, (index + offset) % 3, (index + 1) % 2
            elif kickoff <= now:
                status, home_score, away_score = STATUS_LIVE, 1, 0
                minute = str(int((now - kickoff).total_seconds() // 60))
            fixtures.append(ProviderFixture(
                provider=PROVIDER_NAME, external_id=f"sample-{key}-{day.isoformat()}-{index}",
                competition=_competition(key), home=_team(key, home), away=_team(key, away),
                kickoff_utc=kickoff, status=status, minute=minute, home_score=home_score, away_score=away_score,
                venue=f"{home} Stadium", round=f"Matchday {day.isocalendar()[1]}",
            ))
    return fixtures


class SampleDataProvider(MatchDataProvider):
    name = PROVIDER_NAME
    integration_status = "sample data (not real)"

    def __init__(self, now: datetime = None):
        self._now = now

    def is_configured(self) -> bool:
        return True

    def list_competitions(self, keys: Iterable[str]) -> List[ProviderCompetition]:
        return [_competition(k) for k in keys]

    def get_fixtures(self, day: date, keys: Iterable[str]) -> List[ProviderFixture]:
        return sample_fixtures(day, keys, self._now)

    def get_live(self, keys: Iterable[str]) -> List[ProviderFixture]:
        now = self._now or datetime.now(timezone.utc)
        return [f for f in sample_fixtures(now.date(), keys, now) if f.status == STATUS_LIVE]

    def get_results(self, date_from: date, date_to: date, keys: Iterable[str]) -> List[ProviderFixture]:
        results: List[ProviderFixture] = []
        day = date_from
        while day <= date_to:
            results.extend(f for f in sample_fixtures(day, keys, self._now) if f.status == STATUS_FINISHED)
            day += timedelta(days=1)
        return results

    def get_standings(self, key: str) -> List[ProviderStanding]:
        rows = []
        for position, name in enumerate(SAMPLE_TEAMS[key], start=1):
            played = 6
            won = max(6 - position, 0)
            drawn = 1 if position < 6 else 0
            lost = played - won - drawn
            rows.append(ProviderStanding(position=position, team=_team(key, name), played=played, won=won, drawn=drawn,
                                         lost=lost, goals_for=20 - position * 2, goals_against=6 + position,
                                         goal_difference=(20 - position * 2) - (6 + position), points=won * 3 + drawn,
                                         form=["W", "D", "L"][:3]))
        return rows


class SampleForecastProvider(ForecastProvider):
    name = PROVIDER_NAME
    integration_status = "sample data (not real)"

    def is_configured(self) -> bool:
        return True

    def get_forecasts(self, key: str, date_from: date, date_to: date) -> List[ProviderForecast]:
        forecasts: List[ProviderForecast] = []
        retrieved_at = datetime.now(timezone.utc)   # one retrieval time for the whole response
        day = date_from
        while day <= date_to:
            for index, fixture in enumerate(sample_fixtures(day, [key])):
                if fixture.status != STATUS_SCHEDULED:
                    continue
                home = 0.55 if index == 0 else 0.38
                forecasts.append(ProviderForecast(
                    provider=PROVIDER_NAME, external_event_id=f"sample-forecast-{fixture.external_id}",
                    home_name=fixture.home.name, away_name=fixture.away.name, kickoff_utc=fixture.kickoff_utc,
                    competition_name=fixture.competition.name, competition_key=key,
                    home_prob=home, draw_prob=0.25, away_prob=round(1 - home - 0.25, 4),
                    btts_yes_prob=0.52, btts_no_prob=0.48, over_25_prob=0.57, under_25_prob=0.43,
                    reasoning="Sample forecast for local development; not a real model output.",
                    model_run_at=retrieved_at, provider_updated_at=retrieved_at, fetched_at=retrieved_at,
                ))
            day += timedelta(days=1)
        return forecasts
