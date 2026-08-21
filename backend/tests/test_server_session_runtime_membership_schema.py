from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.services.authorization_membership_service import migrate_legacy_household_memberships
from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)


def _runtime_schema_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, password)
            VALUES ('u-admin', 'admin@rezzerv.local', 'Rezzerv123')
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(
                id, household_id, user_email, role, status
            ) VALUES
                ('m-inactive', '0', 'admin@rezzerv.local', 'owner', 'inactive'),
                ('m-active', '1', 'ADMIN@REZZERV.LOCAL', 'owner', 'active')
        """))
        migrate_legacy_household_memberships(conn)

    app = FastAPI()
    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False, cookie_samesite="lax"),
        )
    )
    return TestClient(app), engine


def test_login_and_session_resolve_with_user_email_membership_schema():
    client, _ = _runtime_schema_client()

    login = client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
    )

    assert login.status_code == 200
    assert login.json()["user"]["id"] == "u-admin"
    assert login.json()["active_household_id"] == "1"
    assert login.json()["role"] == "admin"
    assert client.get("/api/session").status_code == 200


def test_inactive_runtime_membership_is_not_accepted():
    client, engine = _runtime_schema_client()
    with engine.begin() as conn:
        conn.execute(text("UPDATE household_memberships SET status = 'inactive'"))

    response = client.post(
        "/api/auth/login",
        json={"email": "admin@rezzerv.local", "password": "Rezzerv123"},
    )

    assert response.status_code == 401
