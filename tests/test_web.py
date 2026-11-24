"""Offline tests for the interactive local VIA Web UI server."""

from __future__ import annotations

import threading
from pathlib import Path

import httpx

from tests.test_tools import NO_SLEEP, make_fixture_transport
from via.cache import DiskCache
from via.runner import SAMPLE_VARIANTS, inspect_variant
from via.web import create_server


def test_web_server_routes_offline(tmp_path: Path) -> None:
    cache = DiskCache(tmp_path)
    transport = make_fixture_transport()

    def offline_inspector(variant: str, *, eval_mode: bool = False):
        with httpx.Client(transport=transport, trust_env=False) as client:
            return inspect_variant(
                variant,
                eval_mode=eval_mode,
                cache=cache,
                client=client,
                sleep_fn=NO_SLEEP,
            )

    server = create_server("127.0.0.1", 0, inspector_fn=offline_inspector)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{port}"
        with httpx.Client(base_url=base_url, timeout=10.0, trust_env=False) as client:
            home = client.get("/")
            assert home.status_code == 200
            assert "text/html" in home.headers["content-type"]
            assert "VIA" in home.text
            assert "/api/inspect" in home.text

            health = client.get("/api/health")
            assert health.status_code == 200
            assert health.json()["samples"] == SAMPLE_VARIANTS

            std = client.post("/api/inspect", json={"variant": "17:43094464:T:C", "eval_mode": False})
            assert std.status_code == 200
            std_json = std.json()
            assert std_json["eval_mode"] is False
            assert len(std_json["tool_calls"]) == 6
            assert any(tc["tool"] == "clinvar_lookup" for tc in std_json["tool_calls"])

            evl = client.post("/api/inspect", json={"variant": "17:43094464:T:C", "eval_mode": True})
            assert evl.status_code == 200
            evl_json = evl.json()
            assert evl_json["eval_mode"] is True
            assert len(evl_json["tool_calls"]) == 5
            assert all(tc["tool"] != "clinvar_lookup" for tc in evl_json["tool_calls"])

            bad_var = client.post("/api/inspect", json={"variant": "bad-variant"})
            assert bad_var.status_code == 400
            assert "error" in bad_var.json()

            bad_json = client.post("/api/inspect", content=b"{not-json", headers={"Content-Type": "application/json"})
            assert bad_json.status_code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
