from __future__ import annotations

from decimal import Decimal
import hashlib
import uuid

from sqlalchemy import text

from app.db import engine


QUANTITIES = (
    Decimal("0.404"),
    Decimal("1.224"),
    Decimal("1.234567"),
)


def _assert_unbounded_numeric(conn, table_name: str, column_name: str) -> None:
    row = conn.execute(
        text(
            """
            SELECT
                format_type(a.atttypid, a.atttypmod) AS formatted_type,
                a.atttypmod AS type_modifier,
                c.data_type,
                c.numeric_precision,
                c.numeric_scale
            FROM pg_attribute a
            JOIN pg_class t ON t.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN information_schema.columns c
              ON c.table_schema = n.nspname
             AND c.table_name = t.relname
             AND c.column_name = a.attname
            WHERE n.nspname = current_schema()
              AND t.relname = :table_name
              AND a.attname = :column_name
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).mappings().one()

    assert str(row["formatted_type"]) == "numeric", row
    assert int(row["type_modifier"]) == -1, row
    assert str(row["data_type"]) == "numeric", row
    assert row["numeric_precision"] is None, row
    assert row["numeric_scale"] is None, row


def main_test() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name

    household_id = f"f5-quantity-{uuid.uuid4()}"
    provider_id = str(uuid.uuid4())
    connection_id = str(uuid.uuid4())
    purchase_batch_id = str(uuid.uuid4())
    raw_receipt_id = str(uuid.uuid4())
    receipt_table_id = str(uuid.uuid4())

    with engine.begin() as conn:
        current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
        runtime_create = bool(
            conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar_one()
        )
        assert current_user == "rezzerv_app", current_user
        assert runtime_create is False, runtime_create

        _assert_unbounded_numeric(conn, "purchase_import_lines", "quantity_raw")
        _assert_unbounded_numeric(conn, "receipt_table_lines", "quantity")

        conn.execute(
            text(
                """
                INSERT INTO household_registry (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                """
            ),
            {"id": household_id, "naam": "F5 quantity unbounded decimals"},
        )
        conn.execute(
            text(
                """
                INSERT INTO households (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                """
            ),
            {"id": household_id, "naam": "F5 quantity unbounded decimals"},
        )
        conn.execute(
            text(
                """
                INSERT INTO store_providers (id, code, name, status, import_mode)
                VALUES (:id, :code, :name, 'active', 'mock')
                """
            ),
            {
                "id": provider_id,
                "code": f"f5_quantity_{provider_id.replace('-', '')[:12]}",
                "name": "F5 quantity provider",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO household_store_connections (
                    id, household_id, store_provider_id, connection_status, linked_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, 'active', CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": connection_id,
                "household_id": household_id,
                "store_provider_id": provider_id,
            },
        )

        conn.execute(
            text(
                """
                INSERT INTO purchase_import_batches (
                    id, household_id, store_provider_id, connection_id, source_type,
                    source_reference, import_status, raw_payload, created_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, :connection_id, 'mock',
                    :source_reference, 'new', :raw_payload, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": purchase_batch_id,
                "household_id": household_id,
                "store_provider_id": provider_id,
                "connection_id": connection_id,
                "source_reference": f"f5-05::{household_id}",
                "raw_payload": "{}",
            },
        )

        for index, quantity in enumerate(QUANTITIES, start=1):
            conn.execute(
                text(
                    """
                    INSERT INTO purchase_import_lines (
                        id, batch_id, external_line_ref, external_article_code,
                        article_name_raw, brand_raw, quantity_raw, unit_raw,
                        line_price_raw, currency_code, match_status, review_decision,
                        ui_sort_order, created_at
                    ) VALUES (
                        :id, :batch_id, :external_line_ref, NULL,
                        :article_name_raw, NULL, :quantity_raw, 'kg',
                        NULL, 'EUR', 'unmatched', NULL,
                        :ui_sort_order, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "batch_id": purchase_batch_id,
                    "external_line_ref": f"f5-05-purchase-{index}",
                    "article_name_raw": f"F5 quantity {quantity}",
                    "quantity_raw": quantity,
                    "ui_sort_order": index,
                },
            )

        sha256_hash = hashlib.sha256(household_id.encode("utf-8")).hexdigest()
        conn.execute(
            text(
                """
                INSERT INTO raw_receipts (
                    id, household_id, source_id, original_filename, mime_type,
                    storage_path, sha256_hash, duplicate_of_raw_receipt_id,
                    raw_status, imported_at, created_at
                ) VALUES (
                    :id, :household_id, NULL, 'f5-05-quantity.txt', 'text/plain',
                    :storage_path, :sha256_hash, NULL,
                    'imported', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": raw_receipt_id,
                "household_id": household_id,
                "storage_path": f"f5-05/{raw_receipt_id}.txt",
                "sha256_hash": sha256_hash,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO receipt_tables (
                    id, raw_receipt_id, household_id, store_name, store_branch,
                    purchase_at, total_amount, discount_total, currency,
                    parse_status, confidence_score, line_count, workflow_state,
                    created_at, updated_at
                ) VALUES (
                    :id, :raw_receipt_id, :household_id, 'F5', 'Quantity authority',
                    '2026-09-07T10:00:00', 0.00, 0.00, 'EUR',
                    'parsed', 1.0, 3, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": receipt_table_id,
                "raw_receipt_id": raw_receipt_id,
                "household_id": household_id,
            },
        )

        for index, quantity in enumerate(QUANTITIES, start=1):
            conn.execute(
                text(
                    """
                    INSERT INTO receipt_table_lines (
                        id, receipt_table_id, line_index, raw_label, normalized_label,
                        quantity, unit, unit_price, line_total, discount_amount,
                        barcode, article_match_status, matched_article_id,
                        confidence_score, created_at, updated_at
                    ) VALUES (
                        :id, :receipt_table_id, :line_index, :raw_label, :normalized_label,
                        :quantity, 'kg', 0.00, 0.00, 0.00,
                        NULL, 'unmatched', NULL,
                        1.0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "receipt_table_id": receipt_table_id,
                    "line_index": index,
                    "raw_label": f"F5 quantity {quantity}",
                    "normalized_label": f"f5 quantity {quantity}",
                    "quantity": quantity,
                },
            )

        purchase_rows = conn.execute(
            text(
                """
                SELECT ui_sort_order, quantity_raw, quantity_raw::text AS quantity_text
                FROM purchase_import_lines
                WHERE batch_id = :batch_id
                ORDER BY ui_sort_order
                """
            ),
            {"batch_id": purchase_batch_id},
        ).mappings().all()
        receipt_rows = conn.execute(
            text(
                """
                SELECT line_index, quantity, quantity::text AS quantity_text
                FROM receipt_table_lines
                WHERE receipt_table_id = :receipt_table_id
                ORDER BY line_index
                """
            ),
            {"receipt_table_id": receipt_table_id},
        ).mappings().all()

    assert len(purchase_rows) == len(QUANTITIES), purchase_rows
    assert len(receipt_rows) == len(QUANTITIES), receipt_rows

    for expected, purchase_row, receipt_row in zip(QUANTITIES, purchase_rows, receipt_rows):
        assert isinstance(purchase_row["quantity_raw"], Decimal), purchase_row
        assert purchase_row["quantity_raw"] == expected, purchase_row
        assert Decimal(str(purchase_row["quantity_text"])) == expected, purchase_row

        assert isinstance(receipt_row["quantity"], Decimal), receipt_row
        assert receipt_row["quantity"] == expected, receipt_row
        assert Decimal(str(receipt_row["quantity_text"])) == expected, receipt_row

        marker = str(expected).replace(".", "_")
        print(f"PASS purchase_import_quantity_preserves_{marker}")
        print(f"PASS receipt_table_quantity_preserves_{marker}")

    print("PASS quantity_columns_are_unbounded_numeric")
    print("PASS financial_rounding_is_not_quantity_policy")
    print("PASS postgresql_runtime_is_dml_only")
    print("F5_QUANTITY_UNBOUNDED_DECIMALS_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_test())
