"""TD-02: technical platform maintenance; no household/role-name shortcuts."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine
from app.services.maintenance_runtime import state, transition
from app.services.platform_feature_flag_service import (
    FEATURE_FLAG_RETAILER_AUTO_IMPORT, get_platform_feature_flag,
    set_platform_feature_flag,
)
from app.services.maintenance_state_contract import MaintenanceTransitionError
from app.services.maintenance_runtime_preflight import MaintenancePreflightError
from app.services.maintenance_session_drain import revoke_remaining_sessions
from app.services.session_request_context import require_platform_permission_from_session, resolve_current_server_session

router = APIRouter()
PERMISSION = "platform.recovery.manage"


class MaintenanceAction(BaseModel):
    action: str
    expected_generation: int = Field(ge=0)
    announcement: str = Field(default="", max_length=2000)


class ImportPauseAction(BaseModel):
    paused: bool


class MaintenanceSessionClosure(BaseModel):
    expected_generation: int = Field(ge=0)
    confirmed: bool = False


@router.get("/api/platform/maintenance/imports")
def platform_import_pause_status():
    require_platform_permission_from_session(PERMISSION)
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "Importpauze vereist PostgreSQL")
    try:
        with engine.connect() as conn:
            flag = get_platform_feature_flag(conn, FEATURE_FLAG_RETAILER_AUTO_IMPORT)
            current = state(conn)
        return {
            "paused": not flag["enabled"],
            "maintenance_paused": current["state"] not in ("normal", "announced"),
            "open_import_registrations": current["retailer_import_registrations"]["open"],
            "pending_receipts": current["retailer_import_queue"]["pending"],
            "processing_receipts": current["retailer_import_queue"]["processing"],
            "review_required": current["retailer_import_queue"]["review_required"],
            "note": "Een open registratie is niet noodzakelijk een lopende import.",
        }
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Importstatus kan niet betrouwbaar worden gelezen") from exc


@router.post("/api/platform/maintenance/imports")
def platform_import_pause_action(payload: ImportPauseAction):
    actor = require_platform_permission_from_session(PERMISSION)
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "Importpauze vereist PostgreSQL")
    try:
        with engine.begin() as conn:
            # A manual pause persists across restarts. Maintenance release is
            # a separate, proof-gated operation and must never clear this flag.
            flag = set_platform_feature_flag(
                conn, FEATURE_FLAG_RETAILER_AUTO_IMPORT,
                enabled=not payload.paused, updated_by=actor.user_id,
            )
        return {
            "paused": not flag["enabled"],
            "message": ("Nieuwe automatische winkelimports zijn gepauzeerd. "
                        "Lopende verwerkingen worden niet afgebroken."
                        if payload.paused else
                        "Automatische winkelimports zijn vrijgegeven; "
                        "serveronderhoud kan ze nog afzonderlijk blokkeren."),
        }
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Importpauze kon niet betrouwbaar worden opgeslagen") from exc


@router.get("/api/maintenance/status")
def maintenance_status():
    resolve_current_server_session()
    with engine.connect() as conn:
        result = state(conn)
    return {key:result[key] for key in ("state","announcement")}


@router.get("/api/platform/maintenance")
def platform_maintenance_status():
    require_platform_permission_from_session(PERMISSION)
    with engine.connect() as conn:
        return state(conn)


@router.post("/api/platform/maintenance")
def platform_maintenance_action(payload: MaintenanceAction):
    actor = require_platform_permission_from_session(PERMISSION)
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "Serveronderhoud vereist PostgreSQL")
    try:
        with engine.begin() as conn:
            return transition(conn, action=payload.action, expected_generation=payload.expected_generation, actor_user_id=actor.user_id, announcement=payload.announcement)
    except (MaintenanceTransitionError, MaintenancePreflightError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "De onderhoudscontrole is niet betrouwbaar uitvoerbaar. Inhuis blijft geblokkeerd als onderhoud actief is.") from exc


@router.post("/api/platform/maintenance/sessions/close")
def close_sessions_for_maintenance(payload: MaintenanceSessionClosure):
    actor = require_platform_permission_from_session(PERMISSION)
    session_admin = require_platform_permission_from_session("platform.sessions.revoke")
    if actor.user_id != session_admin.user_id or actor.session_id != session_admin.session_id:
        raise HTTPException(403, "Beheersessie kon niet worden bevestigd")
    if not payload.confirmed:
        raise HTTPException(400, "Bevestig eerst het gecontroleerd afmelden")
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "Serveronderhoud vereist PostgreSQL")
    try:
        with engine.begin() as conn:
            return revoke_remaining_sessions(
                conn, expected_generation=payload.expected_generation,
                current_session_id=actor.session_id,
                actor_user_id=actor.user_id,
            )
    except MaintenanceTransitionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Sessies konden niet veilig worden beëindigd") from exc
