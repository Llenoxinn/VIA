"""Command-line interface for VIA (`via inspect`, `via ui`)."""

from __future__ import annotations

import argparse
import sys
import webbrowser
from typing import Sequence

from via.cache import DiskCache
from via.runner import inspect_variant
from via.web import create_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="via", description="Variant Interpretation Agent CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="Gather public evidence for one GRCh38 missense SNV")
    inspect_p.add_argument("variant", help="Variant in chr:pos:ref:alt or chr-pos-ref-alt format (GRCh38)")
    inspect_p.add_argument(
        "--eval-mode",
        action="store_true",
        help="Disable ClinVar lookup and strip clinical fields from VEP (P1)",
    )
    inspect_p.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass the local .cache/ directory",
    )

    ui_p = sub.add_parser("ui", help="Launch the interactive local Web UI")
    ui_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui_p.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    ui_p.add_argument("--no-open", action="store_true", help="Do not open the default browser")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the `via` CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "inspect":
        cache = None if args.no_cache else DiskCache()
        try:
            result = inspect_variant(args.variant, eval_mode=args.eval_mode, cache=cache)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(result.model_dump_json(indent=2))
        return 0

    if args.command == "ui":
        server = create_server(args.host, args.port)
        actual_port = server.server_address[1]
        url = f"http://{args.host}:{actual_port}"
        print(f"VIA UI running at {url} (Ctrl+C to stop)")
        if not args.no_open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping VIA UI.")
        finally:
            server.server_close()
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
