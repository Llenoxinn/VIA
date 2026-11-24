# ARCHITECTURE.md

Status: M1 implemented (tools, leakage guard, interactive local Web UI). Update as code lands (P5).

## Flow
```
variant (chr:pos:ref:alt)
   └─► M1 runner / M2 agent loop (Gemini Flash, tool calling)
          ├─ vep_consequence      → gene, transcript, amino-acid change
          ├─ gnomad_frequency     → allele frequency
          ├─ alphamissense_score  → 0–1 score
          ├─ uniprot_features     → domains/sites at residue
          ├─ alphafold_plddt      → structure confidence at residue
          └─ clinvar_lookup       → DISABLED in eval mode
   └─► M1: InspectionResult JSON / interactive local Web UI (`via ui`)
   └─► M2: report (pydantic): label ∈ {likely_pathogenic, likely_benign, uncertain},
                              evidence[] each with tool_call_id, summary
```

## Layout
```
pyproject.toml     pinned deps (P4), `via` CLI entry point
src/via/
  cli.py           `via inspect chr:pos:ref:alt` and `via ui`
  runner.py        runs M1 tools in sequence and builds InspectionResult
  schema.py        Variant, ToolResult, EvidenceItem, Report, InspectionResult
  cache.py         atomic disk cache in .cache/ (never caches errors)
  http.py          shared httpx client with polite User-Agent and retries
  web.py           local ThreadingHTTPServer for interactive Web UI + /api/inspect
  static/
    index.html     interactive local Web UI (evidence board, tool trace, raw JSON)
  tools/
    errors.py      EvalModeLeakageError exception for eval mode (P1)
    _common.py     timing, cache lookup, HTTP error wrapping
    _sanitize.py   strips colocated_variants/ClinVar/HGMD/COSMIC from VEP
    vep.py         Ensembl VEP REST consequence + UniProt mapping
    gnomad.py      gnomAD v4 GraphQL allele frequencies & popmax
    alphamissense.py Ensembl VEP ?AlphaMissense=1 score
    uniprot.py     UniProtKB structural/functional features (safe fields only)
    alphafold.py   AlphaFold DB API + confidence_v6.json pLDDT
    clinvar.py     NCBI E-utilities lookup (raises EvalModeLeakageError in eval)
  agent.py         (M2) tool-calling loop, step limit, trace
eval/              (M3–M4) dataset.py, baselines.py, run.py
tests/             offline, fixtures in tests/fixtures/; test_schema_and_cache.py,
                   test_tools.py, test_leakage.py, test_web.py
scripts/           smoke_apis.py (LIVE: network, not run by pytest)
data/              downloads, git-ignored
```

## Data sources
| Source | Access | Licence (verified at M1, P6) |
|---|---|---|
| Ensembl VEP REST | rest.ensembl.org | Open REST resource (Apache 2.0 software, CC BY 4.0 docs), ~15 req/s |
| gnomAD | GraphQL API, gnomad.broadinstitute.org | CC0 1.0 (Broad Institute) |
| AlphaMissense | Ensembl VEP `?AlphaMissense=1` (M1); optional TSV in `data/` | CC BY 4.0 (updated Mar 2024; 2023 TSV header reads CC BY-NC-SA 4.0) |
| UniProt | rest.uniprot.org | CC BY 4.0 |
| AlphaFold DB | alphafold.ebi.ac.uk API + confidence JSON | CC BY 4.0 |
| ClinVar | NCBI E-utilities (M1 tool) + FTP variant_summary.txt.gz | Public domain (NCBI/NIH) |

## Key decisions
- **Leakage guard lives in the tool layer**, not the prompt: in eval mode the ClinVar tool is not registered and VEP clinical fields are stripped before the LLM sees them.
- **Tool result states:** `found` / `not_found` / `error`; only the first two are cached, so an outage never looks like "absent from gnomAD".
- **Eval-mode cache:** VEP responses are stripped before caching *and* on read, so an old cache entry cannot leak ClinVar fields.
- **Abstention:** `uncertain` *is* the abstain answer. Headline balanced accuracy counts it as wrong; F1 is on answered cases; coverage = share not `uncertain` (PLAN §3.4).
