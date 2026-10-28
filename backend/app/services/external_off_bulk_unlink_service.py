"""Explicit, atomic bulk unlink of central OFF article relations from ED2.

Never change the OFF/Catalogus product, receipt/import source, household
article, candidate history or inventory. The old candidate-unlink endpoint
has different semantics and must not be reused here.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_unlinked_articles_service import list_all_external_articles


MAX_BULK_UNLINK = 100


def unlink_selected_off_article_links(selections: Any) -> dict[str, Any]:
    if not isinstance(selections, list) or not 1 <= len(selections) <= MAX_BULK_UNLINK:
        raise ValueError(f'Selecteer 1 tot {MAX_BULK_UNLINK} bonartikelen om te ontkoppelen.')

    expected: dict[str, str] = {}
    for value in selections:
        if not isinstance(value, dict):
            raise ValueError('Ongeldige artikelkeuze.')
        item_id = str(value.get('receipt_item_id') or '').strip()
        link_id = str(value.get('link_id') or '').strip()
        if not item_id or not link_id or len(item_id) > 255 or len(link_id) > 255 or item_id in expected:
            raise ValueError('Een selectie is ongeldig of dubbel opgegeven.')
        expected[item_id] = link_id

    with engine.begin() as conn:
        # Recalculate from the canonical receipt sources and central link
        # authority inside the same transaction. Client IDs never confer
        # permission or validate a relationship on their own.
        overview = list_all_external_articles(conn=conn)
        by_id = {row['id']: row for row in overview['items']}
        for item_id, link_id in expected.items():
            row = by_id.get(item_id)
            if not row or row.get('link_status') not in {'linked', 'classification_pending'}:
                raise ValueError('Een geselecteerd bonartikel is niet meer gekoppeld.')
            if not row.get('off_link_id') or row['off_link_id'] != link_id:
                raise ValueError('De OFF-koppeling is gewijzigd. Vernieuw de lijst en selecteer opnieuw.')

        link_ids = set(expected.values())
        # A central link may represent several bonartikel rows. Never silently
        # unlink rows outside the user's explicit selection.
        affected_ids = {row['id'] for row in overview['items'] if row.get('off_link_id') in link_ids}
        if affected_ids != set(expected):
            raise ValueError('De koppeling wordt door meer bonartikelen gebruikt. Selecteer ook die regels.')

        for link_id in sorted(link_ids):
            update = conn.execute(text("""
                UPDATE external_article_product_links
                SET status = 'inactive',
                    confirmed_by = 'external_databases_off_unlinked',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :link_id
                  AND status IN ('confirmed', 'classification_pending')
                  AND confirmed_by IN (
                    'external_databases_off_link',
                    'external_databases_off_manual_link',
                    'external_databases_off_pending_gpc'
                  )
            """), {'link_id': link_id})
            if int(update.rowcount or 0) != 1:
                raise ValueError('De koppeling is tussentijds gewijzigd. Er is niets ontkoppeld.')

        # Refuse success if a historical matching link or GTIN fallback would
        # immediately make an article look coupled again. Raising here rolls
        # back the entire batch, including the first updated link.
        refreshed = {row['id']: row for row in list_all_external_articles(conn=conn)['items']}
        if any(refreshed.get(item_id, {}).get('link_status') != 'unlinked' for item_id in expected):
            raise ValueError('Een oudere koppeling blijft actief. De bulkactie is veilig teruggedraaid.')

    return {
        'ok': True,
        'unlinked_articles': len(expected),
        'unlinked_links': len(link_ids),
        'mutates_receipt_or_inventory': False,
    }
