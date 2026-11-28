"""Existing Lidl historical names are normalized without losing receipt facts."""
from __future__ import annotations

import pytest

from app.services.historical_lidl_name_backfill import normalize_stored_lidl_purchase_names


class _Result:
    def __init__(self, count):
        self.rowcount = count


class _RecordingConn:
    def __init__(self, count=1):
        self.count = count
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), dict(params)))
        return _Result(self.count)


def _line(label, *, store="lidl", corrected=None):
    return {
        "source_type": "retailer_api", "source_provider": store,
        "raw_label": label, "corrected_raw_label": corrected,
        "receipt_table_id": "receipt-1", "line_id": label,
    }


def test_existing_price_and_vat_suffixes_use_one_derived_identity():
    conn = _RecordingConn()
    labels = [
        "Verse halfvolle melk 0,88 B",
        "Verse halfvolle melk 0,99 C",
        "Verse halfvolle melk 2 x 0,99 1,98 B",
    ]
    count = normalize_stored_lidl_purchase_names(
        conn, household_id="home-1", rows=[_line(label) for label in labels],
    )
    assert count == 3
    assert [params["normalized_name"] for _, params in conn.calls] == [
        "Verse halfvolle melk",
        "Verse halfvolle melk",
        "Verse halfvolle melk",
    ]
    assert [params["raw_label"] for _, params in conn.calls] == labels
    assert all(params["household_id"] == "home-1" for _, params in conn.calls)
    assert all("corrected_raw_label IS NULL" in sql for sql, _ in conn.calls)
    assert all("rr.household_id = rt.household_id" in sql for sql, _ in conn.calls)
    assert all("source_path = 'lidl'" in sql for sql, _ in conn.calls)
    assert all("SET corrected_raw_label =" in sql for sql, _ in conn.calls)
    assert all("SET raw_label" not in sql and "DELETE" not in sql for sql, _ in conn.calls)


def test_user_corrections_and_other_retailers_never_change():
    conn = _RecordingConn()
    lines = [
        _line("Melk 0,88 B", corrected="Melk door gebruiker"),
        _line("Melk 0,88 B", corrected="Melk 0,88 B"),
        _line("Melk 0,88 B", store="ah"),
        _line("Rundergehakt 12%"),
        _line("Lasagnebladen 500g"),
        _line("Melk onbekende prijs B"),
    ]
    assert normalize_stored_lidl_purchase_names(
        conn, household_id="home-1", rows=lines,
    ) == 0
    assert conn.calls == []


def test_idempotent_guard_returns_zero_when_correction_already_saved():
    conn = _RecordingConn(count=0)
    assert normalize_stored_lidl_purchase_names(
        conn, household_id="home-1",
        rows=[_line("Verse halfvolle melk 0,88 B")],
    ) == 0
    assert len(conn.calls) == 1


@pytest.mark.parametrize("owner", ["", "0", None])
def test_unknown_or_system_household_is_rejected(owner):
    with pytest.raises(ValueError, match="regulier huishouden"):
        normalize_stored_lidl_purchase_names(
            _RecordingConn(), household_id=owner,
            rows=[_line("Verse halfvolle melk 0,88 B")],
        )
