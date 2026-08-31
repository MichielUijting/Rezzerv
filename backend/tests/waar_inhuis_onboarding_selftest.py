"""Validation for Onboarding v2 step E: Waar Inhuis on PostgreSQL."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.api.server_session_routes import SessionApiConfiguration, create_server_session_router
from app.services.household_location_onboarding_service import ensure_location_foundation
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
        onboarding_use_case="waar_inhuis",
        onboarding_step="profile_follow_up",
    )


def _application(engine) -> FastAPI:
    app = FastAPI()
    app.include_router(create_server_session_router(
        engine,
        SessionApiConfiguration(cookie_secure=False),
    ))
    return app


def _payload(**overrides):
    payload = {
        "unpacking_enabled": True,
        "receipt_processing_enabled": True,
        "almost_out_enabled": False,
    }
    payload.update(overrides)
    return payload


def _finish_shared(client: TestClient):
    response = client.post(
        "/api/onboarding/shared-household-minimum",
        json={"household_name": "Huis Waar Inhuis", "household_usage_mode": "together"},
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
                "/api/onboarding/waar-inhuis",
                headers={"Authorization": "Bearer forged-admin"},
                json=_payload(),
            )
            assert forged.status_code == 401
        checks.append("forged_bearer_cannot_complete_waar_inhuis")

        with TestClient(app) as member:
            login = member.post(
                "/api/auth/login",
                json={"email": "shared-member@rezzerv.local", "password": "MemberPass123!"},
            )
            assert login.status_code == 200
            forbidden = member.post("/api/onboarding/waar-inhuis", json=_payload())
            assert forbidden.status_code == 403
        checks.append("member_cannot_change_waar_inhuis_configuration")

        with TestClient(app) as consumer:
            registration = consumer.post(
                "/api/auth/register",
                json={"email": "waar-inhuis@example.com", "password": "SterkWachtwoord123!"},
            )
            assert registration.status_code == 201, registration.text
            household_id = str(registration.json()["active_household_id"])
            selected = consumer.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "waar_inhuis"},
            )
            assert selected.status_code == 200, selected.text
            assert selected.json()["profile_follow_up_required"] is True

            client_household = consumer.post(
                "/api/onboarding/waar-inhuis",
                json={**_payload(), "household_id": "shared-household"},
            )
            assert client_household.status_code == 422

            legacy_location_payload = consumer.post(
                "/api/onboarding/waar-inhuis",
                json={
                    **_payload(),
                    "main_locations": ["Keuken"],
                    "sublocations": [{"space_name": "Keuken", "name": "Koelkast"}],
                },
            )
            assert legacy_location_payload.status_code == 422
        checks.append("client_household_and_location_payload_are_rejected")

        with engine.begin() as conn:
            count = conn.execute(text("""
                SELECT COUNT(*) FROM household_product_configuration
                WHERE household_id = :household_id
            """), {"household_id": household_id}).scalar_one()
            assert int(count) == 0
            ensure_location_foundation(conn)
            space_count = conn.execute(text("""
                SELECT COUNT(*) FROM spaces WHERE household_id = :household_id
            """), {"household_id": household_id}).scalar_one()
            assert int(space_count) == 0
            conn.execute(text("""
                INSERT INTO spaces (id, naam, household_id, active)
                VALUES ('existing-kitchen', 'Keuken bestaand', :household_id, FALSE)
            """), {"household_id": household_id})
        checks.append("rejected_answers_leave_no_partial_configuration_or_locations")

        with TestClient(app) as consumer:
            login = consumer.post(
                "/api/auth/login",
                json={"email": "waar-inhuis@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            profile = consumer.post("/api/onboarding/waar-inhuis", json=_payload())
            assert profile.status_code == 200, profile.text
            payload = profile.json()
            assert payload["onboarding_status"] == ONBOARDING_STATUS_IN_PROGRESS
            assert payload["onboarding_step"] == "shared_household_minimum"
            assert payload["shared_household_minimum_required"] is True
            assert "location_setup" not in payload
            configuration = payload["product_configuration"]
            assert configuration["inventory_tracking_level"] == "presence"
            assert configuration["location_tracking_level"] == "exact"
            assert configuration["unpacking_enabled"] is True
            assert configuration["receipt_processing_enabled"] is True
            assert configuration["almost_out_enabled"] is False
            assert configuration["shopping_enabled"] is False
            assert configuration["almost_out_notifications_enabled"] is False
            assert configuration["recipes_enabled"] is False
            _finish_shared(consumer)
        checks.append("waar_inhuis_profile_advances_without_location_provisioning")

        with engine.begin() as conn:
            columns = {
                str(column.get("name") or "")
                for column in inspect(conn).get_columns("household_product_configuration")
            }
            assert "unpacking_enabled" in columns
            state = resolve_household_onboarding_state(conn, household_id)
            assert state.onboarding_status == ONBOARDING_STATUS_COMPLETED
            assert state.onboarding_completed_at is not None
            assert state.household_usage_mode == "together"
            assert state.household_name == "Huis Waar Inhuis"
            configuration = resolve_household_product_configuration(conn, household_id)
            assert configuration.inventory_tracking_level == "presence"
            assert configuration.location_tracking_level == "exact"
            assert configuration.unpacking_enabled is True
            spaces = conn.execute(text("""
                SELECT id, naam, active
                FROM spaces
                WHERE household_id = :household_id
                ORDER BY lower(naam)
            """), {"household_id": household_id}).mappings().all()
            assert len(spaces) == 1
            assert str(spaces[0]["id"]) == "existing-kitchen"
            assert str(spaces[0]["naam"]) == "Keuken bestaand"
            assert bool(spaces[0]["active"]) is False
            sublocation_count = conn.execute(text("""
                SELECT COUNT(*)
                FROM sublocations sl
                JOIN spaces s ON s.id = sl.space_id
                WHERE s.household_id = :household_id
            """), {"household_id": household_id}).scalar_one()
            assert int(sublocation_count) == 0
        checks.append("onboarding_preserves_existing_locations_for_settings_management")

        with TestClient(app) as returning_consumer:
            login = returning_consumer.post(
                "/api/auth/login",
                json={"email": "waar-inhuis@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            state = returning_consumer.get("/api/onboarding")
            assert state.status_code == 200
            assert state.json()["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
            assert state.json()["shared_household_minimum_required"] is False
            duplicate = returning_consumer.post("/api/onboarding/waar-inhuis", json=_payload())
            assert duplicate.status_code == 409
        checks.append("completed_waar_inhuis_survives_login_and_cannot_restart")

        with TestClient(app) as other_profile:
            registration = other_profile.post(
                "/api/auth/register",
                json={"email": "other-profile@example.com", "password": "SterkWachtwoord123!"},
            )
            assert registration.status_code == 201
            other_household_id = str(registration.json()["active_household_id"])
            selected = other_profile.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "wat_inhuis"},
            )
            assert selected.status_code == 200
            wrong_profile = other_profile.post("/api/onboarding/waar-inhuis", json=_payload())
            assert wrong_profile.status_code == 409
            with engine.begin() as conn:
                count = conn.execute(text("""
                    SELECT COUNT(*) FROM household_product_configuration
                    WHERE household_id = :household_id
                """), {"household_id": other_household_id}).scalar_one()
                assert int(count) == 0
                ensure_location_foundation(conn)
                space_count = conn.execute(text("""
                    SELECT COUNT(*) FROM spaces WHERE household_id = :household_id
                """), {"household_id": other_household_id}).scalar_one()
                assert int(space_count) == 0
        checks.append("other_profiles_cannot_use_waar_inhuis_completion")
    finally:
        engine.dispose()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("WAAR_INHUIS_ONBOARDING_POSTGRESQL_GREEN")
    print("WAAR_INHUIS_ONBOARDING_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
