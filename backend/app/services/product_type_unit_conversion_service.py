from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.product_inventory_group_store import ensure_product_inventory_group_schema

MASS_FACTORS = {
    "mg": ("mg", 1.0),
    "g": ("mg", 1000.0),
    "kg": ("mg", 1_000_000.0),
}
VOLUME_FACTORS = {
    "ml": ("ml", 1.0),
    "cl": ("ml", 10.0),
    "dl": ("ml", 100.0),
    "l": ("ml", 1000.0),
    "liter": ("ml", 1000.0),
    "litre": ("ml", 1000.0),
}
COUNT_UNITS = {"stuk", "stuks", "piece", "pieces", "rol", "rollen", "wasbeurt", "wasbeurten"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_quantity(value: float, unit: str) -> tuple[float, str] | None:
    normalized = _clean(unit).lower()
    if normalized in MASS_FACTORS:
        canonical, factor = MASS_FACTORS[normalized]
        return value * factor, canonical
    if normalized in VOLUME_FACTORS:
        canonical, factor = VOLUME_FACTORS[normalized]
        return value * factor, canonical
    if normalized in COUNT_UNITS:
        return value, "stuk"
    return None


def convert_quantity(value: float, source_unit: str, target_unit: str) -> float | None:
    source = canonical_quantity(value, source_unit)
    target = canonical_quantity(1.0, target_unit)
    if not source or not target or source[1] != target[1] or target[0] == 0:
        return None
    return source[0] / target[0]


def resolve_package_conversion(
    *,
    global_product_id: str | None,
    product_type_id: str,
    target_unit: str,
    allow_direct_count: bool = False,
) -> dict[str, Any]:
    """Bepaal de hoeveelheid per verpakking in de Producttype-basiseenheid."""
    ensure_product_inventory_group_schema()
    global_product_id = _clean(global_product_id)
    product_type_id = _clean(product_type_id)
    target_unit = _clean(target_unit)
    base = {
        "global_product_id": global_product_id or None,
        "product_type_id": product_type_id or None,
        "target_unit": target_unit or None,
        "read_only": True,
        "mutates_inventory": False,
    }
    if not product_type_id or not target_unit:
        return {**base, "status": "invalid_target", "quantity_per_package": None}
    if not global_product_id:
        if allow_direct_count and canonical_quantity(1.0, target_unit) == (1.0, "stuk"):
            return {**base, "status": "direct_count", "quantity_per_package": 1.0}
        return {**base, "status": "missing_product_identity", "quantity_per_package": None}

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT base_quantity, base_unit, content_value, content_unit,
                       confidence, source
                FROM product_unit_conversions
                WHERE global_product_id = :global_product_id
                  AND (
                      inventory_group_key = :product_type_id
                      OR inventory_group_key IS NULL
                      OR trim(inventory_group_key) = ''
                  )
                ORDER BY CASE WHEN inventory_group_key = :product_type_id THEN 0 ELSE 1 END,
                         confidence DESC,
                         COALESCE(updated_at, created_at, '') DESC
                LIMIT 1
                """
            ),
            {"global_product_id": global_product_id, "product_type_id": product_type_id},
        ).mappings().first()
    if not row:
        return {**base, "status": "missing_unit_conversion", "quantity_per_package": None}

    candidates = (
        (_number(row.get("base_quantity")), _clean(row.get("base_unit"))),
        (_number(row.get("content_value")), _clean(row.get("content_unit"))),
    )
    for value, unit in candidates:
        if value is None or value < 0 or not unit:
            continue
        converted = convert_quantity(value, unit, target_unit)
        if converted is not None:
            return {
                **base,
                "status": "resolved",
                "quantity_per_package": converted,
                "source_value": value,
                "source_unit": unit,
                "confidence": _number(row.get("confidence")),
                "source": _clean(row.get("source")) or None,
            }
    return {**base, "status": "incompatible_unit", "quantity_per_package": None}
