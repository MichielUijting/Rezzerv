from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app.services.runtime_auth_compatibility_service import (
    build_explicit_runtime_token,
    parse_explicit_runtime_token,
)


LEGACY_DEFAULT_ADMIN_EMAIL = "admin@rezzerv.local"


def _load_runtime_identity(main_module: Any, email: str, get_user_record: Callable[[str], Any]) -> dict:
    user = get_user_record(email)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    normalized = dict(user)
    normalized["email"] = email
    normalized.setdefault("user_id", normalized.get("id") or email)

    with main_module.engine.begin() as conn:
        membership = conn.execute(
            text(
                """
                SELECT hm.role
                FROM household_memberships hm
                WHERE lower(trim(hm.user_email)) = :email
                ORDER BY CASE lower(trim(hm.role))
                    WHEN 'owner' THEN 0
                    WHEN 'member' THEN 1
                    WHEN 'viewer' THEN 2
                    ELSE 3
                END,
                hm.created_at ASC,
                hm.household_id ASC
                LIMIT 1
                """
            ),
            {"email": email},
        ).mappings().first()
        platform_role = conn.execute(
            text(
                """
                SELECT role_key
                FROM auth_platform_user_roles
                WHERE lower(trim(user_id)) IN (:user_id, :email)
                  AND active = 1
                ORDER BY CASE role_key
                    WHEN 'platform.supergebruiker' THEN 0
                    WHEN 'platform.frontteam' THEN 1
                    ELSE 2
                END
                LIMIT 1
                """
            ),
            {
                "user_id": str(normalized.get("user_id") or email).strip().lower(),
                "email": email,
            },
        ).mappings().first()

    membership_role = str((membership or {}).get("role") or "").strip().lower()
    platform_role_key = str((platform_role or {}).get("role_key") or "").strip()

    # Compatibility for the remaining legacy central test routes: only the
    # actual Supergebruiker is represented as admin. Household ownership alone
    # never grants central access anymore.
    if platform_role_key == "platform.supergebruiker":
        normalized["role"] = "admin"
    elif membership_role in {"owner", "member", "viewer"}:
        normalized["role"] = membership_role
    else:
        normalized["role"] = "member"

    normalized["platform_role_key"] = platform_role_key or None
    return normalized


def apply_runtime_auth_override(main_module: Any) -> None:
    if getattr(main_module, "_runtime_auth_override_applied", False):
        return

    original_get_user_record = main_module.get_user_record

    def safe_get_user_record(email: str):
        normalized_email = str(email or "").strip().lower()
        if normalized_email == LEGACY_DEFAULT_ADMIN_EMAIL:
            return None
        return original_get_user_record(normalized_email)

    def secure_get_current_user_from_authorization(authorization: str | None):
        email = parse_explicit_runtime_token(authorization)
        if email == LEGACY_DEFAULT_ADMIN_EMAIL:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return _load_runtime_identity(main_module, email, safe_get_user_record)

    main_module.users.pop(LEGACY_DEFAULT_ADMIN_EMAIL, None)
    main_module.get_user_record = safe_get_user_record
    main_module.get_current_user_from_authorization = secure_get_current_user_from_authorization
    main_module.build_auth_token = build_explicit_runtime_token
    main_module._runtime_auth_override_applied = True


def register_runtime_auth_startup(router: APIRouter) -> None:
    @router.on_event("startup")
    def activate_explicit_runtime_auth() -> None:
        from app import main as main_module

        apply_runtime_auth_override(main_module)
