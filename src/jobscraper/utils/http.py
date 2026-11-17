"""Shared HTTP client with small, predictable retry behavior."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from .errors import FetchError

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class HttpClient:
    """A thin wrapper around ``httpx.Client`` used by sources and providers.

    A transport can be injected for offline tests. Retries are intentionally
    conservative and only apply to transport errors, 429, and 5xx responses.
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        retries: int = 2,
        user_agent: str = "jobscraper/0.1",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.retries = max(0, retries)
        self.sleep = sleep
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            },
        )

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        response = self._request("GET", url, headers=headers)
        return response.text

    def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        response = self._request("GET", url, headers=headers)
        return _decode_json(response)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        response = self._request("POST", url, json=payload, headers=headers)
        return _decode_json(response)

    def delay(self, seconds: float) -> None:
        """Politely space out requests when configured by the caller."""
        if seconds > 0:
            self.sleep(seconds)

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        _validate_url(url)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self._client.request(method, url, json=json, headers=headers)
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < self.retries:
                    self.sleep(_backoff(attempt))
                    continue
                raise FetchError(f"Request failed for {url}: {exc}") from exc

            if response.status_code in _RETRYABLE_STATUS and attempt < self.retries:
                retry_after = _retry_after_seconds(response)
                self.sleep(retry_after if retry_after is not None else _backoff(attempt))
                continue
            if response.is_error:
                body = response.text[:400].replace("\n", " ")
                raise FetchError(f"Request to {url} returned HTTP {response.status_code}: {body}")
            return response
        raise FetchError(f"Request failed for {url}: {last_error}")


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise FetchError(f"Unsupported URL: {url!r}")


def _decode_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        body = response.text[:200].replace("\n", " ")
        raise FetchError(f"Expected JSON from {response.url}, got: {body!r}") from exc


def _backoff(attempt: int) -> float:
    return min(4.0, 0.5 * (2**attempt))


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "").strip()
    if not value:
        return None
    try:
        return min(30.0, max(0.0, float(value)))
    except ValueError:
        return None
