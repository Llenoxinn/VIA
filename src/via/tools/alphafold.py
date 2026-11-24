"""AlphaFold DB per-residue pLDDT structure confidence tool."""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from via.cache import DiskCache
from via.http import make_client
from via.schema import ToolResult
from via.tools._common import elapsed_ms, fetch_json_cached

ALPHAFOLD_API_URL = "https://alphafold.ebi.ac.uk/api/prediction"
_CATEGORY_MAP = {
    "H": "very_high",
    "M": "confident",
    "L": "low",
    "D": "very_low",
}


def _select_entry(entries: list[Any], acc: str, residue: int) -> dict[str, Any] | None:
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            continue
        if item.get("uniprotAccession") != acc:
            continue
        start = item.get("uniprotStart")
        end = item.get("uniprotEnd")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= residue <= end and item.get("plddtDocUrl"):
            margin = min(residue - start, end - residue)
            is_canonical_f1 = 1 if item.get("entryId") == f"AF-{acc}-F1" else 0
            candidates.append((margin, is_canonical_f1, item))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return candidates[0][2]


def _confidence_band(score: float, category: Any) -> str:
    if isinstance(category, str) and category.strip().upper() in _CATEGORY_MAP:
        return _CATEGORY_MAP[category.strip().upper()]
    if score >= 90.0:
        return "very_high"
    if score >= 70.0:
        return "confident"
    if score >= 50.0:
        return "low"
    return "very_low"


def alphafold_plddt(
    accession: str,
    residue: int,
    *,
    call_id: str = "call_005_alphafold_plddt",
    cache: DiskCache | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ToolResult:
    """Query AlphaFold DB for per-residue pLDDT structural confidence."""
    t0 = time.perf_counter()
    acc = accession.strip()
    meta_url = f"{ALPHAFOLD_API_URL}/{acc}"
    if not acc or residue < 1:
        return ToolResult(
            call_id=call_id,
            tool="alphafold_plddt",
            status="not_found",
            source_url=meta_url,
            elapsed_ms=elapsed_ms(t0),
        )

    owns_client = client is None
    active_client = make_client() if owns_client else client
    try:
        meta_cached, meta_payload, meta_early = fetch_json_cached(
            call_id=call_id,
            tool="alphafold_plddt",
            method="GET",
            url=meta_url,
            cache_namespace="alphafold_meta",
            cache_key=acc,
            cache=cache,
            client=active_client,
            sleep_fn=sleep_fn,
            headers={"Accept": "application/json"},
        )
        if meta_early is not None:
            return meta_early

        if not isinstance(meta_payload, list) or not meta_payload:
            if not meta_cached and cache is not None:
                cache.set("alphafold_meta", acc, "not_found", None)
            return ToolResult(
                call_id=call_id,
                tool="alphafold_plddt",
                status="not_found",
                cached=meta_cached,
                source_url=meta_url,
                elapsed_ms=elapsed_ms(t0),
            )

        if not meta_cached and cache is not None:
            cache.set("alphafold_meta", acc, "found", meta_payload)

        selected = _select_entry(meta_payload, acc, residue)
        if selected is None:
            return ToolResult(
                call_id=call_id,
                tool="alphafold_plddt",
                status="not_found",
                cached=meta_cached,
                source_url=meta_url,
                elapsed_ms=elapsed_ms(t0),
            )

        entry_id = str(selected.get("entryId") or f"AF-{acc}")
        conf_url = str(selected["plddtDocUrl"])
        conf_cached, conf_payload, conf_early = fetch_json_cached(
            call_id=call_id,
            tool="alphafold_plddt",
            method="GET",
            url=conf_url,
            cache_namespace="alphafold_confidence",
            cache_key=entry_id,
            cache=cache,
            client=active_client,
            sleep_fn=sleep_fn,
            headers={"Accept": "application/json"},
        )
        if conf_early is not None:
            return conf_early

        if not isinstance(conf_payload, dict):
            return ToolResult(
                call_id=call_id,
                tool="alphafold_plddt",
                status="error",
                cached=False,
                error="Unexpected AlphaFold confidence payload shape",
                source_url=conf_url,
                elapsed_ms=elapsed_ms(t0),
            )

        res_nums = conf_payload.get("residueNumber")
        scores = conf_payload.get("confidenceScore")
        cats = conf_payload.get("confidenceCategory") or []
        if not isinstance(res_nums, list) or not isinstance(scores, list):
            return ToolResult(
                call_id=call_id,
                tool="alphafold_plddt",
                status="error",
                cached=False,
                error="Missing residueNumber or confidenceScore arrays",
                source_url=conf_url,
                elapsed_ms=elapsed_ms(t0),
            )

        if not conf_cached and cache is not None:
            cache.set("alphafold_confidence", entry_id, "found", conf_payload)

        local_pos = residue - int(selected["uniprotStart"]) + 1
        idx: int | None = None
        fast = local_pos - 1
        if 0 <= fast < len(res_nums) and res_nums[fast] == local_pos:
            idx = fast
        else:
            try:
                idx = res_nums.index(local_pos)
            except ValueError:
                idx = None

        if idx is None or idx >= len(scores):
            return ToolResult(
                call_id=call_id,
                tool="alphafold_plddt",
                status="not_found",
                cached=meta_cached and conf_cached,
                source_url=conf_url,
                elapsed_ms=elapsed_ms(t0),
            )

        score = float(scores[idx])
        cat = cats[idx] if isinstance(cats, list) and idx < len(cats) else None
        data = {
            "accession": acc,
            "entry_id": entry_id,
            "residue": residue,
            "plddt": score,
            "confidence_band": _confidence_band(score, cat),
            "global_mean_plddt": selected.get("globalMetricValue"),
            "model_version": selected.get("latestVersion"),
        }
        return ToolResult(
            call_id=call_id,
            tool="alphafold_plddt",
            status="found",
            cached=meta_cached and conf_cached,
            data=data,
            source_url=conf_url,
            elapsed_ms=elapsed_ms(t0),
        )
    finally:
        if owns_client:
            active_client.close()
