"""HTTP client utilities with polite User-Agent and bounded transient retries."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

USER_AGENT = "via-variant-agent/0.1"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def make_client(timeout: float = 20.0) -> httpx.Client:
    """Create a configured httpx.Client with VIA's polite User-Agent."""
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})


def _retry_delay(resp: httpx.Response | None, attempt: int, backoff_base: float) -> float:
    if resp is not None:
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            try:
                parsed = float(retry_after.strip())
                if parsed >= 0:
                    return min(parsed, 5.0)
            except ValueError:
                pass
    return backoff_base * (2**attempt)


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    retries: int = 2,
    backoff_base: float = 0.5,
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """Issue an HTTP request, retrying transient network and 429/5xx responses."""
    for attempt in range(retries + 1):
        try:
            resp = client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt >= retries:
                raise
            sleep_fn(_retry_delay(None, attempt, backoff_base))
            continue

        if resp.status_code in RETRYABLE_STATUS_CODES and attempt < retries:
            sleep_fn(_retry_delay(resp, attempt, backoff_base))
            continue
        return resp

    raise AssertionError("unreachable")
