"""Evidence tool registry and leakage-safe tool listing."""

from __future__ import annotations

from via.tools.alphafold import alphafold_plddt
from via.tools.alphamissense import alphamissense_score
from via.tools.clinvar import clinvar_lookup
from via.tools.errors import EvalModeLeakageError
from via.tools.gnomad import gnomad_frequency
from via.tools.uniprot import uniprot_features
from via.tools.vep import vep_consequence

_EVAL_SAFE_TOOLS = [
    "vep_consequence",
    "gnomad_frequency",
    "alphamissense_score",
    "uniprot_features",
    "alphafold_plddt",
]


def get_tool_names(eval_mode: bool = False) -> list[str]:
    """Return registered tool names; omits clinvar_lookup in eval_mode (P1)."""
    if eval_mode:
        return list(_EVAL_SAFE_TOOLS)
    return [*_EVAL_SAFE_TOOLS, "clinvar_lookup"]


__all__ = [
    "EvalModeLeakageError",
    "alphafold_plddt",
    "alphamissense_score",
    "clinvar_lookup",
    "get_tool_names",
    "gnomad_frequency",
    "uniprot_features",
    "vep_consequence",
]
