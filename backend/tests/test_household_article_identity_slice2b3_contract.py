"""Slice 2B3 contract guard for canonical household-article identity.

This test deliberately inspects the production resolver source. Slice 2B3 is a
removal/refactor contract: legacy live:: generation and name-based identity
fallbacks must not silently return in app/main.py.
"""

from __future__ import annotations

import ast
from pathlib import Path


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


def function_source(source: str, tree: ast.AST, name: str) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(source, node)
            assert segment, f"Geen bronsegment gevonden voor {name}"
            return segment
    raise AssertionError(f"Functie ontbreekt: {name}")


def main() -> int:
    source = MAIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "build_live_article_option_id" not in function_names
    assert "build_live_article_option_id(" not in source

    selection = function_source(source, tree, "resolve_household_article_selection_to_id")
    assert "get_household_article_option_by_id" in selection
    assert "resolve_review_article_option" not in selection
    assert "get_household_article_row_by_name" not in selection
    assert "ensure_household_article" not in selection
    assert "startswith('live::')" in selection

    review = function_source(source, tree, "resolve_review_article_option")
    assert "get_household_article_option_by_id" in review
    assert "MOCK_ARTICLE" not in review
    assert "inventory" not in review.lower()
    assert "get_household_article_row_by_name" not in review
    assert "ensure_household_article" not in review
    assert "startswith('live::')" in review

    processing = function_source(source, tree, "resolve_processing_article")
    assert "get_household_article_option_by_id" in processing
    assert "find_generic_existing_article_match" not in processing
    assert "get_household_article_row_by_name" not in processing
    assert "ensure_household_article" not in processing
    assert "startswith('live::')" in processing

    generic = function_source(source, tree, "find_generic_existing_article_match")
    assert "FROM household_articles" in generic
    assert "inventory" not in generic.lower()
    assert "Suggestion-only" in generic

    options = function_source(source, tree, "get_store_review_article_options")
    assert "household_id = :household_id" in options
    assert "MOCK_ARTICLE" not in options
    assert "FROM inventory" not in options
    assert '"household_article_id": article_id' in options

    print("PASS resolver accepts canonical household article IDs only")
    print("PASS name/mock/inventory identity fallbacks removed")
    print("PASS generic name matching is suggestion-only")
    print("PASS live ID generator removed from production source")
    print("HOUSEHOLD_ARTICLE_IDENTITY_SLICE2B3_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
