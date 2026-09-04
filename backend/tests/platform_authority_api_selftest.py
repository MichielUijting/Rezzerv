"""P0 F3-06: platform authority through real server sessions and PostgreSQL API.

The authority proves platform administration at the production API boundary. It
uses opaque login cookies, live canonical permissions, the Alembic PostgreSQL
schema and a DML-only runtime. No authorization or business service is mocked.
It also proves that platform-role changes do not silently create or upgrade
household memberships.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api import platform_authorizations_routes
from app.api import platform_sessions_routes
from app.api import platform_users_routes
from app.api.server_session_routes import SessionApiConfiguration, create_server_session_router
from app.services import session_request_context
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.session_request_context import (
    bind_current_actor_from_request_session_if_available,
    bind_request_session,
    reset_request_session,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
    seed_household,
    seed_user,
)

PASSWORD = "F3PlatformAuthority123!"
TARGET_HOUSEHOLD = "f3-platform-target-household"
ISOLATION_HOUSEHOLD = "f3-platform-isolation-household"
IP_OWNER_ID = "f3-platform-ip-owner"
IP_OWNER_EMAIL = "f3-platform-ip-owner@rezzerv.local"
PLATFORM_ADMIN_ID = "f3-platform-admin"
PLATFORM_ADMIN_EMAIL = "f3-platform-admin@rezzerv.local"
SUPERUSER_ID = "f3-platform-superuser"
SUPERUSER_EMAIL = "f3-platform-superuser@rezzerv.local"
TARGET_ADMIN_ID = "f3-platform-target-admin"
TARGET_ADMIN_EMAIL = "f3-platform-target-admin@rezzerv.local"
REVOKE_TARGET_ID = "f3-platform-revoke-target"
REVOKE_TARGET_EMAIL = "f3-platform-revoke-target@rezzerv.local"


def _assign_platform_role(conn, user_id: str, role_key: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO auth_platform_user_roles (user_id, role_key, active)
            VALUES (:user_id, :role_key, 1)
            """
        ),
        {"user_id": user_id, "role_key": role_key},
    )


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id=TARGET_HOUSEHOLD,
        household_name="F3 platform doelhuishouden",
        admin_id=TARGET_ADMIN_ID,
        admin_email=TARGET_ADMIN_EMAIL,
        admin_password=PASSWORD,
        admin_membership_id="f3-platform-target-admin-membership",
        member_id=REVOKE_TARGET_ID,
        member_email=REVOKE_TARGET_EMAIL,
        member_password=PASSWORD,
        member_membership_id="f3-platform-revoke-target-membership",
    )
    seed_admin_member_household(
        engine,
        household_id=ISOLATION_HOUSEHOLD,
        household_name="F3 platform isolatiehuishouden",
        admin_id="f3-platform-isolation-admin",
        admin_email="f3-platform-isolation-admin@rezzerv.local",
        admin_password=PASSWORD,
        admin_membership_id="f3-platform-isolation-admin-membership",
        member_id="f3-platform-isolation-member",
        member_email="f3-platform-isolation-member@rezzerv.local",
        member_password=PASSWORD,
        member_membership_id="f3-platform-isolation-member-membership",
    )

    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        system_exists = int(
            conn.execute(
                text("SELECT COUNT(*) FROM household_registry WHERE id = '0'")
            ).scalar_one()
        )
        if system_exists == 0:
            seed_household(conn, household_id="0", name="Systeem", context_type="system")

        seed_user(conn, user_id=IP_OWNER_ID, email=IP_OWNER_EMAIL, password=PASSWORD)
        seed_user(
            conn,
            user_id=PLATFORM_ADMIN_ID,
            email=PLATFORM_ADMIN_EMAIL,
            password=PASSWORD,
        )
        seed_user(conn, user_id=SUPERUSER_ID, email=SUPERUSER_EMAIL, password=PASSWORD)

        _assign_platform_role(conn, IP_OWNER_ID, "platform.ip_owner")
        _assign_platform_role(conn, PLATFORM_ADMIN_ID, "platform.platform_admin")
        _assign_platform_role(conn, SUPERUSER_ID, "platform.superuser")


def _application(engine) -> FastAPI:
    session_request_context.engine = engine
    platform_sessions_routes.engine = engine
    platform_users_routes.engine = engine
    platform_authorizations_routes.engine = engine

    app = FastAPI()

    @app.middleware("http")
    async def server_session_request_context(request: Request, call_next):
        token = bind_request_session(request)
        try:
            bind_current_actor_from_request_session_if_available()
            return await call_next(request)
        except Exception as exc:
            if isinstance(exc, HTTPException):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
            raise
        finally:
            reset_request_session(token)

    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False),
        )
    )
    app.include_router(platform_sessions_routes.router)
    app.include_router(platform_users_routes.router)
    app.include_router(platform_authorizations_routes.router)
    return app


def _login(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            assert bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            ) is False
        checks.append("postgresql_dml_only_runtime")

        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as normal_admin:
            normal_session = _login(normal_admin, TARGET_ADMIN_EMAIL)
            assert normal_session["active_household_id"] == TARGET_HOUSEHOLD
            assert normal_session["context_type"] == "regular"

            forbidden_sessions = normal_admin.get("/api/platform/sessions")
            assert forbidden_sessions.status_code == 403, forbidden_sessions.text
            forbidden_users = normal_admin.get("/api/platform/users")
            assert forbidden_users.status_code == 403, forbidden_users.text
            forbidden_authorizations = normal_admin.get("/api/platform/authorizations")
            assert forbidden_authorizations.status_code == 403, forbidden_authorizations.text
        checks.append("regular_household_admin_has_no_platform_authority")

        with TestClient(app) as superuser:
            superuser_session = _login(superuser, SUPERUSER_EMAIL)
            assert superuser_session["active_household_id"] == "0"
            assert superuser_session["context_type"] == "system"
            cannot_mutate_special_role = superuser.post(
                f"/api/platform/authorizations/users/{TARGET_ADMIN_ID}/platform-admin/grant"
            )
            assert cannot_mutate_special_role.status_code == 403, cannot_mutate_special_role.text
        checks.append("superuser_cannot_assume_ip_owner_special_role_authority")

        with TestClient(app) as platform_admin:
            platform_session = _login(platform_admin, PLATFORM_ADMIN_EMAIL)
            assert platform_session["active_household_id"] is None
            assert platform_session["context_type"] == "none"
            assert platform_session["is_platform_admin"] is True

            session_inventory = platform_admin.get("/api/platform/sessions")
            assert session_inventory.status_code == 200, session_inventory.text
            session_payload = session_inventory.json()
            assert session_payload["household_context_used"] is False
            assert session_payload["context_type"] == "none"
            rendered_sessions = repr(session_payload).lower()
            assert "session_token_hash" not in rendered_sessions
            assert TARGET_HOUSEHOLD.lower() not in rendered_sessions
            assert ISOLATION_HOUSEHOLD.lower() not in rendered_sessions

            user_inventory = platform_admin.get("/api/platform/users")
            assert user_inventory.status_code == 200, user_inventory.text
            assert user_inventory.json()["household_context_used"] is False

            authorization_inventory = platform_admin.get("/api/platform/authorizations")
            assert authorization_inventory.status_code == 200, authorization_inventory.text
            assert authorization_inventory.json()["household_context_used"] is False

            denied_special_role = platform_admin.post(
                f"/api/platform/authorizations/users/{TARGET_ADMIN_ID}/platform-admin/grant"
            )
            assert denied_special_role.status_code == 403, denied_special_role.text
        checks.append("platform_admin_uses_none_context_and_safe_platform_projection")
        checks.append("platform_admin_cannot_mutate_ip_owner_only_special_roles")

        with TestClient(app) as revoke_target:
            target_session = _login(revoke_target, REVOKE_TARGET_EMAIL)
            assert target_session["active_household_id"] == TARGET_HOUSEHOLD
            with engine.begin() as conn:
                target_session_id = str(
                    conn.execute(
                        text(
                            """
                            SELECT id
                            FROM server_sessions
                            WHERE user_id = :user_id
                              AND revoked_at IS NULL
                            ORDER BY issued_at DESC
                            LIMIT 1
                            """
                        ),
                        {"user_id": REVOKE_TARGET_ID},
                    ).scalar_one()
                )

            with TestClient(app) as platform_admin:
                _login(platform_admin, PLATFORM_ADMIN_EMAIL)
                revoked = platform_admin.post(
                    f"/api/platform/sessions/{target_session_id}/revoke"
                )
                assert revoked.status_code == 200, revoked.text
                assert revoked.json()["item"]["session_id"] == target_session_id
                still_alive = platform_admin.get("/api/session")
                assert still_alive.status_code == 200, still_alive.text
                assert still_alive.json()["context_type"] == "none"

            rejected_after_revoke = revoke_target.get("/api/session")
            assert rejected_after_revoke.status_code == 401, rejected_after_revoke.text
        checks.append("platform_admin_revokes_target_session_without_revoking_self")

        with engine.begin() as conn:
            memberships_before = conn.execute(
                text(
                    """
                    SELECT household_id, role
                    FROM household_memberships
                    WHERE lower(user_email) = :email
                    ORDER BY household_id
                    """
                ),
                {"email": TARGET_ADMIN_EMAIL},
            ).mappings().all()
            assert len(memberships_before) == 1, memberships_before
            assert str(memberships_before[0]["household_id"]) == TARGET_HOUSEHOLD
            assert str(memberships_before[0]["role"]) == "admin"

        with TestClient(app) as ip_owner:
            owner_session = _login(ip_owner, IP_OWNER_EMAIL)
            assert owner_session["active_household_id"] == "0"
            assert owner_session["context_type"] == "system"
            assert owner_session["is_ip_owner"] is True

            inventory = ip_owner.get("/api/platform/authorizations")
            assert inventory.status_code == 200, inventory.text
            assert inventory.json()["can_manage_special_roles"] is True

            granted = ip_owner.post(
                f"/api/platform/authorizations/users/{TARGET_ADMIN_ID}/platform-admin/grant"
            )
            assert granted.status_code == 200, granted.text
            granted_item = granted.json()["item"]
            assert "platform.platform_admin" in granted_item["platform_role_keys"]
            assert granted.json()["household_context_used"] is False
        checks.append("ip_owner_grants_special_role_through_real_api")

        with engine.begin() as conn:
            memberships_after = conn.execute(
                text(
                    """
                    SELECT household_id, role
                    FROM household_memberships
                    WHERE lower(user_email) = :email
                    ORDER BY household_id
                    """
                ),
                {"email": TARGET_ADMIN_EMAIL},
            ).mappings().all()
            assert memberships_after == memberships_before

            isolation_memberships = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM household_memberships
                        WHERE lower(user_email) = :email
                          AND household_id = :household_id
                        """
                    ),
                    {"email": TARGET_ADMIN_EMAIL, "household_id": ISOLATION_HOUSEHOLD},
                ).scalar_one()
            )
            assert isolation_memberships == 0

            active_role = conn.execute(
                text(
                    """
                    SELECT active
                    FROM auth_platform_user_roles
                    WHERE user_id = :user_id
                      AND role_key = 'platform.platform_admin'
                    """
                ),
                {"user_id": TARGET_ADMIN_ID},
            ).scalar_one()
            assert bool(active_role) is True

            audit = conn.execute(
                text(
                    """
                    SELECT actor_user_id, action, object_type, object_id, reason
                    FROM auth_audit_log
                    WHERE object_id = :user_id
                      AND action = 'platform.role.granted'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"user_id": TARGET_ADMIN_ID},
            ).mappings().one()
            assert str(audit["actor_user_id"]) == IP_OWNER_ID
            assert audit["object_type"] == "platform_user_role"
            assert audit["reason"] == "platform.special_roles.manage"
        checks.append("platform_role_change_is_audited_and_does_not_change_household_membership")

        with TestClient(app) as target_after_role_change:
            login_after_role_change = _login(target_after_role_change, TARGET_ADMIN_EMAIL)
            assert login_after_role_change["context_type"] == "none"
            assert login_after_role_change["active_household_id"] is None
            forbidden_household_projection = target_after_role_change.get(
                f"/api/households/{ISOLATION_HOUSEHOLD}/almost-out"
            )
            assert forbidden_household_projection.status_code in {403, 404}, forbidden_household_projection.text
        checks.append("platform_role_does_not_create_cross_household_access")

        for check in checks:
            print(f"PASS {check}")
        print(f"RESULT {len(checks)}/9 checks passed")
        assert len(checks) == 9
        print("PLATFORM_AUTHORITY_API_POSTGRESQL_GREEN")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run())
