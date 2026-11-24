# PLAN.md

## 1. Goal
Build and honestly evaluate a tool-using LLM agent that classifies single-nucleotide variants (GRCh38) as likely pathogenic / likely benign / uncertain, with a cited report. Outcome: a public repo, a results table against baselines, a failure analysis, and one resume line backed by numbers.

## 2. Success criteria
- `via classify 17:43094464:C:T` (example) prints a validated JSON report in under ~60 s.
- Eval on ~200 balanced ClinVar variants (≥ 3-star review = expert panel or practice guideline; fixed seed), plus a separate post-cutoff subset (labelled after the LLM's training cutoff) runs end to end from one command.
- Results table: agent vs gnomAD-only rule vs AlphaMissense alone vs LLM-no-tools, with F1, accuracy on answered cases, and coverage (share not abstained).
- Zero leakage: test proves ClinVar data for the test variant never reaches the agent in eval mode.
- `pytest` passes offline.

## 3. Scope
### 3.1 In scope
- Single-nucleotide variants (SNVs) on GRCh38 only.
- Tools: Ensembl VEP (consequence), gnomAD (population frequency), AlphaMissense (score), UniProt (protein features), AlphaFold DB (pLDDT confidence at the residue).
- ClinVar used only as ground truth (and as a tool outside eval mode).
- CLI only. One LLM provider (Anthropic Claude).

### 3.2 Out of scope (needs explicit user request)
- Indels, structural variants, copy-number changes, GRCh37.
- Web UI, database, Docker, cloud deploy.
- Full ACMG/AMP criteria engine.
- Fine-tuning or training models.
- Multiple LLM providers, multi-agent setups.
- Patient data of any kind.

## 4. Milestones (≈ 1 week each)
| # | Milestone | Done when |
|---|---|---|
| M0 | Docs + prerequisites | These docs exist, git initialised, env set up, smoke script hits each API once |
| M1 | Tools | Each tool returns a typed result; offline fixture tests pass |
| M2 | Agent loop | Agent classifies one variant end to end; report schema validated; claims cite call IDs |
| M3 | Eval dataset + leakage guard | 3-star set + post-cutoff subset built with seed; leakage test passes |
| M4 | Baselines + metrics | All 4 methods scored; results table generated |
| M5 | Analysis + write-up | Failure cases reviewed, memorisation check, README results section |

## 5. Risks
| ID | Risk | Mitigation |
|---|---|---|
| R1 | Leakage via VEP colocated ClinVar fields or cache | Strip fields in eval mode; test (P1) |
| R2 | LLM memorised famous variants | No-tools baseline; optional post-cutoff subset |
| R3 | API rate limits / downtime | Disk cache, retries, recorded fixtures |
| R4 | AlphaMissense file is large (~GB) | Download once outside git; index only needed rows |
| R5 | LLM cost of eval runs | Cache responses; small dev subset (20) before full run |
| R6 | Class imbalance / easy variants inflate scores | Balanced sampling; report per-consequence breakdown |
| R7 | Too few 3-star benign variants for a balanced 200 (or post-cutoff set too small) | Count at M3 first; shrink set size rather than lower the star bar; report n |
| R8 | M1 runs long | Cut UniProt tool first (AlphaFold pLDDT gives a similar signal) |
