"""Resolve an explicitly confirmed Catalogus synonym component within one household.

Transitivity follows *confirmed graph edges*, not product names or suggested
pairs. No household stock or Catalogus identities are ever merged.
"""
from __future__ import annotations

from sqlalchemy import text

MAX_GROUP_PRODUCTS = 200


def confirmed_household_synonym_group(
    conn, household_id: str, household_article_id: str
) -> tuple[str, ...]:
    """Return unique active household members of the confirmed connected component.

    Missing/invalid identities, inactive Catalogus products, duplicate household
    representations or oversized groups fail closed to the original article.
    Central group members not represented in this household are permitted: they
    cannot contribute inventory, but retain the connected graph identity.
    """
    household_id = str(household_id or "").strip()
    article_id = str(household_article_id or "").strip()
    fallback = (article_id,) if article_id else ()
    if not household_id or not article_id:
        return fallback

    owner = conn.execute(text("""
        SELECT ha.global_product_id
        FROM household_articles ha
        JOIN global_products gp ON gp.id = ha.global_product_id
        WHERE ha.id = :article_id AND ha.household_id = :household_id
          AND COALESCE(ha.status, 'active') = 'active'
          AND COALESCE(gp.status, 'active') = 'active'
    """), {"article_id": article_id, "household_id": household_id}).mappings().all()
    if len(owner) != 1 or not owner[0]["global_product_id"]:
        return fallback
    catalog_id = str(owner[0]["global_product_id"])

    # UNION (not UNION ALL) makes cycles and multiple paths terminate; every
    # traversed edge comes from an explicitly confirmed persisted synonym pair.
    products = conn.execute(text("""
        WITH RECURSIVE connected(product_id) AS (
            SELECT CAST(:catalog_id AS TEXT)
            UNION
            SELECT CASE
                WHEN link.left_product_id = connected.product_id
                THEN link.right_product_id ELSE link.left_product_id
            END
            FROM article_synonym_links link
            JOIN connected ON (
                link.left_product_id = connected.product_id
                OR link.right_product_id = connected.product_id
            )
        )
        SELECT connected.product_id, gp.id AS existing_product_id,
               gp.status AS catalog_status
        FROM connected
        LEFT JOIN global_products gp ON gp.id = connected.product_id
        ORDER BY connected.product_id
    """), {"catalog_id": catalog_id}).mappings().all()
    if not (2 <= len(products) <= MAX_GROUP_PRODUCTS):
        return fallback
    if any(
        row["existing_product_id"] is None
        or str(row["catalog_status"] or "active") != "active"
        for row in products
    ):
        return fallback
    catalog_ids = [str(row["product_id"]) for row in products]

    # Only private articles from *this household* may participate. Each central
    # product may have at most one active private representation; ambiguity is
    # not resolved using product names.
    members = conn.execute(text("""
        SELECT ha.id, ha.global_product_id
        FROM household_articles ha
        WHERE ha.household_id = :household_id
          AND ha.global_product_id = ANY(:catalog_ids)
          AND COALESCE(ha.status, 'active') = 'active'
    """), {"household_id": household_id, "catalog_ids": catalog_ids}).mappings().all()
    by_product: dict[str, list[str]] = {}
    for row in members:
        by_product.setdefault(str(row["global_product_id"]), []).append(str(row["id"]))
    if any(len(article_ids) != 1 for article_ids in by_product.values()):
        return fallback
    if by_product.get(catalog_id) != [article_id]:
        return fallback
    article_ids = tuple(sorted(ids[0] for ids in by_product.values()))
    if len(article_ids) < 2:
        return fallback
    return article_ids


# Keep the former resolver spelling for existing internal imports while the
# route callers and tests migrate. Its output can now contain 3+ members.
confirmed_household_synonym_pair = confirmed_household_synonym_group
