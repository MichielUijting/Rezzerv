from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.db import engine
from app.services.household_dashboard_service import build_household_dashboard, build_household_dashboard_drilldown
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


@router.get("/drilldown")
def get_household_dashboard_drilldown(
    request: Request,
    metric: str,
    granularity: str,
    bucket_index: int,
    series: str = "current",
    comparison: str = "previous",
    group_key: str | None = None,
):
    raw_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    with engine.begin() as conn:
        context = resolve_server_session(conn, raw_session_id)
        if context.context_type != "regular":
            raise HTTPException(status_code=403, detail="Dashboard is alleen beschikbaar binnen een huishouden")
        try:
            return build_household_dashboard_drilldown(
                conn,
                household_id=context.active_household_id,
                user_id=context.user_id,
                metric=metric,
                granularity=granularity,
                bucket_index=bucket_index,
                series=series,
                comparison=comparison,
                group_key=group_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
