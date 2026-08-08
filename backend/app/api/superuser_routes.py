"""Read-only Superuser beheercentrum foundation routes.

S1 exposes only an access/bootstrap endpoint and an auditable screen-open event.
No household data or mutation endpoint is introduced in this release.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.authorization_foundation_service import (
    ensure_authorization_foundation,
    write_authorization_audit,
)
from app.services.server_session_service import SESSION_COOKIE_NAME, resolve_server_session


SUPERUSER_ROLE_KEY = "platform.superuser"
SUPERUSER_TABS = ("Overzicht", "Huishoudens", "Gebruik", "Kassabonnen", "Systeem")


def _require_platform_superuser(conn, raw_session_id: str | None):
    context = resolve_server_session(conn, raw_session_id)
    ensure_authorization_foundation(conn)
    granted = conn.execute(
        text(
            """
            SELECT 1
            FROM auth_platform_user_roles
            WHERE user_id = :user_id
              AND role_key = :role_key
              AND active = 1
            LIMIT 1
            """
        ),
        {"user_id": context.user_id, "role_key": SUPERUSER_ROLE_KEY},
    ).first()
    if not granted:
        raise HTTPException(
            status_code=403,
            detail="Alleen de platform-supergebruiker heeft toegang tot het Rezzerv Beheercentrum",
        )
    return context


def create_superuser_router(engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/api/superuser/bootstrap")
    def bootstrap(request: Request):
        with engine.begin() as conn:
            context = _require_platform_superuser(
                conn,
                request.cookies.get(SESSION_COOKIE_NAME),
            )
        return {
            "access": "read_only",
            "role": SUPERUSER_ROLE_KEY,
            "tabs": list(SUPERUSER_TABS),
            "user_id": context.user_id,
        }

    @router.post("/api/superuser/audit/open", status_code=204)
    def audit_open(request: Request):
        with engine.begin() as conn:
            context = _require_platform_superuser(
                conn,
                request.cookies.get(SESSION_COOKIE_NAME),
            )
            write_authorization_audit(
                conn,
                actor_user_id=context.user_id,
                actor_type="platform_superuser",
                action="superuser.manage_center.opened",
                object_type="superuser_manage_center",
                reason="Superuser opende Rezzerv Beheercentrum",
            )
        return None

    return router
