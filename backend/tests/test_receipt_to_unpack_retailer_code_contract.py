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


def test_article_overview_reads_gtin_only_from_canonical_barcode_column() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "services"
              / "external_unlinked_articles_service.py").read_text(encoding="utf-8")
    # The original placeholder used a retailer product code as GTIN. The
    # overview must overwrite it with the independent receipt barcode.
    assert "rtl.barcode AS source_gtin" in source
    assert 'item["gtin"] = str(row["source_gtin"] or "")' in source
    assert 'item["gtin"] = ""' in source


def test_catalog_projection_never_passes_external_article_code_as_gtin() -> None:
    source = (Path(__file__).resolve().parents[1] / "app" / "services"
              / "external_article_ui_projection.py").read_text(encoding="utf-8")
    assert "            external_article_code,\n            *candidate_gtin_values," not in source
    assert 'candidate.get("external_source_product_code")' not in source
    assert 'candidate.get("source_product_code")' not in source
