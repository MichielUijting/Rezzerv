import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.authorization_foundation_service import (
    ROLE_PERMISSIONS,
    ensure_authorization_foundation,
)
from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)
from app.services.frontteam_household_provisioning import (
    FRONTTEAM_HOUSEHOLD_ID,
    FRONTTEAM_PERSONAL_HOUSEHOLD_NAME,
    resolve_frontteam_personal_household_id,
)
from app.services.server_session_service import resolve_server_session
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL
from app.testing.server_session_contract import create_server_session_contract_schema


def build_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id VARCHAR(64) PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES
              ('0', 'Systeemhuishouden', 'system'),
              ('1', 'Huishouden 1', 'regular'),
              ('2', 'Huishouden 2', 'regular'),
              ('frontteam', 'Historisch Frontteam', 'regular')
        """))
        conn.execute(
            text(
                """
                CREATE TABLE app_users (
                    id VARCHAR(64) PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL
                )
                """
            )
        )
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES
              ('1', 'u1', 'household.admin'),
              ('2', 'u1', 'household.member'),
              ('2', 'u2', 'household.member'),
              ('1', 'u-platform', 'household.member'),
              ('0', 'u3', 'household.owner')
        """))
        conn.execute(
            text(
                """
                CREATE TABLE household_memberships (
                    user_id VARCHAR(64) NOT NULL,
                    household_id VARCHAR(64) NOT NULL,
                    role VARCHAR(32) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, household_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO app_users (id, email, password)
                VALUES ('u1', 'admin@rezzerv.local', 'Rezzerv123'),
                       ('u2', 'lid@rezzerv.local', 'Rezzerv123'),
                       ('u3', 'zero@rezzerv.local', 'Rezzerv123'),
                       ('u-super', :superuser_email, 'Rezzerv123'),
                       ('u-platform', 'platform@example.test', 'Rezzerv123'),
                       ('u-none', 'none@example.test', 'Rezzerv123'),
                       ('u-frontteam', 'frontteam@example.test', 'Rezzerv123'),
                       ('u-ip-owner', 'ip-owner@example.test', 'Rezzerv123'),
                       ('u-inactive-platform', 'inactive-platform@example.test', 'Rezzerv123')
                """
            ),
            {'superuser_email': SUPERGEBRUIKER_EMAIL},
        )
        conn.execute(
            text(
                """
                INSERT INTO household_memberships (user_id, household_id, role)
                VALUES ('u1', '1', 'owner'),
                       ('u1', '2', 'member'),
                       ('u2', '2', 'member'),
                       ('u-platform', '1', 'member'),
                       ('u3', '0', 'owner'),
                       ('u-frontteam', 'frontteam', 'admin')
                """
            )
        )
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('frontteam', 'u-frontteam', 'household.admin')
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES
              ('u-super', 'platform.superuser', 1),
              ('u-platform', 'platform.platform_admin', 1),
              ('u-frontteam', 'platform.frontteam', 1),
              ('u-ip-owner', 'platform.ip_owner', 1),
              ('u-inactive-platform', 'platform.platform_admin', 0)
        """))
        create_server_session_contract_schema(conn)

    app = FastAPI()
    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False, cookie_samesite="lax"),
        )
    )
    return TestClient(app), engine


def test_valid_login_sets_httponly_cookie_and_returns_no_token():
    client, _ = build_client()

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


def test_invalid_login_returns_401_without_cookie():
    client, _ = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "fout"},
    )

    assert response.status_code == 401
    assert "rezzerv_session=" not in response.headers.get("set-cookie", "").lower()


def test_unknown_account_returns_401_without_cookie():
    client, _ = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "unknown@example.test", "password": "Rezzerv123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Ongeldige inloggegevens"


def test_ambiguous_normalized_email_fails_closed_without_session():
    client, engine = build_client()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO app_users(id, email, password)
            VALUES
              ('u-ambiguous-1', 'Case@Example.test', 'Rezzerv123'),
              ('u-ambiguous-2', ' case@example.test ', 'Rezzerv123')
        """))

    response = client.post(
        "/api/auth/login",
        json={"email": "case@example.test", "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        session_count = conn.execute(text("""
            SELECT COUNT(*) FROM server_sessions
            WHERE user_id IN ('u-ambiguous-1', 'u-ambiguous-2')
        """)).scalar_one()

    assert response.status_code == 401
    assert response.json()["detail"] == "Ongeldige inloggegevens"
    assert session_count == 0


def test_member_login_keeps_regular_household_context():
    client, engine = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "lid@rezzerv.local", "password": "Rezzerv123"},
    )
    raw_session_id = response.cookies.get("rezzerv_session")
    with engine.begin() as conn:
        context = resolve_server_session(conn, raw_session_id)

    assert response.status_code == 200
    assert context.context_type == "regular"
    assert response.json()["context_type"] == "regular"
    assert context.active_household_id == "2"
    assert context.role == "member"


def test_superuser_login_uses_system_context_without_household_membership():
    client, engine = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": SUPERGEBRUIKER_EMAIL, "password": "Rezzerv123"},
    )
    raw_session_id = response.cookies.get("rezzerv_session")
    with engine.begin() as conn:
        context = resolve_server_session(conn, raw_session_id)
        membership_count = conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE user_id = 'u-super'
        """)).scalar_one()

    assert response.status_code == 200
    assert membership_count == 0
    assert context.context_type == "system"
    assert response.json()["context_type"] == "system"
    assert context.active_household_id == "0"
    assert context.role == "owner"
    assert context.is_platform_superuser is True
    assert response.json()["is_platform_superuser"] is True
    assert "platform_roles" not in response.json()


def test_ip_owner_login_uses_system_context_without_household_membership():
    client, engine = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "ip-owner@example.test", "password": "Rezzerv123"},
    )
    raw_session_id = response.cookies.get("rezzerv_session")
    with engine.begin() as conn:
        context = resolve_server_session(conn, raw_session_id)
        membership_count = conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE user_id = 'u-ip-owner'
        """)).scalar_one()

    assert response.status_code == 200
    assert membership_count == 0
    assert context.context_type == "system"
    assert response.json()["context_type"] == "system"
    assert context.active_household_id == "0"
    assert context.role == "owner"
    assert context.is_platform_superuser is False
    assert response.json()["is_platform_superuser"] is False
    assert "platform_roles" not in response.json()


def test_frontteam_login_uses_personal_regular_admin_household():
    client, engine = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "frontteam@example.test", "password": "Rezzerv123"},
    )
    raw_session_id = response.cookies.get("rezzerv_session")
    with engine.begin() as conn:
        personal_household_id = resolve_frontteam_personal_household_id(conn, "u-frontteam")
        context = resolve_server_session(conn, raw_session_id)
        membership = conn.execute(text("""
            SELECT hm.role, mr.role_key
            FROM household_memberships hm
            JOIN auth_membership_roles mr
              ON mr.household_id = hm.household_id
             AND mr.membership_id = hm.user_id
            WHERE hm.user_id = 'u-frontteam'
              AND hm.household_id = :household_id
        """), {"household_id": personal_household_id}).mappings().one()
        legacy_membership_count = conn.execute(text("""
            SELECT COUNT(*) FROM household_memberships
            WHERE user_id = 'u-frontteam' AND household_id = :legacy_id
        """), {"legacy_id": FRONTTEAM_HOUSEHOLD_ID}).scalar_one()

    payload = response.json()
    assert response.status_code == 200
    assert personal_household_id
    assert personal_household_id != FRONTTEAM_HOUSEHOLD_ID
    assert context.context_type == "regular"
    assert context.active_household_id == personal_household_id
    assert context.role == "admin"
    assert context.is_frontteam is True
    assert membership["role"] == "admin"
    assert membership["role_key"] == "household.admin"
    assert legacy_membership_count == 0
    assert payload["active_household_id"] == personal_household_id
    assert payload["active_household_name"] == FRONTTEAM_PERSONAL_HOUSEHOLD_NAME
    assert payload["context_type"] == "regular"
    assert payload["role"] == "admin"
    assert payload["is_frontteam"] is True
    for permission in (
        "platform.external_products.view",
        "platform.external_products.search",
        "platform.external_products.link_existing",
    ):
        assert payload["permissions"][permission] is True
    assert "platform_roles" not in payload


def test_frontteam_other_admin_membership_does_not_override_personal_household():
    client, engine = build_client()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO household_memberships(user_id, household_id, role)
            VALUES ('u-frontteam', '1', 'admin')
        """))
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('1', 'u-frontteam', 'household.admin')
        """))

    response = client.post(
        "/api/auth/login",
        json={"email": "frontteam@example.test", "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        personal_household_id = resolve_frontteam_personal_household_id(conn, "u-frontteam")

    assert response.status_code == 200
    assert response.json()["active_household_id"] == personal_household_id
    assert response.json()["active_household_id"] != "1"
    assert response.json()["context_type"] == "regular"
    assert response.json()["is_frontteam"] is True


def test_frontteam_platform_admin_conflict_creates_no_session():
    client, engine = build_client()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('u-frontteam', 'platform.platform_admin', 1)
        """))

    response = client.post(
        "/api/auth/login",
        json={"email": "frontteam@example.test", "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        session_count = conn.execute(text("""
            SELECT COUNT(*) FROM server_sessions WHERE user_id = 'u-frontteam'
        """)).scalar_one()

    assert response.status_code == 403
    assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    assert session_count == 0


@pytest.mark.parametrize(
    ("user_id", "email"),
    [
        ("u-super", SUPERGEBRUIKER_EMAIL),
        ("u-ip-owner", "ip-owner@example.test"),
    ],
)
def test_frontteam_system_context_conflicts_create_no_session(user_id, email):
    client, engine = build_client()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES (:user_id, 'platform.frontteam', 1)
        """), {"user_id": user_id})

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        session_count = conn.execute(text("""
            SELECT COUNT(*) FROM server_sessions WHERE user_id = :user_id
        """), {"user_id": user_id}).scalar_one()

    assert response.status_code == 403
    assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    assert session_count == 0


def test_frontteam_role_revocation_invalidates_existing_session():
    client, engine = build_client()
    login = client.post(
        "/api/auth/login",
        json={"email": "frontteam@example.test", "password": "Rezzerv123"},
    )
    assert login.status_code == 200
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles SET active = 0
            WHERE user_id = 'u-frontteam' AND role_key = 'platform.frontteam'
        """))

    response = client.get("/api/session")

    assert response.status_code == 403
    assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."


def test_platform_admin_only_login_creates_resolvable_none_session():
    client, engine = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "platform@example.test", "password": "Rezzerv123"},
    )
    raw_session_id = response.cookies.get("rezzerv_session")
    with engine.begin() as conn:
        stored_household_id = conn.execute(text("""
            SELECT active_household_id FROM server_sessions
            WHERE user_id = 'u-platform' AND revoked_at IS NULL
        """)).scalar_one()
        context = resolve_server_session(conn, raw_session_id)

    assert response.status_code == 200
    assert stored_household_id is None
    assert context.context_type == "none"
    assert context.active_household_id is None
    assert context.role is None
    assert response.json()["active_household_id"] is None
    assert response.json()["active_household_name"] == ""
    assert response.json()["role"] is None
    assert response.json()["display_role"] is None
    expected_permissions = set(ROLE_PERMISSIONS["platform.platform_admin"])
    assert response.json()["permissions"] == {
        key: True for key in sorted(expected_permissions)
    }
    assert response.json()["supported_permissions"] == sorted(expected_permissions)
    assert response.json()["context_type"] == "none"
    assert "platform_roles" not in response.json()


@pytest.mark.parametrize(
    "email",
    [
        "none@example.test",
        "inactive-platform@example.test",
    ],
)
def test_valid_credentials_without_allowed_context_return_403(email):
    client, engine = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        session_count = conn.execute(text("""
            SELECT COUNT(*) FROM server_sessions s
            JOIN app_users u ON u.id = s.user_id
            WHERE u.email = :email
        """), {"email": email}).scalar_one()

    assert response.status_code == 403
    assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    assert session_count == 0


def test_superuser_platform_admin_conflict_preserves_existing_session():
    client, engine = build_client()
    first_login = client.post(
        "/api/auth/login",
        json={"email": "platform@example.test", "password": "Rezzerv123"},
    )
    assert first_login.status_code == 200
    with engine.begin() as conn:
        session_id, revoked_at = conn.execute(text("""
            SELECT id, revoked_at FROM server_sessions
            WHERE user_id = 'u-platform'
        """)).one()
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('u-platform', 'platform.superuser', 1)
        """))

    conflict = client.post(
        "/api/auth/login",
        json={"email": "platform@example.test", "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        sessions = conn.execute(text("""
            SELECT id, revoked_at FROM server_sessions
            WHERE user_id = 'u-platform'
        """)).all()

    assert revoked_at is None
    assert conflict.status_code == 403
    assert conflict.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    assert sessions == [(session_id, None)]


def test_ip_owner_platform_admin_conflict_creates_no_session():
    client, engine = build_client()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('u-ip-owner', 'platform.platform_admin', 1)
        """))

    response = client.post(
        "/api/auth/login",
        json={"email": "ip-owner@example.test", "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        session_count = conn.execute(text("""
            SELECT COUNT(*) FROM server_sessions WHERE user_id = 'u-ip-owner'
        """)).scalar_one()

    assert response.status_code == 403
    assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    assert session_count == 0


def test_fixed_superuser_identity_without_active_superuser_role_creates_no_session():
    client, engine = build_client()
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles SET active = 0
            WHERE user_id = 'u-super' AND role_key = 'platform.superuser'
        """))
        conn.execute(text("""
            INSERT INTO auth_platform_user_roles(user_id, role_key, active)
            VALUES ('u-super', 'platform.platform_admin', 1)
        """))

    response = client.post(
        "/api/auth/login",
        json={"email": SUPERGEBRUIKER_EMAIL, "password": "Rezzerv123"},
    )
    with engine.begin() as conn:
        session_count = conn.execute(text("""
            SELECT COUNT(*) FROM server_sessions WHERE user_id = 'u-super'
        """)).scalar_one()

    assert response.status_code == 403
    assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."
    assert session_count == 0


def test_system_session_fails_closed_when_superuser_role_is_deactivated():
    client, engine = build_client()
    login = client.post(
        "/api/auth/login",
        json={"email": SUPERGEBRUIKER_EMAIL, "password": "Rezzerv123"},
    )
    assert login.status_code == 200

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_platform_user_roles SET active = 0
            WHERE user_id = 'u-super' AND role_key = 'platform.superuser'
        """))

    response = client.get("/api/session")

    assert response.status_code == 403
    assert response.json()["detail"] == "Geen geldige accountcontext beschikbaar."


def test_session_endpoint_without_cookie_returns_401():
    client, _ = build_client()

    response = client.get("/api/session")

    assert response.status_code == 401


def test_session_endpoint_resolves_context_from_server():
    client, engine = build_client()
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
    )
    assert login.status_code == 200

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE household_memberships
                SET role = 'member'
                WHERE user_id = 'u1' AND household_id = '1'
                """
            )
        )

    response = client.get("/api/session")

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["context_type"] == "regular"


def test_session_endpoint_reflects_canonical_role_update():
    client, engine = build_client()
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
    )
    assert login.status_code == 200

    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE auth_membership_roles
            SET role_key = 'household.member'
            WHERE household_id = '1' AND membership_id = 'u1'
        """))

    response = client.get("/api/session")

    assert response.status_code == 200
    assert response.json()["role"] == "member"


def test_logout_revokes_session_and_clears_cookie():
    client, _ = build_client()
    login = client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
    )
    assert login.status_code == 200

    logout = client.post("/api/auth/logout")

    assert logout.status_code == 204
    assert "rezzerv_session=" in logout.headers.get("set-cookie", "").lower()
    assert client.get("/api/session").status_code == 401


def test_new_login_invalidates_previous_cookie():
    first_client, engine = build_client()
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
    assert first_login.status_code == 200
    old_cookie = first_login.cookies.get("rezzerv_session")

    second_login = second_client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
    )
    assert second_login.status_code == 200
    assert second_login.cookies.get("rezzerv_session") != old_cookie

    first_client.cookies.set("rezzerv_session", old_cookie)
    assert first_client.get("/api/session").status_code == 401
    assert second_client.get("/api/session").status_code == 200


def test_household_zero_is_rejected_on_login():
    client, _ = build_client()

    response = client.post(
        "/api/auth/login",
        json={"email": "zero@rezzerv.local", "password": "Rezzerv123"},
    )

    assert response.status_code == 403


def test_secure_cookie_can_be_enabled_for_non_local_runtime():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                context_type TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO household_registry(id, context_type)
            VALUES ('1', 'regular')
        """))
        conn.execute(text("CREATE TABLE app_users (id TEXT PRIMARY KEY, email TEXT, password TEXT)"))
        conn.execute(text("CREATE TABLE household_memberships (user_id TEXT, household_id TEXT, role TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO app_users VALUES ('u1', 'admin@rezzerv.local', 'Rezzerv123')"))
        conn.execute(text("INSERT INTO household_memberships (user_id, household_id, role) VALUES ('u1', '1', 'owner')"))
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('1', 'u1', 'household.admin')
        """))
        create_server_session_contract_schema(conn)
    app = FastAPI()
    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=True, cookie_samesite="strict"),
        )
    )
    client = TestClient(app, base_url="https://testserver")

    response = client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
    )

    set_cookie = response.headers["set-cookie"].lower()
    assert "secure" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
