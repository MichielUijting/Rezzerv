"""Read-only bonartikelprojectie en expliciet herstel van cataloguskoppelingen.

De leesfunctie in dit bestand voert uitsluitend SELECT-query's en projectie in
geheugen uit. Eventuele historische reparatie van bevestigde kandidaten is een
afzonderlijke, expliciete schrijfactie.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_article_ui_projection import (
    project_central_link_truth_rows,
)
from app.services.external_product_candidate_store import (
    _m2c2h5_list_purchase_import_placeholders,
    _m2c2i_fix2_apply_status_fields,
    _m2c2i_fix7a3_apply_catalog_status_to_placeholders,
    _m2c2i_fix7b_dedupe_top_receipt_items,
    _m2c2i_fix7b_ensure_catalog_products_for_article_codes,
    _m2c2l_enrich_linked_receipt_items,
    ensure_external_product_candidates_schema,
)


def list_external_receipt_items_read_only(limit: int = 500) -> dict[str, Any]:
    """Lees het bonartikelenoverzicht zonder databasewijzigingen."""

    normalized_limit = max(1, min(int(limit or 500), 500))

    with engine.connect() as conn:
        candidate_rows = conn.execute(
            text(
                """
                SELECT *
                FROM external_product_candidates
                ORDER BY updated_at DESC, score DESC
                LIMIT :limit
                """
            ),
            {"limit": normalized_limit},
        ).mappings().all()

        candidates = [dict(row) for row in candidate_rows]
        existing_context_keys = {
            str(row.get("context_key") or "").strip()
            for row in candidates
            if str(row.get("context_key") or "").strip()
        }
        placeholders = _m2c2h5_list_purchase_import_placeholders(
            conn,
            existing_context_keys,
            normalized_limit,
        )
        placeholders = _m2c2i_fix7a3_apply_catalog_status_to_placeholders(
            placeholders,
            candidates,
        )
        placeholders = _m2c2l_enrich_linked_receipt_items(conn, placeholders)

        combined = _m2c2i_fix7b_dedupe_top_receipt_items(placeholders)
        enriched = _m2c2i_fix2_apply_status_fields(
            [dict(row) for row in combined]
        )
        projected = project_central_link_truth_rows(conn, enriched)
        items = _m2c2i_fix7b_dedupe_top_receipt_items(projected)

    return {
        "items": items[:normalized_limit],
        "candidate_rows": len(candidates),
        "purchase_import_line_rows": len(placeholders),
        "total": len(items[:normalized_limit]),
        "read_only": True,
    }


def repair_confirmed_external_catalog_links(limit: int = 500) -> dict[str, Any]:
    """Voer het voormalige impliciete herstel uitsluitend expliciet uit."""

    normalized_limit = max(1, min(int(limit or 500), 500))
    ensure_external_product_candidates_schema()

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM external_product_candidates
                ORDER BY updated_at DESC, score DESC
                LIMIT :limit
                """
            ),
            {"limit": normalized_limit},
        ).mappings().all()
        candidates = [dict(row) for row in rows]
        repaired = _m2c2i_fix7b_ensure_catalog_products_for_article_codes(
            conn,
            candidates,
        )

    repaired_count = sum(
        1
        for before, after in zip(candidates, repaired)
        if (
            str(before.get("global_product_id") or "").strip()
            != str(after.get("global_product_id") or "").strip()
            or str(before.get("status") or "").strip()
            != str(after.get("status") or "").strip()
            or str(before.get("candidate_status") or "").strip()
            != str(after.get("candidate_status") or "").strip()
        )
    )

    return {
        "ok": True,
        "examined_count": len(candidates),
        "repaired_count": repaired_count,
        "explicit_write_action": True,
        "creates_inventory_event": False,
    }
