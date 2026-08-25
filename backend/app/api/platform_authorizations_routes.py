from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db import engine
from app.services.platform_authorization_management_service import (
    FRONTTEAM_ROLE_KEY,
    PLATFORM_ADMIN_ROLE_KEY,
    PLATFORM_PERMISSIONS_MANAGE,
    PLATFORM_SPECIAL_ROLES_MANAGE,
    SUPERUSER_ROLE_KEY,
    PlatformAuthorizationConflictError,
    PlatformAuthorizationNotFoundError,
    grant_special_role,
    list_platform_authorizations,
    revoke_special_role,
)
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_AUTHORIZATIONS_PERMISSION = PLATFORM_PERMISSIONS_MANAGE
PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION = PLATFORM_SPECIAL_ROLES_MANAGE

router = APIRouter()


@router.get("/api/platform/authorizations")
def get_platform_authorizations() -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_AUTHORIZATIONS_PERMISSION
    )
    with engine.connect() as conn:
        payload = list_platform_authorizations(
            conn,
            current_user_id=context.user_id,
        )
    return {
        **payload,
        "household_context_used": False,
        "context_type": context.context_type,
    }


def _run_role_change(user_id: str, *, role_key: str, operation) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_SPECIAL_ROLE_MUTATION_PERMISSION
    )
    try:
        with engine.begin() as conn:
            item = operation(
                conn,
                user_id,
                role_key=role_key,
                actor_user_id=context.user_id,
            )
    except PlatformAuthorizationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlatformAuthorizationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "item": item,
        "household_context_used": False,
        "context_type": context.context_type,
    }


@router.post("/api/platform/authorizations/users/{user_id}/superuser/grant")
def grant_user_superuser(user_id: str) -> dict:
    return _run_role_change(
        user_id,
        role_key=SUPERUSER_ROLE_KEY,
        operation=grant_special_role,
    )


@router.post("/api/platform/authorizations/users/{user_id}/superuser/revoke")
def revoke_user_superuser(user_id: str) -> dict:
    return _run_role_change(
        user_id,
        role_key=SUPERUSER_ROLE_KEY,
        operation=revoke_special_role,
    )


@router.post("/api/platform/authorizations/users/{user_id}/frontteam/grant")
def grant_user_frontteam(user_id: str) -> dict:
    return _run_role_change(
        user_id,
        role_key=FRONTTEAM_ROLE_KEY,
        operation=grant_special_role,
    )


@router.post("/api/platform/authorizations/users/{user_id}/frontteam/revoke")
def revoke_user_frontteam(user_id: str) -> dict:
    return _run_role_change(
        user_id,
        role_key=FRONTTEAM_ROLE_KEY,
        operation=revoke_special_role,
    )


@router.post("/api/platform/authorizations/users/{user_id}/platform-admin/grant")
def grant_user_platform_admin(user_id: str) -> dict:
    return _run_role_change(
        user_id,
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        operation=grant_special_role,
    )


@router.post("/api/platform/authorizations/users/{user_id}/platform-admin/revoke")
def revoke_user_platform_admin(user_id: str) -> dict:
    return _run_role_change(
        user_id,
        role_key=PLATFORM_ADMIN_ROLE_KEY,
        operation=revoke_special_role,
    )
