from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from app.services.authorization_foundation_service import (
    ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS,
    ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS,
    IP_OWNER_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    V2_SUPERUSER_TARGET_PERMISSIONS,
    ensure_authorization_foundation,
    evaluate_platform_permission,
)
from app.services.server_session_service import ServerSessionContext, public_session_payload
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:")


def test_active_superuser_authority_is_exact_v2_target_and_separate_from_admin():
    expected = set(V2_SUPERUSER_TARGET_PERMISSIONS)

    assert ACTIVE_SUPERUSER_PLATFORM_PERMISSIONS == expected
    assert ACTIVE_V1_1_SUPERUSER_PLATFORM_PERMISSIONS == expected
    assert ROLE_PERMISSIONS["platform.superuser"] == expected
    assert not (expected & PLATFORM_ADMIN_PERMISSIONS)
    assert "platform.special_roles.manage" not in expected

    assert ROLE_PERMISSIONS["platform.platform_admin"] == PLATFORM_ADMIN_PERMISSIONS
    assert IP_OWNER_PERMISSIONS == (
        expected | PLATFORM_ADMIN_PERMISSIONS | {"platform.special_roles.manage"}
    )


def test_foundation_reseeds_existing_superuser_from_v1_style_grants_to_exact_v2():
    engine = _engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('existing-superuser', 'platform.superuser', 1)
        """))

        # Simulate a stale pre-cutover technical grant that existed in v1.1.
        conn.execute(text("""
            INSERT INTO auth_role_permissions(role_key, permission_key)
            VALUES ('platform.superuser', 'platform.users.suspend')
        """))

        ensure_authorization_foundation(conn)

        seeded = set(conn.execute(text("""
            SELECT permission_key
            FROM auth_role_permissions
            WHERE role_key = 'platform.superuser'
        """)).scalars().all())
        user_roles = conn.execute(text("""
            SELECT role_key, active
            FROM auth_platform_user_roles
            WHERE user_id = 'existing-superuser'
        """)).all()

    assert seeded == set(V2_SUPERUSER_TARGET_PERMISSIONS)
    assert user_roles == [("platform.superuser", 1)]
    assert "platform.users.suspend" not in seeded
    assert "platform.sessions.revoke" not in seeded
    assert "platform.permissions.manage" not in seeded
    assert "platform.feature_flags.manage" not in seeded


def test_existing_superuser_evaluator_allows_v2_functional_scope_only():
    engine = _engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('existing-superuser', 'platform.superuser', 1)
        """))

        for permission_key in V2_SUPERUSER_TARGET_PERMISSIONS:
            assert evaluate_platform_permission(
                conn,
                user_id="existing-superuser",
                permission_key=permission_key,
            ).allowed is True, permission_key

        for permission_key in PLATFORM_ADMIN_PERMISSIONS:
            assert evaluate_platform_permission(
                conn,
                user_id="existing-superuser",
                permission_key=permission_key,
            ).allowed is False, permission_key

        assert evaluate_platform_permission(
            conn,
            user_id="existing-superuser",
            permission_key="platform.special_roles.manage",
        ).allowed is False


def test_superuser_public_system_session_projects_v2_without_admin_or_special_role_authority():
    now = datetime.now(timezone.utc)
    context = ServerSessionContext(
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
    )

    payload = public_session_payload(context)
    granted = {key for key, allowed in payload["permissions"].items() if allowed}
    expected = set(ROLE_PERMISSIONS["household.owner"]) | set(V2_SUPERUSER_TARGET_PERMISSIONS)

    assert payload["context_type"] == "system"
    assert payload["active_household_id"] == "0"
    assert payload["is_platform_superuser"] is True
    assert granted == expected
    assert set(payload["supported_permissions"]) == expected
    assert not (PLATFORM_ADMIN_PERMISSIONS & granted)
    assert "platform.special_roles.manage" not in granted
    assert "platform_roles" not in payload
