"""Self-contained validation for Onboarding v2 step C: Inhuis halen."""

from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.api.server_session_routes import SessionApiConfiguration, create_server_session_router
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.testing.authorization_schema_fixture import install_authorization_schema
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_COMPLETED,
    ONBOARDING_STATUS_IN_PROGRESS,
    ensure_household_onboarding_foundation,
    resolve_household_onboarding_state,
)
from app.services.household_product_configuration_service import resolve_household_product_configuration
from app.services.roles_v2_schema_foundation import ensure_roles_v2_account_and_household_foundation
from app.testing.onboarding_request_schema_fixture import (
    backfill_completed_household_onboarding,
    install_household_onboarding_schema,
    install_household_product_configuration_schema,
)
from app.testing.server_session_contract import create_server_session_contract_schema


def _prepare_database(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE household_registry (
                id TEXT PRIMARY KEY,
                naam TEXT NOT NULL,
                context_type TEXT NOT NULL DEFAULT 'regular',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE app_users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                account_status TEXT NOT NULL DEFAULT 'active',
                password_hash TEXT,
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
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        install_household_onboarding_schema(conn)
        install_household_product_configuration_schema(conn)
        create_server_session_contract_schema(conn)
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
        backfill_completed_household_onboarding(conn)
        ensure_household_onboarding_foundation(conn)
        conn.execute(text("""
            UPDATE household_onboarding
            SET onboarding_status = 'in_progress',
                primary_use_case = 'inhuis_halen',
                onboarding_step = 'profile_follow_up',
                onboarding_completed_at = NULL
            WHERE household_id = 'shared-household'
        """))


def _application(engine) -> FastAPI:
    app = FastAPI()
    app.include_router(create_server_session_router(
        engine,
        SessionApiConfiguration(cookie_secure=False),
    ))
    return app


def _profile_payload(**overrides):
    payload = {
        "simple_inventory_enabled": True,
        "almost_out_notifications_enabled": True,
        "receipt_processing_enabled": True,
        "recipes_enabled": False,
    }
    payload.update(overrides)
    return payload


def _finish_shared(client: TestClient, *, name: str = "Ons huis", mode: str = "alone"):
    response = client.post(
        "/api/onboarding/shared-household-minimum",
        json={"household_name": name, "household_usage_mode": mode},
    )
    assert response.status_code == 200, response.text
    assert response.json()["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
    return response


def run() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="rezzerv-inhuis-halen-") as tmp:
        database_path = Path(tmp) / "inhuis-halen.db"
        engine = create_engine(
            f"sqlite:///{database_path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as anonymous:
            forged = anonymous.post(
                "/api/onboarding/inhuis-halen",
                headers={"Authorization": "Bearer forged-admin"},
                json=_profile_payload(),
            )
            assert forged.status_code == 401
        checks.append("forged_bearer_cannot_complete_inhuis_halen")

        with TestClient(app) as member:
            login = member.post(
                "/api/auth/login",
                json={"email": "shared-member@rezzerv.local", "password": "MemberPass123!"},
            )
            assert login.status_code == 200
            forbidden = member.post("/api/onboarding/inhuis-halen", json=_profile_payload())
            assert forbidden.status_code == 403
        checks.append("member_cannot_change_household_product_configuration")

        with TestClient(app) as consumer:
            registration = consumer.post(
                "/api/auth/register",
                json={"email": "inhuis-halen@example.com", "password": "SterkWachtwoord123!"},
            )
            assert registration.status_code == 201, registration.text
            household_id = str(registration.json()["active_household_id"])
            selected = consumer.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "inhuis_halen"},
            )
            assert selected.status_code == 200, selected.text
            assert selected.json()["profile_follow_up_required"] is True
            inconsistent = consumer.post(
                "/api/onboarding/inhuis-halen",
                json=_profile_payload(
                    simple_inventory_enabled=False,
                    almost_out_notifications_enabled=True,
                ),
            )
            assert inconsistent.status_code == 422
            cross_household = consumer.post(
                "/api/onboarding/inhuis-halen",
                json={**_profile_payload(), "household_id": "shared-household"},
            )
            assert cross_household.status_code == 422
        checks.append("invalid_dependencies_and_client_household_id_rejected")

        with engine.begin() as conn:
            tables = inspect(conn).get_table_names()
            partial = 0
            if "household_product_configuration" in tables:
                partial = conn.execute(text("""
                    SELECT COUNT(*) FROM household_product_configuration
                    WHERE household_id = :household_id
                """), {"household_id": household_id}).scalar_one()
            assert int(partial) == 0
        checks.append("invalid_answers_leave_no_partial_product_configuration")

        with TestClient(app) as consumer:
            login = consumer.post(
                "/api/auth/login",
                json={"email": "inhuis-halen@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            profile = consumer.post("/api/onboarding/inhuis-halen", json=_profile_payload())
            assert profile.status_code == 200, profile.text
            payload = profile.json()
            assert payload["onboarding_status"] == ONBOARDING_STATUS_IN_PROGRESS
            assert payload["onboarding_step"] == "shared_household_minimum"
            assert payload["shared_household_minimum_required"] is True
            configuration = payload["product_configuration"]
            assert configuration["inventory_tracking_level"] == "quantity"
            assert configuration["location_tracking_level"] == "none"
            assert configuration["shopping_enabled"] is True
            assert configuration["almost_out_enabled"] is True
            assert configuration["almost_out_notifications_enabled"] is True
            assert configuration["receipt_processing_enabled"] is True
            assert configuration["recipes_enabled"] is False
            _finish_shared(consumer, name="Huis Inhuis Halen", mode="alone")
        checks.append("inhuis_halen_answers_advance_to_shared_minimum_then_complete")

        with engine.begin() as conn:
            state = resolve_household_onboarding_state(conn, household_id)
            assert state.onboarding_status == ONBOARDING_STATUS_COMPLETED
            assert state.onboarding_completed_at is not None
            assert state.household_usage_mode == "alone"
            assert state.household_name == "Huis Inhuis Halen"
            configuration = resolve_household_product_configuration(conn, household_id)
            assert configuration.inventory_tracking_level == "quantity"
            assert configuration.location_tracking_level == "none"
            assert configuration.simple_inventory_enabled is True
            assert configuration.shopping_enabled is True
            assert configuration.almost_out_enabled is True
            assert configuration.almost_out_notifications_enabled is True
            assert configuration.receipt_processing_enabled is True
            assert configuration.recipes_enabled is False
        checks.append("product_configuration_and_shared_minimum_persist_server_side")

        with TestClient(app) as returning_consumer:
            login = returning_consumer.post(
                "/api/auth/login",
                json={"email": "inhuis-halen@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            state = returning_consumer.get("/api/onboarding")
            assert state.status_code == 200
            assert state.json()["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
            assert state.json()["shared_household_minimum_required"] is False
            duplicate = returning_consumer.post("/api/onboarding/inhuis-halen", json=_profile_payload())
            assert duplicate.status_code == 409
        checks.append("completed_inhuis_halen_survives_login_and_cannot_restart")

        with TestClient(app) as other_profile:
            registration = other_profile.post(
                "/api/auth/register",
                json={"email": "wat-inhuis@example.com", "password": "SterkWachtwoord123!"},
            )
            assert registration.status_code == 201
            other_household_id = str(registration.json()["active_household_id"])
            selected = other_profile.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "wat_inhuis"},
            )
            assert selected.status_code == 200
            wrong_profile = other_profile.post("/api/onboarding/inhuis-halen", json=_profile_payload())
            assert wrong_profile.status_code == 409
            with engine.begin() as conn:
                tables = inspect(conn).get_table_names()
                if "household_product_configuration" in tables:
                    count = conn.execute(text("""
                        SELECT COUNT(*) FROM household_product_configuration
                        WHERE household_id = :household_id
                    """), {"household_id": other_household_id}).scalar_one()
                    assert int(count) == 0
        checks.append("other_profiles_cannot_use_inhuis_halen_completion")

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("INHUIS_HALEN_ONBOARDING_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
