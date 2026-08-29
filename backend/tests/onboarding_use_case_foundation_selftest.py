"""Self-contained validation for Onboarding v2 step B: use-case foundation."""

from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api.server_session_routes import (
    SessionApiConfiguration,
    create_server_session_router,
)
from app.services.authorization_foundation_service import ensure_authorization_foundation
from app.testing.authorization_schema_fixture import install_authorization_schema
from app.services.authorization_membership_service import create_canonical_membership_role
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_COMPLETED,
    ONBOARDING_STATUS_IN_PROGRESS,
    ONBOARDING_STATUS_NOT_STARTED,
    ensure_household_onboarding_foundation,
    resolve_household_onboarding_state,
)
from app.services.roles_v2_schema_foundation import ensure_roles_v2_account_and_household_foundation
from app.testing.server_session_contract import create_server_session_contract_schema


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
        install_authorization_schema(conn)
        ensure_authorization_foundation(conn)
        create_server_session_contract_schema(conn)

        conn.execute(text("""
            INSERT INTO household_registry(id, naam, context_type)
            VALUES ('existing-household', 'Bestaand huishouden', 'regular')
        """))
        conn.execute(text("""
            INSERT INTO app_users(id, email, password, account_status)
            VALUES
                ('existing-admin', 'existing-admin@rezzerv.local', 'AdminPass123!', 'active'),
                ('existing-member', 'existing-member@rezzerv.local', 'MemberPass123!', 'active')
        """))
        conn.execute(text("""
            INSERT INTO household_memberships(id, household_id, user_email, role)
            VALUES
                ('existing-admin-membership', 'existing-household', 'existing-admin@rezzerv.local', 'admin'),
                ('existing-member-membership', 'existing-household', 'existing-member@rezzerv.local', 'member')
        """))
        create_canonical_membership_role(
            conn,
            household_id="existing-household",
            membership_id="existing-admin-membership",
            legacy_role="admin",
        )
        create_canonical_membership_role(
            conn,
            household_id="existing-household",
            membership_id="existing-member-membership",
            legacy_role="member",
        )

        ensure_household_onboarding_foundation(conn)
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
    with tempfile.TemporaryDirectory(prefix="rezzerv-onboarding-use-case-") as tmp:
        database_path = Path(tmp) / "onboarding.db"
        engine = create_engine(
            f"sqlite:///{database_path}",
            future=True,
            connect_args={"check_same_thread": False},
        )
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

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("ONBOARDING_USE_CASE_FOUNDATION_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
