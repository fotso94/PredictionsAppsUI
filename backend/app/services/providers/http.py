"""Small httpx wrapper shared by providers (timeouts, error translation, test transport)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.services.providers.base import (
    ProviderAuthError,
    ProviderQuotaError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0


class ProviderHttpClient:
    """GET-only JSON client. Pass `transport=httpx.MockTransport(...)` in tests."""

    def __init__(self, provider: str, base_url: str, headers: Optional[Dict[str, str]] = None,
                 transport: Optional[httpx.BaseTransport] = None, timeout: float = DEFAULT_TIMEOUT):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.transport = transport
        self.timeout = timeout

    def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(transport=self.transport, timeout=self.timeout, headers=self.headers) as client:
                response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(f"{self.provider}: network error: {exc}", provider=self.provider) from exc

        status = response.status_code
        if status in (401, 403):
            raise ProviderAuthError(f"{self.provider}: authentication rejected (HTTP {status})",
                                    provider=self.provider, status_code=status)
        if status == 429:
            raise ProviderQuotaError(f"{self.provider}: rate limit or quota exceeded (HTTP 429)",
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
