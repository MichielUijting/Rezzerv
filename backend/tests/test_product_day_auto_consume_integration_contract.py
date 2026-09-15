from __future__ import annotations

import ast
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _main_tree() -> ast.Module:
    return ast.parse(MAIN_PATH.read_text(encoding="utf-8"))


def test_auto_consume_decision_accepts_and_uses_purchase_date():
    tree = _main_tree()
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "determine_auto_consume_decision"
    )
    argument_names = [argument.arg for argument in function.args.args]
    assert "purchase_date" in argument_names

    product_day_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "compute_product_day_auto_deduction"
    ]
    assert len(product_day_calls) == 1
    keyword_names = {keyword.arg for keyword in product_day_calls[0].keywords}
    assert {
        "household_id",
        "household_article_id",
        "purchase_date",
        "mode",
        "pre_purchase_total",
        "purchased_quantity",
    }.issubset(keyword_names)


def test_store_import_processing_passes_receipt_purchase_date_into_auto_consume_decision():
    tree = _main_tree()
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "determine_auto_consume_decision"
    ]
    assert calls, "store-import verwerking moet determine_auto_consume_decision aanroepen"
    assert any(
        any(
            keyword.arg == "purchase_date"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "purchase_date"
            for keyword in call.keywords
        )
        for call in calls
    )
