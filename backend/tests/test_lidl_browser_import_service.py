"""Targeted fail-closed Lidl onboarding import-run tests (no production DB)."""
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.lidl_browser_import_service import (
    begin_lidl_browser_import, complete_lidl_browser_import,
)


class Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class Conn:
    def __init__(self):
        self.state = {}
        self.queues = set()
        self.statuses = {}
        self.statements = []

    def execute(self, query, params):
        sql = " ".join(str(query).split()).upper()
        self.statements.append((sql, dict(params)))
        owner = params.get("household_id") or params.get("id")
        assert owner, "Unscoped SQL is forbidden"
        if "FROM HOUSEHOLD_LIDL_IMPORT_WINDOWS" in sql:
            return Result({"from_date": None, "to_date": None, "last_imported_date": None})
        if sql.startswith("INSERT INTO HOUSEHOLD_SETTINGS"):
            assert "ON CONFLICT (HOUSEHOLD_ID,SETTING_KEY)" in sql
            self.state[owner] = json.loads(params["value"])
            return Result(None)
        if sql.startswith("SELECT SETTING_VALUE FROM HOUSEHOLD_SETTINGS"):
            assert "FOR UPDATE" in sql
            return Result(json.dumps(self.state[owner]) if owner in self.state else None)
        if "FROM RETAILER_IMPORT_QUEUE" in sql:
            assert "HOUSEHOLD_ID=:HOUSEHOLD_ID" in sql and "PROVIDER='LIDL'" in sql
            return Result([{"id": item, "status": self.statuses[item]}
                           for item in params["queue_ids"] if item in self.queues
                           and item in self.statuses])
        if sql.startswith("UPDATE HOUSEHOLD_SETTINGS"):
            assert "HOUSEHOLD_ID=:HOUSEHOLD_ID" in sql
            self.state[owner] = json.loads(params["value"])
            return Result(None)
        raise AssertionError("Unexpected SQL: " + sql)


class Engine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return self

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *_):
        return None


def _begin(conn, owner="house-a"):
    with patch("app.services.lidl_browser_import_service.get_window", return_value={
        "from_date": "2025-01-01", "to_date": "2026-11-25",
    }):
        return begin_lidl_browser_import(Engine(conn), owner)


def _complete(conn, run, ids=None, owner="house-a"):
    return complete_lidl_browser_import(
        Engine(conn), owner, run_id=run["run_id"], queue_ids=ids or [],
        from_date=date(2025, 1, 1), to_date=date(2026, 11, 25),
    )


def test_confirmed_empty_scan_has_durable_household_run():
    conn = Conn()
    run = _begin(conn)
    assert run["scan_complete"] is False
    result = _complete(conn, run)
    assert result["scan_complete"] is True
    assert result["staged_receipts"] == 0
    assert conn.state["house-a"]["queue_ids"] == []
    assert conn.state["house-a"]["scan_complete"] is True


def test_stale_run_cannot_complete_after_retry():
    conn = Conn()
    first = _begin(conn)
    later = _begin(conn)
    assert first["run_id"] != later["run_id"]
    with pytest.raises(ValueError, match="verlopen"):
        _complete(conn, first)
    _complete(conn, later)
    with pytest.raises(ValueError, match="status"):
        _complete(conn, later)


def test_wrong_household_wrong_queue_and_wrong_period_blocked():
    conn = Conn()
    run = _begin(conn)
    with pytest.raises(ValueError, match="verlopen"):
        _complete(conn, run, owner="other-house")
    missing = "00000000-0000-4000-8000-000000000001"
    with pytest.raises(ValueError, match="Niet alle Lidl"):
        _complete(conn, run, [missing])
    with pytest.raises(ValueError, match="periode"):
        complete_lidl_browser_import(Engine(conn), "house-a", run_id=run["run_id"],
                                     queue_ids=[], from_date=date(2026, 1, 1),
                                     to_date=date(2026, 11, 25))


def test_acknowledged_queue_not_equal_processed_queue():
    conn = Conn()
    run = _begin(conn)
    q = "00000000-0000-4000-8000-000000000001"
    conn.queues.add(q)
    conn.statuses[q] = "pending"
    out = _complete(conn, run, [q])
    assert out["staged_receipts"] == 1
    assert conn.state["house-a"]["queue_ids"] == [q]
    assert all(params.get("household_id", params.get("id")) == "house-a"
               for _, params in conn.statements)
