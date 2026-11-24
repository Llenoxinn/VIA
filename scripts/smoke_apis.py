"""LIVE smoke test: calls each data source once. Needs internet. Not run by pytest (P3).

Usage: python scripts/smoke_apis.py
Gemini is checked only if GEMINI_API_KEY is set in the environment or in .env.
"""
import json
import os
import urllib.request
from pathlib import Path

UA = {"User-Agent": "via-smoke-test/0.1"}
VARIANT = "17-43094464-T-C"  # GRCh38 SNV in BRCA1; ref verified by check_ref (P7)
UNIPROT = "P38398"  # BRCA1


def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, (r.read() if method != "HEAD" else b"")


def gemini_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            value = line.split("=", 1)[1].strip().strip('"').strip("'") if line.startswith("GEMINI_API_KEY=") else ""
            if value:
                return value
    return None


def need(value, what):
    if value in (None, "", []):
        raise ValueError(f"missing {what} in response")
    return value


def check_ref():
    chrom, pos, ref, _ = VARIANT.split("-")
    _, body = call(f"https://rest.ensembl.org/sequence/region/human/{chrom}:{pos}..{pos}:1",
                   headers={"Content-Type": "application/json"})
    seq = need(json.loads(body).get("seq"), "seq")
    if seq.upper() != ref:
        raise ValueError(f"ref mismatch: VARIANT says {ref}, GRCh38 has {seq} (P7)")
    return f"ref {seq} matches"


def check_vep():
    chrom, pos, _, alt = VARIANT.split("-")
    _, body = call(f"https://rest.ensembl.org/vep/human/region/{chrom}:{pos}-{pos}:1/{alt}",
                   headers={"Content-Type": "application/json"})
    return need(json.loads(body)[0].get("most_severe_consequence"), "most_severe_consequence")


def check_gnomad():
    q = {"query": '{variant(variantId:"%s", dataset:gnomad_r4){variant_id exome{af} genome{af}}}' % VARIANT}
    _, body = call("https://gnomad.broadinstitute.org/api", data=json.dumps(q).encode(),
                   headers={"Content-Type": "application/json"})
    d = json.loads(body)
    if d.get("data", {}).get("variant"):
        return d["data"]["variant"]
    msg = (d.get("errors") or [{}])[0].get("message", "")
    if msg == "Variant not found":  # a real answer (not_found), not a failure
        return "not_found"
    raise ValueError(f"gnomAD error: {msg or 'empty response'}")


def check_uniprot():
    _, body = call(f"https://rest.uniprot.org/uniprotkb/{UNIPROT}.json?fields=accession,length")
    return json.loads(body)["sequence"]["length"]


def check_alphafold():
    _, body = call(f"https://alphafold.ebi.ac.uk/api/prediction/{UNIPROT}")
    return need(json.loads(body)[0].get("entryId"), "entryId")


def check_clinvar():
    status, _ = call("https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz", method="HEAD")
    return f"HTTP {status}"


def check_alphamissense():
    status, _ = call("https://storage.googleapis.com/dm_alphamissense/AlphaMissense_hg38.tsv.gz", method="HEAD")
    return f"HTTP {status}"


def check_gemini():
    key = gemini_key()
    if not key:
        return "SKIPPED (no GEMINI_API_KEY)"
    _, body = call("https://generativelanguage.googleapis.com/v1beta/models?pageSize=100",
                   headers={"x-goog-api-key": key})
    names = [m["name"] for m in json.loads(body).get("models", []) if "flash" in m["name"]]
    return ", ".join(names) or "no flash models listed"


if __name__ == "__main__":
    failed = 0
    for name, fn in [("Reference base", check_ref), ("Ensembl VEP", check_vep), ("gnomAD", check_gnomad), ("UniProt", check_uniprot),
                     ("AlphaFold DB", check_alphafold), ("ClinVar file", check_clinvar),
                     ("AlphaMissense file", check_alphamissense), ("Gemini", check_gemini)]:
        try:
            print(f"OK    {name}: {fn()}")
        except Exception as e:  # smoke test: report every failure, keep going
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    raise SystemExit(1 if failed else 0)
