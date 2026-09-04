"""P0 F3-01: Settings → persistence → location-policy API authority on PostgreSQL.

The primary action in this test is a real HTTP request with the real opaque
server-session cookie. Business services and authorization are not mocked. The
isolated PostgreSQL runtime engine is wired into the same modules the production
route uses; postconditions assert both persisted state and runtime policy.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.api import household_capability_expansion_routes as capability_routes
from app.api.server_session_routes import SessionApiConfiguration, create_server_session_router
from app.services import session_request_context
from app.services.household_product_configuration_service import (
    resolve_household_product_configuration,
)
from app.services.inventory_location_policy_service import resolve_inventory_location
from app.services.session_request_context import (
    bind_current_actor_from_request_session_if_available,
    bind_request_session,
    reset_request_session,
)
from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    seed_admin_member_household,
)

NONE_HOUSEHOLD = "settings-location-none"
GLOBAL_HOUSEHOLD = "settings-location-global"
ISOLATION_HOUSEHOLD = "settings-location-isolation"
PASSWORD = "SettingsLocationPass123!"


def _seed_household(engine, *, household_id: str, label: str) -> None:
    seed_admin_member_household(
        engine,
        household_id=household_id,
        household_name=f"Settings {label}",
        admin_id=f"{household_id}-admin",
        admin_email=f"{household_id}-admin@rezzerv.local",
        admin_password=PASSWORD,
        admin_membership_id=f"{household_id}-admin-membership",
        member_id=f"{household_id}-member",
        member_email=f"{household_id}-member@rezzerv.local",
        member_password=PASSWORD,
        member_membership_id=f"{household_id}-member-membership",
    )


def _prepare_database(engine) -> None:
    _seed_household(engine, household_id=NONE_HOUSEHOLD, label="zonder locaties")
    _seed_household(engine, household_id=GLOBAL_HOUSEHOLD, label="met hoofdlocaties")
    _seed_household(engine, household_id=ISOLATION_HOUSEHOLD, label="isolatie")


def _application(engine) -> FastAPI:
    # The route and request-context modules are production modules with a module-level
    # engine. Point only that database boundary at the isolated PostgreSQL runtime;
    # no business/authorization behavior is replaced.
    capability_routes.engine = engine
    session_request_context.engine = engine

    app = FastAPI()

    @app.middleware("http")
    async def server_session_request_context(request: Request, call_next):
        token = bind_request_session(request)
        try:
            bind_current_actor_from_request_session_if_available()
            return await call_next(request)
        except Exception as exc:
            # Mirror the production middleware's HTTPException handling while still
            # letting unexpected exceptions fail the selftest loudly.
            from fastapi import HTTPException

            if isinstance(exc, HTTPException):
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=exc.headers,
                )
            raise
        finally:
            reset_request_session(token)

    app.include_router(
        create_server_session_router(
            engine,
            SessionApiConfiguration(cookie_secure=False),
        )
    )
    app.include_router(capability_routes.router)
    return app


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text


def _wat_payload(*, global_locations: bool) -> dict:
    return {
        "inventory_tracking_level": "quantity",
        "global_locations_enabled": global_locations,
        "almost_out_enabled": True,
        "shopping_enabled": True,
    }


def _direct_space_id(conn, household_id: str) -> str:
    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("spaces")
    }
    assert "household_id" in columns
    assert "is_direct" in columns
    row = conn.execute(
        text(
            """
            SELECT id, naam
            FROM spaces
            WHERE household_id = :household_id
              AND is_direct = :is_direct
              AND COALESCE(active, TRUE) = TRUE
            ORDER BY id
            """
        ),
        {"household_id": household_id, "is_direct": 1},
    ).mappings().all()
    assert len(row) == 1, row
    assert str(row[0].get("naam") or "").strip().lower() == "direct"
    return str(row[0]["id"])


def run() -> int:
    checks: list[str] = []
    engine = create_postgresql_runtime_test_engine()
    try:
        assert engine.dialect.name == "postgresql"
        with engine.begin() as conn:
            assert bool(
                conn.execute(
                    text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
                ).scalar_one()
            ) is False
        checks.append("postgresql_dml_only_runtime")

        _prepare_database(engine)
        app = _application(engine)

        with TestClient(app) as anonymous:
            forged = anonymous.post(
                "/api/onboarding/expand/wat-inhuis",
                headers={"Authorization": "Bearer forged-admin"},
                json=_wat_payload(global_locations=False),
            )
            assert forged.status_code == 401, forged.text
        checks.append("missing_server_session_401")

        with TestClient(app) as member:
            _login(member, f"{NONE_HOUSEHOLD}-member@rezzerv.local")
            forbidden = member.post(
                "/api/onboarding/expand/wat-inhuis",
                json=_wat_payload(global_locations=False),
            )
            assert forbidden.status_code == 403, forbidden.text
            assert "household_settings.manage" in str(forbidden.json().get("detail") or "")
        checks.append("household_member_cannot_manage_settings")

        with TestClient(app) as none_admin:
            _login(none_admin, f"{NONE_HOUSEHOLD}-admin@rezzerv.local")
            response = none_admin.post(
                "/api/onboarding/expand/wat-inhuis",
                json={
                    **_wat_payload(global_locations=False),
                    # Pydantic may ignore this legacy/unknown field; authority must still
                    # come exclusively from the server session.
                    "household_id": ISOLATION_HOUSEHOLD,
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["household_id"] == NONE_HOUSEHOLD
            assert payload["product_configuration"]["inventory_tracking_level"] == "quantity"
            assert payload["product_configuration"]["location_tracking_level"] == "none"

            projection = none_admin.get("/api/onboarding/capabilities")
            assert projection.status_code == 200, projection.text
            assert projection.json()["household_id"] == NONE_HOUSEHOLD
            assert projection.json()["product_configuration"]["location_tracking_level"] == "none"
        checks.append("settings_api_persists_locationless_mode")
        checks.append("session_household_is_authoritative")

        with TestClient(app) as global_admin:
            _login(global_admin, f"{GLOBAL_HOUSEHOLD}-admin@rezzerv.local")
            response = global_admin.post(
                "/api/onboarding/expand/wat-inhuis",
                json=_wat_payload(global_locations=True),
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["household_id"] == GLOBAL_HOUSEHOLD
            assert payload["product_configuration"]["inventory_tracking_level"] == "quantity"
            assert payload["product_configuration"]["location_tracking_level"] == "global"
        checks.append("settings_api_persists_global_location_mode")

        with engine.begin() as conn:
            none_configuration = resolve_household_product_configuration(conn, NONE_HOUSEHOLD)
            assert none_configuration.inventory_tracking_level == "quantity"
            assert none_configuration.location_tracking_level == "none"
            assert none_configuration.almost_out_enabled is True
            assert none_configuration.shopping_enabled is True

            none_policy = resolve_inventory_location(conn, NONE_HOUSEHOLD)
            assert none_policy == {
                "location_id": None,
                "space_id": None,
                "sublocation_id": None,
                "location_label": "",
            }
            none_space_count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM spaces WHERE household_id = :household_id"),
                    {"household_id": NONE_HOUSEHOLD},
                ).scalar_one()
            )
            assert none_space_count == 0

            global_configuration = resolve_household_product_configuration(conn, GLOBAL_HOUSEHOLD)
            assert global_configuration.inventory_tracking_level == "quantity"
            assert global_configuration.location_tracking_level == "global"
            assert global_configuration.almost_out_enabled is True
            assert global_configuration.shopping_enabled is True
            direct_space_id = _direct_space_id(conn, GLOBAL_HOUSEHOLD)
            global_policy = resolve_inventory_location(
                conn,
                GLOBAL_HOUSEHOLD,
                space_id=direct_space_id,
            )
            assert global_policy["space_id"] == direct_space_id
            assert global_policy["sublocation_id"] is None
            assert global_policy["location_label"] == "Direct"

            isolation_configuration_count = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM household_product_configuration
                        WHERE household_id = :household_id
                        """
                    ),
                    {"household_id": ISOLATION_HOUSEHOLD},
                ).scalar_one()
            )
            isolation_space_count = int(
                conn.execute(
                    text("SELECT COUNT(*) FROM spaces WHERE household_id = :household_id"),
                    {"household_id": ISOLATION_HOUSEHOLD},
                ).scalar_one()
            )
            assert isolation_configuration_count == 0
            assert isolation_space_count == 0
        checks.append("database_and_runtime_policy_match_saved_settings")
        checks.append("unrelated_household_remains_isolated")
    finally:
        engine.dispose()

    for check in checks:
        print(f"PASS {check}")
    print(f"RESULT {len(checks)}/{len(checks)} checks passed")
    print("SETTINGS_LOCATION_POLICY_API_POSTGRESQL_GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
