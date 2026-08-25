from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.db import engine
from app.services.consumer_account_management_service import (
    ConsumerAccountNotFoundError,
    ConsumerCurrentPasswordMismatchError,
    ConsumerPasswordReuseError,
    change_consumer_password,
)
from app.services.session_request_context import resolve_current_server_session


router = APIRouter()


class ConsumerPasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("current_password")
    @classmethod
    def validate_current_password(cls, value: str) -> str:
        supplied = str(value or "")
        if not supplied:
            raise ValueError("Huidig wachtwoord is verplicht")
        if len(supplied) > 256:
            raise ValueError("Huidig wachtwoord mag maximaal 256 tekens bevatten")
        return supplied

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        supplied = str(value or "")
        if len(supplied) < 10:
            raise ValueError("Nieuw wachtwoord moet minimaal 10 tekens bevatten")
        if len(supplied) > 256:
            raise ValueError("Nieuw wachtwoord mag maximaal 256 tekens bevatten")
        return supplied


def _require_regular_consumer_session():
    context = resolve_current_server_session()
    if context.context_type != "regular":
        raise HTTPException(
            status_code=403,
            detail="Mijn account is alleen beschikbaar in een reguliere accountcontext.",
        )
    return context


@router.post("/api/account/password")
def update_account_password(payload: ConsumerPasswordChangeRequest) -> dict:
    context = _require_regular_consumer_session()
    try:
        with engine.begin() as conn:
            result = change_consumer_password(
                conn,
                user_id=context.user_id,
                current_session_id=context.session_id,
                current_password=payload.current_password,
                new_password=payload.new_password,
            )
    except ConsumerAccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConsumerCurrentPasswordMismatchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConsumerPasswordReuseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        **result,
        "message": "Wachtwoord gewijzigd. Andere actieve sessies zijn ingetrokken.",
        "context_type": context.context_type,
    }
