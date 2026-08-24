from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_AUDIT_VIEW_PERMISSION = "platform.audit.view"
PLATFORM_AUDIT_DEFAULT_LIMIT = 50
PLATFORM_AUDIT_MAX_LIMIT = 200

router = APIRouter()


def list_platform_authorization_audit(conn, *, limit: int) -> list[dict]:
    """Return a deliberately minimal, non-payload audit projection.

    The authorization audit table can contain old/new values, reasons and ticket
    references. Those fields may contain operational or user-provided details and
    are intentionally not exposed by the Platformbeheerder read API in 9.1.7e2.
    """

    rows = conn.execute(
        text(
            """
            SELECT
                id,
                actor_user_id,
                actor_type,
                household_id,
                action,
                object_type,
                object_id,
                created_at
            FROM auth_audit_log
            ORDER BY created_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"limit": int(limit)},
    ).mappings().all()
    return [dict(row) for row in rows]


@router.get("/api/platform/audit")
def get_platform_authorization_audit(
    limit: int = Query(default=PLATFORM_AUDIT_DEFAULT_LIMIT, ge=1, le=PLATFORM_AUDIT_MAX_LIMIT),
) -> dict:
    require_platform_permission_from_session(PLATFORM_AUDIT_VIEW_PERMISSION)
    with engine.begin() as conn:
        items = list_platform_authorization_audit(conn, limit=limit)
    return {
        "items": items,
        "count": len(items),
        "limit": int(limit),
    }
