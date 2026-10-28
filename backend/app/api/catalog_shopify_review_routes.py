"""Explicit Shopify v2026-08 review of existing GTIN-coded central products."""
from __future__ import annotations

import re
import threading
import time
import uuid
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.db import engine
from app.services.gtin_validation_service import is_valid_gtin
from app.services.off_search_service import lookup_off_product_by_gtin
from app.services.session_request_context import require_platform_permission_from_session

router = APIRouter(prefix='/shopify', tags=['catalog-shopify'])
_OFF_LOCK = threading.Lock()
_LAST_OFF = 0.0
TAXONOMY_VERSION = '2026-08'

class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    global_product_id: str = Field(min_length=1, max_length=200)
    expected_gtin: str = Field(min_length=8, max_length=14)
    shopify_id: str = Field(pattern=r'^[a-z]{2}(?:-[0-9]+)+$', max_length=80)
    expected_version: int = Field(ge=0)
    barcode_confirmed: bool

class Batch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[Decision] = Field(min_length=1, max_length=100)

class RemovalDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    global_product_id: str = Field(min_length=1, max_length=200)
    expected_gtin: str = Field(min_length=8, max_length=14)
    expected_version: int = Field(ge=1)

class RemovalBatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    selections: list[RemovalDecision] = Field(min_length=1, max_length=100)

def _actor(permission):
    context = require_platform_permission_from_session(permission)
    if not (context.is_platform_superuser or context.is_frontteam):
        raise HTTPException(403, 'Alleen Superusers en Frontteamleden mogen artikelclassificaties beoordelen.')
    if context.is_platform_superuser and context.context_type != 'system':
        raise HTTPException(403, 'Systeemcontext van Superuser is vereist.')
    if context.is_frontteam and not context.is_platform_superuser and context.context_type != 'regular':
        raise HTTPException(403, 'Reguliere Frontteamcontext is vereist.')
    return context

def _valid_gtin(gtin):
    value = str(gtin or '')
    return bool(re.fullmatch(r'(?:[0-9]{8}|[0-9]{12}|[0-9]{13}|[0-9]{14})', value)) and is_valid_gtin(value)

@lru_cache(maxsize=1)
def _indexes():
    from tools.inhuis_taxonomy_proof6_core import load_indexes
    return load_indexes()

def _reference():
    try:
        return _indexes()
    except (RuntimeError, FileNotFoundError, ImportError, OSError) as exc:
        raise HTTPException(503, 'Artikelclassificatiereferentie niet beschikbaar; er is niets gewijzigd.') from exc

def _product(conn, product_id, lock=False):
    row = conn.execute(text('''
        SELECT id, name, primary_gtin, status FROM global_products
        WHERE id = :id
    ''' + (' FOR UPDATE' if lock else '')), {'id': product_id}).mappings().first()
    if not row or str(row['status'] or '').lower() == 'deleted' or not _valid_gtin(row['primary_gtin']):
        raise HTTPException(409, 'Bestaand Catalogusartikel of barcode is gewijzigd. Ververs de lijst.')
    return row

@router.get('')
def list_reviews(search: str = Query(default='', max_length=100),
                 offset: int = Query(default=0, ge=0),
                 limit: int = Query(default=100, ge=1, le=100)):
    _actor('platform.external_products.view')
    with engine.connect() as conn:
        rows = conn.execute(text('''
            SELECT gp.id, gp.name, gp.brand, gp.primary_gtin, gp.status,
                   CASE WHEN c.is_active THEN c.shopify_id ELSE NULL END AS shopify_id,
                   CASE WHEN c.is_active THEN c.shopify_path ELSE NULL END AS shopify_path,
                   c.version
            FROM global_products gp
            LEFT JOIN global_product_shopify_classifications c
              ON c.global_product_id = gp.id
            WHERE gp.primary_gtin IS NOT NULL AND TRIM(gp.primary_gtin) <> ''
            ORDER BY LOWER(gp.name), gp.id
        ''')).mappings().all()
    needle = search.strip().casefold()
    items = []
    for row in rows:
        if str(row['status'] or '').lower() == 'deleted' or not _valid_gtin(row['primary_gtin']):
            continue
        if needle and not any(needle in str(row[key] or '').casefold() for key in ('name', 'brand', 'primary_gtin')):
            continue
        items.append({
            'id': str(row['id']), 'name': str(row['name'] or ''),
            'brand': str(row['brand'] or ''), 'gtin': str(row['primary_gtin']),
            'shopify_id': str(row['shopify_id'] or ''),
            'shopify_path': str(row['shopify_path'] or ''),
            'version': int(row['version'] or 0),
        })
    return {'items': items[offset:offset + limit], 'total': len(items)}

@router.get('/categories')
def categories(query: str = Query(min_length=2, max_length=100),
               limit: int = Query(default=40, ge=1, le=50)):
    _actor('platform.external_products.view')
    nl = _reference()[0]
    needle = ' '.join(query.casefold().split())
    matches = [{'id': c['id'], 'name': c['naam'], 'path': c['pad']} for c in nl.values()
               if needle in str(c['pad']).casefold()
               or needle in str(c['naam']).casefold()
               or needle == str(c['id']).casefold()]
    matches.sort(key=lambda c: (c['name'].casefold() != needle, len(c['path']), c['path']))
    return {'items': matches[:limit], 'total': len(matches), 'taxonomy_version': TAXONOMY_VERSION}

@router.get('/{product_id}/proposal')
def proposal(product_id: str):
    _actor('platform.external_products.search')
    with engine.connect() as conn:
        product = _product(conn, product_id)
        gtin, name = str(product['primary_gtin']), str(product['name'] or '')
    # No DB transaction is open while querying OFF; never retrieve on table load.
    global _LAST_OFF
    with _OFF_LOCK:
        now = time.monotonic()
        if now - _LAST_OFF < 6:
            raise HTTPException(429, 'OFF maximaal eenmaal per zes seconden opvragen.')
        _LAST_OFF = now
    off = lookup_off_product_by_gtin(gtin)
    if off.get('status') != 'found' or not off.get('product'):
        return {'gtin': gtin, 'status': str(off.get('status') or 'unavailable'),
                'shopify_id': '', 'shopify_path': '',
                'message': 'Geen exact OFF-product gevonden. Kies eventueel handmatig.'}
    from tools.inhuis_taxonomy_proof7_core import classify_proof7
    indexes = _reference()
    classified = classify_proof7(off['product'], name, indexes)
    code = str(classified.get('shopify_id') or '')
    if code and code not in indexes[0]:
        raise HTTPException(503, 'Shopify-categorie uit OFF ontbreekt in de officiële referentie.')
    return {
        'gtin': gtin, 'status': classified['status'], 'shopify_id': code,
        'shopify_path': indexes[0][code]['pad'] if code else '',
        'warning': classified.get('waarschuwing') or '',
        'alternatives': classified.get('alternatieven') or '',
        'evidence': classified.get('bewijs') or '',
        'message': 'Onbevestigd OFF-voorstel. Controleer zelf product en barcode.',
    }

@router.post('/bulk-confirm')
def confirm_batch(payload: Batch):
    actor = _actor('platform.external_products.link_existing')
    nl = _reference()[0]
    decisions = sorted(payload.selections, key=lambda entry: entry.global_product_id)
    if len({decision.global_product_id for decision in decisions}) != len(decisions):
        raise HTTPException(422, 'Dubbele artikelen in selectie zijn niet toegestaan.')
    for d in decisions:
        if not d.barcode_confirmed or not _valid_gtin(d.expected_gtin):
            raise HTTPException(422, 'Bevestig iedere bestaande geldige barcode.')
        if d.shopify_id not in nl:
            raise HTTPException(422, 'Ongeldige Shopify-categorie of referentieversie.')
    # Locks on global_products serialize concurrent reviewer changes, including
    # an initial classification insert. Any rejection rolls back the WHOLE batch.
    with engine.begin() as conn:
        prepared = []
        for d in decisions:
            product = _product(conn, d.global_product_id, lock=True)
            if str(product['primary_gtin']) != d.expected_gtin:
                raise HTTPException(409, 'Barcode gewijzigd; geen enkele classificatie opgeslagen.')
            current = conn.execute(text('''
                SELECT version FROM global_product_shopify_classifications
                WHERE global_product_id = :id FOR UPDATE
            '''), {'id': d.global_product_id}).scalar()
            if int(current or 0) != d.expected_version:
                raise HTTPException(409, 'Bevestigde categorie is gewijzigd; geen enkele classificatie opgeslagen.')
            prepared.append((d, int(current or 0) + 1))
        for d, version in prepared:
            values = {
                'id': d.global_product_id, 'code': d.shopify_id,
                'path': nl[d.shopify_id]['pad'], 'taxonomy': TAXONOMY_VERSION,
                'gtin': d.expected_gtin, 'version': version, 'actor': str(actor.user_id),
            }
            if version == 1:
                conn.execute(text('''
                    INSERT INTO global_product_shopify_classifications
                      (global_product_id, shopify_id, shopify_path, taxonomy_version,
                       barcode_at_confirmation, version, confirmed_by, confirmed_at)
                    VALUES (:id, :code, :path, :taxonomy, :gtin, :version, :actor, CURRENT_TIMESTAMP)
                '''), values)
            else:
                conn.execute(text('''
                    UPDATE global_product_shopify_classifications
                       SET shopify_id = :code, shopify_path = :path,
                           taxonomy_version = :taxonomy, barcode_at_confirmation = :gtin,
                           version = :version, is_active = TRUE, confirmed_by = :actor,
                           confirmed_at = CURRENT_TIMESTAMP
                     WHERE global_product_id = :id
                '''), values)
            conn.execute(text('''
                INSERT INTO global_product_shopify_history
                  (id, global_product_id, shopify_id, shopify_path,
                   taxonomy_version, barcode_at_confirmation,
                   version, confirmed_by, confirmed_at)
                VALUES (:audit_id, :id, :code, :path, :taxonomy, :gtin,
                        :version, :actor, CURRENT_TIMESTAMP)
            '''), {**values, 'audit_id': str(uuid.uuid4())})
    return {'confirmed': len(prepared), 'taxonomy_version': TAXONOMY_VERSION}


@router.post('/bulk-remove')
def remove_batch(payload: RemovalBatch):
    """Deactivate only selected confirmed categories, preserving audit and concurrency version."""
    actor = _actor('platform.external_products.link_existing')
    decisions = sorted(payload.selections, key=lambda item: item.global_product_id)
    if len({item.global_product_id for item in decisions}) != len(decisions):
        raise HTTPException(422, 'Dubbele artikelen in selectie zijn niet toegestaan.')
    with engine.begin() as conn:
        prepared = []
        for decision in decisions:
            if not _valid_gtin(decision.expected_gtin):
                raise HTTPException(422, 'Ongeldige bestaande barcode.')
            product = _product(conn, decision.global_product_id, lock=True)
            if str(product['primary_gtin']) != decision.expected_gtin:
                raise HTTPException(409, 'Barcode gewijzigd; geen classificaties verwijderd.')
            current = conn.execute(text("""
                SELECT shopify_id, shopify_path, taxonomy_version, version, is_active
                FROM global_product_shopify_classifications
                WHERE global_product_id = :id FOR UPDATE
            """), {'id': decision.global_product_id}).mappings().first()
            if not current or not current['is_active']:
                raise HTTPException(409, 'Geen bevestigde artikelclassificatie meer aanwezig. Ververs de tabel.')
            if int(current['version']) != decision.expected_version:
                raise HTTPException(409, 'Artikelclassificatie is gewijzigd; geen classificaties verwijderd.')
            prepared.append((decision, current))
        for decision, current in prepared:
            new_version = int(current['version']) + 1
            params = {
                'id': decision.global_product_id,
                'expected': decision.expected_version,
                'version': new_version,
                'gtin': decision.expected_gtin,
                'code': current['shopify_id'],
                'path': current['shopify_path'],
                'taxonomy': current['taxonomy_version'],
                'actor': str(actor.user_id),
                'audit_id': str(uuid.uuid4()),
            }
            affected = conn.execute(text("""
                UPDATE global_product_shopify_classifications
                   SET is_active = FALSE, version = :version
                 WHERE global_product_id = :id AND version = :expected AND is_active = TRUE
            """), params)
            if affected.rowcount != 1:
                raise HTTPException(409, 'Artikelclassificatie is tussentijds gewijzigd. Niets verwijderd.')
            conn.execute(text("""
                INSERT INTO global_product_shopify_history
                  (id, global_product_id, shopify_id, shopify_path,
                   taxonomy_version, barcode_at_confirmation,
                   version, confirmed_by, confirmed_at, action)
                VALUES (:audit_id, :id, :code, :path, :taxonomy, :gtin,
                        :version, :actor, CURRENT_TIMESTAMP, 'removed')
            """), params)
    return {'removed': len(prepared)}
