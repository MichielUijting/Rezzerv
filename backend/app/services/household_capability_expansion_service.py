from __future__ import annotations

from sqlalchemy import text

from app.services.household_product_configuration_service import (
    ensure_household_product_configuration_foundation,
    resolve_household_product_configuration,
)

INVENTORY_RANK = {"none": 0, "presence": 1, "quantity": 2}
LOCATION_RANK = {"none": 0, "global": 1, "exact": 2}


def _max_level(current: str, requested: str | None, ranks: dict[str, int]) -> str:
    if requested is None:
        return current
    normalized = str(requested or "").strip().lower()
    if normalized not in ranks:
        raise ValueError("Ongeldig configuratieniveau")
    return normalized if ranks[normalized] > ranks[current] else current


def _ensure_neutral_configuration(conn, household_id: str) -> None:
    ensure_household_product_configuration_foundation(conn)
    conn.execute(text("""
        INSERT OR IGNORE INTO household_product_configuration (
            household_id,
            inventory_tracking_level,
            location_tracking_level,
            shopping_enabled,
            almost_out_enabled,
            almost_out_notifications_enabled,
            receipt_processing_enabled,
            recipes_enabled,
            unpacking_enabled,
            created_at,
            updated_at
        ) VALUES (
            :household_id,
            'none',
            'none',
            0, 0, 0, 0, 0, 0,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
    """), {"household_id": household_id})


def expand_household_product_configuration(
    conn,
    *,
    household_id: str,
    inventory_tracking_level: str | None = None,
    location_tracking_level: str | None = None,
    shopping_enabled: bool = False,
    almost_out_enabled: bool = False,
    almost_out_notifications_enabled: bool = False,
    receipt_processing_enabled: bool = False,
    recipes_enabled: bool = False,
    unpacking_enabled: bool = False,
):
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    _ensure_neutral_configuration(conn, normalized_household_id)
    current = resolve_household_product_configuration(conn, normalized_household_id)
    next_inventory = _max_level(
        current.inventory_tracking_level,
        inventory_tracking_level,
        INVENTORY_RANK,
    )
    next_location = _max_level(
        current.location_tracking_level,
        location_tracking_level,
        LOCATION_RANK,
    )
    next_almost_out_notifications = (
        current.almost_out_notifications_enabled
        or bool(almost_out_notifications_enabled)
    )
    next_almost_out = (
        current.almost_out_enabled
        or bool(almost_out_enabled)
        or next_almost_out_notifications
    )

    if next_almost_out_notifications and next_inventory == "none":
        raise ValueError("Bijna-op meldingen vereisen voorraadregistratie")

    conn.execute(text("""
        UPDATE household_product_configuration
        SET inventory_tracking_level = :inventory_tracking_level,
            location_tracking_level = :location_tracking_level,
            shopping_enabled = :shopping_enabled,
            almost_out_enabled = :almost_out_enabled,
            almost_out_notifications_enabled = :almost_out_notifications_enabled,
            receipt_processing_enabled = :receipt_processing_enabled,
            recipes_enabled = :recipes_enabled,
            unpacking_enabled = :unpacking_enabled,
            updated_at = CURRENT_TIMESTAMP
        WHERE household_id = :household_id
    """), {
        "household_id": normalized_household_id,
        "inventory_tracking_level": next_inventory,
        "location_tracking_level": next_location,
        "shopping_enabled": int(current.shopping_enabled or bool(shopping_enabled)),
        "almost_out_enabled": int(next_almost_out),
        "almost_out_notifications_enabled": int(next_almost_out_notifications),
        "receipt_processing_enabled": int(
            current.receipt_processing_enabled or bool(receipt_processing_enabled)
        ),
        "recipes_enabled": int(current.recipes_enabled or bool(recipes_enabled)),
        "unpacking_enabled": int(current.unpacking_enabled or bool(unpacking_enabled)),
    })
    return resolve_household_product_configuration(conn, normalized_household_id)


def expand_with_inhuis_halen(
    conn,
    *,
    household_id: str,
    simple_inventory_enabled: bool,
    almost_out_notifications_enabled: bool,
    receipt_processing_enabled: bool,
    recipes_enabled: bool,
):
    if almost_out_notifications_enabled and not simple_inventory_enabled:
        try:
            current = resolve_household_product_configuration(conn, household_id)
        except LookupError:
            current_inventory = "none"
        else:
            current_inventory = current.inventory_tracking_level
        if current_inventory == "none":
            raise ValueError(
                "Bijna-op meldingen vereisen eenvoudige of bestaande voorraadregistratie"
            )

    return expand_household_product_configuration(
        conn,
        household_id=household_id,
        inventory_tracking_level="quantity" if simple_inventory_enabled else None,
        shopping_enabled=True,
        almost_out_enabled=bool(simple_inventory_enabled),
        almost_out_notifications_enabled=almost_out_notifications_enabled,
        receipt_processing_enabled=receipt_processing_enabled,
        recipes_enabled=recipes_enabled,
    )


def expand_with_wat_inhuis(
    conn,
    *,
    household_id: str,
    inventory_tracking_level: str | None,
    global_locations_enabled: bool,
    almost_out_enabled: bool,
    shopping_enabled: bool,
):
    requested_inventory = None
    if inventory_tracking_level is not None:
        normalized = str(inventory_tracking_level or "").strip().lower()
        if normalized not in {"presence", "quantity"}:
            raise ValueError("Wat Inhuis ondersteunt aanwezigheid of aantallen")
        requested_inventory = normalized

    return expand_household_product_configuration(
        conn,
        household_id=household_id,
        inventory_tracking_level=requested_inventory,
        location_tracking_level="global" if global_locations_enabled else None,
        shopping_enabled=shopping_enabled,
        almost_out_enabled=almost_out_enabled,
    )


def expand_with_waar_inhuis(
    conn,
    *,
    household_id: str,
    unpacking_enabled: bool,
    receipt_processing_enabled: bool,
    almost_out_enabled: bool,
):
    return expand_household_product_configuration(
        conn,
        household_id=household_id,
        inventory_tracking_level="presence",
        location_tracking_level="exact",
        unpacking_enabled=unpacking_enabled,
        receipt_processing_enabled=receipt_processing_enabled,
        almost_out_enabled=almost_out_enabled,
    )
