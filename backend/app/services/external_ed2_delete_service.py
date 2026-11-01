"""Atomic, fail-closed removal from ED2 and the active central Catalogus.

Preserve source receipts, purchase imports, household articles, inventory and history.
Never delete a shared Catalogus product through a single ED2 selection.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import inspect, text

from app.db import engine
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code,
    normalize_external_link_receipt_text,
)
from app.services.external_unlinked_articles_service import _overview_retailer_code, list_all_external_articles


MAX_DELETE = 100


def _presentation_key(row: dict) -> tuple[str, str, str]:
    # These are *display identity* fields, not household article identity.
    # Text spelling and case remain distinct, as in the canonical ED2 overview.
    return (
        str(row.get("retailer_code") or ""),
        str(row.get("receipt_line_text") or ""),
        str(row.get("receipt_article_number") or ""),
    )


def _link_belongs_to_selection(link: dict, selections: list[dict]) -> bool:
    for row in selections:
        retailer, label, code = _presentation_key(row)
        if _overview_retailer_code(retailer) != _overview_retailer_code(link.get("retailer_code")):
            continue
        normalized_code = normalize_external_link_article_code(code)
        normalized_label = normalize_external_link_receipt_text(label)
        if normalized_code and normalized_code == str(link.get("external_article_code") or ""):
            return True
        if normalized_label and normalized_label == str(link.get("receipt_text_normalized") or ""):
            return True
    return False


def remove_selected_ed2_articles(selections: Any) -> dict[str, Any]:
    """Archive the exact overview rows and soft-delete exclusively linked products.

    All sources/relationships are reread on the server, within one transaction.
    Any conflict rolls back *all* selected rows and Catalogus status changes.
    """
    if not isinstance(selections, list) or not 1 <= len(selections) <= MAX_DELETE:
        raise ValueError(f'Selecteer 1 tot {MAX_DELETE} artikelen om te verwijderen.')

    selected_ids = []
    for value in selections:
        if not isinstance(value, dict):
            raise ValueError('Ongeldige artikelkeuze.')
        item_id = str(value.get('receipt_item_id') or '').strip()
        if not item_id or len(item_id) > 255 or item_id in selected_ids:
            raise ValueError('De selectie bevat een ongeldig of dubbel artikel.')
        selected_ids.append(item_id)

    with engine.begin() as conn:
        tables = set(inspect(conn).get_table_names())
        if not {"ed2_removed_articles", "global_products", "external_article_product_links"}.issubset(tables):
            raise ValueError('De verwijderfunctie is nog niet volledig beschikbaar. Er is niets gewijzigd.')

        overview = list_all_external_articles(conn=conn)
        by_id = {row['id']: row for row in overview['items']}
        selected = []
        for item_id in selected_ids:
            row = by_id.get(item_id)
            if row is None:
                raise ValueError('Een artikel is gewijzigd of niet meer zichtbaar. Vernieuw de lijst.')
            selected.append(row)
        selected_keys = [_presentation_key(row) for row in selected]
        if len(set(selected_keys)) != len(selected_keys):
            raise ValueError('De selectie bevat een dubbel artikel.')

        product_ids = {
            str(row.get('catalog_product_id') or '').strip()
            for row in selected if str(row.get('catalog_product_id') or '').strip()
        }
        # An ED2 row can refer to the same Catalogus product as another row.
        # A single product must never be hidden while some of its ED2 rows remain.
        affected_not_selected = [
            row for row in overview['items']
            if str(row.get('catalog_product_id') or '') in product_ids
            and row['id'] not in selected_ids
        ]
        if affected_not_selected:
            raise ValueError(
                'Dit Catalogusartikel wordt ook door andere bonartikelen gebruikt. '
                'Selecteer alle betrokken regels of annuleer de verwijdering.'
            )

        for product_id in sorted(product_ids):
            lock = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
            product = conn.execute(text(
                "SELECT id, status FROM global_products WHERE id = :id" + lock
            ), {"id": product_id}).mappings().first()
            if not product or str(product.get("status") or "").strip().lower() != "active":
                raise ValueError('Het Catalogusartikel is tussentijds gewijzigd. Er is niets verwijderd.')

            if "article_synonym_links" in tables:
                synonym = conn.execute(text("""
                    SELECT 1 FROM article_synonym_links
                    WHERE left_product_id = :id OR right_product_id = :id LIMIT 1
                """), {"id": product_id}).first()
                if synonym:
                    raise ValueError(
                        'Dit Catalogusartikel heeft artikelsynoniemen. '
                        'Verwijderen kan andere artikelen raken en is daarom geblokkeerd.'
                    )

            links = conn.execute(text("""
                SELECT id, retailer_code, receipt_text_normalized, external_article_code
                FROM external_article_product_links
                WHERE global_product_id = :id
                  AND status IN ('confirmed', 'classification_pending')
            """), {"id": product_id}).mappings().all()
            if any(not _link_belongs_to_selection(link, selected) for link in links):
                raise ValueError(
                    'Dit Catalogusartikel is ook aan andere winkelartikelen gekoppeld. '
                    'Er is niets verwijderd.'
                )

        for retailer, label, code in selected_keys:
            # The registry is presentation-scoped only. Never rewrite source rows.
            conn.execute(text("""
                INSERT INTO ed2_removed_articles
                    (retailer_code, receipt_text, external_article_code, removed_at)
                VALUES (:retailer, :label, :code, CURRENT_TIMESTAMP)
            """), {"retailer": retailer, "label": label, "code": code})

        for product_id in sorted(product_ids):
            conn.execute(text("""
                UPDATE external_article_product_links
                SET status = 'inactive', updated_at = CURRENT_TIMESTAMP
                WHERE global_product_id = :id
                  AND status IN ('confirmed', 'classification_pending')
            """), {"id": product_id})
            changed = conn.execute(text("""
                UPDATE global_products
                SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND LOWER(COALESCE(status, '')) = 'active'
            """), {"id": product_id})
            if int(changed.rowcount or 0) != 1:
                raise ValueError('Het Catalogusartikel is tussentijds gewijzigd. Verwijderen teruggedraaid.')

        remaining = {
            row['id'] for row in list_all_external_articles(conn=conn)['items']
        }
        if any(item_id in remaining for item_id in selected_ids):
            raise ValueError('Het artikel is nog zichtbaar. Alle wijzigingen zijn teruggedraaid.')

    return {
        'ok': True,
        'removed_articles': len(selected_ids),
        'removed_catalog_products': len(product_ids),
        'mutates_receipt_or_inventory': False,
    }
