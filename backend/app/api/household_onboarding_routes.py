from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.authorization_foundation_service import evaluate_household_permission
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_IN_PROGRESS,
    PRIMARY_USE_CASES,
    OnboardingAlreadyCompletedError,
    complete_household_onboarding,
    public_household_onboarding_payload,
    resolve_household_onboarding_state,
    select_primary_use_case,
)
from app.services.household_product_configuration_service import (
    public_household_product_configuration_payload,
    save_inhuis_halen_configuration,
    save_wat_inhuis_configuration,
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


class InhuisHalenOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simple_inventory_enabled: bool
    almost_out_notifications_enabled: bool
    receipt_processing_enabled: bool
    recipes_enabled: bool

    @model_validator(mode="after")
    def validate_dependencies(self):
        if not self.simple_inventory_enabled and self.almost_out_notifications_enabled:
            raise ValueError(
                "Bijna-op meldingen vereisen de eenvoudige voorraad van Inhuis halen"
            )
        return self


class WatInhuisOnboardingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inventory_tracking_level: str
    global_locations_enabled: bool
    almost_out_enabled: bool
    shopping_enabled: bool

    @field_validator("inventory_tracking_level")
    @classmethod
    def validate_inventory_tracking_level(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"presence", "quantity"}:
            raise ValueError("Kies aanwezigheid of aantallen")
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


def _require_manage_onboarding(conn, context: ServerSessionContext) -> None:
    if not _can_manage_onboarding(conn, context):
        raise HTTPException(
            status_code=403,
            detail=(
                "Ontbrekende huishoudpermissie: "
                f"{HOUSEHOLD_ONBOARDING_MANAGE_PERMISSION}"
            ),
        )


def _require_profile_follow_up(conn, *, household_id: str, primary_use_case: str) -> None:
    state = resolve_household_onboarding_state(conn, household_id)
    if (
        state.onboarding_status != ONBOARDING_STATUS_IN_PROGRESS
        or state.onboarding_step != "profile_follow_up"
        or state.primary_use_case != primary_use_case
    ):
        raise HTTPException(
            status_code=409,
            detail=f"{primary_use_case} is niet de actieve onboardingstap.",
        )


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
            _require_manage_onboarding(conn, context)
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

    @router.post("/api/onboarding/inhuis-halen")
    def complete_inhuis_halen(
        payload: InhuisHalenOnboardingRequest,
        request: Request,
    ):
        with engine.begin() as conn:
            context = _regular_household_context(conn, request)
            _require_manage_onboarding(conn, context)
            household_id = str(context.active_household_id)
            _require_profile_follow_up(
                conn,
                household_id=household_id,
                primary_use_case="inhuis_halen",
            )

            try:
                configuration = save_inhuis_halen_configuration(
                    conn,
                    household_id=household_id,
                    simple_inventory_enabled=payload.simple_inventory_enabled,
                    almost_out_notifications_enabled=payload.almost_out_notifications_enabled,
                    receipt_processing_enabled=payload.receipt_processing_enabled,
                    recipes_enabled=payload.recipes_enabled,
                )
                completed_state = complete_household_onboarding(
                    conn,
                    household_id=household_id,
                    expected_primary_use_case="inhuis_halen",
                )
            except OnboardingAlreadyCompletedError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            return {
                **public_household_onboarding_payload(
                    completed_state,
                    can_manage=True,
                ),
                "product_configuration": public_household_product_configuration_payload(
                    configuration
                ),
            }

    @router.post("/api/onboarding/wat-inhuis")
    def complete_wat_inhuis(
        payload: WatInhuisOnboardingRequest,
        request: Request,
    ):
        with engine.begin() as conn:
            context = _regular_household_context(conn, request)
            _require_manage_onboarding(conn, context)
            household_id = str(context.active_household_id)
            _require_profile_follow_up(
                conn,
                household_id=household_id,
                primary_use_case="wat_inhuis",
            )

            try:
                configuration = save_wat_inhuis_configuration(
                    conn,
                    household_id=household_id,
                    inventory_tracking_level=payload.inventory_tracking_level,
                    global_locations_enabled=payload.global_locations_enabled,
                    almost_out_enabled=payload.almost_out_enabled,
                    shopping_enabled=payload.shopping_enabled,
                )
                completed_state = complete_household_onboarding(
                    conn,
                    household_id=household_id,
                    expected_primary_use_case="wat_inhuis",
                )
            except OnboardingAlreadyCompletedError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            return {
                **public_household_onboarding_payload(
                    completed_state,
                    can_manage=True,
                ),
                "product_configuration": public_household_product_configuration_payload(
                    configuration
                ),
            }

    return router
