from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.authorization_foundation_service import evaluate_household_permission
from app.services.household_onboarding_service import (
    PRIMARY_USE_CASES,
    OnboardingAlreadyCompletedError,
    public_household_onboarding_payload,
    resolve_household_onboarding_state,
    select_primary_use_case,
)
from app.services.server_session_service import (
    SESSION_COOKIE_NAME,
    ServerSessionContext,
    membership_active_condition,
    membership_id_expression,
    membership_user_join_condition,
    resolve_server_session,
)

HOUSEHOLD_ONBOARDING_MANAGE_PERMISSION = "household_settings.manage"


class PrimaryUseCaseSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_use_case: str

    @field_validator("primary_use_case")
    @classmethod
    def validate_primary_use_case(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in PRIMARY_USE_CASES:
            raise ValueError("Kies Inhuis halen, Wat Inhuis of Waar Inhuis")
        return normalized


def _regular_household_context(conn, request: Request) -> ServerSessionContext:
    raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    context = resolve_server_session(conn, raw_session_id)
    if context.context_type != "regular" or not context.active_household_id:
        raise HTTPException(
            status_code=403,
            detail="Onboarding is alleen beschikbaar in een regulier huishouden.",
        )
    return context


def _active_membership_id(conn, context: ServerSessionContext) -> str:
    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    membership_id_sql = membership_id_expression(conn)
    rows = conn.execute(text(f"""
        SELECT {membership_id_sql} AS membership_id
        FROM app_users u
        JOIN household_memberships hm ON {join_condition}
        WHERE u.id = :user_id
          AND hm.household_id = :household_id
          AND {active_condition}
        LIMIT 2
    """), {
        "user_id": context.user_id,
        "household_id": str(context.active_household_id),
    }).mappings().all()
    if len(rows) != 1:
        raise HTTPException(
            status_code=403,
            detail="Geen eenduidig actief huishoudlidmaatschap beschikbaar.",
        )
    membership_id = str(rows[0].get("membership_id") or "").strip()
    if not membership_id:
        raise HTTPException(
            status_code=403,
            detail="Actief huishoudlidmaatschap ontbreekt.",
        )
    return membership_id


def _can_manage_onboarding(conn, context: ServerSessionContext) -> bool:
    membership_id = _active_membership_id(conn, context)
    decision = evaluate_household_permission(
        conn,
        household_id=str(context.active_household_id),
        membership_id=membership_id,
        permission_key=HOUSEHOLD_ONBOARDING_MANAGE_PERMISSION,
    )
    return bool(decision.allowed)


def create_household_onboarding_router(engine: Engine) -> APIRouter:
    router = APIRouter()

    @router.get("/api/onboarding")
    def get_household_onboarding(request: Request):
        with engine.begin() as conn:
            context = _regular_household_context(conn, request)
            state = resolve_household_onboarding_state(
                conn,
                str(context.active_household_id),
            )
            can_manage = _can_manage_onboarding(conn, context)
            return public_household_onboarding_payload(
                state,
                can_manage=can_manage,
            )

    @router.post("/api/onboarding/primary-use-case")
    def choose_primary_use_case(
        payload: PrimaryUseCaseSelectionRequest,
        request: Request,
    ):
        with engine.begin() as conn:
            context = _regular_household_context(conn, request)
            if not _can_manage_onboarding(conn, context):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Ontbrekende huishoudpermissie: "
                        f"{HOUSEHOLD_ONBOARDING_MANAGE_PERMISSION}"
                    ),
                )
            try:
                state = select_primary_use_case(
                    conn,
                    household_id=str(context.active_household_id),
                    primary_use_case=payload.primary_use_case,
                )
            except OnboardingAlreadyCompletedError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            return public_household_onboarding_payload(
                state,
                can_manage=True,
            )

    return router
