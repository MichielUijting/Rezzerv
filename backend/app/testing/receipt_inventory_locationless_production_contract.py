"""Production contract for ready-only receipt processing without locations.

This contract boots the real ``app.main`` against a temporary SQLite database,
waits for the normal runtime patch registration, configures one household with
``location_tracking_level='none'`` and processes one selected receipt line through
the registered ``ready_only`` production endpoint.

The acceptance invariant is deliberately strict: no synthetic location may be
created or persisted. The resulting inventory identity, inventory event and import
line all keep the location columns NULL.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from sqlalchemy import text

from app.testing.receipt_inventory_production_chain import (
    _initialize_production_schema,
    _insert_row,
    _load_production_module,
)


def _wait_for_location_policy_patch(main) -> None:
    for _ in range(100):
        if getattr(
            main.app.state,
            "purchase_import_location_policy_patch_installed",
            False,
        ):
            return
        time.sleep(0.02)
    raise AssertionError(
        "Purchase-import locatiepolicy is niet via de normale app-startup geïnstalleerd"
    )


def run_locationless_production_contract() -> dict:
    with tempfile.TemporaryDirectory(prefix="rezzerv_locationless_receipt_") as tmp_dir:
        database_path = Path(tmp_dir) / "rezzerv-locationless.sqlite"
        main = _load_production_module(database_path)
        _initialize_production_schema(main)
        _wait_for_location_policy_patch(main)

        from app.services.household_product_configuration_service import (
            save_inhuis_halen_configuration,
        )

        ids = {
            "household_id": "locationless-household",
            "connection_id": "locationless-connection",
            "article_group_id": "locationless-article-group",
            "household_article_id": "locationless-household-article",
            "batch_id": "locationless-batch",
            "line_id": "locationless-line",
        }

        with main.engine.begin() as conn:
            provider = main.ensure_receipt_unpack_provider(conn)
            provider_id = str(provider["id"])

            save_inhuis_halen_configuration(
                conn,
                household_id=ids["household_id"],
                simple_inventory_enabled=True,
                almost_out_notifications_enabled=False,
                receipt_processing_enabled=True,
                recipes_enabled=False,
            )

            _insert_row(
                conn,
                "household_store_connections",
                {
                    "id": ids["connection_id"],
                    "household_id": ids["household_id"],
                    "store_provider_id": provider_id,
                    "connection_status": "active",
                },
            )
            _insert_row(
                conn,
                "article_groups",
                {
                    "id": ids["article_group_id"],
                    "household_id": ids["household_id"],
                    "name": "Voorraad",
                    "normalized_name": "voorraad",
                    "status": "active",
                    "sort_order": 1,
                },
            )
            _insert_row(
                conn,
                "household_articles",
                {
                    "id": ids["household_article_id"],
                    "household_id": ids["household_id"],
                    "naam": "LOCATI ELOZE RIJST",
                    "name": "LOCATI ELOZE RIJST",
                    "custom_name": "LOCATI ELOZE RIJST",
                    "article_group_id": ids["article_group_id"],
                    "status": "active",
                    "active": 1,
                    "consumable": 1,
                    "min_stock": 0,
                    "ideal_stock": 2,
                },
            )
            _insert_row(
                conn,
                "purchase_import_batches",
                {
                    "id": ids["batch_id"],
                    "household_id": ids["household_id"],
                    "store_provider_id": provider_id,
                    "connection_id": ids["connection_id"],
                    "source_type": "receipt",
                    "source_reference": "receipt:locationless-contract",
                    "import_status": "reviewed",
                    "raw_payload": "{}",
                },
            )
            _insert_row(
                conn,
                "purchase_import_lines",
                {
                    "id": ids["line_id"],
                    "batch_id": ids["batch_id"],
                    "external_line_ref": "receipt-line:locationless-contract:1",
                    "article_name_raw": "LOCATI ELOZE RIJST",
                    "quantity_raw": 4,
                    "unit_raw": "stuk",
                    "review_decision": "selected",
                    "match_status": "matched",
                    "matched_household_article_id": ids["household_article_id"],
                    "selected_article_group_id": ids["article_group_id"],
                    "target_location_id": None,
                    "processing_status": "pending",
                    "ui_sort_order": 1,
                },
            )

        main.require_household_context = (
            lambda authorization=None, requested_household_id=None: {
                "active_household_id": str(
                    requested_household_id or ids["household_id"]
                ),
                "display_role": "admin",
                "user_id": "locationless-contract-user",
            }
        )
        payload = main.ProcessBatchRequest(
            processed_by="locationless-production-contract",
            mode="ready_only",
        )
        result = main.process_purchase_import_batch(
            ids["batch_id"],
            payload,
            authorization="Bearer locationless-contract",
        )

        with main.engine.begin() as conn:
            inventory_rows = conn.execute(
                text(
                    """
                    SELECT id, aantal, space_id, sublocation_id
                    FROM inventory
                    WHERE household_id = :household_id
                      AND household_article_id = :household_article_id
                      AND COALESCE(status, 'active') = 'active'
                    """
                ),
                {
                    "household_id": ids["household_id"],
                    "household_article_id": ids["household_article_id"],
                },
            ).mappings().all()
            line = conn.execute(
                text(
                    """
                    SELECT processing_status, processed_event_id, final_location_id,
                           target_location_id
                    FROM purchase_import_lines
                    WHERE id = :line_id
                    LIMIT 1
                    """
                ),
                {"line_id": ids["line_id"]},
            ).mappings().one()
            purchase_events = conn.execute(
                text(
                    """
                    SELECT id, location_id, location_label, quantity
                    FROM inventory_events
                    WHERE household_id = :household_id
                      AND household_article_id = :household_article_id
                      AND lower(COALESCE(event_type, '')) = 'purchase'
                    """
                ),
                {
                    "household_id": ids["household_id"],
                    "household_article_id": ids["household_article_id"],
                },
            ).mappings().all()
            location_count = int(
                conn.execute(
                    text(
                        "SELECT COUNT(*) FROM spaces WHERE household_id = :household_id"
                    ),
                    {"household_id": ids["household_id"]},
                ).scalar()
                or 0
            )

        assert result["processed_count"] == 1, result
        assert result["failed_count"] == 0, result
        assert result["skipped_count"] == 0, result
        assert len(inventory_rows) == 1, inventory_rows
        assert int(inventory_rows[0]["aantal"] or 0) == 4, inventory_rows[0]
        assert inventory_rows[0]["space_id"] is None, inventory_rows[0]
        assert inventory_rows[0]["sublocation_id"] is None, inventory_rows[0]
        assert line["processing_status"] == "processed", line
        assert line["target_location_id"] is None, line
        assert line["final_location_id"] is None, line
        assert line["processed_event_id"], line
        assert len(purchase_events) == 1, purchase_events
        assert purchase_events[0]["location_id"] is None, purchase_events[0]
        assert not str(purchase_events[0]["location_label"] or "").strip(), purchase_events[0]
        assert location_count == 0, "Er is onverwacht een synthetische locatie aangemaakt"

        return {
            "status": "passed",
            "household_id": ids["household_id"],
            "mode": "ready_only",
            "processed_count": result["processed_count"],
            "inventory_quantity": int(inventory_rows[0]["aantal"] or 0),
            "space_id": inventory_rows[0]["space_id"],
            "sublocation_id": inventory_rows[0]["sublocation_id"],
            "final_location_id": line["final_location_id"],
            "purchase_event_location_id": purchase_events[0]["location_id"],
            "synthetic_location_count": location_count,
            "runtime_patch_installed": True,
        }


if __name__ == "__main__":
    report = run_locationless_production_contract()
    print(report)
    print("LOCATIONLESS_RECEIPT_READY_ONLY_PRODUCTION_GREEN")
