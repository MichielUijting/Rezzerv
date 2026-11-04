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
                      operation="synonym_inheritance", related_event_id=None):
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
        "related_event_id": str(related_event_id or ""),
    }
    fingerprint = sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    result = conn.execute(text("""
        INSERT INTO article_classification_sync_events (
            id, event_key, source_product_id, target_product_id,
            classification_system, classification_code, reference_version,
            decision_version, status, reason, actor_id, related_event_id
        ) VALUES (
            :id, :key, :source, :target, :system, :code, :reference,
            :version, :status, :reason, :actor, :related
        ) ON CONFLICT (event_key) DO NOTHING
    """), {**data, "id": str(uuid4()), "key": fingerprint,
           "actor": str(actor_id), "reason": str(reason),
           "related": str(related_event_id) if related_event_id else None})
    return bool(result.rowcount)


def list_sync_exceptions(conn, *, limit=100, offset=0):
    """Internal monitor; not a fourth user-facing work area."""
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Ongeldige paginering.")
    total = conn.execute(text("""
        SELECT COUNT(*) FROM article_classification_sync_events
        WHERE status IN ('conflict', 'failed', 'review_required')
          AND NOT EXISTS (
            SELECT 1 FROM article_classification_sync_events resolution
             WHERE resolution.related_event_id = article_classification_sync_events.id
               AND resolution.status = 'processed'
          )
    """)).scalar_one()
    rows = conn.execute(text("""
        SELECT id, source_product_id, target_product_id,
               classification_system, classification_code, reference_version,
               decision_version, status, reason, actor_id, created_at
          FROM article_classification_sync_events
         WHERE status IN ('conflict', 'failed', 'review_required')
           AND NOT EXISTS (
             SELECT 1 FROM article_classification_sync_events resolution
              WHERE resolution.related_event_id = article_classification_sync_events.id
                AND resolution.status = 'processed'
           )
         ORDER BY created_at DESC, id DESC
         LIMIT :limit OFFSET :offset
    """), {"limit": limit, "offset": offset}).mappings().all()
    return {
        "items": [{**row, "created_at": row["created_at"].isoformat()
                   if row["created_at"] else None} for row in rows],
        "total": int(total), "count_scope": "audit_events",
    }


def retry_sync_exception(conn, *, event_id, expected_decision_version,
                         expected_target_version, expected_target_code, actor_id):
    """Explicit, idempotent retry of a verified exception under canonical locks.

    Never processes conflicts: those require the existing user choice overlay.
    Never retries on names, GTIN, household, inventory or receipt evidence.
    """
    from fastapi import HTTPException
    from app.services.article_synonym_service import confirmed_pairs
    from app.services.synonym_classification_inheritance_service import (
        _components, propagate_confirmed_classifications,
    )

    if conn.dialect.name == "postgresql":
        conn.execute(text("SELECT pg_advisory_xact_lock(639643644)"))
    event = conn.execute(text("""
        SELECT id, source_product_id, target_product_id, classification_system,
               classification_code, reference_version, decision_version, status
          FROM article_classification_sync_events WHERE id=:id FOR UPDATE
    """), {"id": event_id}).mappings().first()
    if not event:
        raise HTTPException(404, "Synchronisatie-uitzondering niet gevonden.")
    if event["status"] == "conflict":
        raise HTTPException(409, "Kies de prevalerende classificatie via Artikel-synoniemen.")
    if event["status"] not in ("review_required", "failed"):
        raise HTTPException(409, "Alleen een echte uitzondering kan opnieuw worden verwerkt.")
    if int(event["decision_version"]) != expected_decision_version:
        raise HTTPException(409, "De beslisversie is gewijzigd; ververs de uitzondering.")

    source_id = str(event["source_product_id"])
    target_id = str(event["target_product_id"])
    links = confirmed_pairs(conn)
    groups = _components(links, {source_id})
    group = next((set(participants) for participants in groups if source_id in participants), set())
    if target_id not in group or source_id == target_id:
        raise HTTPException(409, "Bevestigde synoniemrelatie is gewijzigd; opnieuw beoordelen.")
    rows = conn.execute(text("""
        SELECT id FROM global_products WHERE id IN (:source, :target)
          AND LOWER(COALESCE(status, '')) <> 'deleted' FOR UPDATE
    """), {"source": source_id, "target": target_id}).scalars().all()
    if set(rows) != {source_id, target_id}:
        raise HTTPException(409, "Centrale artikelidentiteit is niet meer geldig.")

    system = event["classification_system"]
    if system == "CBS":
        source = conn.execute(text("""
            SELECT cbs_code, reference_version, version FROM global_product_cbs_classifications
            WHERE global_product_id=:id AND is_active=TRUE FOR UPDATE
        """), {"id": source_id}).mappings().first()
        if (not source or source["cbs_code"] != event["classification_code"]
                or source["reference_version"] != event["reference_version"]
                or int(source["version"]) != expected_decision_version):
            raise HTTPException(409, "CBS-code of -versie is gewijzigd; opnieuw beoordelen.")
    else:
        code = conn.execute(text("""
            SELECT brick_code FROM global_product_gpc_bricks
            WHERE global_product_id=:id FOR UPDATE
        """), {"id": source_id}).scalar_one_or_none()
        if code != event["classification_code"]:
            raise HTTPException(409, "GS1-code is gewijzigd; opnieuw beoordelen.")

    # Optimistic target snapshot: row locks alone would allow retrying after
    # a changed target was cleared. Require explicit expected target state.
    if system == "CBS":
        target = conn.execute(text("""
            SELECT cbs_code, version, is_active
            FROM global_product_cbs_classifications
            WHERE global_product_id=:id FOR UPDATE
        """), {"id": target_id}).mappings().first()
        current_version = int(target["version"]) if target else 0
        current_code = str(target["cbs_code"]) if target and target["is_active"] else ""
    else:
        target = conn.execute(text("""
            SELECT brick_code FROM global_product_gpc_bricks
            WHERE global_product_id=:id FOR UPDATE
        """), {"id": target_id}).scalar_one_or_none()
        current_version = 0
        current_code = str(target or "")
    if current_version != expected_target_version or current_code != expected_target_code:
        raise HTTPException(409, "Doelclassificatie gewijzigd: ververs de uitzondering.")

    record_sync_event(
        conn, source_id=source_id, target_id=target_id,
        system=system, code=event["classification_code"],
        reference=event["reference_version"], decision_version=expected_decision_version,
        status="pending", reason="Expliciete geautoriseerde herverwerking gestart.",
        actor_id=actor_id, operation="retry:" + str(event_id),
    )
    report = propagate_confirmed_classifications(
        conn, links, {source_id, target_id}, actor_id
    )
    if report["conflicts"]:
        # Roll back even independent writes; choice overlay is the only path
        # for conflicting existing confirmed classifications.
        raise HTTPException(409, "Classificatieverschil: gebruik de keuze-overlay in Artikel-synoniemen.")
    record_sync_event(
        conn, source_id=source_id, target_id=target_id,
        system=system, code=event["classification_code"],
        reference=event["reference_version"], decision_version=expected_decision_version,
        status="processed", reason="Geautoriseerde herverwerking afgerond; versie gecontroleerd.",
        actor_id=actor_id, operation="retry:" + str(event_id), related_event_id=event_id,
    )
    return {"status": "processed", "gpc_inherited": report["gpc_inherited"],
            "cbs_inherited": report["cbs_inherited"], "event_id": str(event_id)}
