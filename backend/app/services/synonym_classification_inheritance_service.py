"""Transaction-scoped inheritance of official classifications across confirmed synonyms.

No household/stock identity is changed. The caller owns a single transaction;
conflicting confirmed values stay intact and are reported, never overwritten.
"""
from __future__ import annotations

from collections import defaultdict, deque
from uuid import uuid4

from sqlalchemy import bindparam, text

from app.services.article_classification_sync_monitor import record_sync_event


def _components(links, affected):
    adjacency = defaultdict(set)
    for left, right in links:
        adjacency[left].add(right)
        adjacency[right].add(left)
    visited = set()
    groups = []
    for start in sorted(affected):
        if start in visited:
            continue
        group = set()
        pending = deque([start])
        while pending:
            product_id = pending.popleft()
            if product_id in group:
                continue
            group.add(product_id)
            pending.extend(sorted(adjacency[product_id] - group))
        visited.update(group)
        groups.append(tuple(sorted(group)))
    return groups


def _rows(conn, sql, ids):
    return conn.execute(
        text(sql).bindparams(bindparam("ids", expanding=True)),
        {"ids": list(ids)},
    ).mappings().all()


def propagate_confirmed_classifications(conn, links, affected, actor_id):
    """Fill only missing values, with an independent conflict decision per taxonomy.

    The synonym-confirmation transaction already holds the global advisory lock
    before reading or changing any synonym links. This service never commits.
    """
    if not affected:
        return {"gpc_inherited": 0, "cbs_inherited": 0, "conflicts": []}
    report = {"gpc_inherited": 0, "cbs_inherited": 0, "conflicts": []}
    for group in _components(links, affected):
        # Lock the whole affected central group, not household articles.
        if conn.dialect.name == "postgresql":
            _rows(conn,
                  "SELECT id FROM global_products WHERE id IN :ids ORDER BY id FOR UPDATE",
                  group)
        gpc = _rows(conn, """
            SELECT global_product_id, brick_code, assignment_source, migrated_from
              FROM global_product_gpc_bricks
             WHERE global_product_id IN :ids
        """, group)
        cbs = _rows(conn, """
            SELECT cc.global_product_id, cc.cbs_code, cc.reference_version,
                   cc.version, cc.is_active, cc.confirmation_source
              FROM global_product_cbs_classifications cc
             WHERE cc.global_product_id IN :ids
        """, group)
        gpc_values = {row["brick_code"] for row in gpc if row["brick_code"]}
        cbs_values = {(row["cbs_code"], row["reference_version"])
                      for row in cbs if row["is_active"]}

        if len(gpc_values) > 1:
            report["conflicts"].append({"system": "GPC", "product_ids": list(group)})
            conflicting = sorted((row for row in gpc if row["brick_code"]),
                                 key=lambda row: (str(row["brick_code"]), str(row["global_product_id"])))
            first = conflicting[0]
            other = next(row for row in conflicting if row["brick_code"] != first["brick_code"])
            record_sync_event(
                conn, source_id=first["global_product_id"], target_id=other["global_product_id"],
                system="GPC", code=first["brick_code"], status="conflict",
                reason="Afwijkende bevestigde GS1-classificaties: gebruik de bestaande keuze-overlay.",
                actor_id=actor_id,
            )
        elif len(gpc_values) == 1:
            # Prefer a non-inherited assignment as provenance root.
            source = min(
                (row for row in gpc if row["brick_code"]),
                key=lambda row: (str(row["assignment_source"] or "") == "synonym_inherited",
                                 str(row["global_product_id"])),
            )
            source_id = (str(source["migrated_from"] or "").removeprefix("synonym:")
                         if source["assignment_source"] == "synonym_inherited"
                         else str(source["global_product_id"]))
            existing = {row["global_product_id"] for row in gpc}
            for target in group:
                if target in existing:
                    continue
                written = conn.execute(text("""
                    INSERT INTO global_product_gpc_bricks
                        (global_product_id, brick_code, assignment_source,
                         confidence, migrated_from, updated_at)
                    VALUES (:target, :code, 'synonym_inherited', 1.0,
                            :provenance, CURRENT_TIMESTAMP)
                    ON CONFLICT (global_product_id) DO NOTHING
                """), {"target": target, "code": source["brick_code"],
                       "provenance": "synonym:" + source_id})
                if written.rowcount:
                    record_sync_event(
                        conn, source_id=source["global_product_id"], target_id=target, system="GPC",
                        code=source["brick_code"], status="processed",
                        reason="Automatisch overgenomen uit bevestigde synoniemgroep.",
                        actor_id=actor_id,
                    )
                report["gpc_inherited"] += written.rowcount

        if len(cbs_values) > 1:
            report["conflicts"].append({"system": "CBS", "product_ids": list(group)})
            conflicting = sorted((row for row in cbs if row["is_active"]),
                                 key=lambda row: (str(row["cbs_code"]), str(row["reference_version"]),
                                                  str(row["global_product_id"])))
            first = conflicting[0]
            other = next(row for row in conflicting if
                         (row["cbs_code"], row["reference_version"]) !=
                         (first["cbs_code"], first["reference_version"]))
            record_sync_event(
                conn, source_id=first["global_product_id"], target_id=other["global_product_id"],
                system="CBS", code=first["cbs_code"], reference=first["reference_version"],
                decision_version=int(first["version"]), status="conflict",
                reason="Afwijkende bevestigde CBS-classificaties: gebruik de bestaande keuze-overlay.",
                actor_id=actor_id,
            )
        elif len(cbs_values) == 1:
            code, version_name = next(iter(cbs_values))
            source = min(
                (row for row in cbs if row["is_active"]),
                key=lambda row: (str(row["confirmation_source"] or "").startswith("synonym:"),
                                 str(row["global_product_id"])),
            )
            # Existing active assignments must still be official leaves.
            official = conn.execute(text("""
                SELECT 1 FROM cbs_ecoicop_categories parent
                 WHERE parent.cbs_code = :code
                   AND parent.reference_version = :reference
                   AND NOT EXISTS (
                     SELECT 1 FROM cbs_ecoicop_categories child
                      WHERE child.parent_code = parent.cbs_code
                        AND child.reference_version = parent.reference_version
                   )
            """), {"code": code, "reference": version_name}).first()
            if not official:
                report["conflicts"].append({"system": "CBS-reference",
                                            "product_ids": list(group)})
                record_sync_event(
                    conn, source_id=source["global_product_id"],
                    target_id=next((pid for pid in group if pid != source["global_product_id"]),
                                   source["global_product_id"]),
                    system="CBS", code=code, reference=version_name,
                    decision_version=int(source["version"]), status="review_required",
                    reason="De bestaande CBS-code is geen actuele officiële eindcategorie.",
                    actor_id=actor_id,
                )
                continue
            provenance = str(source["confirmation_source"] or "")
            source_id = (provenance.removeprefix("synonym:")
                         if provenance.startswith("synonym:")
                         else str(source["global_product_id"]))
            current = {row["global_product_id"]: row for row in cbs}
            for target in group:
                row = current.get(target)
                if row and row["is_active"]:
                    continue
                next_version = int(row["version"]) + 1 if row else 1
                params = {
                    "id": target, "code": code, "reference": version_name,
                    "version": next_version, "actor": str(actor_id),
                    "source": "synonym:" + source_id, "history_id": str(uuid4()),
                }
                if row:
                    conn.execute(text("""
                        UPDATE global_product_cbs_classifications
                           SET cbs_code=:code, reference_version=:reference,
                               version=:version, is_active=TRUE,
                               confirmed_by=:actor, confirmation_source=:source,
                               confirmed_at=CURRENT_TIMESTAMP
                         WHERE global_product_id=:id AND is_active=FALSE
                    """), params)
                else:
                    conn.execute(text("""
                        INSERT INTO global_product_cbs_classifications
                            (global_product_id, cbs_code, reference_version,
                             version, is_active, confirmed_by, confirmation_source)
                        VALUES (:id, :code, :reference, :version, TRUE, :actor, :source)
                    """), params)
                conn.execute(text("""
                    INSERT INTO global_product_cbs_history
                        (id, global_product_id, cbs_code, reference_version,
                         version, action, confirmed_by, confirmation_source)
                    VALUES (:history_id, :id, :code, :reference, :version,
                            'confirmed', :actor, :source)
                """), params)
                record_sync_event(
                    conn, source_id=source["global_product_id"], target_id=target, system="CBS",
                    code=code, reference=version_name, decision_version=next_version,
                    status="processed",
                    reason="Automatisch overgenomen uit bevestigde synoniemgroep.",
                    actor_id=actor_id,
                )
                report["cbs_inherited"] += 1
    return report
