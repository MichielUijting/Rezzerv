"""Explicit, optimistic classification choice for two central synonym articles."""
from __future__ import annotations

from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import inspect, text

from app.services.article_classification_sync_monitor import record_sync_event


def _classification(conn, product_id):
    gpc = conn.execute(text("SELECT brick_code FROM global_product_gpc_bricks WHERE global_product_id=:id"),
                       {"id": product_id}).scalar_one_or_none() or ""
    cbs = conn.execute(text("""
        SELECT cbs_code, reference_version, version
        FROM global_product_cbs_classifications
        WHERE global_product_id=:id AND is_active=TRUE
    """), {"id": product_id}).mappings().first()
    gpc_label = ""
    if gpc and inspect(conn).has_table("gpc_product_groups"):
        gpc_label = conn.execute(text("""
            SELECT gpc_brick_name FROM gpc_product_groups
            WHERE gpc_brick_code=:code AND language_code='nl' AND active=TRUE LIMIT 1
        """), {"code": gpc}).scalar_one_or_none() or ""
    cbs_label = ""
    if cbs:
        cbs_label = conn.execute(text("""
            SELECT name_nl FROM cbs_ecoicop_categories
            WHERE cbs_code=:code AND reference_version=:ref
        """), {"code": cbs["cbs_code"], "ref": cbs["reference_version"]}).scalar_one_or_none() or ""
    return {
        "GPC": {"code": str(gpc), "label": str(gpc_label or gpc)},
        "CBS": {"code": str(cbs["cbs_code"]) if cbs else "",
                "label": str(cbs_label or cbs["cbs_code"]) if cbs else "",
                "reference": str(cbs["reference_version"]) if cbs else "",
                "version": int(cbs["version"]) if cbs else 0},
    }


def review_pairs(conn, selections, by_id):
    """Both source labels and codes from the DB, not client assertions."""
    result = []
    for choice in selections:
        ids = (choice["left_product_id"], choice["right_product_id"])
        if ids[0] >= ids[1] or any(pid not in by_id for pid in ids):
            raise HTTPException(409, "Catalogusartikel is gewijzigd. Vernieuw de selectie.")
        values = [_classification(conn, pid) for pid in ids]
        clashes = []
        for system in ("GPC", "CBS"):
            a, b = [row[system] for row in values]
            if a["code"] and b["code"] and (a["code"], a.get("reference")) != (b["code"], b.get("reference")):
                clashes.append({"system": system,
                                "left": {"id": ids[0], "name": by_id[ids[0]]["name"], **a},
                                "right": {"id": ids[1], "name": by_id[ids[1]]["name"], **b}})
        state = [*ids, values, str(choice.get("fingerprint") or "")]
        token = sha256(json.dumps(state, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        result.append({"left_id": ids[0], "right_id": ids[1], "clashes": clashes, "snapshot": token})
    return result


def apply_choices(conn, reviews, decisions, actor_id):
    """Apply ONLY the explicitly selected existing official code of one side.

    Decisions are rechecked against current DB state within the synonym
    transaction. Both GPC and CBS have independent selection and audit.
    """
    conflicts = {(r["left_id"], r["right_id"]): r for r in reviews if r["clashes"]}
    choices = {(d["left_product_id"], d["right_product_id"]): d for d in decisions}
    if len(decisions) != len(choices) or set(choices) != set(conflicts):
        raise HTTPException(409, "Kies voor alle afwijkende classificaties welke moet gelden.")
    # Multiple independent decisions may not write different source codes to
    # the same central product in one batch; ask for pairwise confirmation.
    if len({pid for pair in conflicts for pid in pair}) != 2 * len(conflicts):
        raise HTTPException(409, "Controleer conflicterende synoniemen één paar tegelijk.")
    report = {"gpc_resolved": 0, "cbs_resolved": 0}
    for pair, review in conflicts.items():
        decision = choices[pair]
        if decision.get("snapshot") != review["snapshot"]:
            raise HTTPException(409, "Classificatie gewijzigd: bekijk beide artikelen opnieuw.")
        for system in ("GPC", "CBS"):
            needed = any(c["system"] == system for c in review["clashes"])
            chosen = decision.get("gpc_source_id" if system == "GPC" else "cbs_source_id")
            if needed != bool(chosen) or (chosen and chosen not in pair):
                raise HTTPException(409, "Maak per classificatiesysteem een geldige expliciete keuze.")
        for clash in review["clashes"]:
            system = clash["system"]
            source_id = decision["gpc_source_id" if system == "GPC" else "cbs_source_id"]
            source = clash["left"] if source_id == pair[0] else clash["right"]
            target = clash["right"] if source_id == pair[0] else clash["left"]
            if system == "GPC":
                if not conn.execute(text("""
                    SELECT 1 FROM gpc_product_groups
                    WHERE gpc_brick_code=:code AND language_code='nl' AND active=TRUE LIMIT 1
                """), {"code": source["code"]}).first():
                    raise HTTPException(409, "De gekozen GS1 GPC Brick is niet officieel beschikbaar.")
                conn.execute(text("""
                    UPDATE global_product_gpc_bricks
                    SET brick_code=:code, assignment_source='synonym_review',
                        migrated_from=:source, confidence=1.0, updated_at=CURRENT_TIMESTAMP
                    WHERE global_product_id=:id
                """), {"code": source["code"], "source": "synonym:" + source_id, "id": target["id"]})
                record_sync_event(
                    conn, source_id=source_id, target_id=target["id"], system="GPC",
                    code=source["code"], status="processed",
                    reason="Handmatige prevalentie gekozen in Artikel-synoniemen.",
                    actor_id=actor_id, operation="explicit_synonym_review",
                )
                report["gpc_resolved"] += 1
            else:
                from app.services.cbs_classification_service import confirm_cbs_batch
                confirm_cbs_batch(conn, [{
                    "global_product_id": target["id"],
                    "expected_product_name": target["name"],
                    "cbs_code": source["code"],
                    "reference_version": source["reference"],
                    "expected_version": target["version"],
                }], actor_id=str(actor_id))
                # The existing CBS authority already wrote history; add the
                # chosen source in both current record and that exact history.
                provenance = "synonym_review:" + source_id
                conn.execute(text("""
                    UPDATE global_product_cbs_classifications
                    SET confirmation_source=:source WHERE global_product_id=:id
                """), {"source": provenance, "id": target["id"]})
                conn.execute(text("""
                    UPDATE global_product_cbs_history
                    SET confirmation_source=:source
                    WHERE global_product_id=:id AND version=:version
                      AND confirmation_source='explicit_manual_confirmation'
                """), {"source": provenance, "id": target["id"], "version": target["version"] + 1})
                record_sync_event(
                    conn, source_id=source_id, target_id=target["id"], system="CBS",
                    code=source["code"], reference=source["reference"],
                    decision_version=target["version"] + 1, status="processed",
                    reason="Handmatige prevalentie gekozen in Artikel-synoniemen.",
                    actor_id=actor_id, operation="explicit_synonym_review",
                )
                report["cbs_resolved"] += 1
    return report
