"""PR3 cadence: one repeat is enough, and later current purchases improve it.

No inventory mutations in these mocked storage-contract tests.
"""
from unittest.mock import patch

from app.services.historical_household_stock_writer import (
    _sync_historical_purchase_cadences,
)


class _Rows:
    def __init__(self, rows=None, count=0):
        self.rows = rows or []
        self.rowcount = count

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _CadenceOnlyConn:
    def __init__(self, events=()):
        self.events = list(events)
        self.commands = []
        self.upserts = []

    def execute(self, query, values=None):
        sql = str(query)
        self.commands.append((sql, values))
        if "FROM inventory_events" in sql:
            assert sql.lstrip().startswith("SELECT")
            assert "event_type IN ('purchase', 'auto_repurchase')" in sql
            assert values["household_id"] == "home1"
            return _Rows(self.events)
        if "INSERT INTO household_historical_purchase_cadences" in sql:
            self.upserts.append(values)
            return _Rows(count=1)
        if "DELETE FROM household_historical_purchase_cadences" in sql:
            return _Rows(count=0)
        raise AssertionError("Unexpected SQL: " + sql)


def _projection(days, *, group=None):
    members = group or ("ha-1",)
    return {
        "first_current_purchase_date": "2026-11-20",
        "source_fingerprint": "a" * 64,
        "purchase_cadences": {},
        "purchase_days_by_article": {
            member: list(days) for member in members
        },
        "synonym_groups": {
            member: tuple(members) for member in members
        } if len(members) > 1 else {},
    }


def _event(event_id, article, day):
    return {"id": event_id, "household_article_id": article, "purchase_day": day}


def test_two_historical_purchase_dates_persist_without_waiting():
    conn = _CadenceOnlyConn()
    report = _sync_historical_purchase_cadences(
        conn, owner="home1", calculated=_projection(["2026-11-01", "2026-11-02"]),
    )
    assert report["cadences_written"] == 1
    value = conn.upserts[0]
    assert value["interval"] == 1.0
    assert value["day_count"] == 2
    assert value["last_day"] == "2026-11-02"


def test_one_historical_plus_one_current_purchase_is_first_repeat():
    conn = _CadenceOnlyConn([_event("new", "ha-1", "2026-11-21")])
    report = _sync_historical_purchase_cadences(
        conn, owner="home1", calculated=_projection(["2026-11-01"]),
    )
    assert report["cadences_written"] == 1
    record = conn.upserts[0]
    assert record["interval"] == 20.0
    assert record["day_count"] == 2
    assert record["last_day"] == "2026-11-21"
    assert record["fingerprint"] != "a" * 64
    # No inventory, receipt, or manual user setting is written.
    assert not any("INSERT INTO inventory" in sql or "UPDATE inventory" in sql
                   for sql, _ in conn.commands)


def test_third_purchase_updates_mean_even_with_same_day_duplicates():
    conn = _CadenceOnlyConn([
        _event("new1", "ha-1", "2026-11-21"),
        _event("new2", "ha-1", "2026-12-01"),
        _event("duplicate-day", "ha-1", "2026-12-01"),
    ])
    _sync_historical_purchase_cadences(
        conn, owner="home1", calculated=_projection(["2026-11-01"]),
    )
    assert conn.upserts[0]["day_count"] == 3
    assert conn.upserts[0]["interval"] == 15.0


def test_confirmed_synonyms_share_union_of_historical_and_current_dates():
    conn = _CadenceOnlyConn([
        _event("event1", "ha-2", "2026-12-01"),
        _event("event2", "ha-1", "2026-12-01"),
    ])
    _sync_historical_purchase_cadences(
        conn, owner="home1",
        calculated=_projection(["2026-11-01"], group=("ha-1", "ha-2")),
    )
    assert len(conn.upserts) == 2
    assert {row["interval"] for row in conn.upserts} == {30.0}
    assert {row["day_count"] for row in conn.upserts} == {2}
    assert {row["article_id"] for row in conn.upserts} == {"ha-1", "ha-2"}


def test_one_day_with_multiple_receipts_still_has_no_interval():
    conn = _CadenceOnlyConn([
        _event("dup", "ha-1", "2026-11-01"),
    ])
    _sync_historical_purchase_cadences(
        conn, owner="home1", calculated=_projection(["2026-11-01"]),
    )
    assert conn.upserts == []
    assert any("DELETE FROM household_historical_purchase_cadences" in sql
               for sql, _ in conn.commands)


def test_two_current_purchase_days_suffice_even_without_historical_receipts():
    projection = {
        "first_current_purchase_date": "2026-11-20",
        "source_fingerprint": "a" * 64,
        "purchase_days_by_article": {},
        "purchase_cadences": {},
        "synonym_groups": {},
    }
    conn = _CadenceOnlyConn([
        _event("first", "ha-1", "2026-11-21"),
        _event("repeat", "ha-1", "2026-11-28"),
    ])
    with patch(
        "app.services.historical_household_stock_writer.confirmed_household_synonym_group",
        return_value=("ha-1",),
    ) as resolver:
        report = _sync_historical_purchase_cadences(
            conn, owner="home1", calculated=projection,
        )
    resolver.assert_called_once_with(conn, "home1", "ha-1")
    assert report["cadences_written"] == 1
    assert conn.upserts[0]["day_count"] == 2
    assert conn.upserts[0]["interval"] == 7.0


def test_two_current_synonym_variants_have_one_shared_cadence():
    projection = {
        "first_current_purchase_date": "2026-11-20",
        "source_fingerprint": "a" * 64,
        "purchase_days_by_article": {},
        "purchase_cadences": {},
        "synonym_groups": {},
    }
    conn = _CadenceOnlyConn([
        _event("first", "ha-1", "2026-11-21"),
        _event("repeat", "ha-2", "2026-11-30"),
    ])
    with patch(
        "app.services.historical_household_stock_writer.confirmed_household_synonym_group",
        return_value=("ha-1", "ha-2"),
    ):
        _sync_historical_purchase_cadences(
            conn, owner="home1", calculated=projection,
        )
    assert len(conn.upserts) == 2
    assert {row["interval"] for row in conn.upserts} == {9.0}
    assert {row["day_count"] for row in conn.upserts} == {2}
    assert {row["article_id"] for row in conn.upserts} == {"ha-1", "ha-2"}
