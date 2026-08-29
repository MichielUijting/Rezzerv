from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    evaluate_household_permission,
    evaluate_platform_permission,
    resolve_active_platform_role_keys,
)
from app.services.authorization_membership_service import (
    resolve_effective_household_role,
    set_household_membership_role,
    set_household_permission_override,
)
from app.services.authorization_ui_fixture_provisioning import (
    AUTHORIZATION_UI_MEMBER_EMAIL,
    ensure_authorization_ui_fixture_member,
)
from app.services.platform_authorization_management_service import (
    PLATFORM_ADMIN_ROLE_KEY,
    grant_special_role,
    revoke_special_role,
)
from app.services.system_superuser_session_provisioning import (
    SUPERGEBRUIKER_EMAIL,
    ensure_system_superuser_for_session_runtime,
)


def _engine_url():
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url


def _assert_runtime_create_denied(engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE pr2j_runtime_ddl_should_fail(id INTEGER)"))
    except ProgrammingError:
        print("POSTGRESQL_AUTHORIZATION_RUNTIME_CREATE_DENIED_GREEN")
        return
    raise AssertionError("Runtime role unexpectedly created a PR2j schema object")


def _user_id_for_email(conn, email: str) -> str:
    value = conn.execute(
        text("SELECT id FROM app_users WHERE lower(email) = lower(:email) LIMIT 1"),
        {"email": email},
    ).scalar_one_or_none()
    if value is None:
        raise AssertionError(f"Expected deterministic authorization user: {email}")
    return str(value)


def _assert_schema_validation_and_seed_dml_only(engine) -> None:
    before_tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
    after_tables = set(inspect(engine).get_table_names())
    if before_tables != after_tables:
        raise AssertionError("Authorization validation/seed unexpectedly mutated runtime schema")
    print("POSTGRESQL_AUTHORIZATION_SCHEMA_VALIDATION_ONLY_GREEN")


def _assert_authorization_paths(engine) -> None:
    with engine.begin() as conn:
        system = ensure_system_superuser_for_session_runtime(conn)
        member = ensure_authorization_ui_fixture_member(conn)
        if member is None:
            raise AssertionError("Authorization UI fixture is disabled in PR2j PostgreSQL proof")

        system_user_id = _user_id_for_email(conn, SUPERGEBRUIKER_EMAIL)
        member_user_id = _user_id_for_email(conn, AUTHORIZATION_UI_MEMBER_EMAIL)

        platform_roles = resolve_active_platform_role_keys(conn, system_user_id)
        if "platform.superuser" not in platform_roles:
            raise AssertionError(f"System superuser role resolution failed: {platform_roles}")
        if not evaluate_platform_permission(
            conn,
            user_id=system_user_id,
            permission_key="platform.catalog.view",
        ).allowed:
            raise AssertionError("System superuser platform permission resolution failed")
        print("POSTGRESQL_AUTHORIZATION_PLATFORM_READ_GREEN")

        effective_role = resolve_effective_household_role(
            conn,
            household_id=member.household_id,
            membership_id=member.membership_id,
            legacy_role="member",
        )
        if effective_role != "household.member":
            raise AssertionError(f"Unexpected effective household role: {effective_role}")
        if not evaluate_household_permission(
            conn,
            household_id=member.household_id,
            membership_id=member.membership_id,
            permission_key="inventory.view",
        ).allowed:
            raise AssertionError("Canonical member household permission resolution failed")
        print("POSTGRESQL_AUTHORIZATION_MEMBERSHIP_READ_GREEN")

        set_household_membership_role(
            conn,
            household_id=member.household_id,
            actor_membership_id=system.membership_id,
            actor_user_id=system_user_id,
            target_membership_id=member.membership_id,
            role_key="household.admin",
            reason="PR2j PostgreSQL DML-only proof",
        )
        if not evaluate_household_permission(
            conn,
            household_id=member.household_id,
            membership_id=member.membership_id,
            permission_key="permissions.manage",
        ).allowed:
            raise AssertionError("Household role update did not grant admin permissions")

        set_household_permission_override(
            conn,
            household_id=member.household_id,
            actor_membership_id=system.membership_id,
            actor_user_id=system_user_id,
            target_membership_id=member.membership_id,
            permission_key="inventory.update",
            effect="deny",
            reason="PR2j PostgreSQL DML-only proof",
        )
        denied = evaluate_household_permission(
            conn,
            household_id=member.household_id,
            membership_id=member.membership_id,
            permission_key="inventory.update",
        )
        if denied.allowed or denied.reason != "explicit_deny":
            raise AssertionError(f"Household permission override failed: {denied}")
        print("POSTGRESQL_AUTHORIZATION_MEMBERSHIP_DML_ONLY_GREEN")

        grant_special_role(
            conn,
            member_user_id,
            role_key=PLATFORM_ADMIN_ROLE_KEY,
            actor_user_id=system_user_id,
        )
        if not evaluate_platform_permission(
            conn,
            user_id=member_user_id,
            permission_key="platform.diagnostics.view",
        ).allowed:
            raise AssertionError("Platform role grant did not become effective")
        revoke_special_role(
            conn,
            member_user_id,
            role_key=PLATFORM_ADMIN_ROLE_KEY,
            actor_user_id=system_user_id,
        )
        if evaluate_platform_permission(
            conn,
            user_id=member_user_id,
            permission_key="platform.diagnostics.view",
        ).allowed:
            raise AssertionError("Platform role revoke did not become effective")
        print("POSTGRESQL_AUTHORIZATION_PLATFORM_DML_ONLY_GREEN")

        conn.execute(
            text(
                "DELETE FROM auth_membership_permission_overrides "
                "WHERE household_id = :household_id "
                "AND membership_id = :membership_id "
                "AND permission_key = 'inventory.update'"
            ),
            {
                "household_id": member.household_id,
                "membership_id": member.membership_id,
            },
        )
        set_household_membership_role(
            conn,
            household_id=member.household_id,
            actor_membership_id=system.membership_id,
            actor_user_id=system_user_id,
            target_membership_id=member.membership_id,
            role_key="household.member",
            reason="PR2j PostgreSQL DML-only proof cleanup",
        )


def main() -> None:
    url = _engine_url()
    engine = create_engine(url)
    try:
        if engine.dialect.name != "postgresql":
            raise AssertionError(f"Expected PostgreSQL runtime, got {engine.dialect.name}")
        _assert_runtime_create_denied(engine)
        _assert_schema_validation_and_seed_dml_only(engine)
        _assert_authorization_paths(engine)
    finally:
        engine.dispose()

    print("POSTGRESQL_AUTHORIZATION_DML_ONLY_GREEN")
    print("POSTGRESQL_AUTHORIZATION_AUTHORITY_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
