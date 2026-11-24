# VIA — Variant Interpretation Agent

A tool-using LLM agent that reads public evidence about a human GRCh38 missense variant and writes a cited report: likely pathogenic, likely benign, or uncertain. Evaluated against ClinVar labels (3-star and up) and simple baselines.

> **Not a clinical tool. Not medical advice.** Public research data only.

## Status
**M1 complete** — evidence tools, disk cache, leakage guard, CLI (`via inspect`), interactive local Web UI (`via ui`), and offline tests. Gemini LLM agent loop comes in M2 (no API key needed for M1). See [PLAN.md](PLAN.md).

## Prerequisites
- **Python 3.12+** (3.13 used here; on Windows create the venv with `py -3.13 -m venv .venv`)
- **Git**
- **Gemini API key** (needed later for M2/M4; free from aistudio.google.com, put in `.env` — see `.env.example`)
- **Disk:** ~5 GB free if downloading full ClinVar + AlphaMissense archives into `data/` (never committed)
- **Internet** for live API calls; `pytest` runs completely offline

## Setup & Quickstart
```powershell
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest -v
```

### Run M1 tools from the CLI
```powershell
via inspect 17:43094464:T:C
via inspect 17:43094464:T:C --eval-mode
```

### Launch the interactive local Web UI
```powershell
via ui
```
Then open `http://127.0.0.1:8000` (opens automatically unless `--no-open` is passed).
