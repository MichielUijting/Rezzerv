"""Read-only, identity-safe work queue for central article classification.

One row is one canonical global_product ID, never a receipt, a household
article, an unconfirmed synonym suggestion or a name match. GPC and CBS
tasks are separate (global_product_id, system) keys.
"""
from __future__ import annotations

import json

from sqlalchemy import text



CLASSIFICATION_SQL = """
    -- Page canonical products *before* joining classifications or aggregating
    -- retailer/synonym relationships. Preserve identity and total semantics.
    WITH requested_page AS MATERIALIZED (
        SELECT gp.id, gp.name, gp.brand, gp.primary_gtin
          FROM global_products gp
         WHERE LOWER(COALESCE(gp.status, '')) <> 'deleted'
         ORDER BY LOWER(gp.name), gp.id
         LIMIT :limit OFFSET :offset
    ),
    page_links AS (
        SELECT e.global_product_id, COUNT(*) AS confirmed_links
          FROM external_article_product_links e
          JOIN requested_page page ON page.id = e.global_product_id
         WHERE e.status = 'confirmed'
         GROUP BY e.global_product_id
    ),
    page_synonym_ids AS (
        SELECT s.left_product_id AS id
          FROM article_synonym_links s
          JOIN requested_page page ON page.id = s.left_product_id
        UNION ALL
        SELECT s.right_product_id AS id
          FROM article_synonym_links s
          JOIN requested_page page ON page.id = s.right_product_id
    ),
    page_synonyms AS (
        SELECT id, COUNT(*) AS confirmed_synonyms
          FROM page_synonym_ids
         GROUP BY id
    )
    SELECT page.id, page.name, page.brand, page.primary_gtin,
           gpc.brick_code AS gpc_code,
           cbs.cbs_code, cbs.reference_version AS cbs_reference_version,
           cbs.version AS cbs_version, cbs.is_active AS cbs_active,
           ref.name_nl AS cbs_name,
           COALESCE(links.confirmed_links, 0) AS confirmed_source_links,
           COALESCE(synonyms.confirmed_synonyms, 0) AS confirmed_synonyms
      FROM requested_page page
      LEFT JOIN global_product_gpc_bricks gpc ON gpc.global_product_id = page.id
      LEFT JOIN global_product_cbs_classifications cbs ON cbs.global_product_id = page.id
      LEFT JOIN cbs_ecoicop_categories ref
             ON ref.cbs_code = cbs.cbs_code
            AND ref.reference_version = cbs.reference_version
      LEFT JOIN page_links links ON links.global_product_id = page.id
      LEFT JOIN page_synonyms synonyms ON synonyms.id = page.id
     ORDER BY LOWER(page.name), page.id
"""

def project_classification_tasks(rows):
    """Fail closed on duplicate central identities instead of hiding a join error."""
    items = []
    tasks = []
    seen = set()
    for row in rows:
        product_id = str(row["id"])
        if not product_id or product_id in seen:
            raise ValueError("Cataloguswerkvoorraad bevat dubbele of ontbrekende centrale productidentiteit.")
        seen.add(product_id)
        gpc_code = str(row["gpc_code"] or "")
        cbs_code = str(row["cbs_code"] or "") if row["cbs_active"] else ""
        item = {
            "id": product_id,
            "name": str(row["name"] or ""),
            "brand": str(row["brand"] or ""),
            "gtin": str(row["primary_gtin"] or ""),
            "gpc_code": gpc_code,
            "gpc_status": "classified" if gpc_code else "unclassified",
            "cbs_code": cbs_code,
            "cbs_status": "classified" if cbs_code else "unclassified",
            "cbs_name": str(row["cbs_name"] or "") if cbs_code else "",
            "cbs_reference_version": str(row["cbs_reference_version"] or "") if cbs_code else "",
            "cbs_version": int(row["cbs_version"] or 0),
            "confirmed_source_links": int(row["confirmed_source_links"] or 0),
            "confirmed_synonyms": int(row["confirmed_synonyms"] or 0),
        }
        items.append(item)
        if not gpc_code:
            tasks.append({"key": f"{product_id}:gpc", "global_product_id": product_id,
                          "system": "gpc", "status": "open"})
        if not cbs_code:
            tasks.append({"key": f"{product_id}:cbs", "global_product_id": product_id,
                          "system": "cbs", "status": "open"})
    return items, tasks


def load_classification_workqueue(conn, *, offset=0, limit=100):
    """No writes, implicit name matching, household joins or fabricated totals."""
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Ongeldige paginering.")
    total = int(conn.execute(text("""
        SELECT COUNT(*) FROM global_products
         WHERE LOWER(COALESCE(status, '')) <> 'deleted'
    """)).scalar_one())
    rows = conn.execute(text(CLASSIFICATION_SQL),
                        {"limit": limit, "offset": offset}).mappings().all()
    items, tasks = project_classification_tasks(rows)
    # Page-scoped counts must never masquerade as platform-wide totals.
    return {"items": items, "tasks": tasks, "total": total,
            "task_count_scope": "page", "product_count_scope": "global",
            "limit": limit, "offset": offset}


def project_identification_tasks(source_rows):
    """An unconfirmed receipt identity is not a canonical Catalogus product.

    The authoritative ED2 server projection already excludes removed receipts,
    filters non-products and deduplicates exact source identities. Never merge
    items on barcode, name similarity, synonym suggestions or classification.
    """
    items = []
    seen = set()
    for source in source_rows:
        if source.get("link_status") != "unlinked":
            continue
        retailer = str(source.get("retailer_code") or "")
        label = str(source.get("receipt_line_text") or "")
        article_code = str(source.get("receipt_article_number") or "")
        source_id = str(source.get("id") or "")
        if not retailer or not label or not source_id:
            raise ValueError("Bronartikelidentiteit ontbreekt; geen fictieve taak aanmaken.")
        identity = (retailer, label, article_code)
        if identity in seen:
            raise ValueError("Dubbele bonartikelbronidentiteit in de werkvoorraad.")
        seen.add(identity)
        items.append({
            "key": json.dumps(identity, ensure_ascii=False),
            "source_receipt_id": source_id,
            "retailer_code": retailer,
            "receipt_line_text": label,
            "receipt_article_number": article_code,
            "manual_barcode": str(source.get("manual_barcode") or ""),
            "status": "needs_identification",
            "global_product_id": None,
        })
    return items


def load_identification_workqueue(conn):
    """Reuse the proven, read-only ED2 identity authority; never write a link."""
    from app.services.external_unlinked_articles_service import list_all_external_articles

    source = list_all_external_articles(conn=conn)
    items = project_identification_tasks(source["items"])
    return {
        "items": items,
        "total": len(items),
        "count_scope": "verified_source_identities",
        "classification_task_count": None,
    }
