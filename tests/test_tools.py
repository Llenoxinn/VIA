"""Offline tests for all six evidence tools and the inspection runner (P3)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from via.cache import DiskCache
from via.runner import inspect_variant
from via.schema import Variant
from via.tools import (
    alphafold_plddt,
    alphamissense_score,
    clinvar_lookup,
    gnomad_frequency,
    uniprot_features,
    vep_consequence,
)

FIXTURES = Path(__file__).parent / "fixtures"
NO_SLEEP = lambda _: None  # noqa: E731


def load_fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_fixture_transport(overrides: dict[str, httpx.Response | Exception] | None = None) -> httpx.MockTransport:
    overrides = overrides or {}
    vep_data = load_fixture("vep_brca1_q356r.json")
    vep_am_data = load_fixture("vep_am_brca1_q356r.json")
    gnomad_found = load_fixture("gnomad_brca1_q356r.json")
    gnomad_nf = load_fixture("gnomad_not_found.json")
    uniprot_data = load_fixture("uniprot_p38398.json")
    af_meta = load_fixture("alphafold_meta_p38398.json")
    af_conf = load_fixture("alphafold_conf_p38398.json")
    cv_esearch = load_fixture("clinvar_esearch_43094464.json")
    cv_esum = load_fixture("clinvar_esummary_43094464.json")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for prefix, outcome in overrides.items():
            if prefix in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        if "rest.ensembl.org/vep/" in url and "AlphaMissense=1" in url:
            return httpx.Response(200, json=vep_am_data)
        if "rest.ensembl.org/vep/" in url:
            return httpx.Response(200, json=vep_data)
        if "gnomad.broadinstitute.org/api" in url:
            body = json.loads(request.content.decode("utf-8"))
            if "17-43094464-T-A" in body.get("query", ""):
                return httpx.Response(200, json=gnomad_nf)
            return httpx.Response(200, json=gnomad_found)
        if "rest.uniprot.org/uniprotkb/" in url:
            return httpx.Response(200, json=uniprot_data)
        if "alphafold.ebi.ac.uk/api/prediction/" in url:
            return httpx.Response(200, json=af_meta)
        if "alphafold.ebi.ac.uk/files/AF-P38398-F1-confidence_v6.json" in url:
            return httpx.Response(200, json=af_conf)
        if "eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi" in url:
            return httpx.Response(200, json=cv_esearch)
        if "eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi" in url:
            return httpx.Response(200, json=cv_esum)
        return httpx.Response(404, json={"error": "unmatched test URL"})

    return httpx.MockTransport(handler)


def test_vep_consequence_found_cached_not_found_and_error(tmp_path: Path) -> None:
    variant = Variant.parse("17:43094464:T:C")
    cache = DiskCache(tmp_path)

    with httpx.Client(transport=make_fixture_transport()) as client:
        res1 = vep_consequence(variant, cache=cache, client=client, sleep_fn=NO_SLEEP)
    assert res1.status == "found"
    assert res1.cached is False
    assert res1.data is not None
    assert res1.data["gene_symbol"] == "BRCA1"
    assert res1.data["transcript_id"] == "ENST00000357654"
    assert res1.data["uniprot_accession"] == "P38398"
    assert res1.data["protein_start"] == 356
    assert res1.data["is_missense"] is True

    # Second call hits disk cache even if network errors.
    fail_transport = httpx.MockTransport(lambda req: httpx.Response(500))
    with httpx.Client(transport=fail_transport) as fail_client:
        res2 = vep_consequence(variant, cache=cache, client=fail_client, sleep_fn=NO_SLEEP)
    assert res2.status == "found"
    assert res2.cached is True
    assert res2.data == res1.data

    # 404 -> not_found (cached)
    nf_cache = DiskCache(tmp_path / "nf")
    with httpx.Client(transport=make_fixture_transport({"rest.ensembl.org/vep/": httpx.Response(404)})) as nf_client:
        nf_res = vep_consequence(variant, cache=nf_cache, client=nf_client, sleep_fn=NO_SLEEP)
    assert nf_res.status == "not_found"
    assert nf_cache.get("vep_consequence", variant.canonical_id)[0] is True

    # 503 -> error (never cached)
    err_cache = DiskCache(tmp_path / "err")
    with httpx.Client(transport=make_fixture_transport({"rest.ensembl.org/vep/": httpx.Response(503)})) as err_client:
        err_res = vep_consequence(variant, cache=err_cache, client=err_client, sleep_fn=NO_SLEEP)
    assert err_res.status == "error"
    assert err_cache.get("vep_consequence", variant.canonical_id)[0] is False


def test_gnomad_frequency_found_not_found_and_error(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    v_found = Variant.parse("17:43094464:T:C")
    v_nf = Variant.parse("17:43094464:T:A")

    with httpx.Client(transport=make_fixture_transport()) as client:
        res = gnomad_frequency(v_found, cache=cache, client=client, sleep_fn=NO_SLEEP)
        res_nf = gnomad_frequency(v_nf, cache=cache, client=client, sleep_fn=NO_SLEEP)

    assert res.status == "found"
    assert res.data is not None
    assert res.data["exome_ac"] == 81929
    assert res.data["combined_af"] > 0.05
    assert res.data["popmax_population"] is not None
    assert res.data["popmax_af"] > 0.05
    assert res.data["filters"] == []

    assert res_nf.status == "not_found"
    assert cache.get("gnomad_frequency", v_nf.gnomad_id)[0] is True

    err_cache = DiskCache(tmp_path / "err")
    err_resp = httpx.Response(200, json={"errors": [{"message": "Rate limit exceeded"}], "data": {"variant": None}})
    with httpx.Client(transport=make_fixture_transport({"gnomad.broadinstitute.org": err_resp})) as err_client:
        err_res = gnomad_frequency(v_found, cache=err_cache, client=err_client, sleep_fn=NO_SLEEP)
    assert err_res.status == "error"
    assert err_cache.get("gnomad_frequency", v_found.gnomad_id)[0] is False


def test_alphamissense_score_states(tmp_path: Path) -> None:
    variant = Variant.parse("17:43094464:T:C")
    cache = DiskCache(tmp_path)

    with httpx.Client(transport=make_fixture_transport()) as client:
        res = alphamissense_score(variant, cache=cache, client=client, sleep_fn=NO_SLEEP)
    assert res.status == "found"
    assert res.data is not None
    assert res.data["score"] == pytest.approx(0.1088)
    assert res.data["am_class"] == "likely_benign"

    # Missing alphamissense plugin field -> not_found
    no_am = [{"transcript_consequences": [{"canonical": 1, "transcript_id": "ENST1"}]}]
    with httpx.Client(
        transport=make_fixture_transport({"AlphaMissense=1": httpx.Response(200, json=no_am)})
    ) as nf_client:
        nf = alphamissense_score(variant, client=nf_client, sleep_fn=NO_SLEEP)
    assert nf.status == "not_found"

    # Timeout -> error (not cached)
    err_cache = DiskCache(tmp_path / "err")
    with httpx.Client(
        transport=make_fixture_transport({"AlphaMissense=1": httpx.ReadTimeout("timed out")})
    ) as err_client:
        err = alphamissense_score(variant, cache=err_cache, client=err_client, sleep_fn=NO_SLEEP)
    assert err.status == "error"
    assert err_cache.get("alphamissense_score", variant.canonical_id)[0] is False


def test_uniprot_features_and_alphafold_plddt(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    with httpx.Client(transport=make_fixture_transport()) as client:
        up_356 = uniprot_features("P38398", 356, cache=cache, client=client, sleep_fn=NO_SLEEP)
        up_61 = uniprot_features("P38398", 61, cache=cache, client=client, sleep_fn=NO_SLEEP)
        af_356 = alphafold_plddt("P38398", 356, cache=cache, client=client, sleep_fn=NO_SLEEP)
        af_out = alphafold_plddt("P38398", 99999, cache=cache, client=client, sleep_fn=NO_SLEEP)

    assert up_356.status == "found"
    assert up_356.data is not None
    assert up_356.data["protein_length"] == 1863
    assert any(d["description"] == "BRCT 1" for d in up_356.data["domains"])

    assert up_61.status == "found"
    assert up_61.cached is True
    assert up_61.data is not None
    assert any(f["type"] == "Zinc finger" and f["description"] == "RING-type" for f in up_61.data["overlapping_features"])

    assert af_356.status == "found"
    assert af_356.data is not None
    assert isinstance(af_356.data["plddt"], float)
    assert af_356.data["entry_id"] == "AF-P38398-F1"
    assert af_356.data["model_version"] == 6
    assert af_out.status == "not_found"


def test_clinvar_lookup_exact_spdi_match_and_not_found(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    v_match = Variant.parse("17:43094464:T:C")
    v_other_alt = Variant.parse("17:43094464:T:A")

    with httpx.Client(transport=make_fixture_transport()) as client:
        res = clinvar_lookup(v_match, eval_mode=False, cache=cache, client=client, sleep_fn=NO_SLEEP)
        res_nf = clinvar_lookup(v_other_alt, eval_mode=False, cache=cache, client=client, sleep_fn=NO_SLEEP)

    assert res.status == "found"
    assert res.data is not None
    assert res.data["accession"] == "VCV000041803"
    assert res.data["classification"] == "Benign"
    assert res.data["stars"] == 3
    assert res_nf.status == "not_found"


def test_inspect_variant_end_to_end_and_error_flag(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    with httpx.Client(transport=make_fixture_transport()) as client:
        std = inspect_variant("17:43094464:T:C", eval_mode=False, cache=cache, client=client, sleep_fn=NO_SLEEP)
        evl = inspect_variant("17:43094464:T:C", eval_mode=True, cache=cache, client=client, sleep_fn=NO_SLEEP)

    assert std.flagged_tool_error is False
    assert [tc.tool for tc in std.tool_calls] == [
        "vep_consequence",
        "gnomad_frequency",
        "alphamissense_score",
        "uniprot_features",
        "alphafold_plddt",
        "clinvar_lookup",
    ]
    assert all(tc.status == "found" for tc in std.tool_calls)

    assert evl.eval_mode is True
    assert [tc.tool for tc in evl.tool_calls] == [
        "vep_consequence",
        "gnomad_frequency",
        "alphamissense_score",
        "uniprot_features",
        "alphafold_plddt",
    ]

    # When gnomAD returns 500, flagged_tool_error must be True.
    err_cache = DiskCache(tmp_path / "err")
    with httpx.Client(transport=make_fixture_transport({"gnomad.broadinstitute.org": httpx.Response(500)})) as err_client:
        flagged = inspect_variant("17:43094464:T:C", eval_mode=True, cache=err_cache, client=err_client, sleep_fn=NO_SLEEP)
    assert flagged.flagged_tool_error is True
    gn = next(tc for tc in flagged.tool_calls if tc.tool == "gnomad_frequency")
    assert gn.status == "error"
