"""Validation for Onboarding v2 step D: Wat Inhuis on PostgreSQL."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.api.server_session_routes import SessionApiConfiguration, create_server_session_router
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_COMPLETED,
    ONBOARDING_STATUS_IN_PROGRESS,
    resolve_household_onboarding_state,
)
from app.services.household_product_configuration_service import resolve_household_product_configuration
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id="shared-household",
        household_name="Gedeeld huishouden",
        admin_id="shared-admin",
        admin_email="shared-admin@rezzerv.local",
        admin_password="AdminPass123!",
        admin_membership_id="shared-admin-membership",
        member_id="shared-member",
        member_email="shared-member@rezzerv.local",
        member_password="MemberPass123!",
        member_membership_id="shared-member-membership",
        onboarding_use_case="wat_inhuis",
        onboarding_step="profile_follow_up",
    )


def _application(engine) -> FastAPI:
    app = FastAPI()
    app.include_router(create_server_session_router(
        engine,
        SessionApiConfiguration(cookie_secure=False),
    ))
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


def _profile_payload(**overrides):
    payload = {
        "inventory_tracking_level": "presence",
        "global_locations_enabled": False,
        "almost_out_enabled": True,
        "shopping_enabled": False,
    }
    payload.update(overrides)
    return payload


def _finish_shared(client: TestClient, *, name: str, mode: str = "alone"):
    response = client.post(
        "/api/onboarding/shared-household-minimum",
        json={"household_name": name, "household_usage_mode": mode},
    )
    assert response.status_code == 200, response.text
    assert response.json()["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
    return response


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as anonymous:
            forged = anonymous.post(
                "/api/onboarding/wat-inhuis",
                headers={"Authorization": "Bearer forged-admin"},
                json=_profile_payload(),
            )
            assert forged.status_code == 401
        checks.append("forged_bearer_cannot_complete_wat_inhuis")

        with TestClient(app) as member:
            login = member.post(
                "/api/auth/login",
                json={"email": "shared-member@rezzerv.local", "password": "MemberPass123!"},
            )
            assert login.status_code == 200
            forbidden = member.post("/api/onboarding/wat-inhuis", json=_profile_payload())
            assert forbidden.status_code == 403
        checks.append("member_cannot_change_wat_inhuis_configuration")

        with TestClient(app) as consumer:
            household_id = _register_and_select(consumer, email="wat-presence@example.com")
            invalid_level = consumer.post(
                "/api/onboarding/wat-inhuis",
                json=_profile_payload(inventory_tracking_level="exact"),
            )
            assert invalid_level.status_code == 422
            cross_household = consumer.post(
                "/api/onboarding/wat-inhuis",
                json={**_profile_payload(), "household_id": "shared-household"},
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
            profile = consumer.post("/api/onboarding/wat-inhuis", json=_profile_payload())
            assert profile.status_code == 200, profile.text
            payload = profile.json()
            assert payload["onboarding_status"] == ONBOARDING_STATUS_IN_PROGRESS
            assert payload["onboarding_step"] == "shared_household_minimum"
            assert payload["shared_household_minimum_required"] is True
            configuration = payload["product_configuration"]
            assert configuration["inventory_tracking_level"] == "presence"
            assert configuration["location_tracking_level"] == "none"
            assert configuration["shopping_enabled"] is False
            assert configuration["almost_out_enabled"] is True
            assert configuration["almost_out_notifications_enabled"] is False
            assert configuration["receipt_processing_enabled"] is True
            assert configuration["recipes_enabled"] is False
            _finish_shared(consumer, name="Huis Wat Inhuis", mode="together")
        checks.append("presence_without_locations_advances_to_shared_minimum_then_completes")

        with engine.begin() as conn:
            state = resolve_household_onboarding_state(conn, household_id)
            assert state.onboarding_status == ONBOARDING_STATUS_COMPLETED
            assert state.onboarding_completed_at is not None
            assert state.household_usage_mode == "together"
            assert state.household_name == "Huis Wat Inhuis"
            configuration = resolve_household_product_configuration(conn, household_id)
            assert configuration.inventory_tracking_level == "presence"
            assert configuration.location_tracking_level == "none"
            assert configuration.almost_out_enabled is True
            assert configuration.shopping_enabled is False
            assert configuration.receipt_processing_enabled is True
        checks.append("wat_inhuis_configuration_and_shared_minimum_persist_server_side")

        with TestClient(app) as detailed:
            detailed_household_id = _register_and_select(detailed, email="wat-quantity@example.com")
            profile = detailed.post(
                "/api/onboarding/wat-inhuis",
                json=_profile_payload(
                    inventory_tracking_level="quantity",
                    global_locations_enabled=True,
                    almost_out_enabled=False,
                    shopping_enabled=True,
                ),
            )
            assert profile.status_code == 200, profile.text
            assert profile.json()["onboarding_step"] == "shared_household_minimum"
            configuration = profile.json()["product_configuration"]
            assert configuration["inventory_tracking_level"] == "quantity"
            assert configuration["location_tracking_level"] == "global"
            assert configuration["shopping_enabled"] is True
            assert configuration["almost_out_enabled"] is False
            assert configuration["receipt_processing_enabled"] is True
            _finish_shared(detailed, name="Huis met aantallen")
        with engine.begin() as conn:
            detailed_configuration = resolve_household_product_configuration(conn, detailed_household_id)
            assert detailed_configuration.inventory_tracking_level == "quantity"
            assert detailed_configuration.location_tracking_level == "global"
            assert detailed_configuration.receipt_processing_enabled is True
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
            assert state.json()["shared_household_minimum_required"] is False
            duplicate = returning.post("/api/onboarding/wat-inhuis", json=_profile_payload())
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
            wrong_profile = other_profile.post("/api/onboarding/wat-inhuis", json=_profile_payload())
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
    finally:
        engine.dispose()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("WAT_INHUIS_ONBOARDING_POSTGRESQL_GREEN")
    print("WAT_INHUIS_ONBOARDING_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
