"""Deliberate session sign-out during an announced maintenance window.

Session revocation prevents subsequent authenticated requests. It cannot cancel
already admitted domain operations; the normal maintenance drain remains the
sole authority for safely closing those operations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .maintenance_state_contract import MaintenanceTransitionError

MINIMUM_NOTICE = timedelta(minutes=2)


def revoke_remaining_sessions(
    conn: Connection,
    *,
    expected_generation: int,
    current_session_id: str,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict:
    """Revoke other unexpired sessions, atomically, after a durable warning.

    The caller must separately prove both recovery and session-revoke rights.
    This operation does not transition maintenance state or remove operations.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Tijd zonder tijdzone is niet toegestaan")
    control = conn.execute(text(
        "SELECT state,generation FROM maintenance_control WHERE id=1 FOR UPDATE"
    )).mappings().one()
    if int(control["generation"]) != expected_generation:
        raise MaintenanceTransitionError("Onderhoudstoestand is gewijzigd; vernieuw de pagina")
    if control["state"] not in {"announced", "draining"}:
        raise MaintenanceTransitionError("Kondig onderhoud eerst aan")

    announced = conn.execute(text("""
        SELECT created_at FROM maintenance_audit
        WHERE action='announce' AND generation<=:generation
        ORDER BY created_at DESC, id DESC LIMIT 1
    """), {"generation": expected_generation}).scalar_one_or_none()
    if announced is None:
        raise MaintenanceTransitionError("Er is geen geldige onderhoudsaankondiging")
    if announced.tzinfo is None:
        raise MaintenanceTransitionError("Aankondiging mist tijdzone")
    if current.astimezone(timezone.utc) - announced.astimezone(timezone.utc) < MINIMUM_NOTICE:
        raise MaintenanceTransitionError("Wacht minimaal twee minuten na de aankondiging")

    if not current_session_id or not actor_user_id:
        raise MaintenanceTransitionError("De beheersessie is niet eenduidig")

    result = conn.execute(text("""
        UPDATE server_sessions
        SET revoked_at=:now, updated_at=:now
        WHERE id<>:current_session_id
          AND revoked_at IS NULL AND expires_at>:now
    """), {"now": current, "current_session_id": current_session_id})
    count = int(result.rowcount)
    conn.execute(text("""
        INSERT INTO maintenance_audit(id,generation,actor_user_id,action,evidence_json)
        VALUES (:id,:generation,:actor,'revoke_sessions',:evidence)
    """), {
        "id": str(uuid4()), "generation": expected_generation,
        "actor": actor_user_id, "evidence": json.dumps({"revoked_count": count}),
    })
    return {"sessions_revoked": count, "current_session_preserved": True,
            "operations_untouched": True}
