import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_HOUSEHOLD_ID,
    FRONTTEAM_HOUSEHOLD_NAME,
    ensure_frontteam_household_for_session_runtime,
)
from app.services.server_session_service import (
    create_server_session,
    create_system_server_session,
    public_session_payload,
    resolve_server_session,
)


def build_connection():
    engine = create_engine("sqlite:///:memory:")
    conn = engine.connect()
    conn.execute(text("""
        CREATE TABLE household_registry (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            context_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        INSERT INTO household_registry(id, naam, context_type)
        VALUES ('1', 'Normaal huishouden', 'regular')
    """))
    conn.execute(text("""
        CREATE TABLE app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE
        )
    """))
    conn.execute(text("""
        CREATE TABLE household_memberships (
            user_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, household_id)
        )
    """))
    ensure_authorization_foundation(conn)
    conn.execute(text("""
        INSERT INTO app_users(id, email)
        VALUES
          ('front-active', 'front-active@example.test'),
          ('front-inactive', 'front-inactive@example.test'),
          ('regular-admin', 'regular-admin@example.test')
    """))
    conn.execute(text("""
        INSERT INTO auth_platform_user_roles(user_id, role_key, active)
        VALUES
          ('front-active', 'platform.frontteam', 1),
          ('front-inactive', 'platform.frontteam', 0)
    """))
    conn.execute(text("""
        INSERT INTO household_memberships(user_id, household_id, role)
        VALUES ('front-active', '1', 'admin')
    """))
    conn.execute(text("""
        INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
        VALUES ('1', 'front-active', 'household.admin')
    """))
    conn.commit()
    return engine, conn


def test_frontteam_provisioning_creates_regular_admin_projection_idempotently():
    engine, conn = build_connection()
    try:
        first = ensure_frontteam_household_for_session_runtime(conn)
        second = ensure_frontteam_household_for_session_runtime(conn)

        household = conn.execute(text("""
            SELECT naam, context_type FROM household_registry
            WHERE id = :household_id
        """), {"household_id": FRONTTEAM_HOUSEHOLD_ID}).mappings().one()
        membership = conn.execute(text("""
            SELECT hm.role, hm.status, mr.role_key, mr.active
            FROM household_memberships hm
            JOIN auth_membership_roles mr
              ON mr.household_id = hm.household_id
             AND mr.membership_id = hm.user_id
            WHERE hm.user_id = 'front-active'
              AND hm.household_id = :household_id
        """), {"household_id": FRONTTEAM_HOUSEHOLD_ID}).mappings().one()
        inactive_count = conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE user_id = 'front-inactive'
              AND household_id = :household_id
        """), {"household_id": FRONTTEAM_HOUSEHOLD_ID}).scalar_one()
        original_membership_count = conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE user_id = 'front-active' AND household_id = '1'
        """)).scalar_one()

        assert first.active_frontteam_users == 1
        assert first.memberships_created == 1
        assert second.active_frontteam_users == 1
        assert second.memberships_updated == 1
        assert household["naam"] == FRONTTEAM_HOUSEHOLD_NAME
        assert household["context_type"] == "regular"
        assert membership["role"] == "admin"
        assert membership["status"] == "active"
        assert membership["role_key"] == "household.admin"
        assert membership["active"] == 1
        assert inactive_count == 0
        assert original_membership_count == 1
    finally:
        conn.close()
        engine.dispose()


def test_frontteam_regular_session_exposes_platform_permissions_without_raw_roles():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        raw_session_id, created = create_server_session(
            conn,
            user_id="front-active",
            active_household_id=FRONTTEAM_HOUSEHOLD_ID,
        )
        resolved = resolve_server_session(conn, raw_session_id)
        payload = public_session_payload(resolved)

        assert created.context_type == resolved.context_type == "regular"
        assert created.active_household_id == resolved.active_household_id == FRONTTEAM_HOUSEHOLD_ID
        assert created.role == resolved.role == "admin"
        assert created.is_frontteam is resolved.is_frontteam is True
        assert payload["is_frontteam"] is True
        assert payload["is_platform_superuser"] is False
        assert payload["active_household_name"] == FRONTTEAM_HOUSEHOLD_NAME
        for permission in (
            "platform.external_products.view",
            "platform.external_products.search",
            "platform.external_products.link_existing",
        ):
            assert payload["permissions"][permission] is True
        assert "platform_roles" not in payload
    finally:
        conn.close()
        engine.dispose()


def test_frontteam_session_fails_closed_immediately_after_platform_role_revocation():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        raw_session_id, _ = create_server_session(
            conn,
            user_id="front-active",
            active_household_id=FRONTTEAM_HOUSEHOLD_ID,
        )
        conn.execute(text("""
            UPDATE auth_platform_user_roles SET active = 0
            WHERE user_id = 'front-active' AND role_key = 'platform.frontteam'
        """))

        with pytest.raises(HTTPException) as exc:
            resolve_server_session(conn, raw_session_id)

        assert exc.value.status_code == 403
        assert exc.value.detail == "Geen geldige accountcontext beschikbaar."
    finally:
        conn.close()
        engine.dispose()


def test_reserved_frontteam_household_never_grants_authority_without_platform_role():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)
        conn.execute(text("""
            INSERT INTO household_memberships(user_id, household_id, role)
            VALUES ('regular-admin', :household_id, 'admin')
        """), {"household_id": FRONTTEAM_HOUSEHOLD_ID})
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES (:household_id, 'regular-admin', 'household.admin')
        """), {"household_id": FRONTTEAM_HOUSEHOLD_ID})

        with pytest.raises(HTTPException) as exc:
            create_server_session(
                conn,
                user_id="regular-admin",
                active_household_id=FRONTTEAM_HOUSEHOLD_ID,
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == "Geen geldige accountcontext beschikbaar."
    finally:
        conn.close()
        engine.dispose()


def test_active_frontteam_role_cannot_select_an_unrelated_regular_household():
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)

        with pytest.raises(HTTPException) as exc:
            create_server_session(
                conn,
                user_id="front-active",
                active_household_id="1",
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == "Geen geldige accountcontext beschikbaar."
    finally:
        conn.close()
        engine.dispose()

@pytest.mark.parametrize(
    "system_role",
    [
        "platform.superuser",
        "platform.ip_owner",
    ],
)
def test_frontteam_system_role_conflict_fails_closed_in_session_service(system_role):
    engine, conn = build_connection()
    try:
        ensure_frontteam_household_for_session_runtime(conn)

        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('0', 'Systeemhuishouden', 'system')
        """))

        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('front-active', :role_key, 1)
        """), {"role_key": system_role})

        with pytest.raises(HTTPException) as exc:
            create_system_server_session(
                conn,
                user_id="front-active",
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == "Geen geldige accountcontext beschikbaar."
    finally:
        conn.close()
        engine.dispose()
