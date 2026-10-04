from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import engine
from app.services.authorization_foundation_service import evaluate_household_permission
from app.services.household_profile_service import (
    AGE_BANDS,
    RESIDENT_TYPES,
    create_resident,
    delete_resident,
    public_household_profile,
    save_household_profile,
    update_resident,
)
from app.services.server_session_service import (
    membership_active_condition,
    membership_id_expression,
    membership_user_join_condition,
)
from app.services.session_request_context import resolve_current_server_session


router = APIRouter(tags=["household-profile"])


class HouseholdProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    household_name: str
    street: str | None = None
    house_number: str | None = None
    house_number_addition: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country_code: str | None = "NL"
    preferred_stores: list[str] = Field(default_factory=list)
    shopping_interval_days: int | None = None
    default_reserve_days: int | None = None


class ResidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str
    last_name: str | None = None
    resident_type: Literal["adult", "child", "other"]
    birth_date: date | None = None
    age_band: str | None = None
    linked_user_id: str | None = None

    @field_validator("resident_type")
    @classmethod
    def validate_resident_type(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in RESIDENT_TYPES:
            raise ValueError("Kies volwassene, kind of anders")
        return normalized

    @field_validator("age_band")
    @classmethod
    def validate_age_band(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip() or None
        if normalized is not None and normalized not in AGE_BANDS:
            raise ValueError("Ongeldige leeftijdscategorie")
        return normalized


def _context_and_membership(conn):
    context = resolve_current_server_session()
    if context.context_type != "regular" or not context.active_household_id:
        raise HTTPException(
            status_code=403,
            detail="Huishoudprofiel is alleen beschikbaar in een regulier huishouden.",
        )
    membership_id_sql = membership_id_expression(conn)
    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    row = conn.execute(text(f"""
        SELECT {membership_id_sql} AS membership_id
        FROM app_users u
        JOIN household_memberships hm ON {join_condition}
        WHERE u.id = :user_id
          AND CAST(hm.household_id AS TEXT) = :household_id
          AND {active_condition}
        LIMIT 2
    """), {
        "user_id": str(context.user_id),
        "household_id": str(context.active_household_id),
    }).mappings().all()
    if len(row) != 1 or not str(row[0].get("membership_id") or "").strip():
        raise HTTPException(status_code=403, detail="Geen geldig huishoudlidmaatschap beschikbaar.")
    return context, str(row[0]["membership_id"])


def _require(conn, permission_key: str):
    context, membership_id = _context_and_membership(conn)
    decision = evaluate_household_permission(
        conn,
        household_id=str(context.active_household_id),
        membership_id=membership_id,
        permission_key=permission_key,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Ontbrekende huishoudpermissie: {permission_key}",
        )
    return context


def _payload(conn, context):
    manage = evaluate_household_permission(
        conn,
        household_id=str(context.active_household_id),
        membership_id=_context_and_membership(conn)[1],
        permission_key="household_settings.manage",
    )
    return public_household_profile(
        conn,
        str(context.active_household_id),
        can_manage=manage.allowed,
    )


@router.get("/api/household/profile")
def get_household_profile() -> dict:
    with engine.begin() as conn:
        context = _require(conn, "household_settings.view")
        return _payload(conn, context)


@router.put("/api/household/profile")
def update_household_profile(payload: HouseholdProfileUpdateRequest) -> dict:
    with engine.begin() as conn:
        context = _require(conn, "household_settings.manage")
        try:
            save_household_profile(
                conn,
                str(context.active_household_id),
                **payload.model_dump(),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _payload(conn, context)


@router.post("/api/household/profile/residents")
def add_household_resident(payload: ResidentRequest) -> dict:
    with engine.begin() as conn:
        context = _require(conn, "household_settings.manage")
        try:
            create_resident(
                conn,
                str(context.active_household_id),
                **payload.model_dump(),
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="Deze Inhuis-gebruiker is al aan een bewoner gekoppeld.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _payload(conn, context)


@router.put("/api/household/profile/residents/{resident_id}")
def change_household_resident(resident_id: str, payload: ResidentRequest) -> dict:
    with engine.begin() as conn:
        context = _require(conn, "household_settings.manage")
        try:
            update_resident(
                conn,
                str(context.active_household_id),
                str(resident_id),
                **payload.model_dump(),
            )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="Deze Inhuis-gebruiker is al aan een bewoner gekoppeld.",
            ) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _payload(conn, context)


@router.delete("/api/household/profile/residents/{resident_id}")
def remove_household_resident(resident_id: str) -> dict:
    with engine.begin() as conn:
        context = _require(conn, "household_settings.manage")
        try:
            delete_resident(
                conn,
                str(context.active_household_id),
                str(resident_id),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _payload(conn, context)
