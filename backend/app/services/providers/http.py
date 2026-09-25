"""Small httpx wrapper shared by providers (timeouts, error translation, test transport).

It also reads the provider's OWN accounting off every response it gets. RapidAPI returns three
headers on success and on refusal alike, and they cost nothing - they arrive on responses already
paid for:

    x-ratelimit-requests-limit      the plan's ceiling for the provider's window
    x-ratelimit-requests-remaining  what is left in that window
    x-ratelimit-requests-reset      seconds until that window resets

Reading them is the difference between knowing the provider's window and guessing it. On
2026-09-19 the GameForecastAPI daily counter, keyed by UTC day, started a clean pass at 00:01:10Z
and the provider refused the third request of that "day" with HTTP 429 while our own counter still
showed five of eight left: the provider's window is not the UTC calendar day, and it had been
telling us so on every response we ever made.

Parsing is strictly best effort. The headers are optional, their names vary in case, their values
may be absent, empty or unparseable, and a provider may send none at all. Nothing here may fail a
request: a malformed header is ignored and the call carries on exactly as it did before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import httpx

from app.core.redaction import redact_credentials
from app.services.providers.base import (
    ProviderAuthError,
    ProviderQuotaError,
    ProviderUnavailableError,
)
from app.services.providers.budget import record_rate_limit

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0

#: RapidAPI's per-window accounting, lower-cased. Lookup is case-insensitive either way.
LIMIT_HEADER = "x-ratelimit-requests-limit"
REMAINING_HEADER = "x-ratelimit-requests-remaining"
RESET_HEADER = "x-ratelimit-requests-reset"

#: The reset header is documented as SECONDS until the window turns. A value beyond this is not a
#: rate-limit window - the likeliest reading is an absolute epoch timestamp from some other
#: provider's dialect - and it is discarded rather than believed: taken at face value, 1.8e9
#: "seconds" would pause this provider for fifty-seven years.
MAX_RESET_SECONDS = 7 * 24 * 3600


def _header(headers: Any, name: str) -> Optional[str]:
    """One header by lower-cased name, from httpx.Headers or any plain mapping. Never raises."""
    try:
        value = headers.get(name)
        if value is not None:
            return value
    except Exception:  # pragma: no cover - a mapping that will not be asked
        pass
    try:
        items = headers.items()
    except Exception:  # pragma: no cover
        return None
    for key, value in items:
        try:
            if str(key).strip().lower() == name:
                return value
        except Exception:  # pragma: no cover
            continue
    return None


def _header_int(value: Any) -> Optional[int]:
    """A header's integer value, or None when the provider did not say anything usable.

    None means "unknown", and unknown is never 0: a missing remaining-count that read as zero
    would refuse every request for a provider that simply does not publish the header.
    """
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        pass
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):  # NaN / infinities
        return None
    return int(number)


def _non_negative(value: Optional[int]) -> Optional[int]:
    """Counts and durations cannot be negative; a negative one is a value we cannot read."""
    return value if value is not None and value >= 0 else None


def _plausible_reset(value: Optional[int]) -> Optional[int]:
    """A reset we can believe as a duration, or None. See :data:`MAX_RESET_SECONDS`."""
    return value if value is not None and value <= MAX_RESET_SECONDS else None


@dataclass(frozen=True)
class RateLimitReading:
    """What one response said about the provider's own window. Only what it actually said.

    Every field is optional because every header is optional. A reading is one response's word,
    never an accumulation: a fresh `remaining` is never combined with a ceiling read hours ago,
    because the two would then describe a window neither response reported.
    """

    provider: str
    limit: Optional[int] = None
    remaining: Optional[int] = None
    reset_seconds: Optional[int] = None
    observed_at: Optional[datetime] = None
    status_code: Optional[int] = None

    @property
    def known(self) -> bool:
        """True when the provider published at least one of the three numbers."""
        return any(v is not None for v in (self.limit, self.remaining, self.reset_seconds))

    @property
    def reset_at(self) -> Optional[datetime]:
        """The instant the provider's window resets, or None when it did not say.

        Anchored to when the response was observed, because the header is a duration: storing the
        duration alone would keep reading "resets in 3 hours" for as long as it is stored.
        """
        if self.reset_seconds is None or self.observed_at is None:
            return None
        return self.observed_at + timedelta(seconds=self.reset_seconds)

    def to_dict(self) -> Dict[str, Any]:
        reset_at = self.reset_at
        return {
            "provider": self.provider,
            "limit": self.limit,
            "remaining": self.remaining,
            "reset_seconds": self.reset_seconds,
            "reset_at": reset_at.isoformat() if reset_at else None,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "observed_status": self.status_code,
        }


def parse_rate_limit(provider: str, response: Any, now: Optional[datetime] = None) -> RateLimitReading:
    """Read the three rate-limit headers off a response. Never raises, whatever it is handed."""
    observed_at = now or datetime.now(timezone.utc)
    status_code = getattr(response, "status_code", None)
    headers: Any = getattr(response, "headers", None)
    if headers is None or not (hasattr(headers, "get") or hasattr(headers, "items")):
        return RateLimitReading(provider=provider, observed_at=observed_at, status_code=status_code)
    return RateLimitReading(
        provider=provider,
        limit=_non_negative(_header_int(_header(headers, LIMIT_HEADER))),
        remaining=_non_negative(_header_int(_header(headers, REMAINING_HEADER))),
        reset_seconds=_plausible_reset(_non_negative(_header_int(_header(headers, RESET_HEADER)))),
        observed_at=observed_at,
        status_code=status_code,
    )


class ProviderHttpClient:
    """GET-only JSON client. Pass `transport=httpx.MockTransport(...)` in tests."""

    def __init__(self, provider: str, base_url: str, headers: Optional[Dict[str, str]] = None,
                 transport: Optional[httpx.BaseTransport] = None, timeout: float = DEFAULT_TIMEOUT,
                 rate_limit_sink: Optional[Callable[[RateLimitReading], None]] = None,
                 now: Optional[Callable[[], datetime]] = None):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.transport = transport
        self.timeout = timeout
        #: Where a reading is persisted. Default: the per-provider store in `budget`, which is
        #: what survives the restart this scheduler goes through. Tests pass their own.
        self.rate_limit_sink = rate_limit_sink if rate_limit_sink is not None else record_rate_limit
        self._now = now
        #: The last reading taken, for a caller that wants it without going to the store.
        #: None until a response carries at least one of the headers.
        self.last_rate_limit: Optional[RateLimitReading] = None

    def _note_rate_limit(self, response: Any) -> Optional[RateLimitReading]:
        """Read and store the provider's own accounting. Best effort in the strongest sense.

        Called on every response, success and refusal alike - the 429 is the most informative one
        we get, because it is the only response that states the window we actually hit. Any
        failure here (an unreadable header, a store that will not answer) is swallowed: this is
        bookkeeping about a request that has already happened and must never change its outcome.
        """
        try:
            reading = parse_rate_limit(self.provider, response,
                                       now=self._now() if callable(self._now) else self._now)
            if not reading.known:
                return None
            self.last_rate_limit = reading
            if self.rate_limit_sink is not None:
                self.rate_limit_sink(reading)
            return reading
        except Exception as exc:  # pragma: no cover - defensive; never fails a request
            logger.debug("Rate-limit headers from %s could not be read: %s", self.provider, exc)
            return None

    @staticmethod
    def _upstream_message(response: httpx.Response) -> str:
        """Short, credential-free excerpt of the provider's own error text (e.g. 'not subscribed')."""
        try:
            payload = response.json()
        except ValueError:
            payload = None
        text = None
        if isinstance(payload, dict):
            for field in ("error", "message", "detail", "msg"):
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    text = value.strip()
                    break
        if text is None:
            text = (response.text or "").strip()
        if not text:
            return ""
        text = redact_credentials(text)
        return f": {text[:160]}"

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout, headers=self.headers) as client:
                response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"{self.provider}: network error: {exc}", provider=self.provider) from exc

        # Before anything can raise: the refusals are exactly the responses whose accounting is
        # worth most, and a 429 that threw before being read is a window we never learn about.
        self._note_rate_limit(response)

        status = response.status_code
        if status in (401, 403):
            raise ProviderAuthError(f"{self.provider}: authentication rejected (HTTP {status}){self._upstream_message(response)}",
                                    provider=self.provider, status_code=status)
        if status == 429:
            raise ProviderQuotaError(f"{self.provider}: rate limit or quota exceeded (HTTP 429){self._upstream_message(response)}",
                                     provider=self.provider, status_code=status)
        if status >= 500:
            raise ProviderUnavailableError(f"{self.provider}: upstream error (HTTP {status})",
                                           provider=self.provider, status_code=status)
        if status >= 400:
            raise ProviderUnavailableError(f"{self.provider}: request rejected (HTTP {status}): {response.text[:200]}",
                                           provider=self.provider, status_code=status)
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderUnavailableError(f"{self.provider}: invalid JSON payload", provider=self.provider) from exc
