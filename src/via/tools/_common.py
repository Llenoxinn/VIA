"""Shared helper for timing, disk-cache lookup, HTTP execution, and error wrapping."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from via.cache import DiskCache, SanitizerFn
from via.http import make_client, request_with_retry
from via.schema import ToolResult


def elapsed_ms(start: float) -> int:
    """Return integer milliseconds elapsed since start."""
    return max(0, int((time.perf_counter() - start) * 1000))


def fetch_json_cached(
    *,
    call_id: str,
    tool: str,
    method: str,
    url: str,
    cache_namespace: str,
    cache_key: str,
    cache: DiskCache | None,
    client: httpx.Client | None,
    sleep_fn: Callable[[float], None],
    sanitizer: SanitizerFn | None = None,
    not_found_statuses: frozenset[int] = frozenset({404}),
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[bool, Any, ToolResult | None]:
    """Return (from_cache, raw_payload, terminal_result_if_not_found_or_error).

    When terminal_result_if_not_found_or_error is None, raw_payload is ready to parse.
    """
    t0 = time.perf_counter()

    if cache is not None:
        hit, cached_status, cached_payload = cache.get(cache_namespace, cache_key, sanitizer=sanitizer)
        if hit:
            if cached_status == "not_found":
                return True, None, ToolResult(
                    call_id=call_id,
                    tool=tool,
                    status="not_found",
                    cached=True,
                    source_url=url,
                    elapsed_ms=elapsed_ms(t0),
                )
            return True, cached_payload, None

    owns_client = client is None
    active_client = make_client() if owns_client else client
    try:
        resp = request_with_retry(
            active_client,
            method,
            url,
            sleep_fn=sleep_fn,
            headers=headers,
            json=json_body,
        )
    except httpx.HTTPError as exc:
        return False, None, ToolResult(
            call_id=call_id,
            tool=tool,
            status="error",
            cached=False,
            error=f"{type(exc).__name__}: {exc}",
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )
    finally:
        if owns_client:
            active_client.close()

    if resp.status_code in not_found_statuses:
        if cache is not None:
            cache.set(cache_namespace, cache_key, "not_found", None, sanitizer=sanitizer)
        return False, None, ToolResult(
            call_id=call_id,
            tool=tool,
            status="not_found",
            cached=False,
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    if resp.status_code < 200 or resp.status_code >= 300:
        return False, None, ToolResult(
            call_id=call_id,
            tool=tool,
            status="error",
            cached=False,
            error=f"HTTP {resp.status_code}",
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    try:
        parsed = resp.json()
    except ValueError as exc:
        return False, None, ToolResult(
            call_id=call_id,
            tool=tool,
            status="error",
            cached=False,
            error=f"Invalid JSON response: {exc}",
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    if sanitizer is not None:
        parsed = sanitizer(parsed)
    return False, parsed, None
