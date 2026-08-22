from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

from app.services.server_session_service import ServerSessionContext

ARCHIVED_RECEIPT_PURGE_PERMISSION = "platform.recovery.manage"
ARCHIVED_RECEIPT_PURGE_ROUTES = frozenset(
    {
        ("POST", "/api/admin/receipts/purge-archived"),
    }
)

_archived_receipt_purge_platform_context: ContextVar[ServerSessionContext | None] = ContextVar(
    "rezzerv_archived_receipt_purge_platform_context",
    default=None,
)


def required_archived_receipt_purge_permission(method: str, path: str) -> str | None:
    request_key = (str(method or "").upper(), str(path or ""))
    if request_key not in ARCHIVED_RECEIPT_PURGE_ROUTES:
        return None
    return ARCHIVED_RECEIPT_PURGE_PERMISSION


def bind_archived_receipt_purge_platform_context(context: ServerSessionContext) -> Token:
    """Bind the already-authorized recovery actor for one purge request only."""

    return _archived_receipt_purge_platform_context.set(context)


def reset_archived_receipt_purge_platform_context(token: Token) -> None:
    _archived_receipt_purge_platform_context.reset(token)


def archived_receipt_purge_household_context(
    requested_household_id: str | None,
) -> dict[str, Any] | None:
    """Return a route-scoped target context after canonical recovery authorization.

    The destructive purge endpoint historically re-checked household-admin
    membership after a platform-level guard. Platformbeheerder intentionally has
    no household membership. Once the exact purge route has passed
    ``platform.recovery.manage`` at the session boundary, preserve the explicit
    payload household id as the operation target without manufacturing a
    household membership. Other routes see ``None`` and retain the normal
    household-admin guard.
    """

    context = _archived_receipt_purge_platform_context.get()
    if context is None:
        return None

    target_household_id = str(requested_household_id or "").strip()
    return {
        "user_id": context.user_id,
        "email": context.email,
        "role": context.role,
        "display_role": "platform_recovery",
        "household_id": target_household_id or None,
        "active_household_id": target_household_id or None,
        "membership_count": 0,
        "can_switch_households": False,
    }
