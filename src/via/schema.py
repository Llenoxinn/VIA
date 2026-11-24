"""Core Pydantic schemas for variants, tool results, inspections, and cited reports."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ToolStatus = Literal["found", "not_found", "error"]
ReportLabel = Literal["likely_pathogenic", "likely_benign", "uncertain"]
EvidenceDirection = Literal["pathogenic", "benign", "neutral", "uncertain"]

VALID_CHROMS = frozenset({str(i) for i in range(1, 23)} | {"X", "Y", "MT"})
VALID_BASES = frozenset({"A", "C", "G", "T"})


class Variant(BaseModel):
    """A GRCh38 single-nucleotide variant (SNV)."""

    chrom: str
    pos: int
    ref: str
    alt: str

    @field_validator("chrom", mode="before")
    @classmethod
    def _validate_chrom(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("chromosome must be a string")
        cleaned = value.strip()
        if cleaned[:3].lower() == "chr":
            cleaned = cleaned[3:]
        cleaned = cleaned.upper()
        if cleaned not in VALID_CHROMS:
            raise ValueError(f"unsupported chromosome {value!r}; expected 1-22, X, Y, or MT")
        return cleaned

    @field_validator("pos")
    @classmethod
    def _validate_pos(cls, value: int) -> int:
        if isinstance(value, bool) or value < 1:
            raise ValueError("pos must be a positive integer (>= 1)")
        return value

    @field_validator("ref", "alt", mode="before")
    @classmethod
    def _validate_base(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("allele must be a string")
        cleaned = value.strip().upper()
        if cleaned not in VALID_BASES:
            raise ValueError(f"allele {value!r} must be a single SNV base (A, C, G, or T)")
        return cleaned

    @model_validator(mode="after")
    def _validate_diff(self) -> Variant:
        if self.ref == self.alt:
            raise ValueError(f"ref and alt alleles must differ (got {self.ref})")
        return self

    @classmethod
    def parse(cls, raw: str) -> Variant:
        """Parse 'chr:pos:ref:alt' or 'chr-pos-ref-alt' (with optional chr prefix)."""
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("variant string cannot be empty")
        parts = re.split(r"[:\-]", raw.strip())
        if len(parts) != 4:
            raise ValueError(
                f"invalid variant {raw!r}; expected 'chr:pos:ref:alt' or 'chr-pos-ref-alt'"
            )
        chrom_s, pos_s, ref_s, alt_s = (p.strip() for p in parts)
        if not pos_s.isdigit():
            raise ValueError(f"invalid genomic position {pos_s!r} in {raw!r}")
        return cls(chrom=chrom_s, pos=int(pos_s), ref=ref_s, alt=alt_s)

    @property
    def canonical_id(self) -> str:
        """Return colon-delimited GRCh38 ID, e.g. '17:43094464:T:C'."""
        return f"{self.chrom}:{self.pos}:{self.ref}:{self.alt}"

    @property
    def gnomad_id(self) -> str:
        """Return hyphen-delimited gnomAD variantId, e.g. '17-43094464-T-C'."""
        return f"{self.chrom}-{self.pos}-{self.ref}-{self.alt}"


class ToolResult(BaseModel):
    """Typed result returned by every evidence tool."""

    call_id: str
    tool: str
    status: ToolStatus
    cached: bool = False
    data: dict[str, Any] | None = None
    error: str | None = None
    source_url: str | None = None
    elapsed_ms: int | None = None

    @model_validator(mode="after")
    def _validate_state(self) -> ToolResult:
        if self.status == "error" and not (self.error and self.error.strip()):
            raise ValueError("ToolResult with status='error' must include a non-empty error message")
        if self.status == "found" and self.data is None:
            raise ValueError("ToolResult with status='found' must include data")
        return self


class EvidenceItem(BaseModel):
    """A single claim in a report, grounded to one tool call ID."""

    tool_call_id: str
    claim: str
    direction: EvidenceDirection = "neutral"


class Report(BaseModel):
    """Structured variant classification report with grounded evidence citations."""

    variant: Variant
    label: ReportLabel
    summary: str
    eval_mode: bool = False
    flagged_tool_error: bool = False
    evidence: list[EvidenceItem] = Field(default_factory=list)
    tool_calls: list[ToolResult] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_grounding(self) -> Report:
        valid_ids = {tc.call_id for tc in self.tool_calls}
        missing = [item.tool_call_id for item in self.evidence if item.tool_call_id not in valid_ids]
        if missing:
            raise ValueError(
                f"ungrounded evidence citations (P2): tool_call_id(s) not found in tool_calls: {missing}"
            )
        return self


class InspectionResult(BaseModel):
    """M1 output bundle returned by running all evidence tools on one variant."""

    variant: Variant
    eval_mode: bool
    flagged_tool_error: bool
    tool_calls: list[ToolResult]
    timestamp: str
