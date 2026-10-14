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
        "sms_last_requested": None,
        "sms_request_count": 0,
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


def reserve_picnic_sms_request(engine: Engine, household_id: str) -> str:
    """Atomic, fail-closed SMS throttle across concurrent app workers.

    Reserve before calling Picnic to avoid sending multiple codes due to
    duplicate clicks or repeated requests. No OTP or token leaves storage.
    """
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT credential_ciphertext FROM retailer_account_credentials
            WHERE household_id = :household_id AND provider = :provider
        """), {"household_id": str(household_id), "provider": _PROVIDER}).scalar_one_or_none()
        if not row:
            raise ValueError("Geen geldige Picnic-sms-verificatie actief.")
        try:
            state = json.loads(_fernet().decrypt(str(row).encode("ascii")).decode("utf-8"))
            deadline = datetime.fromisoformat(str(state["pending_until"]))
            last_text = state.get("sms_last_requested")
            last = datetime.fromisoformat(last_text) if last_text else None
        except (InvalidToken, ValueError, TypeError, KeyError, json.JSONDecodeError):
            raise ValueError("Picnic-sms-sessie is ongeldig.") from None
        if not state.get("pending_2fa") or deadline.tzinfo is None or now >= deadline:
            raise ValueError("Picnic-sms-sessie is verlopen.")
        if int(state.get("sms_request_count", 0)) >= 3:
            raise ValueError("Maximum aantal sms-aanvragen bereikt. Meld opnieuw aan.")
        if last is not None and (last.tzinfo is None or (now - last).total_seconds() < 60):
            raise ValueError("Wacht minimaal één minuut voordat je opnieuw een code aanvraagt.")
        token = state.get("auth_key")
        if not isinstance(token, str) or not token:
            raise ValueError("Picnic-sms-sessie is ongeldig.")
        state["sms_last_requested"] = now.isoformat()
        state["sms_request_count"] = int(state.get("sms_request_count", 0)) + 1
        next_cipher = _fernet().encrypt(json.dumps(state, separators=(",", ":")).encode("utf-8")).decode("ascii")
        updated = conn.execute(text("""
            UPDATE retailer_account_credentials SET
                credential_ciphertext = :next_cipher, updated_at = CURRENT_TIMESTAMP
            WHERE household_id = :household_id AND provider = :provider
              AND credential_ciphertext = :prior_cipher
        """), {
            "next_cipher": next_cipher,
            "household_id": str(household_id),
            "provider": _PROVIDER,
            "prior_cipher": str(row),
        })
        if updated.rowcount != 1:
            raise ValueError("Er loopt al een Picnic-sms-aanvraag. Probeer later opnieuw.")
    return token


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
