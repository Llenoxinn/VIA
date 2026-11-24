# PLAN.md

## 1. Goal
Build and honestly evaluate a tool-using LLM agent that classifies **missense** single-nucleotide variants (GRCh38) as likely pathogenic / likely benign / uncertain, with a cited report. Outcome: a public repo, a results table against baselines, a failure analysis, and one resume line backed by numbers.

## 2. Success criteria
- `via classify 17:43094464:C:T` (example) prints a validated JSON report in under ~60 s.
- The full eval (all sets in §3.3) runs end to end from one command, with a fixed seed.
- Results table: agent vs gnomAD-only rule vs AlphaMissense alone vs LLM-no-tools, scored as in §3.4.
- Zero leakage: a test proves ClinVar data for the test variant never reaches the agent in eval mode.
- `pytest` passes offline.

## 3. Scope
### 3.1 In scope
- Missense SNVs on GRCh38 only (D3).
- Tools: Ensembl VEP (consequence), gnomAD (population frequency), AlphaMissense (score), UniProt (protein features), AlphaFold DB (pLDDT confidence at the residue).
- Every tool returns `found` / `not_found` / `error`. Errors are retried, never cached; if a key tool still errors, the answer is `uncertain` and the run is flagged (D7).
- ClinVar used only as ground truth (and as a tool outside eval mode).
- CLI only. One LLM provider: **Google Gemini Flash, free tier**, for both the agent and the no-tools baseline; every response cached; exact model version recorded (D5). Groq is a contingency, not built: switching needs a plan update (R9).

### 3.2 Out of scope (needs explicit user request)
- Indels, structural variants, copy-number changes, GRCh37, non-missense variants.
- Web UI, database, Docker, cloud deploy.
- Full ACMG/AMP criteria engine.
- Fine-tuning or training models.
- Multiple LLM providers in code (a Groq adapter), multi-agent setups.
- Patient data of any kind.

### 3.3 Evaluation sets (D1, D2)
Labels: Pathogenic + Likely pathogenic → `pathogenic`; Benign + Likely benign → `benign`; VUS and conflicting excluded.

| Set | Filter | Role |
|---|---|---|
| Main | ClinVar ≥ 3-star (expert panel / practice guideline), ~200 balanced | Headline result |
| Secondary | ClinVar 2-star (multiple submitters, no conflicts), larger, more genes | Breadth check, reported separately, labelled noisier |
| Post-cutoff | ≥ 2-star, ClinVar "date last evaluated" after the pinned Gemini model's training cutoff; disjoint from Main and Secondary | Memorisation check (R2); rebuilt if the model changes |
| Definite sub-score | Main set restricted to definite Pathogenic / Benign | Sub-analysis |
| Dev | 20 variants, disjoint from all above | Development only, never reported |

Main, Secondary and Post-cutoff are mutually disjoint (no variant scored twice). All sets report per-gene results.

### 3.4 Metrics, fixed before any results (D6)
- **Headline:** balanced accuracy = (recall on pathogenic + recall on benign) / 2 over all variants, where `uncertain` counts as a miss.
- **Detail:** F1 on answered variants, and coverage (share not `uncertain`).
- **Baselines use published cut-offs, never tuned (D4):**
  - AlphaMissense: < 0.34 benign, > 0.564 pathogenic, else uncertain (Cheng et al. 2023, *Science*, doi:10.1126/science.adg7492).
  - gnomAD: allele frequency > 5% benign (ACMG/AMP BA1: Richards et al. 2015, *Genet Med*, doi:10.1038/gim.2015.30; refined by Ghosh et al. 2018, *Hum Mutat*, doi:10.1002/humu.23642), else uncertain.
  - A baseline whose input is `not_found` or `error` outputs `uncertain`. Error counts are reported per method.
  - DOIs to be verified before M4.

## 4. Milestones (≈ 1 week each, no deadline — D8)
| # | Milestone | Done when |
|---|---|---|
| M0 | Docs + prerequisites | These docs exist, git initialised, env set up, smoke script hits each API once, Gemini free limits checked |
| M1 | Tools | Each tool returns a typed found/not_found/error result; offline fixture tests pass |
| M2 | Agent loop | Agent classifies one variant end to end; report schema validated; claims cite call IDs |
| M3 | Eval datasets + leakage guard | All §3.3 sets built with seed; counts reported (R7); leakage test passes |
| M4 | Baselines + metrics | All 4 methods scored per §3.4; results table generated |
| M5 | Analysis + write-up | Failure cases reviewed, memorisation check, README results section |

**Cut order if time is ever short:** UniProt tool → 2-star secondary set → definite sub-score.

## 5. Risks
| ID | Risk | Mitigation |
|---|---|---|
| R1 | Leakage via VEP colocated ClinVar fields or cache | Strip fields in eval mode; test (P1) |
| R2 | LLM memorised famous variants (3-star sets cluster in well-studied genes) | No-tools baseline; post-cutoff set; per-gene results; 2-star secondary set |
| R3 | API rate limits / downtime | Disk cache, retries, found/not_found/error states, recorded fixtures |
| R4 | AlphaMissense file is large (~GB) | Download once outside git; index only needed rows |
| R5 | Free-tier LLM quota limits eval runs | Cache responses; dev set (20) first; spread full runs over days |
| R6 | Class imbalance / easy variants inflate scores | Missense only; balanced sampling; balanced accuracy |
| R7 | Too few 3-star benign missense variants (or post-cutoff set too small) | Count at M3 first; shrink set size rather than lower the star bar; report n |
| R8 | M1 runs long | Cut UniProt tool first (AlphaFold pLDDT gives a similar signal) |
| R9 | Gemini free tier changes or shrinks | Pin model version; fall back to Groq (needs plan update) |
| R10 | Weaker free model hallucinates evidence | Grounding check (P2) rejects uncited claims; report the rejection rate |
