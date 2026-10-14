"""Regression for discount totals in the external Claude scanner bridge.

Load the pure mapper without importing the optional, locally licensed scanner
or starting its Flask service. No credentials or user receipts are needed.
"""
import ast
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SOURCE = Path(__file__).resolve().parents[2] / "tools/receipt_scanner/inhuis_demo_bridge.py"


def _load_mapper():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    names = {"_canonical_result", "_decimal", "_purchase_parts", "_failed_result"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == names
    scope = {
        "Any": Any,
        "Decimal": Decimal,
        "datetime": datetime,
        "timezone": timezone,
        "scan_engine": SimpleNamespace(CLAUDE_MODEL="test-model"),
        "PROVIDER_CODE": "in-huis-demo",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["_canonical_result"]


def _parsed(lines):
    return {
        "totals_match": True,
        "receipt": {
            "total_amount": "8.00",
            "store_name": "Testwinkel",
            "purchase_at": "2026-10-14T10:00:00",
            "lines": lines,
        },
    }


def _map(lines):
    return _load_mapper()(
        scan_id="test-scan",
        sha256="a" * 64,
        mime_type="image/jpeg",
        parsed=_parsed(lines),
    )


def test_separate_negative_discount_is_counted():
    result = _map([
        {"kind": "product", "raw_label": "Artikel", "line_total": "10.00"},
        {"kind": "discount", "raw_label": "Actiekorting", "line_total": "-2.00"},
    ])
    assert result["status"] == "completed"
    assert result["receipt"]["totals"]["discount_total"] == "2.00"
    assert result["receipt"]["lines"][1]["line_type"] == "discount"
    assert Decimal(str(result["receipt"]["lines"][1]["line_total"])) == Decimal("-2")


def test_explicit_discount_not_double_counted():
    result = _map([
        {"kind": "product", "raw_label": "Artikel", "line_total": "10.00", "discount_amount": "-1.00"},
        {"kind": "discount", "raw_label": "Actiekorting", "line_total": "-2.00", "discount_amount": "-2.00"},
    ])
    assert result["receipt"]["totals"]["discount_total"] == "3.00"


def test_missing_discount_is_not_invented():
    result = _map([{"kind": "product", "raw_label": "Artikel", "line_total": "8.00"}])
    assert result["receipt"]["totals"]["discount_total"] is None
