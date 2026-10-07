from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import engine
from app.services.authorization_foundation_service import write_authorization_audit
from app.services.household_reset_service import (
    HouseholdResetConflictError,
    HouseholdResetNotFoundError,
    reset_household_data,
)
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_HOUSEHOLD_RESET_PERMISSION = "platform.recovery.manage"

router = APIRouter()


class HouseholdResetRequest(BaseModel):
    household_id: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=256)


@router.post("/api/platform/recovery/reset-household")
def reset_household(payload: HouseholdResetRequest) -> dict:
    context = require_platform_permission_from_session(
        PLATFORM_HOUSEHOLD_RESET_PERMISSION
    )
    try:
        with engine.begin() as conn:
            result = reset_household_data(
                conn,
                payload.household_id,
                confirmation=payload.confirmation,
            )
            audit_id = write_authorization_audit(
                conn,
                actor_user_id=context.user_id,
                actor_type="platform_admin",
                household_id=result["household_id"],
                action="platform.household.reset",
                object_type="household",
                object_id=result["household_id"],
                new_value={
                    "deleted_row_count": result["deleted_row_count"],
                    "deleted_tables": sorted(result["deleted_by_table"]),
                    "preserved_member_count": result["preserved_member_count"],
                    "sessions_revoked": result["sessions_revoked"],
                },
                reason=(
                    "Platformbeheerder voerde een expliciet bevestigde volledige "
                    "huishoudreset uit met behoud van account- en lidmaatschapsidentiteit."
                ),
            )
            return {
                **result,
                "audit_id": audit_id,
                "household_context_used": False,
                "context_type": context.context_type,
            }
    except HouseholdResetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HouseholdResetConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
