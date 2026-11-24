"""gnomAD v4 population allele frequency tool via GraphQL."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from via.cache import DiskCache
from via.schema import ToolResult, Variant
from via.tools._common import elapsed_ms, fetch_json_cached

GNOMAD_API_URL = "https://gnomad.broadinstitute.org/api"
_SKIP_POP_IDS = frozenset({"XX", "XY", "remaining"})


def _compute_popmax(exome: dict[str, Any], genome: dict[str, Any]) -> tuple[float | None, str | None]:
    totals: dict[str, list[int]] = {}
    for source in (exome, genome):
        for pop in source.get("populations") or []:
            if not isinstance(pop, dict):
                continue
            pid = pop.get("id")
            if not isinstance(pid, str) or pid in _SKIP_POP_IDS or pid.endswith(("_XX", "_XY")):
                continue
            ac = pop.get("ac") or 0
            an = pop.get("an") or 0
            acc = totals.setdefault(pid, [0, 0])
            acc[0] += int(ac)
            acc[1] += int(an)

    best_af: float | None = None
    best_an = -1
    best_pid: str | None = None
    for pid, (ac_sum, an_sum) in totals.items():
        if an_sum <= 0:
            continue
        af = ac_sum / an_sum
        if (
            best_af is None
            or af > best_af
            or (af == best_af and (an_sum > best_an or (an_sum == best_an and pid < (best_pid or ""))))
        ):
            best_af = af
            best_an = an_sum
            best_pid = pid
    return best_af, best_pid


def gnomad_frequency(
    variant: Variant,
    *,
    call_id: str = "call_002_gnomad_frequency",
    cache: DiskCache | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ToolResult:
    """Query gnomAD v4 GraphQL API for exome, genome, combined, and popmax frequencies."""
    t0 = time.perf_counter()
    query = (
        '{variant(variantId:"%s", dataset:gnomad_r4){'
        "variant_id "
        "exome{ac an af filters populations{id ac an}} "
        "genome{ac an af filters populations{id ac an}}"
        "}}"
    ) % variant.gnomad_id

    from_cache, payload, early = fetch_json_cached(
        call_id=call_id,
        tool="gnomad_frequency",
        method="POST",
        url=GNOMAD_API_URL,
        cache_namespace="gnomad_frequency",
        cache_key=variant.gnomad_id,
        cache=cache,
        client=client,
        sleep_fn=sleep_fn,
        headers={"Content-Type": "application/json"},
        json_body={"query": query},
    )
    if early is not None:
        return early

    if not isinstance(payload, dict):
        return ToolResult(
            call_id=call_id,
            tool="gnomad_frequency",
            status="error",
            cached=False,
            error="Unexpected non-object GraphQL response",
            source_url=GNOMAD_API_URL,
            elapsed_ms=elapsed_ms(t0),
        )

    errors = payload.get("errors") or []
    variant_node = (payload.get("data") or {}).get("variant")

    if variant_node is None:
        messages = [str(e.get("message", "")) for e in errors if isinstance(e, dict)]
        if not errors or any("variant not found" in m.lower() for m in messages):
            if not from_cache and cache is not None:
                cache.set("gnomad_frequency", variant.gnomad_id, "not_found", None)
            return ToolResult(
                call_id=call_id,
                tool="gnomad_frequency",
                status="not_found",
                cached=from_cache,
                source_url=GNOMAD_API_URL,
                elapsed_ms=elapsed_ms(t0),
            )
        return ToolResult(
            call_id=call_id,
            tool="gnomad_frequency",
            status="error",
            cached=False,
            error="; ".join(m for m in messages if m) or "gnomAD GraphQL error",
            source_url=GNOMAD_API_URL,
            elapsed_ms=elapsed_ms(t0),
        )

    if errors:
        messages = [str(e.get("message", "")) for e in errors if isinstance(e, dict)]
        return ToolResult(
            call_id=call_id,
            tool="gnomad_frequency",
            status="error",
            cached=False,
            error="; ".join(m for m in messages if m) or "gnomAD GraphQL error",
            source_url=GNOMAD_API_URL,
            elapsed_ms=elapsed_ms(t0),
        )

    if not from_cache and cache is not None:
        cache.set("gnomad_frequency", variant.gnomad_id, "found", payload)

    exome = variant_node.get("exome") or {}
    genome = variant_node.get("genome") or {}
    exome_ac = exome.get("ac")
    exome_an = exome.get("an")
    exome_af = exome.get("af")
    genome_ac = genome.get("ac")
    genome_an = genome.get("an")
    genome_af = genome.get("af")

    combined_ac = (exome_ac or 0) + (genome_ac or 0)
    combined_an = (exome_an or 0) + (genome_an or 0)
    combined_af = (combined_ac / combined_an) if combined_an > 0 else None
    filters = sorted(set(exome.get("filters") or []) | set(genome.get("filters") or []))
    popmax_af, popmax_population = _compute_popmax(exome, genome)

    data = {
        "variant_id": variant_node.get("variant_id", variant.gnomad_id),
        "dataset": "gnomad_r4",
        "exome_ac": exome_ac,
        "exome_an": exome_an,
        "exome_af": exome_af,
        "genome_ac": genome_ac,
        "genome_an": genome_an,
        "genome_af": genome_af,
        "combined_ac": combined_ac if combined_an > 0 else None,
        "combined_an": combined_an if combined_an > 0 else None,
        "combined_af": combined_af,
        "filters": filters,
        "popmax_af": popmax_af,
        "popmax_population": popmax_population,
    }
    return ToolResult(
        call_id=call_id,
        tool="gnomad_frequency",
        status="found",
        cached=from_cache,
        data=data,
        source_url=GNOMAD_API_URL,
        elapsed_ms=elapsed_ms(t0),
    )
