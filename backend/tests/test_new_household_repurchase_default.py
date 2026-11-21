"""New-household default never rewrites existing preferences or stock history."""
import pytest

from app.services.household_onboarding_service import (
    ensure_new_household_repurchase_default,
    NEW_HOUSEHOLD_REPURCHASE_MODE,
)


class _Result:
    def __init__(self, value=None, rowcount=0):
        self.value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.value


class _Conn:
    def __init__(self, existing_table=None, explicit=False):
        self.existing_table = existing_table
        self.explicit = explicit
        self.commands = []

    def execute(self, stmt, params=None):
        statement = str(stmt)
        self.commands.append((statement, params))
        if statement.strip().startswith("SELECT 1"):
            return _Result(value=1 if self.existing_table in statement else None)
        if "INSERT INTO household_settings" in statement:
            assert params["mode"] == "consume_all_existing_before_purchase"
            assert "ON CONFLICT" in statement
            assert "DO NOTHING" in statement
            return _Result(rowcount=0 if self.explicit else 1)
        raise AssertionError("Unexpected SQL: " + statement)


def test_fresh_household_defaults_to_full_old_stock_replacement():
    assert NEW_HOUSEHOLD_REPURCHASE_MODE == "consume_all_existing_before_purchase"
    conn = _Conn()
    assert ensure_new_household_repurchase_default(conn, "home1") is True
    writes = [(sql, args) for sql, args in conn.commands
              if "INSERT INTO household_settings" in sql]
    assert len(writes) == 1
    assert writes[0][1]["household_id"] == "home1"


def test_explicit_household_choice_remains_untouched():
    conn = _Conn(explicit=True)
    assert ensure_new_household_repurchase_default(conn, "home1") is False
    assert sum("INSERT INTO household_settings" in sql for sql, _ in conn.commands) == 1


@pytest.mark.parametrize("table", [
    "raw_receipts", "receipt_tables", "purchase_import_batches",
    "inventory", "inventory_events",
])
def test_old_receipt_or_inventory_blocks_default_seeding(table):
    conn = _Conn(existing_table=table)
    assert ensure_new_household_repurchase_default(conn, "old-home") is False
    assert all("INSERT INTO household_settings" not in sql for sql, _ in conn.commands)


@pytest.mark.parametrize("owner", ["", "0", None])
def test_system_or_missing_household_never_gets_initial_default(owner):
    conn = _Conn()
    with pytest.raises(ValueError):
        ensure_new_household_repurchase_default(conn, owner)
    assert conn.commands == []
