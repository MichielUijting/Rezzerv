"""Read-only proof of uncataloged household identity from independent source GTINs.

This does not merge household articles. The historical repair transaction must
still enforce manual settings, physical stock, unknown FK, and replay guards.
Receipt descriptions, retailer SKUs and unchecked barcodes are not authority.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import bindparam, text

from app.services.receipt_stock_review_service import _checked_gtin_key


def verified_uncataloged_groups(conn, *, household_id, cutoff, articles):
    """Return oldest-first (article rows, verified GTIN14) groups or none.

    Only checked GTINs in physical, original AH/Jumbo API receipt lines can
    authorize this path; each article needs its own independent source evidence,
    and the whole group needs both providers. Catalog-linked identities are
    reserved for the existing canonical product-based repair.
    """
    candidates = {
        str(row["id"]): dict(row) for row in articles
        if row.get("global_product_id") is None
    }
    if len(candidates) < 2:
        return []

    rows = conn.execute(text("""
        SELECT rtl.matched_article_id, rtl.barcode, rtl.matched_global_product_id,
               rs.source_path
        FROM receipt_table_lines rtl
        JOIN receipt_tables rt ON rt.id=rtl.receipt_table_id
        JOIN raw_receipts rr ON rr.id=rt.raw_receipt_id
                            AND rr.household_id=rt.household_id
        JOIN receipt_sources rs ON rs.id=rr.source_id
                               AND rs.household_id=rt.household_id
        WHERE rt.household_id=:household_id
          AND rtl.matched_article_id IN :article_ids
          AND rs.type='retailer_api' AND rs.source_path IN ('ah','jumbo')
          AND rt.deleted_at IS NULL AND rr.deleted_at IS NULL
          AND rr.duplicate_of_raw_receipt_id IS NULL
          AND COALESCE(rt.workflow_state, 'active')='active'
          AND COALESCE(rtl.is_deleted, FALSE)=FALSE
          AND rtl.line_role='product' AND rtl.inventory_eligible=1
          AND rt.purchase_at IS NOT NULL
          AND LOWER(TRIM(COALESCE(rt.purchase_at_source, ''))) <> 'import_default'
          AND CAST(rt.purchase_at AS DATE) < CAST(:cutoff AS DATE)
        ORDER BY rtl.matched_article_id, rtl.id
        LIMIT 20001
    """).bindparams(bindparam("article_ids", expanding=True)), {
        "household_id": household_id, "article_ids": sorted(candidates),
        "cutoff": str(cutoff)[:10],
    }).mappings().all()
    if len(rows) > 20000:
        return []  # A truncated evidence set cannot prove nonconflicting IDs.

    observed = defaultdict(set)
    source_codes = defaultdict(set)
    conflicting_products = set()
    for row in rows:
        article_id = str(row["matched_article_id"])
        if row.get("matched_global_product_id") is not None:
            conflicting_products.add(article_id)
            continue
        checked = _checked_gtin_key(row.get("barcode"))
        if checked:
            observed[article_id].add(checked.zfill(14))
            source_codes[article_id].add(str(row["source_path"]))

    groups = defaultdict(list)
    for article_id, article in candidates.items():
        gtins = observed.get(article_id, set())
        if article_id in conflicting_products or len(gtins) != 1:
            continue
        gtin = next(iter(gtins))
        stored_barcode = str(article.get("barcode") or "").strip()
        if stored_barcode:
            stored_gtin = _checked_gtin_key(stored_barcode)
            if not stored_gtin or stored_gtin.zfill(14) != gtin:
                continue
        groups[gtin].append(article)

    accepted = []
    for gtin, members in groups.items():
        if len(members) < 2:
            continue
        independent = set()
        for member in members:
            independent.update(source_codes[str(member["id"])])
        if {"ah", "jumbo"} <= independent:
            accepted.append((members, gtin))
    return accepted
