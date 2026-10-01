"""Encrypted persistent household-scoped retailer account storage."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.integrations.retailer_accounts.ah import AHAccountSession

_PROVIDER = "ah"
_KEY_ENV = "REZZERV_RETAILER_ACCOUNT_KEY"
_KEY_PATH_ENV = "REZZERV_RETAILER_ACCOUNT_KEY_PATH"
_DEFAULT_KEY_PATH = "/app/secrets/retailer_accounts.key"
_key_lock = RLock()
_cached_fernet: Fernet | None = None


def _fernet() -> Fernet:
    global _cached_fernet
    with _key_lock:
        if _cached_fernet is not None:
            return _cached_fernet

        configured = str(os.getenv(_KEY_ENV, "") or "").strip().encode("ascii")
        if configured:
            key = configured
        else:
            path = Path(os.getenv(_KEY_PATH_ENV, _DEFAULT_KEY_PATH))
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.parent.chmod(0o700)
            except OSError:
                pass
            if path.exists():
                key = path.read_bytes().strip()
            else:
                key = Fernet.generate_key()
                temp = path.with_suffix(path.suffix + ".tmp")
                temp.write_bytes(key + b"\n")
                try:
                    temp.chmod(0o600)
                except OSError:
                    pass
                os.replace(temp, path)
                try:
                    path.chmod(0o600)
                except OSError:
                    pass

        try:
            _cached_fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("REZZERV_RETAILER_ACCOUNT_KEY is geen geldige Fernet-sleutel") from exc
        return _cached_fernet


def _session_payload(session: AHAccountSession) -> bytes:
    return json.dumps(
        {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            "member_id": session.member_id,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _decode_session(ciphertext: str) -> AHAccountSession:
    try:
        raw = _fernet().decrypt(str(ciphertext).encode("ascii"))
    except InvalidToken as exc:
        raise RuntimeError("Opgeslagen AH-accountkoppeling kan niet worden ontsleuteld") from exc
    payload = json.loads(raw.decode("utf-8"))
    expires_at = None
    if payload.get("expires_at"):
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
    return AHAccountSession(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=expires_at,
        member_id=str(payload.get("member_id") or "").strip() or None,
    )


def save_ah_session(engine: Engine, household_id: str, session: AHAccountSession) -> None:
    ciphertext = _fernet().encrypt(_session_payload(session)).decode("ascii")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO retailer_account_credentials(
                    household_id, provider, credential_ciphertext, expires_at, updated_at
                )
                VALUES (:household_id, :provider, :credential_ciphertext, :expires_at, CURRENT_TIMESTAMP)
                ON CONFLICT(household_id, provider) DO UPDATE SET
                    credential_ciphertext = excluded.credential_ciphertext,
                    expires_at = excluded.expires_at,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "household_id": str(household_id),
                "provider": _PROVIDER,
                "credential_ciphertext": ciphertext,
                "expires_at": session.expires_at,
            },
        )


def get_ah_session(engine: Engine, household_id: str) -> AHAccountSession | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT credential_ciphertext
                FROM retailer_account_credentials
                WHERE household_id = :household_id AND provider = :provider
                LIMIT 1
                """
            ),
            {"household_id": str(household_id), "provider": _PROVIDER},
        ).mappings().first()
    if not row:
        return None
    return _decode_session(str(row["credential_ciphertext"]))


def delete_ah_session(engine: Engine, household_id: str) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                DELETE FROM retailer_account_credentials
                WHERE household_id = :household_id AND provider = :provider
                """
            ),
            {"household_id": str(household_id), "provider": _PROVIDER},
        )
        return bool(result.rowcount)


def get_known_ah_receipt_ids(engine: Engine, household_id: str) -> set[str]:
    with engine.begin() as conn:
        value = conn.execute(
            text(
                """
                SELECT known_receipt_ids_json
                FROM retailer_account_credentials
                WHERE household_id = :household_id AND provider = :provider
                LIMIT 1
                """
            ),
            {"household_id": str(household_id), "provider": _PROVIDER},
        ).scalar_one_or_none()
    try:
        values = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        values = []
    return {str(item) for item in values if str(item).strip()}


def mark_ah_receipts_synced(engine: Engine, household_id: str, receipt_ids: set[str]) -> None:
    existing = get_known_ah_receipt_ids(engine, household_id)
    merged = sorted(existing | {str(item) for item in receipt_ids if str(item).strip()})
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE retailer_account_credentials
                SET known_receipt_ids_json = :known_receipt_ids_json,
                    last_sync_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE household_id = :household_id AND provider = :provider
                """
            ),
            {
                "household_id": str(household_id),
                "provider": _PROVIDER,
                "known_receipt_ids_json": json.dumps(merged, separators=(",", ":")),
            },
        )


def touch_ah_sync(engine: Engine, household_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE retailer_account_credentials
                SET last_sync_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE household_id = :household_id AND provider = :provider
                """
            ),
            {"household_id": str(household_id), "provider": _PROVIDER},
        )


def ah_session_status(engine: Engine, household_id: str) -> dict[str, object]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT expires_at, last_sync_at
                FROM retailer_account_credentials
                WHERE household_id = :household_id AND provider = :provider
                LIMIT 1
                """
            ),
            {"household_id": str(household_id), "provider": _PROVIDER},
        ).mappings().first()
    if not row:
        return {"provider": "ah", "connected": False, "persistence": "encrypted_database"}
    expires_at = row.get("expires_at")
    last_sync_at = row.get("last_sync_at")
    return {
        "provider": "ah",
        "connected": True,
        "persistence": "encrypted_database",
        "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else expires_at,
        "last_sync_at": last_sync_at.isoformat() if hasattr(last_sync_at, "isoformat") else last_sync_at,
    }


def reset_retailer_account_key_cache_for_tests() -> None:
    global _cached_fernet
    with _key_lock:
        _cached_fernet = None
