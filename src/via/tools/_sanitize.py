"""Leakage-prevention sanitizers for Ensembl VEP payloads (P1, R1)."""

from __future__ import annotations

from typing import Any

FORBIDDEN_VEP_KEYS = frozenset(
    {
        "colocated_variants",
        "clin_sig",
        "clin_sig_allele",
        "phenotype_or_disease",
        "somatic",
        "var_synonyms",
        "pubmed",
        "clinvar",
        "clinvar_clnsig",
    }
)


def _is_forbidden_key(key: str) -> bool:
    low = key.lower()
    return low in FORBIDDEN_VEP_KEYS or low.startswith("clinvar") or low.startswith("clin_sig")


def strip_vep_payload(obj: Any) -> Any:
    """Recursively drop ClinVar/HGMD/COSMIC/clinical fields from a VEP payload."""
    if isinstance(obj, dict):
        return {k: strip_vep_payload(v) for k, v in obj.items() if not _is_forbidden_key(str(k))}
    if isinstance(obj, list):
        return [strip_vep_payload(item) for item in obj]
    return obj
