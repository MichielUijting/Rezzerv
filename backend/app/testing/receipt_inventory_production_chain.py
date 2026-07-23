"""Integratietest voor de echte Rezzerv-keten Uitpakken -> Voorraad -> Bijna op.

De test gebruikt huishouden 0 in een tijdelijke SQLite-runtime, initialiseert het
bestaande productieschema en roept rechtstreeks de productie-verwerking aan.
Naast voorraad en idempotentie worden ook productkoppeling, producttype,
spaartegoedclassificatie en de Bijna-op-drempel gecontroleerd.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import inspect, text


def _load_production_module(database_path: Path):
    os.environ["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    backend_root = Path(__file__).resolve().parents[2]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    for module_name in [name for name in list(sys.modules) if name == "app" or name.startswith("app.")]:
        del sys.modules[module_name]
    return importlib.import_module("app.main")


def _initialize_production_schema(main) -> None:
    schema_functions = [
        (name, value)
        for name, value in vars(main).items()
        if name.startswith("ensure_release_") and name.endswith("_schema") and callable(value)
    ]
    for _, function in sorted(schema_functions, key=lambda item: item[0]):
        function()

    from app.services.article_group_store import ensure_article_group_schema

    ensure_article_group_schema()

    if hasattr(main, "seed_store_providers"):
        main.seed_store_providers()


def _column_names(conn, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()}


def _insert_row(conn, table_name: str, values: dict) -> None:
    available = _column_names(conn, table_name)
    selected = {key: value for key, value in values.items() if key in available}
    if not selected:
        raise AssertionError(f"Geen bruikbare kolommen voor {table_name}")
    columns = ", ".join(selected)
    parameters = ", ".join(f":{key}" for key in selected)
    conn.execute(text(f"INSERT INTO {table_name} ({columns}) VALUES ({parameters})"), selected)


def _seed_batch(main, *, batch_id: str, line_id: str, receipt_ref: str, quantity: int, ids: dict[str, str]) -> None:
    with main.engine.begin() as conn:
        _insert_row(conn, "purchase_import_batches", {
            "id": batch_id,
            "household_id": "0",
            "store_provider_id": ids["provider_id"],
            "connection_id": ids["connection_id"],
            "source_type": "receipt",
            "source_reference": receipt_ref,
            "import_status": "reviewed",
            "raw_payload": "{}",
        })
        _insert_row(conn, "purchase_import_lines", {
            "id": line_id,
            "batch_id": batch_id,
            "external_line_ref": f"{receipt_ref}:1",
            "external_article_code": "8710000091001",
            "article_name_raw": "AH BANANEN",
            "brand_raw": "Albert Heijn",
            "quantity_raw": quantity,
            "unit_raw": "stuk",
            "line_price_raw": float(quantity),
            "currency_code": "EUR",
            "match_status": "matched",
            "review_decision": "selected",
            "matched_global_product_id": ids["global_product_id"],
            "matched_household_article_id": ids["household_article_id"],
            "target_location_id": ids["sublocation_id"],
            "processing_status": "pending",
            "ui_sort_order": 1,
        })


def _almost_out_state(main, household_article_id: str) -> dict:
    with main.engine.begin() as conn:
        article_row = main.get_household_article_row_by_id(conn, "0", household_article_id)
        assert article_row is not None, "Huishoudartikel ontbreekt voor Bijna-op-evaluatie"
        evaluation = main.evaluate_household_article_almost_out(conn, "0", article_row)
        items = main.build_almost_out_items(conn, "0")
    item_ids = {str(item.get("household_article_id") or "") for item in items}
    included = bool(evaluation.get("include_in_almost_out")) and household_article_id in item_ids
    return {
        "included": included,
        "quantity": float(evaluation.get("current_quantity") or 0),
        "data_state": str(evaluation.get("data_state") or ""),
    }


def _apply_consume_event(main, ids: dict[str, str], *, quantity_before: int, quantity_after: int) -> None:
    delta = quantity_after - quantity_before
    with main.engine.begin() as conn:
        inventory_row = conn.execute(
            text(
                "SELECT id FROM inventory WHERE household_id = '0' "
                "AND household_article_id = :article_id LIMIT 1"
            ),
            {"article_id": ids["household_article_id"]},
        ).mappings().first()
        assert inventory_row and inventory_row.get("id"), "Voorraadregel ontbreekt voor consume-event"
        conn.execute(
            text("UPDATE inventory SET aantal = :quantity, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
            {"quantity": quantity_after, "id": inventory_row["id"]},
        )
        _insert_row(conn, "inventory_events", {
            "id": f"chain-consume-{uuid.uuid4().hex}",
            "household_id": "0",
            "inventory_id": str(inventory_row["id"]),
            "article_id": ids["household_article_id"],
            "household_article_id": ids["household_article_id"],
            "article_name": "AH BANANEN",
            "location_id": ids["sublocation_id"],
            "location_label": "Keuken / Fruitschaal",
            "event_type": "consume",
            "quantity": delta,
            "old_quantity": quantity_before,
            "new_quantity": quantity_after,
            "source": "chain_test",
            "note": "[receipt-inventory-chain] Bijna-op-drempel",
        })


def run_production_chain() -> dict:
    with tempfile.TemporaryDirectory(prefix="rezzerv_production_chain_") as tmp_dir:
        database_path = Path(tmp_dir) / "rezzerv-chain.sqlite"
        main = _load_production_module(database_path)
        _initialize_production_schema(main)

        required_tables = {
            "store_providers", "household_store_connections", "global_products",
            "article_groups", "household_articles", "spaces", "sublocations", "purchase_import_batches",
            "purchase_import_lines", "inventory", "inventory_events",
        }
        actual_tables = set(inspect(main.engine).get_table_names())
        missing = required_tables - actual_tables
        assert not missing, f"Productieschema mist tabellen: {sorted(missing)}"

        ids = {
            "provider_id": "chain-provider",
            "connection_id": "chain-connection",
            "global_product_id": "chain-global-product",
            "product_type_id": "chain-product-type",
            "article_group_id": "chain-article-group",
            "household_article_id": "chain-household-article",
            "space_id": "chain-space",
            "sublocation_id": "chain-sublocation",
        }

        with main.engine.begin() as conn:
            provider = main.ensure_receipt_unpack_provider(conn)
            ids["provider_id"] = str(provider["id"])
            _insert_row(conn, "household_store_connections", {
                "id": ids["connection_id"], "household_id": "0",
                "store_provider_id": ids["provider_id"], "connection_status": "active",
            })
            _insert_row(conn, "global_products", {
                "id": ids["global_product_id"], "name": "AH BANANEN",
                "primary_gtin": "8710000091001", "barcode": "8710000091001",
                "brand": "Albert Heijn", "source": "test", "status": "active",
            })
            if "product_inventory_groups" in actual_tables:
                _insert_row(conn, "product_inventory_groups", {
                    "id": ids["product_type_id"], "name": "Fruit", "active": 1,
                })
            if "product_group_memberships" in actual_tables:
                _insert_row(conn, "product_group_memberships", {
                    "global_product_id": ids["global_product_id"],
                    "product_inventory_group_id": ids["product_type_id"], "is_primary": 1,
                })
            _insert_row(conn, "article_groups", {
                "id": ids["article_group_id"],
                "household_id": "0",
                "name": "Fruit",
                "normalized_name": "fruit",
                "status": "active",
                "sort_order": 1,
            })
            _insert_row(conn, "household_articles", {
                "id": ids["household_article_id"], "household_id": "0",
                "global_product_id": ids["global_product_id"], "naam": "AH BANANEN",
                "name": "AH BANANEN", "custom_name": "AH BANANEN",
                "article_group_id": ids["article_group_id"], "status": "active",
                "active": 1, "consumable": 1, "min_stock": 2, "ideal_stock": 3,
            })
            _insert_row(conn, "spaces", {
                "id": ids["space_id"], "household_id": "0", "naam": "Keuken", "active": 1,
            })
            _insert_row(conn, "sublocations", {
                "id": ids["sublocation_id"], "space_id": ids["space_id"],
                "household_id": "0", "naam": "Fruitschaal", "active": 1,
            })

        _seed_batch(main, batch_id="chain-batch-1", line_id="chain-line-1", receipt_ref="receipt:chain-1", quantity=2, ids=ids)
        _seed_batch(main, batch_id="chain-batch-2", line_id="chain-line-2", receipt_ref="receipt:chain-2", quantity=3, ids=ids)

        main.require_household_context = lambda authorization=None, requested_household_id=None: {
            "active_household_id": str(requested_household_id or "0"), "display_role": "admin"
        }
        payload = main.ProcessBatchRequest(processed_by="integration-test", mode="selected_only")

        first = main.process_purchase_import_batch("chain-batch-1", payload, authorization="Bearer test")
        with main.engine.begin() as conn:
            quantity_after_first = int(conn.execute(text("SELECT COALESCE(SUM(aantal), 0) FROM inventory WHERE household_id = '0'")).scalar() or 0)
        second = main.process_purchase_import_batch("chain-batch-2", payload, authorization="Bearer test")
        with main.engine.begin() as conn:
            quantity_after_second = int(conn.execute(text("SELECT COALESCE(SUM(aantal), 0) FROM inventory WHERE household_id = '0'")).scalar() or 0)
            event_count_after_second = int(conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE household_id = '0' AND event_type = 'purchase'")).scalar() or 0)
            household_link_count = int(conn.execute(text("SELECT COUNT(*) FROM household_articles WHERE household_id = '0' AND global_product_id = :global_product_id"), {"global_product_id": ids["global_product_id"]}).scalar() or 0)
            product_type_count = 0
            if "product_group_memberships" in actual_tables:
                product_type_count = int(conn.execute(text("SELECT COUNT(*) FROM product_group_memberships WHERE global_product_id = :global_product_id"), {"global_product_id": ids["global_product_id"]}).scalar() or 0)
        repeated = main.process_purchase_import_batch("chain-batch-2", payload, authorization="Bearer test")
        with main.engine.begin() as conn:
            quantity_after_repeat = int(conn.execute(text("SELECT COALESCE(SUM(aantal), 0) FROM inventory WHERE household_id = '0'")).scalar() or 0)
            event_count_after_repeat = int(conn.execute(text("SELECT COUNT(*) FROM inventory_events WHERE household_id = '0' AND event_type = 'purchase'")).scalar() or 0)

        from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded

        physical_line_is_excluded = is_spaarzegels_flow_excluded({
            "receipt_line_text": "AH BANANEN", "quantity": 3, "unit_price": "1.00", "line_total": "3.00"
        })
        loyalty_line_is_excluded = is_spaarzegels_flow_excluded({
            "receipt_line_text": "KOOPZEGELS", "raw_label": "KOOPZEGELS", "quantity": 2,
            "unit_price": "0.10", "line_total": "0.20", "price": "0.20"
        })

        almost_out_after_purchase = _almost_out_state(main, ids["household_article_id"])
        _apply_consume_event(main, ids, quantity_before=5, quantity_after=1)
        almost_out_after_consume = _almost_out_state(main, ids["household_article_id"])

        assert first["processed_count"] == 1
        assert quantity_after_first == 2
        assert second["processed_count"] == 1
        assert quantity_after_second == 5
        assert event_count_after_second == 2
        assert repeated["processed_count"] == 1
        assert quantity_after_repeat == 5
        assert event_count_after_repeat == 2
        assert household_link_count == 1
        if "product_group_memberships" in actual_tables:
            assert product_type_count == 1
        assert physical_line_is_excluded is False
        assert loyalty_line_is_excluded is True
        assert almost_out_after_purchase["quantity"] == 5
        assert almost_out_after_purchase["included"] is False
        assert almost_out_after_consume["quantity"] == 1
        assert almost_out_after_consume["included"] is True

        return {
            "status": "passed",
            "household_id": "0",
            "inventory_path": [0, 2, 5, 5, 1],
            "purchase_event_path": [0, 1, 2, 2],
            "household_product_link_count": household_link_count,
            "product_type_link_count": product_type_count,
            "loyalty_excluded_from_physical_stock": loyalty_line_is_excluded,
            "almost_out_path": [False, True],
            "production_endpoint": True,
        }


if __name__ == "__main__":
    try:
        print(run_production_chain())
        print("RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN")
    except Exception as exc:
        print(f"PRODUCTION_CHAIN_FAILURE|{exc.__class__.__name__}|{exc}")
        raise SystemExit(1)
