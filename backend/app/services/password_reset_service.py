from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.password_service import hash_password


PASSWORD_RESET_TABLE = "account_password_reset_tokens"
PASSWORD_RESET_TTL = timedelta(minutes=30)
PASSWORD_RESET_RATE_WINDOW = timedelta(minutes=15)
PASSWORD_RESET_EMAIL_LIMIT = 3
PASSWORD_RESET_IP_LIMIT = 10
PASSWORD_RESET_RETENTION = timedelta(days=7)
PASSWORD_RESET_GENERIC_MESSAGE = (
    "Als dit e-mailadres bij ons bekend is, ontvang je een e-mail waarmee je "
    "je wachtwoord opnieuw kunt instellen."
)
PASSWORD_RESET_INVALID_MESSAGE = "Deze herstellink is ongeldig of verlopen."

_REQUIRED_RESET_COLUMNS = {
    "id",
    "user_id",
    "request_email_hash",
    "request_ip_hash",
    "token_hash",
    "requested_at",
    "expires_at",
    "used_at",
    "invalidated_at",
}
_REQUIRED_USER_COLUMNS = {"id", "email", "password"}
_REQUIRED_SESSION_COLUMNS = {"user_id", "revoked_at"}


class PasswordResetSchemaError(RuntimeError):
    pass


class PasswordResetTokenInvalidError(ValueError):
    pass


@dataclass(frozen=True)
class PasswordResetIssueResult:
    email: str | None
    raw_token: str | None
    expires_at: datetime | None
    rate_limited: bool

    @property
    def should_deliver(self) -> bool:
        return bool(self.email and self.raw_token and self.expires_at)


@dataclass(frozen=True)
class PasswordResetConfirmResult:
    user_id: str
    email: str
    revoked_sessions: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_ip(value: str | None) -> str:
    normalized = str(value or "").strip()
    return normalized or "unknown"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password_reset_token(raw_token: str) -> str:
    return _sha256(str(raw_token or ""))


def generate_password_reset_token() -> str:
    return secrets.token_urlsafe(48)


def validate_password_reset_schema(connection: Connection) -> dict[str, set[str]]:
    """Validate migration-owned reset/account/session schema without mutating it."""
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    required_tables = {PASSWORD_RESET_TABLE, "app_users", "server_sessions"}
    missing_tables = sorted(required_tables - tables)
    if missing_tables:
        raise PasswordResetSchemaError(
            "Password-reset schema ontbreekt; voer eerst Alembic-migraties uit: "
            + ", ".join(missing_tables)
        )

    reset_columns = {item["name"] for item in inspector.get_columns(PASSWORD_RESET_TABLE)}
    user_columns = {item["name"] for item in inspector.get_columns("app_users")}
    session_columns = {item["name"] for item in inspector.get_columns("server_sessions")}

    missing_reset = sorted(_REQUIRED_RESET_COLUMNS - reset_columns)
    missing_users = sorted(_REQUIRED_USER_COLUMNS - user_columns)
    missing_sessions = sorted(_REQUIRED_SESSION_COLUMNS - session_columns)
    if missing_reset or missing_users or missing_sessions:
        raise PasswordResetSchemaError(
            "Password-reset schema-contract ongeldig: "
            f"reset={missing_reset} users={missing_users} sessions={missing_sessions}"
        )

    return {
        "reset": reset_columns,
        "users": user_columns,
        "sessions": session_columns,
    }


def _cleanup_old_requests(connection: Connection, *, now: datetime) -> None:
    cutoff = now - PASSWORD_RESET_RETENTION
    connection.execute(
        text(
            f"DELETE FROM {PASSWORD_RESET_TABLE} "
            "WHERE requested_at < :cutoff"
        ),
        {"cutoff": cutoff},
    )


def _recent_request_count(
    connection: Connection,
    *,
    column_name: str,
    value_hash: str,
    since: datetime,
) -> int:
    if column_name not in {"request_email_hash", "request_ip_hash"}:
        raise ValueError("Unsupported password-reset rate-limit dimension")
    return int(
        connection.execute(
            text(
                f"SELECT COUNT(*) FROM {PASSWORD_RESET_TABLE} "
                f"WHERE {column_name} = :value_hash AND requested_at >= :since"
            ),
            {"value_hash": value_hash, "since": since},
        ).scalar_one()
        or 0
    )


def _find_active_user(
    connection: Connection,
    *,
    normalized_email: str,
    user_columns: set[str],
) -> dict[str, Any] | None:
    selected = ["id", "email"]
    if "account_status" in user_columns:
        selected.append("account_status")
    query = (
        f"SELECT {', '.join(selected)} FROM app_users "
        "WHERE LOWER(TRIM(email)) = :email"
    )
    if "account_status" in user_columns:
        query += " AND LOWER(COALESCE(account_status, 'active')) = 'active'"
    query += " LIMIT 1"
    row = connection.execute(text(query), {"email": normalized_email}).mappings().first()
    return dict(row) if row is not None else None


def issue_password_reset(
    connection: Connection,
    *,
    email: str,
    request_ip: str | None,
    now: datetime | None = None,
) -> PasswordResetIssueResult:
    schema = validate_password_reset_schema(connection)
    requested_at = now or _utcnow()
    normalized_email = _normalize_email(email)
    normalized_ip = _normalize_ip(request_ip)
    email_hash = _sha256(normalized_email)
    ip_hash = _sha256(normalized_ip)

    _cleanup_old_requests(connection, now=requested_at)
    since = requested_at - PASSWORD_RESET_RATE_WINDOW
    email_count = _recent_request_count(
        connection,
        column_name="request_email_hash",
        value_hash=email_hash,
        since=since,
    )
    ip_count = _recent_request_count(
        connection,
        column_name="request_ip_hash",
        value_hash=ip_hash,
        since=since,
    )
    if email_count >= PASSWORD_RESET_EMAIL_LIMIT or ip_count >= PASSWORD_RESET_IP_LIMIT:
        return PasswordResetIssueResult(
            email=None,
            raw_token=None,
            expires_at=None,
            rate_limited=True,
        )

    user = _find_active_user(
        connection,
        normalized_email=normalized_email,
        user_columns=schema["users"],
    )
    request_id = secrets.token_hex(32)
    raw_token: str | None = None
    token_hash: str | None = None
    expires_at: datetime | None = None
    user_id: str | None = None
    delivery_email: str | None = None

    if user is not None:
        user_id = str(user["id"])
        delivery_email = str(user["email"])
        raw_token = generate_password_reset_token()
        token_hash = hash_password_reset_token(raw_token)
        expires_at = requested_at + PASSWORD_RESET_TTL
        connection.execute(
            text(
                f"UPDATE {PASSWORD_RESET_TABLE} "
                "SET invalidated_at = :now "
                "WHERE user_id = :user_id "
                "AND used_at IS NULL AND invalidated_at IS NULL"
            ),
            {"now": requested_at, "user_id": user_id},
        )

    connection.execute(
        text(
            f"INSERT INTO {PASSWORD_RESET_TABLE} "
            "(id, user_id, request_email_hash, request_ip_hash, token_hash, "
            "requested_at, expires_at, used_at, invalidated_at) "
            "VALUES (:id, :user_id, :email_hash, :ip_hash, :token_hash, "
            ":requested_at, :expires_at, NULL, NULL)"
        ),
        {
            "id": request_id,
            "user_id": user_id,
            "email_hash": email_hash,
            "ip_hash": ip_hash,
            "token_hash": token_hash,
            "requested_at": requested_at,
            "expires_at": expires_at,
        },
    )
    return PasswordResetIssueResult(
        email=delivery_email,
        raw_token=raw_token,
        expires_at=expires_at,
        rate_limited=False,
    )


def confirm_password_reset(
    connection: Connection,
    *,
    raw_token: str,
    new_password: str,
    now: datetime | None = None,
) -> PasswordResetConfirmResult:
    schema = validate_password_reset_schema(connection)
    changed_at = now or _utcnow()
    token_hash = hash_password_reset_token(raw_token)
    if not raw_token or not token_hash:
        raise PasswordResetTokenInvalidError(PASSWORD_RESET_INVALID_MESSAGE)

    lock_suffix = " FOR UPDATE" if connection.dialect.name == "postgresql" else ""
    reset_row = connection.execute(
        text(
            f"SELECT id, user_id FROM {PASSWORD_RESET_TABLE} "
            "WHERE token_hash = :token_hash "
            "AND user_id IS NOT NULL "
            "AND used_at IS NULL "
            "AND invalidated_at IS NULL "
            "AND expires_at IS NOT NULL "
            "AND expires_at > :now"
            + lock_suffix
        ),
        {"token_hash": token_hash, "now": changed_at},
    ).mappings().first()
    if reset_row is None:
        raise PasswordResetTokenInvalidError(PASSWORD_RESET_INVALID_MESSAGE)

    user_id = str(reset_row["user_id"])
    selected = ["id", "email", "password"]
    if "password_hash" in schema["users"]:
        selected.append("password_hash")
    user_row = connection.execute(
        text(
            f"SELECT {', '.join(selected)} FROM app_users "
            "WHERE id = :user_id LIMIT 1"
        ),
        {"user_id": user_id},
    ).mappings().first()
    if user_row is None:
        raise PasswordResetTokenInvalidError(PASSWORD_RESET_INVALID_MESSAGE)

    encoded_password = hash_password(new_password)
    assignments = ["password = :password"]
    parameters: dict[str, Any] = {
        "password": encoded_password,
        "user_id": user_id,
    }
    if "password_hash" in schema["users"]:
        assignments.append("password_hash = :password_hash")
        parameters["password_hash"] = encoded_password
    if "updated_at" in schema["users"]:
        assignments.append("updated_at = :updated_at")
        parameters["updated_at"] = changed_at

    connection.execute(
        text(f"UPDATE app_users SET {', '.join(assignments)} WHERE id = :user_id"),
        parameters,
    )
    connection.execute(
        text(
            f"UPDATE {PASSWORD_RESET_TABLE} "
            "SET used_at = :now WHERE id = :reset_id"
        ),
        {"now": changed_at, "reset_id": str(reset_row["id"])},
    )
    connection.execute(
        text(
            f"UPDATE {PASSWORD_RESET_TABLE} "
            "SET invalidated_at = :now "
            "WHERE user_id = :user_id AND id <> :reset_id "
            "AND used_at IS NULL AND invalidated_at IS NULL"
        ),
        {
            "now": changed_at,
            "user_id": user_id,
            "reset_id": str(reset_row["id"]),
        },
    )
    revoked = connection.execute(
        text(
            "UPDATE server_sessions SET revoked_at = :now "
            "WHERE user_id = :user_id AND revoked_at IS NULL"
        ),
        {"now": changed_at, "user_id": user_id},
    )

    return PasswordResetConfirmResult(
        user_id=user_id,
        email=str(user_row["email"]),
        revoked_sessions=max(int(revoked.rowcount or 0), 0),
    )
