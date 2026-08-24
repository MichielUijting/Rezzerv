from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection


class PlatformSessionNotFoundError(LookupError):
    pass


class PlatformSessionConflictError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("Sessie bevat een ongeldige tijdstempel")
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_datetime(value: Any) -> str:
    return _normalize_datetime(value).isoformat()


def _safe_session_item(row: Any, *, current_session_id: str) -> dict:
    return {
        "session_id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "email": str(row["email"]),
        "issued_at": _iso_datetime(row["issued_at"]),
        "expires_at": _iso_datetime(row["expires_at"]),
        "is_current": str(row["id"]) == str(current_session_id),
    }


def list_platform_sessions(
    conn: Connection,
    *,
    current_session_id: str,
    now: datetime | None = None,
) -> list[dict]:
    current = now or utc_now()
    rows = conn.execute(
        text("""
            SELECT s.id, s.user_id, u.email, s.issued_at, s.expires_at
            FROM server_sessions s
            JOIN app_users u ON u.id = s.user_id
            WHERE s.revoked_at IS NULL
              AND s.expires_at > :now
            ORDER BY s.issued_at DESC, s.id ASC
        """),
        {"now": current},
    ).mappings().all()
    return [
        _safe_session_item(row, current_session_id=current_session_id)
        for row in rows
    ]


def revoke_platform_session_by_id(
    conn: Connection,
    session_id: str,
    *,
    current_session_id: str,
    now: datetime | None = None,
) -> dict:
    normalized_session_id = str(session_id or "").strip()
    normalized_current_session_id = str(current_session_id or "").strip()
    if not normalized_session_id:
        raise PlatformSessionNotFoundError("Sessie bestaat niet")
    if normalized_session_id == normalized_current_session_id:
        raise PlatformSessionConflictError(
            "De huidige beheersessie kan hier niet worden ingetrokken; gebruik Uitloggen."
        )

    row = conn.execute(
        text("""
            SELECT s.id, s.user_id, u.email, s.issued_at, s.expires_at, s.revoked_at
            FROM server_sessions s
            JOIN app_users u ON u.id = s.user_id
            WHERE s.id = :session_id
            LIMIT 1
        """),
        {"session_id": normalized_session_id},
    ).mappings().first()
    if row is None:
        raise PlatformSessionNotFoundError("Sessie bestaat niet")

    current = now or utc_now()
    if row["revoked_at"] is not None:
        raise PlatformSessionConflictError("Sessie is al ingetrokken")
    if _normalize_datetime(row["expires_at"]) <= current:
        raise PlatformSessionConflictError("Sessie is al verlopen")

    result = conn.execute(
        text("""
            UPDATE server_sessions
            SET revoked_at = :now, updated_at = :now
            WHERE id = :session_id
              AND revoked_at IS NULL
              AND expires_at > :now
        """),
        {"session_id": normalized_session_id, "now": current},
    )
    if result.rowcount != 1:
        raise PlatformSessionConflictError("Sessie kon niet meer worden ingetrokken")

    return {
        "session_id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "email": str(row["email"]),
        "issued_at": _iso_datetime(row["issued_at"]),
        "expires_at": _iso_datetime(row["expires_at"]),
        "revoked_at": current.isoformat(),
    }
