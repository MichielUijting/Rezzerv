"""Read-only Catalogus presentation for visible, household-scoped Bijna op signals.

Stock, signal membership, household labels and all canonical article IDs remain
owned by household_articles. A confirmed Catalogus product supplies optional
name, GS1 metadata and photo; receipt names alone never establish identity.
"""
from __future__ import annotations

from sqlalchemy import bindparam, text

from app.services.household_alias_policy import resolve_household_catalog_images


def _active_catalog_products(conn, product_ids):
    """Read names and own photos for proven global_product IDs; no writes."""
    result = {}
    ids = sorted({str(product_id).strip() for product_id in product_ids if str(product_id).strip()})
    for offset in range(0, len(ids), 200):
        batch = ids[offset:offset + 200]
        rows = conn.execute(text("""
            SELECT CAST(id AS TEXT) AS id, name,
                   COALESCE(image_url, '') AS image_url
            FROM global_products
            WHERE CAST(id AS TEXT) IN :product_ids
              AND lower(COALESCE(status, 'active')) = 'active'
        """).bindparams(bindparam("product_ids", expanding=True)), {
            "product_ids": batch,
        }).mappings().all()
        for row in rows:
            product_id = str(row.get("id") or "").strip()
            if product_id:
                result[product_id] = dict(row)
    return result


def _confirmed_catalog_gpc(conn, product_ids):
    """Project only *existing* GS1 assignments; do not auto-classify on reads."""
    from app.services.dutch_gpc_projection_service import (
        _canonical_hierarchy_by_brick, _tables,
    )
    ids = sorted({str(product_id).strip() for product_id in product_ids if str(product_id).strip()})
    if not ids or "global_product_gpc_bricks" not in _tables(conn):
        return {}

    assignments = {}
    for offset in range(0, len(ids), 200):
        batch = ids[offset:offset + 200]
        rows = conn.execute(text("""
            SELECT CAST(global_product_id AS TEXT) AS product_id, brick_code
            FROM global_product_gpc_bricks
            WHERE CAST(global_product_id AS TEXT) IN :product_ids
        """).bindparams(bindparam("product_ids", expanding=True)), {
            "product_ids": batch,
        }).mappings().all()
        for row in rows:
            product_id = str(row.get("product_id") or "").strip()
            code = str(row.get("brick_code") or "").strip()
            if product_id and code:
                assignments[product_id] = code

    hierarchy = _canonical_hierarchy_by_brick(conn, assignments.values())
    return {
        product_id: hierarchy[code]
        for product_id, code in assignments.items() if code in hierarchy
    }


def fill_visible_almost_out_catalog_details(conn, text_factory, household_rows, visible_items):
    """Enrich already-selected signals from exact links, not by guessed names.

    A single household article remains the record behind each action. Verified
    group members may furnish *presentation* when the representative has no
    own Catalogus identity; they never replace that household ID.
    """
    if not visible_items:
        return visible_items

    by_id = {str(row.get("id") or "").strip(): dict(row) for row in household_rows}
    ordered_members = {}
    relevant_ids = set()
    for item in visible_items:
        representative = str(item.get("household_article_id") or "").strip()
        members = {
            str(member).strip() for member in item.get("member_article_ids") or []
        }
        ordered = [representative] + sorted(members - {representative, ""})
        # Members were populated exclusively by the existing safe group service.
        ordered_members[id(item)] = ordered
        relevant_ids.update(member for member in ordered if member in by_id)

    verified = {
        article_id: str(by_id[article_id].get("global_product_id") or "").strip()
        for article_id in relevant_ids
        if str(by_id[article_id].get("global_product_id") or "").strip()
    }
    # Reuse exactly the existing GTIN/product_identities/confirmed-receipt
    # resolver. Its optional verified map excludes name-only photo fallback.
    unresolved = [by_id[article_id] for article_id in sorted(relevant_ids) if article_id not in verified]
    if unresolved:
        resolved = resolve_household_catalog_images(
            conn, text_factory, unresolved, verified_identity_by_article=verified,
        )
        # The photo resolver may produce a valid, read-only fallback from a
        # product whose ID has not been proven. This cannot rename the product.
        for item in visible_items:
            if str(item.get("image_url") or "").strip():
                continue
            for article_id in ordered_members[id(item)]:
                photo = str(resolved.get(article_id) or "").strip()
                if photo:
                    item["image_url"] = photo
                    break

    products = _active_catalog_products(conn, verified.values()) if verified else {}
    gpc_by_product = _confirmed_catalog_gpc(conn, products.keys()) if products else {}

    for item in visible_items:
        members = ordered_members[id(item)]
        # Own verified identity always wins. A group member is a fallback only
        # because the existing grouping authority already proved equivalence.
        selected_id = next(
            (verified[article_id] for article_id in members
             if verified.get(article_id) in products),
            None,
        )
        product = products.get(selected_id) if selected_id else None
        if product:
            product_name = str(product.get("name") or "").strip()
            if product_name:
                item["product_name"] = product_name
            item["catalog_product_id"] = selected_id
            item["catalog_link_status"] = "confirmed"
            if not str(item.get("image_url") or "").strip():
                item["image_url"] = str(product.get("image_url") or "").strip()
            if selected_id in gpc_by_product:
                item.update(gpc_by_product[selected_id])

        if not str(item.get("image_url") or "").strip():
            item["photo_missing_reason"] = (
                "Catalogus heeft geen foto" if product else
                "Geen bevestigde Cataloguskoppeling"
            )
        else:
            item["photo_missing_reason"] = None
    return visible_items
