from __future__ import annotations

import os
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.postgresql_boolean_contract import (
    enforce_postgresql_boolean_parameters_before_execute,
)
from app.services.receipt_inventory_lifecycle_service import retime_receipt_inventory_events
from app.services.receipt_reimport_lineage_service import (
    get_prior_processed_line_fact,
    load_deleted_reimport_lineage,
)
from app.services.receipt_source_helper_service import (
    configure_receipt_source_helper_service,
    ensure_household_email_source,
)
from app.services.receipt_status_baseline_service import (
    _ensure_receipt_store_chain_schema,
    validate_receipt_status_baseline,
)
from app.services.receipt_status_sync import sync_receipt_statuses

HOUSEHOLD_ID = "postgresql-receipt-residual"
SOURCE_ID = f"{HOUSEHOLD_ID}-email-route"


def _engine_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _assert_runtime_create_denied(engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE receipt_residual_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_RECEIPT_RESIDUAL_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a receipt schema object")


def _column_map(inspector, table_name: str) -> dict[str, dict]:
    return {
        str(column.get("name") or ""): column
        for column in inspector.get_columns(table_name)
    }


def _assert_schema_contract(engine) -> None:
    inspector = inspect(engine)
    receipt_columns = _column_map(inspector, "receipt_tables")
    if "store_chain" not in receipt_columns:
        raise AssertionError("Canonical receipt_tables.store_chain is missing")
    if not isinstance(receipt_columns["store_chain"]["type"], (sa.Text, sa.String)):
        raise AssertionError(receipt_columns["store_chain"])

    line_columns = _column_map(inspector, "receipt_table_lines")
    source_columns = _column_map(inspector, "receipt_sources")
    for table_name, columns, column_names in (
        ("receipt_table_lines", line_columns, ("is_deleted", "is_validated")),
        ("receipt_sources", source_columns, ("is_active",)),
    ):
        for column_name in column_names:
            if not isinstance(columns[column_name]["type"], sa.Boolean):
                raise AssertionError(
                    f"Expected PostgreSQL BOOLEAN for {table_name}.{column_name}, "
                    f"got {columns[column_name]['type']}"
                )
    print("POSTGRESQL_RECEIPT_RESIDUAL_SCHEMA_CONTRACT_GREEN")
    print("POSTGRESQL_RECEIPT_RESIDUAL_BOOLEAN_TYPES_GREEN")


def _assert_receipt_approve_nullable_string_bind(engine) -> None:
    event.listen(
        engine,
        "before_execute",
        enforce_postgresql_boolean_parameters_before_execute,
        retval=True,
    )
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    UPDATE receipt_table_lines
                    SET matched_global_product_id = :matched_global_product_id,
                        matched_article_id = CASE
                            WHEN :matched_household_article_id IS NOT NULL THEN :matched_household_article_id
                            ELSE matched_article_id
                        END,
                        article_match_status = CASE
                            WHEN :matched_household_article_id IS NOT NULL THEN 'matched'
                            WHEN :matched_global_product_id IS NOT NULL THEN 'product_matched'
                            ELSE 'unmatched'
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :line_id AND receipt_table_id = :receipt_table_id
                    """
                ),
                {
                    "line_id": "no-such-receipt-line",
                    "receipt_table_id": "no-such-receipt",
                    "matched_global_product_id": None,
                    "matched_household_article_id": None,
                },
            )
            if result.rowcount not in (0, -1):
                raise AssertionError(result.rowcount)
    finally:
        event.remove(
            engine,
            "before_execute",
            enforce_postgresql_boolean_parameters_before_execute,
        )
    print("POSTGRESQL_RECEIPT_APPROVE_NULLABLE_STRING_BIND_GREEN")


def _assert_unpack_nullable_review_decision_bind(engine) -> None:
    event.listen(
        engine,
        "before_execute",
        enforce_postgresql_boolean_parameters_before_execute,
        retval=True,
    )
    try:
        with engine.begin() as conn:
            target_location_result = conn.execute(
                text(
                    """
                    UPDATE purchase_import_lines
                    SET target_location_id = :target_location_id,
                        location_override_mode = :location_override_mode,
                        review_decision = CASE WHEN :next_review_decision IS NOT NULL THEN :next_review_decision ELSE review_decision END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {
                    "target_location_id": "no-such-target-location",
                    "location_override_mode": "manual",
                    "next_review_decision": None,
                    "id": "no-such-purchase-import-line",
                },
            )
            if target_location_result.rowcount not in (0, -1):
                raise AssertionError(target_location_result.rowcount)

            article_link_result = conn.execute(
                text(
                    """
                    UPDATE purchase_import_lines
                    SET matched_household_article_id = :article_id,
                        review_decision = CASE WHEN :next_review_decision IS NOT NULL THEN :next_review_decision ELSE review_decision END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {
                    "article_id": "no-such-household-article",
                    "next_review_decision": None,
                    "id": "no-such-purchase-import-line",
                },
            )
            if article_link_result.rowcount not in (0, -1):
                raise AssertionError(article_link_result.rowcount)
    finally:
        event.remove(
            engine,
            "before_execute",
            enforce_postgresql_boolean_parameters_before_execute,
        )
    print("POSTGRESQL_UNPACK_NULLABLE_REVIEW_DECISION_BIND_GREEN")


def _serialize_source(row) -> dict:
    item = dict(row)
    item["is_active"] = bool(item.get("is_active"))
    return item


def _assert_receipt_paths(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())

    configure_receipt_source_helper_service(
        engine=engine,
        text=text,
        normalize_household_id=lambda value: str(value).strip(),
        serialize_receipt_source=_serialize_source,
    )

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM receipt_sources WHERE id = :id"), {"id": SOURCE_ID})
        conn.execute(
            text(
                """
                INSERT INTO household_registry (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {"id": HOUSEHOLD_ID, "naam": "PostgreSQL receipt residual proof"},
        )
        conn.execute(
            text(
                """
                INSERT INTO households (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO NOTHING
                """
            ),
            {"id": HOUSEHOLD_ID, "naam": "PostgreSQL receipt residual proof"},
        )
        _ensure_receipt_store_chain_schema(conn)
        lineage = load_deleted_reimport_lineage(conn, HOUSEHOLD_ID, "no-such-sha")
        if lineage is not None:
            raise AssertionError(lineage)
        processed = get_prior_processed_line_fact(
            conn,
            "no-such-logical-line",
            current_receipt_table_id="no-current-receipt",
        )
        if processed is not None:
            raise AssertionError(processed)
        retimed = retime_receipt_inventory_events(
            conn,
            receipt_table_id="no-such-receipt",
            purchase_at="2026-08-30T09:15:00+00:00",
            household_id=HOUSEHOLD_ID,
        )
        if int(retimed.get("updated_event_count") or 0) != 0:
            raise AssertionError(retimed)

    sync_result = sync_receipt_statuses(engine, HOUSEHOLD_ID)
    if int(sync_result.get("checked") or 0) != 0:
        raise AssertionError(sync_result)

    source = ensure_household_email_source(HOUSEHOLD_ID)
    if source.get("is_active") is not True:
        raise AssertionError(source)
    with engine.begin() as conn:
        stored = conn.execute(
            text("SELECT is_active FROM receipt_sources WHERE id = :id"),
            {"id": SOURCE_ID},
        ).scalar_one()
        if stored is not True:
            raise AssertionError(stored)
        conn.execute(
            text("UPDATE receipt_sources SET is_active = FALSE WHERE id = :id"),
            {"id": SOURCE_ID},
        )
    source = ensure_household_email_source(HOUSEHOLD_ID)
    if source.get("is_active") is not True:
        raise AssertionError(source)

    with engine.begin() as conn:
        validation = validate_receipt_status_baseline(conn, household_id=HOUSEHOLD_ID)
        if "summary" not in validation:
            raise AssertionError(validation)
        conn.execute(text("DELETE FROM receipt_sources WHERE id = :id"), {"id": SOURCE_ID})
        conn.execute(text("DELETE FROM households WHERE id = :id"), {"id": HOUSEHOLD_ID})
        conn.execute(text("DELETE FROM household_registry WHERE id = :id"), {"id": HOUSEHOLD_ID})

    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError(
            "Receipt residual runtime path mutated schema: "
            f"added={sorted(after_tables - before_tables)} removed={sorted(before_tables - after_tables)}"
        )

    print("POSTGRESQL_RECEIPT_INVENTORY_RETIME_DML_ONLY_GREEN")
    print("POSTGRESQL_RECEIPT_REIMPORT_LINEAGE_DML_ONLY_GREEN")
    print("POSTGRESQL_RECEIPT_SOURCE_BOOLEAN_DML_ONLY_GREEN")
    print("POSTGRESQL_RECEIPT_STATUS_BASELINE_DML_ONLY_GREEN")
    print("POSTGRESQL_RECEIPT_STATUS_SYNC_DML_ONLY_GREEN")
    print("POSTGRESQL_RECEIPT_RESIDUAL_SCHEMA_UNCHANGED_GREEN")


def main() -> None:
    engine = create_engine(_engine_url(), future=True)
    try:
        _assert_runtime_create_denied(engine)
        _assert_schema_contract(engine)
        _assert_receipt_approve_nullable_string_bind(engine)
        _assert_unpack_nullable_review_decision_bind(engine)
        _assert_receipt_paths(engine)
    finally:
        engine.dispose()
    print("POSTGRESQL_RECEIPT_RESIDUAL_DML_ONLY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
