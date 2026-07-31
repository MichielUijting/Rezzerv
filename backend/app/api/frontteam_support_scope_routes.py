from __future__ import annotations

from fastapi import APIRouter, Header

from app.db import engine
from app.services.frontteam_support_scope_service import resolve_support_household_scope
from app.services.platform_actor_service import resolve_platform_actor


router = APIRouter(tags=["meldingen-en-autorisatie"])


def _runtime_user(authorization: str | None):
    from app import main as main_module

    return main_module.get_current_user_from_authorization(authorization)


@router.get("/api/platform/support/bereik")
def get_platform_support_scope(authorization: str | None = Header(None)):
    runtime_user = _runtime_user(authorization)
    with engine.begin() as conn:
        actor = resolve_platform_actor(
            conn,
            runtime_user=runtime_user,
            permission_key="platform.support_access.read",
        )
        scope = resolve_support_household_scope(conn, actor=actor)
    return {
        "rol": actor.role,
        "onbeperkt": scope.unrestricted,
        "toegestane_huishoudens": list(scope.household_ids),
    }
