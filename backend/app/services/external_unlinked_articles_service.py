"""Read-only platform overview of receipt articles without a Catalogus barcode.

Uses the existing central link projection, never household product references or
the legacy candidate listing (which can promote candidates during a read).
"""
from __future__ import annotations

from sqlalchemy import text

from app.db import engine
from app.services.external_article_ui_projection import project_central_link_truth
from app.services.external_article_product_link_service import (
    normalize_external_link_retailer_code,
)
from app.services.external_product_candidate_store import _m2c2h5_purchase_import_placeholder
from app.services.external_receipt_item_projection import _receipt_table_line_placeholder
from app.services.gtin_validation_service import is_valid_gtin


def _overview_retailer_code(value):
    code = normalize_external_link_retailer_code(value)
    return 'ah' if code in {'ah', 'albert-heijn', 'albert-heijn-digitaal'} else code


def _source_articles(conn):
    # No LIMIT: filtering and UI pagination must cover the complete source set.
    purchases = conn.execute(text("""
        SELECT pil.id AS purchase_import_line_id, pib.raw_payload AS batch_raw_payload,
               pil.external_article_code, pil.article_name_raw, pil.brand_raw,
               pil.quantity_raw, pil.unit_raw
        FROM purchase_import_lines pil
        LEFT JOIN purchase_import_batches pib ON pib.id = pil.batch_id
        WHERE COALESCE(pib.source_type, '') <> 'receipt'
          AND COALESCE(pil.external_line_ref, '') NOT LIKE 'receipt-line:%'
        ORDER BY pil.created_at DESC, pil.id ASC
    """)).mappings()
    for row in purchases:
        item = _m2c2h5_purchase_import_placeholder(dict(row))
        item["external_article_code"] = row["external_article_code"]
        yield item

    # Receipt-derived Uitpakken/import rows are copies, not another source of
    # product truth. Read their canonical receipt once below, with its current
    # business role and lifecycle. Stale copies must not reintroduce deposits,
    # loyalty, deleted details or deleted receipts into the article overview.
    receipts = conn.execute(text("""
        SELECT rtl.id AS receipt_line_id,
               COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '') AS retailer_code,
               COALESCE(NULLIF(rtl.corrected_raw_label, ''), NULLIF(rtl.normalized_label, ''), NULLIF(rtl.raw_label, ''), '') AS receipt_line_text,
               rtl.external_article_code AS retailer_article_number,
               TRIM(COALESCE(CAST(rtl.quantity AS TEXT), '') || ' ' || COALESCE(rtl.unit, '')) AS quantity_label
        FROM receipt_table_lines rtl
        JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
        JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
        WHERE COALESCE(rtl.is_deleted, FALSE) = FALSE
          AND rt.deleted_at IS NULL AND rr.deleted_at IS NULL
          AND COALESCE(rt.workflow_state, 'active') NOT IN ('removed_reimport_allowed', 'removed')
          AND rtl.line_role = 'product' AND rtl.inventory_eligible = 1
        ORDER BY rt.created_at DESC, rtl.line_index ASC, rtl.id ASC
    """)).mappings()
    for row in receipts:
        item = _receipt_table_line_placeholder(dict(row))
        item["external_article_code"] = row["retailer_article_number"]
        yield item


def list_articles_without_catalog_barcode() -> dict:
    items = []
    seen = set()
    with engine.connect() as conn:
        for source in _source_articles(conn):
            if not str(source.get("receipt_line_text") or "").strip():
                continue
            # Presentation-only grouping requested by the PO. Exact displayed
            # spelling, including case/inner spaces/accents; never product identity.
            key = (
                _overview_retailer_code(source.get("retailer_code")),
                source["receipt_line_text"],
            )
            if key in seen:
                continue
            projected = project_central_link_truth(conn, source)
            if projected.get("central_link_active") is True and is_valid_gtin(
                str(projected.get("linked_gtin") or "")
            ):
                continue
            seen.add(key)
            items.append({
                "id": source["receipt_item_id"],
                "receipt_line_text": source["receipt_line_text"],
                "retailer_code": key[0],
                "receipt_article_number": str(source.get("external_article_code") or ""),
                "quantity_label": str(source.get("quantity_label") or ""),
            })
    return {"items": items, "total": len(items)}
