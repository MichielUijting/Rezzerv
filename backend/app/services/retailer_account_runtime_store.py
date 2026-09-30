"""Runtime-only household-scoped retailer account sessions."""

from __future__ import annotations

from threading import RLock

from app.integrations.retailer_accounts.ah import AHAccountSession

_lock = RLock()
_ah_sessions: dict[str, AHAccountSession] = {}


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
