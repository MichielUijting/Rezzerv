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
from app.services.external_product_candidate_store import ensure_external_product_candidates_schema
from app.services.external_product_index_store import ensure_external_product_index_seeded
from app.services.off_product_link_service import _upsert_global_product

GTIN_ALPHA = "8712345678901"
GTIN_BRAVO = "8712345678902"
NAME_ALPHA = "postgresql catalog off proof alpha"
NAME_BRAVO = "PostgreSQL Catalog OFF Proof Bravo"
NAME_FILTER = "postgresql catalog off proof"


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
            "DELETE FROM product_identities "
            "WHERE identity_type = 'gtin' AND identity_value IN (:gtin_alpha, :gtin_bravo)"
        ),
        {"gtin_alpha": GTIN_ALPHA, "gtin_bravo": GTIN_BRAVO},
    )
    conn.execute(
        text("DELETE FROM global_products WHERE primary_gtin IN (:gtin_alpha, :gtin_bravo)"),
        {"gtin_alpha": GTIN_ALPHA, "gtin_bravo": GTIN_BRAVO},
    )


def _assert_schema_contract() -> None:
    inspector = inspect(engine)
    before_tables = set(inspector.get_table_names())

    revision = None
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    if revision != "20260829_14":
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

    print("POSTGRESQL_CATALOG_OFF_ALEMBIC_HEAD_14_GREEN")
    print("POSTGRESQL_CATALOG_OFF_BOOLEAN_TYPES_GREEN")
    print("POSTGRESQL_CATALOG_OFF_VALIDATION_ONLY_SCHEMA_GREEN")


def _off_payload(gtin: str, name: str) -> dict[str, object]:
    return {
        "gtin": gtin,
        "product_name": name,
        "brand": "PostgreSQL proof",
        "category": "proof",
        "quantity": "500 g",
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
    print("POSTGRESQL_CATALOG_CASE_INSENSITIVE_SORT_DML_GREEN")
    print("POSTGRESQL_CATALOG_NUMERIC_SORT_DML_GREEN")
    print("POSTGRESQL_CATALOG_RECEIPT_TIMESTAMP_QUERY_GREEN")


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
