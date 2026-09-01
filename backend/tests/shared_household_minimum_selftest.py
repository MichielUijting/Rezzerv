"""Validation for the shared household minimum in Onboarding v2 on PostgreSQL."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.api.server_session_routes import SessionApiConfiguration, create_server_session_router
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_COMPLETED,
    ONBOARDING_STATUS_IN_PROGRESS,
    ensure_household_onboarding_foundation,
    resolve_household_onboarding_state,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
    seed_completed_legacy_household,
)


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id="shared-household",
        household_name="Tijdelijk huishouden",
        admin_id="shared-admin",
        admin_email="shared-admin@rezzerv.local",
        admin_password="AdminPass123!",
        admin_membership_id="shared-admin-membership",
        member_id="shared-member",
        member_email="shared-member@rezzerv.local",
        member_password="MemberPass123!",
        member_membership_id="shared-member-membership",
        onboarding_use_case="inhuis_halen",
        onboarding_step="shared_household_minimum",
    )
    seed_completed_legacy_household(
        engine,
        household_id="legacy-household",
        household_name="Bestaand huishouden",
    )


def _application(engine) -> FastAPI:
    app = FastAPI()
    app.include_router(create_server_session_router(
        engine,
        SessionApiConfiguration(cookie_secure=False),
    ))
    return app


def _register_select_and_profile(client: TestClient, *, email: str) -> str:
    registration = client.post(
        "/api/auth/register",
        json={"email": email, "password": "SterkWachtwoord123!"},
    )
    assert registration.status_code == 201, registration.text
    household_id = str(registration.json()["active_household_id"])
    selected = client.post(
        "/api/onboarding/primary-use-case",
        json={"primary_use_case": "inhuis_halen"},
    )
    assert selected.status_code == 200, selected.text
    profile = client.post(
        "/api/onboarding/inhuis-halen",
        json={
            "simple_inventory_enabled": True,
            "almost_out_notifications_enabled": False,
            "receipt_processing_enabled": False,
            "recipes_enabled": False,
        },
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["onboarding_status"] == ONBOARDING_STATUS_IN_PROGRESS
    assert profile.json()["onboarding_step"] == "shared_household_minimum"
    assert profile.json()["shared_household_minimum_required"] is True
    return household_id


def _invitation_count(engine) -> int:
    with engine.begin() as conn:
        if "household_invitations" not in inspect(conn).get_table_names():
            return 0
        return int(conn.execute(text("SELECT COUNT(*) FROM household_invitations")).scalar_one())


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as anonymous:
            forged = anonymous.post(
                "/api/onboarding/shared-household-minimum",
                headers={"Authorization": "Bearer forged-admin"},
                json={"household_name": "Vals", "household_usage_mode": "alone"},
            )
            assert forged.status_code == 401
        checks.append("forged_bearer_cannot_complete_shared_household_minimum")

        with TestClient(app) as member:
            login = member.post(
                "/api/auth/login",
                json={"email": "shared-member@rezzerv.local", "password": "MemberPass123!"},
            )
            assert login.status_code == 200
            forbidden = member.post(
                "/api/onboarding/shared-household-minimum",
                json={"household_name": "Niet toegestaan", "household_usage_mode": "together"},
            )
            assert forbidden.status_code == 403
        checks.append("member_cannot_change_shared_household_minimum")

        with engine.begin() as conn:
            ensure_household_onboarding_foundation(conn)
            legacy = resolve_household_onboarding_state(conn, "legacy-household")
            assert legacy.onboarding_status == ONBOARDING_STATUS_COMPLETED
            assert legacy.household_name == "Bestaand huishouden"
            assert legacy.household_usage_mode is None
        checks.append("existing_completed_households_are_not_reopened")

        with TestClient(app) as consumer:
            household_id = _register_select_and_profile(
                consumer,
                email="shared-minimum-alone@example.com",
            )
            state = consumer.get("/api/onboarding")
            assert state.status_code == 200
            assert state.json()["household_name"] == "Mijn huishouden"
            assert state.json()["shared_household_minimum_required"] is True
        checks.append("profile_follow_up_advances_to_shared_household_minimum")

        with TestClient(app) as consumer:
            login = consumer.post(
                "/api/auth/login",
                json={"email": "shared-minimum-alone@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            blank_name = consumer.post(
                "/api/onboarding/shared-household-minimum",
                json={"household_name": "   ", "household_usage_mode": "alone"},
            )
            assert blank_name.status_code == 422
            invalid_mode = consumer.post(
                "/api/onboarding/shared-household-minimum",
                json={"household_name": "Mijn echte huis", "household_usage_mode": "friends"},
            )
            assert invalid_mode.status_code == 422
            cross_household = consumer.post(
                "/api/onboarding/shared-household-minimum",
                json={
                    "household_name": "Mijn echte huis",
                    "household_usage_mode": "alone",
                    "household_id": "shared-household",
                },
            )
            assert cross_household.status_code == 422
        with engine.begin() as conn:
            unchanged = resolve_household_onboarding_state(conn, household_id)
            assert unchanged.onboarding_status == ONBOARDING_STATUS_IN_PROGRESS
            assert unchanged.household_name == "Mijn huishouden"
            assert unchanged.household_usage_mode is None
        checks.append("invalid_shared_answers_leave_no_partial_household_update")

        with TestClient(app) as consumer:
            login = consumer.post(
                "/api/auth/login",
                json={"email": "shared-minimum-alone@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            completed = consumer.post(
                "/api/onboarding/shared-household-minimum",
                json={"household_name": "  Huis   Alleen  ", "household_usage_mode": "alone"},
            )
            assert completed.status_code == 200, completed.text
            payload = completed.json()
            assert payload["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
            assert payload["onboarding_step"] is None
            assert payload["household_name"] == "Huis Alleen"
            assert payload["household_usage_mode"] == "alone"
            assert payload["shared_household_minimum_required"] is False
            session = consumer.get("/api/session")
            assert session.status_code == 200
            assert session.json()["active_household_name"] == "Huis Alleen"
        checks.append("alone_mode_updates_household_name_and_completes_onboarding")

        invitations_before = _invitation_count(engine)
        with TestClient(app) as together:
            together_household_id = _register_select_and_profile(
                together,
                email="shared-minimum-together@example.com",
            )
            with engine.begin() as conn:
                before_members = int(conn.execute(text("""
                    SELECT COUNT(*) FROM household_memberships
                    WHERE household_id = :household_id
                """), {"household_id": together_household_id}).scalar_one())
            completed = together.post(
                "/api/onboarding/shared-household-minimum",
                json={"household_name": "Samen Thuis", "household_usage_mode": "together"},
            )
            assert completed.status_code == 200, completed.text
            assert completed.json()["household_usage_mode"] == "together"
            with engine.begin() as conn:
                after_members = int(conn.execute(text("""
                    SELECT COUNT(*) FROM household_memberships
                    WHERE household_id = :household_id
                """), {"household_id": together_household_id}).scalar_one())
                assert after_members == before_members == 1
        assert _invitation_count(engine) == invitations_before
        checks.append("together_mode_can_finish_without_fake_or_implicit_invitation")

        with TestClient(app) as returning:
            login = returning.post(
                "/api/auth/login",
                json={"email": "shared-minimum-together@example.com", "password": "SterkWachtwoord123!"},
            )
            assert login.status_code == 200
            state = returning.get("/api/onboarding")
            assert state.status_code == 200
            assert state.json()["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
            assert state.json()["household_name"] == "Samen Thuis"
            assert state.json()["household_usage_mode"] == "together"
            duplicate = returning.post(
                "/api/onboarding/shared-household-minimum",
                json={"household_name": "Andere naam", "household_usage_mode": "alone"},
            )
            assert duplicate.status_code == 409
        checks.append("shared_minimum_survives_login_and_cannot_be_repeated")
    finally:
        engine.dispose()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("SHARED_HOUSEHOLD_MINIMUM_POSTGRESQL_GREEN")
    print("SHARED_HOUSEHOLD_MINIMUM_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
