from __future__ import annotations

import argparse
from decimal import Decimal

from sqlalchemy import text

from app.db import engine


TARGETS = (
    ("239ccbf1-6880-4390-9c83-cb141836f72c", Decimal("0.40"), Decimal("0.404")),
    ("572f88a8-1bca-4e47-ac8c-0d903188ca4b", Decimal("1.22"), Decimal("1.224")),
)

DECOYS = (
    ("11111111-1111-4111-8111-111111111111", Decimal("0.40")),
    ("22222222-2222-4222-8222-222222222222", Decimal("1.22")),
)

HOUSEHOLD_ID = "33333333-3333-4333-8333-333333333333"
PROVIDER_ID = "44444444-4444-4444-8444-444444444444"
CONNECTION_ID = "55555555-5555-4555-8555-555555555555"
BATCH_ID = "66666666-6666-4666-8666-666666666666"


def _assert_runtime_boundary(conn) -> None:
    current_user = str(conn.execute(text("SELECT current_user")).scalar_one())
    runtime_create = bool(
        conn.execute(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        ).scalar_one()
    )
    assert current_user == "rezzerv_app", current_user
    assert runtime_create is False, runtime_create


def _current_revision(conn) -> str:
    return str(conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def _quantity_map(conn) -> dict[str, Decimal]:
    ids = [line_id for line_id, *_ in TARGETS] + [line_id for line_id, _ in DECOYS]
    rows = conn.execute(
        text(
            """
            SELECT id, quantity_raw
            FROM purchase_import_lines
            WHERE id IN (:target_1, :target_2, :decoy_1, :decoy_2)
            """
        ),
        {
            "target_1": ids[0],
            "target_2": ids[1],
            "decoy_1": ids[2],
            "decoy_2": ids[3],
        },
    ).mappings().all()
    result = {str(row["id"]): row["quantity_raw"] for row in rows}
    assert len(result) == 4, result
    for value in result.values():
        assert isinstance(value, Decimal), result
    return result


def seed_legacy() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.begin() as conn:
        _assert_runtime_boundary(conn)
        assert _current_revision(conn) == "20260902_01", _current_revision(conn)

        conn.execute(
            text(
                """
                INSERT INTO household_registry (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                """
            ),
            {"id": HOUSEHOLD_ID, "naam": "F5 historical quantity restoration"},
        )
        conn.execute(
            text(
                """
                INSERT INTO households (id, naam, created_at)
                VALUES (:id, :naam, CURRENT_TIMESTAMP)
                """
            ),
            {"id": HOUSEHOLD_ID, "naam": "F5 historical quantity restoration"},
        )
        conn.execute(
            text(
                """
                INSERT INTO store_providers (id, code, name, status, import_mode)
                VALUES (:id, 'f5_history_quantity', 'F5 historical quantity', 'active', 'mock')
                """
            ),
            {"id": PROVIDER_ID},
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
                "id": CONNECTION_ID,
                "household_id": HOUSEHOLD_ID,
                "store_provider_id": PROVIDER_ID,
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
                    'f5-06-historical-quantity-restoration', 'new', '{}', CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": BATCH_ID,
                "household_id": HOUSEHOLD_ID,
                "store_provider_id": PROVIDER_ID,
                "connection_id": CONNECTION_ID,
            },
        )

        lines: list[tuple[str, Decimal, str]] = [
            (TARGETS[0][0], TARGETS[0][1], "target-0.40"),
            (TARGETS[1][0], TARGETS[1][1], "target-1.22"),
            (DECOYS[0][0], DECOYS[0][1], "decoy-0.40"),
            (DECOYS[1][0], DECOYS[1][1], "decoy-1.22"),
        ]
        for index, (line_id, quantity, label) in enumerate(lines, start=1):
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
                    "id": line_id,
                    "batch_id": BATCH_ID,
                    "external_line_ref": f"f5-06-{index}",
                    "article_name_raw": label,
                    "quantity_raw": quantity,
                    "ui_sort_order": index,
                },
            )

        values = _quantity_map(conn)
        for line_id, rounded, _ in TARGETS:
            assert values[line_id] == rounded, values
        for line_id, rounded in DECOYS:
            assert values[line_id] == rounded, values

    print("PASS historical_quantity_legacy_fixture_seeded_at_20260902_01")
    print("PASS postgresql_runtime_is_dml_only")
    return 0


def verify_restored() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.connect() as conn:
        _assert_runtime_boundary(conn)
        assert _current_revision(conn) == "20260903_01", _current_revision(conn)
        values = _quantity_map(conn)

    for line_id, _, restored in TARGETS:
        assert values[line_id] == restored, values
    for line_id, rounded in DECOYS:
        assert values[line_id] == rounded, values

    print("PASS historical_quantity_target_239ccbf1_restored_0_404")
    print("PASS historical_quantity_target_572f88a8_restored_1_224")
    print("PASS unrelated_rounded_quantity_0_40_is_not_changed")
    print("PASS unrelated_rounded_quantity_1_22_is_not_changed")
    print("PASS historical_quantity_restoration_reaches_20260903_01")
    print("PASS postgresql_runtime_is_dml_only")
    print("F5_HISTORICAL_QUANTITY_RESTORATION_GREEN")
    return 0


def prepare_guard() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.begin() as conn:
        _assert_runtime_boundary(conn)
        assert _current_revision(conn) == "20260902_01", _current_revision(conn)
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET quantity_raw = :quantity
                WHERE id = :line_id
                """
            ),
            {"line_id": TARGETS[0][0], "quantity": Decimal("0.41")},
        )
        conn.execute(
            text(
                """
                UPDATE purchase_import_lines
                SET quantity_raw = :quantity
                WHERE id = :line_id
                """
            ),
            {"line_id": TARGETS[1][0], "quantity": Decimal("1.23")},
        )
        values = _quantity_map(conn)
        assert values[TARGETS[0][0]] == Decimal("0.41"), values
        assert values[TARGETS[1][0]] == Decimal("1.23"), values

    print("PASS guarded_quantity_user_edits_prepared")
    print("PASS postgresql_runtime_is_dml_only")
    return 0


def verify_guard() -> int:
    assert engine.dialect.name == "postgresql", engine.dialect.name
    with engine.connect() as conn:
        _assert_runtime_boundary(conn)
        assert _current_revision(conn) == "20260903_01", _current_revision(conn)
        values = _quantity_map(conn)

    assert values[TARGETS[0][0]] == Decimal("0.41"), values
    assert values[TARGETS[1][0]] == Decimal("1.23"), values
    assert values[DECOYS[0][0]] == Decimal("0.40"), values
    assert values[DECOYS[1][0]] == Decimal("1.22"), values

    print("PASS historical_quantity_guard_preserves_user_edit_0_41")
    print("PASS historical_quantity_guard_preserves_user_edit_1_23")
    print("PASS historical_quantity_guard_remains_uuid_scoped")
    print("PASS historical_quantity_guard_reaches_20260903_01")
    print("PASS postgresql_runtime_is_dml_only")
    print("F5_HISTORICAL_QUANTITY_GUARD_GREEN")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=("seed-legacy", "verify-restored", "prepare-guard", "verify-guard"),
    )
    args = parser.parse_args()
    if args.mode == "seed-legacy":
        return seed_legacy()
    if args.mode == "verify-restored":
        return verify_restored()
    if args.mode == "prepare-guard":
        return prepare_guard()
    return verify_guard()


if __name__ == "__main__":
    raise SystemExit(main())
