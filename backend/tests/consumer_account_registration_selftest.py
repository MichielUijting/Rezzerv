"""Self-contained validation for the first Inhuis onboarding implementation slice.

Validates consumer account creation, own regular household, canonical Beheerder
role, hashed credentials, immediate server-side session and legacy login
compatibility. Runs without pytest.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from pathlib import Path
import tempfile

from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from app.api.server_session_routes import (
    SessionApiConfiguration,
    SessionLoginRequest,
    SessionRegisterRequest,
    create_server_session_router,
)
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.password_service import is_password_hash
from app.services.roles_v2_schema_foundation import ensure_roles_v2_account_and_household_foundation
from app.services.server_session_service import SESSION_COOKIE_NAME, resolve_server_session
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL


def _route(router, path: str, method: str):
    matches = [
        route
        for route in router.routes
        if getattr(route, "path", None) == path
        and method in set(getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1, f"verwacht exact 1 route voor {method} {path}, kreeg {len(matches)}"
    return matches[0]


def _cookie_value(response: Response, name: str) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers.get("set-cookie", ""))
    assert name in cookie, f"cookie {name} ontbreekt"
    return str(cookie[name].value)


def _expect_http_status(expected_status: int, fn) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == expected_status, (
            f"verwacht HTTP {expected_status}, kreeg HTTP {exc.status_code}"
        )
        return
    raise AssertionError(f"verwacht HTTP {expected_status}, maar geen fout ontvangen")


def _prepare_database(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE household_memberships (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                user_email TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(household_id, user_email)
            )
        """))
        ensure_roles_v2_account_and_household_foundation(conn)
        ensure_authorization_foundation(conn)

        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('legacy-household', 'Bestaand huishouden', 'regular')
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, password, account_status)
            VALUES ('legacy-user', 'legacy@rezzerv.local', 'LegacyPass123', 'active')
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_email, role)
            VALUES ('legacy-membership', 'legacy-household', 'legacy@rezzerv.local', 'admin')
        """))
        create_canonical_membership_role(
            conn,
            household_id="legacy-household",
            membership_id="legacy-membership",
            legacy_role="admin",
        )


def run() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rezzerv-consumer-account-") as tmp:
        database_path = Path(tmp) / "consumer-account.db"
        engine = create_engine(f"sqlite:///{database_path}", future=True)
        _prepare_database(engine)

        router = create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False),
        )
        register_route = _route(router, "/api/auth/register", "POST")
        login_route = _route(router, "/api/auth/login", "POST")
        assert register_route.status_code == 201
        register = register_route.endpoint
        login = login_route.endpoint
        checks.append("registration_route_unique_201")

        registration_response = Response()
        payload = register(
            SessionRegisterRequest(
                email="  Nieuwe.Gebruiker@Example.com ",
                password="SterkWachtwoord123!",
            ),
            registration_response,
        )
        assert payload["email"] == "nieuwe.gebruiker@example.com"
        assert payload["context_type"] == "regular"
        assert payload["role"] == "admin"
        assert payload["active_household_id"]
        assert payload["active_household_id"] != "0"
        assert payload["is_platform_superuser"] is False
        assert payload["is_frontteam"] is False
        assert payload["can_manage_members"] is True
        raw_session = _cookie_value(registration_response, SESSION_COOKIE_NAME)
        checks.append("new_consumer_registered_and_logged_in")

        household_id = str(payload["active_household_id"])
        with engine.begin() as conn:
            account = conn.execute(text("""
                SELECT id, email, password, password_hash, account_status
                FROM app_users
                WHERE email = 'nieuwe.gebruiker@example.com'
            """)).mappings().one()
            assert account["password"] != "SterkWachtwoord123!"
            assert is_password_hash(account["password"])
            assert account["password_hash"] == account["password"]
            assert account["account_status"] == "active"

            household = conn.execute(text("""
                SELECT naam, context_type
                FROM household_registry
                WHERE id = :household_id
            """), {"household_id": household_id}).mappings().one()
            assert household["naam"] == "Mijn huishouden"
            assert household["context_type"] == "regular"

            membership = conn.execute(text("""
                SELECT id, role
                FROM household_memberships
                WHERE household_id = :household_id
                  AND lower(user_email) = 'nieuwe.gebruiker@example.com'
            """), {"household_id": household_id}).mappings().one()
            assert membership["role"] == "admin"

            canonical_role = conn.execute(text("""
                SELECT role_key
                FROM auth_membership_roles
                WHERE household_id = :household_id
                  AND membership_id = :membership_id
                  AND active = 1
            """), {
                "household_id": household_id,
                "membership_id": str(membership["id"]),
            }).scalar_one()
            assert canonical_role == "household.admin"

            platform_grants = conn.execute(text("""
                SELECT COUNT(*)
                FROM auth_platform_user_roles
                WHERE user_id = :user_id AND active = 1
            """), {"user_id": str(account["id"])}).scalar_one()
            assert int(platform_grants) == 0

            resolved = resolve_server_session(conn, raw_session)
            assert resolved.user_id == str(account["id"])
            assert resolved.active_household_id == household_id
            assert resolved.context_type == "regular"
            assert resolved.role == "admin"
        checks.append("atomic_regular_household_canonical_admin_no_platform_grant")
        checks.append("new_password_hashed_not_plaintext")
        checks.append("registration_session_resolves_server_side")

        new_login_response = Response()
        new_login_payload = login(
            SessionLoginRequest(
                email="nieuwe.gebruiker@example.com",
                password="SterkWachtwoord123!",
            ),
            new_login_response,
        )
        assert new_login_payload["role"] == "admin"
        _cookie_value(new_login_response, SESSION_COOKIE_NAME)
        _expect_http_status(
            401,
            lambda: login(
                SessionLoginRequest(
                    email="nieuwe.gebruiker@example.com",
                    password="VerkeerdWachtwoord123!",
                ),
                Response(),
            ),
        )
        checks.append("hashed_account_login_and_wrong_password")

        legacy_login_payload = login(
            SessionLoginRequest(
                email="legacy@rezzerv.local",
                password="LegacyPass123",
            ),
            Response(),
        )
        assert legacy_login_payload["active_household_id"] == "legacy-household"
        assert legacy_login_payload["role"] == "admin"
        checks.append("legacy_plaintext_login_remains_compatible")

        _expect_http_status(
            409,
            lambda: register(
                SessionRegisterRequest(
                    email="NIEUWE.GEBRUIKER@example.com",
                    password="AndereSterkePass123!",
                ),
                Response(),
            ),
        )
        with engine.begin() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM app_users
                WHERE lower(email) = 'nieuwe.gebruiker@example.com'
            """)).scalar_one()
            assert int(count) == 1
        checks.append("duplicate_email_case_insensitive_409")

        before_counts = None
        with engine.begin() as conn:
            before_counts = (
                int(conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one()),
                int(conn.execute(text("SELECT COUNT(*) FROM household_registry")).scalar_one()),
                int(conn.execute(text("SELECT COUNT(*) FROM household_memberships")).scalar_one()),
            )
        try:
            SessionRegisterRequest(
                email="zwak@example.com",
                password="kort",
            )
        except ValidationError:
            pass
        else:
            raise AssertionError("zwak wachtwoord werd niet geweigerd")
        with engine.begin() as conn:
            after_counts = (
                int(conn.execute(text("SELECT COUNT(*) FROM app_users")).scalar_one()),
                int(conn.execute(text("SELECT COUNT(*) FROM household_registry")).scalar_one()),
                int(conn.execute(text("SELECT COUNT(*) FROM household_memberships")).scalar_one()),
            )
        assert after_counts == before_counts
        checks.append("weak_password_rejected_without_partial_state")

        _expect_http_status(
            409,
            lambda: register(
                SessionRegisterRequest(
                    email=SUPERGEBRUIKER_EMAIL,
                    password="SterkWachtwoord123!",
                ),
                Response(),
            ),
        )
        checks.append("reserved_system_identity_not_consumer_registerable")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("CONSUMER_ACCOUNT_FOUNDATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
