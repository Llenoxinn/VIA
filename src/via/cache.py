"""Disk cache for API responses.

Only 'found' and 'not_found' results are persisted; 'error' results are never cached
so transient outages never masquerade as absent evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable

from via.schema import ToolStatus

SanitizerFn = Callable[[Any], Any]


class DiskCache:
    """Simple JSON-on-disk cache keyed by (namespace, key)."""

    def __init__(self, root: Path | str = Path(".cache")) -> None:
        self.root = Path(root)

    def _entry_path(self, namespace: str, key: str) -> Path:
        safe_ns = re.sub(r"[^a-zA-Z0-9._-]", "_", namespace)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / safe_ns / f"{digest}.json"

    def get(
        self,
        namespace: str,
        key: str,
        sanitizer: SanitizerFn | None = None,
    ) -> tuple[bool, ToolStatus | None, Any]:
        """Return (hit, status, payload). Errors and corrupt entries always miss."""
        path = self._entry_path(namespace, key)
        if not path.is_file():
            return False, None, None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False, None, None

        if not isinstance(raw, dict):
            return False, None, None
        status = raw.get("status")
        if status not in ("found", "not_found") or "payload" not in raw:
            return False, None, None

        payload = raw["payload"]
        if sanitizer is not None:
            payload = sanitizer(payload)
        return True, status, payload

    def set(
        self,
        namespace: str,
        key: str,
        status: ToolStatus,
        payload: Any,
        sanitizer: SanitizerFn | None = None,
    ) -> None:
        """Persist 'found' or 'not_found' payload atomically. Ignores 'error'."""
        if status == "error":
            return
        if status not in ("found", "not_found"):
            raise ValueError(f"invalid cache status: {status!r}")

        clean_payload = sanitizer(payload) if sanitizer is not None else payload
        path = self._entry_path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = json.dumps({"status": status, "payload": clean_payload}, ensure_ascii=False)

        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(envelope)
            os.replace(tmp_name, path)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise
