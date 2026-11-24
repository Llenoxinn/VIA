"""Lightweight interactive local HTTP server for the VIA Web UI."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from via.cache import DiskCache
from via.runner import SAMPLE_VARIANTS, inspect_variant
from via.schema import InspectionResult

InspectorFn = Callable[..., InspectionResult]
_STATIC_INDEX = Path(__file__).with_name("static") / "index.html"
_MAX_BODY_BYTES = 65_536


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    inspector_fn: InspectorFn | None = None,
    cache: DiskCache | None = None,
) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer serving the VIA interactive UI and JSON API."""
    if inspector_fn is not None:
        active_inspector = inspector_fn
    else:
        active_cache = cache if cache is not None else DiskCache()

        def active_inspector(variant: str, *, eval_mode: bool = False) -> InspectionResult:
            return inspect_variant(variant, eval_mode=eval_mode, cache=active_cache)

    class ViaRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html_bytes: bytes) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(html_bytes)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                if not _STATIC_INDEX.is_file():
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "UI asset missing"})
                    return
                self._send_html(_STATIC_INDEX.read_bytes())
                return

            if path == "/api/health":
                self._send_json(
                    HTTPStatus.OK,
                    {"status": "ok", "milestone": "M1", "samples": SAMPLE_VARIANTS},
                )
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown route: {path}"})

        def do_POST(self) -> None:
            path = self.path.split("?", 1)[0]
            if path != "/api/inspect":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Unknown route: {path}"})
                return

            raw_len = self.headers.get("Content-Length")
            if raw_len is None or not raw_len.isdigit():
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Valid Content-Length header required"})
                return
            length = int(raw_len)
            if length <= 0 or length > _MAX_BODY_BYTES:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Request body size out of bounds"})
                return

            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"Invalid JSON body: {exc}"})
                return

            if not isinstance(body, dict) or not isinstance(body.get("variant"), str):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "JSON body must contain string field 'variant'"})
                return

            eval_mode = bool(body.get("eval_mode", False))
            try:
                result = active_inspector(body["variant"], eval_mode=eval_mode)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(exc).__name__}: {exc}"})
                return

            self._send_json(HTTPStatus.OK, result.model_dump(mode="json"))

    return ThreadingHTTPServer((host, port), ViaRequestHandler)
