# VIA — Variant Interpretation Agent

A tool-using LLM agent that reads public evidence about a DNA variant and writes a cited report: likely pathogenic, likely benign, or uncertain. Evaluated against expert-reviewed ClinVar labels and simple baselines.

> **Not a clinical tool. Not medical advice.** Public research data only.

## Status
M0 — docs and prerequisites. See `PLAN.md`.

## Prerequisites
- **Python 3.12+** (3.14 installed here; check `python --version`)
- **Git**
- **Anthropic API key** (from console.anthropic.com), put in `.env` — see `.env.example`
- **Disk:** ~5 GB free for ClinVar + AlphaMissense downloads (into `data/`, never committed)
- **Internet** for live API calls; tests run offline

## Setup (once M1 adds `pyproject.toml`)
```
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env   # then add your key
pytest
```
