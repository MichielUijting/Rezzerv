"""Operator CLI for explicit download of an official translated GPC publication."""
from __future__ import annotations

import argparse
import json
import sys

from app.services.gpc_official_translation_source import download_official_gpc_translation_sync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download een officiële vertaalde GS1 GPC-publicatie.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--language", default="nl")
    parser.add_argument("--format", choices=("xml", "json", "xlsx"), default="xml")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = download_official_gpc_translation_sync(
            args.output_dir,
            language_code=args.language,
            file_format=args.format,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(json.dumps({"status": "failed", "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "downloaded", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
