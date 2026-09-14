from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import engine
from app.services.platform_feature_flag_service import (
    list_platform_feature_flags,
    list_home_action_flags,
    set_platform_feature_flag,
    require_feature_category,
    require_home_action,
)
from app.services.session_request_context import (
    require_platform_permission_from_session,
    resolve_current_server_session,
)


PLATFORM_FEATURE_FLAGS_MANAGE_PERMISSION = "platform.feature_flags.manage"
FUNCTIONAL_FEATURES_MANAGE_PERMISSION = "platform.functional_features.manage"
ACTION_BUTTONS_MANAGE_PERMISSION = FUNCTIONAL_FEATURES_MANAGE_PERMISSION

router = APIRouter()


class PlatformFeatureFlagUpdateRequest(BaseModel):
    enabled: bool


def _technical_flag_contract(item: dict) -> dict:
    """Keep the pre-existing technical Feature Flags response shape stable."""
    return {
        "key": item["key"],
        "label": item["label"],
        "description": item["description"],
        "enabled": item["enabled"],
        "default_enabled": item["default_enabled"],
        "source": item["source"],
        "updated_by": item["updated_by"],
        "updated_at": item["updated_at"],
    }


@router.get("/api/platform/feature-flags")
def get_platform_feature_flags() -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_FEATURE_FLAGS_MANAGE_PERMISSION
    )
    with engine.connect() as conn:
        items = [
            _technical_flag_contract(item)
            for item in list_platform_feature_flags(conn, category="technical")
        ]
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
        require_feature_category(flag_key, "technical")
        with engine.begin() as conn:
            item = _technical_flag_contract(set_platform_feature_flag(
                conn,
                flag_key,
                enabled=payload.enabled,
                updated_by=context.user_id,
            ))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Onbekende platformfeatureflag") from exc

    return {
        "item": item,
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.get("/api/features")
def get_feature_availability() -> dict:
    """Authenticated product projection; no actor or management metadata."""
    resolve_current_server_session()
    with engine.connect() as conn:
        items = list_platform_feature_flags(conn, category="functional")
    return {"features": {item["key"]: item["enabled"] for item in items}}


@router.get("/api/platform/functional-features")
def get_functional_features() -> dict:
    context = require_platform_permission_from_session(FUNCTIONAL_FEATURES_MANAGE_PERMISSION)
    with engine.connect() as conn:
        items = list_platform_feature_flags(conn, category="functional")
    return {
        "items": items,
        "count": len(items),
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.put("/api/platform/functional-features/{flag_key}")
def update_functional_feature(
    flag_key: str,
    payload: PlatformFeatureFlagUpdateRequest,
) -> dict:
    context = require_platform_permission_from_session(FUNCTIONAL_FEATURES_MANAGE_PERMISSION)
    try:
        require_feature_category(flag_key, "functional")
        with engine.begin() as conn:
            item = set_platform_feature_flag(
                conn,
                flag_key,
                enabled=payload.enabled,
                updated_by=context.user_id,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Onbekende functionele feature") from exc
    return {
        "item": item,
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.get("/api/action-buttons")
def get_action_button_availability() -> dict:
    """Authenticated projection for the globally managed Startpagina actions."""
    resolve_current_server_session()
    with engine.connect() as conn:
        items = list_home_action_flags(conn)
    return {
        "items": [
            {
                "key": item["key"],
                "home_tile_key": item.get("home_tile_key"),
                "enabled": item["enabled"],
            }
            for item in items
        ]
    }


@router.get("/api/platform/action-buttons")
def get_action_buttons() -> dict:
    context = require_platform_permission_from_session(ACTION_BUTTONS_MANAGE_PERMISSION)
    with engine.connect() as conn:
        items = list_home_action_flags(conn)
    return {
        "items": items,
        "count": len(items),
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.put("/api/platform/action-buttons/{flag_key}")
def update_action_button(
    flag_key: str,
    payload: PlatformFeatureFlagUpdateRequest,
) -> dict:
    context = require_platform_permission_from_session(ACTION_BUTTONS_MANAGE_PERMISSION)
    try:
        require_home_action(flag_key)
        with engine.begin() as conn:
            item = set_platform_feature_flag(
                conn,
                flag_key,
                enabled=payload.enabled,
                updated_by=context.user_id,
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Onbekende actie op de Startpagina") from exc
    return {
        "item": item,
        "household_context_used": False,
        "context_type": context.context_type,
    }
