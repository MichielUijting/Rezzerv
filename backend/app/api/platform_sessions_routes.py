from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import engine
from app.services.platform_session_management_service import (
    PlatformSessionConflictError,
    PlatformSessionNotFoundError,
    list_platform_sessions,
    revoke_platform_session_by_id,
)
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_SESSIONS_REVOKE_PERMISSION = "platform.sessions.revoke"

router = APIRouter()


@router.get("/api/platform/sessions")
def get_platform_sessions() -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_SESSIONS_REVOKE_PERMISSION
    )
    with engine.connect() as conn:
        items = list_platform_sessions(
            conn,
            current_session_id=context.session_id,
        )
    return {
        "items": items,
        "count": len(items),
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.post("/api/platform/sessions/{session_id}/revoke")
def revoke_platform_session(session_id: str) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_SESSIONS_REVOKE_PERMISSION
    )
    try:
        with engine.begin() as conn:
            item = revoke_platform_session_by_id(
                conn,
                session_id,
                current_session_id=context.session_id,
            )
    except PlatformSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlatformSessionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "item": item,
        "household_context_used": False,
        "context_type": context.context_type,
    }
