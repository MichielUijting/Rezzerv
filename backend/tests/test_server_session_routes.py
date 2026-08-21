from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)


def build_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
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
                       ('u3', 'zero@rezzerv.local', 'Rezzerv123')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO household_memberships (user_id, household_id, role)
                VALUES ('u1', '1', 'owner'),
                       ('u1', '2', 'member'),
                       ('u2', '2', 'member'),
                       ('u3', '0', 'owner')
                """
            )
        )

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
        conn.execute(text("CREATE TABLE app_users (id TEXT PRIMARY KEY, email TEXT, password TEXT)"))
        conn.execute(text("CREATE TABLE household_memberships (user_id TEXT, household_id TEXT, role TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO app_users VALUES ('u1', 'admin@rezzerv.local', 'Rezzerv123')"))
        conn.execute(text("INSERT INTO household_memberships (user_id, household_id, role) VALUES ('u1', '1', 'owner')"))
        ensure_authorization_foundation(conn)
        conn.execute(text("""
            INSERT INTO auth_membership_roles(household_id, membership_id, role_key)
            VALUES ('1', 'u1', 'household.admin')
        """))
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
