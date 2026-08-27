from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine
from app.services.authorization_foundation_service import evaluate_household_permission
from app.services.household_capability_expansion_service import (
    expand_with_inhuis_halen,
    expand_with_wat_inhuis,
    expand_with_waar_inhuis,
)
from app.services.household_onboarding_service import (
    ONBOARDING_STATUS_COMPLETED,
    resolve_household_onboarding_state,
)
from app.services.household_product_configuration_service import (
    public_household_product_configuration_payload,
    resolve_household_product_configuration,
)
from app.services.household_product_use_case_service import (
    activate_household_product_use_case,
    resolve_active_household_product_use_cases,
)
from app.services.server_session_service import (
    membership_active_condition,
    membership_id_expression,
    membership_user_join_condition,
)
from app.services.session_request_context import resolve_current_server_session

router = APIRouter(tags=["onboarding-v2-circular-expansion"])


class ExpandInhuisHalenRequest(BaseModel):
    simple_inventory_enabled: bool = False
    almost_out_notifications_enabled: bool = False
    receipt_processing_enabled: bool = False
    recipes_enabled: bool = False


class ExpandWatInhuisRequest(BaseModel):
    inventory_tracking_level: str | None = None
    global_locations_enabled: bool = False
    almost_out_enabled: bool = False
    shopping_enabled: bool = False


class ExpansionSublocationRequest(BaseModel):
    space_name: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)


class ExpandWaarInhuisRequest(BaseModel):
    # Transitional compatibility only: older clients may still send these fields.
    # Waar Inhuis activation itself never creates or changes locations; that belongs
    # exclusively to Instellingen → Locaties.
    main_locations: list[str] = Field(default_factory=list, max_length=12)
    sublocations: list[ExpansionSublocationRequest] = Field(default_factory=list, max_length=30)
    unpacking_enabled: bool = False
    receipt_processing_enabled: bool = False
    almost_out_enabled: bool = False


def _require_manage_context():
    context = resolve_current_server_session()
    if context.context_type != "regular" or not context.active_household_id:
        raise HTTPException(status_code=403, detail="Een regulier huishouden is vereist")

    with engine.begin() as conn:
        membership_id_sql = membership_id_expression(conn, membership_alias="hm")
        user_join_sql = membership_user_join_condition(
            conn,
            membership_alias="hm",
            user_alias="u",
        )
        active_sql = membership_active_condition(conn, membership_alias="hm")
        membership_id = conn.execute(text(f"""
            SELECT {membership_id_sql} AS membership_id
            FROM household_memberships hm
            JOIN app_users u ON {user_join_sql}
            WHERE CAST(hm.household_id AS TEXT) = :household_id
              AND u.id = :user_id
              AND {active_sql}
            ORDER BY {membership_id_sql}
            LIMIT 1
        """), {
            "household_id": str(context.active_household_id),
            "user_id": str(context.user_id),
        }).scalar()
        if not membership_id:
            raise HTTPException(status_code=403, detail="Actief huishoudlidmaatschap ontbreekt")
        decision = evaluate_household_permission(
            conn,
            household_id=str(context.active_household_id),
            membership_id=str(membership_id),
            permission_key="household_settings.manage",
        )
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail="Ontbrekende huishoudpermissie: household_settings.manage",
        )
    return context


def _projection(conn, household_id: str) -> dict:
    state = resolve_household_onboarding_state(conn, household_id)
    try:
        configuration = resolve_household_product_configuration(conn, household_id)
    except LookupError:
        configuration_payload = None
    else:
        configuration_payload = public_household_product_configuration_payload(configuration)

    return {
        "household_id": state.household_id,
        "household_name": state.household_name,
        "onboarding_status": state.onboarding_status,
        "onboarding_version": state.onboarding_version,
        "primary_use_case": state.primary_use_case,
        "active_use_cases": resolve_active_household_product_use_cases(
            conn,
            household_id=state.household_id,
            primary_use_case=state.primary_use_case,
        ),
        "product_configuration": configuration_payload,
        "can_manage": True,
    }


def _require_completed(conn, household_id: str) -> None:
    state = resolve_household_onboarding_state(conn, household_id)
    if state.onboarding_status != ONBOARDING_STATUS_COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Rond eerst de initiële onboarding af voordat je Inhuis uitbreidt",
        )


def _already_active(conn, household_id: str, use_case: str) -> bool:
    state = resolve_household_onboarding_state(conn, household_id)
    return use_case in resolve_active_household_product_use_cases(
        conn,
        household_id=household_id,
        primary_use_case=state.primary_use_case,
    )


@router.get("/api/onboarding/capabilities")
def get_household_capabilities():
    context = _require_manage_context()
    household_id = str(context.active_household_id)
    with engine.begin() as conn:
        _require_completed(conn, household_id)
        return _projection(conn, household_id)


@router.post("/api/onboarding/expand/inhuis-halen")
def expand_inhuis_halen(payload: ExpandInhuisHalenRequest):
    context = _require_manage_context()
    household_id = str(context.active_household_id)
    try:
        with engine.begin() as conn:
            _require_completed(conn, household_id)
            if not _already_active(conn, household_id, "inhuis_halen"):
                expand_with_inhuis_halen(
                    conn,
                    household_id=household_id,
                    simple_inventory_enabled=payload.simple_inventory_enabled,
                    almost_out_notifications_enabled=payload.almost_out_notifications_enabled,
                    receipt_processing_enabled=payload.receipt_processing_enabled,
                    recipes_enabled=payload.recipes_enabled,
                )
                activate_household_product_use_case(
                    conn,
                    household_id=household_id,
                    use_case="inhuis_halen",
                )
            return _projection(conn, household_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/onboarding/expand/wat-inhuis")
def expand_wat_inhuis(payload: ExpandWatInhuisRequest):
    context = _require_manage_context()
    household_id = str(context.active_household_id)
    try:
        with engine.begin() as conn:
            _require_completed(conn, household_id)
            if not _already_active(conn, household_id, "wat_inhuis"):
                expand_with_wat_inhuis(
                    conn,
                    household_id=household_id,
                    inventory_tracking_level=payload.inventory_tracking_level,
                    global_locations_enabled=payload.global_locations_enabled,
                    almost_out_enabled=payload.almost_out_enabled,
                    shopping_enabled=payload.shopping_enabled,
                )
                activate_household_product_use_case(
                    conn,
                    household_id=household_id,
                    use_case="wat_inhuis",
                )
            return _projection(conn, household_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/onboarding/expand/waar-inhuis")
def expand_waar_inhuis(payload: ExpandWaarInhuisRequest):
    context = _require_manage_context()
    household_id = str(context.active_household_id)
    try:
        with engine.begin() as conn:
            _require_completed(conn, household_id)
            if not _already_active(conn, household_id, "waar_inhuis"):
                # Deliberately do not provision or mutate locations here. Existing
                # locationless inventory remains locationless and can be assigned later;
                # location management belongs exclusively to Instellingen → Locaties.
                expand_with_waar_inhuis(
                    conn,
                    household_id=household_id,
                    unpacking_enabled=payload.unpacking_enabled,
                    receipt_processing_enabled=payload.receipt_processing_enabled,
                    almost_out_enabled=payload.almost_out_enabled,
                )
                activate_household_product_use_case(
                    conn,
                    household_id=household_id,
                    use_case="waar_inhuis",
                )
            return _projection(conn, household_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
