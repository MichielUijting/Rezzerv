"""PostgreSQL proof for the temporary all-articles-consumable repurchase policy."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.household_product_configuration_service import save_wat_inhuis_configuration
from app.testing.postgresql_onboarding_selftest_fixture import create_postgresql_runtime_test_engine
from tests.kassa_review_api_selftest import (
    TARGET_ADMIN_EMAIL,
    TARGET_HOUSEHOLD,
    _headers,
    _prepare_database,
    _seed_receipt,
)


def _manual_line_id(conn, receipt_table_id: str, article_name: str) -> str:
    row = conn.execute(
        text(
            """
            SELECT id
            FROM receipt_table_lines
            WHERE receipt_table_id = :receipt_table_id
              AND COALESCE(corrected_raw_label, raw_label) = :article_name
              AND COALESCE(is_deleted, FALSE) = FALSE
            ORDER BY line_index DESC, created_at DESC, id DESC
            LIMIT 1
            """
        ),
        {
            "receipt_table_id": receipt_table_id,
            "article_name": article_name,
        },
    ).mappings().one()
    return str(row["id"])


def _import_line(conn, receipt_table_id: str, line_id: str):
    return conn.execute(
        text(
            """
            SELECT pil.id, pil.quantity_raw, pil.unit_raw,
                   pil.processing_status, pil.matched_household_article_id,
                   pil.processed_event_id
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            WHERE pib.household_id = :household_id
              AND pib.source_type = 'receipt'
              AND pib.source_reference = :source_reference
              AND pil.external_line_ref = :external_line_ref
            LIMIT 1
            """
        ),
        {
            "household_id": TARGET_HOUSEHOLD,
            "source_reference": f"receipt:{receipt_table_id}",
            "external_line_ref": f"receipt-line:{line_id}",
        },
    ).mappings().one()


def _inventory_total(conn, article_id: str) -> float:
    return float(
        conn.execute(
            text(
                """
                SELECT COALESCE(SUM(aantal), 0)
                FROM inventory
                WHERE household_id = :household_id
                  AND household_article_id = :article_id
                  AND COALESCE(status, 'active') = 'active'
                """
            ),
            {
                "household_id": TARGET_HOUSEHOLD,
                "article_id": article_id,
            },
        ).scalar_one()
        or 0
    )


def run() -> int:
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql"
        _prepare_database(engine)

        with engine.begin() as conn:
            configuration = save_wat_inhuis_configuration(
                conn,
                household_id=TARGET_HOUSEHOLD,
                inventory_tracking_level="quantity",
                global_locations_enabled=False,
                almost_out_enabled=True,
                shopping_enabled=False,
            )
            assert configuration.receipt_processing_enabled is True
            assert configuration.unpacking_enabled is False

        from app import main as main_module

        main_module.engine = engine
        headers = _headers(TARGET_ADMIN_EMAIL)
        article_name = "TIJDELIJK CONSUMABLE POSTGRESQL REGRESSIE"

        with TestClient(main_module.app) as client:
            first_receipt = _seed_receipt(
                engine,
                fixture_name="normal_physical",
                seed_key="temporary-consumable-stock-2",
            )
            first_created = client.post(
                f"/api/receipts/{first_receipt['receipt_table_id']}/lines",
                headers=headers,
                json={
                    "article_name": article_name,
                    "quantity": 2,
                    "line_total": 2.00,
                    "is_validated": True,
                },
            )
            assert first_created.status_code == 200, first_created.text

            with engine.begin() as conn:
                first_line_id = _manual_line_id(
                    conn,
                    first_receipt["receipt_table_id"],
                    article_name,
                )

            first_approval = client.post(
                f"/api/receipts/{first_receipt['receipt_table_id']}/approve",
                headers=headers,
            )
            assert first_approval.status_code == 200, first_approval.text
            assert first_approval.json()["approval_destination"] == "inventory"

            with engine.begin() as conn:
                first_import = _import_line(
                    conn,
                    first_receipt["receipt_table_id"],
                    first_line_id,
                )
                assert first_import["processing_status"] == "processed", first_import
                article_id = str(first_import["matched_household_article_id"])
                assert article_id
                assert float(first_import["quantity_raw"] or 0) == 2.0, first_import
                assert _inventory_total(conn, article_id) == 2.0

                conn.execute(
                    text(
                        """
                        UPDATE household_articles
                        SET consumable = FALSE,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :article_id
                          AND household_id = :household_id
                        """
                    ),
                    {
                        "article_id": article_id,
                        "household_id": TARGET_HOUSEHOLD,
                    },
                )
                main_module.set_household_auto_consume_mode(
                    conn,
                    TARGET_HOUSEHOLD,
                    main_module.ARTICLE_AUTO_CONSUME_ALL_EXISTING,
                )
                persisted_before = conn.execute(
                    text(
                        """
                        SELECT consumable
                        FROM household_articles
                        WHERE id = :article_id
                          AND household_id = :household_id
                        """
                    ),
                    {
                        "article_id": article_id,
                        "household_id": TARGET_HOUSEHOLD,
                    },
                ).scalar_one()
                assert bool(persisted_before) is False

                decision = main_module.determine_auto_consume_decision(
                    conn,
                    TARGET_HOUSEHOLD,
                    article_id,
                    article_name,
                    2,
                    10,
                )
                assert decision["effective_mode"] == main_module.ARTICLE_AUTO_CONSUME_ALL_EXISTING, decision
                assert int(decision["requested_deduction_quantity"] or 0) == 2, decision
                assert decision["should_auto_consume"] is True, decision

            second_receipt = _seed_receipt(
                engine,
                fixture_name="normal_physical",
                seed_key="temporary-consumable-repurchase-10",
            )
            second_created = client.post(
                f"/api/receipts/{second_receipt['receipt_table_id']}/lines",
                headers=headers,
                json={
                    "article_name": article_name,
                    "quantity": 10,
                    "line_total": 10.00,
                    "is_validated": True,
                },
            )
            assert second_created.status_code == 200, second_created.text

            with engine.begin() as conn:
                second_line_id = _manual_line_id(
                    conn,
                    second_receipt["receipt_table_id"],
                    article_name,
                )

            second_approval = client.post(
                f"/api/receipts/{second_receipt['receipt_table_id']}/approve",
                headers=headers,
            )
            assert second_approval.status_code == 200, second_approval.text
            assert second_approval.json()["approval_destination"] == "inventory"

            with engine.begin() as conn:
                second_import = _import_line(
                    conn,
                    second_receipt["receipt_table_id"],
                    second_line_id,
                )
                assert second_import["processing_status"] == "processed", second_import
                assert str(second_import["matched_household_article_id"]) == article_id, second_import
                assert float(second_import["quantity_raw"] or 0) == 10.0, second_import

                final_total = _inventory_total(conn, article_id)
                assert final_total == 10.0, final_total

                purchase_event = conn.execute(
                    text(
                        """
                        SELECT event_type, quantity
                        FROM inventory_events
                        WHERE id = :event_id
                          AND household_id = :household_id
                          AND household_article_id = :article_id
                        """
                    ),
                    {
                        "event_id": str(second_import["processed_event_id"]),
                        "household_id": TARGET_HOUSEHOLD,
                        "article_id": article_id,
                    },
                ).mappings().one()
                assert purchase_event["event_type"] == "purchase", purchase_event
                assert float(purchase_event["quantity"] or 0) == 10.0, purchase_event

                auto_event = conn.execute(
                    text(
                        """
                        SELECT event_type, quantity
                        FROM inventory_events
                        WHERE household_id = :household_id
                          AND household_article_id = :article_id
                          AND event_type = 'auto_repurchase'
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "household_id": TARGET_HOUSEHOLD,
                        "article_id": article_id,
                    },
                ).mappings().one()
                assert float(auto_event["quantity"] or 0) == -2.0, auto_event

                persisted_after = conn.execute(
                    text(
                        """
                        SELECT consumable
                        FROM household_articles
                        WHERE id = :article_id
                          AND household_id = :household_id
                        """
                    ),
                    {
                        "article_id": article_id,
                        "household_id": TARGET_HOUSEHOLD,
                    },
                ).scalar_one()
                assert bool(persisted_after) is False

        print("PASS temporary_policy_keeps_persistent_consumable_false")
        print("PASS existing_2_is_auto_consumed_before_repurchase_10")
        print("PASS repurchase_finishes_with_inventory_10")
        print("TEMPORARY_ALL_ARTICLES_CONSUMABLE_POSTGRESQL_GREEN")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run())
