"""UniProt protein domains and functional sites tool (leakage-safe fields only, P1)."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from via.cache import DiskCache
from via.schema import ToolResult
from via.tools._common import elapsed_ms, fetch_json_cached

# Only structural and functional annotation fields; excludes ft_variant, ft_mutagen, and cc_disease (P1).
SAFE_UNIPROT_FIELDS = (
    "accession,id,gene_names,sequence,"
    "ft_domain,ft_act_site,ft_binding,ft_site,ft_region,ft_motif,ft_repeat,ft_zn_fing,ft_disulfid,ft_mod_res"
)
UNIPROT_BASE_URL = "https://rest.uniprot.org/uniprotkb"
DOMAIN_TYPES = frozenset({"Domain", "Zinc finger", "Region", "Repeat", "Motif"})


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def uniprot_features(
    accession: str,
    residue: int,
    *,
    call_id: str = "call_004_uniprot_features",
    cache: DiskCache | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ToolResult:
    """Query UniProtKB for domains and functional annotations at a protein residue."""
    t0 = time.perf_counter()
    acc = accession.strip()
    url = f"{UNIPROT_BASE_URL}/{acc}.json?fields={SAFE_UNIPROT_FIELDS}"
    if not acc or residue < 1:
        return ToolResult(
            call_id=call_id,
            tool="uniprot_features",
            status="not_found",
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    from_cache, payload, early = fetch_json_cached(
        call_id=call_id,
        tool="uniprot_features",
        method="GET",
        url=url,
        cache_namespace="uniprot_entry",
        cache_key=acc,
        cache=cache,
        client=client,
        sleep_fn=sleep_fn,
        headers={"Accept": "application/json"},
    )
    if early is not None:
        return early

    if not isinstance(payload, dict) or not payload.get("primaryAccession"):
        if not from_cache and cache is not None:
            cache.set("uniprot_entry", acc, "not_found", None)
        return ToolResult(
            call_id=call_id,
            tool="uniprot_features",
            status="not_found",
            cached=from_cache,
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    if not from_cache and cache is not None:
        cache.set("uniprot_entry", acc, "found", payload)

    genes = payload.get("genes") or []
    gene_symbol = None
    if genes and isinstance(genes[0], dict):
        gene_symbol = (genes[0].get("geneName") or {}).get("value")

    overlapping: list[dict[str, Any]] = []
    domains: list[dict[str, Any]] = []
    for feat in payload.get("features") or []:
        if not isinstance(feat, dict):
            continue
        loc = feat.get("location") or {}
        start = _int_or_none((loc.get("start") or {}).get("value"))
        end = _int_or_none((loc.get("end") or {}).get("value"))
        if start is None or end is None:
            continue
        ftype = str(feat.get("type") or "")
        entry = {
            "type": ftype,
            "start": start,
            "end": end,
            "description": str(feat.get("description") or ""),
        }
        if start <= residue <= end:
            overlapping.append(entry)
        if ftype in DOMAIN_TYPES:
            domains.append(entry)

    data = {
        "accession": payload.get("primaryAccession", acc),
        "entry_id": payload.get("uniProtkbId"),
        "gene_symbol": gene_symbol,
        "protein_length": (payload.get("sequence") or {}).get("length"),
        "residue": residue,
        "overlapping_features": overlapping,
        "domains": domains,
    }
    return ToolResult(
        call_id=call_id,
        tool="uniprot_features",
        status="found",
        cached=from_cache,
        data=data,
        source_url=url,
        elapsed_ms=elapsed_ms(t0),
    )
