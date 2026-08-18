from __future__ import annotations

from types import ModuleType
from typing import Any, Callable


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
        article_rows = conn.execute(
            text(
                f'''
                SELECT
                    ha.id,
                    ha.naam,
                    ha.custom_name,
                    COALESCE(gp.name, '') AS product_name
                FROM household_articles ha
                LEFT JOIN global_products gp ON gp.id = ha.global_product_id
                WHERE ha.id IN ({placeholders})
                '''
            ),
            params,
        ).mappings().all()

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
        row['household_article_name'] = custom_name or canonical_name or str(row.get('artikel') or '')
        row['product_name'] = product_name or canonical_name or str(row.get('artikel') or '')
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
