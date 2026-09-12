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

        print("PASS wat_inhuis_kassa_approval_routes_directly_to_inventory")
        print("PASS direct_inventory_approval_is_idempotent")
        print("PASS unpacking_enabled_configuration_keeps_unpacking_boundary")
        print("WAT_INHUIS_KASSA_DIRECT_INVENTORY_POSTGRESQL_GREEN")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run())
