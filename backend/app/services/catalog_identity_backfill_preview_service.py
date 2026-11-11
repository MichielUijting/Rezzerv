"""Read-only candidate planning for historical Catalogus identity repair.

This service never changes household articles, stock, receipt or Catalogus
records. It follows exact receipt-line references and requires confirmation
for every store-specific code. The separate writeback is intentionally not
automated until preview counts and conflicts are validated on a real runtime.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import text

from app.services.catalog_identity_resolution_service import resolve_catalog_identity


def preview_household_catalog_identity_backfill(
    conn, *, household_id: str, limit: int = 10000,
) -> dict[str, Any]:
    household = str(household_id or "").strip()
    if not household:
        raise ValueError("household_id is required")
    limit = max(1, min(int(limit), 10000))
    # The two canonical reference parts identify the exact receipt and line.
    # Never use textual article descriptions to identify historical purchases.
    rows = conn.execute(
        text("""
            SELECT ha.id AS household_article_id,
                   ha.global_product_id AS current_product_id,
                   rtl.barcode AS gtin,
                   rtl.external_article_code AS retailer_article_code,
                   rt.store_name AS retailer_code
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            JOIN receipt_tables rt
              ON rt.id = substr(pib.source_reference, 9)
             AND rt.household_id = pib.household_id
            JOIN receipt_table_lines rtl
              ON rtl.id = substr(pil.external_line_ref, 14)
             AND rtl.receipt_table_id = rt.id
            JOIN household_articles ha
              ON ha.id = pil.matched_household_article_id
             AND ha.household_id = pib.household_id
            WHERE pib.household_id = :household_id
              AND pib.source_type = 'receipt'
              AND pib.source_reference LIKE 'receipt:%'
              AND pil.external_line_ref LIKE 'receipt-line:%'
              AND COALESCE(rtl.is_deleted, FALSE) = FALSE
            ORDER BY ha.id, rtl.id
            LIMIT :limit
        """),
        {"household_id": household, "limit": limit},
    ).mappings().all()
    by_article: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"candidates": set(), "current": set(), "unresolved": 0, "sources": 0}
    )
    for row in rows:
        article = by_article[str(row["household_article_id"])]
        article["sources"] += 1
        current = str(row.get("current_product_id") or "").strip()
        if current:
            article["current"].add(current)
        result = resolve_catalog_identity(
            conn,
            gtin=row.get("gtin"),
            retailer_code=row.get("retailer_code"),
            external_article_code=row.get("retailer_article_code"),
        )
        if result["status"] == "matched":
            article["candidates"].add(result["global_product_id"])
        elif result["status"] != "no_identity":
            # Pending, missing, invalid or conflicting identity prevents
            # automatic writeback of the household article.
            article["unresolved"] += 1

    report = {
        "household_id": household,
        "source_rows_examined": len(rows),
        "articles_examined": len(by_article),
        "eligible": 0,
        "already_linked": 0,
        "conflict": 0,
        "unresolved": 0,
        "no_confirmed_identity": 0,
        "limited": len(rows) >= limit,
        "changes": "none",
    }
    for article in by_article.values():
        current = article["current"]
        candidates = article["candidates"]
        if len(current) > 1 or len(candidates) > 1 or (current and candidates and current != candidates):
            report["conflict"] += 1
        elif current:
            report["already_linked"] += 1
        elif article["unresolved"]:
            report["unresolved"] += 1
        elif len(candidates) == 1:
            report["eligible"] += 1
        else:
            report["no_confirmed_identity"] += 1
    return report
