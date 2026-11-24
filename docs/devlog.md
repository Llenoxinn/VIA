# Devlog

## 2026-11-24
- Done: wrote AGENTS.md, CLAUDE.md, PLAN.md, ARCHITECTURE.md, README.md, .gitignore, .env.example.
- W5 review (Haiku): fixed fixtures gitignore, abstention definition, ClinVar star wording, eval-mode cache, layout gaps. Rejected: licence rows, which stay 'verify at M1' by plan.
- Stopped at: M0 — git not yet initialised, no code.
- Next: user reviews docs (optionally grill the plan, W6); then `git init`, first commit, set up venv, smoke-test APIs.
- User decisions: ClinVar ≥ 3-star only (R7); add post-cutoff subset (R2); UniProt is first cut if M1 runs long (R8).
- Grilled the plan; decisions D1–D8 recorded in PLAN.md §3–4 (3-star main + 2-star + post-cutoff sets, merged labels, missense only, published baseline cut-offs, Gemini Flash free tier, balanced accuracy headline, found/not_found/error states, no deadline).
- W5 review 2: fixed set overlap, post-cutoff definition, metric formula, baseline not_found handling, Groq wording, placeholder model ID. Rejected: mojibake (display artefact, file is valid UTF-8) and G5 (push was user-requested).
- Next: then M0 env setup, check Gemini limits and training cutoff, smoke script.
- M0 (partial): pushed bb0c8ad. Added scripts/smoke_apis.py (stdlib only, LIVE). All 6 data sources OK. Gemini skipped (no key yet).
- W5 review: smoke script now fails on missing fields and checks the ref itself; .env quotes stripped. Rejected: "results unverified" (script was run, output seen).
- Mistake: example variant 17:43094464:C:T had the wrong ref (it is T). Fix: P7 in AGENTS.md (check ref before using a variant ID).
- Installed Python 3.13.17 (winget, user scope); created .venv with py -3.13; smoke test passes in it.
- Next: user adds GEMINI_API_KEY to .env; rerun smoke test; pin Flash model, note limits + training cutoff.
- Data prep: downloaded data/variant_summary.txt.gz (458.6 MB) and data/AlphaMissense_hg38.tsv.gz (643.0 MB) into git-ignored data/; verified gzip headers (note: AlphaMissense header specifies CC BY-NC-SA 4.0 for P6 check).
- R7 & P6 check: verified AlphaMissense licence in TSV header as CC BY-NC-SA 4.0 and updated ARCHITECTURE.md. Counted GRCh38 missense SNVs in data/variant_summary.txt.gz (9,356,209 rows; strict merged ClinSig): 3+ star pathogenic=3,536 (133 genes; definite=1,637 across 120 genes), benign=1,557 (115 genes; definite=903 across 106 genes), 137 unique genes; 2-star pathogenic=22,459 (2,277 genes; definite=4,518 across 1,136 genes), benign=40,014 (7,130 genes; definite=12,739 across 5,148 genes), 7,499 unique genes; combined 2+ star LastEvaluated by year: 2024=7,265 (4,517 path / 2,748 ben), 2025=18,405 (9,471 path / 8,934 ben), 2026=27,556 (6,803 path / 20,753 ben) — sufficient for M3 sets.
- W5 review (flash_lite): reviewed ARCHITECTURE.md and devlog diff — no concrete problems found.
