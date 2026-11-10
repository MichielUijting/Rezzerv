"""Read-only, fail-closed household article pairing for repurchase policy.

Only directly confirmed Catalogus synonyms may form a pair. The service does not
infer transitive equivalence, merge household articles, or mutate stock.
"""
from __future__ import annotations

from sqlalchemy import text


def confirmed_household_synonym_pair(conn, household_id: str, household_article_id: str) -> tuple[str, ...]:
    """Return a safe two-article pair, else the original household article alone.

    Fail closed on missing/catalog-inactive identities, chains/stars, duplicate
    household representations and cross-household records. Catalogus synonyms
    are direct pairs, not transitive equivalence classes.
    """
    household_id = str(household_id or '').strip()
    article_id = str(household_article_id or '').strip()
    if not household_id or not article_id:
        return (article_id,) if article_id else ()

    owner = conn.execute(text("""
        SELECT ha.global_product_id
        FROM household_articles ha
        JOIN global_products gp ON gp.id = ha.global_product_id
        WHERE ha.id = :article_id AND ha.household_id = :household_id
          AND COALESCE(ha.status, 'active') = 'active'
          AND COALESCE(gp.status, 'active') = 'active'
    """), {'article_id': article_id, 'household_id': household_id}).mappings().all()
    if len(owner) != 1 or not owner[0]['global_product_id']:
        return (article_id,)
    catalog_id = str(owner[0]['global_product_id'])
    linked = conn.execute(text("""
        SELECT CASE WHEN left_product_id = :catalog_id THEN right_product_id
                    ELSE left_product_id END AS partner
        FROM article_synonym_links
        WHERE left_product_id = :catalog_id OR right_product_id = :catalog_id
    """), {'catalog_id': catalog_id}).mappings().all()
    if len(linked) != 1 or not linked[0]['partner']:
        return (article_id,)
    partner_id = str(linked[0]['partner'])
    reverse = conn.execute(text("""
        SELECT 1 FROM article_synonym_links
        WHERE left_product_id = :partner OR right_product_id = :partner
    """), {'partner': partner_id}).all()
    if len(reverse) != 1:
        return (article_id,)

    members = conn.execute(text("""
        SELECT ha.id, ha.global_product_id
        FROM household_articles ha
        JOIN global_products gp ON gp.id = ha.global_product_id
        WHERE ha.household_id = :household_id
          AND ha.global_product_id IN (:catalog_id, :partner)
          AND COALESCE(ha.status, 'active') = 'active'
          AND COALESCE(gp.status, 'active') = 'active'
    """), {'household_id': household_id, 'catalog_id': catalog_id, 'partner': partner_id}).mappings().all()
    by_product = {}
    for row in members:
        by_product.setdefault(str(row['global_product_id']), []).append(str(row['id']))
    if len(by_product.get(catalog_id, [])) != 1 or by_product[catalog_id][0] != article_id:
        return (article_id,)
    if len(by_product.get(partner_id, [])) != 1:
        return (article_id,)
    return tuple(sorted((article_id, by_product[partner_id][0])))
