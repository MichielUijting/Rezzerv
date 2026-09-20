from __future__ import annotations

import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api import catalog_routes
from app.db import engine
from app.services.external_database_off_index_matchers import match_retailer_receipt_line
from app.services.external_article_confirmation_service import _candidate_identity
from app.services.external_article_ui_projection import (
    _central_product_details,
    project_central_link_truth,
)
from app.services.external_article_product_link_service import (
    _complete_global_product_link_data,
    save_external_article_product_link,
)
from app.services.external_product_candidate_store import (
    _m2c2l_enrich_linked_receipt_items,
    ensure_external_product_candidates_schema,
    list_external_receipt_items,
)
from app.services.external_product_index_store import ensure_external_product_index_seeded
from app.services.gpc_local_catalog_service import classify_gpc_product
from app.services.off_product_link_service import (
    _upsert_global_product,
    link_off_product_with_product_type,
)
from app.services.off_search_service import _normalize_result, _resolve_receipt_table_line
from app.services.product_inventory_group_store import (
    link_global_product_to_inventory_group_with_connection,
)

GTIN_ALPHA = "8712345678901"
GTIN_BRAVO = "8712345678902"
GTIN_CHARLIE = "8712345678903"
NAME_ALPHA = "postgresql catalog off proof alpha"
NAME_BRAVO = "PostgreSQL Catalog OFF Proof Bravo"
NAME_CHARLIE = "PostgreSQL Global OFF Scope Proof"
NAME_FILTER = "postgresql catalog off proof"
ALEMBIC_HEAD = "20260919_01"
TEST_GROUP_KEY = "__postgresql_catalog_off_membership_group__"
OFFICIAL_GPC_GROUP_KEY = "gpc:99999999"
OFFICIAL_GPC_BRICK_CODE = "99999999"
EXTERNAL_LINK_CONFIRMED_BY = "postgresql_catalog_off_request_dml_only_selftest"
GLOBAL_SCOPE_PROVIDER_ID = "__postgresql_global_scope_provider__"
GLOBAL_SCOPE_CONNECTION_ID = "__postgresql_global_scope_connection__"
GLOBAL_SCOPE_BATCH_ID = "__postgresql_global_scope_batch__"
GLOBAL_SCOPE_LINE_ID = "__postgresql_global_scope_line__"
GLOBAL_SCOPE_HOUSEHOLD_ARTICLE_ID = "__postgresql_global_scope_household_article__"
GLOBAL_SCOPE_HOUSEHOLD_ID = "__postgresql_global_scope_household__"
GLOBAL_SCOPE_CANDIDATE_ID = "__postgresql_global_scope_candidate__"
GLOBAL_SCOPE_RECEIPT_TEXT = "AH BOUILLON GLOBAL SCOPE PROOF"
GLOBAL_SCOPE_RETAILER = "albert-heijn"
GLOBAL_SCOPE_LEGACY_PRODUCT_ID = "__legacy_household_only_product__"


def _assert_runtime_create_denied() -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE catalog_off_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_CATALOG_OFF_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a catalog/OFF schema object")


def _cleanup(conn) -> None:
    conn.execute(
        text(
            "DELETE FROM external_product_candidates "
            "WHERE id = :candidate_id"
        ),
        {"candidate_id": GLOBAL_SCOPE_CANDIDATE_ID},
    )
    conn.execute(
        text(
            "DELETE FROM external_article_product_links "
            "WHERE retailer_code = :retailer_code "
            "AND receipt_text_normalized = :receipt_text_normalized"
        ),
        {
            "retailer_code": GLOBAL_SCOPE_RETAILER,
            "receipt_text_normalized": GLOBAL_SCOPE_RECEIPT_TEXT.lower(),
        },
    )
    conn.execute(
        text("DELETE FROM purchase_import_lines WHERE id = :id"),
        {"id": GLOBAL_SCOPE_LINE_ID},
    )
    conn.execute(
        text("DELETE FROM purchase_import_batches WHERE id = :id"),
        {"id": GLOBAL_SCOPE_BATCH_ID},
    )
    conn.execute(
        text("DELETE FROM household_store_connections WHERE id = :id"),
        {"id": GLOBAL_SCOPE_CONNECTION_ID},
    )
    conn.execute(
        text("DELETE FROM store_providers WHERE id = :id"),
        {"id": GLOBAL_SCOPE_PROVIDER_ID},
    )
    conn.execute(
        text("DELETE FROM household_articles WHERE id = :id"),
        {"id": GLOBAL_SCOPE_HOUSEHOLD_ARTICLE_ID},
    )
    conn.execute(
        text(
            "DELETE FROM global_product_gpc_bricks "
            "WHERE global_product_id IN ("
            "SELECT id FROM global_products WHERE primary_gtin = :gtin_charlie"
            ")"
        ),
        {"gtin_charlie": GTIN_CHARLIE},
    )
    conn.execute(
        text(
            "DELETE FROM external_article_product_links "
            "WHERE confirmed_by = :confirmed_by"
        ),
        {"confirmed_by": EXTERNAL_LINK_CONFIRMED_BY},
    )
    conn.execute(
        text(
            "DELETE FROM product_group_memberships "
            "WHERE inventory_group_key IN (:test_group_key, :official_gpc_group_key)"
        ),
        {
            "test_group_key": TEST_GROUP_KEY,
            "official_gpc_group_key": OFFICIAL_GPC_GROUP_KEY,
        },
    )
    conn.execute(
        text(
            "DELETE FROM product_inventory_groups "
            "WHERE inventory_group_key IN (:test_group_key, :official_gpc_group_key)"
        ),
        {
            "test_group_key": TEST_GROUP_KEY,
            "official_gpc_group_key": OFFICIAL_GPC_GROUP_KEY,
        },
    )
    conn.execute(
        text(
            "DELETE FROM product_group_memberships "
            "WHERE global_product_id IN ("
            "SELECT id FROM global_products "
            "WHERE primary_gtin IN (:gtin_alpha, :gtin_bravo, :gtin_charlie)"
            ")"
        ),
        {"gtin_alpha": GTIN_ALPHA, "gtin_bravo": GTIN_BRAVO, "gtin_charlie": GTIN_CHARLIE},
    )
    conn.execute(
        text(
            "DELETE FROM product_identities "
            "WHERE identity_type = 'gtin' AND identity_value IN (:gtin_alpha, :gtin_bravo, :gtin_charlie)"
        ),
        {"gtin_alpha": GTIN_ALPHA, "gtin_bravo": GTIN_BRAVO, "gtin_charlie": GTIN_CHARLIE},
    )
    conn.execute(
        text("DELETE FROM global_products WHERE primary_gtin IN (:gtin_alpha, :gtin_bravo, :gtin_charlie)"),
        {"gtin_alpha": GTIN_ALPHA, "gtin_bravo": GTIN_BRAVO, "gtin_charlie": GTIN_CHARLIE},
    )


def _assert_schema_contract() -> None:
    inspector = inspect(engine)
    before_tables = set(inspector.get_table_names())

    revision = None
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != ALEMBIC_HEAD:
        raise AssertionError(f"Unexpected Alembic head: {revision}")

    identity_columns = {
        str(column["name"]): column
        for column in inspector.get_columns("product_identities")
    }
    if not isinstance(identity_columns["is_primary"]["type"], sa.Boolean):
        raise AssertionError(identity_columns["is_primary"])

    candidate_columns = {
        str(column["name"]): column
        for column in inspector.get_columns("external_product_candidates")
    }
    product_columns = {
        str(column["name"]): column
        for column in inspector.get_columns("global_products")
    }
    if "image_url" not in candidate_columns or "image_url" not in product_columns:
        raise AssertionError("Catalog/OFF image_url schema contract ontbreekt")
    for column_name in (
        "is_probable",
        "is_user_confirmed",
        "is_external_database_override",
    ):
        if not isinstance(candidate_columns[column_name]["type"], sa.Boolean):
            raise AssertionError((column_name, candidate_columns[column_name]))

    ensure_external_product_candidates_schema()
    ensure_external_product_index_seeded()

    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("Catalog/OFF validation unexpectedly mutated runtime schema")

    print("POSTGRESQL_CATALOG_OFF_ALEMBIC_HEAD_20260919_01_GREEN")
    print("POSTGRESQL_CATALOG_OFF_IMAGE_SCHEMA_GREEN")
    print("POSTGRESQL_CATALOG_OFF_BOOLEAN_TYPES_GREEN")
    print("POSTGRESQL_CATALOG_OFF_VALIDATION_ONLY_SCHEMA_GREEN")


def _off_payload(gtin: str, name: str) -> dict[str, object]:
    return {
        "gtin": gtin,
        "product_name": name,
        "brand": "PostgreSQL proof",
        "category": "proof",
        "quantity": "500 g",
        "image_url": f"https://images.openfoodfacts.test/{gtin}.jpg",
    }


def _assert_off_identity_and_catalog_queries() -> None:
    with engine.begin() as conn:
        _cleanup(conn)
        alpha_id, alpha_gtin, _, _ = _upsert_global_product(
            conn,
            _off_payload(GTIN_ALPHA, NAME_ALPHA),
        )
        bravo_id, bravo_gtin, _, _ = _upsert_global_product(
            conn,
            _off_payload(GTIN_BRAVO, NAME_BRAVO),
        )
        if alpha_gtin != GTIN_ALPHA or bravo_gtin != GTIN_BRAVO:
            raise AssertionError((alpha_gtin, bravo_gtin))

        alpha_identity = conn.execute(
            text(
                "SELECT is_primary FROM product_identities "
                "WHERE identity_type = 'gtin' AND identity_value = :gtin"
            ),
            {"gtin": GTIN_ALPHA},
        ).mappings().one()
        if alpha_identity["is_primary"] is not True:
            raise AssertionError(alpha_identity)

        # Exercise the existing-identity UPDATE branch as well as the INSERT branch.
        updated_id, _, _, _ = _upsert_global_product(
            conn,
            _off_payload(GTIN_ALPHA, NAME_ALPHA),
        )
        if updated_id != alpha_id:
            raise AssertionError((alpha_id, updated_id))

    identities = catalog_routes._identity_rows(alpha_id)
    if not identities or identities[0].get("is_primary") is not True:
        raise AssertionError(identities)

    catalog = catalog_routes.list_catalog(
        name=NAME_FILTER,
        brand="",
        primary_gtin="",
        product_type="",
        source="",
        household_article_count="",
        sort_by="name",
        sort_direction="asc",
        limit=20,
        offset=0,
    )
    proof_items = [
        item for item in catalog["items"]
        if item.get("id") in {alpha_id, bravo_id}
    ]
    if [item.get("id") for item in proof_items] != [alpha_id, bravo_id]:
        raise AssertionError(proof_items)
    image_by_id = {item.get("id"): item.get("image_url") for item in proof_items}
    if image_by_id.get(alpha_id) != f"https://images.openfoodfacts.test/{GTIN_ALPHA}.jpg":
        raise AssertionError(image_by_id)
    if image_by_id.get(bravo_id) != f"https://images.openfoodfacts.test/{GTIN_BRAVO}.jpg":
        raise AssertionError(image_by_id)

    # Numeric sort must not be wrapped in LOWER().
    numeric_catalog = catalog_routes.list_catalog(
        name=NAME_FILTER,
        brand="",
        primary_gtin="",
        product_type="",
        source="",
        household_article_count="",
        sort_by="household_article_count",
        sort_direction="desc",
        limit=20,
        offset=0,
    )
    if len(numeric_catalog["items"]) < 2:
        raise AssertionError(numeric_catalog)

    # The query itself is the proof: PostgreSQL must parse and execute timestamp ordering.
    receipt_rows = catalog_routes._receipt_line_rows(alpha_id)
    if not isinstance(receipt_rows, list):
        raise AssertionError(receipt_rows)

    with engine.begin() as conn:
        _cleanup(conn)

    print("POSTGRESQL_OFF_IDENTITY_INSERT_UPDATE_BOOLEAN_GREEN")
    print("POSTGRESQL_CATALOG_IDENTITY_BOOLEAN_ORDER_GREEN")
    print("POSTGRESQL_CATALOG_OFF_IMAGE_PERSISTENCE_GREEN")
    print("POSTGRESQL_CATALOG_CASE_INSENSITIVE_SORT_DML_GREEN")
    print("POSTGRESQL_CATALOG_NUMERIC_SORT_DML_GREEN")
    print("POSTGRESQL_CATALOG_RECEIPT_TIMESTAMP_QUERY_GREEN")



def _assert_integer_membership_projection() -> None:
    with engine.begin() as conn:
        _cleanup(conn)
        global_product_id, _, _, _ = _upsert_global_product(
            conn,
            _off_payload(GTIN_ALPHA, NAME_ALPHA),
        )
        conn.execute(
            text(
                """
                INSERT INTO product_inventory_groups (
                    inventory_group_key,
                    display_name,
                    default_base_unit,
                    aggregation_mode,
                    active,
                    created_at,
                    updated_at,
                    source
                ) VALUES (
                    :inventory_group_key,
                    :display_name,
                    'stuk',
                    'count',
                    1,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    :source
                )
                """
            ),
            {
                "inventory_group_key": TEST_GROUP_KEY,
                "display_name": "PostgreSQL Catalog OFF membership proof",
                "source": "postgresql_catalog_off_request_dml_only_selftest",
            },
        )

        linked = link_global_product_to_inventory_group_with_connection(
            conn,
            global_product_id=global_product_id,
            inventory_group_key=TEST_GROUP_KEY,
            confidence=0.93,
            source="postgresql_catalog_off_request_dml_only_selftest",
            confirmed_by_user=True,
        )
        if not bool(linked.get("ok")):
            raise AssertionError(linked)

        membership = conn.execute(
            text(
                """
                SELECT active, confirmed_by_user
                FROM product_group_memberships
                WHERE global_product_id = :global_product_id
                LIMIT 1
                """
            ),
            {"global_product_id": global_product_id},
        ).mappings().one()
        if int(membership["active"]) != 1 or int(membership["confirmed_by_user"]) != 1:
            raise AssertionError(membership)

        enriched = _m2c2l_enrich_linked_receipt_items(
            conn,
            [{"global_product_id": global_product_id}],
        )
        if len(enriched) != 1:
            raise AssertionError(enriched)
        if enriched[0].get("linked_product_type_id") != TEST_GROUP_KEY:
            raise AssertionError(enriched)

        _cleanup(conn)

    print("POSTGRESQL_CATALOG_OFF_INTEGER_MEMBERSHIP_PROJECTION_GREEN")


def _assert_complete_official_gpc_link_validation() -> None:
    with engine.begin() as conn:
        _cleanup(conn)
        global_product_id, _, _, _ = _upsert_global_product(
            conn,
            _off_payload(GTIN_ALPHA, NAME_ALPHA),
        )
        conn.execute(
            text(
                """
                INSERT INTO product_inventory_groups (
                    inventory_group_key,
                    display_name,
                    default_base_unit,
                    aggregation_mode,
                    active,
                    gpc_brick_code,
                    created_at,
                    updated_at,
                    source
                ) VALUES (
                    :inventory_group_key,
                    :display_name,
                    'stuk',
                    'count',
                    1,
                    :gpc_brick_code,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP,
                    :source
                )
                """
            ),
            {
                "inventory_group_key": OFFICIAL_GPC_GROUP_KEY,
                "display_name": "PostgreSQL OFF complete-link proof",
                "gpc_brick_code": OFFICIAL_GPC_BRICK_CODE,
                "source": "gs1_gpc_postgresql_test",
            },
        )

        linked = link_global_product_to_inventory_group_with_connection(
            conn,
            global_product_id=global_product_id,
            inventory_group_key=OFFICIAL_GPC_GROUP_KEY,
            comparison_group_key=OFFICIAL_GPC_GROUP_KEY,
            confidence=1.0,
            source="manual_gs1_gpc",
            confirmed_by_user=True,
        )
        if not bool(linked.get("ok")):
            raise AssertionError(linked)

        projected = _central_product_details(conn, global_product_id)
        if projected.get("product_type_id") != OFFICIAL_GPC_GROUP_KEY:
            raise AssertionError(projected)
        if projected.get("gpc_brick_code") != OFFICIAL_GPC_BRICK_CODE:
            raise AssertionError(projected)
        if not str(projected.get("gpc_brick_name") or "").strip():
            raise AssertionError(projected)

        completeness = _complete_global_product_link_data(conn, global_product_id)
        if not completeness.get("complete"):
            raise AssertionError(completeness)
        if not completeness.get("has_active_official_gpc"):
            raise AssertionError(completeness)

        saved = save_external_article_product_link(
            conn,
            retailer_code="aldi",
            receipt_text="CHOC OPOPS / CHOCO SHELLS",
            external_article_code="",
            global_product_id=global_product_id,
            confirmed_by=EXTERNAL_LINK_CONFIRMED_BY,
        )
        if saved.get("status") != "confirmed":
            raise AssertionError(saved)
        if saved.get("global_product_id") != global_product_id:
            raise AssertionError(saved)

        _cleanup(conn)

    print("POSTGRESQL_OFF_COMPLETE_GPC_LINK_VALIDATION_GREEN")
    print("POSTGRESQL_EXTERNAL_ARTICLE_UI_GPC_METADATA_GREEN")


def _assert_candidate_identity_timestamp_order() -> None:
    with engine.begin() as conn:
        candidate = _candidate_identity(
            conn,
            "purchase-import-line:__postgresql_candidate_timestamp_probe__",
            "__postgresql_candidate_timestamp_probe__",
        )
    if candidate is not None:
        raise AssertionError(candidate)

    print("POSTGRESQL_OFF_CANDIDATE_TIMESTAMP_ORDER_GREEN")


def _assert_receipt_table_off_search_postgresql_types() -> None:
    with engine.begin() as conn:
        resolved = _resolve_receipt_table_line(
            conn,
            "__postgresql_off_receipt_table_quantity_probe__",
        )
    if resolved is not None:
        raise AssertionError(resolved)

    print("POSTGRESQL_OFF_RECEIPT_TABLE_NUMERIC_QUANTITY_GREEN")


def _assert_external_article_ui_membership_projection() -> None:
    with engine.begin() as conn:
        details = _central_product_details(
            conn,
            "__postgresql_external_article_ui_probe__",
        )
    if details:
        raise AssertionError(details)

    print("POSTGRESQL_EXTERNAL_ARTICLE_UI_INTEGER_MEMBERSHIP_GREEN")


def _assert_global_off_link_ignores_household_specific_product_link() -> None:
    with engine.begin() as conn:
        _cleanup(conn)
        conn.execute(
            text(
                """
                INSERT INTO store_providers (
                    id, code, name, status, import_mode, created_at, updated_at
                ) VALUES (
                    :id, :code, :name, 'active', 'receipt',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": GLOBAL_SCOPE_PROVIDER_ID,
                "code": GLOBAL_SCOPE_PROVIDER_ID,
                "name": "PostgreSQL global scope provider",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO household_store_connections (
                    id, household_id, store_provider_id, connection_status,
                    created_at, updated_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, 'active',
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": GLOBAL_SCOPE_CONNECTION_ID,
                "household_id": GLOBAL_SCOPE_HOUSEHOLD_ID,
                "store_provider_id": GLOBAL_SCOPE_PROVIDER_ID,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO purchase_import_batches (
                    id, household_id, store_provider_id, connection_id,
                    source_type, source_reference, import_status, raw_payload,
                    created_at
                ) VALUES (
                    :id, :household_id, :store_provider_id, :connection_id,
                    'receipt', 'postgresql-global-scope-proof', 'imported',
                    :raw_payload, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": GLOBAL_SCOPE_BATCH_ID,
                "household_id": GLOBAL_SCOPE_HOUSEHOLD_ID,
                "store_provider_id": GLOBAL_SCOPE_PROVIDER_ID,
                "connection_id": GLOBAL_SCOPE_CONNECTION_ID,
                "raw_payload": '{"batch_metadata":{"store_name":"Albert Heijn"}}',
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO household_articles (
                    id, household_id, naam, consumable, global_product_id,
                    status, default_inventory_handling, created_at, updated_at
                ) VALUES (
                    :id, :household_id, :naam, 0, :global_product_id,
                    'active', 'STOCK', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": GLOBAL_SCOPE_HOUSEHOLD_ARTICLE_ID,
                "household_id": GLOBAL_SCOPE_HOUSEHOLD_ID,
                "naam": GLOBAL_SCOPE_RECEIPT_TEXT,
                "global_product_id": GLOBAL_SCOPE_LEGACY_PRODUCT_ID,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO purchase_import_lines (
                    id, batch_id, article_name_raw, brand_raw, quantity_raw,
                    unit_raw, line_price_raw, currency_code, match_status,
                    matched_household_article_id, ui_sort_order, created_at,
                    updated_at
                ) VALUES (
                    :id, :batch_id, :article_name_raw, 'Albert Heijn', 1,
                    'stuk', 1.65, 'EUR', 'matched',
                    :matched_household_article_id, 1, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": GLOBAL_SCOPE_LINE_ID,
                "batch_id": GLOBAL_SCOPE_BATCH_ID,
                "article_name_raw": GLOBAL_SCOPE_RECEIPT_TEXT,
                "matched_household_article_id": GLOBAL_SCOPE_HOUSEHOLD_ARTICLE_ID,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO external_product_candidates (
                    id, purchase_import_line_id, source_name, candidate_name,
                    candidate_source_name, candidate_source_product_code,
                    retailer_code, receipt_line_text, score, status,
                    candidate_status, created_by, is_probable,
                    is_user_confirmed, is_external_database_override,
                    created_at, updated_at
                ) VALUES (
                    :id, :purchase_import_line_id, 'postgresql_test',
                    :candidate_name, 'postgresql_test', 'global-scope-proof',
                    :retailer_code, :receipt_line_text, 0.9, 'candidate',
                    'candidate', 'postgresql_global_scope_test', FALSE,
                    FALSE, FALSE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": GLOBAL_SCOPE_CANDIDATE_ID,
                "purchase_import_line_id": GLOBAL_SCOPE_LINE_ID,
                "candidate_name": NAME_CHARLIE,
                "retailer_code": GLOBAL_SCOPE_RETAILER,
                "receipt_line_text": GLOBAL_SCOPE_RECEIPT_TEXT,
            },
        )

    result = link_off_product_with_product_type(
        receipt_item_id=f"purchase-import-line:{GLOBAL_SCOPE_LINE_ID}",
        off_product=_off_payload(GTIN_CHARLIE, NAME_CHARLIE),
        product_type_assignment={
            "product_type_id": "gpc:10005897",
            "gpc_source": "manual",
            "mapping_source": "manual_gs1_gpc",
            "confidence_score": 1.0,
        },
    )
    linked_product_id = str((result.get("global_product") or {}).get("id") or "")
    if not linked_product_id:
        raise AssertionError(result)

    with engine.begin() as conn:
        household_article = conn.execute(
            text(
                """
                SELECT global_product_id
                FROM household_articles
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": GLOBAL_SCOPE_HOUSEHOLD_ARTICLE_ID},
        ).mappings().one()
        if household_article.get("global_product_id") != GLOBAL_SCOPE_LEGACY_PRODUCT_ID:
            raise AssertionError(household_article)

        purchase_line = conn.execute(
            text(
                """
                SELECT matched_global_product_id, match_status
                FROM purchase_import_lines
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": GLOBAL_SCOPE_LINE_ID},
        ).mappings().one()
        if purchase_line.get("matched_global_product_id") not in (None, ""):
            raise AssertionError(purchase_line)

        central_link = conn.execute(
            text(
                """
                SELECT global_product_id, status
                FROM external_article_product_links
                WHERE retailer_code = :retailer_code
                  AND receipt_text_normalized = :receipt_text_normalized
                ORDER BY confirmed_at DESC, id DESC
                LIMIT 1
                """
            ),
            {
                "retailer_code": GLOBAL_SCOPE_RETAILER,
                "receipt_text_normalized": GLOBAL_SCOPE_RECEIPT_TEXT.lower(),
            },
        ).mappings().one()
        if central_link.get("global_product_id") != linked_product_id:
            raise AssertionError(central_link)
        if central_link.get("status") != "confirmed":
            raise AssertionError(central_link)

    projected = list_external_receipt_items(limit=500)
    matching = [
        item
        for item in projected.get("items") or []
        if str(item.get("receipt_line_text") or "").strip() == GLOBAL_SCOPE_RECEIPT_TEXT
    ]
    if len(matching) != 1:
        raise AssertionError(matching)
    row = matching[0]
    if row.get("central_link_active") is not True:
        raise AssertionError(row)
    if str(row.get("global_product_id") or "") != linked_product_id:
        raise AssertionError(row)
    if str(row.get("linked_candidate_name") or "") != NAME_CHARLIE:
        raise AssertionError(row)

    with engine.begin() as conn:
        _cleanup(conn)

    print("POSTGRESQL_OFF_GLOBAL_LINK_IGNORES_HOUSEHOLD_PRODUCT_GREEN")
    print("POSTGRESQL_EXTERNAL_RECEIPT_MAIN_TABLE_CENTRAL_LINK_GREEN")


def _assert_household_only_link_not_projected_as_global() -> None:
    with engine.begin() as conn:
        projected = project_central_link_truth(
            conn,
            {
                "retailer_code": "__global_scope_probe__",
                "receipt_line_text": "__household_only_link_probe__",
                "global_product_id": "__household_only_product__",
                "matched_global_product_id": "__household_only_product__",
                "canonical_catalog_product_id": "__household_only_product__",
                "linked_candidate_name": "Household-only product",
                "linked_product_type_id": "gpc:10000284",
                "linked_product_type": "Household-only type",
                "linked_score": 1.0,
                "status": "linked_to_catalog",
                "candidate_status": "linked_to_catalog",
                "candidates": [],
            },
        )

    if projected.get("central_link_active"):
        raise AssertionError(projected)
    for field in (
        "global_product_id",
        "matched_global_product_id",
        "canonical_catalog_product_id",
        "linked_candidate_name",
        "linked_gtin",
        "linked_product_type_id",
        "linked_product_type",
        "linked_score",
    ):
        if projected.get(field) not in (None, ""):
            raise AssertionError((field, projected))

    print("POSTGRESQL_EXTERNAL_ARTICLE_UI_HOUSEHOLD_ONLY_LINK_IGNORED_GREEN")


def _assert_off_gpc_normalization() -> None:
    normalized = _normalize_result(
        query="bananen",
        retailer_code="albert heijn",
        quantity_label="1 stuk",
        product={
            "code": "8718265184886",
            "product_name": "Bananen",
            "brands": "AH",
            "quantity": "1 stuk",
            "categories": "Fruit",
            "gpcCategoryCode": "10005897",
            "countries": "Nederland",
        },
    )
    if not normalized:
        raise AssertionError(normalized)
    if normalized.get("gpc_brick_code") != "10005897":
        raise AssertionError(normalized)
    if normalized.get("explicit_gpc_brick_code") != "10005897":
        raise AssertionError(normalized)

    print("POSTGRESQL_OFF_GPC_CODE_PROPAGATION_GREEN")


def _assert_explicit_off_gpc_uses_official_reference_catalog() -> None:
    classified = classify_gpc_product(
        product_name="Bananen",
        category="Fruit",
        explicit_gpc_brick_code="10005897",
    )
    if classified.get("status") != "classified":
        raise AssertionError(classified)
    if classified.get("classification_source") != "explicit_gpc_code":
        raise AssertionError(classified)
    if classified.get("product_type_id") != "gpc:10005897":
        raise AssertionError(classified)
    if classified.get("gpc_brick_code") != "10005897":
        raise AssertionError(classified)
    if not str(classified.get("source") or "").startswith("gs1_gpc_"):
        raise AssertionError(classified)

    print("POSTGRESQL_OFF_EXPLICIT_GPC_OFFICIAL_REFERENCE_GREEN")


def _assert_off_index_matcher() -> None:
    result = match_retailer_receipt_line(
        "lidl",
        "melk",
        include_below_threshold=True,
    )
    if not isinstance(result, dict) or "candidates" not in result:
        raise AssertionError(result)
    if result.get("uses_legacy_fallback") is not False:
        raise AssertionError(result)
    print("POSTGRESQL_OFF_INDEX_MATCHER_READ_PATH_GREEN")


def main() -> None:
    before_tables = set(inspect(engine).get_table_names())
    try:
        _assert_runtime_create_denied()
        _assert_schema_contract()
        _assert_off_identity_and_catalog_queries()
        _assert_integer_membership_projection()
        _assert_complete_official_gpc_link_validation()
        _assert_candidate_identity_timestamp_order()
        _assert_receipt_table_off_search_postgresql_types()
        _assert_external_article_ui_membership_projection()
        _assert_global_off_link_ignores_household_specific_product_link()
        _assert_household_only_link_not_projected_as_global()
        _assert_off_gpc_normalization()
        _assert_explicit_off_gpc_uses_official_reference_catalog()
        _assert_off_index_matcher()
    finally:
        with engine.begin() as conn:
            _cleanup(conn)
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("Catalog/OFF DML proof changed the runtime schema")
    print("POSTGRESQL_CATALOG_OFF_RUNTIME_SCHEMA_UNCHANGED_GREEN")
    print("POSTGRESQL_CATALOG_OFF_REQUEST_DML_ONLY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
