"""Evaluation leakage-guard tests (P1, R1)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tests.test_tools import NO_SLEEP, load_fixture, make_fixture_transport
from via.cache import DiskCache
from via.runner import inspect_variant
from via.schema import Variant
from via.tools import (
    EvalModeLeakageError,
    alphamissense_score,
    clinvar_lookup,
    get_tool_names,
    uniprot_features,
    vep_consequence,
)
from via.tools.uniprot import SAFE_UNIPROT_FIELDS

LEAK_MARKERS = (
    "colocated_variants",
    "clin_sig",
    "VCV000041803",
    "RCV000462965",
    "HGMD_MUTATION",
    "COSMIC_MUTATION",
    "COSV58788306",
    "phenotype_or_disease",
    "pubmed",
)


def test_tool_registry_hides_clinvar_in_eval_mode() -> None:
    assert "clinvar_lookup" in get_tool_names(eval_mode=False)
    assert "clinvar_lookup" not in get_tool_names(eval_mode=True)


def test_clinvar_lookup_raises_immediately_in_eval_mode(tmp_path: Path) -> None:
    variant = Variant.parse("17:43094464:T:C")
    cache = DiskCache(tmp_path)
    calls: list[str] = []

    def fail_if_called(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        raise AssertionError("HTTP must not be called in eval_mode")

    with httpx.Client(transport=httpx.MockTransport(fail_if_called)) as client:
        with pytest.raises(EvalModeLeakageError):
            clinvar_lookup(variant, eval_mode=True, cache=cache, client=client, sleep_fn=NO_SLEEP)
    assert calls == []


def test_vep_and_am_strip_colocated_clinvar_from_output_and_cache(tmp_path: Path) -> None:
    variant = Variant.parse("17:43094464:T:C")
    cache = DiskCache(tmp_path)

    with httpx.Client(transport=make_fixture_transport()) as client:
        vep_res = vep_consequence(variant, cache=cache, client=client, sleep_fn=NO_SLEEP)
        am_res = alphamissense_score(variant, cache=cache, client=client, sleep_fn=NO_SLEEP)

    for text in (vep_res.model_dump_json(), am_res.model_dump_json()):
        for marker in LEAK_MARKERS:
            assert marker not in text

    for ns in ("vep_consequence", "alphamissense_score"):
        cache_file = cache._entry_path(ns, variant.canonical_id)
        disk_text = cache_file.read_text(encoding="utf-8")
        for marker in LEAK_MARKERS:
            assert marker not in disk_text


def test_poisoned_cache_is_sanitized_on_read(tmp_path: Path) -> None:
    variant = Variant.parse("17:43094464:T:C")
    cache = DiskCache(tmp_path)

    poisoned_vep = dict(load_fixture("vep_brca1_q356r.json")[0])
    poisoned_vep["clinvar_clnsig"] = "Benign"
    poisoned_vep["clin_sig"] = ["benign"]

    poisoned_am = dict(load_fixture("vep_am_brca1_q356r.json")[0])
    poisoned_am["clinvar_clnsig"] = "Benign"
    poisoned_am["clin_sig"] = ["benign"]

    vep_path = cache._entry_path("vep_consequence", variant.canonical_id)
    vep_path.parent.mkdir(parents=True, exist_ok=True)
    vep_path.write_text(json.dumps({"status": "found", "payload": poisoned_vep}), encoding="utf-8")

    am_path = cache._entry_path("alphamissense_score", variant.canonical_id)
    am_path.parent.mkdir(parents=True, exist_ok=True)
    am_path.write_text(json.dumps({"status": "found", "payload": poisoned_am}), encoding="utf-8")

    # Even read directly via cache.get(..., strip_vep_payload) must be clean, and tool outputs too.
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as dead_client:
        vep_res = vep_consequence(variant, cache=cache, client=dead_client, sleep_fn=NO_SLEEP)
        am_res = alphamissense_score(variant, cache=cache, client=dead_client, sleep_fn=NO_SLEEP)

    assert vep_res.status == "found" and vep_res.cached is True
    assert am_res.status == "found" and am_res.cached is True
    for text in (vep_res.model_dump_json(), am_res.model_dump_json()):
        for marker in LEAK_MARKERS + ("clinvar_clnsig",):
            assert marker not in text


def test_uniprot_requests_only_safe_fields(tmp_path: Path) -> None:
    seen_urls: list[str] = []
    uniprot_data = load_fixture("uniprot_p38398.json")

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json=uniprot_data)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        res = uniprot_features("P38398", 356, cache=DiskCache(tmp_path), client=client, sleep_fn=NO_SLEEP)

    assert res.status == "found"
    assert len(seen_urls) == 1
    assert f"fields={SAFE_UNIPROT_FIELDS}" in seen_urls[0]
    for forbidden in ("ft_variant", "ft_mutagen", "cc_disease"):
        assert forbidden not in seen_urls[0]


def test_inspect_variant_eval_mode_has_zero_clinvar_leakage(tmp_path: Path) -> None:
    with httpx.Client(transport=make_fixture_transport()) as client:
        res = inspect_variant("17:43094464:T:C", eval_mode=True, cache=DiskCache(tmp_path), client=client, sleep_fn=NO_SLEEP)

    assert all(tc.tool != "clinvar_lookup" for tc in res.tool_calls)
    serialized = res.model_dump_json()
    for marker in LEAK_MARKERS + ("clinvar_lookup",):
        assert marker not in serialized
