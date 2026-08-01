"""Server-side session adapter for household support messages.

Every active household member may create, read and reply to their own support
threads. Platform-wide support remains restricted by the existing platform
permission checks in support_message_routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.services.household_context_adapter import household_context_from_runtime_context


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "items"):
        return dict(value.items())
    return {
        "user_id": getattr(value, "user_id", None),
        "email": getattr(value, "email", None),
        "name": getattr(value, "name", None),
        "display_name": getattr(value, "display_name", None),
        "role": getattr(value, "role", None),
        "display_role": getattr(value, "display_role", None),
    }


def household_support_actor(authorization: str | None = None) -> dict[str, str]:
    """Resolve an authenticated active household member for support messaging."""

    from app import main as main_module

    runtime = _mapping(main_module.require_household_context(authorization))
    context = household_context_from_runtime_context(runtime)
    user_id = str(runtime.get("user_id") or runtime.get("email") or "").strip()
    if not user_id:
        raise HTTPException(status_code=403, detail="Gebruiker heeft geen bruikbaar gebruikers-ID")

    role = str(runtime.get("role") or runtime.get("display_role") or "household.member").strip().lower()
    return {
        "user_id": user_id,
        "name": str(
            runtime.get("name")
            or runtime.get("display_name")
            or runtime.get("email")
            or "Rezzerv-gebruiker"
        ),
        "role": role or "household.member",
        "household_id": str(context.active_household_id),
    }
