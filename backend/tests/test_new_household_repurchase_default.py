"""New-household default never rewrites existing preferences or stock history."""
import pytest

from app.services.household_onboarding_service import (
    ensure_new_household_repurchase_default,
    ensure_store_onboarding_prediction_defaults_if_missing,
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
            return _Result(value=1 if self.existing_table and self.existing_table in statement else None)
        if "INSERT INTO household_settings" in statement:
            assert "ON CONFLICT" in statement
            assert "DO NOTHING" in statement
            if "mode" in params:
                assert params["mode"] == "consume_all_existing_before_purchase"
                return _Result(rowcount=0 if self.explicit else 1)
            assert (params["setting_key"], params["setting_value"]) in {
                ("almost_out_prediction_enabled", "true"),
                ("almost_out_prediction_days", "30"),
            }
            return _Result(rowcount=0 if self.explicit else 1)
        raise AssertionError("Unexpected SQL: " + statement)


def test_fresh_household_defaults_to_full_old_stock_replacement():
    assert NEW_HOUSEHOLD_REPURCHASE_MODE == "consume_all_existing_before_purchase"
    conn = _Conn()
    assert ensure_new_household_repurchase_default(conn, "home1") is True
    writes = [(sql, args) for sql, args in conn.commands
              if "INSERT INTO household_settings" in sql]
    assert len(writes) == 3
    assert all(args["household_id"] == "home1" for _, args in writes)


def test_explicit_household_choice_remains_untouched():
    conn = _Conn(explicit=True)
    assert ensure_new_household_repurchase_default(conn, "home1") is False
    assert sum("INSERT INTO household_settings" in sql for sql, _ in conn.commands) == 3


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


def test_new_household_prediction_defaults_are_insert_only():
    conn = _Conn()
    ensure_new_household_repurchase_default(conn, "home1")
    writes = [(sql, args) for sql, args in conn.commands
              if "INSERT INTO household_settings" in sql]
    predictions = [(sql, args) for sql, args in writes if "setting_key" in args]
    assert len(predictions) == 2
    assert all("ON CONFLICT (household_id, setting_key) DO NOTHING" in sql
               for sql, _ in predictions)
    assert {args["setting_key"]: args["setting_value"] for _, args in predictions} == {
        "almost_out_prediction_enabled": "true",
        "almost_out_prediction_days": "30",
    }


class _ForecastConn:
    def __init__(self, *, store_onboarding=True, settings=None):
        self.store_onboarding = store_onboarding
        self.settings = dict(settings or {})
        self.commands = []

    def execute(self, stmt, args=None):
        sql = " ".join(str(stmt).split())
        self.commands.append((sql, args))
        if sql.startswith("SELECT 1 FROM household_settings"):
            return _Result(value=1 if self.store_onboarding else None)
        if sql.startswith("INSERT INTO household_settings"):
            assert "ON CONFLICT (household_id, setting_key) DO NOTHING" in sql
            key = args["setting_key"]
            if key in self.settings:
                return _Result(rowcount=0)
            self.settings[key] = args["setting_value"]
            return _Result(rowcount=1)
        raise AssertionError("Unexpected SQL: " + sql)


def test_existing_store_onboarding_gets_missing_prediction_only():
    conn = _ForecastConn(settings={"almost_out_prediction_days": "100"})
    assert ensure_store_onboarding_prediction_defaults_if_missing(conn, "house-1") == 1
    assert conn.settings == {
        "almost_out_prediction_days": "100",
        "almost_out_prediction_enabled": "true",
    }
    assert ensure_store_onboarding_prediction_defaults_if_missing(conn, "house-1") == 0


def test_deliberately_disabled_forecast_stays_off_during_history_refresh():
    conn = _ForecastConn(settings={
        "almost_out_prediction_enabled": "false",
        "almost_out_prediction_days": "100",
    })
    assert ensure_store_onboarding_prediction_defaults_if_missing(conn, "house-1") == 0
    assert conn.settings["almost_out_prediction_enabled"] == "false"


def test_legacy_households_cannot_get_auto_forecast_defaults():
    conn = _ForecastConn(store_onboarding=False)
    assert ensure_store_onboarding_prediction_defaults_if_missing(conn, "old-house") == 0
    assert conn.settings == {}
