from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.engine import Engine

from app.api.server_session_routes import SessionApiConfiguration, session_api_configuration_from_environment
from app.services.household_invitation_acceptance_service import (
    InvitationAccountExistsError,
    InvitationEmailMismatchError,
    InvitationMembershipConflictError,
    accept_household_invitation,
    preview_household_invitation,
    provision_invited_consumer_account,
)
from app.services.household_invitation_service import InvitationConflictError, InvitationNotFoundError
from app.services.household_invitation_target_policy import InvitationTargetNotAllowedError
from app.services.server_session_service import (
    DEFAULT_SESSION_TTL,
    SESSION_COOKIE_NAME,
    create_server_session,
    public_session_payload,
    resolve_server_session,
    rotate_active_household,
)


class InvitationRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("Geldig e-mailadres is verplicht")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        supplied = str(value or "")
        if len(supplied) < 10:
            raise ValueError("Wachtwoord moet minimaal 10 tekens bevatten")
        if len(supplied) > 256:
            raise ValueError("Wachtwoord mag maximaal 256 tekens bevatten")
        return supplied


def _set_session_cookie(
    response: Response,
    raw_session_id: str,
    configuration: SessionApiConfiguration,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session_id,
        max_age=int(DEFAULT_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=configuration.cookie_secure,
        samesite=configuration.cookie_samesite,
        path=configuration.cookie_path,
    )


def _raise_acceptance_http_error(exc: Exception) -> None:
    if isinstance(exc, InvitationNotFoundError):
        raise HTTPException(status_code=404, detail="Uitnodiging niet gevonden") from exc
    if isinstance(exc, (InvitationEmailMismatchError, InvitationTargetNotAllowedError)):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, (InvitationConflictError, InvitationAccountExistsError, InvitationMembershipConflictError)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


def create_household_invitation_acceptance_router(
    engine: Engine,
    configuration: SessionApiConfiguration | None = None,
) -> APIRouter:
    configuration = configuration or session_api_configuration_from_environment()
    router = APIRouter(tags=["household-invitation-acceptance"])

    @router.get("/api/household/invitations/accept/{raw_token}")
    def preview_invitation(raw_token: str, request: Request):
        try:
            with engine.begin() as conn:
                preview = preview_household_invitation(conn, raw_token=raw_token)
                authenticated = False
                authenticated_email_matches = False
                raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
                if raw_session_id:
                    try:
                        current = resolve_server_session(conn, raw_session_id)
                        authenticated = True
                        authenticated_email_matches = (
                            str(current.email or "").strip().lower()
                            == str(preview.get("invitee_email_masked") or "").strip().lower()
                        )
                    except HTTPException:
                        pass
                # The full invited e-mail address is deliberately never returned.
                preview["authenticated"] = authenticated
                preview["authenticated_email_matches"] = authenticated_email_matches
                return preview
        except Exception as exc:
            _raise_acceptance_http_error(exc)

    @router.post("/api/household/invitations/accept/{raw_token}")
    def accept_existing_account(raw_token: str, request: Request, response: Response):
        raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not raw_session_id:
            raise HTTPException(status_code=401, detail="Log eerst in met het uitgenodigde account")
        try:
            with engine.begin() as conn:
                current = resolve_server_session(conn, raw_session_id)
                if current.context_type != "regular":
                    raise HTTPException(
                        status_code=403,
                        detail="Deze uitnodiging kan alleen met een regulier account worden geaccepteerd",
                    )
                accepted = accept_household_invitation(
                    conn,
                    raw_token=raw_token,
                    user_id=current.user_id,
                    email=current.email,
                )
                raw_new_session_id, new_context = rotate_active_household(
                    conn,
                    raw_session_id,
                    accepted.household_id,
                )
                payload = dict(public_session_payload(new_context))
                payload["active_household_name"] = accepted.household_name
                payload["invitation_accepted"] = True
                payload["membership_id"] = accepted.membership_id
            _set_session_cookie(response, raw_new_session_id, configuration)
            return payload
        except HTTPException:
            raise
        except Exception as exc:
            _raise_acceptance_http_error(exc)

    @router.post(
        "/api/household/invitations/accept/{raw_token}/register",
        status_code=status.HTTP_201_CREATED,
    )
    def register_and_accept(
        raw_token: str,
        payload: InvitationRegistrationRequest,
        response: Response,
    ):
        try:
            with engine.begin() as conn:
                invitation_preview = preview_household_invitation(conn, raw_token=raw_token)
                # Exact e-mail binding is enforced again inside accept_household_invitation;
                # preview deliberately exposes only a masked address.
                account = provision_invited_consumer_account(
                    conn,
                    email=payload.email,
                    password=payload.password,
                )
                accepted = accept_household_invitation(
                    conn,
                    raw_token=raw_token,
                    user_id=account["user_id"],
                    email=account["email"],
                )
                raw_session_id, context = create_server_session(
                    conn,
                    user_id=accepted.user_id,
                    active_household_id=accepted.household_id,
                    replace_existing=True,
                )
                session_payload = dict(public_session_payload(context))
                session_payload["active_household_name"] = accepted.household_name
                session_payload["invitation_accepted"] = True
                session_payload["membership_id"] = accepted.membership_id
                session_payload["invitation_preview"] = invitation_preview
            _set_session_cookie(response, raw_session_id, configuration)
            return session_payload
        except HTTPException:
            raise
        except Exception as exc:
            _raise_acceptance_http_error(exc)

    return router
