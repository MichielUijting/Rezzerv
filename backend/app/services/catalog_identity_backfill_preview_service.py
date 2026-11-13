"""Read-only candidate planning for historical Catalogus identity repair.

This service never changes household articles, stock, receipt or Catalogus
records. It follows exact receipt-line references and requires confirmation
for every store-specific code. The separate writeback is intentionally not
automated until preview counts and conflicts are validated on a real runtime.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any

from sqlalchemy import bindparam, text

from app.services.catalog_identity_resolution_service import resolve_catalog_identity


def preview_household_catalog_identity_backfill(
    conn, *, household_id: str, limit: int = 10000, include_candidates: bool = False,
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
                   COALESCE(NULLIF(rtl.corrected_raw_label, ''),
                            NULLIF(rtl.normalized_label, ''),
                            NULLIF(rtl.raw_label, ''), '') AS receipt_text,
                   COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '') AS retailer_code
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
        lambda: {"candidates": set(), "current": set(), "unresolved": 0, "without_identity": 0, "sources": 0}
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
            receipt_text=row.get("receipt_text"),
        )
        if result["status"] == "matched":
            article["candidates"].add(result["global_product_id"])
        elif result["status"] == "no_identity":
            # A second historical line lacking any code does not prove that
            # it is the same product. Do not auto-link from a partial trail.
            article["without_identity"] += 1
        else:
            # Pending, missing, invalid or conflicting identity prevents
            # automatic writeback of the household article.
            article["unresolved"] += 1

    candidate_owners: dict[str, set[str]] = defaultdict(set)
    for article_id, article in by_article.items():
        for product_id in article["candidates"]:
            candidate_owners[product_id].add(article_id)

    occupied_products: set[str] = set()
    if candidate_owners:
        occupied = conn.execute(
            text("""
                SELECT DISTINCT global_product_id FROM household_articles
                WHERE household_id = :household_id
                  AND global_product_id IN :candidate_ids
            """).bindparams(bindparam("candidate_ids", expanding=True)),
            {"household_id": household, "candidate_ids": sorted(candidate_owners)},
        ).scalars().all()
        occupied_products = {str(value) for value in occupied if value}

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
    eligible_candidates: list[dict[str, str]] = []
    for article_id, article in by_article.items():
        current = article["current"]
        candidates = article["candidates"]
        if len(current) > 1 or len(candidates) > 1 or (current and candidates and current != candidates):
            report["conflict"] += 1
        elif current:
            report["already_linked"] += 1
        elif article["unresolved"] or (candidates and article["without_identity"]):
            report["unresolved"] += 1
        elif len(candidates) == 1:
            target = next(iter(candidates))
            if target in occupied_products or len(candidate_owners[target]) > 1:
                report["conflict"] += 1
            else:
                report["eligible"] += 1
                eligible_candidates.append({"article_id": article_id, "global_product_id": target})
        else:
            report["no_confirmed_identity"] += 1
    if report["limited"]:
        # LIMIT can hide another line for the same household article. Never
        # advertise any candidate as eligible from an incomplete scan.
        report["eligible_withheld_due_to_limit"] = report["eligible"]
        report["eligible"] = 0
        eligible_candidates.clear()
    # The token binds the reviewed household and *entire* reviewed plan, not
    # merely the number of eligible articles. Apply always recalculates it.
    stable = {
        "household_id": household,
        "candidates": sorted(eligible_candidates, key=lambda item: item["article_id"]),
        "counts": {key: report[key] for key in (
            "source_rows_examined", "articles_examined", "already_linked",
            "conflict", "unresolved", "no_confirmed_identity", "limited",
        )},
    }
    report["plan_token"] = hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if include_candidates:
        report["eligible_candidates"] = stable["candidates"]
    return report
