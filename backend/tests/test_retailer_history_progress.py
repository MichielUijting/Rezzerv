"""PR5: read-only household import-history projection contracts.

No alternate database is started; the canonical PostgreSQL full-stack gates
exercise the actual runtime. Fakes here verify query scope and status semantics.
"""
from datetime import date, datetime

import pytest

from app.services.retailer_history_progress import load_retailer_history_progress


class _Result:
    def __init__(self, *, rows=None, scalar=None):
        self.rows = list(rows or [])
        self.scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar_one_or_none(self):
        return self.scalar


class _ReadOnlyConnection:
    def __init__(self, *, household, cutoff, receipts, queue, enabled=True, state="normal"):
        self.household = household
        self.cutoff = cutoff
        self.receipts = receipts
        self.queue = queue
        self.enabled = enabled
        self.state = state
        self.queries = []

    def execute(self, statement, params=None):
        sql = str(statement)
        arguments = dict(params or {})
        assert sql.lstrip().startswith("SELECT"), "Progress must never mutate data"
        self.queries.append((sql, arguments))

        if "FROM household_receipt_history_cutovers" in sql:
            assert arguments["household_id"] == self.household
            return _Result(scalar=self.cutoff)

        if "FROM raw_receipts rr" in sql:
            assert arguments["household_id"] == self.household
            assert "rt.household_id = :household_id" in sql
            assert "rr.household_id = :household_id" in sql
            assert "rt.deleted_at IS NULL" in sql
            assert "rr.deleted_at IS NULL" in sql
            assert "rr.duplicate_of_raw_receipt_id IS NULL" in sql
            assert "rt.purchase_at < :cutoff_datetime" in sql
            assert "rt.purchase_at_source" in sql
            assert "rt.approved_at IS NULL" in sql
            assert "AS kassa_inbox_receipts" in sql
            assert "CAST(rt.purchase_at AS DATE) >= :cutoff_date" in sql
            assert arguments["cutoff_date"] == self.cutoff
            assert "'import_default'" in sql
            assert "('parsed', 'approved')" in sql
            assert arguments["ah_source"] == self.household + "-retailer-ah"
            assert arguments["lidl_source"] == self.household + "-retailer-lidl"
            assert arguments["jumbo_source"] == self.household + "-retailer-jumbo"
            assert arguments["cutover_enabled"] == int(self.cutoff is not None)
            assert arguments["cutoff_datetime"] == (
                datetime.combine(self.cutoff, datetime.min.time()) if self.cutoff else None
            )
            return _Result(rows=self.receipts)

        if "FROM retailer_import_queue" in sql:
            assert arguments["household_id"] == self.household
            assert "provider IN ('lidl', 'jumbo')" in sql
            assert "GROUP BY provider, status" in sql
            return _Result(rows=self.queue)

        if "FROM maintenance_control" in sql:
            return _Result(scalar=self.state)

        if "FROM platform_feature_flags" in sql:
            assert arguments["flag_key"] == "retailer_auto_import"
            return _Result(rows=[{"enabled": self.enabled}])

        raise AssertionError("Unexpected read query in import progress service")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class _ReadOnlyEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


def _read(*, household="home-a", cutoff=date(2026, 11, 21),
          receipts=None, queue=None, enabled=True, state="normal"):
    db = _ReadOnlyConnection(
        household=household, cutoff=cutoff, receipts=receipts or [],
        queue=queue or [], enabled=enabled, state=state,
    )
    return load_retailer_history_progress(
        _ReadOnlyEngine(db), household_id=household,
    ), db


def _store(result, code):
    return next(row for row in result["providers"] if row["code"] == code)


def test_uses_server_household_original_date_and_durable_queue_only():
    result, db = _read(
        receipts=[
            {"source_id": "home-a-retailer-ah", "saved_receipts": 3,
             "kassa_receipts": 3, "kassa_inbox_receipts": 1, "historical_receipts": 1, "review_receipts": 1},
            {"source_id": "home-a-retailer-jumbo", "saved_receipts": 1,
             "kassa_receipts": 1, "historical_receipts": 0, "review_receipts": 1},
        ],
        queue=[
            {"provider": "lidl", "status": "pending", "item_count": 2},
            {"provider": "lidl", "status": "processing", "item_count": 1},
            {"provider": "lidl", "status": "completed", "item_count": 3},
            {"provider": "jumbo", "status": "review_required", "item_count": 1},
        ],
    )
    assert result["history_cutover_enabled"] is True
    assert result["coverage"] == "persisted_retailer_receipts_and_queue_only"
    assert result["complete_retailer_history_known"] is False
    assert result["auto_import_paused"] is False
    assert [row["code"] for row in result["providers"]] == ["ah", "lidl", "jumbo"]
    assert _store(result, "ah")["kassa_receipts"] == 3
    assert _store(result, "ah")["kassa_inbox_receipts"] == 1
    assert _store(result, "ah")["historical_receipts"] == 1
    assert _store(result, "ah")["review_receipts"] == 1
    assert _store(result, "lidl")["queue_pending"] == 2
    assert _store(result, "lidl")["queue_processing"] == 1
    assert _store(result, "lidl")["queue_completed"] == 3
    assert _store(result, "lidl")["kassa_receipts"] == 0
    assert _store(result, "jumbo")["queue_review_required"] == 1
    assert len(db.queries) == 5


def test_legacy_household_never_gets_a_fabricated_historical_zero():
    result, _ = _read(household="home-b", cutoff=None, receipts=[
        {"source_id": "home-b-retailer-ah", "saved_receipts": 2,
         "kassa_receipts": 2, "historical_receipts": 2, "review_receipts": 0},
    ])
    assert result["history_cutover_enabled"] is False
    assert _store(result, "ah")["kassa_receipts"] == 2
    assert _store(result, "ah")["historical_receipts"] is None
    assert _store(result, "ah")["review_receipts"] is None


@pytest.mark.parametrize("enabled,state", [
    (False, "normal"), (True, "draining"), (True, None),
])
def test_maintenance_or_platform_pause_does_not_change_queue(enabled, state):
    result, db = _read(
        enabled=enabled, state=state,
        queue=[{"provider": "lidl", "status": "pending", "item_count": 1}],
    )
    assert result["auto_import_paused"] is True
    assert _store(result, "lidl")["queue_pending"] == 1
    assert all(sql.strip().startswith("SELECT") for sql, _ in db.queries)


def test_invalid_household_is_refused_before_any_db_access():
    with pytest.raises(ValueError, match="huishouden"):
        load_retailer_history_progress(_ReadOnlyEngine(None), household_id="  ")
