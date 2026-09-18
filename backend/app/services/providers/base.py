"""
Provider abstractions and normalised data transfer objects.

All providers (Live Score API, GameForecastAPI, API-Football, TheSportsDB, sample data)
translate their payloads into these DTOs so the rest of the backend never depends on a
specific vendor's schema.
"""

from __future__ import annotations

import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base class for provider failures."""

    def __init__(self, message: str, provider: str = "", status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class ProviderNotConfiguredError(ProviderError):
    """Credentials or mandatory settings are missing."""


class ProviderAuthError(ProviderError):
    """The provider rejected the credentials (expired trial, wrong key...)."""


class ProviderQuotaError(ProviderError):
    """The provider (or our own daily budget) refused the request because of quota limits."""


class ProviderUnavailableError(ProviderError):
    """Network failure, 5xx or malformed payload."""


# ---------------------------------------------------------------------------
# Normalised match statuses
# ---------------------------------------------------------------------------

STATUS_SCHEDULED = "scheduled"
STATUS_LIVE = "live"
STATUS_HALFTIME = "halftime"
STATUS_FINISHED = "finished"
STATUS_POSTPONED = "postponed"
STATUS_CANCELLED = "cancelled"
STATUS_UNKNOWN = "unknown"

ALL_STATUSES = (
    STATUS_SCHEDULED, STATUS_LIVE, STATUS_HALFTIME, STATUS_FINISHED,
    STATUS_POSTPONED, STATUS_CANCELLED, STATUS_UNKNOWN,
)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

@dataclass
class ProviderCompetition:
    provider: str
    external_id: str
    name: str
    key: Optional[str] = None            # canonical key (premier_league, ...) when recognised
    country: Optional[str] = None
    country_code: Optional[str] = None
    is_cup: bool = False
    season_name: Optional[str] = None
    logo: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderTeam:
    provider: str
    external_id: str
    name: str
    logo: Optional[str] = None
    country: Optional[str] = None
    short_name: Optional[str] = None


@dataclass
class ProviderFixture:
    provider: str
    external_id: str
    competition: ProviderCompetition
    home: ProviderTeam
    away: ProviderTeam
    kickoff_utc: datetime
    status: str = STATUS_SCHEDULED
    minute: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    ht_home_score: Optional[int] = None
    ht_away_score: Optional[int] = None
    venue: Optional[str] = None
    round: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderStanding:
    position: int
    team: ProviderTeam
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0
    form: List[str] = field(default_factory=list)


@dataclass
class ProviderForecast:
    """A third-party model forecast for one fixture. Probabilities are 0-1 floats or None."""
    provider: str
    external_event_id: str
    home_name: str
    away_name: str
    kickoff_utc: Optional[datetime]
    competition_name: Optional[str] = None
    competition_external_id: Optional[str] = None
    competition_key: Optional[str] = None
    home_external_id: Optional[str] = None
    away_external_id: Optional[str] = None
    home_prob: Optional[float] = None
    draw_prob: Optional[float] = None
    away_prob: Optional[float] = None
    btts_yes_prob: Optional[float] = None
    btts_no_prob: Optional[float] = None
    over_25_prob: Optional[float] = None
    under_25_prob: Optional[float] = None
    over_35_prob: Optional[float] = None
    under_35_prob: Optional[float] = None
    exact_score: Optional[Dict[str, float]] = None
    recommended_bets: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    model_run_at: Optional[datetime] = None
    provider_updated_at: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def has_any_market(self) -> bool:
        return any(v is not None for v in (
            self.home_prob, self.draw_prob, self.away_prob,
            self.btts_yes_prob, self.over_25_prob, self.over_35_prob,
        ))


# ---------------------------------------------------------------------------
# Provider interfaces
# ---------------------------------------------------------------------------

class MatchDataProvider(ABC):
    """Fixtures, live scores, results, standings and competitions."""

    name: str = "abstract"
    #: Human-readable status of the integration: "primary", "retained", "sample"
    integration_status: str = "retained"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def list_competitions(self, keys: Iterable[str]) -> List[ProviderCompetition]:
        """Resolve the canonical competition keys to provider competitions."""

    @abstractmethod
    def get_fixtures(self, day: date, keys: Iterable[str]) -> List[ProviderFixture]:
        """Fixtures (any status) kicking off on the given UTC date for the competitions."""

    @abstractmethod
    def get_live(self, keys: Iterable[str]) -> List[ProviderFixture]:
        """Matches currently in play for the competitions."""

    @abstractmethod
    def get_results(self, date_from: date, date_to: date, keys: Iterable[str]) -> List[ProviderFixture]:
        """Finished matches in the date range (inclusive)."""

    @abstractmethod
    def get_standings(self, key: str) -> List[ProviderStanding]: ...

    def get_fixture(self, external_id: str) -> Optional[ProviderFixture]:
        """Single fixture by provider id (optional capability)."""
        return None

    def get_upcoming(self, key: str, days_ahead: int = 14) -> List[ProviderFixture]:
        """Upcoming fixtures of one competition. Default: one call per day via get_fixtures."""
        from datetime import timedelta
        today = datetime.now(timezone.utc).date()
        fixtures: List[ProviderFixture] = []
        for offset in range(days_ahead + 1):
            fixtures.extend(self.get_fixtures(today + timedelta(days=offset), [key]))
        return fixtures


class ForecastProvider(ABC):
    """Third-party match forecasts."""

    name: str = "abstract"
    integration_status: str = "retained"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def get_forecasts(self, key: str, date_from: date, date_to: date) -> List[ProviderForecast]:
        """Forecasts for fixtures of the canonical competition kicking off in the date range."""


# ---------------------------------------------------------------------------
# Helpers shared by providers
# ---------------------------------------------------------------------------

def to_probability(value: Any) -> Optional[float]:
    """
    Convert a provider probability to a 0-1 float.

    Accepts fractions (0.65), percentages (65 or "65%") and strings. Values outside
    0-100 or non-numeric values return None so they are reported as unavailable instead
    of being guessed.
    """
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().rstrip("%")
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    if number <= 1.0:
        return round(number, 4)
    if number <= 100.0:
        return round(number / 100.0, 4)
    return None


def parse_utc(value: Any) -> Optional[datetime]:
    """Parse ISO-8601 strings (with or without offset) into aware UTC datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    dt = None  # type: ignore[assignment]
            if dt is None:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_score(text: Any) -> Tuple[Optional[int], Optional[int]]:
    """Parse "2 - 1" style scores; returns (None, None) when absent."""
    if not text or not isinstance(text, str):
        return None, None
    parts = [p.strip() for p in text.replace("–", "-").split("-")]
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
