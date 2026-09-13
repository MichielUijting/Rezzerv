"""PO acceptance regression: Wat Inhuis approves Kassa receipts directly into inventory."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.household_product_configuration_service import save_wat_inhuis_configuration
from app.services.receipt_direct_inventory_approval_patch import (
    should_process_approved_receipt_directly_to_inventory,
)
from app.testing.postgresql_onboarding_selftest_fixture import create_postgresql_runtime_test_engine
from tests.kassa_review_api_selftest import (
    TARGET_ADMIN_EMAIL,
    TARGET_HOUSEHOLD,
    _headers,
    _prepare_database,
    _seed_receipt,
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
            assert configuration.location_tracking_level == "none"

        receipt = _seed_receipt(
            engine,
            fixture_name="normal_physical",
            seed_key="wat-inhuis-direct",
        )

        from app import main as main_module

        main_module.engine = engine
        assert should_process_approved_receipt_directly_to_inventory(configuration) is True
        assert should_process_approved_receipt_directly_to_inventory(
            SimpleNamespace(
                receipt_processing_enabled=True,
                simple_inventory_enabled=True,
                unpacking_enabled=True,
                location_tracking_level="exact",
            )
        ) is False

        headers = _headers(TARGET_ADMIN_EMAIL)
        with engine.begin() as conn:
            before_events = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM inventory_events "
                        "WHERE household_id = :household_id"
                    ),
                    {"household_id": TARGET_HOUSEHOLD},
                ).scalar_one()
            )

        with TestClient(main_module.app) as client:
            def reimport_identical():
                response = client.post(
                    '/api/receipts/import',
                    data={'household_id': TARGET_HOUSEHOLD},
                    files={'file': ('duplicate.pdf', b'f3-04:wat-inhuis-direct', 'application/pdf')},
                    headers=headers,
                )
                assert response.status_code == 200, response.text
                assert response.json()['duplicate'] is True, response.text
                assert response.json()['receipt_table_id'] == receipt['receipt_table_id']
                detail = client.get(
                    f"/api/receipts/{receipt['receipt_table_id']}", headers=headers,
                )
                assert detail.status_code == 200, detail.text
                return detail.json()

            active_duplicate = reimport_identical()
            assert active_duplicate['approved_at'] is None
            assert active_duplicate['import_status'] is None
            first = client.post(
                f"/api/receipts/{receipt['receipt_table_id']}/approve",
                headers=headers,
            )
            assert first.status_code == 200, first.text
            first_payload = first.json()
            assert first_payload["approval_destination"] == "inventory", first_payload
            processing = first_payload.get("inventory_processing") or {}
            assert int(processing.get("processed_count") or 0) > 0, processing
            assert int(processing.get("failed_count") or 0) == 0, processing
            assert int(processing.get("skipped_count") or 0) == 0, processing

            with engine.begin() as conn:
                after_first_events = int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM inventory_events "
                            "WHERE household_id = :household_id"
                        ),
                        {"household_id": TARGET_HOUSEHOLD},
                    ).scalar_one()
                )
                assert after_first_events > before_events
                batch = conn.execute(
                    text(
                        "SELECT id, import_status FROM purchase_import_batches "
                        "WHERE household_id = :household_id "
                        "AND source_type = 'receipt' AND source_reference = :source_reference "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {
                        "household_id": TARGET_HOUSEHOLD,
                        "source_reference": f"receipt:{receipt['receipt_table_id']}",
                    },
                ).mappings().one()
                line_states = conn.execute(
                    text(
                        "SELECT review_decision, processing_status, matched_household_article_id "
                        "FROM purchase_import_lines WHERE batch_id = :batch_id"
                    ),
                    {"batch_id": str(batch["id"])},
                ).mappings().all()
                assert line_states
                assert all(row["review_decision"] == "selected" for row in line_states)
                assert all(row["processing_status"] == "processed" for row in line_states)
                assert all(row["matched_household_article_id"] for row in line_states)

            processed_duplicate = reimport_identical()
            assert processed_duplicate['approved_at']
            assert processed_duplicate['import_status'] == 'processed'
            with engine.begin() as conn:
                assert int(conn.execute(text(
                    'SELECT COUNT(*) FROM inventory_events WHERE household_id = :household_id'
                ), {'household_id': TARGET_HOUSEHOLD}).scalar_one()) == after_first_events

            second = client.post(
                f"/api/receipts/{receipt['receipt_table_id']}/approve",
                headers=headers,
            )
            assert second.status_code == 200, second.text
            assert second.json()["approval_destination"] == "inventory"

            with engine.begin() as conn:
                after_second_events = int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM inventory_events "
                            "WHERE household_id = :household_id"
                        ),
                        {"household_id": TARGET_HOUSEHOLD},
                    ).scalar_one()
                )
                assert after_second_events == after_first_events, (
                    after_first_events,
                    after_second_events,
                )

            manual_receipt = _seed_receipt(
                engine,
                fixture_name="normal_physical",
                seed_key="wat-inhuis-manual-article",
            )
            manual_article_name = "AH M GEHAKT HANDMATIG REGRESSIE"
            created = client.post(
                f"/api/receipts/{manual_receipt['receipt_table_id']}/lines",
                headers=headers,
                json={
                    "article_name": manual_article_name,
                    "quantity": 3,
                    "line_total": 4.99,
                    "is_validated": True,
                },
            )
            assert created.status_code == 200, created.text

            with engine.begin() as conn:
                manual_line = conn.execute(
                    text(
                        """
                        SELECT id, line_role, inventory_eligible,
                               COALESCE(corrected_quantity, quantity) AS effective_quantity,
                               COALESCE(corrected_unit, unit) AS effective_unit
                        FROM receipt_table_lines
                        WHERE receipt_table_id = :receipt_table_id
                          AND COALESCE(corrected_raw_label, raw_label) = :article_name
                          AND COALESCE(is_deleted, FALSE) = FALSE
                        ORDER BY line_index DESC, created_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "receipt_table_id": manual_receipt["receipt_table_id"],
                        "article_name": manual_article_name,
                    },
                ).mappings().one()
                assert manual_line["line_role"] == "product", manual_line
                assert bool(manual_line["inventory_eligible"]) is True, manual_line
                assert float(manual_line["effective_quantity"] or 0) == 3.0, manual_line
                assert manual_line["effective_unit"] == "stuk", manual_line
                manual_line_id = str(manual_line["id"])

            manual_approval = client.post(
                f"/api/receipts/{manual_receipt['receipt_table_id']}/approve",
                headers=headers,
            )
            assert manual_approval.status_code == 200, manual_approval.text
            manual_payload = manual_approval.json()
            assert manual_payload["approval_destination"] == "inventory", manual_payload
            manual_processing = manual_payload.get("inventory_processing") or {}
            assert int(manual_processing.get("failed_count") or 0) == 0, manual_processing
            assert int(manual_processing.get("skipped_count") or 0) == 0, manual_processing

            with engine.begin() as conn:
                manual_import_line = conn.execute(
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
                        "source_reference": f"receipt:{manual_receipt['receipt_table_id']}",
                        "external_line_ref": f"receipt-line:{manual_line_id}",
                    },
                ).mappings().one()
                assert float(manual_import_line["quantity_raw"] or 0) == 3.0, manual_import_line
                assert manual_import_line["unit_raw"] == "stuk", manual_import_line
                assert manual_import_line["processing_status"] == "processed", manual_import_line
                assert manual_import_line["matched_household_article_id"], manual_import_line
                assert manual_import_line["processed_event_id"], manual_import_line

                manual_article_id = str(manual_import_line["matched_household_article_id"])
                inventory_row = conn.execute(
                    text(
                        """
                        SELECT naam, aantal
                        FROM inventory
                        WHERE household_id = :household_id
                          AND household_article_id = :article_id
                          AND COALESCE(status, 'active') = 'active'
                        LIMIT 1
                        """
                    ),
                    {
                        "household_id": TARGET_HOUSEHOLD,
                        "article_id": manual_article_id,
                    },
                ).mappings().one()
                assert inventory_row["naam"] == manual_article_name, inventory_row
                assert float(inventory_row["aantal"] or 0) == 3.0, inventory_row

                purchase_event = conn.execute(
                    text(
                        """
                        SELECT event_type, quantity, source_reference, source_line_id
                        FROM inventory_events
                        WHERE household_id = :household_id
                          AND household_article_id = :article_id
                          AND source_reference = :source_reference
                          AND source_line_id = :source_line_id
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "household_id": TARGET_HOUSEHOLD,
                        "article_id": manual_article_id,
                        "source_reference": f"receipt:{manual_receipt['receipt_table_id']}",
                        "source_line_id": str(manual_import_line["id"]),
                    },
                ).mappings().one()
                assert purchase_event["event_type"] == "purchase", purchase_event
                assert float(purchase_event["quantity"] or 0) == 3.0, purchase_event

        print("PASS wat_inhuis_kassa_approval_routes_directly_to_inventory")
        print("PASS direct_inventory_approval_is_idempotent")
        print("PASS active_and_processed_reimport_preserve_identity_and_inventory_events")
        print("PASS unpacking_enabled_configuration_keeps_unpacking_boundary")
        print("PASS manual_kassa_article_is_product_and_reaches_inventory")
        print("WAT_INHUIS_KASSA_DIRECT_INVENTORY_POSTGRESQL_GREEN")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run())
