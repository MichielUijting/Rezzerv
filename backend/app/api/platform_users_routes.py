from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import engine
from app.services.platform_user_suspension_service import (
    PlatformUserConflictError,
    PlatformUserNotFoundError,
    list_platform_users,
    suspend_platform_user,
)
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_USERS_SUSPEND_PERMISSION = "platform.users.suspend"

router = APIRouter()


@router.get("/api/platform/users")
def get_platform_users() -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_USERS_SUSPEND_PERMISSION
    )
    with engine.connect() as conn:
        items = list_platform_users(
            conn,
            current_user_id=context.user_id,
        )
    return {
        "items": items,
        "count": len(items),
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.post("/api/platform/users/{user_id}/suspend")
def suspend_user(user_id: str) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_USERS_SUSPEND_PERMISSION
    )
    try:
        with engine.begin() as conn:
            item = suspend_platform_user(
                conn,
                user_id,
                actor_user_id=context.user_id,
            )
    except PlatformUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlatformUserConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "item": item,
        "household_context_used": False,
        "context_type": context.context_type,
    }
