"""Server-side session storage for Rezzerv.

This module is intentionally independent from browser state. It stores only a
cryptographic hash of the opaque session identifier and resolves user,
household and membership context from the database on every request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any, Mapping

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.system_superuser_session_provisioning import (
    SUPERGEBRUIKER_EMAIL,
    SUPERGEBRUIKER_HUISHOUDEN_ID,
)

SESSION_COOKIE_NAME = "rezzerv_session"
DEFAULT_SESSION_TTL = timedelta(hours=12)


@dataclass(frozen=True)
class ServerSessionContext:
    session_id: str
    user_id: str
    email: str
    active_household_id: str
    role: str
    session_version: int
    issued_at: datetime
    expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_session_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    if not normalized:
        raise ValueError("session_id ontbreekt")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def new_opaque_session_id() -> str:
    return secrets.token_urlsafe(48)


def _membership_columns(conn: Connection) -> set[str]:
    return {
        str(column.get("name") or "").strip().lower()
        for column in inspect(conn).get_columns("household_memberships")
    }


def membership_user_join_condition(
    conn: Connection,
    *,
    membership_alias: str = "hm",
    user_alias: str = "u",
) -> str:
    """Return the safe join used by the active runtime membership schema.

    Historic test databases used ``user_id`` while the production Rezzerv
    schema identifies a membership through ``user_email``. Only these two
    explicitly supported layouts are accepted; an unknown layout fails closed.
    """

    columns = _membership_columns(conn)
    if "user_email" in columns:
        return (
            f"lower(trim({membership_alias}.user_email)) = "
            f"lower(trim({user_alias}.email))"
        )
    if "user_id" in columns:
        return f"{membership_alias}.user_id = {user_alias}.id"
    raise RuntimeError(
        "household_memberships mist zowel user_email als user_id"
    )


def membership_active_condition(
    conn: Connection,
    *,
    membership_alias: str = "hm",
) -> str:
    columns = _membership_columns(conn)
    if "status" in columns:
        return f"lower(trim(COALESCE({membership_alias}.status, 'active'))) = 'active'"
    return "1 = 1"


def _household_zero_allowed(*, household_id: str, email: str, role: str) -> bool:
    """Allow the reserved household only for the canonical fixed superuser."""

    if household_id != SUPERGEBRUIKER_HUISHOUDEN_ID:
        return True
    return (
        str(email or "").strip().lower() == SUPERGEBRUIKER_EMAIL
        and str(role or "").strip().lower() == "owner"
    )


def ensure_server_session_schema(conn: Connection) -> None:
    """Create the session table idempotently."""

    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS server_sessions (
                id VARCHAR(64) PRIMARY KEY,
                session_token_hash VARCHAR(64) NOT NULL UNIQUE,
                user_id VARCHAR(64) NOT NULL,
                active_household_id VARCHAR(64) NOT NULL,
                issued_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                session_version INTEGER NOT NULL DEFAULT 1,
                revoked_at TIMESTAMP NULL,
                replaced_by_session_id VARCHAR(64) NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_server_sessions_user_active
            ON server_sessions(user_id, revoked_at, expires_at)
            """
        )
    )


def _normalize_database_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def create_server_session(
    conn: Connection,
    *,
    user_id: str,
    active_household_id: str,
    ttl: timedelta = DEFAULT_SESSION_TTL,
    replace_existing: bool = True,
    now: datetime | None = None,
) -> tuple[str, ServerSessionContext]:
    ensure_server_session_schema(conn)
    issued_at = (now or utc_now()).astimezone(timezone.utc)
    expires_at = issued_at + ttl
    user_id = str(user_id or "").strip()
    household_id = str(active_household_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Gebruiker ontbreekt")
    if not household_id:
        raise HTTPException(status_code=403, detail="Actief huishouden ontbreekt")

    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    membership = conn.execute(
        text(
            f"""
            SELECT u.id AS user_id, u.email, hm.role
            FROM app_users u
            JOIN household_memberships hm ON {join_condition}
            WHERE u.id = :user_id
              AND hm.household_id = :household_id
              AND {active_condition}
            LIMIT 1
            """
        ),
        {"user_id": user_id, "household_id": household_id},
    ).mappings().first()
    if not membership:
        raise HTTPException(status_code=403, detail="Geen toegang tot dit huishouden")

    membership_email = str(membership.get("email") or "")
    membership_role = str(membership.get("role") or "").strip().lower()
    if not _household_zero_allowed(
        household_id=household_id,
        email=membership_email,
        role=membership_role,
    ):
        raise HTTPException(status_code=403, detail="Ongeldig actief huishouden")

    raw_session_id = new_opaque_session_id()
    token_hash = hash_session_id(raw_session_id)
    record_id = secrets.token_hex(32)

    if replace_existing:
        conn.execute(
            text(
                """
                UPDATE server_sessions
                SET revoked_at = :now, updated_at = :now
                WHERE user_id = :user_id
                  AND revoked_at IS NULL
                  AND expires_at > :now
                """
            ),
            {"user_id": user_id, "now": issued_at},
        )

    conn.execute(
        text(
            """
            INSERT INTO server_sessions (
                id, session_token_hash, user_id, active_household_id,
                issued_at, expires_at, session_version, revoked_at,
                replaced_by_session_id, created_at, updated_at
            ) VALUES (
                :id, :token_hash, :user_id, :household_id,
                :issued_at, :expires_at, 1, NULL, NULL,
                :issued_at, :issued_at
            )
            """
        ),
        {
            "id": record_id,
            "token_hash": token_hash,
            "user_id": user_id,
            "household_id": household_id,
            "issued_at": issued_at,
            "expires_at": expires_at,
        },
    )

    return raw_session_id, ServerSessionContext(
        session_id=record_id,
        user_id=user_id,
        email=membership_email,
        active_household_id=household_id,
        role=membership_role,
        session_version=1,
        issued_at=issued_at,
        expires_at=expires_at,
    )


def resolve_server_session(
    conn: Connection,
    raw_session_id: str | None,
    *,
    now: datetime | None = None,
) -> ServerSessionContext:
    if not raw_session_id:
        raise HTTPException(status_code=401, detail="Geen geldige sessie")
    ensure_server_session_schema(conn)
    current_time = (now or utc_now()).astimezone(timezone.utc)
    join_condition = membership_user_join_condition(conn)
    active_condition = membership_active_condition(conn)
    row = conn.execute(
        text(
            f"""
            SELECT
                s.id AS session_id,
                s.user_id,
                u.email,
                s.active_household_id,
                hm.role,
                s.session_version,
                s.issued_at,
                s.expires_at,
                s.revoked_at
            FROM server_sessions s
            JOIN app_users u ON u.id = s.user_id
            JOIN household_memberships hm
              ON {join_condition}
             AND hm.household_id = s.active_household_id
             AND {active_condition}
            WHERE s.session_token_hash = :token_hash
            LIMIT 1
            """
        ),
        {"token_hash": hash_session_id(raw_session_id)},
    ).mappings().first()

    if not row or row.get("revoked_at") is not None:
        raise HTTPException(status_code=401, detail="Sessie is ongeldig")
    expires_at = _normalize_database_datetime(row.get("expires_at"))
    if expires_at <= current_time:
        conn.execute(
            text("UPDATE server_sessions SET revoked_at = :now, updated_at = :now WHERE id = :id"),
            {"now": current_time, "id": row.get("session_id")},
        )
        raise HTTPException(status_code=401, detail="Sessie is verlopen")

    household_id = str(row.get("active_household_id") or "").strip()
    email = str(row.get("email") or "")
    role = str(row.get("role") or "").strip().lower()
    if not household_id:
        raise HTTPException(status_code=403, detail="Actief huishouden ontbreekt")
    if not role:
        raise HTTPException(status_code=403, detail="Bevoegdheid ontbreekt")
    if not _household_zero_allowed(
        household_id=household_id,
        email=email,
        role=role,
    ):
        raise HTTPException(status_code=403, detail="Ongeldig actief huishouden")

    return ServerSessionContext(
        session_id=str(row.get("session_id")),
        user_id=str(row.get("user_id")),
        email=email,
        active_household_id=household_id,
        role=role,
        session_version=int(row.get("session_version") or 1),
        issued_at=_normalize_database_datetime(row.get("issued_at")),
        expires_at=expires_at,
    )


def revoke_server_session(conn: Connection, raw_session_id: str | None, *, now: datetime | None = None) -> None:
    if not raw_session_id:
        return
    current_time = (now or utc_now()).astimezone(timezone.utc)
    ensure_server_session_schema(conn)
    conn.execute(
        text(
            """
            UPDATE server_sessions
            SET revoked_at = COALESCE(revoked_at, :now), updated_at = :now
            WHERE session_token_hash = :token_hash
            """
        ),
        {"now": current_time, "token_hash": hash_session_id(raw_session_id)},
    )


def rotate_active_household(
    conn: Connection,
    raw_session_id: str,
    new_household_id: str,
    *,
    now: datetime | None = None,
) -> tuple[str, ServerSessionContext]:
    current = resolve_server_session(conn, raw_session_id, now=now)
    new_household_id = str(new_household_id or "").strip()
    if not new_household_id:
        raise HTTPException(status_code=403, detail="Ongeldig huishouden")

    raw_new_session_id, new_context = create_server_session(
        conn,
        user_id=current.user_id,
        active_household_id=new_household_id,
        replace_existing=False,
        now=now,
    )
    current_time = (now or utc_now()).astimezone(timezone.utc)
    conn.execute(
        text(
            """
            UPDATE server_sessions
            SET revoked_at = :now,
                replaced_by_session_id = :replacement_id,
                updated_at = :now
            WHERE id = :session_id
            """
        ),
        {
            "now": current_time,
            "replacement_id": new_context.session_id,
            "session_id": current.session_id,
        },
    )
    return raw_new_session_id, new_context


def public_session_payload(context: ServerSessionContext) -> Mapping[str, Any]:
    return {
        "user": {"id": context.user_id, "email": context.email},
        "active_household_id": context.active_household_id,
        "role": context.role,
        "session_version": context.session_version,
        "expires_at": context.expires_at.isoformat(),
    }
