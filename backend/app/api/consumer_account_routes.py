from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, field_validator

from app.db import engine
from app.services.consumer_account_management_service import (
    ConsumerAccountNotFoundError,
    ConsumerCurrentPasswordMismatchError,
    ConsumerPasswordReuseError,
    change_consumer_password,
)
from app.services.password_reset_delivery_service import (
    deliver_password_changed_email,
    deliver_password_reset_email,
)
from app.services.password_reset_service import (
    PASSWORD_RESET_GENERIC_MESSAGE,
    PASSWORD_RESET_INVALID_MESSAGE,
    PasswordResetTokenInvalidError,
    confirm_password_reset,
    issue_password_reset,
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


class PasswordResetRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        supplied = str(value or "").strip().lower()
        if not supplied:
            raise ValueError("E-mailadres is verplicht")
        if len(supplied) > 320:
            raise ValueError("E-mailadres mag maximaal 320 tekens bevatten")
        if "@" not in supplied or supplied.startswith("@") or supplied.endswith("@"):
            raise ValueError("Vul een geldig e-mailadres in")
        return supplied


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        supplied = str(value or "").strip()
        if not supplied:
            raise ValueError("Herstelcode ontbreekt")
        if len(supplied) > 512:
            raise ValueError("Herstelcode is ongeldig")
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


def _request_ip(request: Request) -> str | None:
    # Trust only the direct peer. Proxy-header trust belongs at the deployment boundary,
    # not inside this public authentication endpoint.
    return request.client.host if request.client is not None else None


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


@router.post(
    "/api/auth/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """Accept recovery requests without disclosing whether an account exists."""
    with engine.begin() as conn:
        result = issue_password_reset(
            conn,
            email=payload.email,
            request_ip=_request_ip(request),
        )

    if result.should_deliver:
        background_tasks.add_task(
            deliver_password_reset_email,
            email=str(result.email),
            raw_token=str(result.raw_token),
        )

    # Unknown e-mail, rate-limited e-mail and successful issuance are indistinguishable.
    return {"message": PASSWORD_RESET_GENERIC_MESSAGE}


@router.post("/api/auth/password-reset/confirm")
def confirm_forgotten_password(
    payload: PasswordResetConfirmRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    try:
        with engine.begin() as conn:
            result = confirm_password_reset(
                conn,
                raw_token=payload.token,
                new_password=payload.new_password,
            )
    except PasswordResetTokenInvalidError as exc:
        raise HTTPException(status_code=400, detail=PASSWORD_RESET_INVALID_MESSAGE) from exc

    background_tasks.add_task(
        deliver_password_changed_email,
        email=result.email,
    )
    return {
        "message": (
            "Je wachtwoord is gewijzigd. Alle bestaande sessies zijn beëindigd. "
            "Log opnieuw in met je nieuwe wachtwoord."
        )
    }
