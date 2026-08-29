from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import engine
from app.services.article_group_store import (
    create_article_group,
    ensure_article_group_schema,
)
from app.services.household_location_onboarding_service import (
    ensure_location_foundation,
    provision_waar_inhuis_locations,
)
from app.services.household_product_configuration_service import (
    ensure_household_product_configuration_foundation,
    save_wat_inhuis_configuration,
)
from app.services.loyalty_stamp_transaction_service import (
    ensure_loyalty_stamp_transactions_schema,
)
from app.services.platform_user_suspension_service import (
    ensure_user_account_status_schema,
    suspend_platform_user,
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
SUSPENSION_USER_ID = "__pr337_suspension_target__"
SUSPENSION_EMAIL = "pr337-suspension@example.test"
SUSPENSION_SESSION_ID = "__pr337_suspension_session__"


def _assert_location_default_introspection_is_portable() -> None:
    main_source = (BACKEND_ROOT / "app" / "main.py").read_text(encoding="utf-8")
    forbidden = 'PRAGMA table_info(household_article_settings)'
    if forbidden in main_source:
        raise AssertionError(
            "Location-default request path still uses SQLite-only PRAGMA schema introspection"
        )
    print("POSTGRESQL_LOCATION_DEFAULT_INTROSPECTION_PORTABLE_GREEN")


def _assert_account_context_runtime_is_schema_mutation_free() -> None:
    service_root = BACKEND_ROOT / "app" / "services"
    checks = {
        "roles_v2_schema_foundation.py": ("ALTER TABLE", "CREATE TRIGGER"),
        "platform_user_suspension_service.py": (
            "ALTER TABLE app_users",
            "CREATE TABLE app_users",
        ),
    }
    for filename, forbidden_tokens in checks.items():
        source = (service_root / filename).read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in source:
                raise AssertionError(
                    f"Runtime account-context service still contains schema mutation: "
                    f"{filename}: {token}"
                )
    print("POSTGRESQL_ACCOUNT_CONTEXT_SCHEMA_MUTATION_FREE_GREEN")


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
    with engine.begin() as conn:
        ensure_location_foundation(conn)
        ensure_household_product_configuration_foundation(conn)
        ensure_shopping_list_schema(conn)
        ensure_loyalty_stamp_transactions_schema(conn)
        ensure_user_account_status_schema(conn)
    print("POSTGRESQL_CORE_REQUEST_SCHEMA_VALIDATION_ONLY_GREEN")


def _insert_suspension_target(conn, now: datetime) -> None:
    inspector = inspect(conn)
    columns = inspector.get_columns("app_users")
    known_values = {
        "id": SUSPENSION_USER_ID,
        "email": SUSPENSION_EMAIL,
        "password": "PR337-not-used-login-secret",
        "password_hash": "PR337-not-used-password-hash",
        "account_status": "active",
        "suspended_at": None,
        "created_at": now,
        "updated_at": now,
    }
    required_without_default = {
        str(column.get("name") or "")
        for column in columns
        if not bool(column.get("nullable"))
        and column.get("default") is None
    }
    unknown_required = required_without_default - set(known_values)
    if unknown_required:
        raise AssertionError(
            "PR337 suspension fixture does not cover required app_users columns: "
            f"{sorted(unknown_required)}"
        )

    names = [
        str(column.get("name") or "")
        for column in columns
        if str(column.get("name") or "") in known_values
    ]
    params = {name: known_values[name] for name in names}
    column_sql = ", ".join(names)
    value_sql = ", ".join(f":{name}" for name in names)
    conn.execute(
        text(f"INSERT INTO app_users ({column_sql}) VALUES ({value_sql})"),
        params,
    )


def _exercise_account_suspension_dml() -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires_at = now + timedelta(hours=1)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM server_sessions WHERE id = :session_id"),
            {"session_id": SUSPENSION_SESSION_ID},
        )
        conn.execute(
            text("DELETE FROM app_users WHERE id = :user_id"),
            {"user_id": SUSPENSION_USER_ID},
        )
        _insert_suspension_target(conn, now)
        conn.execute(
            text(
                """
                INSERT INTO server_sessions(
                    id,
                    session_token_hash,
                    user_id,
                    active_household_id,
                    issued_at,
                    expires_at,
                    session_version,
                    revoked_at,
                    replaced_by_session_id,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :session_token_hash,
                    :user_id,
                    NULL,
                    :issued_at,
                    :expires_at,
                    1,
                    NULL,
                    NULL,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "id": SUSPENSION_SESSION_ID,
                "session_token_hash": "9" * 64,
                "user_id": SUSPENSION_USER_ID,
                "issued_at": now,
                "expires_at": expires_at,
                "created_at": now,
                "updated_at": now,
            },
        )

        result = suspend_platform_user(
            conn,
            SUSPENSION_USER_ID,
            actor_user_id="__pr337_platform_admin__",
            now=now,
        )
        if result.get("account_status") != "suspended":
            raise AssertionError(f"Suspension service returned unexpected status: {result}")
        if int(result.get("active_sessions_revoked") or 0) != 1:
            raise AssertionError(f"Suspension did not revoke active session: {result}")

        account = conn.execute(
            text(
                """
                SELECT account_status, suspended_at
                FROM app_users
                WHERE id = :user_id
                """
            ),
            {"user_id": SUSPENSION_USER_ID},
        ).mappings().one()
        if str(account.get("account_status") or "") != "suspended":
            raise AssertionError(f"Database rejected canonical suspended status: {account}")
        if account.get("suspended_at") is None:
            raise AssertionError("Suspension did not persist suspended_at")

        revoked_at = conn.execute(
            text("SELECT revoked_at FROM server_sessions WHERE id = :session_id"),
            {"session_id": SUSPENSION_SESSION_ID},
        ).scalar_one()
        if revoked_at is None:
            raise AssertionError("Suspension did not revoke server session")

        conn.execute(
            text("DELETE FROM server_sessions WHERE id = :session_id"),
            {"session_id": SUSPENSION_SESSION_ID},
        )
        conn.execute(
            text("DELETE FROM app_users WHERE id = :user_id"),
            {"user_id": SUSPENSION_USER_ID},
        )

    print("POSTGRESQL_ACCOUNT_SUSPENSION_DML_ONLY_GREEN")


def _exercise_request_dml() -> None:
    article_group_name = "PR337 runtime DML only"
    created_group = create_article_group(HOUSEHOLD_ID, article_group_name)
    if not created_group.get("ok"):
        raise AssertionError(f"Article-group DML failed: {created_group}")

    with engine.begin() as conn:
        product_configuration = save_wat_inhuis_configuration(
            conn,
            household_id=HOUSEHOLD_ID,
            inventory_tracking_level="presence",
            global_locations_enabled=True,
            almost_out_enabled=True,
            shopping_enabled=True,
        )
        if product_configuration.location_tracking_level != "global":
            raise AssertionError(
                f"Product-configuration DML failed: {product_configuration}"
            )
        direct = conn.execute(
            text(
                """
                SELECT id, naam, active, is_direct
                FROM spaces
                WHERE household_id = :household_id
                  AND is_direct = 1
                """
            ),
            {"household_id": HOUSEHOLD_ID},
        ).mappings().one()
        if str(direct.get("naam") or "").strip() != "Direct" or not bool(direct.get("active")):
            raise AssertionError(f"Direct-location DML failed: {direct}")

        locations = provision_waar_inhuis_locations(
            conn,
            household_id=HOUSEHOLD_ID,
            main_locations=["PR337 pantry"],
            sublocations=[
                {"space_name": "PR337 pantry", "name": "PR337 shelf"}
            ],
        )
        if len(locations.get("spaces") or []) != 1:
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

    # Cleanup is ordinary DML. The canonical Direct row is intentionally retained:
    # Alembic-owned immutability guards make that row non-deletable by design.
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
                "(SELECT id FROM spaces WHERE household_id = :household_id AND is_direct = 0)"
            ),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text(
                "DELETE FROM spaces "
                "WHERE household_id = :household_id AND is_direct = 0"
            ),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("DELETE FROM household_product_configuration WHERE household_id = :household_id"),
            {"household_id": HOUSEHOLD_ID},
        )
        conn.execute(
            text("DELETE FROM article_groups WHERE household_id = :household_id"),
            {"household_id": HOUSEHOLD_ID},
        )

    print("POSTGRESQL_CORE_REQUEST_DML_ONLY_GREEN")


def main() -> None:
    _assert_location_default_introspection_is_portable()
    _assert_account_context_runtime_is_schema_mutation_free()
    _assert_runtime_has_no_schema_create()
    _validate_all_cutover_contracts()
    _exercise_account_suspension_dml()
    _exercise_request_dml()
    print("POSTGRESQL_CORE_REQUEST_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
