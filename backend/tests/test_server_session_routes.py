import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)
from app.services.authorization_foundation_service import (
    ROLE_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_HOUSEHOLD_ID,
    FRONTTEAM_PERSONAL_HOUSEHOLD_NAME,
    resolve_frontteam_personal_household_id,
)
from app.services.server_session_service import resolve_server_session
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
    seed_household,
    seed_membership,
    seed_user,
)


def _seed_membership(conn, *, membership_id, household_id, user_id, email, role):
    seed_membership(
        conn,
        membership_id=membership_id,
        household_id=household_id,
        user_id=user_id,
        email=email,
        role=role,
    )


def build_client(*, cookie_secure: bool = False, cookie_samesite: str = "lax"):
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    with engine.begin() as conn:
        ensure_authorization_foundation(conn)
        seed_household(conn, household_id="0", name="Systeemhuishouden", context_type="system")
        seed_household(conn, household_id="1", name="Huishouden 1", context_type="regular")
        seed_household(conn, household_id="2", name="Huishouden 2", context_type="regular")
        seed_household(
            conn,
            household_id=FRONTTEAM_HOUSEHOLD_ID,
            name="Historisch Frontteam",
            context_type="regular",
        )
        users = (
            ("u1", "admin@rezzerv.local"),
            ("u2", "lid@rezzerv.local"),
            ("u3", "zero@rezzerv.local"),
            ("u-super", SUPERGEBRUIKER_EMAIL),
            ("u-platform", "platform@example.test"),
            ("u-none", "none@example.test"),
            ("u-frontteam", "frontteam@example.test"),
            ("u-ip-owner", "ip-owner@example.test"),
            ("u-inactive-platform", "inactive-platform@example.test"),
        )
        for user_id, email in users:
            seed_user(conn, user_id=user_id, email=email, password="Rezzerv123")

        _seed_membership(
            conn,
            membership_id="m-u1-h1",
            household_id="1",
            user_id="u1",
            email="admin@rezzerv.local",
            role="admin",
        )
        _seed_membership(
            conn,
            membership_id="m-u1-h2",
            household_id="2",
            user_id="u1",
            email="admin@rezzerv.local",
            role="member",
        )
        _seed_membership(
            conn,
            membership_id="m-u2-h2",
            household_id="2",
            user_id="u2",
            email="lid@rezzerv.local",
            role="member",
        )
        _seed_membership(
            conn,
            membership_id="m-u-platform-h1",
            household_id="1",
            user_id="u-platform",
            email="platform@example.test",
            role="member",
        )
        _seed_membership(
            conn,
            membership_id="m-u3-h0",
            household_id="0",
            user_id="u3",
            email="zero@rezzerv.local",
            role="owner",
        )
        _seed_membership(
            conn,
            membership_id="m-u-frontteam-legacy",
            household_id=FRONTTEAM_HOUSEHOLD_ID,
            user_id="u-frontteam",
            email="frontteam@example.test",
            role="admin",
        )
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('u-super', 'platform.superuser', TRUE),
              ('u-platform', 'platform.platform_admin', TRUE),
              ('u-frontteam', 'platform.frontteam', TRUE),
              ('u-ip-owner', 'platform.ip_owner', TRUE),
              ('u-inactive-platform', 'platform.platform_admin', FALSE)
        """))

    app = FastAPI()
    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(
                cookie_secure=cookie_secure,
                cookie_samesite=cookie_samesite,
            ),
        )
    )
    base_url = "https://testserver" if cookie_secure else "http://testserver"
    return TestClient(app, base_url=base_url), engine


def test_valid_login_sets_httponly_cookie_and_returns_no_token():
    client, engine = build_client()
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": "ADMIN@REZZERV.LOCAL", "password": "Rezzerv123"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["id"] == "u1"
        assert response.json()["active_household_id"] == "1"
        assert "token" not in response.json()
        assert "session_id" not in response.json()
        set_cookie = response.headers["set-cookie"].lower()
        assert "rezzerv_session=" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("admin@rezzerv.local", "fout"),
        ("unknown@example.test", "Rezzerv123"),
    ],
)
def test_invalid_credentials_return_401_without_cookie(email, password):
    client, engine = build_client()
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert response.status_code == 401
        assert "rezzerv_session=" not in response.headers.get("set-cookie", "").lower()
    finally:
        engine.dispose()


def test_member_login_keeps_regular_household_context():
    client, engine = build_client()
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": "lid@rezzerv.local", "password": "Rezzerv123"},
        )
        raw_session_id = response.cookies.get("rezzerv_session")
        with engine.begin() as conn:
            context = resolve_server_session(conn, raw_session_id)
        assert response.status_code == 200
        assert context.context_type == "regular"
        assert context.active_household_id == "2"
        assert context.role == "member"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("email", "is_superuser"),
    [
        (SUPERGEBRUIKER_EMAIL, True),
        ("ip-owner@example.test", False),
    ],
)
def test_system_platform_roles_login_without_household_membership(email, is_superuser):
    client, engine = build_client()
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "Rezzerv123"},
        )
        raw_session_id = response.cookies.get("rezzerv_session")
        with engine.begin() as conn:
            context = resolve_server_session(conn, raw_session_id)
        assert response.status_code == 200
        assert context.context_type == "system"
        assert context.active_household_id == "0"
        assert context.role == "owner"
        assert context.is_platform_superuser is is_superuser
        assert response.json()["is_platform_superuser"] is is_superuser
        assert "platform_roles" not in response.json()
    finally:
        engine.dispose()


def test_frontteam_login_uses_personal_regular_admin_household():
    client, engine = build_client()
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": "frontteam@example.test", "password": "Rezzerv123"},
        )
        raw_session_id = response.cookies.get("rezzerv_session")
        with engine.begin() as conn:
            personal_household_id = resolve_frontteam_personal_household_id(conn, "u-frontteam")
            context = resolve_server_session(conn, raw_session_id)
            legacy_count = conn.execute(text("""
                SELECT COUNT(*) FROM household_memberships
                WHERE id = 'm-u-frontteam-legacy'
            """)).scalar_one()
        payload = response.json()
        assert response.status_code == 200
        assert personal_household_id
        assert personal_household_id != FRONTTEAM_HOUSEHOLD_ID
        assert legacy_count == 0
        assert context.context_type == "regular"
        assert context.active_household_id == personal_household_id
        assert context.role == "admin"
        assert context.is_frontteam is True
        assert payload["active_household_name"] == FRONTTEAM_PERSONAL_HOUSEHOLD_NAME
        assert payload["is_frontteam"] is True
        for permission in (
            "platform.external_products.view",
            "platform.external_products.search",
            "platform.external_products.link_existing",
        ):
            assert payload["permissions"][permission] is True
    finally:
        engine.dispose()


def test_platform_admin_only_login_creates_resolvable_none_session():
    client, engine = build_client()
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": "platform@example.test", "password": "Rezzerv123"},
        )
        raw_session_id = response.cookies.get("rezzerv_session")
        with engine.begin() as conn:
            context = resolve_server_session(conn, raw_session_id)
            stored_household_id = conn.execute(text("""
                SELECT active_household_id FROM server_sessions
                WHERE user_id = 'u-platform' AND revoked_at IS NULL
            """)).scalar_one()
        assert response.status_code == 200
        assert stored_household_id is None
        assert context.context_type == "none"
        assert context.active_household_id is None
        assert context.role is None
        expected_permissions = set(ROLE_PERMISSIONS["platform.platform_admin"])
        assert response.json()["permissions"] == {
            key: True for key in sorted(expected_permissions)
        }
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "email",
    ["none@example.test", "inactive-platform@example.test", "zero@rezzerv.local"],
)
def test_valid_credentials_without_allowed_context_return_403(email):
    client, engine = build_client()
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "Rezzerv123"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    finally:
        engine.dispose()


def test_conflicting_platform_roles_fail_closed_without_creating_new_session():
    client, engine = build_client()
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO auth_platform_user_roles(user_id, role_key, active)
                VALUES ('u-frontteam', 'platform.platform_admin', TRUE)
            """))
        response = client.post(
            "/api/auth/login",
            json={"email": "frontteam@example.test", "password": "Rezzerv123"},
        )
        with engine.begin() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM server_sessions WHERE user_id = 'u-frontteam'
            """)).scalar_one()
        assert response.status_code == 403
        assert count == 0
    finally:
        engine.dispose()


def test_platform_role_revocation_invalidates_existing_session():
    client, engine = build_client()
    try:
        login = client.post(
            "/api/auth/login",
            json={"email": "frontteam@example.test", "password": "Rezzerv123"},
        )
        assert login.status_code == 200
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE auth_platform_user_roles SET active = FALSE
                WHERE user_id = 'u-frontteam' AND role_key = 'platform.frontteam'
            """))
        response = client.get("/api/session")
        assert response.status_code == 403
        assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    finally:
        engine.dispose()


def test_session_endpoint_ignores_stale_legacy_role_and_reflects_canonical_role_update():
    client, engine = build_client()
    try:
        login = client.post(
            "/api/auth/login",
            json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
        )
        assert login.status_code == 200
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE household_memberships SET role = 'member'
                WHERE id = 'm-u1-h1'
            """))
        stale = client.get("/api/session")
        assert stale.status_code == 200
        assert stale.json()["role"] == "admin"

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE auth_membership_roles
                SET role_key = 'household.member'
                WHERE household_id = '1' AND membership_id = 'm-u1-h1'
            """))
        canonical = client.get("/api/session")
        assert canonical.status_code == 200
        assert canonical.json()["role"] == "member"
    finally:
        engine.dispose()


def test_logout_revokes_session_and_clears_cookie():
    client, engine = build_client()
    try:
        login = client.post(
            "/api/auth/login",
            json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
        )
        assert login.status_code == 200
        logout = client.post("/api/auth/logout")
        assert logout.status_code == 204
        assert "rezzerv_session=" in logout.headers.get("set-cookie", "").lower()
        assert client.get("/api/session").status_code == 401
    finally:
        engine.dispose()


def test_new_login_invalidates_previous_cookie():
    first_client, engine = build_client()
    try:
        second_app = FastAPI()
        second_app.include_router(
            create_server_session_router(
                engine,
                SessionApiConfiguration(cookie_secure=False, cookie_samesite="lax"),
            )
        )
        second_client = TestClient(second_app)
        first_login = first_client.post(
            "/api/auth/login",
            json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
        )
        old_cookie = first_login.cookies.get("rezzerv_session")
        second_login = second_client.post(
            "/api/auth/login",
            json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
        )
        assert first_login.status_code == second_login.status_code == 200
        assert second_login.cookies.get("rezzerv_session") != old_cookie
        first_client.cookies.set("rezzerv_session", old_cookie)
        assert first_client.get("/api/session").status_code == 401
        assert second_client.get("/api/session").status_code == 200
    finally:
        engine.dispose()


def test_secure_cookie_can_be_enabled_for_non_local_runtime():
    client, engine = build_client(cookie_secure=True, cookie_samesite="strict")
    try:
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
        )
        assert response.status_code == 200
        set_cookie = response.headers["set-cookie"].lower()
        assert "secure" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=strict" in set_cookie
    finally:
        engine.dispose()
