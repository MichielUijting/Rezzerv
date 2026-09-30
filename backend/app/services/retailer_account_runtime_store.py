"""Runtime-only household-scoped retailer account sessions."""

from __future__ import annotations

from threading import RLock

from app.integrations.retailer_accounts.ah import AHAccountSession
from app.integrations.retailer_accounts.lidl import LidlAccountSession, LidlAuthAttempt

_lock = RLock()
_ah_sessions: dict[str, AHAccountSession] = {}
_lidl_sessions: dict[str, LidlAccountSession] = {}
_lidl_auth_attempts: dict[str, LidlAuthAttempt] = {}


def get_ah_session(household_id: str) -> AHAccountSession | None:
    with _lock:
        return _ah_sessions.get(str(household_id))


def set_ah_session(household_id: str, session: AHAccountSession) -> None:
    with _lock:
        _ah_sessions[str(household_id)] = session


def delete_ah_session(household_id: str) -> bool:
    with _lock:
        return _ah_sessions.pop(str(household_id), None) is not None


def ah_session_status(household_id: str) -> dict[str, object]:
    session = get_ah_session(household_id)
    if session is None:
        return {
            "provider": "ah",
            "connected": False,
            "persistence": "runtime_only",
        }
    return {
        "provider": "ah",
        "connected": True,
        "persistence": "runtime_only",
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
    }


def get_lidl_session(household_id: str) -> LidlAccountSession | None:
    with _lock:
        return _lidl_sessions.get(str(household_id))


def set_lidl_session(household_id: str, session: LidlAccountSession) -> None:
    with _lock:
        _lidl_sessions[str(household_id)] = session


def delete_lidl_session(household_id: str) -> bool:
    with _lock:
        return _lidl_sessions.pop(str(household_id), None) is not None


def set_lidl_auth_attempt(household_id: str, attempt: LidlAuthAttempt) -> None:
    with _lock:
        _lidl_auth_attempts[str(household_id)] = attempt


def get_lidl_auth_attempt(household_id: str) -> LidlAuthAttempt | None:
    with _lock:
        return _lidl_auth_attempts.get(str(household_id))


def delete_lidl_auth_attempt(household_id: str) -> bool:
    with _lock:
        return _lidl_auth_attempts.pop(str(household_id), None) is not None


def lidl_session_status(household_id: str) -> dict[str, object]:
    session = get_lidl_session(household_id)
    if session is None:
        return {
            "provider": "lidl",
            "connected": False,
            "persistence": "runtime_only",
        }
    return {
        "provider": "lidl",
        "connected": True,
        "persistence": "runtime_only",
        "country": session.country,
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
    }
