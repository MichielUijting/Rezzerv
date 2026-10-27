"""TD-02: technical platform maintenance; no household/role-name shortcuts."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.db import engine
from app.services.maintenance_runtime import state, transition
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


class MaintenanceSessionClosure(BaseModel):
    expected_generation: int = Field(ge=0)
    confirmed: bool = False


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
