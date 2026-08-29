from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
from typing import Any, Mapping

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.server_session_service import ensure_server_session_schema


ACTIVE_ACCOUNT_STATUS = "active"
SUSPENDED_ACCOUNT_STATUS = "suspended"


class PlatformUserNotFoundError(LookupError):
    pass


class PlatformUserConflictError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_user_account_status_schema(conn: Connection) -> None:
    """Fail closed when Alembic has not installed account suspension columns."""

    inspector = inspect(conn)
    if not inspector.has_table("app_users"):
        raise RuntimeError("app_users ontbreekt")
    columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns("app_users")
    }
    missing_columns = sorted({"account_status", "suspended_at"} - columns)
    if missing_columns:
        raise RuntimeError(
            "app_users schema drift; ontbrekende kolommen: "
            + ", ".join(missing_columns)
        )


def normalize_user_account_status_data(conn: Connection) -> None:
    """Normalize legacy empty statuses using DML only after schema validation."""

    conn.execute(text("""
        UPDATE app_users
        SET account_status = 'active'
        WHERE account_status IS NULL OR trim(account_status) = ''
    """))


def ensure_user_account_status_schema(conn: Connection) -> None:
    """Compatibility shim: validate Alembic authority and normalize data only."""

    validate_user_account_status_schema(conn)
    normalize_user_account_status_data(conn)


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_active_status(value: Any) -> bool:
    return _normalize_status(value) == ACTIVE_ACCOUNT_STATUS


def _iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def user_account_is_active(conn: Connection, user_id: str) -> bool:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return False
    row = conn.execute(text("""
        SELECT account_status
        FROM app_users
        WHERE id = :user_id
        LIMIT 1
    """), {"user_id": normalized_user_id}).mappings().first()
    return bool(row) and _is_active_status(row.get("account_status"))


def require_user_account_active(conn: Connection, user_id: str) -> None:
    if not user_account_is_active(conn, user_id):
        raise HTTPException(status_code=401, detail="Account is geschorst")


def _safe_user_item(
    row: Mapping[str, Any],
    *,
    current_user_id: str,
    active_session_count: int,
) -> dict[str, Any]:
    status = _normalize_status(row.get("account_status"))
    if status not in {ACTIVE_ACCOUNT_STATUS, SUSPENDED_ACCOUNT_STATUS}:
        status = SUSPENDED_ACCOUNT_STATUS
    user_id = str(row.get("id") or "")
    return {
        "user_id": user_id,
        "email": str(row.get("email") or ""),
        "account_status": status,
        "suspended_at": _iso_datetime(row.get("suspended_at")),
        "active_session_count": int(active_session_count or 0),
        "is_current": user_id == str(current_user_id or ""),
    }


def list_platform_users(
    conn: Connection,
    *,
    current_user_id: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current = now or utc_now()
    session_counts: dict[str, int] = {}
    if inspect(conn).has_table("server_sessions"):
        rows = conn.execute(text("""
            SELECT user_id, COUNT(*) AS active_session_count
            FROM server_sessions
            WHERE revoked_at IS NULL AND expires_at > :now
            GROUP BY user_id
        """), {"now": current}).mappings().all()
        session_counts = {
            str(row.get("user_id") or ""): int(row.get("active_session_count") or 0)
            for row in rows
        }

    users = conn.execute(text("""
        SELECT id, email, account_status, suspended_at
        FROM app_users
        ORDER BY lower(trim(email)) ASC, id ASC
    """)).mappings().all()
    return [
        _safe_user_item(
            row,
            current_user_id=current_user_id,
            active_session_count=session_counts.get(str(row.get("id") or ""), 0),
        )
        for row in users
    ]


def suspend_platform_user(
    conn: Connection,
    user_id: str,
    *,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_user_account_status_schema(conn)
    ensure_server_session_schema(conn)

    target_user_id = str(user_id or "").strip()
    actor_user_id = str(actor_user_id or "").strip()
    if not target_user_id:
        raise PlatformUserNotFoundError("Gebruiker bestaat niet")
    if target_user_id == actor_user_id:
        raise PlatformUserConflictError(
            "Je kunt je eigen huidige account niet via Platformbeheer schorsen."
        )

    row = conn.execute(text("""
        SELECT id, email, account_status, suspended_at
        FROM app_users
        WHERE id = :user_id
        LIMIT 1
    """), {"user_id": target_user_id}).mappings().first()
    if row is None:
        raise PlatformUserNotFoundError("Gebruiker bestaat niet")
    if not _is_active_status(row.get("account_status")):
        raise PlatformUserConflictError("Account is al geschorst")

    current = (now or utc_now()).astimezone(timezone.utc)
    update_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspect(conn).get_columns("app_users")
    }
    updated_at_sql = ", updated_at = :now" if "updated_at" in update_columns else ""
    conn.execute(text(f"""
        UPDATE app_users
        SET account_status = :status,
            suspended_at = :now
            {updated_at_sql}
        WHERE id = :user_id
    """), {
        "status": SUSPENDED_ACCOUNT_STATUS,
        "now": current,
        "user_id": target_user_id,
    })

    revoked = conn.execute(text("""
        UPDATE server_sessions
        SET revoked_at = :now, updated_at = :now
        WHERE user_id = :user_id
          AND revoked_at IS NULL
          AND expires_at > :now
    """), {"now": current, "user_id": target_user_id})

    return {
        "user_id": target_user_id,
        "email": str(row.get("email") or ""),
        "account_status": SUSPENDED_ACCOUNT_STATUS,
        "suspended_at": current.isoformat(),
        "active_sessions_revoked": int(revoked.rowcount or 0),
    }


def install_server_session_suspension_guard() -> None:
    """Make account suspension authoritative for new cookie-session login.

    The cookie router may already have been constructed when app.api.router is
    imported. Its login closure resolves this module-global helper at request
    time, so replacing the helper is effective both before and after router
    construction without changing legacy route ownership.
    """

    from app.api import server_session_routes

    if bool(getattr(server_session_routes, "_platform_user_suspension_guard_installed", False)):
        return

    original_resolve_login_identity = server_session_routes._resolve_login_identity

    @wraps(original_resolve_login_identity)
    def guarded_resolve_login_identity(conn, email: str, password: str):
        identity = original_resolve_login_identity(conn, email, password)
        ensure_user_account_status_schema(conn)
        require_user_account_active(conn, str(identity.get("user_id") or ""))
        return identity

    server_session_routes._resolve_login_identity = guarded_resolve_login_identity
    server_session_routes._platform_user_suspension_guard_installed = True
