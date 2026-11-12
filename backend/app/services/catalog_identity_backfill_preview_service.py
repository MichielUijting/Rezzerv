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

from sqlalchemy import bindparam, inspect, text

from app.services.catalog_identity_resolution_service import resolve_catalog_identity
from app.services.catalog_retailer_identity_keys import canonical_catalog_retailer
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)


def preview_household_catalog_identity_backfill(
    conn, *, household_id: str, limit: int = 10000, include_candidates: bool = False,
    include_conflicts: bool = False,
) -> dict[str, Any]:
    household = str(household_id or "").strip()
    if not household:
        raise ValueError("household_id is required")
    limit = max(1, min(int(limit), 10000))
    # The two canonical reference parts identify the exact receipt and line.
    # Never use textual article descriptions to identify historical purchases.
    # Legacy and isolated fixture schemas may have no receipt description
    # columns. Use them when available; preserve code-only compatibility
    # otherwise. Never infer an article from a display name.
    receipt_columns = {col["name"] for col in inspect(conn).get_columns("receipt_table_lines")}
    label_parts = [
        f"NULLIF(rtl.{column}, '')"
        for column in ("corrected_raw_label", "normalized_label", "raw_label")
        if column in receipt_columns
    ]
    receipt_label_sql = "COALESCE(" + ", ".join(label_parts) + ")" if label_parts else "NULL"
    # Only the authorized review view needs household names and exact source
    # line IDs. Preserve the existing read-only preview contract by default.
    extra_review_columns = ""
    retailer_expression = "rt.store_name"
    if include_conflicts:
        receipt_table_columns = {col["name"] for col in inspect(conn).get_columns("receipt_tables")}
        if "store_chain" in receipt_table_columns:
            retailer_expression = "COALESCE(NULLIF(rt.store_chain, ''), rt.store_name)"
        article_columns = {col["name"] for col in inspect(conn).get_columns("household_articles")}
        name_parts = [f"NULLIF(ha.{col}, '')" for col in ("custom_name", "naam")
                      if col in article_columns]
        name_sql = ("COALESCE(" + ", ".join(name_parts) + ")") if name_parts else "NULL"
        extra_review_columns = f", rtl.id AS receipt_line_id, {name_sql} AS household_article_name"
    rows = conn.execute(
        text(f"""
            SELECT ha.id AS household_article_id,
                   ha.global_product_id AS current_product_id,
                   rtl.barcode AS gtin,
                   rtl.external_article_code AS retailer_article_code,
                   {receipt_label_sql} AS receipt_text,
                   {retailer_expression} AS retailer_code
                   {extra_review_columns}
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
        lambda: {"candidates": set(), "current": set(), "unresolved": 0, "without_identity": 0, "sources": 0,
                 "source_map": {}, "name": ""}
    )
    for row in rows:
        article = by_article[str(row["household_article_id"])]
        article["sources"] += 1
        if include_conflicts:
            article["name"] = str(row.get("household_article_name") or "")
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
        if include_conflicts:
            retailer = canonical_catalog_retailer(row.get("retailer_code"))
            label = normalize_external_link_receipt_text(row.get("receipt_text"))
            code = normalize_external_link_article_code(row.get("retailer_article_code"))
            source_key = (retailer, label, code)
            if source_key not in article["source_map"]:
                article["source_map"][source_key] = {
                    "receipt_line_id": str(row.get("receipt_line_id") or ""),
                    "retailer_code": retailer,
                    "receipt_text": label,
                    "external_article_code": code,
                    "receipt_count": 0,
                    "identity_status": result["status"],
                    "candidate_product_id": result.get("global_product_id") if result["status"] == "matched" else None,
                }
            article["source_map"][source_key]["receipt_count"] += 1
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
    conflict_reasons: dict[str, str] = {}
    for article_id, article in by_article.items():
        current = article["current"]
        candidates = article["candidates"]
        if len(current) > 1 or len(candidates) > 1 or (current and candidates and current != candidates):
            report["conflict"] += 1
            conflict_reasons[article_id] = "tegenstrijdige_bronidentiteiten"
        elif current:
            report["already_linked"] += 1
        elif article["unresolved"] or (candidates and article["without_identity"]):
            report["unresolved"] += 1
        elif len(candidates) == 1:
            target = next(iter(candidates))
            if target in occupied_products or len(candidate_owners[target]) > 1:
                report["conflict"] += 1
                conflict_reasons[article_id] = ("catalogusproduct_al_bezet" if target in occupied_products
                                                else "meerdere_huishoudartikelen")
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
    if include_conflicts:
        # An incomplete source scan cannot authorize any historical review.
        # All rows, names and candidate products are read only and scoped to
        # the household provided by the authenticated caller.
        review_items = []
        if not report["limited"]:
            for article_id, reason in sorted(conflict_reasons.items()):
                article = by_article[article_id]
                review_items.append({
                    "household_article_id": article_id,
                    "article_name": article["name"],
                    "reason": reason,
                    "current_product_ids": sorted(article["current"]),
                    "candidate_product_ids": sorted(article["candidates"]),
                    "source_count": article["sources"],
                    "sources": sorted(article["source_map"].values(), key=lambda source: (
                        source["retailer_code"], source["receipt_text"],
                        source["external_article_code"], source["receipt_line_id"],
                    )),
                })
        product_ids = sorted({
            product_id for item in review_items
            for product_id in (item["current_product_ids"] + item["candidate_product_ids"])
        })
        product_rows = []
        if product_ids:
            product_columns = {col["name"] for col in inspect(conn).get_columns("global_products")}
            name_expression = "name" if "name" in product_columns else "NULL AS name"
            gtin_expression = "primary_gtin" if "primary_gtin" in product_columns else "NULL AS primary_gtin"
            product_rows = conn.execute(text(f"""
                SELECT id, {name_expression}, {gtin_expression} FROM global_products
                WHERE id IN :ids AND LOWER(COALESCE(status, 'active')) = 'active'
            """).bindparams(bindparam("ids", expanding=True)),
                {"ids": product_ids}).mappings().all()
        report["conflict_items"] = review_items
        report["conflict_products"] = [
            {"id": str(product["id"]), "name": str(product["name"] or ""),
             "primary_gtin": str(product["primary_gtin"] or "")}
            for product in product_rows
        ]
        report["conflict_list_complete"] = not report["limited"]
    return report
