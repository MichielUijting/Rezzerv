from __future__ import annotations

from sqlalchemy import create_engine, text

import app.services.receipt_service as receipt_service


def _schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE raw_receipts (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            raw_status TEXT,
            original_filename TEXT,
            sha256_hash TEXT,
            deleted_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE receipt_tables (
            id TEXT PRIMARY KEY,
            raw_receipt_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            store_name TEXT,
            store_branch TEXT,
            purchase_at TEXT,
            total_amount REAL,
            parse_status TEXT,
            line_count INTEGER,
            workflow_state TEXT,
            approved_at TEXT,
            deleted_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE receipt_table_lines (
            id TEXT PRIMARY KEY,
            receipt_table_id TEXT NOT NULL,
            line_index INTEGER,
            raw_label TEXT,
            normalized_label TEXT,
            line_total REAL
        )
    """))


def _insert_receipt(conn, *, suffix: str, workflow_state: str, deleted: bool = False) -> None:
    raw_id = f"raw-{suffix}"
    receipt_id = f"receipt-{suffix}"
    deleted_at = "2026-09-30T12:00:00" if deleted else None
    conn.execute(
        text("""
            INSERT INTO raw_receipts (
                id, household_id, raw_status, original_filename, sha256_hash, deleted_at
            ) VALUES (
                :id, 'household-1', 'parsed', :filename, :sha, :deleted_at
            )
        """),
        {
            "id": raw_id,
            "filename": f"{suffix}.jpg",
            "sha": f"sha-{suffix}",
            "deleted_at": deleted_at,
        },
    )
    conn.execute(
        text("""
            INSERT INTO receipt_tables (
                id, raw_receipt_id, household_id, store_name, purchase_at,
                total_amount, parse_status, line_count, workflow_state,
                approved_at, deleted_at
            ) VALUES (
                :id, :raw_id, 'household-1', 'Testwinkel', '2026-09-30T10:00:00',
                12.34, 'approved', 1, :workflow_state,
                '2026-09-30T10:05:00', :deleted_at
            )
        """),
        {
            "id": receipt_id,
            "raw_id": raw_id,
            "workflow_state": workflow_state,
            "deleted_at": deleted_at,
        },
    )
    conn.execute(
        text("""
            INSERT INTO receipt_table_lines (
                id, receipt_table_id, line_index, raw_label, normalized_label, line_total
            ) VALUES (
                :id, :receipt_id, 0, 'Testartikel', 'testartikel', 12.34
            )
        """),
        {"id": f"line-{suffix}", "receipt_id": receipt_id},
    )


def test_exact_hash_blocks_active_approved_and_archived_receipts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        _schema(conn)
        _insert_receipt(conn, suffix="kassa", workflow_state="active")
        _insert_receipt(conn, suffix="archief", workflow_state="archived", deleted=True)

        active = receipt_service.find_existing_receipt_by_content_hash(
            conn, "household-1", "sha-kassa"
        )
        archived = receipt_service.find_existing_receipt_by_content_hash(
            conn, "household-1", "sha-archief"
        )

    assert active and active["receipt_table_id"] == "receipt-kassa"
    assert archived and archived["receipt_table_id"] == "receipt-archief"


def test_explicit_removed_reimport_allowed_does_not_block_exact_hash() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        _schema(conn)
        _insert_receipt(
            conn,
            suffix="removed",
            workflow_state="removed_reimport_allowed",
            deleted=True,
        )

        duplicate = receipt_service.find_existing_receipt_by_content_hash(
            conn, "household-1", "sha-removed"
        )

    assert duplicate is None


def test_cross_source_fingerprint_includes_archived_but_excludes_reimport_allowed(monkeypatch) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        _schema(conn)
        _insert_receipt(conn, suffix="archived-web", workflow_state="archived", deleted=True)
        _insert_receipt(
            conn,
            suffix="removed-photo",
            workflow_state="removed_reimport_allowed",
            deleted=True,
        )

        monkeypatch.setattr(
            receipt_service,
            "_fingerprint_from_stored_receipt",
            lambda row, lines: "same-purchase"
            if row["receipt_table_id"] == "receipt-archived-web"
            else "other",
        )

        duplicate = receipt_service.find_existing_receipt_by_fingerprint(
            conn,
            "household-1",
            "same-purchase",
        )

    assert duplicate
    assert duplicate["receipt_table_id"] == "receipt-archived-web"
    assert duplicate["workflow_state"] == "archived"


def test_workflow_state_policy_blocks_kassa_unpack_inventory_history() -> None:
    assert receipt_service._blocks_receipt_reimport("active") is True
    assert receipt_service._blocks_receipt_reimport("returned_to_kassa") is True
    assert receipt_service._blocks_receipt_reimport("archived") is True
    assert receipt_service._blocks_receipt_reimport(None) is True
    assert receipt_service._blocks_receipt_reimport("removed_reimport_allowed") is False
    assert receipt_service._blocks_receipt_reimport("legacy_deleted") is False
