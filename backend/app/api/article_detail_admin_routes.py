from __future__ import annotations

from inspect import signature
from typing import Any, get_type_hints

from fastapi import APIRouter, Body, Header, HTTPException, Request

from app.services.household_alias_policy import install_household_alias_policy

router = APIRouter()


@router.on_event('startup')
def install_article_detail_household_alias_policy() -> None:
    # The router is imported while app.main is still being defined. At startup the
    # module is complete, so the legacy enrichment helpers can safely be wrapped.
    import app.main as main_module

    install_household_alias_policy(main_module)


def _main_route_endpoint(request: Request, path: str, method: str):
    wanted_method = str(method or '').upper()
    for route in request.app.routes:
        if getattr(route, 'path', None) != path:
            continue
        if wanted_method not in set(getattr(route, 'methods', set()) or set()):
            continue
        endpoint = getattr(route, 'endpoint', None)
        if endpoint is not None and getattr(endpoint, '__module__', '') == 'app.main':
            return endpoint
    raise HTTPException(status_code=500, detail=f'Interne Artikeldetail-route ontbreekt: {method} {path}')


def _require_admin(endpoint, authorization: str | None) -> dict[str, Any]:
    require_admin = getattr(endpoint, '__globals__', {}).get('require_household_admin_context')
    if not callable(require_admin):
        raise HTTPException(status_code=500, detail='Interne admin-autorisatie is niet beschikbaar')
    return require_admin(authorization)


def _payload_model(endpoint, payload: dict[str, Any]):
    try:
        annotation = get_type_hints(endpoint, globalns=getattr(endpoint, '__globals__', {})).get('payload')
    except Exception:
        annotation = signature(endpoint).parameters.get('payload').annotation
    if annotation is None:
        raise HTTPException(status_code=500, detail='Interne payloaddefinitie ontbreekt')
    if hasattr(annotation, 'model_validate'):
        return annotation.model_validate(payload)
    return annotation(**payload)


def _assert_inventory_belongs_to_article(endpoint, context: dict[str, Any], household_article_id: str, inventory_id: str | None) -> None:
    normalized_inventory_id = str(inventory_id or '').strip()
    if not normalized_inventory_id:
        return

    globals_map = getattr(endpoint, '__globals__', {})
    engine = globals_map.get('engine')
    fetch_inventory_row = globals_map.get('fetch_inventory_row')
    resolve_existing_article_id = globals_map.get('resolve_existing_inventory_household_article_id')
    if engine is None or not callable(fetch_inventory_row) or not callable(resolve_existing_article_id):
        raise HTTPException(status_code=500, detail='Interne voorraadvalidatie is niet beschikbaar')

    household_id = str(context.get('active_household_id') or '').strip()
    with engine.begin() as conn:
        row = fetch_inventory_row(conn, inventory_id=normalized_inventory_id, household_id=household_id)
        linked_article_id = str(row.get('household_article_id') or '').strip()
        if not linked_article_id:
            article_name = str(row.get('article_name') or '').strip()
            linked_article_id = str(resolve_existing_article_id(conn, household_id, article_name) or '').strip()

    if linked_article_id != str(household_article_id or '').strip():
        raise HTTPException(status_code=409, detail='Voorraadregel hoort niet bij dit artikel')


def _preserve_server_owned_settings(endpoint, context: dict[str, Any], household_article_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Artikeldetail bezit geen afgeleide prijs of nog niet uitgewerkte auto_restock-policy.

    De oudere settings-service schrijft een volledig model terug. Daarom vullen we deze twee
    niet-gepresenteerde velden met de actuele serverwaarde in plaats van een mogelijk verouderde
    browserwaarde of model-default. Zo kan een wijziging aan bijvoorbeeld minimumvoorraad nooit
    de berekende prijs of een bestaande technische vlag onbedoeld wijzigen.
    """
    globals_map = getattr(endpoint, '__globals__', {})
    engine = globals_map.get('engine')
    get_settings = globals_map.get('get_household_article_settings')
    if engine is None or not callable(get_settings):
        raise HTTPException(status_code=500, detail='Interne huishoudinstellingen zijn niet beschikbaar')

    household_id = str(context.get('active_household_id') or '').strip()
    with engine.begin() as conn:
        current = get_settings(conn, household_id, str(household_article_id or '').strip()) or {}
    current_settings = current.get('settings') if isinstance(current, dict) else {}
    current_settings = current_settings if isinstance(current_settings, dict) else {}

    sanitized = dict(payload or {})
    sanitized['average_price'] = current_settings.get('average_price')
    sanitized['auto_restock'] = current_settings.get('auto_restock')
    return sanitized


@router.patch('/api/household-articles/{household_article_id}')
def update_article_detail_admin_only(
    household_article_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    endpoint = _main_route_endpoint(request, '/api/household-articles/{household_article_id}', 'PATCH')
    _require_admin(endpoint, authorization)
    return endpoint(household_article_id, _payload_model(endpoint, payload), authorization)


@router.put('/api/household-articles/{household_article_id}/settings')
def update_article_detail_settings_admin_only(
    household_article_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    endpoint = _main_route_endpoint(request, '/api/household-articles/{household_article_id}/settings', 'PUT')
    context = _require_admin(endpoint, authorization)
    sanitized_payload = _preserve_server_owned_settings(endpoint, context, household_article_id, payload)
    return endpoint(household_article_id, _payload_model(endpoint, sanitized_payload), authorization)


@router.post('/api/household-articles/{household_article_id}/inventory-events')
def mutate_article_detail_inventory_admin_only(
    household_article_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    endpoint = _main_route_endpoint(request, '/api/inventory-events', 'POST')
    context = _require_admin(endpoint, authorization)
    _assert_inventory_belongs_to_article(endpoint, context, household_article_id, payload.get('inventory_id'))
    return endpoint(_payload_model(endpoint, payload), authorization)


@router.post('/api/household-articles/{household_article_id}/inventory-transfers')
def transfer_article_detail_inventory_admin_only(
    household_article_id: str,
    request: Request,
    payload: dict[str, Any] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
):
    endpoint = _main_route_endpoint(request, '/api/inventory-transfers', 'POST')
    context = _require_admin(endpoint, authorization)
    _assert_inventory_belongs_to_article(endpoint, context, household_article_id, payload.get('inventory_id'))
    return endpoint(_payload_model(endpoint, payload), authorization)
