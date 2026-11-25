"""Fail-closed Jumbo scan continuation and household queue isolation."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.jumbo_history_import_service import (
    _queue_completed, begin_jumbo_history, complete_jumbo_history,
)


class Rows:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value

    def scalar_one(self):
        return self.value


class Conn:
    def __init__(self, old=None, statuses=None):
        self.old = old
        self.statuses = statuses or {}
        self.params = []
        self.pending = None
        self.run_id = None

    def execute(self, query, params):
        sql = str(query)
        self.params.append((sql, dict(params)))
        if "retailer_import_queue" in sql:
            assert params["household_id"] == "house-a"
            return Rows([{"id": key, "status": self.statuses[key]}
                         for key in params["queue_ids"] if key in self.statuses])
        if "SELECT pending_from_date,scan_complete" in sql:
            return Rows(self.old)
        if "SELECT run_id FROM" in sql:
            return Rows({"run_id": self.run_id} if self.run_id else None)
        if "INSERT INTO household_jumbo_import_runs" in sql:
            self.run_id = params["run_id"]
            self.pending = params["first"]
            return Rows(None)
        if "SELECT pending_from_date FROM" in sql:
            return Rows(self.pending)
        if "UPDATE household_jumbo_import_runs" in sql:
            return Rows(None)
        raise AssertionError("Unexpected query: " + sql)


class Engine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *_):
        return None


def test_first_import_from_previous_calendar_year_and_household_scoped():
    conn = Conn()
    with patch("app.services.jumbo_history_import_service.latest_retailer_import_dates",
               return_value={"jumbo": None}):
        result = begin_jumbo_history(Engine(conn), "house-a")
    today = date.today()
    assert result["from_date"][:4] in {str(today.year - 1), str(today.year - 2)}
    assert result["from_date"].endswith("-01-01")
    assert result["scan_complete"] is False
    assert all(params.get("household_id") == "house-a" for _, params in conn.params)


def test_partial_history_keeps_oldest_start_even_if_newer_receipt_completed():
    conn = Conn(old={"pending_from_date": date(2025, 1, 1),
                     "scan_complete": False, "queue_ids": []})
    with patch("app.services.jumbo_history_import_service.latest_retailer_import_dates",
               return_value={"jumbo": "2026-10-25"}):
        result = begin_jumbo_history(Engine(conn), "house-a")
    assert result["from_date"] == "2025-01-01"


def test_completed_scan_with_failed_queue_retains_start():
    conn = Conn(old={"pending_from_date": date(2025, 1, 1),
                     "scan_complete": True,
                     "queue_ids": ["00000000-0000-4000-8000-000000000001"]})
    conn.statuses = {"00000000-0000-4000-8000-000000000001": "review_required"}
    with patch("app.services.jumbo_history_import_service.latest_retailer_import_dates",
               return_value={"jumbo": "2026-09-01"}):
        result = begin_jumbo_history(Engine(conn), "house-a")
    assert result["from_date"] == "2025-01-01"


def test_queue_completion_only_for_all_owned_completed_rows():
    ids = ["00000000-0000-4000-8000-000000000001",
           "00000000-0000-4000-8000-000000000002"]
    c = Conn(statuses={ids[0]: "completed"})
    assert _queue_completed(c, "house-a", ids) is False
    c.statuses[ids[1]] = "processing"
    assert _queue_completed(c, "house-a", ids) is False
    c.statuses[ids[1]] = "completed"
    assert _queue_completed(c, "house-a", ids) is True


def test_scan_completion_fails_if_queue_not_in_active_household():
    conn = Conn()
    conn.run_id = "00000000-0000-4000-8000-000000000003"
    with pytest.raises(ValueError, match="Niet alle Jumbo-bonnen"):
        complete_jumbo_history(Engine(conn), "house-a", run_id=conn.run_id,
                               queue_ids=["00000000-0000-4000-8000-000000000001"])


def test_stale_run_cannot_complete_another_attempt():
    conn = Conn()
    conn.run_id = "00000000-0000-4000-8000-000000000003"
    with pytest.raises(ValueError, match="verlopen"):
        complete_jumbo_history(Engine(conn), "house-a",
                               run_id="00000000-0000-4000-8000-000000000004",
                               queue_ids=[])
