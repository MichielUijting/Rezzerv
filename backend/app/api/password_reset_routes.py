from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.db import engine
from app.services.password_reset_delivery_service import (
    send_password_changed_email,
    send_password_reset_email,
)
from app.services.password_reset_service import (
    PasswordResetConfigurationError,
    PasswordResetInvalidTokenError,
    PasswordResetPasswordReuseError,
    confirm_password_reset,
    request_password_reset,
    revoke_password_reset_token,
)


router = APIRouter()
logger = logging.getLogger(__name__)

GENERIC_RESET_REQUEST_MESSAGE = (
    "Als dit e-mailadres bij ons bekend is, ontvang je een e-mail waarmee je "
    "je wachtwoord opnieuw kunt instellen."
)


class PasswordResetRequestPayload(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized or "@" not in normalized or len(normalized) > 320:
            raise ValueError("Geldig e-mailadres is verplicht")
        return normalized


class PasswordResetConfirmPayload(BaseModel):
    token: str
    new_password: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        token = str(value or "").strip()
        if not token or len(token) > 512:
            raise ValueError("Herstellink is ongeldig of verlopen")
        return token

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        supplied = str(value or "")
        if len(supplied) < 10:
            raise ValueError("Nieuw wachtwoord moet minimaal 10 tekens bevatten")
        if len(supplied) > 256:
            raise ValueError("Nieuw wachtwoord mag maximaal 256 tekens bevatten")
        return supplied


def _deliver_reset_email(
    *,
    recipient_email: str,
    raw_token: str,
    token_hash: str,
) -> None:
    result = send_password_reset_email(
        recipient_email=recipient_email,
        raw_token=raw_token,
    )
    if result.sent:
        return
    logger.warning("Password-reset e-mail kon niet veilig worden afgeleverd: %s", result.message)
    try:
        with engine.begin() as conn:
            revoke_password_reset_token(conn, token_hash=token_hash)
    except Exception:
        logger.exception("Password-reset token kon na mailfout niet worden ingetrokken")


def _deliver_password_changed_email(*, recipient_email: str) -> None:
    result = send_password_changed_email(recipient_email=recipient_email)
    if not result.sent:
        logger.warning("Password-changed securitymail kon niet worden afgeleverd: %s", result.message)


@router.post("/api/auth/password-reset/request", status_code=202)
def request_account_password_reset(
    payload: PasswordResetRequestPayload,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    client_ip = str(request.client.host if request.client else "unknown")
    try:
        with engine.begin() as conn:
            result = request_password_reset(
                conn,
                email=payload.email,
                client_ip=client_ip,
            )
    except PasswordResetConfigurationError as exc:
        # Fail closed without exposing whether this e-mail belongs to an account.
        logger.error("Password-reset configuratie is niet veilig bruikbaar: %s", exc)
        return {"message": GENERIC_RESET_REQUEST_MESSAGE}

    if (
        result.account_found
        and not result.rate_limited
        and result.recipient_email
        and result.raw_token
        and result.token_hash
    ):
        background_tasks.add_task(
            _deliver_reset_email,
            recipient_email=result.recipient_email,
            raw_token=result.raw_token,
            token_hash=result.token_hash,
        )

    return {"message": GENERIC_RESET_REQUEST_MESSAGE}


@router.post("/api/auth/password-reset/confirm")
def confirm_account_password_reset(
    payload: PasswordResetConfirmPayload,
    background_tasks: BackgroundTasks,
) -> dict[str, object]:
    try:
        with engine.begin() as conn:
            result = confirm_password_reset(
                conn,
                raw_token=payload.token,
                new_password=payload.new_password,
            )
    except PasswordResetInvalidTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PasswordResetPasswordReuseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if result.email:
        background_tasks.add_task(
            _deliver_password_changed_email,
            recipient_email=result.email,
        )

    return {
        "password_updated": True,
        "revoked_sessions": result.revoked_sessions,
        "message": "Wachtwoord gewijzigd. Log opnieuw in met je nieuwe wachtwoord.",
    }
