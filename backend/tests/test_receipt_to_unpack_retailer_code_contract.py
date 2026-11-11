"""Guard against losing retailer article numbers between Kassa and Uitpakken.

This lightweight contract inspects the production synchronization function's
bindings.  An end-to-end database test is still required before Ready.
"""
from __future__ import annotations

import ast
from pathlib import Path


def test_receipt_sync_preserves_retailer_code_in_both_write_paths() -> None:
    module = ast.parse(
        (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    )
    function = next(
        node for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "sync_unpack_batch_lines_for_receipt"
    )
    retailer_code_bindings = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or key.value != "external_article_code":
                continue
            retailer_code_bindings.append(ast.unparse(value))
    assert len(retailer_code_bindings) == 2, retailer_code_bindings
    assert retailer_code_bindings == [
        "line.get('external_article_code')",
        "line.get('external_article_code')",
    ], retailer_code_bindings
