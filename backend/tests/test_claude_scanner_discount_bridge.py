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
        {"kind": "adjustment", "raw_label": "Actiekorting", "line_total": "-2.00"},
    ])
    assert result["status"] == "completed"
    assert result["receipt"]["totals"]["discount_total"] == "2.00"
    assert result["receipt"]["lines"][1]["line_type"] == "discount"
    assert Decimal(str(result["receipt"]["lines"][1]["line_total"])) == Decimal("-2")


def test_explicit_discount_not_double_counted():
    result = _map([
        {"kind": "product", "raw_label": "Artikel", "line_total": "10.00", "discount_amount": "-1.00"},
        {"kind": "adjustment", "raw_label": "Actiekorting", "line_total": "-2.00"},
    ])
    assert result["receipt"]["totals"]["discount_total"] == "3.00"


def test_missing_discount_is_not_invented():
    result = _map([{"kind": "product", "raw_label": "Artikel", "line_total": "8.00"}])
    assert result["receipt"]["totals"]["discount_total"] is None


def test_ah_single_discount_receipt_total():
    """Anonymized AH receipt: 4.37 - 0.15 + 0.80 stamps = 5.02."""
    result = _map([
        {"kind": "product", "raw_label": "Artikel A", "line_total": "1.19"},
        {"kind": "product", "raw_label": "Artikel B", "line_total": "0.99"},
        {"kind": "product", "raw_label": "Artikel C", "line_total": "2.19"},
        {"kind": "adjustment", "raw_label": "Bonus Box", "line_total": "-0.15"},
        {"kind": "adjustment", "raw_label": "Koopzegels", "line_total": "0.80"},
    ])
    assert result["status"] == "completed"
    assert result["receipt"]["totals"]["discount_total"] == "0.15"
    assert result["receipt"]["lines"][3]["line_type"] == "discount"
    assert result["receipt"]["lines"][4]["line_type"] == "fee"
    amount = sum(Decimal(str(line["line_total"])) for line in result["receipt"]["lines"])
    assert amount == Decimal("5.02")


def test_ah_five_discounts_not_confused_with_stamps():
    """Anonymized AH totals: 43.35 - 2.28 + 8.20 stamps = 49.27."""
    discount_values = ["-0.54", "-0.20", "-0.49", "-0.54", "-0.51"]
    lines = [{"kind": "product", "raw_label": "Productensom", "line_total": "43.35"}]
    lines += [
        {"kind": "adjustment", "raw_label": f"Voordeel {index}", "line_total": amount}
        for index, amount in enumerate(discount_values, start=1)
    ]
    lines.append({"kind": "adjustment", "raw_label": "Koopzegels", "line_total": "8.20"})
    result = _map(lines)
    assert result["receipt"]["totals"]["discount_total"] == "2.28"
    assert [line["line_type"] for line in result["receipt"]["lines"][1:6]] == ["discount"] * 5
    assert result["receipt"]["lines"][-1]["line_type"] == "fee"
    amount = sum(Decimal(str(line["line_total"])) for line in result["receipt"]["lines"])
    assert amount == Decimal("49.27")


def test_product_discount_and_positive_stamps_are_separate():
    result = _map([
        {"kind": "product", "raw_label": "Artikel", "line_total": "10.00", "discount_amount": "1.00"},
        {"kind": "adjustment", "raw_label": "Koopzegels", "line_total": "0.80"},
    ])
    assert result["receipt"]["totals"]["discount_total"] == "1.00"
    assert result["receipt"]["lines"][0]["line_type"] == "product"
    assert result["receipt"]["lines"][1]["line_type"] == "fee"


def test_ah_mobile_photo_separate_bonus_and_stamps():
    """Source contract: 13.23 - 2.88 + 1.00 = 11.35."""
    result = _map([
        {"kind": "product", "raw_label": "Artikelen", "line_total": "13.23"},
        {"kind": "adjustment", "raw_label": "BONUS", "line_total": "-2.88"},
        {"kind": "adjustment", "raw_label": "KOOPZEGELS", "line_total": "1.00"},
    ])
    assert result["receipt"]["totals"]["discount_total"] == "2.88"
    assert [line["line_type"] for line in result["receipt"]["lines"]] == ["product", "discount", "fee"]
    assert sum(Decimal(str(line["line_total"])) for line in result["receipt"]["lines"]) == Decimal("11.35")


def _load_semantics():
    """Exercise the real persisted line-role mapping without app/database startup."""
    source = SOURCE.parents[1] / "backend/app/receipt_ingestion/receipt_line_semantics.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = [
        node for node in tree.body
        if (isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id.startswith("ROLE_") for t in node.targets
        ))
        or (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
            and node.target.id == "_CANONICAL_TO_BUSINESS_ROLE")
        or (isinstance(node, ast.FunctionDef) and node.name in {
            "_as_bool", "derive_receipt_line_semantics"
        })
    ]
    scope = {"Any": Any}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), "exec"), scope)
    return scope["derive_receipt_line_semantics"]


def test_source_adjustments_remain_financial_and_not_inventory_eligible():
    """Kassa persistence semantics: negative discount and positive stamps never stock."""
    converted = _map([
        {"kind": "product", "raw_label": "Artikel", "line_total": "13.23"},
        {"kind": "adjustment", "raw_label": "Actiekorting", "line_total": "-2.88"},
        {"kind": "adjustment", "raw_label": "Zegels", "line_total": "1.00"},
    ])
    derive = _load_semantics()
    facts = [derive(line) for line in converted["receipt"]["lines"]]
    assert facts == [
        {"line_role": "product", "inventory_eligible": True},
        {"line_role": "financial", "inventory_eligible": False},
        {"line_role": "financial", "inventory_eligible": False},
    ]


def test_unpack_filters_scanner_financial_lines():
    """Guard the existing Kassa -> Uitpakken filter at its actual call site."""
    main = (SOURCE.parents[1] / "backend/app/main.py").read_text(encoding="utf-8")
    start = main.index("def sync_unpack_batch_lines_for_receipt(")
    end = main.index("\\ndef ", start + 1)
    body = main[start:end]
    assert "derive_receipt_line_semantics(" in body
    assert "if not semantics['inventory_eligible']:" in body
    assert "continue" in body[body.index("if not semantics['inventory_eligible']:"):body.index("prior_processed = get_prior_processed_line_fact")]
