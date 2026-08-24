from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.services.authorization_membership_service import (
    AuthorizationDeniedError,
    require_household_permission,
)
from app.services.household_invitation_delivery_service import (
    DELIVERY_STATUS_CONFIG_INVALID,
    DELIVERY_STATUS_DISABLED,
    DELIVERY_STATUS_SENT,
    InvitationEmailConfiguration,
    InvitationEmailTransport,
    deliver_created_household_invitation,
    get_household_invitation_with_delivery,
    list_household_invitations_with_delivery,
    resend_household_invitation,
)
from app.services.household_invitation_service import (
    InvitationConflictError,
    InvitationNotFoundError,
    create_household_invitation,
    revoke_household_invitation,
)
from app.services.household_invitation_target_policy import (
    InvitationTargetNotAllowedError,
    assert_household_invitation_target_allowed,
)
from app.services.server_session_service import (
    SESSION_COOKIE_NAME,
    membership_active_condition,
    membership_id_expression,
    resolve_server_session,
)


class HouseholdInvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("Geldig e-mailadres is verplicht")
        local, _, domain = normalized.partition("@")
        if not local or not domain or "." not in domain:
            raise ValueError("Geldig e-mailadres is verplicht")
        return normalized


def _actor_context(conn, request: Request) -> dict[str, str]:
    raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = resolve_server_session(conn, raw_session_id)
    if session.context_type != "regular" or not session.active_household_id:
        raise HTTPException(
            status_code=403,
            detail="Uitnodigingen zijn alleen beschikbaar vanuit een regulier huishouden",
        )

    membership_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspect(conn).get_columns("household_memberships")
    }
    if "household_id" not in membership_columns:
        raise HTTPException(status_code=403, detail="Geen geldig huishoudlidmaatschap")
    membership_id_sql = membership_id_expression(conn, membership_alias="hm")
    active_condition = membership_active_condition(conn, membership_alias="hm")

    if "user_email" in membership_columns:
        membership = conn.execute(
            text(
                f"""
                SELECT {membership_id_sql} AS membership_id
                FROM household_memberships hm
                WHERE hm.household_id = :household_id
                  AND lower(trim(hm.user_email)) = :email
                  AND {active_condition}
                LIMIT 1
                """
            ),
            {
                "household_id": str(session.active_household_id),
                "email": str(session.email).strip().lower(),
            },
        ).mappings().first()
    elif "user_id" in membership_columns:
        membership = conn.execute(
            text(
                f"""
                SELECT {membership_id_sql} AS membership_id
                FROM household_memberships hm
                WHERE hm.household_id = :household_id
                  AND hm.user_id = :user_id
                  AND {active_condition}
                LIMIT 1
                """
            ),
            {
                "household_id": str(session.active_household_id),
                "user_id": str(session.user_id),
            },
        ).mappings().first()
    else:
        membership = None

    if not membership or not str(membership.get("membership_id") or "").strip():
        raise HTTPException(status_code=403, detail="Geen geldig huishoudlidmaatschap")

    return {
        "user_id": str(session.user_id),
        "email": str(session.email).strip().lower(),
        "household_id": str(session.active_household_id),
        "membership_id": str(membership["membership_id"]),
    }


def _require_invitation_management(conn, context: dict[str, str]) -> None:
    try:
        require_household_permission(
            conn,
            household_id=context["household_id"],
            membership_id=context["membership_id"],
            permission_key="members.manage",
        )
    except AuthorizationDeniedError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "authorization_denied",
                "permission_key": exc.decision.permission_key,
                "reason": exc.decision.reason,
            },
        ) from exc


def create_household_invitation_router(
    engine: Engine,
    *,
    email_configuration: InvitationEmailConfiguration | None = None,
    email_transport: InvitationEmailTransport | None = None,
) -> APIRouter:
    router = APIRouter(tags=["household-invitations"])

    @router.post("/api/household/invitations", status_code=status.HTTP_201_CREATED)
    def create_invitation(payload: HouseholdInvitationCreateRequest, request: Request):
        try:
            with engine.begin() as conn:
                context = _actor_context(conn, request)
                _require_invitation_management(conn, context)
                assert_household_invitation_target_allowed(conn, payload.email)
                result = create_household_invitation(
                    conn,
                    household_id=context["household_id"],
                    invitee_email=payload.email,
                    created_by_user_id=context["user_id"],
                )
                delivery = deliver_created_household_invitation(
                    conn,
                    household_id=context["household_id"],
                    invitation_id=str(result.invitation["id"]),
                    raw_token=result.raw_token,
                    actor_user_id=context["user_id"],
                    configuration=email_configuration,
                    transport=email_transport,
                )
                invitation = get_household_invitation_with_delivery(
                    conn,
                    household_id=context["household_id"],
                    invitation_id=str(result.invitation["id"]),
                )
                # The raw bearer token exists only transiently for the outbound email.
                return {
                    "ok": True,
                    "invitation": invitation,
                    "delivery": delivery.public_payload(),
                }
        except InvitationTargetNotAllowedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvitationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/household/invitations")
    def list_invitations(request: Request):
        with engine.begin() as conn:
            context = _actor_context(conn, request)
            _require_invitation_management(conn, context)
            items = list_household_invitations_with_delivery(
                conn,
                household_id=context["household_id"],
            )
            return {
                "household_id": context["household_id"],
                "items": items,
                "total": len(items),
            }

    @router.post("/api/household/invitations/{invitation_id}/resend")
    def resend_invitation(invitation_id: str, request: Request):
        try:
            with engine.begin() as conn:
                context = _actor_context(conn, request)
                _require_invitation_management(conn, context)
                current = get_household_invitation_with_delivery(
                    conn,
                    household_id=context["household_id"],
                    invitation_id=invitation_id,
                )
                assert_household_invitation_target_allowed(
                    conn,
                    str(current["invitee_email"]),
                )
                invitation, delivery = resend_household_invitation(
                    conn,
                    household_id=context["household_id"],
                    invitation_id=invitation_id,
                    actor_user_id=context["user_id"],
                    configuration=email_configuration,
                    transport=email_transport,
                )
        except InvitationTargetNotAllowedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvitationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvitationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if delivery.status != DELIVERY_STATUS_SENT:
            failure_status = (
                503
                if delivery.status in {DELIVERY_STATUS_DISABLED, DELIVERY_STATUS_CONFIG_INVALID}
                else 502
            )
            raise HTTPException(
                status_code=failure_status,
                detail={
                    "code": "invitation_delivery_failed",
                    "delivery": delivery.public_payload(),
                },
            )
        return {
            "ok": True,
            "invitation": invitation,
            "delivery": delivery.public_payload(),
        }

    @router.post("/api/household/invitations/{invitation_id}/revoke")
    def revoke_invitation(invitation_id: str, request: Request):
        try:
            with engine.begin() as conn:
                context = _actor_context(conn, request)
                _require_invitation_management(conn, context)
                revoke_household_invitation(
                    conn,
                    household_id=context["household_id"],
                    invitation_id=invitation_id,
                    actor_user_id=context["user_id"],
                )
                invitation = get_household_invitation_with_delivery(
                    conn,
                    household_id=context["household_id"],
                    invitation_id=invitation_id,
                )
                return {"ok": True, "invitation": invitation}
        except InvitationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvitationConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
