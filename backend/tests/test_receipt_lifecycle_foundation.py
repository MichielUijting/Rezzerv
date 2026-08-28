import pytest
from types import SimpleNamespace
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.services.receipt_lifecycle_foundation_service import (
    ensure_receipt_lifecycle_foundation_schema,
    install_receipt_lifecycle_foundation,
    reconcile_receipt_lifecycle_foundation_data,
)
from app.testing.receipt_lifecycle_contract import create_receipt_approval_guard_trigger


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
            WHERE deleted_at IS NULL
        """))
        conn.execute(text("""
            CREATE TABLE receipt_tables (
                id TEXT PRIMARY KEY,
                raw_receipt_id TEXT NOT NULL UNIQUE,
                household_id TEXT NOT NULL,
                parse_status TEXT,
                approved_at DATETIME,
                reviewed_at DATETIME,
                approved_by_user_email TEXT,
                totals_overridden INTEGER NOT NULL DEFAULT 0,
                deleted_at DATETIME,
                updated_at DATETIME,
                logical_receipt_key TEXT,
                workflow_state TEXT NOT NULL DEFAULT 'active'
            )
        """))
        conn.execute(text("""
            CREATE INDEX idx_receipt_tables_logical_receipt_key
            ON receipt_tables (household_id, logical_receipt_key)
        """))
        conn.execute(text("""
            CREATE INDEX idx_receipt_tables_workflow_state
            ON receipt_tables (household_id, workflow_state)
        """))
        conn.execute(text("""
            CREATE TABLE receipt_table_lines (
                id TEXT PRIMARY KEY,
                receipt_table_id TEXT NOT NULL,
                line_index INTEGER NOT NULL,
                raw_label TEXT NOT NULL,
                logical_line_key TEXT
            )
        """))
        conn.execute(text("""
            CREATE INDEX idx_receipt_table_lines_logical_line_key
            ON receipt_table_lines (logical_line_key)
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
        create_receipt_approval_guard_trigger(conn)
    return engine


def _schema(conn):
    return tuple(
        conn.execute(
            text(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE sql IS NOT NULL ORDER BY type, name"
            )
        ).all()
    )


def test_legacy_schema_hook_is_inert_on_canonical_schema():
    engine = _engine()
    with engine.begin() as conn:
        before = _schema(conn)
        result = ensure_receipt_lifecycle_foundation_schema(conn)
        after = _schema(conn)

    assert result is None
    assert before == after


def test_runtime_installer_reconciles_data_immediately_and_once():
    engine = _engine()
    app = SimpleNamespace(state=SimpleNamespace())
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-1', '0', 'abc')"))
        conn.execute(text("INSERT INTO receipt_tables (id, raw_receipt_id, household_id) VALUES ('receipt-1', 'raw-1', '0')"))
        conn.execute(text("INSERT INTO receipt_table_lines (id, receipt_table_id, line_index, raw_label) VALUES ('line-1', 'receipt-1', 1, 'Melk')"))

    install_receipt_lifecycle_foundation(app, engine)

    with engine.begin() as conn:
        assert conn.execute(text("SELECT logical_receipt_key FROM receipt_tables WHERE id='receipt-1'")).scalar_one()
        assert conn.execute(text("SELECT logical_line_key FROM receipt_table_lines WHERE id='line-1'")).scalar_one()

    install_receipt_lifecycle_foundation(app, engine)
    assert app.state._rezzerv_receipt_lifecycle_foundation_installed is True


def test_data_reconciliation_backfills_identity_once_and_is_idempotent():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO raw_receipts (id, household_id, sha256_hash) VALUES ('raw-1', '0', 'abc')"))
        conn.execute(text("INSERT INTO receipt_tables (id, raw_receipt_id, household_id) VALUES ('receipt-1', 'raw-1', '0')"))
        conn.execute(text("INSERT INTO receipt_table_lines (id, receipt_table_id, line_index, raw_label) VALUES ('line-1', 'receipt-1', 1, 'Melk')"))

        first = reconcile_receipt_lifecycle_foundation_data(conn)
        receipt_key_1 = conn.execute(text("SELECT logical_receipt_key FROM receipt_tables WHERE id='receipt-1'")).scalar_one()
        line_key_1 = conn.execute(text("SELECT logical_line_key FROM receipt_table_lines WHERE id='line-1'")).scalar_one()

        second = reconcile_receipt_lifecycle_foundation_data(conn)
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
        reconcile_receipt_lifecycle_foundation_data(conn)
        assert conn.execute(text("SELECT workflow_state FROM receipt_tables WHERE id='receipt-1'")).scalar_one() == "legacy_deleted"
