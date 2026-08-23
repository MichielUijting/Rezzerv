from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

INVENTORY_TRACKING_LEVELS = frozenset({"none", "presence", "quantity"})
LOCATION_TRACKING_LEVELS = frozenset({"none", "global", "exact"})


@dataclass(frozen=True)
class HouseholdProductConfiguration:
    household_id: str
    inventory_tracking_level: str
    location_tracking_level: str
    shopping_enabled: bool
    almost_out_enabled: bool
    almost_out_notifications_enabled: bool
    receipt_processing_enabled: bool
    recipes_enabled: bool

    @property
    def simple_inventory_enabled(self) -> bool:
        return self.inventory_tracking_level != "none"


def ensure_household_product_configuration_foundation(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS household_product_configuration (
            household_id TEXT PRIMARY KEY,
            inventory_tracking_level TEXT NOT NULL
                CHECK (inventory_tracking_level IN ('none', 'presence', 'quantity')),
            location_tracking_level TEXT NOT NULL
                CHECK (location_tracking_level IN ('none', 'global', 'exact')),
            shopping_enabled INTEGER NOT NULL DEFAULT 0 CHECK (shopping_enabled IN (0, 1)),
            almost_out_enabled INTEGER NOT NULL DEFAULT 0 CHECK (almost_out_enabled IN (0, 1)),
            almost_out_notifications_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (almost_out_notifications_enabled IN (0, 1)),
            receipt_processing_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (receipt_processing_enabled IN (0, 1)),
            recipes_enabled INTEGER NOT NULL DEFAULT 0 CHECK (recipes_enabled IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))


def save_inhuis_halen_configuration(
    conn,
    *,
    household_id: str,
    simple_inventory_enabled: bool,
    almost_out_notifications_enabled: bool,
    receipt_processing_enabled: bool,
    recipes_enabled: bool,
) -> HouseholdProductConfiguration:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")
    if not simple_inventory_enabled and almost_out_notifications_enabled:
        raise ValueError(
            "Bijna-op meldingen vereisen de eenvoudige voorraad van Inhuis halen"
        )

    ensure_household_product_configuration_foundation(conn)
    inventory_tracking_level = "quantity" if simple_inventory_enabled else "none"
    almost_out_enabled = bool(simple_inventory_enabled)

    conn.execute(text("""
        INSERT INTO household_product_configuration (
            household_id,
            inventory_tracking_level,
            location_tracking_level,
            shopping_enabled,
            almost_out_enabled,
            almost_out_notifications_enabled,
            receipt_processing_enabled,
            recipes_enabled,
            created_at,
            updated_at
        ) VALUES (
            :household_id,
            :inventory_tracking_level,
            'none',
            1,
            :almost_out_enabled,
            :almost_out_notifications_enabled,
            :receipt_processing_enabled,
            :recipes_enabled,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id) DO UPDATE SET
            inventory_tracking_level = excluded.inventory_tracking_level,
            location_tracking_level = 'none',
            shopping_enabled = 1,
            almost_out_enabled = excluded.almost_out_enabled,
            almost_out_notifications_enabled = excluded.almost_out_notifications_enabled,
            receipt_processing_enabled = excluded.receipt_processing_enabled,
            recipes_enabled = excluded.recipes_enabled,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": normalized_household_id,
        "inventory_tracking_level": inventory_tracking_level,
        "almost_out_enabled": int(almost_out_enabled),
        "almost_out_notifications_enabled": int(bool(almost_out_notifications_enabled)),
        "receipt_processing_enabled": int(bool(receipt_processing_enabled)),
        "recipes_enabled": int(bool(recipes_enabled)),
    })
    return resolve_household_product_configuration(conn, normalized_household_id)


def resolve_household_product_configuration(
    conn,
    household_id: str,
) -> HouseholdProductConfiguration:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    ensure_household_product_configuration_foundation(conn)
    row = conn.execute(text("""
        SELECT
            household_id,
            inventory_tracking_level,
            location_tracking_level,
            shopping_enabled,
            almost_out_enabled,
            almost_out_notifications_enabled,
            receipt_processing_enabled,
            recipes_enabled
        FROM household_product_configuration
        WHERE household_id = :household_id
        LIMIT 1
    """), {"household_id": normalized_household_id}).mappings().first()
    if not row:
        raise LookupError("Voor dit huishouden bestaat geen productconfiguratie")

    inventory_level = str(row.get("inventory_tracking_level") or "").strip().lower()
    location_level = str(row.get("location_tracking_level") or "").strip().lower()
    if inventory_level not in INVENTORY_TRACKING_LEVELS:
        raise RuntimeError("Ongeldig voorraadniveau in productconfiguratie")
    if location_level not in LOCATION_TRACKING_LEVELS:
        raise RuntimeError("Ongeldig locatieniveau in productconfiguratie")

    return HouseholdProductConfiguration(
        household_id=str(row.get("household_id") or ""),
        inventory_tracking_level=inventory_level,
        location_tracking_level=location_level,
        shopping_enabled=bool(row.get("shopping_enabled")),
        almost_out_enabled=bool(row.get("almost_out_enabled")),
        almost_out_notifications_enabled=bool(row.get("almost_out_notifications_enabled")),
        receipt_processing_enabled=bool(row.get("receipt_processing_enabled")),
        recipes_enabled=bool(row.get("recipes_enabled")),
    )


def public_household_product_configuration_payload(
    configuration: HouseholdProductConfiguration,
) -> dict[str, Any]:
    return {
        "inventory_tracking_level": configuration.inventory_tracking_level,
        "location_tracking_level": configuration.location_tracking_level,
        "simple_inventory_enabled": configuration.simple_inventory_enabled,
        "shopping_enabled": configuration.shopping_enabled,
        "almost_out_enabled": configuration.almost_out_enabled,
        "almost_out_notifications_enabled": configuration.almost_out_notifications_enabled,
        "receipt_processing_enabled": configuration.receipt_processing_enabled,
        "recipes_enabled": configuration.recipes_enabled,
    }
