"""Immutable, transaction-bound synchronization evidence for confirmed article synonyms."""
from __future__ import annotations

from hashlib import sha256
from uuid import uuid4
import json

from sqlalchemy import text

STATUSES = frozenset({"pending", "processed", "conflict", "failed", "review_required"})
SYSTEMS = frozenset({"GPC", "CBS"})


def record_sync_event(conn, *, source_id, target_id, system, code,
                      reference="", decision_version=0, status, reason, actor_id,
                      operation="synonym_inheritance"):
    """Append one event per exact action/version, with repeat-safe uniqueness.

    Caller owns the transaction: a failure rolls back both classification and
    event. Duplicate retries cannot create duplicate evidence.
    """
    if system not in SYSTEMS or status not in STATUSES or int(decision_version) < 0:
        raise ValueError("Ongeldig synchronisatie-event.")
    if not source_id or not target_id or not actor_id or not reason:
        raise ValueError("Synchronisatie-event mist canonieke bewijsvelden.")
    data = {
        "source": str(source_id), "target": str(target_id),
        "system": system, "code": str(code or ""),
        "reference": str(reference or ""), "version": int(decision_version),
        "status": status, "operation": operation,
    }
    fingerprint = sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    result = conn.execute(text("""
        INSERT INTO article_classification_sync_events (
            id, event_key, source_product_id, target_product_id,
            classification_system, classification_code, reference_version,
            decision_version, status, reason, actor_id
        ) VALUES (
            :id, :key, :source, :target, :system, :code, :reference,
            :version, :status, :reason, :actor
        ) ON CONFLICT (event_key) DO NOTHING
    """), {**data, "id": str(uuid4()), "key": fingerprint,
           "actor": str(actor_id), "reason": str(reason)})
    return bool(result.rowcount)


def list_sync_exceptions(conn, *, limit=100, offset=0):
    """Internal monitor; not a fourth user-facing work area."""
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Ongeldige paginering.")
    total = conn.execute(text("""
        SELECT COUNT(*) FROM article_classification_sync_events
        WHERE status IN ('conflict', 'failed', 'review_required')
    """)).scalar_one()
    rows = conn.execute(text("""
        SELECT id, source_product_id, target_product_id,
               classification_system, classification_code, reference_version,
               decision_version, status, reason, actor_id, created_at
          FROM article_classification_sync_events
         WHERE status IN ('conflict', 'failed', 'review_required')
         ORDER BY created_at DESC, id DESC
         LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).mappings().all()
    return {
        "items": [{**row, "created_at": row["created_at"].isoformat()
                   if row["created_at"] else None} for row in rows],
        "total": int(total), "count_scope": "audit_events",
    }
