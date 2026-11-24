"""Custom exceptions for VIA evidence tools."""

from __future__ import annotations


class EvalModeLeakageError(RuntimeError):
    """Raised if a ClinVar lookup is invoked while eval_mode is enabled (P1)."""
