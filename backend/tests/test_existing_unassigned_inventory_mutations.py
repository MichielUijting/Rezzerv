"""Regression: legacy locationless stock remains adjustable when Waar Inhuis is enabled.

The exception is deliberately limited to mutations referencing an existing,
household-scoped inventory row. New inventory and arbitrary locationless
events must still be rejected by the normal location authority.
"""
import ast
from pathlib import Path

import pytest
from fastapi import HTTPException


def _location_guard():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "require_resolved_location"
    )
    function.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    ns = {"HTTPException": HTTPException}
    exec(compile(module, "<inventory-location-regression>", "exec"), ns)
    return ns["require_resolved_location"], source


def test_existing_unassigned_inventory_row_can_keep_its_null_location():
    guard, _ = _location_guard()
    value = {"location_id": None, "space_id": None, "sublocation_id": None, "location_label": ""}
    assert guard(value, allow_existing_unassigned=True) == value


def test_new_stock_cannot_bypass_location_requirement():
    guard, _ = _location_guard()
    with pytest.raises(HTTPException) as exc:
        guard({"location_id": None, "space_id": None, "sublocation_id": None})
    assert exc.value.status_code == 400


def test_exemption_is_only_passed_for_existing_inventory_row_mutations():
    _, source = _location_guard()
    endpoint = source.split('@app.post("/api/inventory-events")', 1)[1].split(
        '@app.post("/api/inventory-transfers")', 1
    )[0]
    assert "existing_inventory_without_location = not inventory_row.get('space_id')" in endpoint
    assert "existing_inventory_without_location = False" in endpoint
    assert endpoint.count("allow_existing_unassigned=existing_inventory_without_location") == 2
