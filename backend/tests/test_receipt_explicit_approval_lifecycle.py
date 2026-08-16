from __future__ import annotations

from sqlalchemy import create_engine, text

from app.services.receipt_lifecycle_foundation_service import (
    ensure_receipt_lifecycle_foundation_schema,
    reconcile_explicit_receipt_approvals,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE raw_receipts (
                id TEXT PRIMARY KEY,
                household_id TEXT,
                sha256_hash TEXT,
                deleted_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT NOT NULL,
                household_id TEXT NOT NULL,
                parse_status TEXT,
                approved_at TEXT,
                reviewed_at TEXT,
                approved_by_user_email TEXT,
                totals_overridden INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT,
                updated_at TEXT,
                logical_receipt_key TEXT,
                workflow_state TEXT NOT NULL DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                logical_line_key TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT,
                quantity REAL
            )
        """))
    return engine


def _insert_receipt(
    conn,
    *,
    receipt_id: str,
    parse_status: str,
    approved_at: str | None,
    workflow_state: str = "active",
    deleted_at: str | None = None,
    raw_deleted_at: str | None = None,
    totals_overridden: int = 0,
):
    raw_id = f"raw-{receipt_id}"
    conn.execute(
        text("INSERT INTO raw_receipts (id, household_id, sha256_hash, deleted_at) VALUES (:id, '1', :sha, :deleted_at)"),
        {"id": raw_id, "sha": f"sha-{receipt_id}", "deleted_at": raw_deleted_at},
    )
    conn.execute(
        text("""
            INSERT INTO receipt_tables (
                id, raw_receipt_id, household_id, parse_status, approved_at,
                reviewed_at, approved_by_user_email, totals_overridden,
                deleted_at, updated_at, logical_receipt_key, workflow_state
            ) VALUES (
                :id, :raw_id, '1', :parse_status, :approved_at,
                :approved_at, 'po@example.test', :totals_overridden,
                :deleted_at, CURRENT_TIMESTAMP, :logical_key, :workflow_state
            )
        """),
        {
            "id": receipt_id,
            "raw_id": raw_id,
            "parse_status": parse_status,
            "approved_at": approved_at,
            "totals_overridden": totals_overridden,
            "deleted_at": deleted_at,
            "logical_key": f"logical-{receipt_id}",
            "workflow_state": workflow_state,
        },
    )
    return raw_id


def _row(conn, receipt_id: str):
    return conn.execute(
        text("SELECT parse_status, approved_at, workflow_state, deleted_at FROM receipt_tables WHERE id = :id"),
        {"id": receipt_id},
    ).mappings().one()


def test_startup_reconciliation_preserves_user_approval_and_restores_parse_status():
    engine = _engine()
    with engine.begin() as conn:
        _insert_receipt(
            conn,
            receipt_id="ah-app-1",
            parse_status="review_needed",
            approved_at="2026-08-13 14:20:06",
        )
        result = ensure_receipt_lifecycle_foundation_schema(conn)
        row = _row(conn, "ah-app-1")

    assert result["reconciled_explicit_approvals"] == 1
    assert row["parse_status"] == "approved"
    assert row["approved_at"] == "2026-08-13 14:20:06"
    assert row["workflow_state"] == "active"


def test_totals_override_restores_approved_override_without_clearing_approval():
    engine = _engine()
    with engine.begin() as conn:
        _insert_receipt(
            conn,
            receipt_id="override",
            parse_status="review_needed",
            approved_at="2026-08-15 06:21:05",
            totals_overridden=1,
        )
        reconcile_explicit_receipt_approvals(conn)
        row = _row(conn, "override")

    assert row["parse_status"] == "approved_override"
    assert row["approved_at"] == "2026-08-15 06:21:05"
    assert row["workflow_state"] == "active"


def test_background_parse_status_update_cannot_downgrade_explicit_approval():
    engine = _engine()
    with engine.begin() as conn:
        _insert_receipt(
            conn,
            receipt_id="protected",
            parse_status="approved",
            approved_at="2026-08-15 06:20:02",
        )
        ensure_receipt_lifecycle_foundation_schema(conn)
        conn.execute(
            text("UPDATE receipt_tables SET parse_status = 'review_needed', updated_at = CURRENT_TIMESTAMP WHERE id = 'protected'")
        )
        row = _row(conn, "protected")

    assert row["parse_status"] == "approved"
    assert row["approved_at"] == "2026-08-15 06:20:02"
    assert row["workflow_state"] == "active"


def test_returned_to_kassa_receipt_without_approval_is_not_reapproved_by_trigger():
    engine = _engine()
    with engine.begin() as conn:
        _insert_receipt(
            conn,
            receipt_id="returned",
            parse_status="approved",
            approved_at=None,
            workflow_state="returned_to_kassa",
        )
        ensure_receipt_lifecycle_foundation_schema(conn)
        conn.execute(
            text("UPDATE receipt_tables SET parse_status = 'review_needed', updated_at = CURRENT_TIMESTAMP WHERE id = 'returned'")
        )
        row = _row(conn, "returned")

    assert row["parse_status"] == "review_needed"
    assert row["approved_at"] is None
    assert row["workflow_state"] == "returned_to_kassa"


def test_deleted_archived_or_removed_receipts_are_not_reactivated():
    engine = _engine()
    with engine.begin() as conn:
        _insert_receipt(
            conn,
            receipt_id="archived",
            parse_status="review_needed",
            approved_at="2026-08-01 10:00:00",
            workflow_state="archived",
            deleted_at="2026-08-02 10:00:00",
        )
        _insert_receipt(
            conn,
            receipt_id="removed",
            parse_status="review_needed",
            approved_at="2026-08-01 10:00:00",
            workflow_state="removed_reimport_allowed",
            deleted_at="2026-08-02 10:00:00",
            raw_deleted_at="2026-08-02 10:00:00",
        )
        result = ensure_receipt_lifecycle_foundation_schema(conn)
        archived = _row(conn, "archived")
        removed = _row(conn, "removed")

    assert result["reconciled_explicit_approvals"] == 0
    assert archived["workflow_state"] == "archived"
    assert archived["approved_at"] == "2026-08-01 10:00:00"
    assert removed["workflow_state"] == "removed_reimport_allowed"
    assert removed["approved_at"] == "2026-08-01 10:00:00"


def test_reconciliation_does_not_touch_inventory_events():
    engine = _engine()
    with engine.begin() as conn:
        _insert_receipt(
            conn,
            receipt_id="inventory-safe",
            parse_status="manual",
            approved_at="2026-08-03 11:00:00",
        )
        conn.execute(
            text("INSERT INTO inventory_events (id, receipt_table_id, quantity) VALUES ('evt-1', 'inventory-safe', 3)")
        )
        before = conn.execute(text("SELECT id, receipt_table_id, quantity FROM inventory_events")).all()
        ensure_receipt_lifecycle_foundation_schema(conn)
        after = conn.execute(text("SELECT id, receipt_table_id, quantity FROM inventory_events")).all()
        row = _row(conn, "inventory-safe")

    assert before == after
    assert row["approved_at"] == "2026-08-03 11:00:00"
    assert row["parse_status"] == "approved"
