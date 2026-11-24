"""AlphaMissense pathogenicity score tool via Ensembl VEP AlphaMissense plugin."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from via.cache import DiskCache
from via.schema import ToolResult, Variant
from via.tools._common import elapsed_ms, fetch_json_cached
from via.tools._sanitize import strip_vep_payload
from via.tools.vep import VEP_BASE_URL


def _pick_am_transcript(transcripts: list[dict[str, Any]]) -> dict[str, Any] | None:
    def has_am(tx: dict[str, Any]) -> bool:
        am = tx.get("alphamissense")
        return isinstance(am, dict) and am.get("am_pathogenicity") is not None

    for tx in transcripts:
        if tx.get("canonical") == 1 and has_am(tx):
            return tx
    for tx in transcripts:
        if has_am(tx):
            return tx
    return None


def alphamissense_score(
    variant: Variant,
    *,
    call_id: str = "call_003_alphamissense_score",
    cache: DiskCache | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ToolResult:
    """Query Ensembl VEP AlphaMissense plugin for the 0-1 missense score."""
    t0 = time.perf_counter()
    url = (
        f"{VEP_BASE_URL}/{variant.chrom}:{variant.pos}-{variant.pos}:1/{variant.alt}"
        "?AlphaMissense=1&canonical=1"
    )
    from_cache, payload, early = fetch_json_cached(
        call_id=call_id,
        tool="alphamissense_score",
        method="GET",
        url=url,
        cache_namespace="alphamissense_score",
        cache_key=variant.canonical_id,
        cache=cache,
        client=client,
        sleep_fn=sleep_fn,
        sanitizer=strip_vep_payload,
        headers={"Accept": "application/json"},
    )
    if early is not None:
        return early

    entry: dict[str, Any] | None = None
    if isinstance(payload, list):
        entry = payload[0] if payload and isinstance(payload[0], dict) else None
    elif isinstance(payload, dict):
        entry = payload

    if entry is None:
        if not from_cache and cache is not None:
            cache.set("alphamissense_score", variant.canonical_id, "not_found", None, sanitizer=strip_vep_payload)
        return ToolResult(
            call_id=call_id,
            tool="alphamissense_score",
            status="not_found",
            cached=from_cache,
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    entry = strip_vep_payload(entry)
    transcripts = [t for t in (entry.get("transcript_consequences") or []) if isinstance(t, dict)]
    tx = _pick_am_transcript(transcripts)
    if tx is None:
        if not from_cache and cache is not None:
            cache.set("alphamissense_score", variant.canonical_id, "not_found", None, sanitizer=strip_vep_payload)
        return ToolResult(
            call_id=call_id,
            tool="alphamissense_score",
            status="not_found",
            cached=from_cache,
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    if not from_cache and cache is not None:
        cache.set("alphamissense_score", variant.canonical_id, "found", entry, sanitizer=strip_vep_payload)

    am = tx["alphamissense"]
    data = {
        "score": float(am["am_pathogenicity"]),
        "am_class": am.get("am_class"),
        "transcript_id": tx.get("transcript_id"),
        "gene_symbol": tx.get("gene_symbol"),
        "source": "ensembl_vep_alphamissense",
    }
    return ToolResult(
        call_id=call_id,
        tool="alphamissense_score",
        status="found",
        cached=from_cache,
        data=data,
        source_url=url,
        elapsed_ms=elapsed_ms(t0),
    )
