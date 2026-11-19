"""Request-scoped, read-only prefetch for individual Bijna op evaluations.

The historical evaluator needs inventory by *article name*, events by canonical
article ID OR name, and purchase events in chronological order. Fetch those
three household-scoped projections once instead of making the same three
round-trips plus member lookups for every individual article.

Only call this helper for non-aggregated signals: the established safe grouping
authority keeps full ownership of grouped product/synonym evaluations.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import bindparam, text


def _ordered_union(by_id, by_name, article_ids, article_names):
    """Preserve the original database ORDER BY, even if a row matches both."""
    positions = {}
    for key in article_ids:
        for position, row in by_id.get(key, ()):
            positions[position] = row
    for name in article_names:
        for position, row in by_name.get(name, ()):
            positions[position] = row
    return [positions[position] for position in sorted(positions)]


def _index(rows, id_key, name_key):
    by_id, by_name = defaultdict(list), defaultdict(list)
    for position, raw in enumerate(rows):
        row = dict(raw)
        identifier = str(row.get(id_key) or '').strip()
        name = str(row.get(name_key) or '').strip().lower()
        if identifier:
            by_id[identifier].append((position, row))
        if name:
            by_name[name].append((position, row))
    return by_id, by_name


def prefetch_individual_almost_out(conn, household_id, all_articles, candidates,
                                  *, include_purchases):
    """Return source-equivalent projections keyed by canonical household ID.

    Every query remains household-scoped; this is a per-request local mapping,
    not a stale shared cache or a new article-identity authority.
    """
    if not candidates:
        return {}

    by_product = defaultdict(list)
    by_article = {}
    for raw in all_articles:
        row = dict(raw)
        article_id = str(row.get('id') or '').strip()
        if not article_id:
            continue
        by_article[article_id] = row
        product_id = str(row.get('global_product_id') or '').strip()
        if product_id:
            by_product[product_id].append(row)

    # The caller already loaded all active household articles in the SQL
    # ORDER BY of the legacy member lookup; preserve its database collation.

    members = {}
    requested_ids, requested_names = set(), set()
    for candidate in candidates:
        article_id = str(candidate.get('id') or '').strip()
        row = by_article.get(article_id)
        if not row:
            continue
        product_id = str(row.get('global_product_id') or '').strip()
        member_rows = by_product.get(product_id, [row]) if product_id else [row]
        ids = tuple(str(member['id']) for member in member_rows)
        names = tuple({str(member.get('naam') or '').strip().lower()
                       for member in member_rows if str(member.get('naam') or '').strip()})
        members[article_id] = (ids, names)
        requested_ids.update(ids)
        requested_names.update(names)
    if not members:
        return {}

    args = {'household_id': str(household_id),
            'article_ids': sorted(requested_ids),
            'article_names': sorted(requested_names)}
    inventory_rows = conn.execute(text("""
        SELECT i.id, i.naam AS article_name, i.aantal AS quantity,
               i.household_id, i.space_id, i.sublocation_id,
               COALESCE(s.naam, '') AS space_name,
               COALESCE(sl.naam, '') AS sublocation_name,
               COALESCE(i.status, 'active') AS status
        FROM inventory i
        LEFT JOIN spaces s ON s.id = i.space_id
        LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
        WHERE i.household_id = :household_id
          AND lower(trim(i.naam)) IN :article_names
          AND COALESCE(i.status, 'active') = 'active'
          AND COALESCE(i.aantal, 0) > 0
        ORDER BY COALESCE(i.updated_at, i.created_at) DESC, i.id ASC
    """).bindparams(bindparam('article_names', expanding=True)), args).mappings().all()

    event_rows = conn.execute(text("""
        SELECT id, article_id, article_name, location_id, location_label,
               event_type, quantity, old_quantity, new_quantity, source, note,
               created_at, purchase_date, supplier_name, price, currency,
               article_number, barcode
        FROM inventory_events
        WHERE household_id = :household_id
          AND (article_id IN :article_ids
               OR lower(trim(article_name)) IN :article_names)
        ORDER BY created_at DESC NULLS LAST, id DESC
    """).bindparams(
        bindparam('article_ids', expanding=True),
        bindparam('article_names', expanding=True),
    ), args).mappings().all()

    purchase_rows = []
    if include_purchases:
        purchase_rows = conn.execute(text("""
            SELECT article_id, article_name, event_type, quantity,
                   purchase_date, created_at
            FROM inventory_events
            WHERE household_id = :household_id
              AND COALESCE(quantity, 0) > 0
              AND event_type IN ('purchase', 'auto_repurchase')
              AND (article_id IN :article_ids
                   OR lower(trim(article_name)) IN :article_names)
            ORDER BY COALESCE(CAST(purchase_date AS TIMESTAMPTZ), created_at) ASC,
                     created_at ASC, id ASC
        """).bindparams(
            bindparam('article_ids', expanding=True),
            bindparam('article_names', expanding=True),
        ), args).mappings().all()

    _, inv_name = _index(inventory_rows, 'id', 'article_name')
    event_id, event_name = _index(event_rows, 'article_id', 'article_name')
    purchase_id, purchase_name = _index(purchase_rows, 'article_id', 'article_name')
    result = {}
    for article_id, (ids, names) in members.items():
        # Existing inventory lookup matches names only, not i.household_article_id.
        # Restore query order after union of multiple household product names.
        inventory = _ordered_union({}, inv_name, (), names)
        primary_id = ids[0] if ids else article_id
        converted = [{
            'id': row['id'],
            'household_article_id': primary_id, 'article_id': primary_id,
            'product_scope_article_ids': list(ids),
            'article_name': row['article_name'],
            'quantity': float(row['quantity']) if row.get('quantity') is not None else 0,
            'aantal': float(row['quantity']) if row.get('quantity') is not None else 0,
            'space_id': row['space_id'] or '',
            'sublocation_id': row['sublocation_id'] or '',
            'space_name': row['space_name'] or '', 'locatie': row['space_name'] or '',
            'sublocation_name': row['sublocation_name'] or '',
            'sublocatie': row['sublocation_name'] or '',
            'location_label': ' / '.join(part for part in (
                row['space_name'] or '', row['sublocation_name'] or '') if part),
            'status': row['status'] or 'active',
        } for row in inventory]
        result[article_id] = {
            'inventory_rows': converted,
            'event_rows': _ordered_union(event_id, event_name, ids, names),
            'purchase_rows': _ordered_union(purchase_id, purchase_name, ids, names),
        }
    return result
