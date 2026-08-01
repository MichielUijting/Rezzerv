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
from app.services.system_superuser_session_provisioning import SUPERGEBRUIKER_EMAIL

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


def legacy_user_payload_from_session(_authorization: str | None = None) -> dict[str, Any]:
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
        "display_role": context.role,
        "household_id": context.active_household_id,
        "active_household_id": context.active_household_id,
        "membership_count": 1,
        "can_switch_households": False,
    }


def require_household_admin_from_session(
    _authorization: str | None = None,
    requested_household_id: str | None = None,
) -> dict[str, Any]:
    """Require household ownership from the authoritative server session.

    ``owner`` is the canonical household-management role. ``admin`` remains
    accepted only for compatibility with still-active legacy memberships.
    """

    context = household_context_from_session(None, requested_household_id)
    role = str(context.get("role") or "").strip().lower()
    if role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Alleen de beheerder van het huishouden mag deze actie uitvoeren",
        )
    return context


def authorized_household_id_from_session(
    _authorization: str | None = None,
    requested_household_id: str | None = None,
    *,
    fallback: str | None = None,
    require_authorization: bool = False,
) -> str:
    del fallback, require_authorization
    context = household_context_from_session(None, requested_household_id)
    return str(context["active_household_id"])


def request_household_id_from_session(
    _authorization: str | None = None,
    fallback: str | None = None,
) -> str:
    del fallback
    context = household_context_from_session(None, None)
    return str(context["active_household_id"])


def is_platform_superuser(user: dict[str, Any]) -> bool:
    return str(user.get("email") or "").strip().lower() == SUPERGEBRUIKER_EMAIL


def require_platform_admin_from_session(
    _authorization: str | None = None,
) -> dict[str, Any]:
    user = legacy_user_payload_from_session(None)
    if not is_platform_superuser(user):
        raise HTTPException(
            status_code=403,
            detail="Alleen de platform-supergebruiker mag deze actie uitvoeren",
        )
    return user
