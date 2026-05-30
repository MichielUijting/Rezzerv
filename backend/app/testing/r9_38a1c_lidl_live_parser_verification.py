from __future__ import annotations

import json
import mimetypes
import traceback
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.services.receipt_service import parse_receipt_content

TARGET_FILENAMES = (
    "Lidl App 1.png",
    "Lidl App 2.png",
    "Lidl App 4.pdf",
)

SEARCH_ROOTS = (
    Path.cwd(),
    Path.cwd() / "backend",
    Path.cwd() / "data",
    Path.cwd() / "backend" / "data",
    Path("/app"),
    Path("/app/backend"),
    Path("/app/backend/data"),
    Path("/tmp"),
)

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
}


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _find_source_file(filename: str) -> Path | None:
    seen_roots: set[Path] = set()
    for root in SEARCH_ROOTS:
        try:
            resolved = root.resolve()
        except Exception:
            continue
        if resolved in seen_roots or not resolved.exists():
            continue
        seen_roots.add(resolved)

        direct = resolved / filename
        if direct.is_file():
            return direct

        try:
            for path in resolved.rglob(filename):
                if any(part in SKIP_DIR_NAMES for part in path.parts):
                    continue
                if path.is_file():
                    return path
        except Exception:
            continue
    return None


def _line_payload(line: dict[str, Any]) -> dict[str, Any]:
    trace = line.get("producer_trace") if isinstance(line, dict) else None
    if not isinstance(trace, dict):
        trace = {}
    return {
        "raw_label": line.get("raw_label"),
        "normalized_label": line.get("normalized_label"),
        "quantity": line.get("quantity"),
        "unit": line.get("unit"),
        "unit_price": line.get("unit_price"),
        "line_total": line.get("line_total"),
        "discount_amount": line.get("discount_amount"),
        "source_index": line.get("source_index"),
        "trace_function": trace.get("function_name"),
        "trace_branch": trace.get("append_branch"),
        "near_duplicate_consolidated": trace.get("near_duplicate_consolidated"),
        "near_duplicate_consolidated_label": trace.get("near_duplicate_consolidated_label"),
        "near_duplicate_consolidated_amount": trace.get("near_duplicate_consolidated_amount"),
    }


def _summarize_result(filename: str, source_path: Path) -> dict[str, Any]:
    file_bytes = source_path.read_bytes()
    mime_type = mimetypes.guess_type(str(source_path))[0] or "application/octet-stream"
    result = parse_receipt_content(file_bytes, filename, mime_type)
    lines = list(getattr(result, "lines", None) or [])
    gross_sum = sum((_decimal(line.get("line_total")) for line in lines), Decimal("0.00")).quantize(Decimal("0.01"))
    line_discount_sum = sum((_decimal(line.get("discount_amount")) for line in lines), Decimal("0.00")).quantize(Decimal("0.01"))
    discount_total = getattr(result, "discount_total", None)
    effective_discount = _decimal(discount_total) if discount_total is not None else line_discount_sum
    net_sum = (gross_sum + effective_discount).quantize(Decimal("0.01"))

    return {
        "filename": filename,
        "source_path": str(source_path),
        "mime_type": mime_type,
        "store_name": getattr(result, "store_name", None),
        "parse_status": getattr(result, "parse_status", None),
        "total_amount": str(getattr(result, "total_amount", None)),
        "line_count": len(lines),
        "gross_line_sum": str(gross_sum),
        "discount_total": str(discount_total) if discount_total is not None else None,
        "line_discount_sum": str(line_discount_sum),
        "net_line_sum": str(net_sum),
        "key_observations": {
            "jonge_bladsla_lines": [
                _line_payload(line)
                for line in lines
                if "jonge bladsla" in str(line.get("normalized_label") or line.get("raw_label") or "").lower()
            ],
            "mexicaanse_kruiden_lines": [
                _line_payload(line)
                for line in lines
                if "mexicaanse kruiden" in str(line.get("normalized_label") or line.get("raw_label") or "").lower()
            ],
            "aardappel_zoet_lines": [
                _line_payload(line)
                for line in lines
                if "aardappel zoet" in str(line.get("normalized_label") or line.get("raw_label") or "").lower()
            ],
            "weight_detail_as_product_lines": [
                _line_payload(line)
                for line in lines
                if "kg" in str(line.get("normalized_label") or line.get("raw_label") or "").lower()
                and "aardappel" not in str(line.get("normalized_label") or line.get("raw_label") or "").lower()
            ],
        },
        "lines": [_line_payload(line) for line in lines],
    }


def main() -> int:
    output: dict[str, Any] = {
        "test": "R9-38A1c Lidl live parser verification",
        "mode": "read_only_live_parse",
        "parser_changed": False,
        "status_classification_changed": False,
        "target_filenames": list(TARGET_FILENAMES),
        "results": [],
        "missing_files": [],
        "parse_errors": [],
    }

    for filename in TARGET_FILENAMES:
        source_path = _find_source_file(filename)
        if source_path is None:
            output["missing_files"].append(filename)
            continue
        try:
            output["results"].append(_summarize_result(filename, source_path))
        except Exception as exc:
            output["parse_errors"].append(
                {
                    "filename": filename,
                    "source_path": str(source_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback_tail": traceback.format_exc().splitlines()[-8:],
                }
            )

    print(json.dumps(output, indent=2, ensure_ascii=False))

    if output["missing_files"]:
        print("R9-38A1C LIVE PARSER VERIFICATION INCOMPLETE: source files not found")
        return 2
    if output["parse_errors"]:
        print("R9-38A1C LIVE PARSER VERIFICATION COMPLETED WITH PARSE ERRORS")
        return 1
    print("R9-38A1C LIVE PARSER VERIFICATION COMPLETED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
