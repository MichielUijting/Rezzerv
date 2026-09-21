from __future__ import annotations

from types import ModuleType
from typing import Any, Callable

from app.services.external_article_product_link_service import (
    normalize_external_link_article_code,
    normalize_external_link_receipt_text,
    normalize_external_link_retailer_code,
)
from app.services.household_representative_image_service import (
    materialize_household_representative_images,
)


_POLICY_MARKER = '_rezzerv_household_alias_policy_installed'
_INVENTORY_PREVIEW_MARKER = '_rezzerv_household_alias_inventory_preview_installed'
_INVENTORY_UPDATE_MARKER = '_rezzerv_household_alias_inventory_update_installed'


def _route_for(main_module: ModuleType, path: str, method: str):
    app = getattr(main_module, 'app', None)
    if app is None:
        return None
    wanted_method = str(method or '').upper()
    for route in getattr(app, 'routes', []) or []:
        if getattr(route, 'path', None) != path:
            continue
        if wanted_method not in set(getattr(route, 'methods', set()) or set()):
            continue
        return route
    return None



def _normalize_catalog_gtin(value: Any) -> str:
    return ''.join(character for character in str(value or '') if character.isdigit())


def _canonical_catalog_images_for_household_articles(conn, text, article_rows: list[dict[str, Any]]) -> dict[str, str]:
    """Resolve images from canonical household/product identities without guessing by name.

    Some existing households predate household_articles.global_product_id. They can still
    have a canonical product_identities link or a stored GTIN/barcode. Those identities
    are safe to use for read-only image projection because they identify the exact
    Catalogus product. Ambiguous identity history fails closed.
    """
    unresolved_rows = [
        dict(row)
        for row in article_rows
        if str(row.get('id') or '').strip() and not str(row.get('image_url') or '').strip()
    ]
    if not unresolved_rows:
        return {}

    article_ids = [str(row.get('id') or '').strip() for row in unresolved_rows]
    placeholders = ', '.join(f':canonical_article_id_{index}' for index in range(len(article_ids)))
    params = {
        f'canonical_article_id_{index}': article_id
        for index, article_id in enumerate(article_ids)
    }

    products_by_article: dict[str, dict[str, str]] = {
        article_id: {}
        for article_id in article_ids
    }

    identity_rows = conn.execute(
        text(
            f'''
            SELECT
                pi.household_article_id,
                pi.global_product_id,
                COALESCE(gp.image_url, '') AS image_url
            FROM product_identities pi
            JOIN global_products gp ON gp.id = pi.global_product_id
            WHERE pi.household_article_id IN ({placeholders})
              AND pi.global_product_id IS NOT NULL
              AND lower(COALESCE(gp.status, 'active')) = 'active'
            ORDER BY pi.is_primary DESC, pi.created_at DESC, pi.id DESC
            '''
        ),
        params,
    ).mappings().all()

    for identity in identity_rows:
        article_id = str(identity.get('household_article_id') or '').strip()
        product_id = str(identity.get('global_product_id') or '').strip()
        if article_id in products_by_article and product_id:
            products_by_article[article_id][product_id] = str(identity.get('image_url') or '').strip()

    articles_by_gtin: dict[str, list[str]] = {}
    for article in unresolved_rows:
        article_id = str(article.get('id') or '').strip()
        gtin = _normalize_catalog_gtin(article.get('barcode'))
        if article_id and gtin:
            articles_by_gtin.setdefault(gtin, []).append(article_id)

    if articles_by_gtin:
        gtin_placeholders = ', '.join(f':catalog_gtin_{index}' for index in range(len(articles_by_gtin)))
        gtin_params = {
            f'catalog_gtin_{index}': gtin
            for index, gtin in enumerate(sorted(articles_by_gtin))
        }
        gtin_rows = conn.execute(
            text(
                f'''
                SELECT
                    id AS global_product_id,
                    primary_gtin,
                    COALESCE(image_url, '') AS image_url
                FROM global_products
                WHERE primary_gtin IN ({gtin_placeholders})
                  AND lower(COALESCE(status, 'active')) = 'active'
                ORDER BY id
                '''
            ),
            gtin_params,
        ).mappings().all()
        for product in gtin_rows:
            gtin = _normalize_catalog_gtin(product.get('primary_gtin'))
            product_id = str(product.get('global_product_id') or '').strip()
            if not gtin or not product_id:
                continue
            for article_id in articles_by_gtin.get(gtin, []):
                products_by_article[article_id][product_id] = str(product.get('image_url') or '').strip()

    images_by_article: dict[str, str] = {}
    for article_id, products in products_by_article.items():
        if len(products) != 1:
            continue
        image_url = next(iter(products.values()))
        if image_url:
            images_by_article[article_id] = image_url
    return images_by_article

def _central_catalog_images_for_household_articles(conn, text, article_rows: list[dict[str, Any]]) -> dict[str, str]:
    """Resolve Catalogus images without mutating household-specific article links.

    Exact Catalogus links created in Externe databases are platform-wide and deliberately
    do not write household_articles.global_product_id. For Voorraad we therefore use
    the receipt/import lineage that already points at the canonical household article,
    then resolve the confirmed central external-article link for that same shop identity.

    If one household article has receipt lineage to multiple different central products,
    the projection fails closed and shows no derived image instead of guessing a photo.
    """
    unresolved = {
        str(row.get('id') or '').strip()
        for row in article_rows
        if str(row.get('id') or '').strip() and not str(row.get('image_url') or '').strip()
    }
    if not unresolved:
        return {}

    placeholders = ', '.join(f':fallback_article_id_{index}' for index in range(len(unresolved)))
    params = {
        f'fallback_article_id_{index}': article_id
        for index, article_id in enumerate(sorted(unresolved))
    }
    source_rows = conn.execute(
        text(
            f'''
            WITH source_identities AS (
                SELECT
                    pil.matched_household_article_id AS household_article_id,
                    COALESCE(NULLIF(rt.store_chain, ''), NULLIF(rt.store_name, ''), NULLIF(epc.retailer_code, ''), '') AS retailer_code,
                    COALESCE(NULLIF(pil.article_name_raw, ''), NULLIF(epc.receipt_line_text, ''), '') AS receipt_line_text,
                    COALESCE(NULLIF(pil.external_article_code, ''), NULLIF(epc.external_article_code, ''), '') AS external_article_code,
                    COALESCE(epc.updated_at, epc.created_at, pil.updated_at, pil.created_at) AS source_at
                FROM purchase_import_lines pil
                JOIN purchase_import_batches pib ON pib.id = pil.batch_id
                JOIN household_articles source_ha
                  ON source_ha.id = pil.matched_household_article_id
                 AND source_ha.household_id = pib.household_id
                LEFT JOIN external_product_candidates epc
                  ON epc.purchase_import_line_id = pil.id
                LEFT JOIN receipt_tables rt
                  ON pib.source_reference = ('receipt:' || CAST(rt.id AS TEXT))
                WHERE pil.matched_household_article_id IN ({placeholders})

                UNION ALL

                SELECT
                    rtl.matched_article_id AS household_article_id,
                    COALESCE(NULLIF(rt.store_chain, ''), NULLIF(rt.store_name, ''), NULLIF(epc.retailer_code, ''), '') AS retailer_code,
                    COALESCE(NULLIF(rtl.corrected_raw_label, ''), NULLIF(rtl.raw_label, ''), NULLIF(rtl.normalized_label, ''), NULLIF(epc.receipt_line_text, ''), '') AS receipt_line_text,
                    COALESCE(NULLIF(rtl.external_article_code, ''), NULLIF(epc.external_article_code, ''), '') AS external_article_code,
                    COALESCE(epc.updated_at, epc.created_at, rt.updated_at, rt.created_at) AS source_at
                FROM receipt_table_lines rtl
                JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
                LEFT JOIN external_product_candidates epc
                  ON epc.receipt_line_id = rtl.id
                JOIN household_articles source_ha
                  ON source_ha.id = rtl.matched_article_id
                 AND source_ha.household_id = rt.household_id
                WHERE rtl.matched_article_id IN ({placeholders})
            ), ranked AS (
                SELECT
                    household_article_id,
                    retailer_code,
                    receipt_line_text,
                    external_article_code,
                    ROW_NUMBER() OVER (
                        PARTITION BY household_article_id
                        ORDER BY source_at DESC
                    ) AS source_rank
                FROM source_identities
            )
            SELECT
                household_article_id,
                retailer_code,
                receipt_line_text,
                external_article_code,
                source_rank
            FROM ranked
            WHERE source_rank <= 8
            ORDER BY household_article_id, source_rank
            '''
        ),
        params,
    ).mappings().all()

    sources_by_article: dict[str, list[dict[str, str]]] = {}
    unique_identities: list[tuple[str, str, str]] = []
    seen_identities: set[tuple[str, str, str]] = set()
    for source in source_rows:
        article_id = str(source.get('household_article_id') or '').strip()
        retailer = normalize_external_link_retailer_code(source.get('retailer_code'))
        article_code = normalize_external_link_article_code(source.get('external_article_code'))
        receipt_text = normalize_external_link_receipt_text(source.get('receipt_line_text'))
        if not article_id or not retailer or (not article_code and not receipt_text):
            continue
        identity = (retailer, article_code, receipt_text)
        sources_by_article.setdefault(article_id, []).append({
            'retailer': retailer,
            'article_code': article_code,
            'receipt_text': receipt_text,
        })
        if identity not in seen_identities:
            seen_identities.add(identity)
            unique_identities.append(identity)

    if not unique_identities:
        return {}

    links_by_code: dict[tuple[str, str], dict[str, Any]] = {}
    links_by_text: dict[tuple[str, str], dict[str, Any]] = {}
    batch_size = 100
    for batch_start in range(0, len(unique_identities), batch_size):
        batch = unique_identities[batch_start:batch_start + batch_size]
        clauses = []
        link_params: dict[str, Any] = {}
        for index, (retailer, article_code, receipt_text) in enumerate(batch):
            suffix = f'{batch_start}_{index}'
            link_params[f'retailer_{suffix}'] = retailer
            alternatives = []
            if article_code:
                link_params[f'article_code_{suffix}'] = article_code
                alternatives.append(f'link.external_article_code = :article_code_{suffix}')
            if receipt_text:
                link_params[f'receipt_text_{suffix}'] = receipt_text
                alternatives.append(f'link.receipt_text_normalized = :receipt_text_{suffix}')
            if alternatives:
                clauses.append(
                    f"(link.retailer_code = :retailer_{suffix} AND ({' OR '.join(alternatives)}))"
                )
        if not clauses:
            continue
        link_rows = conn.execute(
            text(
                f'''
                SELECT
                    link.retailer_code,
                    link.external_article_code,
                    link.receipt_text_normalized,
                    link.global_product_id,
                    COALESCE(gp.image_url, '') AS image_url,
                    link.confirmed_at,
                    link.id
                FROM external_article_product_links link
                JOIN global_products gp ON gp.id = link.global_product_id
                WHERE link.status = 'confirmed'
                  AND lower(COALESCE(gp.status, 'active')) = 'active'
                  AND ({' OR '.join(clauses)})
                ORDER BY link.confirmed_at DESC, link.id DESC
                '''
            ),
            link_params,
        ).mappings().all()
        for link in link_rows:
            retailer = str(link.get('retailer_code') or '').strip()
            article_code = str(link.get('external_article_code') or '').strip()
            receipt_text = str(link.get('receipt_text_normalized') or '').strip()
            if article_code:
                links_by_code.setdefault((retailer, article_code), dict(link))
            if receipt_text:
                links_by_text.setdefault((retailer, receipt_text), dict(link))

    images_by_article: dict[str, str] = {}
    for article_id, sources in sources_by_article.items():
        products: dict[str, str] = {}
        for source in sources:
            link = None
            if source['article_code']:
                link = links_by_code.get((source['retailer'], source['article_code']))
            if link is None and source['receipt_text']:
                link = links_by_text.get((source['retailer'], source['receipt_text']))
            if not link:
                continue
            product_id = str(link.get('global_product_id') or '').strip()
            if product_id:
                products[product_id] = str(link.get('image_url') or '').strip()
        if len(products) == 1:
            image_url = next(iter(products.values()))
            if image_url:
                images_by_article[article_id] = image_url
    return images_by_article


def _inventory_alias_projection(main_module: ModuleType, payload: Any) -> Any:
    if not isinstance(payload, dict) or not isinstance(payload.get('rows'), list):
        return payload
    engine = getattr(main_module, 'engine', None)
    text = getattr(main_module, 'text', None)
    if engine is None or not callable(text):
        return payload

    rows = [dict(row or {}) for row in payload.get('rows') or []]
    article_ids = []
    for row in rows:
        article_id = str(row.get('household_article_id') or '').strip()
        if article_id and article_id not in article_ids:
            article_ids.append(article_id)
    if not article_ids:
        return {**payload, 'rows': rows}

    placeholders = ', '.join(f':article_id_{index}' for index in range(len(article_ids)))
    params = {f'article_id_{index}': article_id for index, article_id in enumerate(article_ids)}
    with engine.begin() as conn:
        materialized_representative_images = materialize_household_representative_images(
            conn,
            article_ids,
        )
        article_rows = conn.execute(
            text(
                f'''
                SELECT
                    ha.id,
                    ha.household_id,
                    ha.naam,
                    ha.custom_name,
                    ha.global_product_id,
                    ha.barcode,
                    ha.representative_image_url,
                    ha.representative_image_global_product_id,
                    ha.representative_image_gpc_brick_code,
                    COALESCE(gp.name, '') AS product_name,
                    COALESCE(gp.image_url, '') AS image_url
                FROM household_articles ha
                LEFT JOIN global_products gp ON gp.id = ha.global_product_id
                WHERE ha.id IN ({placeholders})
                '''
            ),
            params,
        ).mappings().all()
        canonical_images = _canonical_catalog_images_for_household_articles(conn, text, article_rows)
        central_projection_rows = [
            {
                **dict(article),
                'image_url': (
                    str(article.get('image_url') or '').strip()
                    or canonical_images.get(str(article.get('id') or '').strip(), '')
                ),
            }
            for article in article_rows
        ]
        derived_images = _central_catalog_images_for_household_articles(conn, text, central_projection_rows)

    articles_by_id = {str(row.get('id') or ''): row for row in article_rows}
    projected = []
    for row in rows:
        article_id = str(row.get('household_article_id') or '').strip()
        article = articles_by_id.get(article_id)
        if not article:
            projected.append(row)
            continue
        canonical_name = str(article.get('naam') or '').strip()
        custom_name = str(article.get('custom_name') or '').strip()
        product_name = str(article.get('product_name') or '').strip()
        image_url = (
            str(article.get('representative_image_url') or '').strip()
            or materialized_representative_images.get(article_id, '')
            or str(article.get('image_url') or '').strip()
            or canonical_images.get(article_id, '')
            or derived_images.get(article_id, '')
        )
        row['household_article_name'] = custom_name or canonical_name or str(row.get('artikel') or '')
        row['product_name'] = product_name or canonical_name or str(row.get('artikel') or '')
        row['image_url'] = image_url
        projected.append(row)
    return {**payload, 'rows': projected}


def _install_inventory_preview_projection(main_module: ModuleType) -> None:
    route = _route_for(main_module, '/api/dev/inventory-preview', 'GET')
    dependant = getattr(route, 'dependant', None) if route is not None else None
    original_call = getattr(dependant, 'call', None) if dependant is not None else None
    if not callable(original_call) or getattr(original_call, _INVENTORY_PREVIEW_MARKER, False):
        return

    def projected_endpoint(**values):
        payload = original_call(**values)
        return _inventory_alias_projection(main_module, payload)

    setattr(projected_endpoint, _INVENTORY_PREVIEW_MARKER, True)
    dependant.call = projected_endpoint


def _copy_payload_with_name(payload: Any, name: str):
    model_copy = getattr(payload, 'model_copy', None)
    if callable(model_copy):
        return model_copy(update={'naam': name})
    model_dump = getattr(payload, 'model_dump', None)
    if callable(model_dump):
        data = dict(model_dump())
        data['naam'] = name
        return type(payload)(**data)
    if isinstance(payload, dict):
        return {**payload, 'naam': name}
    return payload


def _payload_name(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get('naam') or '').strip()
    return str(getattr(payload, 'naam', '') or '').strip()


def _install_inventory_alias_update(main_module: ModuleType) -> None:
    route = _route_for(main_module, '/api/dev/inventory/{inventory_id}', 'PUT')
    dependant = getattr(route, 'dependant', None) if route is not None else None
    original_call = getattr(dependant, 'call', None) if dependant is not None else None
    engine = getattr(main_module, 'engine', None)
    text = getattr(main_module, 'text', None)
    if (
        not callable(original_call)
        or getattr(original_call, _INVENTORY_UPDATE_MARKER, False)
        or engine is None
        or not callable(text)
    ):
        return

    def alias_aware_endpoint(**values):
        inventory_id = str(values.get('inventory_id') or '').strip()
        payload = values.get('payload')
        authorization = values.get('authorization')
        requested_name = _payload_name(payload)
        require_write = getattr(main_module, 'require_inventory_write_context', None)
        if callable(require_write):
            require_write(authorization)

        inventory_row = None
        if inventory_id:
            with engine.begin() as conn:
                inventory_row = conn.execute(
                    text(
                        '''
                        SELECT id, naam, household_article_id
                        FROM inventory
                        WHERE id = :inventory_id
                        LIMIT 1
                        '''
                    ),
                    {'inventory_id': inventory_id},
                ).mappings().first()

        canonical_name = str((inventory_row or {}).get('naam') or '').strip()
        household_article_id = str((inventory_row or {}).get('household_article_id') or '').strip()
        alias_changed = bool(household_article_id and requested_name != canonical_name)
        if alias_changed:
            values['payload'] = _copy_payload_with_name(payload, canonical_name)

        result = original_call(**values)

        if alias_changed:
            custom_name = requested_name or None
            with engine.begin() as conn:
                conn.execute(
                    text(
                        '''
                        UPDATE household_articles
                        SET custom_name = :custom_name,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :household_article_id
                        '''
                    ),
                    {
                        'custom_name': custom_name,
                        'household_article_id': household_article_id,
                    },
                )
            if isinstance(result, dict) and isinstance(result.get('row'), dict):
                result = {**result, 'row': {**result['row'], 'household_article_name': custom_name or canonical_name}}
        return result

    setattr(alias_aware_endpoint, _INVENTORY_UPDATE_MARKER, True)
    dependant.call = alias_aware_endpoint


def install_household_alias_policy(main_module: ModuleType) -> None:
    """Keep household custom_name owned by the household, not product enrichment.

    The legacy enrichment helpers also populate/merge custom_name from an enriched
    product title. That conflicts with the Article detail contract where custom_name
    is an optional household alias. We wrap those two legacy helpers at application
    startup so the product title can still enrich product fields, while custom_name
    remains exactly the persisted household value.

    The legacy Voorraad preview also projects inventory.naam as the household label.
    Its canonical routes are wrapped in-place so the preview reads custom_name and an
    inline Voorraadartikel rename updates custom_name without renaming inventory.naam.

    Existing stored aliases are intentionally not migrated: historical automatic and
    user-entered values cannot be distinguished safely after the fact.
    """
    if getattr(main_module, _POLICY_MARKER, False):
        return

    original_apply: Callable[..., Any] = getattr(main_module, 'apply_household_article_defaults_from_enrichment')
    original_merge: Callable[..., dict] = getattr(main_module, 'merge_household_article_details_with_product_defaults')
    text = getattr(main_module, 'text')

    def apply_without_household_alias(conn, household_article_id: str | None, enrichment: dict | None):
        normalized_article_id = str(household_article_id or '').strip()
        original_alias = None
        alias_row_found = False
        if normalized_article_id:
            row = conn.execute(
                text('SELECT custom_name FROM household_articles WHERE id = :household_article_id LIMIT 1'),
                {'household_article_id': normalized_article_id},
            ).mappings().first()
            if row is not None:
                alias_row_found = True
                original_alias = row.get('custom_name')

        result = original_apply(conn, household_article_id, enrichment)

        if normalized_article_id and alias_row_found:
            conn.execute(
                text('UPDATE household_articles SET custom_name = :custom_name WHERE id = :household_article_id'),
                {
                    'custom_name': original_alias,
                    'household_article_id': normalized_article_id,
                },
            )
        return result

    def merge_without_household_alias(row: dict, product_details: dict | None) -> dict:
        merged = dict(original_merge(row, product_details) or {})
        merged['custom_name'] = (row or {}).get('custom_name')
        return merged

    apply_without_household_alias.__name__ = original_apply.__name__
    merge_without_household_alias.__name__ = original_merge.__name__
    main_module.apply_household_article_defaults_from_enrichment = apply_without_household_alias
    main_module.merge_household_article_details_with_product_defaults = merge_without_household_alias
    _install_inventory_preview_projection(main_module)
    _install_inventory_alias_update(main_module)
    setattr(main_module, _POLICY_MARKER, True)
