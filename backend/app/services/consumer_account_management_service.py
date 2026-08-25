from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from app.services.password_service import hash_password, verify_password
from app.services.server_session_service import ensure_server_session_schema


class ConsumerAccountNotFoundError(LookupError):
    pass


class ConsumerCurrentPasswordMismatchError(ValueError):
    pass


class ConsumerPasswordReuseError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def change_consumer_password(
    conn: Connection,
    *,
    user_id: str,
    current_session_id: str,
    current_password: str,
    new_password: str,
    now: datetime | None = None,
) -> dict[str, int | bool]:
    """Change one consumer password and revoke every other active session.

    ``app_users`` remains the canonical identity store. New and migrated
    accounts keep the v2 PBKDF2 hash in ``password`` and, when the transition
    column exists, mirror the same value in ``password_hash``. The caller's
    current server session remains valid so a successful change does not log
    the user out of the browser that performed it.
    """

    normalized_user_id = str(user_id or "").strip()
    normalized_session_id = str(current_session_id or "").strip()
    if not normalized_user_id:
        raise ConsumerAccountNotFoundError("Account bestaat niet")
    if not normalized_session_id:
        raise ValueError("Huidige sessie ontbreekt")

    user_columns = {
        str(column.get("name") or "").strip().lower()
        for column in inspect(conn).get_columns("app_users")
    }
    if "id" not in user_columns or "password" not in user_columns:
        raise RuntimeError("app_users mist de vereiste accountkolommen")

    password_hash_expression = "password_hash" if "password_hash" in user_columns else "NULL"
    account = conn.execute(text(f"""
        SELECT id, password, {password_hash_expression} AS password_hash
        FROM app_users
        WHERE id = :user_id
        LIMIT 1
    """), {"user_id": normalized_user_id}).mappings().first()
    if account is None:
        raise ConsumerAccountNotFoundError("Account bestaat niet")

    if not verify_password(
        account.get("password"),
        current_password,
        stored_password_hash=account.get("password_hash"),
    ):
        raise ConsumerCurrentPasswordMismatchError("Huidig wachtwoord is onjuist")

    if verify_password(
        account.get("password"),
        new_password,
        stored_password_hash=account.get("password_hash"),
    ):
        raise ConsumerPasswordReuseError("Nieuw wachtwoord moet verschillen van het huidige wachtwoord")

    encoded_password = hash_password(new_password)
    assignments = ["password = :password"]
    params: dict[str, object] = {
        "password": encoded_password,
        "user_id": normalized_user_id,
    }
    if "password_hash" in user_columns:
        assignments.append("password_hash = :password_hash")
        params["password_hash"] = encoded_password
    current = (now or utc_now()).astimezone(timezone.utc)
    if "updated_at" in user_columns:
        assignments.append("updated_at = :updated_at")
        params["updated_at"] = current

    conn.execute(text(f"""
        UPDATE app_users
        SET {', '.join(assignments)}
        WHERE id = :user_id
    """), params)

    ensure_server_session_schema(conn)
    revoked = conn.execute(text("""
        UPDATE server_sessions
        SET revoked_at = :now,
            updated_at = :now
        WHERE user_id = :user_id
          AND id <> :current_session_id
          AND revoked_at IS NULL
          AND expires_at > :now
    """), {
        "now": current,
        "user_id": normalized_user_id,
        "current_session_id": normalized_session_id,
    })

    return {
        "password_updated": True,
        "other_active_sessions_revoked": int(revoked.rowcount or 0),
    }
