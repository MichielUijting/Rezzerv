from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.services.product_inventory_group_store import (
    assign_inventory_item_to_group,
    ensure_product_inventory_group_schema,
    link_global_product_to_inventory_group,
    list_inventory_groups,
)

router = APIRouter()


@router.get('/api/inventory/groups')
def inventory_groups(household_id: str | None = Query(default=None)):
    """Return inventory aggregated by Rezzerv product meaning.

    M2C2i-30A/30B: this projection groups inventory across shops and brands.
    It does not create inventory events and does not change stock quantities.
    """
    return list_inventory_groups(household_id=household_id)


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
