import pytest
from types import SimpleNamespace
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.services.receipt_lifecycle_foundation_service import (
    ensure_receipt_lifecycle_foundation_schema,
    install_receipt_lifecycle_foundation,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE raw_receipts (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                sha256_hash TEXT NOT NULL,
                deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE UNIQUE INDEX uq_raw_receipts_household_hash
            ON raw_receipts (household_id, sha256_hash)
        """))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT NOT NULL UNIQUE,
                household_id TEXT NOT NULL,
                deleted_at DATETIME
            )
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                line_index INTEGER NOT NULL,
                raw_label TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_batches (
                id TEXT PRIMARY KEY,
                source_type TEXT,
                source_reference TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                external_line_ref TEXT,
                review_decision TEXT,
                processing_status TEXT,
                processed_event_id TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE inventory_events (
                id TEXT PRIMARY KEY,
                source_reference TEXT,
                source_line_id TEXT
            )
        """))
    return engine


def _columns(conn, table):
    return {str(row[1]) for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}


def test_release_a_extends_existing_entities_without_parallel_tables():
    engine = _engine()
    with engine.begin() as conn:
        before_tables = {
            str(row[0])
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        result = ensure_receipt_lifecycle_foundation_schema(conn)
        after_tables = {
            str(row[0])
            for row in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }

        assert before_tables == after_tables
        assert "logical_receipt_key" in _columns(conn, "receipt_tables")
        assert "workflow_state" in _columns(conn, "receipt_tables")
        assert "logical_line_key" in _columns(conn, "receipt_table_lines")
        assert result["added_columns"] == [
            "receipt_tables.logical_receipt_key",
            "receipt_tables.workflow_state",
            "receipt_table_lines.logical_line_key",
        ]


def test_release_a_runtime_installer_applies_schema_immediately_and_once():
    engine = _engine()
    app = SimpleNamespace(state=SimpleNamespace())

    install_receipt_lifecycle_foundation(app, engine)

    with engine.begin() as conn:
        assert "logical_receipt_key" in _columns(conn, "receipt_tables")
        assert "workflow_state" in _columns(conn, "receipt_tables")
        assert "logical_line_key" in _columns(conn, "receipt_table_lines")

    # A second install is a no-op through the app-state marker.
    install_receipt_lifecycle_foundation(app, engine)
    assert app.state._rezzerv_receipt_lifecycle_foundation_installed is True


def test_release_a_backfills_identity_once_and_is_idempotent():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-1', '0', 'abc')"))
        conn.execute(text("INSERT INTO receipt_tables (id, raw_receipt_id, household_id) VALUES ('receipt-1', 'raw-1', '0')"))
        conn.execute(text("INSERT INTO receipt_table_lines (id, receipt_table_id, line_index, raw_label) VALUES ('line-1', 'receipt-1', 1, 'Melk')"))

        first = ensure_receipt_lifecycle_foundation_schema(conn)
        receipt_key_1 = conn.execute(text("SELECT logical_receipt_key FROM receipt_tables WHERE id='receipt-1'")).scalar_one()
        line_key_1 = conn.execute(text("SELECT logical_line_key FROM receipt_table_lines WHERE id='line-1'")).scalar_one()

        second = ensure_receipt_lifecycle_foundation_schema(conn)
        receipt_key_2 = conn.execute(text("SELECT logical_receipt_key FROM receipt_tables WHERE id='receipt-1'")).scalar_one()
        line_key_2 = conn.execute(text("SELECT logical_line_key FROM receipt_table_lines WHERE id='line-1'")).scalar_one()

        assert receipt_key_1 and receipt_key_1 == receipt_key_2
        assert line_key_1 and line_key_1 == line_key_2
        assert first["backfilled_receipts"] == 1
        assert first["backfilled_lines"] == 1
        assert second["backfilled_receipts"] == 0
        assert second["backfilled_lines"] == 0


def test_logical_keys_may_be_reused_by_future_reimport_attempts():
    engine = _engine()
    with engine.begin() as conn:
        ensure_receipt_lifecycle_foundation_schema(conn)
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-1', '0', 'hash-1')"))
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-2', '0', 'hash-2')"))
        conn.execute(text("""
            INSERT INTO receipt_tables (id, raw_receipt_id, household_id, logical_receipt_key)
            VALUES ('receipt-1', 'raw-1', '0', 'same-receipt')
        """))
        conn.execute(text("""
            INSERT INTO receipt_tables (id, raw_receipt_id, household_id, logical_receipt_key)
            VALUES ('receipt-2', 'raw-2', '0', 'same-receipt')
        """))
        conn.execute(text("""
            INSERT INTO receipt_table_lines (id, receipt_table_id, line_index, raw_label, logical_line_key)
            VALUES ('line-1', 'receipt-1', 1, 'Melk', 'same-line')
        """))
        conn.execute(text("""
            INSERT INTO receipt_table_lines (id, receipt_table_id, line_index, raw_label, logical_line_key)
            VALUES ('line-2', 'receipt-2', 1, 'Melk', 'same-line')
        """))

        assert conn.execute(text("SELECT COUNT(*) FROM receipt_tables WHERE logical_receipt_key='same-receipt'")).scalar_one() == 2
        assert conn.execute(text("SELECT COUNT(*) FROM receipt_table_lines WHERE logical_line_key='same-line'")).scalar_one() == 2


def test_exact_source_hash_can_be_reused_only_after_soft_delete():
    engine = _engine()
    with engine.begin() as conn:
        ensure_receipt_lifecycle_foundation_schema(conn)
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-active', '0', 'same-hash')"))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-duplicate', '0', 'same-hash')"))

    with engine.begin() as conn:
        conn.execute(text("UPDATE raw_receipts SET deleted_at=CURRENT_TIMESTAMP WHERE id='raw-active'"))
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-reimport', '0', 'same-hash')"))
        assert conn.execute(text("SELECT COUNT(*) FROM raw_receipts WHERE household_id='0' AND sha256_hash='same-hash'")).scalar_one() == 2


def test_legacy_deleted_receipt_gets_no_invented_archive_or_remove_meaning():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash, deleted_at) VALUES ('raw-1', '0', 'abc', CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO receipt_tables (id, raw_receipt_id, household_id, deleted_at) VALUES ('receipt-1', 'raw-1', '0', CURRENT_TIMESTAMP)"))
        ensure_receipt_lifecycle_foundation_schema(conn)
        assert conn.execute(text("SELECT workflow_state FROM receipt_tables WHERE id='receipt-1'")).scalar_one() == "legacy_deleted"
