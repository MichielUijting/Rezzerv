from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.routing import APIRoute

LEGACY_MEMBER_CREATE_PATH = "/api/household/members"
LEGACY_MEMBER_CREATE_ENDPOINT_NAME = "create_household_member"
REPLACEMENT_INVITATION_PATH = "/api/household/invitations"


def _is_legacy_member_create_route(route: Any) -> bool:
    if not isinstance(route, APIRoute):
        return False
    methods = {str(method).upper() for method in (route.methods or set())}
    endpoint_name = str(getattr(getattr(route, "endpoint", None), "__name__", ""))
    return (
        route.path == LEGACY_MEMBER_CREATE_PATH
        and "POST" in methods
        and endpoint_name == LEGACY_MEMBER_CREATE_ENDPOINT_NAME
    )


def retire_legacy_household_member_create_route(app: FastAPI) -> APIRoute:
    """Remove exactly the pre-I.1 direct member-create endpoint.

    GET/PUT/DELETE household-member endpoints are intentionally left untouched.
    Failing loudly when the expected route is not present prevents a future refactor
    from accidentally reopening or shadowing the retired creation path.
    """

    matches = [route for route in app.router.routes if _is_legacy_member_create_route(route)]
    if len(matches) != 1:
        raise RuntimeError(
            "Legacy household member creation closure expected exactly one "
            f"POST {LEGACY_MEMBER_CREATE_PATH} route named "
            f"{LEGACY_MEMBER_CREATE_ENDPOINT_NAME!r}; found {len(matches)}"
        )

    retired = matches[0]
    app.router.routes[:] = [route for route in app.router.routes if route is not retired]
    return retired


def retire_legacy_household_member_create_route_from_loaded_main() -> bool:
    """Apply the closure while app.main is finishing its route registration.

    app.api.router is imported at the bottom of app.main, after the legacy routes
    exist and before the canonical API router is included. Standalone imports of
    app.api.router (for tooling/tests) do not mutate or import app.main.
    """

    main_module = sys.modules.get("app.main")
    app = getattr(main_module, "app", None) if main_module is not None else None
    if app is None:
        return False
    retire_legacy_household_member_create_route(app)
    return True


def create_legacy_household_member_creation_closure_router() -> APIRouter:
    router = APIRouter(tags=["household-members-legacy-closure"])

    @router.post(LEGACY_MEMBER_CREATE_PATH, status_code=410)
    def legacy_household_member_creation_retired():
        raise HTTPException(
            status_code=410,
            detail={
                "code": "legacy_household_member_creation_retired",
                "message": (
                    "Direct huishoudleden koppelen is beëindigd. "
                    "Maak voortaan een huishoud-uitnodiging aan."
                ),
                "replacement": REPLACEMENT_INVITATION_PATH,
            },
        )

    return router
