"""Household-scoped encrypted Picnic auth state, isolated from AH credentials.

Only Picnic auth keys are stored. Never store email/password or sms code.
The existing retailer_account_credentials table and Fernet key are reused.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import InvalidToken
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.services.retailer_account_secure_store import _fernet


_PROVIDER = "picnic"


def save_picnic_auth(engine: Engine, household_id: str, auth_key: str, *, pending_2fa: bool) -> None:
    if not str(household_id or "").strip() or not isinstance(auth_key, str) or not auth_key:
        raise ValueError("Picnic-accountcontext is ongeldig")
    plaintext = json.dumps({
        "auth_key": auth_key,
        "pending_2fa": bool(pending_2fa),
        "pending_until": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat() if pending_2fa else None,
    }, separators=(",", ":"))
    ciphertext = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO retailer_account_credentials(
                household_id, provider, credential_ciphertext, updated_at
            ) VALUES (:household_id, :provider, :ciphertext, CURRENT_TIMESTAMP)
            ON CONFLICT(household_id, provider) DO UPDATE SET
                credential_ciphertext = excluded.credential_ciphertext,
                expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
        """), {"household_id": str(household_id), "provider": _PROVIDER, "ciphertext": ciphertext})


def get_picnic_auth(engine: Engine, household_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        value = conn.execute(text("""
            SELECT credential_ciphertext FROM retailer_account_credentials
            WHERE household_id = :household_id AND provider = :provider
        """), {"household_id": str(household_id), "provider": _PROVIDER}).scalar_one_or_none()
    if value is None:
        return None
    try:
        payload = json.loads(_fernet().decrypt(str(value).encode("ascii")).decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise RuntimeError("Picnic-accountgegevens konden niet veilig worden gelezen") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("auth_key"), str) or not payload["auth_key"]:
        raise RuntimeError("Picnic-accountgegevens zijn ongeldig")
    if not isinstance(payload.get("pending_2fa"), bool):
        raise RuntimeError("Picnic-verificatiestatus is ongeldig")
    if payload["pending_2fa"]:
        until = payload.get("pending_until")
        try:
            deadline = datetime.fromisoformat(str(until))
            if deadline.tzinfo is None or datetime.now(timezone.utc) >= deadline:
                return None
        except (ValueError, TypeError):
            return None
    return payload


def delete_picnic_auth(engine: Engine, household_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM retailer_account_credentials
            WHERE household_id = :household_id AND provider = :provider
        """), {"household_id": str(household_id), "provider": _PROVIDER})


def picnic_status(engine: Engine, household_id: str) -> dict[str, Any]:
    auth = get_picnic_auth(engine, household_id)
    return {
        "provider": _PROVIDER,
        "connected": auth is not None and not auth["pending_2fa"],
        "verification_required": auth is not None and auth["pending_2fa"],
        "persistence": "encrypted_database",
        "receipt_import_enabled": False,
    }
