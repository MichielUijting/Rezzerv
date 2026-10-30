"""Fail-closed household workflow preference guards (no database mutation)."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.household_workflow_preferences_service import (
    save_household_workflow_preferences,
)
from app.services.receipt_direct_inventory_approval_patch import (
    should_process_approved_receipt_directly_to_inventory,
)


class FakeConnection:
    def __init__(self, *, pending=False, located_stock=False):
        self.pending = pending
        self.located_stock = located_stock
        self.statements = []
        self.parameters = []

    def execute(self, statement, parameters):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        self.parameters.append(dict(parameters))
        if "FROM purchase_import_batches" in sql:
            return SimpleNamespace(first=lambda: (1,) if self.pending else None)
        if "FROM inventory" in sql:
            return SimpleNamespace(first=lambda: (1,) if self.located_stock else None)
        raise AssertionError("Onverwachte schrijfactie of query: " + sql)


def config(*, location="exact", unpacking=True):
    return SimpleNamespace(
        household_id="h1",
        location_tracking_level=location,
        unpacking_enabled=unpacking,
        simple_inventory_enabled=True,
        receipt_processing_enabled=True,
    )


def test_location_downgrade_with_stock_fails_without_mutation():
    conn = FakeConnection(located_stock=True)
    with patch(
        "app.services.household_workflow_preferences_service.resolve_household_product_configuration",
        return_value=config(),
    ):
        with pytest.raises(ValueError, match="actieve voorraad"):
            save_household_workflow_preferences(
                conn,
                household_id="h1",
                location_tracking_level="none",
                unpacking_enabled=False,
            )
    assert not any("UPDATE " in sql or "DELETE " in sql for sql in conn.statements)
    assert all(params["household_id"] == "h1" for params in conn.parameters)


def test_disabling_unpacking_with_global_located_stock_is_also_blocked():
    conn = FakeConnection(located_stock=True)
    with patch(
        "app.services.household_workflow_preferences_service.resolve_household_product_configuration",
        return_value=config(location="global", unpacking=True),
    ):
        with pytest.raises(ValueError, match="actieve voorraad"):
            save_household_workflow_preferences(
                conn,
                household_id="h1",
                location_tracking_level="global",
                unpacking_enabled=False,
            )
    assert not any("UPDATE " in sql or "DELETE " in sql for sql in conn.statements)


def test_open_receipt_blocks_disabling_unpacking():
    conn = FakeConnection(pending=True)
    with patch(
        "app.services.household_workflow_preferences_service.resolve_household_product_configuration",
        return_value=config(location="global", unpacking=True),
    ):
        with pytest.raises(ValueError, match="bonartikelen open"):
            save_household_workflow_preferences(
                conn,
                household_id="h1",
                location_tracking_level="global",
                unpacking_enabled=False,
            )
    assert not any("UPDATE " in sql or "DELETE " in sql for sql in conn.statements)


def test_exact_location_requires_unpacking():
    conn = FakeConnection()
    with patch(
        "app.services.household_workflow_preferences_service.resolve_household_product_configuration",
        return_value=config(),
    ):
        with pytest.raises(ValueError, match="Exacte voorraadlocaties"):
            save_household_workflow_preferences(
                conn,
                household_id="h1",
                location_tracking_level="exact",
                unpacking_enabled=False,
            )
    assert not conn.statements


def test_direct_kassa_inventory_rule_only_for_safe_configuration():
    assert should_process_approved_receipt_directly_to_inventory(
        config(location="none", unpacking=False)
    )
    assert should_process_approved_receipt_directly_to_inventory(
        config(location="global", unpacking=False)
    )
    assert not should_process_approved_receipt_directly_to_inventory(
        config(location="exact", unpacking=True)
    )
    assert not should_process_approved_receipt_directly_to_inventory(
        config(location="none", unpacking=True)
    )
