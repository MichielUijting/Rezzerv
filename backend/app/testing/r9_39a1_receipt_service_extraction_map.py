"""
Technical Design Reference:
- TD Section: TD-08 Test, baseline en regressie
- Module Role: Test or baseline support
- Runtime Type: test
- Used By: see docs/technical/PYTHON-MODULE-CATALOG.md
- Depends On: see generated inventory
- Reads Data: see generated inventory
- Writes Data: see generated inventory
- Status Authority: no
- Refactor Status: classify
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "app" / "services" / "receipt_service.py"


def _risk_for(name: str, size: int) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("persist", "reparse", "insert", "update", "delete", "archive", "restore", "store", "save")):
        return "high"
    if any(token in lowered for token in ("parse", "extract", "classify", "receipt", "ocr", "result")):
        return "medium" if size < 120 else "high"
    return "low" if size < 80 else "medium"


def _target_module_for(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("amount", "price", "decimal", "total", "money", "quantity")):
        return "app/receipt_ingestion/parsing/amount_helpers.py"
    if any(token in lowered for token in ("label", "normalize", "text", "clean")):
        return "app/receipt_ingestion/parsing/text_label_normalization.py"
    if any(token in lowered for token in ("classify", "non_product", "continuation", "candidate")):
        return "app/receipt_ingestion/parsing/line_classification.py"
    if any(token in lowered for token in ("ocr", "image", "pdf", "preprocess")):
        return "app/receipt_ingestion/service_parts/image_ocr_flow.py"
    if any(token in lowered for token in ("store", "chain", "specific", "jumbo", "lidl", "plus", "aldi", "ah")):
        return "app/receipt_ingestion/service_parts/store_specific_parsers.py or profiles/<chain>/"
    if any(token in lowered for token in ("persist", "reparse", "insert", "update", "delete", "archive", "save")):
        return "app/receipt_ingestion/persistence/receipt_table_writer.py"
    if any(token in lowered for token in ("debug", "diagnos", "trace", "summary")):
        return "app/receipt_ingestion/diagnostics/"
    if any(token in lowered for token in ("upload", "service", "receipt")):
        return "keep in receipt_service.py as orchestration unless proven pure"
    return "app/receipt_ingestion/parsing/common_helpers.py"


def _group_for(target_module: str) -> str:
    if "persistence" in target_module:
        return "persistence"
    if "line_classification" in target_module:
        return "classification"
    if "diagnostics" in target_module:
        return "diagnostics"
    if "image_ocr" in target_module:
        return "ocr_flow"
    if "store_specific" in target_module or "profiles" in target_module:
        return "store_profile"
    if "receipt_service.py" in target_module:
        return "orchestration"
    return "low_risk_helpers"


def _called_names(node: ast.AST) -> list[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return sorted(names)


def _print_human(report: dict[str, Any]) -> None:
    print("R9-39A1 RECEIPT_SERVICE EXTRACTION MAP")
    print(f"target={report['target']}")
    print(f"total_lines={report['total_lines']}")
    print(f"top_level_function_count={report['top_level_function_count']}")
    print("\nGROUP SUMMARY")
    for group, summary in sorted(report["group_summary"].items()):
        print(
            f"- {group}: functions={summary['functions']} lines={summary['lines']} "
            f"risk_counts={summary['risk_counts']}"
        )
    print("\nTOP FUNCTIONS BY SIZE")
    for item in report["functions_by_size"][:25]:
        print(
            f"- {item['name']}: lines={item['line_count']} "
            f"risk={item['risk']} group={item['group']} target={item['target_module']}"
        )
    print("\nORDERED EXTRACTION CANDIDATES")
    for item in report["recommended_order"]:
        print(
            f"- {item['phase']}: {item['name']} ({item['line_count']} lines) -> "
            f"{item['target_module']} [{item['risk']}]"
        )


def build_report() -> dict[str, Any]:
    text = TARGET.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    tree = ast.parse(text)

    function_items: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_lineno = getattr(node, "end_lineno", node.lineno)
        size = end_lineno - node.lineno + 1
        target_module = _target_module_for(node.name)
        item = {
            "name": node.name,
            "start_line": node.lineno,
            "end_line": end_lineno,
            "line_count": size,
            "risk": _risk_for(node.name, size),
            "target_module": target_module,
            "group": _group_for(target_module),
            "calls": _called_names(node)[:25],
        }
        function_items.append(item)

    group_summary: dict[str, dict[str, Any]] = {}
    for item in function_items:
        group = item["group"]
        summary = group_summary.setdefault(group, {"functions": 0, "lines": 0, "risk_counts": {}})
        summary["functions"] += 1
        summary["lines"] += item["line_count"]
        summary["risk_counts"][item["risk"]] = summary["risk_counts"].get(item["risk"], 0) + 1

    phase_order = {
        "low_risk_helpers": 1,
        "diagnostics": 2,
        "classification": 3,
        "store_profile": 4,
        "ocr_flow": 5,
        "persistence": 6,
        "orchestration": 7,
    }
    recommended_order = sorted(
        function_items,
        key=lambda item: (phase_order.get(item["group"], 99), {"low": 0, "medium": 1, "high": 2}.get(item["risk"], 9), -item["line_count"]),
    )

    return {
        "test": "R9-39A1 receipt_service extraction map",
        "mode": "read_only_architecture_inventory",
        "target": str(TARGET.relative_to(ROOT)),
        "total_lines": len(lines),
        "top_level_function_count": len(function_items),
        "functions_by_line": function_items,
        "functions_by_size": sorted(function_items, key=lambda item: item["line_count"], reverse=True),
        "group_summary": group_summary,
        "recommended_order": [
            {"phase": index + 1, **item}
            for index, item in enumerate(recommended_order[:40])
        ],
        "architecture_rule": "receipt_service.py should shrink toward orchestration only; extracted code must preserve behavior.",
    }


def main() -> int:
    report = build_report()
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
