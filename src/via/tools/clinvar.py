"""ClinVar E-utilities lookup tool (strictly disabled in eval mode, P1)."""

from __future__ import annotations

import time
import urllib.parse
from typing import Any, Callable

import httpx

from via.cache import DiskCache
from via.http import make_client, request_with_retry
from via.schema import ToolResult, Variant
from via.tools._common import elapsed_ms
from via.tools.errors import EvalModeLeakageError

CLINVAR_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def _review_stars(review_status: str) -> int:
    rs = review_status.strip().lower()
    if "practice guideline" in rs:
        return 4
    if "reviewed by expert panel" in rs:
        return 3
    if "multiple submitters, no conflicts" in rs:
        return 2
    if "single submitter" in rs or "conflicting" in rs:
        return 1
    return 0


def _matches_variant(record: dict[str, Any], variant: Variant) -> bool:
    for vs in record.get("variation_set") or []:
        if not isinstance(vs, dict):
            continue
        spdi = str(vs.get("canonical_spdi") or "")
        parts = spdi.split(":")
        if len(parts) != 4 or not parts[1].isdigit():
            continue
        if int(parts[1]) != variant.pos - 1:
            continue
        if parts[2].upper() != variant.ref or parts[3].upper() != variant.alt:
            continue
        for loc in vs.get("variation_loc") or []:
            if not isinstance(loc, dict):
                continue
            if (
                loc.get("assembly_name") == "GRCh38"
                and str(loc.get("chr")) == variant.chrom
                and str(loc.get("start")) == str(variant.pos)
            ):
                return True
    return False


def _extract_clinvar_data(record: dict[str, Any]) -> dict[str, Any]:
    germ = record.get("germline_classification") or {}
    review_status = str(germ.get("review_status") or "")
    conditions = [
        str(trait["trait_name"])
        for trait in (germ.get("trait_set") or [])
        if isinstance(trait, dict) and trait.get("trait_name")
    ]
    return {
        "accession": record.get("accession"),
        "title": record.get("title"),
        "classification": germ.get("description") or None,
        "review_status": review_status or None,
        "stars": _review_stars(review_status),
        "last_evaluated": germ.get("last_evaluated") or None,
        "conditions": conditions,
    }


def clinvar_lookup(
    variant: Variant,
    *,
    eval_mode: bool = False,
    call_id: str = "call_006_clinvar_lookup",
    cache: DiskCache | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ToolResult:
    """Query NCBI ClinVar for germline classification. Fails loudly in eval_mode."""
    if eval_mode:
        raise EvalModeLeakageError("clinvar_lookup is disabled in eval mode (P1)")

    t0 = time.perf_counter()
    term = urllib.parse.quote(f"{variant.chrom}[chr] AND {variant.pos}[chrpos38]")
    esearch_url = f"{CLINVAR_EUTILS_BASE}/esearch.fcgi?db=clinvar&term={term}&retmode=json"

    if cache is not None:
        hit, cached_status, cached_payload = cache.get("clinvar_lookup", variant.canonical_id)
        if hit:
            if cached_status == "not_found":
                return ToolResult(
                    call_id=call_id,
                    tool="clinvar_lookup",
                    status="not_found",
                    cached=True,
                    source_url=esearch_url,
                    elapsed_ms=elapsed_ms(t0),
                )
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="found",
                cached=True,
                data=cached_payload,
                source_url=esearch_url,
                elapsed_ms=elapsed_ms(t0),
            )

    owns_client = client is None
    active_client = make_client() if owns_client else client
    try:
        try:
            es_resp = request_with_retry(active_client, "GET", esearch_url, sleep_fn=sleep_fn)
        except httpx.HTTPError as exc:
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                source_url=esearch_url,
                elapsed_ms=elapsed_ms(t0),
            )

        if es_resp.status_code != 200:
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="error",
                error=f"HTTP {es_resp.status_code}",
                source_url=esearch_url,
                elapsed_ms=elapsed_ms(t0),
            )

        try:
            es_json = es_resp.json()
        except ValueError as exc:
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="error",
                error=f"Invalid JSON from esearch: {exc}",
                source_url=esearch_url,
                elapsed_ms=elapsed_ms(t0),
            )

        idlist = [str(i) for i in ((es_json.get("esearchresult") or {}).get("idlist") or [])[:20]]
        if not idlist:
            if cache is not None:
                cache.set("clinvar_lookup", variant.canonical_id, "not_found", None)
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="not_found",
                source_url=esearch_url,
                elapsed_ms=elapsed_ms(t0),
            )

        esum_url = f"{CLINVAR_EUTILS_BASE}/esummary.fcgi?db=clinvar&id={','.join(idlist)}&retmode=json"
        try:
            sum_resp = request_with_retry(active_client, "GET", esum_url, sleep_fn=sleep_fn)
        except httpx.HTTPError as exc:
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                source_url=esum_url,
                elapsed_ms=elapsed_ms(t0),
            )

        if sum_resp.status_code != 200:
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="error",
                error=f"HTTP {sum_resp.status_code}",
                source_url=esum_url,
                elapsed_ms=elapsed_ms(t0),
            )

        try:
            sum_json = sum_resp.json()
        except ValueError as exc:
            return ToolResult(
                call_id=call_id,
                tool="clinvar_lookup",
                status="error",
                error=f"Invalid JSON from esummary: {exc}",
                source_url=esum_url,
                elapsed_ms=elapsed_ms(t0),
            )

        result_map = sum_json.get("result") or {}
        for cid in idlist:
            record = result_map.get(cid)
            if isinstance(record, dict) and _matches_variant(record, variant):
                data = _extract_clinvar_data(record)
                if cache is not None:
                    cache.set("clinvar_lookup", variant.canonical_id, "found", data)
                return ToolResult(
                    call_id=call_id,
                    tool="clinvar_lookup",
                    status="found",
                    data=data,
                    source_url=esum_url,
                    elapsed_ms=elapsed_ms(t0),
                )

        if cache is not None:
            cache.set("clinvar_lookup", variant.canonical_id, "not_found", None)
        return ToolResult(
            call_id=call_id,
            tool="clinvar_lookup",
            status="not_found",
            source_url=esum_url,
            elapsed_ms=elapsed_ms(t0),
        )
    finally:
        if owns_client:
            active_client.close()
