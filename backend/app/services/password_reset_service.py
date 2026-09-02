from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import secrets
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.password_service import hash_password, verify_password


PASSWORD_RESET_TABLE = "account_password_reset_tokens"
PASSWORD_RESET_TTL = timedelta(minutes=30)
PASSWORD_RESET_RATE_WINDOW = timedelta(minutes=15)
PASSWORD_RESET_MAX_PER_USER = 3
PASSWORD_RESET_MAX_PER_IP = 10
PASSWORD_RESET_TOKEN_BYTES = 48

_REQUIRED_COLUMNS = {
    "id",
    "user_id",
    "token_hash",
    "request_ip_hash",
    "requested_at",
    "expires_at",
    "used_at",
    "revoked_at",
    "created_at",
    "updated_at",
}


class PasswordResetInvalidTokenError(ValueError):
    pass


class PasswordResetPasswordReuseError(ValueError):
    pass


class PasswordResetConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PasswordResetRequestResult:
    account_found: bool
    rate_limited: bool
    recipient_email: str | None = None
    raw_token: str | None = None
    token_hash: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class PasswordResetConfirmResult:
    user_id: str
    email: str
    revoked_sessions: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_password_reset_token() -> str:
    return secrets.token_urlsafe(PASSWORD_RESET_TOKEN_BYTES)


def hash_password_reset_token(raw_token: str) -> str:
    normalized = str(raw_token or "").strip()
    if not normalized:
        raise PasswordResetInvalidTokenError("Herstellink is ongeldig of verlopen")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _rate_limit_secret() -> bytes:
    configured = str(os.getenv("REZZERV_PASSWORD_RESET_RATE_LIMIT_SECRET", "") or "").strip()
    if configured:
        if len(configured) < 32:
            raise PasswordResetConfigurationError(
                "REZZERV_PASSWORD_RESET_RATE_LIMIT_SECRET moet minimaal 32 tekens bevatten"
            )
        return configured.encode("utf-8")

    environment = str(os.getenv("REZZERV_ENV", "production") or "production").strip().lower()
    if environment in {"local", "development", "test"}:
        return b"rezzerv-password-reset-local-rate-limit-only"
    raise PasswordResetConfigurationError(
        "REZZERV_PASSWORD_RESET_RATE_LIMIT_SECRET ontbreekt"
    )


def hash_password_reset_request_ip(client_ip: str) -> str:
    normalized = str(client_ip or "unknown").strip() or "unknown"
    return hmac.new(
        _rate_limit_secret(),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def validate_password_reset_schema(conn: Connection) -> None:
    inspector = inspect(conn)
    if not inspector.has_table(PASSWORD_RESET_TABLE):
        raise RuntimeError(
            "Canonical password-reset schema ontbreekt; voer Alembic migrations uit"
        )
    columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspector.get_columns(PASSWORD_RESET_TABLE)
    }
    missing = _REQUIRED_COLUMNS - columns
    if missing:
        raise RuntimeError(
            "Canonical password-reset schema wijkt af; ontbrekend: "
            f"{sorted(missing)}"
        )


def _normalize_database_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def request_password_reset(
    conn: Connection,
    *,
    email: str,
    client_ip: str,
    now: datetime | None = None,
) -> PasswordResetRequestResult:
    """Create a one-time reset secret without exposing whether the account exists."""

    validate_password_reset_schema(conn)
    request_ip_hash = hash_password_reset_request_ip(client_ip)
    current = (now or utc_now()).astimezone(timezone.utc)
    window_start = current - PASSWORD_RESET_RATE_WINDOW
    normalized_email = str(email or "").strip().lower()

    accounts = conn.execute(
        text(
            """
            SELECT id, email
            FROM app_users
            WHERE lower(trim(email)) = :email
            LIMIT 2
            """
        ),
        {"email": normalized_email},
    ).mappings().all()
    if len(accounts) != 1:
        return PasswordResetRequestResult(account_found=False, rate_limited=False)

    account = accounts[0]
    user_id = str(account.get("id") or "").strip()
    recipient_email = str(account.get("email") or "").strip().lower()
    if not user_id or not recipient_email:
        return PasswordResetRequestResult(account_found=False, rate_limited=False)

    user_attempts = int(
        conn.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM {PASSWORD_RESET_TABLE}
                WHERE user_id = :user_id
                  AND requested_at >= :window_start
                """
            ),
            {"user_id": user_id, "window_start": window_start},
        ).scalar()
        or 0
    )
    ip_attempts = int(
        conn.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM {PASSWORD_RESET_TABLE}
                WHERE request_ip_hash = :request_ip_hash
                  AND requested_at >= :window_start
                """
            ),
            {"request_ip_hash": request_ip_hash, "window_start": window_start},
        ).scalar()
        or 0
    )
    if user_attempts >= PASSWORD_RESET_MAX_PER_USER or ip_attempts >= PASSWORD_RESET_MAX_PER_IP:
        return PasswordResetRequestResult(
            account_found=True,
            rate_limited=True,
            recipient_email=recipient_email,
        )

    conn.execute(
        text(
            f"""
            UPDATE {PASSWORD_RESET_TABLE}
            SET revoked_at = :now,
                updated_at = :now
            WHERE user_id = :user_id
              AND used_at IS NULL
              AND revoked_at IS NULL
              AND expires_at > :now
            """
        ),
        {"now": current, "user_id": user_id},
    )

    raw_token = new_password_reset_token()
    token_hash = hash_password_reset_token(raw_token)
    expires_at = current + PASSWORD_RESET_TTL
    conn.execute(
        text(
            f"""
            INSERT INTO {PASSWORD_RESET_TABLE} (
                id, user_id, token_hash, request_ip_hash,
                requested_at, expires_at, used_at, revoked_at,
                created_at, updated_at
            ) VALUES (
                :id, :user_id, :token_hash, :request_ip_hash,
                :requested_at, :expires_at, NULL, NULL,
                :requested_at, :requested_at
            )
            """
        ),
        {
            "id": uuid.uuid4().hex,
            "user_id": user_id,
            "token_hash": token_hash,
            "request_ip_hash": request_ip_hash,
            "requested_at": current,
            "expires_at": expires_at,
        },
    )
    return PasswordResetRequestResult(
        account_found=True,
        rate_limited=False,
        recipient_email=recipient_email,
        raw_token=raw_token,
        token_hash=token_hash,
        expires_at=expires_at,
    )


def revoke_password_reset_token(
    conn: Connection,
    *,
    token_hash: str,
    now: datetime | None = None,
) -> None:
    current = (now or utc_now()).astimezone(timezone.utc)
    conn.execute(
        text(
            f"""
            UPDATE {PASSWORD_RESET_TABLE}
            SET revoked_at = COALESCE(revoked_at, :now),
                updated_at = :now
            WHERE token_hash = :token_hash
              AND used_at IS NULL
            """
        ),
        {"now": current, "token_hash": str(token_hash or "")},
    )


def confirm_password_reset(
    conn: Connection,
    *,
    raw_token: str,
    new_password: str,
    now: datetime | None = None,
) -> PasswordResetConfirmResult:
    """Atomically consume one reset token, change password and revoke all sessions."""

    validate_password_reset_schema(conn)
    token_hash = hash_password_reset_token(raw_token)
    current = (now or utc_now()).astimezone(timezone.utc)
    lock_suffix = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
    token_row = conn.execute(
        text(
            f"""
            SELECT id, user_id, expires_at, used_at, revoked_at
            FROM {PASSWORD_RESET_TABLE}
            WHERE token_hash = :token_hash
            LIMIT 1{lock_suffix}
            """
        ),
        {"token_hash": token_hash},
    ).mappings().first()
    if token_row is None:
        raise PasswordResetInvalidTokenError("Herstellink is ongeldig of verlopen")
    if token_row.get("used_at") is not None or token_row.get("revoked_at") is not None:
        raise PasswordResetInvalidTokenError("Herstellink is ongeldig of verlopen")
    expires_at = _normalize_database_datetime(token_row.get("expires_at"))
    if expires_at <= current:
        raise PasswordResetInvalidTokenError("Herstellink is ongeldig of verlopen")

    user_id = str(token_row.get("user_id") or "").strip()
    user_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspect(conn).get_columns("app_users")
    }
    password_hash_expression = "password_hash" if "password_hash" in user_columns else "NULL"
    account = conn.execute(
        text(
            f"""
            SELECT id, email, password, {password_hash_expression} AS password_hash
            FROM app_users
            WHERE id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": user_id},
    ).mappings().first()
    if account is None:
        raise PasswordResetInvalidTokenError("Herstellink is ongeldig of verlopen")

    supplied_password = str(new_password or "")
    if verify_password(
        account.get("password"),
        supplied_password,
        stored_password_hash=account.get("password_hash"),
    ):
        raise PasswordResetPasswordReuseError(
            "Nieuw wachtwoord moet verschillen van het huidige wachtwoord"
        )

    encoded_password = hash_password(supplied_password)
    assignments = ["password = :password"]
    params: dict[str, object] = {"password": encoded_password, "user_id": user_id}
    if "password_hash" in user_columns:
        assignments.append("password_hash = :password_hash")
        params["password_hash"] = encoded_password
    if "updated_at" in user_columns:
        assignments.append("updated_at = :updated_at")
        params["updated_at"] = current
    conn.execute(
        text(f"UPDATE app_users SET {', '.join(assignments)} WHERE id = :user_id"),
        params,
    )

    token_id = str(token_row.get("id") or "")
    conn.execute(
        text(
            f"""
            UPDATE {PASSWORD_RESET_TABLE}
            SET used_at = :now,
                updated_at = :now
            WHERE id = :token_id
              AND used_at IS NULL
              AND revoked_at IS NULL
            """
        ),
        {"now": current, "token_id": token_id},
    )
    conn.execute(
        text(
            f"""
            UPDATE {PASSWORD_RESET_TABLE}
            SET revoked_at = :now,
                updated_at = :now
            WHERE user_id = :user_id
              AND id <> :token_id
              AND used_at IS NULL
              AND revoked_at IS NULL
            """
        ),
        {"now": current, "user_id": user_id, "token_id": token_id},
    )

    revoked_sessions = 0
    if inspect(conn).has_table("server_sessions"):
        revoked = conn.execute(
            text(
                """
                UPDATE server_sessions
                SET revoked_at = :now,
                    updated_at = :now
                WHERE user_id = :user_id
                  AND revoked_at IS NULL
                  AND expires_at > :now
                """
            ),
            {"now": current, "user_id": user_id},
        )
        revoked_sessions = int(revoked.rowcount or 0)

    return PasswordResetConfirmResult(
        user_id=user_id,
        email=str(account.get("email") or "").strip().lower(),
        revoked_sessions=revoked_sessions,
    )
