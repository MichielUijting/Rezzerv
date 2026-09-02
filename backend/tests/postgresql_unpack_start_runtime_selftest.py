from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# This test intentionally exercises the production Uitpakken conversion helper
# through app.main on the real PostgreSQL runtime engine.  The household exists
# only in household_registry: receipt authority must not depend on the retired
# legacy households table.
UNPACK_HOUSEHOLD_ID = "postgresql-unpack-start-runtime"
RAW_RECEIPT_ID = "postgresql-unpack-start-raw"
RECEIPT_TABLE_ID = "postgresql-unpack-start-receipt"
RECEIPT_LINE_ID = "postgresql-unpack-start-line"


def _assert_postgresql_runtime() -> None:
    database_url = str(os.getenv("DATABASE_URL") or "").strip().lower()
    if not database_url.startswith("postgresql"):
        raise RuntimeError("This selftest requires PostgreSQL DATABASE_URL")
    if os.getenv("MIGRATION_DATABASE_URL"):
        raise RuntimeError("MIGRATION_DATABASE_URL must be absent during the DML-only runtime proof")


def _configure_test_runtime_paths() -> None:
    # app.main performs its normal runtime initialization at import time. GitHub
    # runners cannot create the container-only /app/data path, so keep this proof
    # on a writable isolated path without changing production startup semantics.
    os.environ["RECEIPT_STORAGE_ROOT"] = "/tmp/rezzerv-postgresql-unpack/receipts/raw"
    os.environ["REZZERV_RECEIPT_STARTUP_OCR_WARMUP"] = "false"
    os.environ["REZZERV_RECEIPT_STARTUP_REMBG_WARMUP"] = "false"


def _insert_approved_receipt_fixture(conn) -> None:
    conn.execute(
        text(
            """
            INSERT INTO household_registry (id, naam, created_at)
            VALUES (:id, :naam, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO NOTHING
            """
        ),
        {
            "id": UNPACK_HOUSEHOLD_ID,
            "naam": "PostgreSQL unpack start runtime proof",
        },
    )

    legacy_household = conn.execute(
        text("SELECT id FROM households WHERE id = :id"),
        {"id": UNPACK_HOUSEHOLD_ID},
    ).first()
    if legacy_household is not None:
        raise AssertionError("Unpack runtime fixture must not depend on legacy households")

    conn.execute(
        text(
            """
            INSERT INTO raw_receipts (
                id, household_id, source_id, original_filename, mime_type,
                storage_path, sha256_hash, raw_status, imported_at, created_at
            ) VALUES (
                :id, :household_id, NULL, :original_filename, 'application/pdf',
                :storage_path, :sha256_hash, 'imported', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": RAW_RECEIPT_ID,
            "household_id": UNPACK_HOUSEHOLD_ID,
            "original_filename": "postgresql-unpack-start.pdf",
            "storage_path": "/tmp/postgresql-unpack-start.pdf",
            "sha256_hash": "7" * 64,
        },
    )

    conn.execute(
        text(
            """
            INSERT INTO receipt_tables (
                id, raw_receipt_id, household_id, store_name, purchase_at,
                total_amount, currency, parse_status, line_count,
                approved_at, approved_by_user_email, created_at, updated_at
            ) VALUES (
                :id, :raw_receipt_id, :household_id, 'PostgreSQL Testwinkel', CURRENT_TIMESTAMP,
                2.50, 'EUR', 'approved', 1,
                CURRENT_TIMESTAMP, 'postgresql-selftest@rezzerv.local', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": RECEIPT_TABLE_ID,
            "raw_receipt_id": RAW_RECEIPT_ID,
            "household_id": UNPACK_HOUSEHOLD_ID,
        },
    )

    conn.execute(
        text(
            """
            INSERT INTO receipt_table_lines (
                id, receipt_table_id, line_index, raw_label, normalized_label,
                quantity, unit, line_total, article_match_status,
                matched_global_product_id, matched_article_id,
                created_at, updated_at
            ) VALUES (
                :id, :receipt_table_id, 1, 'HALFVOLLE MELK', 'halfvolle melk',
                1, 'st', 2.50, 'unmatched',
                NULL, NULL,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": RECEIPT_LINE_ID,
            "receipt_table_id": RECEIPT_TABLE_ID,
        },
    )


def main() -> None:
    _assert_postgresql_runtime()
    _configure_test_runtime_paths()

    import app.main as legacy_main

    with legacy_main.engine.connect() as conn:
        transaction = conn.begin()
        try:
            _insert_approved_receipt_fixture(conn)

            receipt = {
                "receipt_table_id": RECEIPT_TABLE_ID,
                "id": RECEIPT_TABLE_ID,
                "household_id": UNPACK_HOUSEHOLD_ID,
                "store_name": "PostgreSQL Testwinkel",
                "store_branch": None,
                "purchase_at": "2026-09-03T09:30:00+00:00",
                "created_at": "2026-09-03T09:30:00+00:00",
                "currency": "EUR",
                "line_count": 1,
                "total_amount": 2.50,
                "discount_total_effective": 0,
                "line_total_sum": 2.50,
                "net_line_total_sum": 2.50,
                "parse_status": "approved",
                "approved_at": "2026-09-03T09:31:00+00:00",
            }

            status = legacy_main.derive_unpack_receipt_status(receipt)
            if status not in {"Gecontroleerd", "Controle nodig"}:
                raise AssertionError(f"Unexpected Uitpakken inbox status: {status!r}")

            batch_id = legacy_main.ensure_unpack_batch_for_receipt(conn, receipt)
            if not batch_id:
                raise AssertionError("Approved receipt did not produce an Uitpakken batch")

            batch = conn.execute(
                text(
                    """
                    SELECT id, household_id, source_type, source_reference
                    FROM purchase_import_batches
                    WHERE id = :id
                    """
                ),
                {"id": batch_id},
            ).mappings().first()
            if not batch:
                raise AssertionError("Uitpakken batch was not persisted in the transaction")
            if str(batch.get("household_id") or "") != UNPACK_HOUSEHOLD_ID:
                raise AssertionError(batch)
            if str(batch.get("source_type") or "") != "receipt":
                raise AssertionError(batch)
            if str(batch.get("source_reference") or "") != f"receipt:{RECEIPT_TABLE_ID}":
                raise AssertionError(batch)

            line_count = conn.execute(
                text("SELECT COUNT(*) FROM purchase_import_lines WHERE batch_id = :batch_id"),
                {"batch_id": batch_id},
            ).scalar_one()
            if int(line_count or 0) < 1:
                raise AssertionError("Approved receipt produced no Uitpakken purchase-import lines")

            print("POSTGRESQL_RECEIPT_UNPACK_START_BATCH_GREEN")
        finally:
            transaction.rollback()


if __name__ == "__main__":
    main()
