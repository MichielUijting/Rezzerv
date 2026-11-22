from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.db import engine
from app.services.authorization_foundation_service import evaluate_platform_permission
from app.services.consumer_account_deletion_service import (
    AccountDeletionConflictError,
    delete_platform_managed_account,
    deletion_preview,
)
from app.services.consumer_account_file_deletion_service import (
    HouseholdFileStage,
    AccountFileDeletionConflict,
)
from app.services.platform_user_suspension_service import (
    PlatformUserConflictError,
    PlatformUserNotFoundError,
    list_platform_users,
    suspend_platform_user,
    unsuspend_platform_user,
)
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_USERS_SUSPEND_PERMISSION = "platform.users.suspend"
PLATFORM_USERS_DELETE_PERMISSION = "platform.users.delete"

router = APIRouter()


class PlatformUserDeleteRequest(BaseModel):
    confirmation: str

    @field_validator("confirmation")
    @classmethod
    def valid_confirmation(cls, value: str) -> str:
        if not value or len(value) > 350:
            raise ValueError("Vul de vereiste bevestiging in.")
        return value


def _require_other_user(user_id: str, actor_user_id: str) -> None:
    if not str(user_id or "").strip() or str(user_id).strip() == str(actor_user_id).strip():
        raise HTTPException(status_code=409, detail="Je kunt je eigen beheeraccount hier niet wijzigen.")



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
        can_delete = evaluate_platform_permission(
            conn, user_id=context.user_id,
            permission_key=PLATFORM_USERS_DELETE_PERMISSION,
        ).allowed
    return {
        "items": items,
        "can_delete": bool(can_delete),
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


@router.post("/api/platform/users/{user_id}/unsuspend")
def unsuspend_user(user_id: str) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_USERS_SUSPEND_PERMISSION
    )
    try:
        with engine.begin() as conn:
            item = unsuspend_platform_user(
                conn, user_id, actor_user_id=context.user_id,
            )
    except PlatformUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlatformUserConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "item": item, "household_context_used": False,
        "context_type": context.context_type,
    }


@router.get("/api/platform/users/{user_id}/deletion-preview")
def get_platform_user_deletion_preview(user_id: str) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_USERS_DELETE_PERMISSION
    )
    _require_other_user(user_id, context.user_id)
    try:
        with engine.connect() as conn:
            preview = deletion_preview(conn, user_id=user_id)
    except AccountDeletionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {**preview, "user_id": user_id}


@router.delete("/api/platform/users/{user_id}")
def delete_platform_user(user_id: str, payload: PlatformUserDeleteRequest) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_USERS_DELETE_PERMISSION
    )
    _require_other_user(user_id, context.user_id)
    try:
        stage = HouseholdFileStage()
        try:
            with engine.begin() as conn:
                outcome = delete_platform_managed_account(
                    conn, user_id=user_id, actor_user_id=context.user_id,
                    confirmation=payload.confirmation, file_stage=stage,
                )
        except Exception:
            stage.restore()
            raise
        stage.finalize()
    except (AccountDeletionConflictError, AccountFileDeletionConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        **outcome, "message": "Gebruiker definitief verwijderd.",
        "household_context_used": False, "context_type": context.context_type,
    }
