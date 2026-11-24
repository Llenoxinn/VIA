"""Ensembl VEP consequence tool with strict ClinVar/HGMD/COSMIC stripping (P1)."""

from __future__ import annotations

import re
import time
from typing import Any, Callable

import httpx

from via.cache import DiskCache
from via.schema import ToolResult, Variant
from via.tools._common import elapsed_ms, fetch_json_cached
from via.tools._sanitize import strip_vep_payload

VEP_BASE_URL = "https://rest.ensembl.org/vep/human/region"


def _pick_transcript(transcripts: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not transcripts:
        return None
    for tx in transcripts:
        if tx.get("canonical") == 1:
            return tx
    for tx in transcripts:
        if tx.get("biotype") == "protein_coding":
            return tx
    return transcripts[0]


def _extract_uniprot_accession(tx: dict[str, Any]) -> str | None:
    swissprot = tx.get("swissprot") or []
    for item in swissprot:
        if isinstance(item, str) and item.strip():
            return item.strip().split(".", 1)[0]
    isoforms = tx.get("uniprot_isoform") or []
    for item in isoforms:
        if isinstance(item, str) and item.strip():
            return re.sub(r"-\d+$", "", item.strip())
    return None


def vep_consequence(
    variant: Variant,
    *,
    call_id: str = "call_001_vep_consequence",
    cache: DiskCache | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ToolResult:
    """Query Ensembl VEP for consequence, canonical transcript, and UniProt mapping."""
    t0 = time.perf_counter()
    url = (
        f"{VEP_BASE_URL}/{variant.chrom}:{variant.pos}-{variant.pos}:1/{variant.alt}"
        "?canonical=1&uniprot=1&hgvs=1"
    )
    from_cache, payload, early = fetch_json_cached(
        call_id=call_id,
        tool="vep_consequence",
        method="GET",
        url=url,
        cache_namespace="vep_consequence",
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
            cache.set("vep_consequence", variant.canonical_id, "not_found", None, sanitizer=strip_vep_payload)
        return ToolResult(
            call_id=call_id,
            tool="vep_consequence",
            status="not_found",
            cached=from_cache,
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    entry = strip_vep_payload(entry)
    transcripts = [t for t in (entry.get("transcript_consequences") or []) if isinstance(t, dict)]
    tx = _pick_transcript(transcripts)
    if tx is None:
        if not from_cache and cache is not None:
            cache.set("vep_consequence", variant.canonical_id, "not_found", None, sanitizer=strip_vep_payload)
        return ToolResult(
            call_id=call_id,
            tool="vep_consequence",
            status="not_found",
            cached=from_cache,
            source_url=url,
            elapsed_ms=elapsed_ms(t0),
        )

    if not from_cache and cache is not None:
        cache.set("vep_consequence", variant.canonical_id, "found", entry, sanitizer=strip_vep_payload)

    consequence_terms = list(tx.get("consequence_terms") or [])
    data = {
        "gene_symbol": tx.get("gene_symbol"),
        "gene_id": tx.get("gene_id"),
        "transcript_id": tx.get("transcript_id"),
        "canonical": tx.get("canonical") == 1,
        "most_severe_consequence": entry.get("most_severe_consequence"),
        "consequence_terms": consequence_terms,
        "is_missense": "missense_variant" in consequence_terms,
        "impact": tx.get("impact"),
        "amino_acids": tx.get("amino_acids"),
        "protein_start": tx.get("protein_start"),
        "protein_end": tx.get("protein_end"),
        "codons": tx.get("codons"),
        "hgvsc": tx.get("hgvsc"),
        "hgvsp": tx.get("hgvsp"),
        "uniprot_accession": _extract_uniprot_accession(tx),
        "sift_score": tx.get("sift_score"),
        "sift_prediction": tx.get("sift_prediction"),
        "polyphen_score": tx.get("polyphen_score"),
        "polyphen_prediction": tx.get("polyphen_prediction"),
    }
    return ToolResult(
        call_id=call_id,
        tool="vep_consequence",
        status="found",
        cached=from_cache,
        data=data,
        source_url=url,
        elapsed_ms=elapsed_ms(t0),
    )
