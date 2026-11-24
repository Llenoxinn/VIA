# ARCHITECTURE.md

Status: planned (M0). Update as code lands (P5).

## Flow
```
variant (chr:pos:ref:alt)
   └─► agent loop (Claude, tool calling)
          ├─ vep_consequence      → gene, transcript, amino-acid change
          ├─ gnomad_frequency     → allele frequency
          ├─ alphamissense_score  → 0–1 score
          ├─ uniprot_features     → domains/sites at residue
          ├─ alphafold_plddt      → structure confidence at residue
          └─ clinvar_lookup       → DISABLED in eval mode
   └─► report (pydantic): label ∈ {likely_pathogenic, likely_benign, uncertain},
                          evidence[] each with tool_call_id, summary
```

## Planned layout
```
pyproject.toml  pinned deps (P4), `via` CLI entry point
src/via/
  cli.py        `via classify chr:pos:ref:alt`
  tools/        one module per data source, typed outputs
  agent.py      tool-calling loop, step limit, trace
  schema.py     Variant, ToolResult, Report
  cache.py      disk cache for HTTP (in .cache/, git-ignored)
eval/
  dataset.py    ClinVar sampling (seeded, ≥ 3-star, post-cutoff subset by date last evaluated)
  baselines.py  gnomAD rule, AlphaMissense threshold, LLM no-tools
  run.py        runs methods, writes eval/results/ (git-ignored)
tests/          offline, fixtures in tests/fixtures/; test_leakage.py (P1)
scripts/        smoke_apis.py (LIVE: network, not run by pytest)
data/           downloads, git-ignored
```

## Data sources
| Source | Access | Licence (verify at M1, P6) |
|---|---|---|
| Ensembl VEP REST | rest.ensembl.org | Open, rate-limited (~15 req/s) |
| gnomAD | GraphQL API, gnomad.broadinstitute.org | ODbL / open |
| AlphaMissense | Precomputed TSV (Zenodo/GCS) | CC BY 4.0 (check) |
| UniProt | rest.uniprot.org | CC BY 4.0 |
| AlphaFold DB | alphafold.ebi.ac.uk API | CC BY 4.0 |
| ClinVar | NCBI FTP variant_summary.txt.gz | Public domain |

## Key decisions
- **Leakage guard lives in the tool layer**, not the prompt: in eval mode the ClinVar tool is not registered and VEP clinical fields are stripped before the LLM sees them.
- **Eval-mode cache:** VEP responses are stripped before caching *and* on read, so an old cache entry cannot leak ClinVar fields.
- **Abstention:** `uncertain` *is* the abstain answer. Accuracy/F1 are computed on cases labelled pathogenic or benign; coverage = share not `uncertain`. It is never counted as an error.
