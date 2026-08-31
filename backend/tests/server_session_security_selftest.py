"""Rezzerv server-session security validation on the canonical PostgreSQL schema.

The workflow prepares Alembic head before this selftest runs. This file performs
fixture DML only and deliberately fails if it is pointed at SQLite or if the
runtime role owns schema CREATE authority.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import inspect, text

from app.db import engine
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.server_session_service import (
    create_server_session,
    create_system_server_session,
    resolve_server_session,
    revoke_server_session,
)
from app.services.system_superuser_session_provisioning import (
    SUPERGEBRUIKER_EMAIL,
    SUPERGEBRUIKER_HUISHOUDEN_ID,
)


USER_A_ID = "session-security-user-a"
USER_A_EMAIL = "session-security-a@rezzerv.local"
USER_B_ID = "session-security-user-b"
USER_B_EMAIL = "session-security-b@rezzerv.local"
SYSTEM_USER_ID = "session-security-system-superuser"
MEMBERSHIP_A_ID = "session-security-membership-a"
MEMBERSHIP_B_ID = "session-security-membership-b"
MEMBERSHIP_A_ZERO_ID = "session-security-membership-a-zero"


def _expect_http_status(expected_status: int, fn) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == expected_status, (
            f"verwacht HTTP {expected_status}, kreeg HTTP {exc.status_code}"
        )
        return
    raise AssertionError(f"verwacht HTTP {expected_status}, maar geen fout ontvangen")


def _columns(conn, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns(table_name)
    }


def _insert_household(conn, household_id: str, name: str, context_type: str) -> None:
    columns = _columns(conn, "household_registry")
    id_column = "id" if "id" in columns else "household_id"
    name_column = "naam" if "naam" in columns else "name" if "name" in columns else None
    insert_columns = [id_column]
    insert_values = [":household_id"]
    params = {"household_id": household_id, "name": name, "context_type": context_type}
    updates = []
    if name_column:
        insert_columns.append(name_column)
        insert_values.append(":name")
        updates.append(f"{name_column} = excluded.{name_column}")
    if "context_type" in columns:
        insert_columns.append("context_type")
        insert_values.append(":context_type")
        updates.append("context_type = excluded.context_type")
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    update_sql = ", ".join(updates) if updates else f"{id_column} = excluded.{id_column}"
    conn.execute(
        text(
            f"INSERT INTO household_registry ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)}) "
            f"ON CONFLICT({id_column}) DO UPDATE SET {update_sql}"
        ),
        params,
    )


def _insert_user(conn, user_id: str, email: str) -> None:
    columns = _columns(conn, "app_users")
    id_column = "id" if "id" in columns else "user_id"
    email_column = "email" if "email" in columns else "user_email"
    password_column = "password" if "password" in columns else "password_hash" if "password_hash" in columns else None
    insert_columns = [id_column, email_column]
    insert_values = [":user_id", ":email"]
    params = {"user_id": user_id, "email": email, "password": "session-security-test-only"}
    updates = [f"{id_column} = excluded.{id_column}"]
    if password_column:
        insert_columns.append(password_column)
        insert_values.append(":password")
        updates.append(f"{password_column} = excluded.{password_column}")
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")
        updates.append("updated_at = CURRENT_TIMESTAMP")
    conn.execute(
        text(
            f"INSERT INTO app_users ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)}) "
            f"ON CONFLICT({email_column}) DO UPDATE SET {', '.join(updates)}"
        ),
        params,
    )


def _membership_identity_column(columns: set[str]) -> str:
    for candidate in ("id", "membership_id", "user_id", "user_email"):
        if candidate in columns:
            return candidate
    raise RuntimeError("household_memberships heeft geen bruikbare identiteit")


def _insert_membership(
    conn,
    *,
    membership_id: str,
    user_id: str,
    email: str,
    household_id: str,
    legacy_role: str,
    canonical_role: str,
) -> None:
    columns = _columns(conn, "household_memberships")
    insert_columns = []
    insert_values = []
    params = {
        "membership_id": membership_id,
        "user_id": user_id,
        "email": email,
        "household_id": household_id,
        "legacy_role": legacy_role,
        "canonical_role": canonical_role,
    }
    if "id" in columns:
        insert_columns.append("id")
        insert_values.append(":membership_id")
    elif "membership_id" in columns:
        insert_columns.append("membership_id")
        insert_values.append(":membership_id")
    insert_columns.append("household_id")
    insert_values.append(":household_id")
    if "user_email" in columns:
        insert_columns.append("user_email")
        insert_values.append(":email")
    elif "email" in columns:
        insert_columns.append("email")
        insert_values.append(":email")
    elif "user_id" in columns:
        insert_columns.append("user_id")
        insert_values.append(":user_id")
    else:
        raise RuntimeError("household_memberships mist user_email/email/user_id")
    role_column = "role" if "role" in columns else "rol" if "rol" in columns else None
    if not role_column:
        raise RuntimeError("household_memberships mist role/rol")
    insert_columns.append(role_column)
    insert_values.append(":legacy_role")
    if "status" in columns:
        insert_columns.append("status")
        insert_values.append("'active'")
    if "created_at" in columns:
        insert_columns.append("created_at")
        insert_values.append("CURRENT_TIMESTAMP")
    if "updated_at" in columns:
        insert_columns.append("updated_at")
        insert_values.append("CURRENT_TIMESTAMP")

    conn.execute(
        text(
            f"INSERT INTO household_memberships ({', '.join(insert_columns)}) "
            f"VALUES ({', '.join(insert_values)})"
        ),
        params,
    )
    conn.execute(
        text(
            """
            INSERT INTO auth_membership_roles(
                household_id, membership_id, role_key, active, created_at, updated_at
            ) VALUES (
                :household_id, :membership_id, :canonical_role,
                TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT(household_id, membership_id) DO UPDATE SET
                role_key = excluded.role_key,
                active = TRUE,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        params,
    )


def _update_membership_legacy_role(conn, membership_id: str, role: str) -> None:
    columns = _columns(conn, "household_memberships")
    identity_column = _membership_identity_column(columns)
    role_column = "role" if "role" in columns else "rol"
    identity_value = membership_id
    if identity_column == "user_id":
        identity_value = USER_A_ID
    elif identity_column == "user_email":
        identity_value = USER_A_EMAIL
    conn.execute(
        text(
            f"UPDATE household_memberships SET {role_column} = :role "
            f"WHERE CAST({identity_column} AS TEXT) = :identity"
        ),
        {"role": role, "identity": identity_value},
    )


def _system_membership_count(conn) -> int:
    columns = _columns(conn, "household_memberships")
    if "user_id" in columns:
        sql = "SELECT COUNT(*) FROM household_memberships WHERE user_id = :value"
        value = SYSTEM_USER_ID
    elif "user_email" in columns:
        sql = "SELECT COUNT(*) FROM household_memberships WHERE lower(user_email) = lower(:value)"
        value = SUPERGEBRUIKER_EMAIL
    elif "email" in columns:
        sql = "SELECT COUNT(*) FROM household_memberships WHERE lower(email) = lower(:value)"
        value = SUPERGEBRUIKER_EMAIL
    else:
        raise RuntimeError("household_memberships mist gebruikerskolom")
    return int(conn.execute(text(sql), {"value": value}).scalar_one())


def _cleanup_database(conn) -> None:
    conn.execute(text("""
        DELETE FROM server_sessions
        WHERE user_id IN (
            'session-security-user-a',
            'session-security-user-b',
            'session-security-system-superuser'
        )
    """))
    conn.execute(text("""
        DELETE FROM auth_membership_permission_overrides
        WHERE membership_id IN (
            'session-security-membership-a',
            'session-security-membership-b',
            'session-security-membership-a-zero'
        )
    """))
    conn.execute(text("""
        DELETE FROM auth_membership_roles
        WHERE membership_id IN (
            'session-security-membership-a',
            'session-security-membership-b',
            'session-security-membership-a-zero'
        )
    """))
    conn.execute(text("""
        DELETE FROM auth_platform_user_roles
        WHERE user_id IN (
            'session-security-user-a',
            'session-security-user-b',
            'session-security-system-superuser'
        )
    """))

    membership_columns = _columns(conn, "household_memberships")
    predicates = []
    if "id" in membership_columns:
        predicates.append("id IN ('session-security-membership-a', 'session-security-membership-b', 'session-security-membership-a-zero')")
    if "membership_id" in membership_columns:
        predicates.append("membership_id IN ('session-security-membership-a', 'session-security-membership-b', 'session-security-membership-a-zero')")
    if "user_id" in membership_columns:
        predicates.append("user_id IN ('session-security-user-a', 'session-security-user-b', 'session-security-system-superuser')")
    if "user_email" in membership_columns:
        predicates.append("lower(user_email) IN ('session-security-a@rezzerv.local', 'session-security-b@rezzerv.local', 'supergebruiker@rezzerv.local')")
    if "email" in membership_columns:
        predicates.append("lower(email) IN ('session-security-a@rezzerv.local', 'session-security-b@rezzerv.local', 'supergebruiker@rezzerv.local')")
    if predicates:
        conn.execute(text("DELETE FROM household_memberships WHERE " + " OR ".join(predicates)))

    conn.execute(text("""
        DELETE FROM app_users
        WHERE id IN (
            'session-security-user-a',
            'session-security-user-b',
            'session-security-system-superuser'
        )
    """))
    conn.execute(text("DELETE FROM household_registry WHERE CAST(id AS TEXT) IN ('0', '1', '2')"))


def _prepare_database() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "SERVER_SESSION_SECURITY vereist PostgreSQL; "
            f"ontvangen dialect={engine.dialect.name}"
        )
    with engine.begin() as conn:
        can_create = conn.execute(
            text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
        ).scalar_one()
        if bool(can_create):
            raise RuntimeError("Runtime-role heeft onverwacht CREATE op schema public")
        ensure_authorization_foundation(conn)
        _cleanup_database(conn)
        _insert_household(conn, "0", "Session security system", "system")
        _insert_household(conn, "1", "Session security A", "regular")
        _insert_household(conn, "2", "Session security B", "regular")
        _insert_user(conn, USER_A_ID, USER_A_EMAIL)
        _insert_user(conn, USER_B_ID, USER_B_EMAIL)
        _insert_user(conn, SYSTEM_USER_ID, SUPERGEBRUIKER_EMAIL)
        _insert_membership(
            conn,
            membership_id=MEMBERSHIP_A_ID,
            user_id=USER_A_ID,
            email=USER_A_EMAIL,
            household_id="1",
            legacy_role="owner",
            canonical_role="household.admin",
        )
        _insert_membership(
            conn,
            membership_id=MEMBERSHIP_B_ID,
            user_id=USER_B_ID,
            email=USER_B_EMAIL,
            household_id="2",
            legacy_role="member",
            canonical_role="household.member",
        )
        conn.execute(
            text(
                """
                INSERT INTO auth_platform_user_roles(
                    user_id, role_key, active, created_at, updated_at
                ) VALUES (
                    :user_id, 'platform.superuser', TRUE,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                ON CONFLICT(user_id, role_key) DO UPDATE SET
                    active = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {"user_id": SYSTEM_USER_ID},
        )


def run() -> int:
    checks = []
    _prepare_database()
    try:
        with engine.begin() as conn:
            _expect_http_status(401, lambda: resolve_server_session(conn, None))
        checks.append("missing_cookie_401")

        with engine.begin() as conn:
            raw_session, context = create_server_session(
                conn,
                user_id=USER_A_ID,
                active_household_id="1",
                ttl=timedelta(hours=1),
            )
            assert raw_session
            assert context.user_id == USER_A_ID
            assert context.active_household_id == "1"
            assert context.context_type == "regular"
            assert context.role == "admin"
        checks.append("valid_session_created")

        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.email == USER_A_EMAIL
            assert resolved.active_household_id == "1"
            assert resolved.role == "admin"
        checks.append("valid_session_resolved")

        with engine.begin() as conn:
            _update_membership_legacy_role(conn, MEMBERSHIP_A_ID, "viewer")
        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.role == "admin"
        checks.append("stale_legacy_role_ignored")

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE auth_membership_roles
                    SET role_key = 'household.viewer', updated_at = CURRENT_TIMESTAMP
                    WHERE household_id = '1' AND membership_id = :membership_id
                    """
                ),
                {"membership_id": MEMBERSHIP_A_ID},
            )
        with engine.begin() as conn:
            resolved = resolve_server_session(conn, raw_session)
            assert resolved.role == "viewer"
        checks.append("canonical_role_refreshed_server_side")

        with engine.begin() as conn:
            superuser_session, superuser_context = create_system_server_session(
                conn,
                user_id=SYSTEM_USER_ID,
            )
            assert superuser_session
            assert superuser_context.email == SUPERGEBRUIKER_EMAIL
            assert superuser_context.active_household_id == SUPERGEBRUIKER_HUISHOUDEN_ID
            assert superuser_context.context_type == "system"
            assert superuser_context.role == "owner"
            assert superuser_context.is_platform_superuser is True
            assert _system_membership_count(conn) == 0
        with engine.begin() as conn:
            resolved_superuser = resolve_server_session(conn, superuser_session)
            assert resolved_superuser.email == SUPERGEBRUIKER_EMAIL
            assert resolved_superuser.active_household_id == SUPERGEBRUIKER_HUISHOUDEN_ID
            assert resolved_superuser.is_platform_superuser is True
        checks.append("platform_role_superuser_system_context_allowed")

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE auth_platform_user_roles SET active = FALSE, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :user_id AND role_key = 'platform.superuser'
                    """
                ),
                {"user_id": SYSTEM_USER_ID},
            )
        with engine.begin() as conn:
            _expect_http_status(403, lambda: resolve_server_session(conn, superuser_session))
            _expect_http_status(
                403,
                lambda: create_system_server_session(conn, user_id=SYSTEM_USER_ID),
            )
        checks.append("inactive_superuser_role_blocks_system_context")

        with engine.begin() as conn:
            _insert_membership(
                conn,
                membership_id=MEMBERSHIP_A_ZERO_ID,
                user_id=USER_A_ID,
                email=USER_A_EMAIL,
                household_id="0",
                legacy_role="owner",
                canonical_role="household.owner",
            )
            _expect_http_status(
                403,
                lambda: create_server_session(
                    conn,
                    user_id=USER_A_ID,
                    active_household_id="0",
                ),
            )
        checks.append("household_zero_blocked_for_regular_user")

        with engine.begin() as conn:
            _expect_http_status(
                403,
                lambda: create_server_session(
                    conn,
                    user_id=USER_A_ID,
                    active_household_id="2",
                ),
            )
        checks.append("cross_household_membership_blocked")

        with engine.begin() as conn:
            revoke_server_session(conn, raw_session)
        with engine.begin() as conn:
            _expect_http_status(401, lambda: resolve_server_session(conn, raw_session))
        checks.append("revoked_session_401")
    finally:
        with engine.begin() as conn:
            _cleanup_database(conn)

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("SERVER_SESSION_SECURITY_POSTGRESQL_GREEN")
    print("SERVER_SESSION_SECURITY_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
