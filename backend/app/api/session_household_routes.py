from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.api.server_session_routes import SessionApiConfiguration, session_api_configuration_from_environment
from app.services.authorization_membership_service import canonical_role_to_runtime_role, resolve_effective_household_role
from app.services.frontteam_household_provisioning import LEGACY_FRONTTEAM_HOUSEHOLD_ID
from app.services.server_session_service import (
    DEFAULT_SESSION_TTL,
    SESSION_COOKIE_NAME,
    membership_active_condition,
    membership_id_expression,
    membership_user_join_condition,
    resolve_server_session,
    rotate_active_household,
)
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_HUISHOUDEN_ID


class HouseholdSwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    household_id: str

    @field_validator("household_id")
    @classmethod
    def validate_household_id(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("Huishouden ontbreekt")
        if len(normalized) > 128:
            raise ValueError("Ongeldig huishouden")
        return normalized


def _set_session_cookie(response: Response, raw_session_id: str, configuration: SessionApiConfiguration) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session_id,
        max_age=int(DEFAULT_SESSION_TTL.total_seconds()),
        httponly=True,
        secure=configuration.cookie_secure,
        samesite=configuration.cookie_samesite,
        path=configuration.cookie_path,
    )


def _household_registry_columns(conn) -> tuple[str, str]:
    columns = {
        str(column.get("name") or "").strip()
        for column in inspect(conn).get_columns("household_registry")
    }
    id_column = "id" if "id" in columns else ("household_id" if "household_id" in columns else "")
    name_column = "naam" if "naam" in columns else ("name" if "name" in columns else "")
    if not id_column or not name_column:
        raise RuntimeError("household_registry mist de vereiste kolommen")
    return id_column, name_column


def _available_households(conn, context) -> list[dict[str, object]]:
    if context.context_type != "regular" or not context.active_household_id:
        return []
    if context.is_frontteam:
        id_column, name_column = _household_registry_columns(conn)
        row = conn.execute(
            text(
                f"SELECT {name_column} AS household_name FROM household_registry "
                f"WHERE CAST({id_column} AS TEXT) = :household_id LIMIT 1"
            ),
            {"household_id": str(context.active_household_id)},
        ).mappings().first()
        return [{
            "household_id": str(context.active_household_id),
            "household_name": str((row or {}).get("household_name") or "").strip() or "Huishouden",
            "role": str(context.role or ""),
            "active": True,
        }]

    id_column, name_column = _household_registry_columns(conn)
    membership_id_sql = membership_id_expression(conn, membership_alias="hm")
    active_condition = membership_active_condition(conn, membership_alias="hm")
    join_condition = membership_user_join_condition(conn, membership_alias="hm", user_alias="u")
    rows = conn.execute(
        text(
            f"""
            SELECT
                {membership_id_sql} AS membership_id,
                hm.household_id,
                hm.role,
                h.{name_column} AS household_name
            FROM household_memberships hm
            JOIN app_users u ON {join_condition}
            JOIN household_registry h ON CAST(h.{id_column} AS TEXT) = CAST(hm.household_id AS TEXT)
            WHERE u.id = :user_id
              AND {active_condition}
              AND CAST(hm.household_id AS TEXT) <> :system_household_id
              AND CAST(hm.household_id AS TEXT) <> :legacy_frontteam_household_id
            ORDER BY lower(trim(COALESCE(h.{name_column}, ''))) ASC, CAST(hm.household_id AS TEXT) ASC
            """
        ),
        {
            "user_id": str(context.user_id),
            "system_household_id": SUPERGEBRUIKER_HUISHOUDEN_ID,
            "legacy_frontteam_household_id": LEGACY_FRONTTEAM_HOUSEHOLD_ID,
        },
    ).mappings().all()

    result: list[dict[str, object]] = []
    for row in rows:
        household_id = str(row.get("household_id") or "").strip()
        membership_id = str(row.get("membership_id") or "").strip()
        if not household_id or not membership_id:
            continue
        role_key = resolve_effective_household_role(
            conn,
            household_id=household_id,
            membership_id=membership_id,
            legacy_role=row.get("role"),
        )
        runtime_role = canonical_role_to_runtime_role(role_key or "")
        if not runtime_role:
            continue
        result.append({
            "household_id": household_id,
            "household_name": str(row.get("household_name") or "").strip() or "Huishouden",
            "role": runtime_role,
            "active": household_id == str(context.active_household_id),
        })
    return result


def create_session_household_router(
    engine: Engine,
    configuration: SessionApiConfiguration | None = None,
) -> APIRouter:
    configuration = configuration or session_api_configuration_from_environment()
    router = APIRouter(tags=["session-households"])

    @router.get("/api/session/households")
    def list_session_households(request: Request):
        raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
        with engine.begin() as conn:
            context = resolve_server_session(conn, raw_session_id)
            if context.context_type != "regular":
                return {"items": [], "total": 0, "can_switch_households": False}
            items = _available_households(conn, context)
            return {
                "items": items,
                "total": len(items),
                "can_switch_households": len(items) > 1,
            }

    @router.post("/api/session/household")
    def switch_session_household(payload: HouseholdSwitchRequest, request: Request, response: Response):
        raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not raw_session_id:
            raise HTTPException(status_code=401, detail="Geen geldige sessie")
        with engine.begin() as conn:
            current = resolve_server_session(conn, raw_session_id)
            if current.context_type != "regular":
                raise HTTPException(status_code=403, detail="Huishoudwissel is alleen beschikbaar in reguliere context")
            raw_new_session_id, new_context = rotate_active_household(
                conn,
                raw_session_id,
                payload.household_id,
            )
            items = _available_households(conn, new_context)
            active = next((item for item in items if item["active"]), None)
        _set_session_cookie(response, raw_new_session_id, configuration)
        return {
            "ok": True,
            "active_household_id": str(new_context.active_household_id or ""),
            "active_household_name": str((active or {}).get("household_name") or ""),
            "role": str(new_context.role or ""),
        }

    return router
