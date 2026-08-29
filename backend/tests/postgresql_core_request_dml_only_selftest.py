from __future__ import annotations

from sqlalchemy import text

from app.db import engine
from app.services.article_group_store import (
    create_article_group,
    ensure_article_group_schema,
)
from app.services.household_location_onboarding_service import (
    ensure_location_foundation,
    provision_waar_inhuis_locations,
)
from app.services.loyalty_stamp_transaction_service import (
    ensure_loyalty_stamp_transactions_schema,
)
from app.services.product_inventory_group_store import (
    ensure_product_inventory_group_schema,
)
from app.services.product_taxonomy_store import ensure_product_taxonomy_schema
from app.services.shopping_list_service import (
    add_shopping_list_item,
    delete_shopping_list_item,
    ensure_shopping_list_schema,
    update_shopping_list_item,
)


HOUSEHOLD_ID = "__pr337_runtime_dml_only__"


def _assert_runtime_has_no_schema_create() -> None:
    with engine.connect() as conn:
        if conn.dialect.name != "postgresql":
            raise AssertionError(
                f"DML-only authority proof requires PostgreSQL, got {conn.dialect.name}"
            )
        has_create = bool(
            conn.execute(
                text(
                    "SELECT has_schema_privilege(current_user, current_schema(), 'CREATE')"
                )
            ).scalar_one()
        )
        if has_create:
            raise AssertionError("Runtime role unexpectedly has schema CREATE privilege")
    print("POSTGRESQL_CORE_REQUEST_RUNTIME_CREATE_DENIED_GREEN")


def _validate_all_cutover_contracts() -> None:
    ensure_product_taxonomy_schema()
    # This validation also seeds canonical reference data using ordinary DML,
    # proving that the runtime role can still perform intended data writes.
    ensure_product_inventory_group_schema()
    ensure_article_group_schema()
    with engine.connect() as conn:
        ensure_location_foundation(conn)
        ensure_shopping_list_schema(conn)
        ensure_loyalty_stamp_transactions_schema(conn)
    print("POSTGRESQL_CORE_REQUEST_SCHEMA_VALIDATION_ONLY_GREEN")


def _exercise_request_dml() -> None:
    article_group_name = "PR337 runtime DML only"
    created_group = create_article_group(HOUSEHOLD_ID, article_group_name)
    if not created_group.get("ok"):
        raise AssertionError(f"Article-group DML failed: {created_group}")

    with engine.begin() as conn:
        locations = provision_waar_inhuis_locations(
            conn,
            household_id=HOUSEHOLD_ID,
            main_locations=["PR337 pantry"],
            sublocations=[
                {"main_location": "PR337 pantry", "name": "PR337 shelf"}
            ],
        )
        if len(locations.get("main_locations") or []) != 1:
            raise AssertionError(f"Location DML failed: {locations}")

        item = add_shopping_list_item(
            conn,
            HOUSEHOLD_ID,
            {
                "article_name": "PR337 test item",
                "quantity": 1,
                "unit": "stuk",
                "note": "runtime DML-only authority proof",
            },
        )
        updated = update_shopping_list_item(
            conn,
            HOUSEHOLD_ID,
            item["id"],
            {"checked": True, "note": "updated without schema privilege"},
        )
        if not updated or updated.get("checked") is not True:
            raise AssertionError(f"Shopping-list DML update failed: {updated}")
        if not delete_shopping_list_item(conn, HOUSEHOLD_ID, item["id"]):
            raise AssertionError("Shopping-list DML delete failed")

    # Cleanup is also DML and intentionally leaves no PR-specific rows behind.
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM shopping_list_items WHERE household_id = :household_id"),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("DELETE FROM shopping_lists WHERE household_id = :household_id"),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text(
                "DELETE FROM sublocations WHERE space_id IN "
                "(SELECT id FROM spaces WHERE household_id = :household_id)"
            ),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("DELETE FROM spaces WHERE household_id = :household_id"),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("DELETE FROM article_groups WHERE household_id = :household_id"),
            {"household_id": HOUSEHOLD_ID},
        )

    print("POSTGRESQL_CORE_REQUEST_DML_ONLY_GREEN")


def main() -> None:
    _assert_runtime_has_no_schema_create()
    _validate_all_cutover_contracts()
    _exercise_request_dml()
    print("POSTGRESQL_CORE_REQUEST_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
