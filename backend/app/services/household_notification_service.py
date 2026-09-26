from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import inspect, text

ALLOWED_SEVERITIES = frozenset({"info", "success", "attention", "action"})
REQUIRED_COLUMNS = {"id","household_id","recipient_user_id","category","severity","title","message","target_route","source_type","source_key","read_at","created_at"}

class HouseholdNotificationError(RuntimeError):
    pass

def ensure_household_notification_foundation(conn) -> None:
    inspector = inspect(conn)
    if "household_notifications" not in set(inspector.get_table_names()):
        raise RuntimeError("Canonical household notification schema ontbreekt")
    columns = {c["name"] for c in inspector.get_columns("household_notifications")}
    missing = sorted(REQUIRED_COLUMNS - columns)
    if missing:
        raise RuntimeError("household_notifications schema drift: " + ", ".join(missing))

def publish_household_notification(conn, *, household_id, category, title, message, source_type, source_key=None, severity="info", target_route=None, recipient_user_id=None):
    ensure_household_notification_foundation(conn)
    if severity not in ALLOWED_SEVERITIES:
        raise HouseholdNotificationError("Onbekende meldingsprioriteit")
    notification_id = str(uuid.uuid4())
    params = {
        "id": notification_id, "household_id": str(household_id), "recipient_user_id": str(recipient_user_id) if recipient_user_id else None,
        "category": str(category).strip(), "severity": severity, "title": str(title).strip(), "message": str(message).strip(),
        "target_route": str(target_route).strip() if target_route else None, "source_type": str(source_type).strip(),
        "source_key": str(source_key).strip() if source_key else None,
    }
    if not params["category"] or not params["title"] or not params["message"] or not params["source_type"]:
        raise HouseholdNotificationError("Categorie, titel, bericht en bron zijn verplicht")
    if params["source_key"]:
        existing = conn.execute(text("""
            SELECT id FROM household_notifications
            WHERE household_id=:household_id
              AND ((recipient_user_id IS NULL AND :recipient_user_id IS NULL) OR recipient_user_id=:recipient_user_id)
              AND source_type=:source_type AND source_key=:source_key
            LIMIT 1
        """), params).scalar()
        if existing:
            return str(existing)
    conn.execute(text("""
        INSERT INTO household_notifications(
            id, household_id, recipient_user_id, category, severity, title, message,
            target_route, source_type, source_key, read_at, created_at
        ) VALUES (
            :id, :household_id, :recipient_user_id, :category, :severity, :title, :message,
            :target_route, :source_type, :source_key, NULL, CURRENT_TIMESTAMP
        )
    """), params)
    return notification_id

def list_household_notifications(conn, *, household_id, user_id):
    ensure_household_notification_foundation(conn)
    return [dict(row) for row in conn.execute(text("""
        SELECT id, category, severity, title, message, target_route, source_type, source_key, read_at, created_at
        FROM household_notifications
        WHERE household_id=:household_id
          AND (recipient_user_id IS NULL OR recipient_user_id=:user_id)
        ORDER BY created_at DESC, id DESC
    """), {"household_id": str(household_id), "user_id": str(user_id)}).mappings().all()]

def mark_household_notification_read(conn, *, notification_id, household_id, user_id):
    ensure_household_notification_foundation(conn)
    result = conn.execute(text("""
        UPDATE household_notifications SET read_at=:read_at
        WHERE id=:id AND household_id=:household_id
          AND (recipient_user_id IS NULL OR recipient_user_id=:user_id)
    """), {"id": str(notification_id), "household_id": str(household_id), "user_id": str(user_id), "read_at": datetime.now(timezone.utc).isoformat()})
    if result.rowcount != 1:
        raise HouseholdNotificationError("Melding niet gevonden")
