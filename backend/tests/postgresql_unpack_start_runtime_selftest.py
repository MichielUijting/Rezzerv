from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Boolean, Integer, inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# This test intentionally exercises the production Uitpakken HTTP endpoint
# through app.main on the real PostgreSQL runtime engine. The fixture is
# committed because the ASGI request uses its own runtime database connection.
UNPACK_HOUSEHOLD_ID = "postgresql-unpack-start-runtime"
RAW_RECEIPT_ID = "postgresql-unpack-start-raw"
RECEIPT_TABLE_ID = "postgresql-unpack-start-receipt"
RECEIPT_LINE_ID = "postgresql-unpack-start-line"
ARTICLE_GROUP_ID = "postgresql-unpack-start-group"
HOUSEHOLD_ARTICLE_ID = "postgresql-unpack-start-article"
SPACE_ID = "postgresql-unpack-start-space"
SUBLOCATION_ID = "postgresql-unpack-start-sublocation"
MEMORY_ID = "postgresql-unpack-start-memory"


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


def _column_map(conn, table_name: str) -> dict[str, dict]:
    return {
        str(column.get("name") or ""): column
        for column in inspect(conn).get_columns(table_name)
    }


def _coerce_fixture_value(column: dict, value):
    column_type = column.get("type")
    if isinstance(column_type, Boolean):
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return bool(value)
    if isinstance(column_type, Integer) and isinstance(value, bool):
        return int(value)
    return value


def _insert_row(conn, table_name: str, values: dict) -> None:
    available = _column_map(conn, table_name)
    selected = {
        key: _coerce_fixture_value(available[key], value)
        for key, value in values.items()
        if key in available
    }
    if not selected:
        raise AssertionError(f"No usable fixture columns for {table_name}")
    columns = ", ".join(selected)
    parameters = ", ".join(f":{key}" for key in selected)
    conn.execute(text(f"INSERT INTO {table_name} ({columns}) VALUES ({parameters})"), selected)


def _insert_approved_receipt_fixture(conn) -> None:
    _insert_row(
        conn,
        "household_registry",
        {"id": UNPACK_HOUSEHOLD_ID, "naam": "PostgreSQL unpack start runtime proof"},
    )

    legacy_household = conn.execute(
        text("SELECT id FROM households WHERE id = :id"),
        {"id": UNPACK_HOUSEHOLD_ID},
    ).first()
    if legacy_household is not None:
        raise AssertionError("Unpack runtime fixture must not depend on legacy households")

    _insert_row(
        conn,
        "article_groups",
        {
            "id": ARTICLE_GROUP_ID,
            "household_id": UNPACK_HOUSEHOLD_ID,
            "name": "Zuivel",
            "normalized_name": "zuivel",
            "status": "active",
            "sort_order": 1,
        },
    )
    _insert_row(
        conn,
        "household_articles",
        {
            "id": HOUSEHOLD_ARTICLE_ID,
            "household_id": UNPACK_HOUSEHOLD_ID,
            "naam": "Halfvolle melk",
            "name": "Halfvolle melk",
            "custom_name": "Halfvolle melk",
            "article_group_id": ARTICLE_GROUP_ID,
            "status": "active",
            "active": True,
            "consumable": True,
        },
    )
    _insert_row(
        conn,
        "spaces",
        {
            "id": SPACE_ID,
            "household_id": UNPACK_HOUSEHOLD_ID,
            "naam": "Keuken",
            "active": True,
        },
    )
    _insert_row(
        conn,
        "sublocations",
        {
            "id": SUBLOCATION_ID,
            "space_id": SPACE_ID,
            "household_id": UNPACK_HOUSEHOLD_ID,
            "naam": "Koelkast",
            "active": True,
        },
    )

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
                total_amount, currency, parse_status, workflow_state, line_count,
                approved_at, approved_by_user_email, created_at, updated_at
            ) VALUES (
                :id, :raw_receipt_id, :household_id, 'PostgreSQL Testwinkel', CURRENT_TIMESTAMP,
                2.50, 'EUR', 'approved', 'active', 1,
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
                line_role, inventory_eligible,
                matched_global_product_id, matched_article_id,
                created_at, updated_at
            ) VALUES (
                :id, :receipt_table_id, 1, 'HALFVOLLE MELK', 'halfvolle melk',
                1, 'st', 2.50, 'unmatched',
                'product', 1,
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


def _insert_confirmed_store_memory(conn, legacy_main) -> None:
    normalized_key = legacy_main.normalize_store_memory_key("HALFVOLLE MELK", None)
    _insert_row(
        conn,
        "store_import_memory",
        {
            "id": MEMORY_ID,
            "household_id": UNPACK_HOUSEHOLD_ID,
            "store_provider_code": "receipt",
            "raw_article_name": "HALFVOLLE MELK",
            "raw_brand": None,
            "normalized_key": normalized_key,
            "matched_household_article_id": HOUSEHOLD_ARTICLE_ID,
            "preferred_location_id": SUBLOCATION_ID,
            "times_confirmed": 1,
        },
    )


def main() -> None:
    _assert_postgresql_runtime()
    _configure_test_runtime_paths()

    import app.main as legacy_main

    if legacy_main.engine.dialect.name != "postgresql":
        raise AssertionError(f"Unexpected runtime dialect: {legacy_main.engine.dialect.name}")

    # The real UI request uses a separate database connection, so seed and commit
    # exactly the rows it must discover at runtime.
    with legacy_main.engine.begin() as conn:
        _insert_approved_receipt_fixture(conn)
        _insert_confirmed_store_memory(conn, legacy_main)

    # Authentication is not under test here. Keep the real FastAPI route, request,
    # transaction handling, receipt query, batch creation/sync and prefill path.
    original_resolver = legacy_main.resolve_authorized_household_id
    legacy_main.resolve_authorized_household_id = (
        lambda authorization, requested_household_id, require_authorization=True: UNPACK_HOUSEHOLD_ID
    )
    try:
        with TestClient(legacy_main.app) as client:
            try:
                response = client.get(
                    "/api/unpack-start-batches",
                    params={"householdId": UNPACK_HOUSEHOLD_ID},
                    headers={"Authorization": "Bearer postgresql-runtime-selftest"},
                )
            except Exception:
                print("POSTGRESQL_RECEIPT_UNPACK_HTTP_RUNTIME_EXCEPTION")
                traceback.print_exc()
                raise
    finally:
        legacy_main.resolve_authorized_household_id = original_resolver

    if response.status_code != 200:
        raise AssertionError(
            f"Uitpakken runtime endpoint returned HTTP {response.status_code}: {response.text}"
        )
    payload = response.json()
    items = list(payload.get("items") or [])
    matching = [item for item in items if str(item.get("receipt_table_id") or "") == RECEIPT_TABLE_ID]
    if len(matching) != 1:
        raise AssertionError(f"Uitpakken runtime endpoint did not return the approved receipt: {payload!r}")

    batch_id = str(matching[0].get("batch_id") or "")
    if not batch_id:
        raise AssertionError("Uitpakken runtime endpoint returned no batch id")

    with legacy_main.engine.begin() as conn:
        line = conn.execute(
            text(
                """
                SELECT matched_household_article_id, target_location_id,
                       is_auto_prefilled, review_decision, match_status
                FROM purchase_import_lines
                WHERE batch_id = :batch_id
                LIMIT 1
                """
            ),
            {"batch_id": batch_id},
        ).mappings().first()
    if not line:
        raise AssertionError("Uitpakken runtime endpoint created no purchase import line")
    if str(line.get("matched_household_article_id") or "") != HOUSEHOLD_ARTICLE_ID:
        raise AssertionError(dict(line))
    if str(line.get("target_location_id") or "") != SUBLOCATION_ID:
        raise AssertionError(dict(line))
    if line.get("is_auto_prefilled") is not True:
        raise AssertionError(dict(line))

    print("POSTGRESQL_RECEIPT_UNPACK_HTTP_RUNTIME_GREEN")
    print("POSTGRESQL_RECEIPT_UNPACK_START_BATCH_GREEN")


if __name__ == "__main__":
    main()
