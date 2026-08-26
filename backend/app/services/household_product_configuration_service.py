from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import inspect, text

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
    unpacking_enabled: bool

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
            unpacking_enabled INTEGER NOT NULL DEFAULT 0 CHECK (unpacking_enabled IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    columns = {
        str(column.get("name") or "")
        for column in inspect(conn).get_columns("household_product_configuration")
    }
    if "unpacking_enabled" not in columns:
        conn.execute(text("""
            ALTER TABLE household_product_configuration
            ADD COLUMN unpacking_enabled INTEGER NOT NULL DEFAULT 0
                CHECK (unpacking_enabled IN (0, 1))
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
            unpacking_enabled,
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
            0,
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
            unpacking_enabled = 0,
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


def save_wat_inhuis_configuration(
    conn,
    *,
    household_id: str,
    inventory_tracking_level: str,
    global_locations_enabled: bool,
    almost_out_enabled: bool,
    shopping_enabled: bool,
) -> HouseholdProductConfiguration:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    normalized_inventory_level = str(inventory_tracking_level or "").strip().lower()
    if normalized_inventory_level not in {"presence", "quantity"}:
        raise ValueError("Wat Inhuis ondersteunt aanwezigheid of aantallen")

    location_tracking_level = "global" if global_locations_enabled else "none"
    ensure_household_product_configuration_foundation(conn)

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
            unpacking_enabled,
            created_at,
            updated_at
        ) VALUES (
            :household_id,
            :inventory_tracking_level,
            :location_tracking_level,
            :shopping_enabled,
            :almost_out_enabled,
            0,
            1,
            0,
            0,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id) DO UPDATE SET
            inventory_tracking_level = excluded.inventory_tracking_level,
            location_tracking_level = excluded.location_tracking_level,
            shopping_enabled = excluded.shopping_enabled,
            almost_out_enabled = excluded.almost_out_enabled,
            almost_out_notifications_enabled = 0,
            receipt_processing_enabled = 1,
            recipes_enabled = 0,
            unpacking_enabled = 0,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": normalized_household_id,
        "inventory_tracking_level": normalized_inventory_level,
        "location_tracking_level": location_tracking_level,
        "shopping_enabled": int(bool(shopping_enabled)),
        "almost_out_enabled": int(bool(almost_out_enabled)),
    })
    return resolve_household_product_configuration(conn, normalized_household_id)


def save_waar_inhuis_configuration(
    conn,
    *,
    household_id: str,
    unpacking_enabled: bool,
    receipt_processing_enabled: bool,
    almost_out_enabled: bool,
) -> HouseholdProductConfiguration:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    ensure_household_product_configuration_foundation(conn)
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
            unpacking_enabled,
            created_at,
            updated_at
        ) VALUES (
            :household_id,
            'presence',
            'exact',
            0,
            :almost_out_enabled,
            0,
            :receipt_processing_enabled,
            0,
            :unpacking_enabled,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT(household_id) DO UPDATE SET
            inventory_tracking_level = 'presence',
            location_tracking_level = 'exact',
            shopping_enabled = 0,
            almost_out_enabled = excluded.almost_out_enabled,
            almost_out_notifications_enabled = 0,
            receipt_processing_enabled = excluded.receipt_processing_enabled,
            recipes_enabled = 0,
            unpacking_enabled = excluded.unpacking_enabled,
            updated_at = CURRENT_TIMESTAMP
    """), {
        "household_id": normalized_household_id,
        "almost_out_enabled": int(bool(almost_out_enabled)),
        "receipt_processing_enabled": int(bool(receipt_processing_enabled)),
        "unpacking_enabled": int(bool(unpacking_enabled)),
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
            recipes_enabled,
            unpacking_enabled
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
        unpacking_enabled=bool(row.get("unpacking_enabled")),
    )


def resolve_canonical_household_product_configuration(
    conn,
    *,
    household_id: str,
    primary_use_case: str | None,
) -> HouseholdProductConfiguration:
    configuration = resolve_household_product_configuration(conn, household_id)
    normalized_primary_use_case = str(primary_use_case or "").strip().lower()

    if (
        normalized_primary_use_case != "wat_inhuis"
        or configuration.receipt_processing_enabled
    ):
        return configuration

    conn.execute(text("""
        UPDATE household_product_configuration
        SET receipt_processing_enabled = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE household_id = :household_id
          AND receipt_processing_enabled = 0
    """), {"household_id": configuration.household_id})
    return resolve_household_product_configuration(conn, configuration.household_id)


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
        "unpacking_enabled": configuration.unpacking_enabled,
    }
