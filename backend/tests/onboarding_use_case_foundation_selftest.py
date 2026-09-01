"""Validation for Onboarding v2 use-case foundation on PostgreSQL."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_COMPLETED,
    ONBOARDING_STATUS_IN_PROGRESS,
    ONBOARDING_STATUS_NOT_STARTED,
    resolve_household_onboarding_state,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)


def _prepare_database(engine) -> None:
    seed_admin_member_household(
        engine,
        household_id="existing-household",
        household_name="Bestaand huishouden",
        admin_id="existing-admin",
        admin_email="existing-admin@rezzerv.local",
        admin_password="AdminPass123!",
        admin_membership_id="existing-admin-membership",
        member_id="existing-member",
        member_email="existing-member@rezzerv.local",
        member_password="MemberPass123!",
        member_membership_id="existing-member-membership",
    )
    with engine.begin() as conn:
        existing_state = resolve_household_onboarding_state(conn, "existing-household")
        assert existing_state.onboarding_status == ONBOARDING_STATUS_COMPLETED
        assert existing_state.primary_use_case is None


def _application(engine) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False),
        )
    )
    return app


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as anonymous:
            forged_get = anonymous.get(
                "/api/onboarding",
                headers={"Authorization": "Bearer forged-admin"},
            )
            assert forged_get.status_code == 401
            forged_post = anonymous.post(
                "/api/onboarding/primary-use-case",
                headers={"Authorization": "Bearer forged-admin"},
                json={"primary_use_case": "inhuis_halen"},
            )
            assert forged_post.status_code == 401
        checks.append("forged_bearer_cannot_supply_onboarding_authority")

        with TestClient(app) as new_consumer:
            registration = new_consumer.post(
                "/api/auth/register",
                json={
                    "email": "new-onboarding@example.com",
                    "password": "SterkWachtwoord123!",
                },
            )
            assert registration.status_code == 201, registration.text
            household_id = str(registration.json()["active_household_id"])

            onboarding = new_consumer.get("/api/onboarding")
            assert onboarding.status_code == 200, onboarding.text
            state = onboarding.json()
            assert state["household_id"] == household_id
            assert state["onboarding_status"] == ONBOARDING_STATUS_NOT_STARTED
            assert state["onboarding_version"] == 2
            assert state["primary_use_case"] is None
            assert state["initial_choice_required"] is True
            assert state["can_manage"] is True
        checks.append("new_household_requires_initial_use_case")

        with engine.begin() as conn:
            database_state = resolve_household_onboarding_state(conn, household_id)
            assert database_state.onboarding_status == ONBOARDING_STATUS_NOT_STARTED
            assert database_state.initial_choice_required is True
        checks.append("new_household_state_persisted_server_side")

        with TestClient(app) as existing_admin:
            login = existing_admin.post(
                "/api/auth/login",
                json={
                    "email": "existing-admin@rezzerv.local",
                    "password": "AdminPass123!",
                },
            )
            assert login.status_code == 200, login.text
            existing = existing_admin.get("/api/onboarding")
            assert existing.status_code == 200, existing.text
            payload = existing.json()
            assert payload["onboarding_status"] == ONBOARDING_STATUS_COMPLETED
            assert payload["initial_choice_required"] is False
            assert payload["can_manage"] is True
            blocked_restart = existing_admin.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "wat_inhuis"},
            )
            assert blocked_restart.status_code == 409
        checks.append("existing_households_backfilled_complete_and_untouched")

        with TestClient(app) as existing_member:
            login = existing_member.post(
                "/api/auth/login",
                json={
                    "email": "existing-member@rezzerv.local",
                    "password": "MemberPass123!",
                },
            )
            assert login.status_code == 200, login.text
            visible = existing_member.get("/api/onboarding")
            assert visible.status_code == 200
            assert visible.json()["can_manage"] is False
            forbidden = existing_member.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "waar_inhuis"},
            )
            assert forbidden.status_code == 403
        checks.append("member_can_read_but_cannot_configure_household_onboarding")

        with TestClient(app) as new_consumer:
            login = new_consumer.post(
                "/api/auth/login",
                json={
                    "email": "new-onboarding@example.com",
                    "password": "SterkWachtwoord123!",
                },
            )
            assert login.status_code == 200, login.text

            invalid = new_consumer.post(
                "/api/onboarding/primary-use-case",
                json={"primary_use_case": "alles"},
            )
            assert invalid.status_code == 422

            cross_household = new_consumer.post(
                "/api/onboarding/primary-use-case",
                json={
                    "primary_use_case": "inhuis_halen",
                    "household_id": "existing-household",
                },
            )
            assert cross_household.status_code == 422
        checks.append("invalid_or_client_supplied_household_choice_rejected")

        with TestClient(app) as new_consumer:
            login = new_consumer.post(
                "/api/auth/login",
                json={
                    "email": "new-onboarding@example.com",
                    "password": "SterkWachtwoord123!",
                },
            )
            assert login.status_code == 200
            for use_case in ("inhuis_halen", "wat_inhuis", "waar_inhuis", "inhuis_halen"):
                selected = new_consumer.post(
                    "/api/onboarding/primary-use-case",
                    json={"primary_use_case": use_case},
                )
                assert selected.status_code == 200, selected.text
                payload = selected.json()
                assert payload["primary_use_case"] == use_case
                assert payload["onboarding_status"] == ONBOARDING_STATUS_IN_PROGRESS
                assert payload["initial_choice_required"] is False
                assert payload["can_manage"] is True
        checks.append("three_canonical_use_cases_are_server_side_selectable")

        with engine.begin() as conn:
            selected_state = resolve_household_onboarding_state(conn, household_id)
            assert selected_state.primary_use_case == "inhuis_halen"
            assert selected_state.onboarding_status == ONBOARDING_STATUS_IN_PROGRESS
            assert selected_state.onboarding_step == "profile_follow_up"
            assert selected_state.onboarding_completed_at is None
        checks.append("selection_persists_without_falsely_completing_onboarding")

        with TestClient(app) as returning_consumer:
            login = returning_consumer.post(
                "/api/auth/login",
                json={
                    "email": "new-onboarding@example.com",
                    "password": "SterkWachtwoord123!",
                },
            )
            assert login.status_code == 200
            state = returning_consumer.get("/api/onboarding")
            assert state.status_code == 200
            assert state.json()["primary_use_case"] == "inhuis_halen"
            assert state.json()["initial_choice_required"] is False
        checks.append("selected_use_case_survives_new_login")
    finally:
        engine.dispose()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("ONBOARDING_USE_CASE_POSTGRESQL_GREEN")
    print("ONBOARDING_USE_CASE_FOUNDATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
