"""Bridge legacy route guards to the server-side session context.

Existing domain routes still accept an ``Authorization`` parameter in their
function signatures. During tranche 3 that parameter is deliberately ignored:
the only accepted authority is the opaque HttpOnly session cookie captured for
the current request.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from fastapi import HTTPException, Request

from app.db import engine
from app.services.server_session_service import (
    SESSION_COOKIE_NAME,
    ServerSessionContext,
    resolve_server_session,
)

_raw_session_cookie: ContextVar[str | None] = ContextVar(
    "rezzerv_raw_session_cookie", default=None
)


def bind_request_session(request: Request) -> Token:
    """Bind only the opaque cookie value for the lifetime of one request."""

    return _raw_session_cookie.set(request.cookies.get(SESSION_COOKIE_NAME))


def reset_request_session(token: Token) -> None:
    _raw_session_cookie.reset(token)


def resolve_current_server_session() -> ServerSessionContext:
    raw_session_id = _raw_session_cookie.get()
    with engine.begin() as conn:
        return resolve_server_session(conn, raw_session_id)


def legacy_user_payload_from_session(
    _authorization: str | None = None,
) -> dict[str, Any]:
    """Compatibility payload for existing route code.

    ``_authorization`` is intentionally ignored. Supplying a valid-looking
    Bearer token without a valid session cookie must still result in HTTP 401.
    """

    context = resolve_current_server_session()
    return {
        "id": context.user_id,
        "user_id": context.user_id,
        "email": context.email,
        "role": context.role,
        "household_id": context.active_household_id,
        "active_household_id": context.active_household_id,
    }


def household_context_from_session(
    _authorization: str | None = None,
    requested_household_id: str | None = None,
) -> dict[str, Any]:
    """Return the active household and reject browser-driven switching."""

    context = resolve_current_server_session()
    requested = str(requested_household_id or "").strip()
    if requested and requested != context.active_household_id:
        raise HTTPException(
            status_code=403,
            detail="Huishouden kan uitsluitend via de serversessie worden gewijzigd",
        )
    return {
        "user_id": context.user_id,
        "email": context.email,
        "role": context.role,
        "household_id": context.active_household_id,
        "active_household_id": context.active_household_id,
        "membership_count": 1,
        "can_switch_households": False,
    }


def authorized_household_id_from_session(
    _authorization: str | None = None,
    requested_household_id: str | None = None,
    *,
    fallback: str = "demo-household",
    require_authorization: bool = False,
) -> str:
    """Cookie-only replacement for the legacy household resolver.

    ``fallback`` and ``require_authorization`` are retained only for signature
    compatibility. A missing serversessie always fails closed with HTTP 401;
    no demo/default household is ever selected in the migrated runtime.
    """

    del fallback, require_authorization
    context = household_context_from_session(None, requested_household_id)
    return str(context["active_household_id"])


def request_household_id_from_session(
    _authorization: str | None = None,
    fallback: str = "demo-household",
) -> str:
    """Cookie-only replacement for legacy request-household fallback logic."""

    del fallback
    context = household_context_from_session(None, None)
    return str(context["active_household_id"])


def require_platform_admin_from_session(
    _authorization: str | None = None,
) -> dict[str, Any]:
    """Resolve the current session and fail closed unless its live role is admin."""

    user = legacy_user_payload_from_session(None)
    if str(user.get("role") or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Alleen de beheerder mag deze actie uitvoeren")
    return user
