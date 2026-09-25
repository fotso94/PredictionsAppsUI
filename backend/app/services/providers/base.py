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

from app.core.redaction import redact_credentials


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Base class for provider failures.

    The message is redacted here, once, for every provider: it is stored in the Redis status
    payload that GET /api/v1/data-providers/status serves and in a match's recovery
    `last_provider_error`, and it is built from text we do not control - an httpx error, a
    provider's error body - which may quote the request URL, and Live Score's URL carries the key
    and secret.
    """

    def __init__(self, message: str, provider: str = "", status_code: Optional[int] = None):
        super().__init__(redact_credentials(message) if isinstance(message, str) else message)
        self.provider = provider
        self.status_code = status_code


class ProviderNotConfiguredError(ProviderError):
    """Credentials or mandatory settings are missing."""


class ProviderAuthError(ProviderError):
    """The provider rejected the credentials (expired trial, wrong key...)."""


class ProviderQuotaError(ProviderError):
    """The provider (or our own daily budget) refused the request because of quota limits."""


class ProviderRequestNotSent(ProviderQuotaError):
    """An allowance refused a request BEFORE it left: nothing was sent, so nothing was unreachable.

    Raised by `RequestBudget.consume` when our own daily ceiling is spent, when the provider's own
    reported window says it is spent, or when there is no counter store to meter against and the
    budget fails closed; and by `MatchDataService._call_chain` when a caller's `skip` declines a
    provider. It is a `ProviderQuotaError`, so everything that already treats a quota refusal as
    one keeps doing so. What it adds is the one fact a quota error cannot carry: no request was
    made, which is the difference between "the allowance was spent" and "the provider did not
    answer", and the recovery bookkeeping records those two as different outcomes.

    `refused_by` says whose limit it was: "ours" (a ceiling this installation configured, or its
    refusal to spend unmetered) or "provider" (the provider's own reported window).
    """

    def __init__(self, message: str, provider: str = "", status_code: Optional[int] = None,
                 refused_by: str = "ours"):
        super().__init__(message, provider=provider, status_code=status_code)
        self.refused_by = refused_by


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
# "this did not end at 90 minutes"
# ---------------------------------------------------------------------------

#: Free-text markers a source may put in a minute/period/status field to say the match carried on
#: past 90 minutes plus stoppage. "AP" is Live Score API's marker for a tie decided on penalties
#: and reads on a real row as `time: "AP"`; "AET" is its marker for one decided in extra time.
#: Defined here, with the DTO that first sees them, and imported by everything downstream that
#: reads a stored marker, so one spelling is recognised in one place.
BEYOND_REGULATION_MARKERS = frozenset({
    "aet", "ap", "pen", "et", "after extra time", "after_extra_time",
    "extra_time", "extra time", "penalties", "pens", "after penalties",
})


def marks_beyond_regulation(value: Any) -> bool:
    """Is this free-text value one of the markers meaning the match went past 90 minutes?

    False for anything that is not a recognised marker, including None and "FT". That is not a
    claim the match ended at 90 - an unrecognised marker says nothing either way - so a caller
    deciding "did this go beyond regulation" must not read False here as a No.
    """
    return isinstance(value, str) and value.strip().lower() in BEYOND_REGULATION_MARKERS


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
    """One fixture as a provider describes it.

    The scoreline is carried as separate PERIODS, because a knockout tie has more than one and
    they mean different things. ``home_score``/``away_score`` are the scoreline on display: the
    running score while the match is in play, and once it is over the score of the football that
    was played, extra time included. That is the number a reader wants and the wrong number to
    settle a market on, so the periods are kept apart rather than collapsed into it:

    * ``ft_*`` is REGULATION time, 90 minutes plus stoppage. Markets settle on this and on
      nothing else, so a provider must only populate it from a field it actually labels full
      time - never from a general "score" field, which after extra time is the extra-time score.
    * ``et_*`` is the score after extra time and ``ps_*`` the penalty shoot-out. Both are the
      true result of the tie and are carried so a reader can be shown it; neither settles
      anything.

    ``None`` means "this provider did not supply this period" everywhere here, and a period that
    was not supplied is never substituted with another one *in storage*: nothing downstream writes
    an ``et_*`` score into an ``ft_*`` column, or the tie's score into either. Settlement is a
    separate question with a separate answer - a finished match that nothing says went past 90
    minutes is settled on its stored score, because for such a match that score IS the regulation
    score - and :func:`app.services.settlement.regulation_score` states and justifies that rule
    where it is applied.
    """
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
    ft_home_score: Optional[int] = None
    ft_away_score: Optional[int] = None
    et_home_score: Optional[int] = None
    et_away_score: Optional[int] = None
    ps_home_score: Optional[int] = None
    ps_away_score: Optional[int] = None
    venue: Optional[str] = None
    round: Optional[str] = None
    #: Does this provider enumerate a finished match's periods, so that a period it left empty was
    #: NOT PLAYED rather than not reported? Live Score API does: its `scores` object always carries
    #: `et_score` and `ps_score`, "" when the match ended at 90. Providers that send only the
    #: periods that happened leave this False, and their silence stays "we were not told".
    periods_reported: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)
    #: Did the provider STATE this kickoff, date and time, or did the mapping have to fill part of
    #: it in? The captured `matches/history.json` reply in
    #: docs/evidence/livescore-history-2026-09-16-la-liga.json carries a `date` and no `scheduled`
    #: time, and `matches/live.json` rows have been observed with `date` null; the mapping still
    #: needs a datetime, so it uses midnight or today, and that value is a placeholder rather than
    #: a report. A fixture carrying
    #: one may still be matched and stored, but it never moves a kickoff a stored row already holds.
    kickoff_supplied: bool = True

    @property
    def went_beyond_regulation(self) -> Optional[bool]:
        """Did this tie carry on past 90 minutes plus stoppage? True, False, or None for unknown.

        Three answers, because there are three situations and only two of them are knowledge:

        * ``True`` - evidence that it did: a score for extra time or for a shoot-out, or a period
          marker that says so ("AET", "AP").
        * ``False`` - evidence that it did NOT: this provider enumerates the periods of a finished
          match (``periods_reported``), and the beyond-regulation ones came back empty. Only a
          provider that would have told us is allowed to be read as telling us.
        * ``None`` - nobody said. A provider that sends only the periods that happened, one that
          sends no periods at all, and a match still in play all land here. This is NOT False:
          "the tie did not go past 90" and "we do not know whether it did" are different claims,
          and only the first of them may ever be stored as a fact about the tie.
        """
        if any(v is not None for v in (self.et_home_score, self.et_away_score,
                                       self.ps_home_score, self.ps_away_score)):
            return True
        if marks_beyond_regulation(self.minute):
            return True
        if self.periods_reported and self.status == STATUS_FINISHED:
            return False
        return None


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
    #: Remainder probability the provider assigns to every scoreline it does not list
    #: ("other" bucket). Kept separate so it is never rendered as a scoreline and so a
    #: partial score list is never renormalised to imply certainty.
    exact_score_other_prob: Optional[float] = None
    recommended_bets: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    model_run_at: Optional[datetime] = None
    provider_updated_at: Optional[datetime] = None
    #: When WE retrieved this forecast from the provider (UTC), stamped at parse time by the
    #: provider itself. It must never be taken at attach/persist time: doing so stamps a forecast
    #: that was read from a cache minutes or hours ago as freshly retrieved.
    fetched_at: Optional[datetime] = None
    #: Consistency problems detected in the provider payload (sums out of tolerance,
    #: values dropped because they were out of bounds). Reported, never silently fixed.
    anomalies: List[Dict[str, str]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def has_any_market(self) -> bool:
        return any(v is not None for v in (
            self.home_prob, self.draw_prob, self.away_prob,
            self.btts_yes_prob, self.btts_no_prob,
            self.over_25_prob, self.under_25_prob,
            self.over_35_prob, self.under_35_prob,
        )) or bool(self.exact_score)

    def markets(self) -> Dict[str, bool]:
        """Which markets this forecast actually supplies, for unavailable-vs-zero rendering."""
        return {
            "match_result": any(v is not None for v in (self.home_prob, self.draw_prob, self.away_prob)),
            "btts": any(v is not None for v in (self.btts_yes_prob, self.btts_no_prob)),
            "over_under_25": any(v is not None for v in (self.over_25_prob, self.under_25_prob)),
            "over_under_35": any(v is not None for v in (self.over_35_prob, self.under_35_prob)),
            "exact_score": bool(self.exact_score),
        }


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

    def get_calendar_head(self, key: str, limit: int = 5) -> Optional[List[ProviderFixture]]:
        """The earliest fixtures still to come in one competition's calendar, or None.

        Answers "when does this competition play again, and against whom" for a competition that
        has nothing inside the few days the fixtures task looks at. The caller asks it once per
        competition, so the contract is a hard ONE request per call: no pagination, no widening
        window, no walking forward a day at a time.

        `None` means this provider cannot answer under that contract, and the caller must treat it
        as "we do not know" rather than as "there is nothing". Returning None is the default
        precisely because `get_upcoming` above would answer it by asking for `days_ahead + 1`
        separate days — eighteen days of silence across six competitions is over a hundred
        requests for a sentence in an empty state, which is not a trade any caller should be able
        to make by accident. A provider whose API has a dateless calendar endpoint overrides this;
        one that has only a per-day endpoint leaves it alone.

        An empty LIST is a different answer again: the provider was asked, answered, and listed no
        fixture to come. That is a real fact about the calendar, and the caller may say so.
        """
        return None


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

#: Default scale for provider probabilities: percentages (0-100). Providers publishing unit
#: fractions pass scale=1.0 explicitly.
PERCENT_SCALE = 100.0


def to_probability(value: Any, scale: float = PERCENT_SCALE) -> Optional[float]:
    """
    Convert one provider probability to a 0-1 float on an EXPLICIT scale.

    `scale` is the caller's documented contract with the provider (100.0 for percentages,
    1.0 for unit fractions). It is never inferred from the magnitude of the value: inferring
    it silently turns a genuine 1% into 100% certainty.

    Returns None - meaning "market unavailable" - for anything that is not a finite number
    inside 0..scale. Nothing is guessed, clamped or rescaled.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if value.endswith("%"):
            value = value[:-1].strip()
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):  # NaN / +-inf
        return None
    if number < 0 or number > scale:
        return None
    return round(number / scale, 4)


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
