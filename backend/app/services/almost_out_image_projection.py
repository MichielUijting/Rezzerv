"""Read-only photo enrichment for visible Bijna op signals.

Priorities: own Catalogus image, verified matched-group member image, then
the existing identity/synonym resolver. Never group or match by name here.
"""
from __future__ import annotations

from app.services.household_alias_policy import resolve_household_catalog_images


def fill_visible_almost_out_photos(conn, text_factory, household_rows, visible_items):
    by_id = {str(row['id']): dict(row) for row in household_rows}
    missing_items = [
        item for item in visible_items
        if not str(item.get('image_url') or '').strip()
    ]
    if not missing_items:
        return visible_items

    # A member_article_ids list is created by the existing exact-product,
    # approved-synonym or vetted automatic-product-type grouping authority.
    candidate_ids = set()
    for item in missing_items:
        representative = str(item.get('household_article_id') or '').strip()
        candidate_ids.add(representative)
        candidate_ids.update(str(member).strip() for member in item.get('member_article_ids') or [])
    candidate_rows = [by_id[id_] for id_ in sorted(candidate_ids) if id_ in by_id]
    if not candidate_rows:
        return visible_items

    # Resolve missing product photos through existing canonical GTIN, confirmed
    # match and *directly* confirmed synonym evidence; no writes or name guesses.
    missing_rows = [row for row in candidate_rows if not str(row.get('image_url') or '').strip()]
    resolved = resolve_household_catalog_images(conn, text_factory, missing_rows) if missing_rows else {}

    for item in missing_items:
        representative = str(item.get('household_article_id') or '').strip()
        members = [
            str(member).strip() for member in item.get('member_article_ids') or []
        ]
        ordered = [representative] + sorted(set(members) - {representative})
        # A direct Catalogus image from any proven group member is preferable
        # to a related synonym substitute, but the represented article wins.
        for member_id in ordered:
            row = by_id.get(member_id)
            url = str(row.get('image_url') or '').strip() if row else ''
            if url:
                item['image_url'] = url
                break
        if not str(item.get('image_url') or '').strip():
            for member_id in ordered:
                url = str(resolved.get(member_id) or '').strip()
                if url:
                    item['image_url'] = url
                    break
    return visible_items
