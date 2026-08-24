from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.platform_log_service import (
    PLATFORM_LOG_DEFAULT_LIMIT,
    PLATFORM_LOG_LEVELS,
    PLATFORM_LOG_MAX_ENTRIES,
    PLATFORM_LOG_MAX_LIMIT,
    list_platform_logs,
    normalize_platform_log_level,
)
from app.services.session_request_context import require_platform_permission_from_session


PLATFORM_LOGS_VIEW_PERMISSION = "platform.logs.view"

router = APIRouter()


@router.get("/api/platform/logs")
def get_platform_logs(
    limit: int = Query(default=PLATFORM_LOG_DEFAULT_LIMIT, ge=1, le=PLATFORM_LOG_MAX_LIMIT),
    level: str | None = Query(default=None),
) -> dict:
    context = require_platform_permission_from_session(PLATFORM_LOGS_VIEW_PERMISSION)
    try:
        normalized_level = normalize_platform_log_level(level)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = list_platform_logs(limit=limit, level=normalized_level)
    return {
        "items": items,
        "count": len(items),
        "limit": int(limit),
        "level": normalized_level,
        "levels": list(PLATFORM_LOG_LEVELS),
        "retention": "runtime_memory",
        "max_entries": PLATFORM_LOG_MAX_ENTRIES,
        "source": "rezzerv.*",
        "audit_separate": True,
        "household_context_used": False,
        "context_type": context.context_type,
    }
