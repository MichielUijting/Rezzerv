"""Self-contained validation for Onboarding v2 step D: Wat Inhuis."""

from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_COMPLETED,
    ensure_household_onboarding_foundation,
    resolve_household_onboarding_state,
)
from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)
from app.services.roles_v2_schema_foundation import ensure_roles_v2_account_and_household_foundation


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
            VALUES ('shared-household', 'Gedeeld huishouden', 'regular')
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, password, account_status)
            VALUES
                ('shared-admin', 'shared-admin@rezzerv.local', 'AdminPass123!', 'active'),
                ('shared-member', 'shared-member@rezzerv.local', 'MemberPass123!', 'active')
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_email, role)
            VALUES
                ('shared-admin-membership', 'shared-household', 'shared-admin@rezzerv.local', 'admin'),
                ('shared-member-membership', 'shared-household', 'shared-member@rezzerv.local', 'member')
        """))
        create_canonical_membership_role(
            conn,
            household_id="shared-household",
            membership_id="shared-admin-membership",
            legacy_role="admin",
        )
        create_canonical_membership_role(
            conn,
            household_id="shared-household",
            membership_id="shared-member-membership",
            legacy_role="member",
        )
        ensure_household_onboarding_foundation(conn)
        conn.execute(text("""
            UPDATE household_onboarding
            SET onboarding_status = 'in_progress',
                primary_use_case = 'wat_inhuis',
                onboarding_step = 'profile_follow_up',
                onboarding_completed_at = NULL
            WHERE household_id = 'shared-household'
        """))


def _application(engine) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False),
        )
    )
    return app


def _register_and_select(client: TestClient, *, email: str) -> str:
    registration = client.post(
        "/api/auth/register",
        json={"email": email, "password": "SterkWachtwoord123!"},
    )
    assert registration.status_code == 201, registration.text
    household_id = str(registration.json()["active_household_id"])
    selected = client.post(
        "/api/onboarding/primary-use-case",
        json={"primary_use_case": "wat_inhuis"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["profile_follow_up_required"] is True
    return household_id


def run() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rezzerv-wat-inhuis-") as tmp:
        database_path = Path(tmp) / "wat-inhuis.db"
        engine = create_engine(
            f"sqlite:///{database_path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as anonymous:
            forged = anonymous.post(
                "/api/onboarding/wat-inhuis",
                headers={"Authorization": "Bearer forged-admin"},
                json={
                    "inventory_tracking_level": "presence",
                    "global_locations_enabled": False,
                    "almost_out_enabled": False,
                    "shopping_enabled": False,
                },
            )
            assert forged.status_code == 401
        checks.append("forged_bearer_cannot_complete_wat_inhuis")

        with TestClient(app) as member:
            login = member.post(
                "/api/auth/login",
                json={"email": "shared-member@rezzerv.local", "password": "MemberPass123!"},
            )
            assert login.status_code == 200
            forbidden = member.post(
                "/api/onboarding/wat-inhuis",
                json={
                    "inventory_tracking_level": "presence",
                    "global_locations_enabled": False,
                    "almost_out_enabled": False,
                    "shopping_enabled": False,
                },
            )
            assert forbidden.status_code == 403
        checks.append("member_cannot_change_wat_inhuis_configuration")

        with TestClient(app) as consumer:
            household_id = _register_and_select(consumer, email="wat-presence@example.com")
            invalid_level = consumer.post(
                "/api/onboarding/wat-inhuis",
                json={
                    "inventory_tracking_level": "exact",
                    "global_locations_enabled": False,
                    "almost_out_enabled": False,
                    "shopping_enabled": False,
                },
            )
            assert invalid_level.status_code == 422
            cross_household = consumer.post(
                "/api/onboarding/wat-inhuis",
                json={
                    "inventory_tracking_level": "presence",
                    "global_locations_enabled": False,
                    "almost_out_enabled": False,
                    "shopping_enabled": False,
                    "household_id": "shared-household",
                },
            )
            assert cross_household.status_code == 422
        with engine.begin() as conn:
            tables = inspect(conn).get_table_names()
            count = 0
            if "household_product_configuration" in tables:
                count = int(conn.execute(text("""
                    SELECT COUNT(*) FROM household_product_configuration
                    WHERE household_id = :household_id
                """), {"household_id": household_id}).scalar_one())
            assert count == 0
        checks.append("invalid_wat_inhuis_answers_leave_no_partial_configuration")

        with TestClient(app) as consumer:
            login = consumer.post(
                "/api/auth/login",
                json={"email": "wat-presence@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            completed = consumer.post(
                "/api/onboarding/wat-inhuis",
                json={
                    "inventory_tracking_level": "presence",
                    "global_locations_enabled": False,
                    "almost_out_enabled": True,
                    "shopping_enabled": False,
                },
            )
            assert completed.status_code == 200, completed.text
            payload = completed.json()
            assert payload["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
            assert payload["primary_use_case"] == "wat_inhuis"
            configuration = payload["product_configuration"]
            assert configuration["inventory_tracking_level"] == "presence"
            assert configuration["location_tracking_level"] == "none"
            assert configuration["shopping_enabled"] is False
            assert configuration["almost_out_enabled"] is True
            assert configuration["almost_out_notifications_enabled"] is False
            assert configuration["receipt_processing_enabled"] is False
            assert configuration["recipes_enabled"] is False
        checks.append("presence_without_locations_can_complete_wat_inhuis")

        with engine.begin() as conn:
            state = resolve_household_onboarding_state(conn, household_id)
            assert state.onboarding_status == ONBOARDING_STATUS_COMPLETED
            assert state.onboarding_completed_at is not None
            configuration = resolve_household_product_configuration(conn, household_id)
            assert configuration.inventory_tracking_level == "presence"
            assert configuration.location_tracking_level == "none"
            assert configuration.almost_out_enabled is True
            assert configuration.shopping_enabled is False
        checks.append("wat_inhuis_configuration_persists_server_side")

        with TestClient(app) as detailed:
            detailed_household_id = _register_and_select(detailed, email="wat-quantity@example.com")
            completed = detailed.post(
                "/api/onboarding/wat-inhuis",
                json={
                    "inventory_tracking_level": "quantity",
                    "global_locations_enabled": True,
                    "almost_out_enabled": False,
                    "shopping_enabled": True,
                },
            )
            assert completed.status_code == 200, completed.text
            configuration = completed.json()["product_configuration"]
            assert configuration["inventory_tracking_level"] == "quantity"
            assert configuration["location_tracking_level"] == "global"
            assert configuration["shopping_enabled"] is True
            assert configuration["almost_out_enabled"] is False
        with engine.begin() as conn:
            detailed_configuration = resolve_household_product_configuration(conn, detailed_household_id)
            assert detailed_configuration.inventory_tracking_level == "quantity"
            assert detailed_configuration.location_tracking_level == "global"
        checks.append("quantity_with_global_locations_and_shopping_supported")

        with TestClient(app) as returning:
            login = returning.post(
                "/api/auth/login",
                json={"email": "wat-presence@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            state = returning.get("/api/onboarding")
            assert state.status_code == 200
            assert state.json()["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
            assert state.json()["profile_follow_up_required"] is False
            duplicate = returning.post(
                "/api/onboarding/wat-inhuis",
                json={
                    "inventory_tracking_level": "quantity",
                    "global_locations_enabled": True,
                    "almost_out_enabled": True,
                    "shopping_enabled": True,
                },
            )
            assert duplicate.status_code == 409
        checks.append("completed_wat_inhuis_survives_login_and_cannot_restart")

        with TestClient(app) as other_profile:
            registration = other_profile.post(
                "/api/auth/register",
                json={"email": "waar-profile@example.com", "password": "SterkWachtwoord123!"},
            )
            assert registration.status_code == 201
            other_household_id = str(registration.json()["active_household_id"])
            selected = other_profile.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "waar_inhuis"},
            )
            assert selected.status_code == 200
            wrong_profile = other_profile.post(
                "/api/onboarding/wat-inhuis",
                json={
                    "inventory_tracking_level": "presence",
                    "global_locations_enabled": False,
                    "almost_out_enabled": False,
                    "shopping_enabled": False,
                },
            )
            assert wrong_profile.status_code == 409
            with engine.begin() as conn:
                tables = inspect(conn).get_table_names()
                if "household_product_configuration" in tables:
                    count = int(conn.execute(text("""
                        SELECT COUNT(*) FROM household_product_configuration
                        WHERE household_id = :household_id
                    """), {"household_id": other_household_id}).scalar_one())
                    assert count == 0
        checks.append("other_profiles_cannot_use_wat_inhuis_completion")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("WAT_INHUIS_ONBOARDING_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
