from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Query

from app.api.article_detail_admin_routes import router as article_detail_admin_router
from app.api.authorization_membership_routes import router as authorization_membership_router
from app.api.household_article_option_routes import router as household_article_option_router
from app.api.shopping_list_routes import router as shopping_list_router
from app.services.gpc_import_service import import_gs1_gpc_nl, require_admin_key
from app.services.gpc_local_catalog_service import classify_gpc_product, import_bundled_gpc_catalog
from app.services.external_product_candidate_store import promote_external_product_candidate_with_product_type
from app.services.off_product_link_service import link_off_product_with_product_type
from app.services.product_group_crud_store import create_product_group, delete_product_group, list_product_groups, update_product_group
from app.services.product_inventory_group_projection_service import list_inventory_groups_with_hierarchy
from app.services.product_inventory_group_store import assign_inventory_item_to_group, ensure_product_inventory_group_schema, link_global_product_to_inventory_group
from app.services.session_request_context import require_platform_permission_from_session

router = APIRouter()
router.include_router(article_detail_admin_router)
router.include_router(authorization_membership_router)
router.include_router(household_article_option_router)
router.include_router(shopping_list_router)


def _payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or '').strip()
        if value:
            return value
    return ''


@router.get('/api/inventory/groups')
def inventory_groups(household_id: str | None = Query(default=None)):
    return list_inventory_groups_with_hierarchy(household_id=household_id)


@router.get('/api/product-groups')
def product_groups():
    return list_product_groups()


@router.post('/api/product-groups')
def product_group_create(payload: dict[str, Any] = Body(default_factory=dict)):
    result = create_product_group(display_name=str(payload.get('display_name') or '').strip(), default_base_unit=str(payload.get('default_base_unit') or 'stuk').strip() or 'stuk', family_name=_payload_text(payload, 'gpc_family_name', 'family_name', 'hoofdgroep'), class_name=_payload_text(payload, 'gpc_class_name', 'class_name', 'groep'))
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Productgroep kon niet worden toegevoegd')
    return result


@router.put('/api/product-groups/{inventory_group_key:path}')
def product_group_update(inventory_group_key: str, payload: dict[str, Any] = Body(default_factory=dict)):
    result = update_product_group(inventory_group_key=inventory_group_key, display_name=str(payload.get('display_name') or '').strip(), default_base_unit=str(payload.get('default_base_unit') or 'stuk').strip() or 'stuk', family_name=_payload_text(payload, 'gpc_family_name', 'family_name', 'hoofdgroep'), class_name=_payload_text(payload, 'gpc_class_name', 'class_name', 'groep'))
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Productgroep kon niet worden bijgewerkt')
    return result


@router.delete('/api/product-groups/{inventory_group_key:path}')
def product_group_delete(inventory_group_key: str):
    result = delete_product_group(inventory_group_key=inventory_group_key)
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Productgroep kon niet worden verwijderd')
    return result


@router.post('/api/inventory/items/{inventory_id}/group')
def inventory_item_group_assignment(inventory_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
    result = assign_inventory_item_to_group(inventory_id=inventory_id, inventory_group_key=str(payload.get('inventory_group_key') or '').strip(), source=str(payload.get('source') or 'productgroepen_ui').strip() or 'productgroepen_ui')
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikel kon niet aan productgroep worden gekoppeld')
    return result


@router.post('/api/products/{global_product_id}/inventory-group')
def product_inventory_group_link(global_product_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
    result = link_global_product_to_inventory_group(global_product_id=global_product_id, inventory_group_key=str(payload.get('inventory_group_key') or '').strip(), comparison_group_key=str(payload.get('comparison_group_key') or '').strip() or None, confidence=float(payload.get('confidence') or 1.0), source=str(payload.get('source') or 'user').strip() or 'user', confirmed_by_user=bool(payload.get('confirmed_by_user', True)))
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Voorraadgroep kon niet worden gekoppeld')
    return result


@router.post('/api/external-databases/catalog/promote-candidate-with-product-type')
def external_candidate_product_type_link(payload: dict[str, Any] = Body(default_factory=dict)):
    assignment = payload.get('product_type_assignment')
    if not isinstance(assignment, dict):
        raise HTTPException(status_code=400, detail='Producttypebeslissing is verplicht')
    try:
        result = promote_external_product_candidate_with_product_type(candidate_id=str(payload.get('candidate_id') or '').strip(), product_type_assignment=assignment, force_overwrite=bool(payload.get('force_overwrite', False)))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or result.get('reason') or 'Koppeling kon niet worden opgeslagen')
    return result


@router.post('/api/external-products/gpc/classify')
def external_product_gpc_classify(payload: dict[str, Any] = Body(default_factory=dict)):
    return classify_gpc_product(product_name=_payload_text(payload, 'product_name', 'candidate_name', 'name'), category=_payload_text(payload, 'category', 'categories'), explicit_gpc_brick_code=_payload_text(payload, 'gpc_brick_code', 'gpcCategoryCode'))


@router.post('/api/external-products/off/link')
def external_off_product_type_link(payload: dict[str, Any] = Body(default_factory=dict)):
    assignment = payload.get('product_type_assignment')
    if not isinstance(assignment, dict):
        raise HTTPException(status_code=400, detail='Producttypebeslissing is verplicht')
    try:
        result = link_off_product_with_product_type(receipt_item_id=str(payload.get('receipt_item_id') or '').strip(), off_product=payload.get('off_product') or {}, product_type_assignment=assignment)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@router.post('/api/admin/inventory/groups/ensure-schema')
def inventory_groups_ensure_schema(authorization: str | None = Header(default=None)):
    require_platform_permission_from_session(
        'platform.technical_configuration.manage',
        authorization,
    )
    ensure_product_inventory_group_schema()
    return {'ok': True, 'schema': 'product_inventory_groups', 'seed': 'm2c2i30a_seed', 'mutates_inventory': False}


@router.post('/api/admin/product-groups/import-gpc-en-bundled')
def admin_product_groups_import_gpc_en_bundled(x_rezzerv_admin_key: str | None = Header(default=None)):
    try:
        require_admin_key(x_rezzerv_admin_key)
        return import_bundled_gpc_catalog()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Gebundelde GS1 GPC-import is mislukt: {exc}') from exc


@router.post('/api/admin/product-groups/import-gpc-nl')
def admin_product_groups_import_gpc_nl(authorization: str | None = Header(default=None)):
    require_platform_permission_from_session(
        'platform.technical_configuration.manage',
        authorization,
    )
    try:
        return import_gs1_gpc_nl()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'GS1 GPC NL-import is mislukt: {exc}') from exc
