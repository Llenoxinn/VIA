"""Orchestrates all M1 evidence tools for a single GRCh38 missense SNV."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

import httpx

from via.cache import DiskCache
from via.http import make_client
from via.schema import InspectionResult, ToolResult, Variant
from via.tools import (
    alphafold_plddt,
    alphamissense_score,
    clinvar_lookup,
    gnomad_frequency,
    uniprot_features,
    vep_consequence,
)

# Reference bases verified against Ensembl /sequence/region GRCh38 (P7).
SAMPLE_VARIANTS: list[dict[str, str]] = [
    {"variant": "17:43094464:T:C", "label": "BRCA1 Q356R", "note": "Common benign missense"},
    {"variant": "17:7675088:C:T", "label": "TP53 R175H", "note": "DNA-binding hotspot"},
    {"variant": "7:140753336:A:T", "label": "BRAF V600E", "note": "Kinase activation hotspot"},
]


def inspect_variant(
    variant_str: str,
    *,
    eval_mode: bool = False,
    cache: DiskCache | None = None,
    client: httpx.Client | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> InspectionResult:
    """Run all evidence tools for one variant and return a structured InspectionResult."""
    variant = Variant.parse(variant_str)
    owns_client = client is None
    active_client = make_client() if owns_client else client
    tool_calls: list[ToolResult] = []

    try:
        vep_res = vep_consequence(
            variant,
            call_id="call_001_vep_consequence",
            cache=cache,
            client=active_client,
            sleep_fn=sleep_fn,
        )
        tool_calls.append(vep_res)

        tool_calls.append(
            gnomad_frequency(
                variant,
                call_id="call_002_gnomad_frequency",
                cache=cache,
                client=active_client,
                sleep_fn=sleep_fn,
            )
        )
        tool_calls.append(
            alphamissense_score(
                variant,
                call_id="call_003_alphamissense_score",
                cache=cache,
                client=active_client,
                sleep_fn=sleep_fn,
            )
        )

        vep_data = vep_res.data or {}
        accession = vep_data.get("uniprot_accession")
        residue = vep_data.get("protein_start")

        if vep_res.status == "found" and isinstance(accession, str) and accession and isinstance(residue, int):
            tool_calls.append(
                uniprot_features(
                    accession,
                    residue,
                    call_id="call_004_uniprot_features",
                    cache=cache,
                    client=active_client,
                    sleep_fn=sleep_fn,
                )
            )
            tool_calls.append(
                alphafold_plddt(
                    accession,
                    residue,
                    call_id="call_005_alphafold_plddt",
                    cache=cache,
                    client=active_client,
                    sleep_fn=sleep_fn,
                )
            )
        else:
            reason = "No canonical UniProt accession and residue mapping from VEP."
            tool_calls.append(
                ToolResult(
                    call_id="call_004_uniprot_features",
                    tool="uniprot_features",
                    status="not_found",
                    data={"reason": reason},
                )
            )
            tool_calls.append(
                ToolResult(
                    call_id="call_005_alphafold_plddt",
                    tool="alphafold_plddt",
                    status="not_found",
                    data={"reason": reason},
                )
            )

        if not eval_mode:
            tool_calls.append(
                clinvar_lookup(
                    variant,
                    eval_mode=False,
                    call_id="call_006_clinvar_lookup",
                    cache=cache,
                    client=active_client,
                    sleep_fn=sleep_fn,
                )
            )
    finally:
        if owns_client:
            active_client.close()

    flagged_error = any(tc.status == "error" for tc in tool_calls)
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return InspectionResult(
        variant=variant,
        eval_mode=eval_mode,
        flagged_tool_error=flagged_error,
        tool_calls=tool_calls,
        timestamp=timestamp,
    )
