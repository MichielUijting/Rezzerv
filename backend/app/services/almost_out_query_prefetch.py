"""Request-scoped, read-only prefetch for individual Bijna op evaluations.

The historical evaluator uses canonical household article IDs wherever present.
Legacy unlinked name-only data may be read only when the household has exactly
one active article with that name. Ambiguous names never combine inventory or
purchase history. These three read-only projections are prefetched per request.

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


def _index(rows, id_key, name_key, *, known_article_ids, unique_names,
           allow_legacy_event_ids=False):
    """An owned canonical ID outranks labels; legacy names require uniqueness."""
    by_id, by_name = defaultdict(list), defaultdict(list)
    for position, raw in enumerate(rows):
        row = dict(raw)
        # The event ledger retains both a snapshot article_id and the verified
        # household ID. Prefer the latter whenever it was written.
        owner_id = str(row.get('household_article_id') or '').strip()
        identifier = owner_id or str(row.get(id_key) or '').strip()
        name = str(row.get(name_key) or '').strip().lower()
        if identifier:
            by_id[identifier].append((position, row))
        # A known ID cannot enter another article's projection via its name.
        # Unlinked legacy rows may still serve a unique-name article.
        legacy = not owner_id and (
            not identifier or (allow_legacy_event_ids
                               and identifier not in known_article_ids)
        )
        if legacy and name in unique_names:
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

    # Names shared by distinct household IDs cannot authorize history sharing,
    # even when the names are identical. Only proven product IDs form groups.
    name_owners = defaultdict(set)
    for source_id, source in by_article.items():
        normalized_name = str(source.get('naam') or '').strip().lower()
        if normalized_name:
            name_owners[normalized_name].add(source_id)
    unique_names = frozenset(
        name for name, owners in name_owners.items() if len(owners) == 1
    )
    known_article_ids = frozenset(by_article)
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
        SELECT i.id, i.household_article_id, i.naam AS article_name, i.aantal AS quantity,
               i.household_id, i.space_id, i.sublocation_id,
               COALESCE(s.naam, '') AS space_name,
               COALESCE(sl.naam, '') AS sublocation_name,
               COALESCE(i.status, 'active') AS status
        FROM inventory i
        LEFT JOIN spaces s ON s.id = i.space_id
        LEFT JOIN sublocations sl ON sl.id = i.sublocation_id
        WHERE i.household_id = :household_id
          AND (i.household_article_id IN :article_ids
               OR (i.household_article_id IS NULL
                   AND lower(trim(i.naam)) IN :article_names))
          AND COALESCE(i.status, 'active') = 'active'
          AND COALESCE(i.aantal, 0) > 0
        ORDER BY COALESCE(i.updated_at, i.created_at) DESC, i.id ASC
    """).bindparams(
        bindparam('article_names', expanding=True),
        bindparam('article_ids', expanding=True),
    ), args).mappings().all()

    event_rows = conn.execute(text("""
        SELECT id, article_id, household_article_id, article_name, location_id, location_label,
               event_type, quantity, old_quantity, new_quantity, source, note,
               created_at, purchase_date, supplier_name, price, currency,
               article_number, barcode
        FROM inventory_events
        WHERE household_id = :household_id
          AND (household_article_id IN :article_ids
               OR (household_article_id IS NULL AND (
                   article_id IN :article_ids
                   OR lower(trim(article_name)) IN :article_names)))
        ORDER BY created_at DESC NULLS LAST, id DESC
    """).bindparams(
        bindparam('article_ids', expanding=True),
        bindparam('article_names', expanding=True),
    ), args).mappings().all()

    purchase_rows = []
    if include_purchases:
        purchase_rows = conn.execute(text("""
            SELECT article_id, household_article_id, article_name, event_type, quantity,
                   purchase_date, created_at
            FROM inventory_events
            WHERE household_id = :household_id
              AND COALESCE(quantity, 0) > 0
              AND event_type IN ('purchase', 'auto_repurchase')
              AND (household_article_id IN :article_ids
                   OR (household_article_id IS NULL AND (
                       article_id IN :article_ids
                       OR lower(trim(article_name)) IN :article_names)))
            ORDER BY COALESCE(CAST(purchase_date AS TIMESTAMPTZ), created_at) ASC,
                     created_at ASC, id ASC
        """).bindparams(
            bindparam('article_ids', expanding=True),
            bindparam('article_names', expanding=True),
        ), args).mappings().all()

    inventory_id, inv_name = _index(
        inventory_rows, 'household_article_id', 'article_name',
        known_article_ids=known_article_ids, unique_names=unique_names,
    )
    event_id, event_name = _index(
        event_rows, 'article_id', 'article_name',
        known_article_ids=known_article_ids, unique_names=unique_names,
        allow_legacy_event_ids=True,
    )
    purchase_id, purchase_name = _index(
        purchase_rows, 'article_id', 'article_name',
        known_article_ids=known_article_ids, unique_names=unique_names,
        allow_legacy_event_ids=True,
    )
    result = {}
    for article_id, (ids, names) in members.items():
        # Canonical identities do not leak between same-name articles.
        # Truly unlinked legacy rows count only when a name is unique.
        inventory = _ordered_union(
            inventory_id, inv_name, ids,
            [name for name in names if name in unique_names],
        )
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
            'event_rows': _ordered_union(
                event_id, event_name, ids,
                [name for name in names if name in unique_names],
            ),
            'purchase_rows': _ordered_union(
                purchase_id, purchase_name, ids,
                [name for name in names if name in unique_names],
            ),
        }
    return result
