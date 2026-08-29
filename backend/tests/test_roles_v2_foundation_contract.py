from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.services.authorization_foundation_service import (
    ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS,
    ADMIN_PERMISSIONS,
    FRONTTEAM_PLATFORM_PERMISSIONS,
    HOUSEHOLD_PERMISSIONS,
    IP_OWNER_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    V2_PLATFORM_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    ensure_authorization_foundation,
    evaluate_platform_permission,
    permissions_for_session_role,
    resolve_active_platform_role_keys,
)
from app.services.roles_v2_schema_foundation import (
    ACCOUNT_STATUSES,
    HOUSEHOLD_CONTEXT_TYPES,
    ensure_roles_v2_account_and_household_foundation,
)
from app.services.server_session_service import ServerSessionContext, public_session_payload
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from app.testing.authorization_schema_fixture import install_authorization_schema


def make_engine():
    return create_engine("sqlite+pysqlite:///:memory:")


def column_contract(columns):
    return [
        (
            column["name"],
            str(column["type"]),
            bool(column["nullable"]),
            column.get("default"),
            int(column.get("primary_key") or 0),
        )
        for column in columns
    ]


def test_v2_platform_roles_and_permissions_are_seeded_idempotently():
    engine = make_engine()
    with engine.begin() as conn:
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key)
            VALUES ('existing-superuser', 'platform.superuser')
        """))
        conn.execute(text("""
            INSERT INTO auth_membership_roles(
                household_id, membership_id, role_key
            ) VALUES ('existing-household', 'existing-member', 'household.owner')
        """))
        before_platform = conn.execute(text(
            "SELECT user_id, role_key, active FROM auth_platform_user_roles"
        )).all()
        before_household = conn.execute(text(
            "SELECT household_id, membership_id, role_key, active "
            "FROM auth_membership_roles"
        )).all()
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        after_platform = conn.execute(text(
            "SELECT user_id, role_key, active FROM auth_platform_user_roles"
        )).all()
        after_household = conn.execute(text(
            "SELECT household_id, membership_id, role_key, active "
            "FROM auth_membership_roles"
        )).all()
        roles = dict(conn.execute(text(
            "SELECT role_key, scope FROM auth_roles"
        )).all())
        scopes = dict(conn.execute(text(
            "SELECT permission_key, scope FROM auth_permissions"
        )).all())

    assert roles["platform.frontteam"] == "platform"
    assert roles["platform.platform_admin"] == "platform"
    assert roles["platform.ip_owner"] == "platform"
    assert all(scopes[key] == "platform" for key in V2_PLATFORM_PERMISSIONS)
    assert before_platform == after_platform == [
        ("existing-superuser", "platform.superuser", 1)
    ]
    assert before_household == after_household == [
        ("existing-household", "existing-member", "household.owner", 1)
    ]


def test_only_one_active_ip_owner_can_exist():
    engine = make_engine()
    with engine.begin() as conn:
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key)
            VALUES ('owner-1', 'platform.ip_owner')
        """))
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key)
                VALUES ('owner-2', 'platform.ip_owner')
            """))


def test_active_platform_role_resolution_uses_only_registered_active_platform_roles():
    engine = make_engine()
    with engine.begin() as conn:
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('platform-user', 'platform.platform_admin', 1),
              ('platform-user', 'platform.frontteam', 0),
              ('platform-user', 'household.admin', 1)
        """))
        conn.execute(text("""
            UPDATE auth_roles SET active = 0
            WHERE role_key = 'platform.support_read'
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('platform-user', 'platform.support_read', 1)
        """))

        roles = resolve_active_platform_role_keys(conn, 'platform-user')

    assert roles == frozenset({'platform.platform_admin'})


def test_v2_platform_role_permission_boundaries():
    assert "platform.system_household.access" in V2_SUPERUSER_TARGET_PERMISSIONS
    assert "platform.system_household.access" in IP_OWNER_PERMISSIONS
    assert "platform.system_household.access" not in PLATFORM_ADMIN_PERMISSIONS
    assert "platform.system_household.access" not in FRONTTEAM_PLATFORM_PERMISSIONS
    assert "platform.special_roles.manage" in IP_OWNER_PERMISSIONS
    assert "platform.special_roles.manage" not in V2_SUPERUSER_TARGET_PERMISSIONS
    assert "platform.special_roles.manage" not in PLATFORM_ADMIN_PERMISSIONS
    assert "platform.special_roles.manage" not in FRONTTEAM_PLATFORM_PERMISSIONS
    assert IP_OWNER_PERMISSIONS == (
        V2_SUPERUSER_TARGET_PERMISSIONS
        | PLATFORM_ADMIN_PERMISSIONS
        | {"platform.special_roles.manage"}
    )


def test_frontteam_external_permissions_only_link_existing_products():
    assert {
        "platform.external_products.view",
        "platform.external_products.search",
        "platform.external_products.link_existing",
    } <= FRONTTEAM_PLATFORM_PERMISSIONS
    assert "platform.catalog.update" not in FRONTTEAM_PLATFORM_PERMISSIONS
    assert "platform.catalog.manage" not in FRONTTEAM_PLATFORM_PERMISSIONS
    assert "platform.gpc.manage" not in FRONTTEAM_PLATFORM_PERMISSIONS
    assert "platform.external_sources.manage" not in FRONTTEAM_PLATFORM_PERMISSIONS


def test_legacy_and_regular_household_role_mappings_are_preserved():
    assert {
        "household.viewer",
        "household.member",
        "household.advanced_member",
        "household.admin",
        "household.owner",
        "household.frontteam",
    } <= ROLE_PERMISSIONS.keys()
    assert ROLE_PERMISSIONS["household.admin"] == ADMIN_PERMISSIONS
    assert ROLE_PERMISSIONS["household.member"] <= set(HOUSEHOLD_PERMISSIONS)


def test_household_and_account_foundation_validates_canonical_schema_idempotently():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL DEFAULT 'regular'
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                account_status TEXT NOT NULL DEFAULT 'active',
                password_hash TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('0', 'Systeem', 'system'), ('1', 'Regulier', 'regular')
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, password, account_status, password_hash)
            VALUES ('u1', 'fixture@example.invalid', 'legacy-value', 'active', NULL)
        """))

        ensure_roles_v2_account_and_household_foundation(conn)
        ensure_roles_v2_account_and_household_foundation(conn)
        households = dict(conn.execute(text(
            "SELECT id, context_type FROM household_registry ORDER BY id"
        )).all())
        account = conn.execute(text(
            "SELECT account_status, password, password_hash FROM app_users WHERE id = 'u1'"
        )).mappings().one()

    assert HOUSEHOLD_CONTEXT_TYPES == {"regular", "system"}
    assert households == {"0": "system", "1": "regular"}
    assert ACCOUNT_STATUSES == {"active", "disabled", "suspended"}
    assert account["account_status"] == "active"
    assert account["password"] == "legacy-value"
    assert account["password_hash"] is None


def test_account_and_household_foundation_rejects_invalid_canonical_values():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                account_status TEXT NOT NULL,
                password_hash TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('x', 'Ongeldig', 'private')
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, password, account_status, password_hash)
            VALUES ('u1', 'invalid@example.invalid', 'legacy', 'blocked', NULL)
        """))

        with pytest.raises(RuntimeError, match="ongeldige context_type"):
            ensure_roles_v2_account_and_household_foundation(conn)

        conn.execute(text(
            "UPDATE household_registry SET context_type = 'regular' WHERE id = 'x'"
        ))
        with pytest.raises(RuntimeError, match="ongeldige account_status"):
            ensure_roles_v2_account_and_household_foundation(conn)


def test_roles_v2_foundation_does_not_change_server_session_schema_or_rows():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL DEFAULT 'regular'
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                account_status TEXT NOT NULL DEFAULT 'active',
                password_hash TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE server_sessions (
                id VARCHAR(64) PRIMARY KEY,
                session_token_hash VARCHAR(64) NOT NULL UNIQUE,
                user_id VARCHAR(64) NOT NULL,
                active_household_id VARCHAR(64) NOT NULL,
                issued_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                session_version INTEGER NOT NULL DEFAULT 1,
                revoked_at TIMESTAMP NULL,
                replaced_by_session_id VARCHAR(64) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO server_sessions(
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at
            ) VALUES ('s1', 'hash1', 'u1', '1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))

        before_columns = inspect(conn).get_columns("server_sessions")
        before_indexes = inspect(conn).get_indexes("server_sessions")
        before_rows = conn.execute(text("SELECT * FROM server_sessions")).all()
        ensure_roles_v2_account_and_household_foundation(conn)
        after_columns = inspect(conn).get_columns("server_sessions")
        after_indexes = inspect(conn).get_indexes("server_sessions")
        after_rows = conn.execute(text("SELECT * FROM server_sessions")).all()

    assert column_contract(before_columns) == column_contract(after_columns)
    assert before_indexes == after_indexes
    assert before_rows == after_rows
    active_household = next(
        column for column in after_columns if column["name"] == "active_household_id"
    )
    assert active_household["nullable"] is False


def test_active_v2_superuser_permissions_and_public_payload_are_exact():
    expected = set(V2_SUPERUSER_TARGET_PERMISSIONS)
    assert ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS == expected
    assert ROLE_PERMISSIONS["platform.superuser"] == expected
    assert permissions_for_session_role("", platform_superuser=True) == expected
    assert not (expected & PLATFORM_ADMIN_PERMISSIONS)
    assert "platform.special_roles.manage" not in expected

    now = datetime.now(timezone.utc)
    payload = public_session_payload(ServerSessionContext(
        session_id="session-id",
        user_id="superuser-id",
        email=SUPERGEBRUIKER_EMAIL,
        active_household_id="0",
        context_type="system",
        role="owner",
        session_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
        is_platform_superuser=True,
    ))
    expected_public_permissions = ROLE_PERMISSIONS["household.owner"] | expected
    assert set(payload["permissions"]) == expected_public_permissions
    assert set(payload["supported_permissions"]) == expected_public_permissions
    assert payload["is_platform_superuser"] is True
    assert not (PLATFORM_ADMIN_PERMISSIONS & set(payload["permissions"]))
    assert "platform.special_roles.manage" not in payload["permissions"]


def test_fixed_superuser_email_alone_does_not_grant_public_superuser_rights():
    now = datetime.now(timezone.utc)
    payload = public_session_payload(ServerSessionContext(
        session_id="session-id",
        user_id="email-only-id",
        email=SUPERGEBRUIKER_EMAIL,
        active_household_id="0",
        context_type="system",
        role="owner",
        session_version=1,
        issued_at=now,
        expires_at=now + timedelta(hours=1),
    ))

    assert payload["is_platform_superuser"] is False
    assert set(payload["permissions"]) == ROLE_PERMISSIONS["household.owner"]
    assert not ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS & set(payload["permissions"])


def test_existing_platform_superuser_is_cut_over_to_exact_v2_target_permissions():
    engine = make_engine()
    with engine.begin() as conn:
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key)
            VALUES ('existing-superuser', 'platform.superuser')
        """))
        for permission_key in V2_PLATFORM_PERMISSIONS:
            decision = evaluate_platform_permission(
                conn,
                user_id="existing-superuser",
                permission_key=permission_key,
            )
            assert decision.allowed is (
                permission_key in V2_SUPERUSER_TARGET_PERMISSIONS
            ), permission_key
        for permission_key in V2_SUPERUSER_TARGET_PERMISSIONS:
            decision = evaluate_platform_permission(
                conn,
                user_id="existing-superuser",
                permission_key=permission_key,
            )
            assert decision.allowed is True, permission_key
        for permission_key in PLATFORM_ADMIN_PERMISSIONS:
            decision = evaluate_platform_permission(
                conn,
                user_id="existing-superuser",
                permission_key=permission_key,
            )
            assert decision.allowed is False, permission_key
        special_role = evaluate_platform_permission(
            conn,
            user_id="existing-superuser",
            permission_key="platform.special_roles.manage",
        )
        assert special_role.allowed is False
