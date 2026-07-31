from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.db import engine
from app.services.authorization_foundation_service import PLATFORM_PERMISSIONS
from app.services.platform_actor_service import resolve_platform_actor

router = APIRouter(prefix="/api/platform", tags=["centrale-autorisatie"])

ALLOWED_PERMISSION_PROBES = frozenset(PLATFORM_PERMISSIONS)


@router.get("/toegang")
def get_platform_access(
    bevoegdheid: str = Query(min_length=1, max_length=120),
    authorization: str | None = Header(None),
):
    permission_key = str(bevoegdheid or "").strip()
    if permission_key not in ALLOWED_PERMISSION_PROBES:
        raise HTTPException(status_code=400, detail="Onbekende centrale bevoegdheid")

    from app import main as main_module

    runtime_user = main_module.get_current_user_from_authorization(authorization)
    with engine.begin() as conn:
        actor = resolve_platform_actor(
            conn,
            runtime_user=runtime_user,
            permission_key=permission_key,
        )
    return {
        "toegang": True,
        "bevoegdheid": permission_key,
        "rol": actor.role,
        "rolcode": actor.role_key,
        "gebruiker": actor.email,
    }
