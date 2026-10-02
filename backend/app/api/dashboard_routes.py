from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.db import engine
from app.services.household_dashboard_service import build_household_dashboard
from app.services.server_session_service import SESSION_COOKIE_NAME, resolve_server_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_household_dashboard(request: Request):
    raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    with engine.begin() as conn:
        context = resolve_server_session(conn, raw_session_id)
        if context.context_type != "regular":
            raise HTTPException(status_code=403, detail="Dashboard is alleen beschikbaar binnen een huishouden")
        return build_household_dashboard(
            conn,
            household_id=context.active_household_id,
            user_id=context.user_id,
        )
