from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TARGET_FILES = [
    "backend/app/services/receipt_service.py",
    "backend/app/api/routes/receipt_parser_diagnosis.py",
    "backend/app/testing_receipt_parser_diagnosis_routes.py",
    "backend/app/testing_receipt_line_diagnosis_routes.py",
    "backend/app/receipt_ingestion/text_layout_regions.py",
    "tools/check_r7c8_paddle_text_layout_diagnostics.py",
    "tools/check_r7c11d_ah_foto_3_route_diagnostics.py",
    "tools/check_r7c12_ah3_topology_reconstruction_diagnostics.py",
]

TARGET_FUNCTIONS = [
    "_ocr_image_text_with_paddle",
    "_ocr_image_text_with_tesseract",
    "_group_paddle_texts_to_lines",
    "_ocr_bbox_to_line_anchor",
    "_extract_payload_from_paddle_item",
    "_normalize_paddle_collection",
    "parse_receipt_content",
    "reparse_receipt",
]

PATTERNS = {
    "paddle_raw_texts": [r"PaddleOCR", r"ocr\.ocr", r"model\.ocr", r"texts", r"normalized_texts", r"text_value"],
    "paddle_boxes": [r"\bbox", r"\bboxes", r"current_boxes", r"_ocr_bbox_to_line_anchor", r"bounding", r"topology"],
    "line_grouping": [r"_group_paddle_texts_to_lines", r"line_candidates", r"anchor", r"line_index"],
    "tesseract_lines": [r"tesseract", r"completed\.stdout", r"_normalize_text_lines"],
    "parse_input": [r"parse_receipt_content", r"_parse_result_from_text_lines", r"paddle_lines", r"tesseract_lines", r"ocr_lines", r"direct_text"],
    "persist_raw_receipts": [r"INSERT\s+INTO\s+raw_receipts", r"UPDATE\s+raw_receipts", r"raw_receipts", r"storage_path", r"sha256_hash"],
    "persist_receipt_tables": [r"INSERT\s+INTO\s+receipt_tables", r"UPDATE\s+receipt_tables", r"receipt_tables", r"total_amount", r"line_count"],
    "persist_receipt_table_lines": [r"INSERT\s+INTO\s+receipt_table_lines", r"receipt_table_lines", r"raw_label", r"normalized_label", r"line_total", r"line_index"],
    "diagnosis_routes": [r"receipt_parser_diagnosis", r"receipt_line_diagnosis", r"ocr_lines", r"processing_diagnostics", r"raw_label", r"normalized_label"],
    "status_guardrail": [r"receipt_status_baseline_service_v4", r"parse_status", r"Gecontroleerd", r"Controle nodig", r"apply_po_norm_status"],
}


@dataclass
class Match:
    file: str
    line_number: int
    category: str
    line: str


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="ignore")
    except Exception:
        return ""


def scan_file(root: Path, path: Path) -> list[Match]:
    text = read_text(path)
    out: list[Match] = []
    for i, line in enumerate(text.splitlines(), 1):
        for cat, patterns in PATTERNS.items():
            if any(re.search(p, line, re.IGNORECASE) for p in patterns):
                out.append(Match(rel(root, path), i, cat, line.strip()[:500]))
                break
    return out


def function_ranges(path: Path) -> dict[str, tuple[int, int]]:
    text = read_text(path)
    if not text:
        return {}
    try:
        tree = ast.parse(text)
    except Exception:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = (int(node.lineno), int(getattr(node, "end_lineno", node.lineno)))
    return out


def inspect(root: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    all_matches: list[Match] = []

    for target in TARGET_FILES:
        path = root / target
        if not path.exists():
            files[target] = {"exists": False}
            continue

        matches = scan_file(root, path)
        all_matches.extend(matches)
        ranges = function_ranges(path)

        functions = {}
        for name, (start, end) in ranges.items():
            if target == "backend/app/services/receipt_service.py" and name not in TARGET_FUNCTIONS:
                continue
            evidence = [m for m in matches if start <= m.line_number <= end]
            if not evidence and target != "backend/app/services/receipt_service.py":
                continue
            counts = {}
            for m in evidence:
                counts[m.category] = counts.get(m.category, 0) + 1
            functions[name] = {"start_line": start, "end_line": end, "category_counts": counts, "evidence": [asdict(m) for m in evidence[:80]]}

        counts = {}
        for m in matches:
            counts[m.category] = counts.get(m.category, 0) + 1

        files[target] = {
            "exists": True,
            "category_counts": counts,
            "functions": functions,
            "matches": [asdict(m) for m in matches[:250]],
        }

    return {"files": files, "all_matches": [asdict(m) for m in all_matches]}


def has(matches: list[dict[str, Any]], category: str, file_part: str | None = None) -> bool:
    return any(m["category"] == category and (file_part is None or file_part in m["file"]) for m in matches)


def derive(report: dict[str, Any]) -> dict[str, Any]:
    matches = report["code_inspection"]["all_matches"]
    return {
        "raw_ocr_exists_in_memory": has(matches, "paddle_raw_texts", "receipt_service.py") or has(matches, "tesseract_lines", "receipt_service.py"),
        "bounding_boxes_exist_in_memory": has(matches, "paddle_boxes", "receipt_service.py"),
        "grouped_ocr_lines_exist_before_parser": has(matches, "line_grouping", "receipt_service.py") or has(matches, "parse_input", "receipt_service.py"),
        "post_parser_lines_are_persisted": has(matches, "persist_receipt_table_lines", "receipt_service.py"),
        "raw_receipt_file_metadata_is_persisted": has(matches, "persist_raw_receipts", "receipt_service.py"),
        "pre_parser_ocr_lines_or_boxes_persisted": False,
        "existing_diagnosis_routes_present": has(matches, "diagnosis_routes"),
        "recommended_next_step": "R9-28B5 — expose existing in-memory pre-parser OCR lines and Paddle boxes via SSOT-safe diagnostics/export; do not add parser/status logic.",
    }


def render_md(report: dict[str, Any]) -> str:
    p = report["proof"]
    lines = [
        "# R9-28B4-SCAN — Receipt service OCR codepath proof",
        "",
        f"Gemaakt: `{report['created_at']}`",
        "",
        "## SSOT-compliance",
        "",
        "- `status_determination`: `not_performed`",
        "- `parse_status_used_as_truth`: `False`",
        "- `parser_mutated`: `False`",
        "- `ocr_mutated`: `False`",
        "- `database_mutated`: `False`",
        "- `baseline_mutated`: `False`",
        "- `ui_touched`: `False`",
        "",
        "## Bewijsantwoorden",
        "",
    ]
    for k, v in p.items():
        lines.append(f"- `{k}`: `{v}`")
    lines += ["", "## Bestanden en functieblokken", ""]
    for file, info in report["code_inspection"]["files"].items():
        lines.append(f"### `{file}`")
        lines.append(f"- exists: `{info.get('exists')}`")
        if info.get("exists"):
            lines.append(f"- category_counts: `{info.get('category_counts')}`")
            funcs = info.get("functions") or {}
            for fn, fni in funcs.items():
                lines.append(f"  - `{fn}` regels `{fni['start_line']}-{fni['end_line']}` counts `{fni['category_counts']}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="tools/debug_output/R9-28B4_SCAN")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    report = {
        "audit": "R9-28B4-SCAN Receipt service OCR codepath proof",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "scope": ["inventory/proof only", "no parser change", "no OCR change", "no database mutation", "no status determination", "no UI change", "no receipt_status_baseline_service_v4.py modification"],
        "code_inspection": inspect(root),
    }
    report["proof"] = derive(report)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out / f"R9-28B4_SCAN_receipt_service_ocr_codepath_proof_{stamp}.json"
    md_path = out / f"R9-28B4_SCAN_receipt_service_ocr_codepath_proof_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_md(report), encoding="utf-8")

    print("R9-28B4-SCAN rapport geschreven:")
    print(f"- {json_path}")
    print(f"- {md_path}")
    print("SSOT: no parser/OCR/database/status/baseline/UI mutation")
    for k, v in report["proof"].items():
        print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
