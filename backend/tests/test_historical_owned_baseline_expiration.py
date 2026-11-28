"""Historical baseline invalidation is transaction-bound and fail-closed.

A prior safe stock projection must not survive invalidated source lines.
Actual PostgreSQL chain proof remains required by the release gate.
"""
from datetime import date
from unittest.mock import patch

import pytest

from app.services import historical_household_stock_writer as writer


BASELINE = {
    "inventory_id": "inv-1",
    "inventory_event_id": "event-1",
    "quantity": 3,
    "source_fingerprint": "a" * 64,
}


class Result:
    def __init__(self, *, rows=None, count=0):
        self.rows = list(rows or [])
        self.rowcount = count

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class Conn:
    def __init__(self, *, event_source="historical_auto_stock", failed_delete=None):
        self.events = []
        self.event_source = event_source
        self.failed_delete = failed_delete

    def execute(self, query, params):
        sql = str(query)
        self.events.append((sql, params))
        assert params["household_id"] == "home-1"
        if "FROM inventory_events" in sql:
            return Result(rows=[{
                "id": "event-1", "event_type": "baseline",
                "source": self.event_source, "quantity": 3,
                "effective_at": "2026-11-20T00:00:00+00:00",
            }])
        if sql.lstrip().startswith("DELETE FROM"):
            assert params["article_id"] == "ha-1"
            return Result(count=0 if self.failed_delete in sql else 1)
        raise AssertionError("Unexpected SQL: " + sql)


def _expire(conn, *, has_manual=False, has_article=True, stock=True):
    with patch.object(
        writer, "_lock_owned_article",
        return_value={"id": "ha-1", "naam": "Product"} if has_article else None,
    ), patch.object(
        writer, "_block_existing_business_history", return_value=has_manual,
    ), patch.object(
        writer, "_existing_baseline_stock",
        return_value={"id": "inv-1", "aantal": 3} if stock else None,
    ):
        return writer._expire_unreferenced_owned_baseline(
            conn, owner="home-1", article_id="ha-1",
            baseline=BASELINE, cutoff=date(2026, 11, 20),
        )


def test_expiration_removes_only_proven_owned_stock_event_and_baseline():
    conn = Conn()
    assert _expire(conn) is True
    deletions = [(sql, params) for sql, params in conn.events if sql.lstrip().startswith("DELETE")]
    assert len(deletions) == 3
    assert "DELETE FROM inventory\n" in deletions[0][0]
    assert "DELETE FROM inventory_events" in deletions[1][0]
    assert "DELETE FROM household_historical_auto_stock_baselines" in deletions[2][0]
    assert all(params["article_id"] == "ha-1" for _, params in deletions)
    assert all("DELETE FROM raw_receipts" not in sql for sql, _ in deletions)


@pytest.mark.parametrize("has_manual,has_article", [(True, True), (False, False)])
def test_custom_history_or_inactive_article_preserves_stock(has_manual, has_article):
    conn = Conn()
    assert _expire(conn, has_manual=has_manual, has_article=has_article) is False
    assert not conn.events


def test_changed_baseline_event_is_not_deleted():
    conn = Conn(event_source="manual")
    with pytest.raises(ValueError, match="niet meer intact"):
        _expire(conn)
    assert all("DELETE" not in sql for sql, _ in conn.events)


def test_changed_inventory_blocks_transaction_and_rolls_back_in_caller():
    conn = Conn(failed_delete="DELETE FROM inventory\n")
    with pytest.raises(ValueError, match="mag niet"):
        _expire(conn)
    assert not any("DELETE FROM inventory_events" in sql for sql, _ in conn.events)


def test_zero_quantity_baseline_has_no_stock_row_to_remove():
    conn = Conn()
    zero = {**BASELINE, "inventory_id": None, "quantity": 0}
    with patch.object(writer, "_lock_owned_article", return_value={"id": "ha-1"}), \
         patch.object(writer, "_block_existing_business_history", return_value=False), \
         patch.object(writer, "_existing_baseline_stock", return_value=None):
        # Mocked event's saved quantity must match; no destructive SQL follows.
        with pytest.raises(ValueError, match="niet meer intact"):
            writer._expire_unreferenced_owned_baseline(
                conn, owner="home-1", article_id="ha-1",
                baseline=zero, cutoff=date(2026, 11, 20),
            )
    assert all("DELETE" not in sql for sql, _ in conn.events)
