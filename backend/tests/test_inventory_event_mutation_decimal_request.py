"""Regression for exact non-financial inventory adjustment quantities.

Importing app.main initializes the full runtime schema, so this test executes only the
actual InventoryEventMutationRequest class definition from main.py. That keeps the
request-contract regression fast while still testing the production validator source.
"""

import ast
from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, field_validator


MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"


def _inventory_event_mutation_request_class():
    module = ast.parse(MAIN_PATH.read_text(encoding="utf-8"), filename=str(MAIN_PATH))
    class_node = next(
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == "InventoryEventMutationRequest"
    )
    isolated_module = ast.fix_missing_locations(ast.Module(body=[class_node], type_ignores=[]))
    namespace = {
        "BaseModel": BaseModel,
        "field_validator": field_validator,
        "Decimal": Decimal,
        "Optional": Optional,
        "normalize_household_article_name": lambda value: " ".join(str(value or "").strip().split()),
    }
    exec(compile(isolated_module, str(MAIN_PATH), "exec"), namespace)
    return namespace["InventoryEventMutationRequest"]


def test_adjustment_request_preserves_exact_decimal_quantity():
    request_class = _inventory_event_mutation_request_class()

    payload = request_class(quantity="1.234567", event_type="adjustment")

    assert isinstance(payload.quantity, Decimal)
    assert payload.quantity == Decimal("1.234567")


def test_integral_purchase_quantity_remains_exact_decimal_for_route_validation():
    request_class = _inventory_event_mutation_request_class()

    payload = request_class(quantity="2", event_type="purchase")

    assert isinstance(payload.quantity, Decimal)
    assert payload.quantity == Decimal("2")
