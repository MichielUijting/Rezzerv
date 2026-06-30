from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Query

from app.services.gpc_import_service import import_gs1_gpc_nl, require_admin_key
from app.services.product_group_crud_store import (
    create_product_group,
    delete_product_group,
    list_product_groups,
    update_product_group,
)
from app.services.product_inventory_group_projection_service import list_inventory_groups_with_hierarchy
from app.services.product_inventory_group_store import (
    assign_inventory_item_to_group,
    ensure_product_inventory_group_schema,
    link_global_product_to_inventory_group,
)

router = APIRouter()


@router.get('/api/inventory/groups')
def inventory_groups(household_id: str | None = Query(default=None)):
    """Return inventory aggregated by Rezzerv product meaning.

    M2C2i-30A/30B/30C: this projection groups inventory across shops and brands.
    It does not create inventory events and does not change stock quantities.
    """
    return list_inventory_groups_with_hierarchy(household_id=household_id)


@router.get('/api/product-groups')
def product_groups():
    return list_product_groups()


@router.post('/api/product-groups')
def product_group_create(payload: dict[str, Any] = Body(default_factory=dict)):
    result = create_product_group(
        display_name=str(payload.get('display_name') or '').strip(),
        default_base_unit=str(payload.get('default_base_unit') or 'stuk').strip() or 'stuk',
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Productgroep kon niet worden toegevoegd')
    return result


@router.put('/api/product-groups/{inventory_group_key:path}')
def product_group_update(inventory_group_key: str, payload: dict[str, Any] = Body(default_factory=dict)):
    result = update_product_group(
        inventory_group_key=inventory_group_key,
        display_name=str(payload.get('display_name') or '').strip(),
        default_base_unit=str(payload.get('default_base_unit') or 'stuk').strip() or 'stuk',
    )
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
    result = assign_inventory_item_to_group(
        inventory_id=inventory_id,
        inventory_group_key=str(payload.get('inventory_group_key') or '').strip(),
        source=str(payload.get('source') or 'productgroepen_ui').strip() or 'productgroepen_ui',
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Artikel kon niet aan productgroep worden gekoppeld')
    return result


@router.post('/api/products/{global_product_id}/inventory-group')
def product_inventory_group_link(global_product_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
    result = link_global_product_to_inventory_group(
        global_product_id=global_product_id,
        inventory_group_key=str(payload.get('inventory_group_key') or '').strip(),
        comparison_group_key=str(payload.get('comparison_group_key') or '').strip() or None,
        confidence=float(payload.get('confidence') or 1.0),
        source=str(payload.get('source') or 'user').strip() or 'user',
        confirmed_by_user=bool(payload.get('confirmed_by_user', True)),
    )
    if not bool(result.get('ok', False)):
        raise HTTPException(status_code=400, detail=result.get('error') or 'Voorraadgroep kon niet worden gekoppeld')
    return result


@router.post('/api/admin/inventory/groups/ensure-schema')
def inventory_groups_ensure_schema():
    ensure_product_inventory_group_schema()
    return {
        'ok': True,
        'schema': 'product_inventory_groups',
        'seed': 'm2c2i30a_seed',
        'mutates_inventory': False,
    }


@router.post('/api/admin/product-groups/import-gpc-nl')
def admin_product_groups_import_gpc_nl(x_rezzerv_admin_key: str | None = Header(default=None)):
    try:
        require_admin_key(x_rezzerv_admin_key)
        return import_gs1_gpc_nl()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'GS1 GPC NL import is mislukt: {exc}') from exc
