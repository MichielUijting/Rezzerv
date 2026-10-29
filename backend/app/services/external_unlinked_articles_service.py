"""Read-only platform overviews of receipt articles and their central Catalogus status.

Uses the existing central link projection, never household product references or
the legacy candidate listing (which can promote candidates during a read).
"""
from __future__ import annotations

from contextlib import nullcontext

from sqlalchemy import text

from app.db import engine
from app.services.external_article_ui_projection import project_central_link_truth
from app.services.external_article_product_link_service import (
    normalize_external_link_retailer_code,
    get_pending_classification_external_article_link,
)
from app.services.external_product_candidate_store import _m2c2h5_purchase_import_placeholder
from app.services.external_receipt_item_projection import _receipt_table_line_placeholder
from app.services.gtin_validation_service import is_valid_gtin
from app.receipt_ingestion.spaarzegels_terms import is_spaarzegels_flow_excluded


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
            # This article has a verified Catalogus GTIN but is waiting for a
            # real GS1 Brick. It no longer belongs in the barcode-to-find list.
            # Pending is never projected as an operational confirmed link.
            if get_pending_classification_external_article_link(
                conn,
                retailer_code=source.get("retailer_code"),
                receipt_text=source.get("receipt_line_text"),
                external_article_code=source.get("external_article_code"),
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


def list_all_external_articles(*, conn=None) -> dict:
    """Platformoverzicht van alle unieke bronartikelen, inclusief Cataloguskoppelingen.

    Een bonartikelnummer is geen GTIN. De Art.code-kolom is uitsluitend een
    gevalideerde Catalogus-GTIN; generieke koppelingen blijven zonder barcode.
    """
    items = []
    seen = set()
    counts = {"unlinked": 0, "classification_pending": 0, "linked": 0}
    with (engine.connect() if conn is None else nullcontext(conn)) as conn:
        for source in _source_articles(conn):
            receipt_text = str(source.get("receipt_line_text") or "")
            if not receipt_text.strip() or is_spaarzegels_flow_excluded(source):
                continue
            retailer = _overview_retailer_code(source.get("retailer_code"))
            article_number = str(source.get("external_article_code") or "")
            # Presentatiegroepering; afzonderlijke boncodes kunnen verschillende
            # centrale koppelingen hebben en mogen niet worden samengevoegd.
            key = (retailer, receipt_text, article_number)
            if key in seen:
                continue
            projected = project_central_link_truth(conn, source)
            if projected.get("central_link_active") is True:
                status = "linked"
                linked_gtin = str(projected.get("linked_gtin") or "")
                article_code = linked_gtin if is_valid_gtin(linked_gtin) else ""
                central_link = projected.get("central_external_article_product_link") or {}
            else:
                pending = get_pending_classification_external_article_link(
                    conn,
                    retailer_code=source.get("retailer_code"),
                    receipt_text=receipt_text,
                    external_article_code=article_number,
                )
                status = "classification_pending" if pending else "unlinked"
                pending_gtin = str((pending or {}).get("primary_gtin") or "")
                article_code = pending_gtin if is_valid_gtin(pending_gtin) else ""
                central_link = pending or {}
            seen.add(key)
            counts[status] += 1
            items.append({
                "id": source["receipt_item_id"],
                "receipt_line_text": receipt_text,
                "retailer_code": retailer,
                "receipt_article_number": article_number,
                "quantity_label": str(source.get("quantity_label") or ""),
                "article_code": article_code,
                "link_status": status,
                "is_generic_catalog_link": bool(projected.get("is_generic_catalog_link")),
                "pending_global_product_id": str(central_link.get("global_product_id") or "")
                if status == "classification_pending" and str(central_link.get("confirmed_by") or "")
                == "external_databases_off_pending_gpc" else "",
                # Alleen expliciete OFF-koppelingen mogen vanuit ED2 worden
                # ontkoppeld. Een GTIN-fallback of generieke Cataloguskoppeling
                # geeft geen verwijderbevoegdheid.
                "off_link_id": str(central_link.get("id") or "") if str(
                    central_link.get("confirmed_by") or "") in {
                    "external_databases_off_link", "external_databases_off_manual_link",
                    "external_databases_off_pending_gpc",
                } and status != "unlinked" else "",
            })
    return {"items": items, "total": len(items), "counts": counts}
