"""Confirm a missing official GS1 GPC Brick for one staged ED2 OFF identity.

The pending OFF link and catalog product are revalidated under one transaction.
The existing canonical product-type and GPC assignment writers are reused so
Kassa/Voorraad may only see the link after all required authorities agree.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.automatic_product_type_service import gpc_brick_conflict, persist_product_type
from app.services.external_article_product_link_service import _complete_global_product_link_data
from app.services.external_product_identity_policy import assert_external_product_identity_compatible
from app.services.external_unlinked_articles_service import list_all_external_articles
from app.services.off_product_link_service import (
    _ensure_official_gpc_product_type,
    _persist_global_product_gpc_assignment,
)
from app.services.product_inventory_group_store import link_global_product_to_inventory_group_with_connection


def classify_pending_off_article(*, receipt_item_id: Any, link_id: Any, brick_code: Any) -> dict[str, Any]:
    article_id = str(receipt_item_id or '').strip()
    expected_link = str(link_id or '').strip()
    brick = str(brick_code or '').strip()
    if not article_id or len(article_id) > 255 or not expected_link or len(expected_link) > 255:
        raise ValueError('Kies opnieuw het bonartikel dat op classificatie wacht.')
    if not re.fullmatch(r'[0-9]{8}', brick):
        raise ValueError('Kies een officiële GS1 GPC Brickcode van acht cijfers.')

    with engine.begin() as conn:
        overview = list_all_external_articles(conn=conn)
        source = next((row for row in overview['items'] if row.get('id') == article_id), None)
        if (not source or source.get('link_status') != 'classification_pending'
                or source.get('off_link_id') != expected_link
                or not source.get('pending_global_product_id')):
            raise ValueError('De koppeling of classificatiestatus is gewijzigd. Vernieuw de lijst.')

        link = conn.execute(text("""
            SELECT link.id, link.global_product_id, link.confirmed_by,
                   gp.name, COALESCE(gp.brand, '') AS brand,
                   gp.primary_gtin, COALESCE(gp.status, 'active') AS product_status
            FROM external_article_product_links link
            JOIN global_products gp ON gp.id = link.global_product_id
            WHERE link.id = :link_id
              AND link.status = 'classification_pending'
              AND link.confirmed_by = 'external_databases_off_pending_gpc'
            FOR UPDATE OF link, gp
        """), {'link_id': expected_link}).mappings().first()
        if (not link or str(link['global_product_id']) != source['pending_global_product_id']
                or str(link.get('product_status') or '').lower() != 'active'):
            raise ValueError('De OFF-koppeling is niet meer beschikbaar. Vernieuw de lijst.')

        product_id = str(link['global_product_id'])
        completeness = _complete_global_product_link_data(conn, product_id)
        if (completeness.get('is_generic_catalog_product')
                or not completeness.get('has_valid_primary_gtin')
                or not completeness.get('has_matching_gtin_identity')
                or completeness.get('has_active_official_gpc')):
            raise ValueError('Dit artikel is niet langer een ongeclassificeerd exact Catalogusproduct.')

        assert_external_product_identity_compatible(
            retailer_code=source.get('retailer_code'),
            receipt_text=source.get('receipt_line_text'),
            candidate_brand=link.get('brand'),
            candidate_name=link.get('name'),
        )
        conflict = gpc_brick_conflict({'name': link.get('name'), 'brand': link.get('brand')}, brick)
        if conflict:
            raise ValueError(conflict)

        existing = conn.execute(text("""
            SELECT brick_code FROM global_product_gpc_bricks
            WHERE global_product_id = :product_id LIMIT 1
        """), {'product_id': product_id}).mappings().first()
        if existing and str(existing.get('brick_code') or '') != brick:
            raise ValueError('Het Catalogusproduct heeft al een andere GS1-classificatie. Controleer eerst de Catalogus.')

        # All writers use the same transaction: no partial classification,
        # no household/receipt/inventory writes and no new schema objects.
        product_type_id = _ensure_official_gpc_product_type(conn, brick)
        membership = link_global_product_to_inventory_group_with_connection(
            conn,
            global_product_id=product_id,
            inventory_group_key=product_type_id,
            comparison_group_key=product_type_id,
            confidence=1.0,
            source='manual_gs1_gpc',
            confirmed_by_user=True,
        )
        if not membership.get('ok'):
            raise ValueError(str(membership.get('error') or 'GS1-producttype kon niet worden gekoppeld.'))
        _persist_global_product_gpc_assignment(
            conn, global_product_id=product_id, brick_code=brick,
            gpc_source='manual', confidence=1.0,
        )
        persist_product_type(conn, product_id, {
            'name': link.get('name'), 'brand': link.get('brand'),
            'gtin': link.get('primary_gtin'),
        }, brick)

        refreshed = next((row for row in list_all_external_articles(conn=conn)['items']
                          if row.get('id') == article_id), None)
        if not refreshed or refreshed.get('link_status') != 'linked':
            raise ValueError('De officiële classificatie activeert de koppeling niet. Wijzigingen zijn teruggedraaid.')

    return {
        'ok': True,
        'linked': True,
        'receipt_item_id': article_id,
        'global_product_id': product_id,
        'gpc_brick_code': brick,
        'mutates_receipt_or_inventory': False,
    }
