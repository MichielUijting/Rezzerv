"""PostgreSQL integratietest voor kassabon -> voorraad -> Bijna op.

Deze test draait uitsluitend tegen een vooraf via Alembic gemigreerde PostgreSQL-
database. De functionele keten gebruikt daarna alleen DATABASE_URL (de runtime-
credential); MIGRATION_DATABASE_URL hoort tijdens deze stap niet beschikbaar te
zijn. Daarmee bewijst dezelfde 0 -> 2 -> 5 -> 5 -> 1-keten ook de DML-only
PostgreSQL-runtimegrens.
"""
from __future__ import annotations

import importlib
import os
import sys
import uuid
from pathlib import Path

from sqlalchemy import Boolean, Integer, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


HOUSEHOLD_ID = "0"


def _runtime_database_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required for the PostgreSQL receipt chain")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "PostgreSQL receipt chain requires a PostgreSQL DATABASE_URL; "
            f"configured datastore={url.get_backend_name()!r}"
        )
    return url


def _load_production_module():
    _runtime_database_url()
    if str(os.getenv("MIGRATION_DATABASE_URL") or "").strip():
        raise RuntimeError(
            "MIGRATION_DATABASE_URL must be unavailable during the runtime chain proof"
        )
    return importlib.import_module("app.main")


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
        raise AssertionError(f"Geen bruikbare kolommen voor {table_name}")
    columns = ", ".join(selected)
    parameters = ", ".join(f":{key}" for key in selected)
    conn.execute(
        text(f"INSERT INTO {table_name} ({columns}) VALUES ({parameters})"),
        selected,
    )


def _seed_batch(main, *, batch_id: str, line_id: str, receipt_ref: str, quantity: int, ids: dict[str, str]) -> None:
    with main.engine.begin() as conn:
        _insert_row(
            conn,
            "purchase_import_batches",
            {
                "id": batch_id,
                "household_id": HOUSEHOLD_ID,
                "store_provider_id": ids["provider_id"],
                "connection_id": ids["connection_id"],
                "source_type": "receipt",
                "source_reference": receipt_ref,
                "import_status": "reviewed",
                "raw_payload": "{}",
            },
        )
        _insert_row(
            conn,
            "purchase_import_lines",
            {
                "id": line_id,
                "batch_id": batch_id,
                "external_line_ref": f"{receipt_ref}:1",
                "external_article_code": "8718265184886",
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
            },
        )


def _almost_out_state(main, household_article_id: str) -> dict:
    with main.engine.begin() as conn:
        article_row = main.get_household_article_row_by_id(
            conn, HOUSEHOLD_ID, household_article_id
        )
        assert article_row is not None, "Huishoudartikel ontbreekt voor Bijna-op-evaluatie"
        evaluation = main.evaluate_household_article_almost_out(
            conn, HOUSEHOLD_ID, article_row
        )
        items = main.build_almost_out_items(conn, HOUSEHOLD_ID)
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
                "SELECT id FROM inventory WHERE household_id = :household_id "
                "AND household_article_id = :article_id LIMIT 1"
            ),
            {
                "household_id": HOUSEHOLD_ID,
                "article_id": ids["household_article_id"],
            },
        ).mappings().first()
        assert inventory_row and inventory_row.get("id"), "Voorraadregel ontbreekt voor consume-event"
        conn.execute(
            text(
                "UPDATE inventory SET aantal = :quantity, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"quantity": quantity_after, "id": inventory_row["id"]},
        )
        _insert_row(
            conn,
            "inventory_events",
            {
                "id": f"chain-consume-{uuid.uuid4().hex}",
                "household_id": HOUSEHOLD_ID,
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
            },
        )


def _assert_runtime_create_denied(main) -> str:
    with main.engine.connect() as conn:
        runtime_user = str(conn.execute(text("SELECT current_user")).scalar_one())
    try:
        with main.engine.begin() as conn:
            conn.execute(text("CREATE TABLE receipt_chain_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_RECEIPT_CHAIN_RUNTIME_CREATE_DENIED_GREEN")
        return runtime_user
    raise AssertionError("Runtime role unexpectedly has CREATE privilege")


def run_production_chain() -> dict:
    main = _load_production_module()
    if main.engine.dialect.name != "postgresql":
        raise AssertionError(f"Unexpected runtime dialect: {main.engine.dialect.name}")

    runtime_user = _assert_runtime_create_denied(main)

    required_tables = {
        "households",
        "household_registry",
        "store_providers",
        "household_store_connections",
        "global_products",
        "product_inventory_groups",
        "product_group_memberships",
        "article_groups",
        "household_articles",
        "spaces",
        "sublocations",
        "purchase_import_batches",
        "purchase_import_lines",
        "inventory",
        "inventory_events",
    }
    actual_tables = set(inspect(main.engine).get_table_names())
    missing = required_tables - actual_tables
    assert not missing, f"Productieschema mist tabellen: {sorted(missing)}"

    ids = {
        "provider_id": "chain-provider",
        "connection_id": "chain-connection",
        "global_product_id": "chain-global-product",
        "product_type_id": "gpc:10005897",
        "article_group_id": "chain-article-group",
        "household_article_id": "chain-household-article",
        "space_id": "chain-space",
        "sublocation_id": "chain-sublocation",
    }

    with main.engine.begin() as conn:
        _insert_row(
            conn,
            "household_registry",
            {"id": HOUSEHOLD_ID, "naam": "Kassabonketentest huishouden 0"},
        )
        _insert_row(
            conn,
            "households",
            {"id": HOUSEHOLD_ID, "naam": "Kassabonketentest huishouden 0"},
        )
        provider = main.ensure_receipt_unpack_provider(conn)
        ids["provider_id"] = str(provider["id"])
        _insert_row(
            conn,
            "household_store_connections",
            {
                "id": ids["connection_id"],
                "household_id": HOUSEHOLD_ID,
                "store_provider_id": ids["provider_id"],
                "connection_status": "active",
            },
        )
        _insert_row(
            conn,
            "global_products",
            {
                "id": ids["global_product_id"],
                "name": "AH BANANEN",
                "primary_gtin": "8718265184886",
                "barcode": "8718265184886",
                "brand": "Albert Heijn",
                "source": "test",
                "status": "active",
            },
        )
        _insert_row(
            conn,
            "product_inventory_groups",
            {
                "inventory_group_key": ids["product_type_id"],
                "display_name": "Bananen (Cavendish)",
                "default_base_unit": "stuk",
                "aggregation_mode": "sum_quantity",
                "active": True,
                "gpc_brick_code": "10005897",
                "source": "gs1_gpc_2026_05_en",
            },
        )
        _insert_row(
            conn,
            "product_group_memberships",
            {
                "id": "chain-product-type-membership",
                "global_product_id": ids["global_product_id"],
                "inventory_group_key": ids["product_type_id"],
                "comparison_group_key": ids["product_type_id"],
                "confidence": 1.0,
                "source": "receipt-inventory-production-chain",
                "confirmed_by_user": True,
                "active": True,
            },
        )
        _insert_row(
            conn,
            "article_groups",
            {
                "id": ids["article_group_id"],
                "household_id": HOUSEHOLD_ID,
                "name": "Fruit",
                "normalized_name": "fruit",
                "status": "active",
                "sort_order": 1,
            },
        )
        _insert_row(
            conn,
            "household_articles",
            {
                "id": ids["household_article_id"],
                "household_id": HOUSEHOLD_ID,
                "global_product_id": ids["global_product_id"],
                "naam": "AH BANANEN",
                "name": "AH BANANEN",
                "custom_name": "AH BANANEN",
                "article_group_id": ids["article_group_id"],
                "status": "active",
                "active": True,
                "consumable": True,
                "min_stock": 2,
                "ideal_stock": 3,
            },
        )
        if "product_identities" in actual_tables:
            _insert_row(
                conn,
                "product_identities",
                {
                    "id": "chain-product-gtin-identity",
                    "household_article_id": ids["household_article_id"],
                    "global_product_id": ids["global_product_id"],
                    "identity_type": "gtin",
                    "identity_value": "8718265184886",
                    "is_primary": True,
                    "source": "receipt-inventory-production-chain",
                },
            )
        _insert_row(
            conn,
            "spaces",
            {
                "id": ids["space_id"],
                "household_id": HOUSEHOLD_ID,
                "naam": "Keuken",
                "active": True,
            },
        )
        _insert_row(
            conn,
            "sublocations",
            {
                "id": ids["sublocation_id"],
                "space_id": ids["space_id"],
                "household_id": HOUSEHOLD_ID,
                "naam": "Fruitschaal",
                "active": True,
            },
        )

    _seed_batch(
        main,
        batch_id="chain-batch-1",
        line_id="chain-line-1",
        receipt_ref="receipt:chain-1",
        quantity=2,
        ids=ids,
    )
    _seed_batch(
        main,
        batch_id="chain-batch-2",
        line_id="chain-line-2",
        receipt_ref="receipt:chain-2",
        quantity=3,
        ids=ids,
    )

    main.require_household_context = lambda authorization=None, requested_household_id=None: {
        "active_household_id": str(requested_household_id or HOUSEHOLD_ID),
        "display_role": "admin",
    }
    payload = main.ProcessBatchRequest(processed_by="integration-test", mode="selected_only")

    first = main.process_purchase_import_batch(
        "chain-batch-1", payload, authorization="Bearer test"
    )
    with main.engine.begin() as conn:
        quantity_after_first = int(
            conn.execute(
                text(
                    "SELECT COALESCE(SUM(aantal), 0) FROM inventory "
                    "WHERE household_id = :household_id"
                ),
                {"household_id": HOUSEHOLD_ID},
            ).scalar()
            or 0
        )

    second = main.process_purchase_import_batch(
        "chain-batch-2", payload, authorization="Bearer test"
    )
    with main.engine.begin() as conn:
        quantity_after_second = int(
            conn.execute(
                text(
                    "SELECT COALESCE(SUM(aantal), 0) FROM inventory "
                    "WHERE household_id = :household_id"
                ),
                {"household_id": HOUSEHOLD_ID},
            ).scalar()
            or 0
        )
        event_count_after_second = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM inventory_events "
                    "WHERE household_id = :household_id AND event_type = 'purchase'"
                ),
                {"household_id": HOUSEHOLD_ID},
            ).scalar()
            or 0
        )
        household_link_count = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM household_articles "
                    "WHERE household_id = :household_id "
                    "AND global_product_id = :global_product_id"
                ),
                {
                    "household_id": HOUSEHOLD_ID,
                    "global_product_id": ids["global_product_id"],
                },
            ).scalar()
            or 0
        )
        product_type_count = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM product_group_memberships "
                    "WHERE global_product_id = :global_product_id"
                ),
                {"global_product_id": ids["global_product_id"]},
            ).scalar()
            or 0
        )

    repeated = main.process_purchase_import_batch(
        "chain-batch-2", payload, authorization="Bearer test"
    )
    with main.engine.begin() as conn:
        quantity_after_repeat = int(
            conn.execute(
                text(
                    "SELECT COALESCE(SUM(aantal), 0) FROM inventory "
                    "WHERE household_id = :household_id"
                ),
                {"household_id": HOUSEHOLD_ID},
            ).scalar()
            or 0
        )
        event_count_after_repeat = int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM inventory_events "
                    "WHERE household_id = :household_id AND event_type = 'purchase'"
                ),
                {"household_id": HOUSEHOLD_ID},
            ).scalar()
            or 0
        )

    from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded

    physical_line_is_excluded = is_spaarzegels_flow_excluded(
        {
            "receipt_line_text": "AH BANANEN",
            "quantity": 3,
            "unit_price": "1.00",
            "line_total": "3.00",
        }
    )
    loyalty_line_is_excluded = is_spaarzegels_flow_excluded(
        {
            "receipt_line_text": "KOOPZEGELS",
            "raw_label": "KOOPZEGELS",
            "quantity": 2,
            "unit_price": "0.10",
            "line_total": "0.20",
            "price": "0.20",
        }
    )

    almost_out_after_purchase = _almost_out_state(
        main, ids["household_article_id"]
    )
    _apply_consume_event(
        main, ids, quantity_before=5, quantity_after=1
    )
    almost_out_after_consume = _almost_out_state(
        main, ids["household_article_id"]
    )

    assert first["processed_count"] == 1
    assert quantity_after_first == 2
    assert second["processed_count"] == 1
    assert quantity_after_second == 5
    assert event_count_after_second == 2
    assert repeated["processed_count"] == 1
    assert quantity_after_repeat == 5
    assert event_count_after_repeat == 2
    assert household_link_count == 1
    assert product_type_count == 1
    assert physical_line_is_excluded is False
    assert loyalty_line_is_excluded is True
    assert almost_out_after_purchase["quantity"] == 5
    assert almost_out_after_purchase["included"] is False
    assert almost_out_after_consume["quantity"] == 1
    assert almost_out_after_consume["included"] is True

    return {
        "status": "passed",
        "datastore": "postgresql",
        "runtime_user": runtime_user,
        "migration_credential_available": False,
        "household_id": HOUSEHOLD_ID,
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
        print("POSTGRESQL_RECEIPT_INVENTORY_ALMOST_OUT_CHAIN_GREEN")
    except Exception as exc:
        print(f"POSTGRESQL_PRODUCTION_CHAIN_FAILURE|{exc.__class__.__name__}|{exc}")
        raise SystemExit(1)
