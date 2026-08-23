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
from sqlalchemy import text

from app.db import engine
from app.services.actor_attribution_service import bind_current_actor, clear_current_actor
from app.services.authorization_foundation_service import evaluate_platform_permission
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
    clear_current_actor()
    return _raw_session_cookie.set(request.cookies.get(SESSION_COOKIE_NAME))


def reset_request_session(token: Token) -> None:
    clear_current_actor()
    _raw_session_cookie.reset(token)


def resolve_current_server_session() -> ServerSessionContext:
    raw_session_id = _raw_session_cookie.get()
    with engine.begin() as conn:
        context = resolve_server_session(conn, raw_session_id)
    bind_current_actor(context.user_id, context.active_household_id)
    return context


def require_platform_permission_from_session(
    permission_key: str,
    _authorization: str | None = None,
) -> ServerSessionContext:
    """Require one canonical platform permission for the current server session.

    The opaque server session is the sole identity source. Platform role names,
    legacy bearer values and reserved account e-mail addresses do not take part
    in the decision; the permission registry is evaluated live for the
    canonical ``app_users.id`` on every request.
    """
    context = resolve_current_server_session()
    with engine.begin() as conn:
        decision = evaluate_platform_permission(
            conn,
            user_id=context.user_id,
            permission_key=permission_key,
        )
    if not decision.allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Ontbrekende platformpermissie: {permission_key}",
        )
    return context


def require_platform_permissions_from_session(
    permission_keys: tuple[str, ...],
    _authorization: str | None = None,
) -> ServerSessionContext:
    """Require every listed canonical platform permission for one request.

    Each permission is evaluated through the same live server-session authority.
    The function deliberately does not collapse permissions into a role-name
    shortcut: callers must satisfy every permission in the supplied order.
    """

    normalized_permissions = tuple(
        str(permission_key or "").strip()
        for permission_key in permission_keys
        if str(permission_key or "").strip()
    )
    if not normalized_permissions:
        raise ValueError("platformpermissies ontbreken")

    context: ServerSessionContext | None = None
    for permission_key in normalized_permissions:
        context = require_platform_permission_from_session(
            permission_key,
            _authorization,
        )
    assert context is not None
    return context


def bind_current_actor_from_request_session_if_available() -> ServerSessionContext | None:
    """Eagerly bind the canonical actor for every authenticated request.

    Actor provenance must not depend on whether a legacy route happens to call a
    particular authorization helper before performing a domain write. A valid
    server session therefore binds its canonical ``app_users.id`` at middleware
    entry. Public/unauthenticated requests keep an empty actor context.
    """
    raw_session_id = _raw_session_cookie.get()
    if not raw_session_id:
        clear_current_actor()
        return None
    try:
        with engine.begin() as conn:
            context = resolve_server_session(conn, raw_session_id)
    except HTTPException:
        clear_current_actor()
        return None
    bind_current_actor(context.user_id, context.active_household_id)
    return context


def legacy_display_role_from_canonical_role(role: str | None) -> str:
    """Translate canonical server-session roles for still-active legacy guards.

    The server-side session uses canonical English role keys, while a small
    number of legacy routes still consume the historical display roles
    ``admin``, ``lid`` and ``viewer``. Keeping this translation in one bridge
    prevents individual routes from making conflicting role decisions.
    """

    normalized_role = str(role or "").strip().lower()
    if normalized_role in {"owner", "admin", "household.owner", "household.admin"}:
        return "admin"
    if normalized_role in {
        "member",
        "advanced_member",
        "lid",
        "household.member",
        "household.advanced_member",
    }:
        return "lid"
    if normalized_role in {"viewer", "household.viewer"}:
        return "viewer"
    return normalized_role


def _legacy_user_payload_from_context(context: ServerSessionContext) -> dict[str, Any]:
    return {
        "id": context.user_id,
        "user_id": context.user_id,
        "email": context.email,
        "role": context.role,
        "household_id": context.active_household_id,
        "active_household_id": context.active_household_id,
    }


def legacy_user_payload_from_session(_authorization: str | None = None) -> dict[str, Any]:
    return _legacy_user_payload_from_context(resolve_current_server_session())


def household_context_from_session(
    _authorization: str | None = None,
    requested_household_id: str | None = None,
) -> dict[str, Any]:
    context = resolve_current_server_session()
    if context.context_type == "none" or context.active_household_id is None:
        raise HTTPException(
            status_code=403,
            detail="Geen actieve huishoudcontext beschikbaar",
        )
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
        "display_role": legacy_display_role_from_canonical_role(context.role),
        "household_id": context.active_household_id,
        "active_household_id": context.active_household_id,
        "membership_count": 1,
        "can_switch_households": False,
    }


def legacy_household_context_from_session(
    _user: dict[str, Any] | None = None,
    requested_household_id: str | None = None,
) -> dict[str, Any]:
    """Keep legacy household callers bound to the authoritative server session."""

    context = household_context_from_session(
        None,
        requested_household_id=requested_household_id,
    )
    household_id = str(context["active_household_id"])
    with engine.begin() as conn:
        household = conn.execute(
            text("""
                SELECT naam, created_at
                FROM household_registry
                WHERE id = :household_id
                LIMIT 1
            """),
            {"household_id": household_id},
        ).mappings().first()
    if not household:
        raise HTTPException(status_code=403, detail="Actieve huishoudcontext is ongeldig")

    household_name = household.get("naam")
    household_created_at = household.get("created_at")
    membership = {
        "household_id": household_id,
        "household_name": household_name,
        "household_created_at": household_created_at,
        "role": context["role"],
        "display_role": context["display_role"],
        "is_default": True,
    }
    return {
        **context,
        "active_household_name": household_name,
        "active_household_created_at": household_created_at,
        "memberships": [membership],
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
