"""Offline unit tests for core Pydantic schemas and DiskCache (P2, P3, D7)."""

from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from via.cache import DiskCache
from via.schema import EvidenceItem, Report, ToolResult, Variant


def test_variant_parse_valid_formats() -> None:
    v1 = Variant.parse("17:43094464:T:C")
    assert v1.chrom == "17"
    assert v1.pos == 43094464
    assert v1.ref == "T"
    assert v1.alt == "C"
    assert v1.canonical_id == "17:43094464:T:C"
    assert v1.gnomad_id == "17-43094464-T-C"

    v2 = Variant.parse(" chrX-12345-a-g ")
    assert v2.canonical_id == "X:12345:A:G"

    v3 = Variant.parse("CHRmt:99:c:t")
    assert v3.canonical_id == "MT:99:C:T"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "17:43094464:T",
        "17:43094464:T:C:G",
        "17:0:T:C",
        "17:-5:T:C",
        "17:1_000:T:C",
        "23:100:A:G",
        "17:43094464:TT:C",
        "17:43094464:T:CG",
        "17:43094464:N:C",
        "17:43094464:T:T",
    ],
)
def test_variant_parse_rejects_invalid(raw: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        Variant.parse(raw)


def test_tool_result_state_validation() -> None:
    ToolResult(call_id="c1", tool="vep", status="not_found")
    ToolResult(call_id="c2", tool="vep", status="found", data={"x": 1})
    ToolResult(call_id="c3", tool="vep", status="error", error="HTTP 503")

    with pytest.raises(ValidationError):
        ToolResult(call_id="c4", tool="vep", status="found", data=None)
    with pytest.raises(ValidationError):
        ToolResult(call_id="c5", tool="vep", status="error", error="   ")


def test_report_grounding_validation_p2() -> None:
    variant = Variant.parse("17:43094464:T:C")
    calls = [ToolResult(call_id="call_001_vep_consequence", tool="vep_consequence", status="found", data={"gene": "BRCA1"})]

    report = Report(
        variant=variant,
        label="uncertain",
        summary="Only VEP inspected.",
        evidence=[EvidenceItem(tool_call_id="call_001_vep_consequence", claim="Missense in BRCA1", direction="neutral")],
        tool_calls=calls,
    )
    assert report.evidence[0].tool_call_id == "call_001_vep_consequence"

    with pytest.raises(ValidationError, match="ungrounded evidence citations"):
        Report(
            variant=variant,
            label="likely_benign",
            summary="Fake citation.",
            evidence=[EvidenceItem(tool_call_id="call_999_invented", claim="Invented AF", direction="benign")],
            tool_calls=calls,
        )


def test_disk_cache_found_not_found_and_never_errors(tmp_path) -> None:
    cache = DiskCache(tmp_path)

    cache.set("gnomad", "17-1-A-G", "found", {"af": 0.01})
    hit, status, payload = cache.get("gnomad", "17-1-A-G")
    assert (hit, status, payload) == (True, "found", {"af": 0.01})

    cache.set("gnomad", "17-2-A-G", "not_found", None)
    hit, status, payload = cache.get("gnomad", "17-2-A-G")
    assert (hit, status, payload) == (True, "not_found", None)

    cache.set("gnomad", "17-3-A-G", "error", {"error": "timeout"})
    hit, status, payload = cache.get("gnomad", "17-3-A-G")
    assert (hit, status, payload) == (False, None, None)

    # Even if an error entry were manually injected on disk, get() must ignore it.
    bad_file = cache._entry_path("gnomad", "17-4-A-G")
    bad_file.parent.mkdir(parents=True, exist_ok=True)
    bad_file.write_text(json.dumps({"status": "error", "payload": {"msg": "boom"}}), encoding="utf-8")
    assert cache.get("gnomad", "17-4-A-G") == (False, None, None)


def test_disk_cache_applies_sanitizer_on_write_and_read(tmp_path) -> None:
    cache = DiskCache(tmp_path)

    def strip_secret(obj: dict) -> dict:
        return {k: v for k, v in obj.items() if k != "secret"}

    cache.set("vep", "k1", "found", {"gene": "BRCA1", "secret": "ClinVar"}, sanitizer=strip_secret)
    raw_file = cache._entry_path("vep", "k1")
    assert "secret" not in raw_file.read_text(encoding="utf-8")

    # Poisoned file written directly on disk is still sanitized on read.
    poison_path = cache._entry_path("vep", "k2")
    poison_path.write_text(json.dumps({"status": "found", "payload": {"gene": "TP53", "secret": "HGMD"}}), encoding="utf-8")
    hit, status, payload = cache.get("vep", "k2", sanitizer=strip_secret)
    assert hit and status == "found"
    assert payload == {"gene": "TP53"}
