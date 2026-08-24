from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import engine
from app.services.platform_feature_flag_service import (
    list_platform_feature_flags,
    set_platform_feature_flag,
)
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_FEATURE_FLAGS_MANAGE_PERMISSION = "platform.feature_flags.manage"

router = APIRouter()


class PlatformFeatureFlagUpdateRequest(BaseModel):
    enabled: bool


@router.get("/api/platform/feature-flags")
def get_platform_feature_flags() -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_FEATURE_FLAGS_MANAGE_PERMISSION
    )
    with engine.connect() as conn:
        items = list_platform_feature_flags(conn)
    return {
        "items": items,
        "count": len(items),
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.put("/api/platform/feature-flags/{flag_key}")
def update_platform_feature_flag(
    flag_key: str,
    payload: PlatformFeatureFlagUpdateRequest,
) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_FEATURE_FLAGS_MANAGE_PERMISSION
    )
    try:
        with engine.begin() as conn:
            item = set_platform_feature_flag(
                conn,
                flag_key,
                enabled=payload.enabled,
                updated_by=context.user_id,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Onbekende platformfeatureflag") from exc

    return {
        "item": item,
        "household_context_used": False,
        "context_type": context.context_type,
    }
