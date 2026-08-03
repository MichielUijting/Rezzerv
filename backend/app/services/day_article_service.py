from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import write_authorization_audit

STOCK = "STOCK"
DIRECT_CONSUMPTION = "DIRECT_CONSUMPTION"
VALID_HANDLING = {STOCK, DIRECT_CONSUMPTION}
DIRECT_LOCATION_KEY = "system.direct"


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if table_name not in inspector.get_table_names():
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def ensure_day_article_schema(conn) -> None:
    article_columns = _columns(conn, "household_articles")
    if not article_columns:
        raise RuntimeError("household_articles ontbreekt")
    if "default_inventory_handling" not in article_columns:
        conn.execute(text("ALTER TABLE household_articles ADD COLUMN default_inventory_handling TEXT NOT NULL DEFAULT 'STOCK'"))
    if "inventory_handling_updated_at" not in article_columns:
        conn.execute(text("ALTER TABLE household_articles ADD COLUMN inventory_handling_updated_at TEXT"))
    if "inventory_handling_updated_by_user_id" not in article_columns:
        conn.execute(text("ALTER TABLE household_articles ADD COLUMN inventory_handling_updated_by_user_id TEXT"))

    space_columns = _columns(conn, "spaces")
    if not space_columns:
        raise RuntimeError("spaces ontbreekt")
    if "system_key" not in space_columns:
        conn.execute(text("ALTER TABLE spaces ADD COLUMN system_key TEXT"))
    if "protected" not in space_columns:
        conn.execute(text("ALTER TABLE spaces ADD COLUMN protected INTEGER NOT NULL DEFAULT 0"))

    sublocation_columns = _columns(conn, "sublocations")
    if not sublocation_columns:
        raise RuntimeError("sublocations ontbreekt")
    if "system_key" not in sublocation_columns:
        conn.execute(text("ALTER TABLE sublocations ADD COLUMN system_key TEXT"))
    if "protected" not in sublocation_columns:
        conn.execute(text("ALTER TABLE sublocations ADD COLUMN protected INTEGER NOT NULL DEFAULT 0"))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS day_article_processing_events (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            household_article_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('RECEIPT', 'DIRECT_CONSUMPTION')),
            quantity NUMERIC NOT NULL,
            space_id TEXT NOT NULL,
            sublocation_id TEXT NOT NULL,
            actor_user_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (household_id, idempotency_key, event_type)
        )
    """))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_spaces_household_system_key ON spaces (household_id, system_key) WHERE system_key IS NOT NULL"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_sublocations_space_system_key ON sublocations (space_id, system_key) WHERE system_key IS NOT NULL"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_day_article_events_article ON day_article_processing_events (household_id, household_article_id, created_at)"))


def ensure_direct_location(conn, household_id: str) -> dict[str, str]:
    ensure_day_article_schema(conn)
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("household_id is verplicht")
    namespace = uuid.UUID("d7b40c51-05ee-4d28-b3de-2c24a90cd318")
    space_id = str(uuid.uuid5(namespace, f"{normalized_household_id}:direct:space"))
    sublocation_id = str(uuid.uuid5(namespace, f"{normalized_household_id}:direct:sublocation"))
    conn.execute(text("""
        INSERT INTO spaces (id, naam, household_id, system_key, protected)
        VALUES (:id, 'Direct', :household_id, :system_key, 1)
        ON CONFLICT(id) DO UPDATE SET naam = 'Direct', household_id = excluded.household_id,
          system_key = excluded.system_key, protected = 1
    """), {"id": space_id, "household_id": normalized_household_id, "system_key": DIRECT_LOCATION_KEY})
    conn.execute(text("""
        INSERT INTO sublocations (id, naam, space_id, system_key, protected)
        VALUES (:id, 'Direct', :space_id, :system_key, 1)
        ON CONFLICT(id) DO UPDATE SET naam = 'Direct', space_id = excluded.space_id,
          system_key = excluded.system_key, protected = 1
    """), {"id": sublocation_id, "space_id": space_id, "system_key": DIRECT_LOCATION_KEY})
    return {"space_id": space_id, "sublocation_id": sublocation_id, "location": "Direct", "sublocation": "Direct"}


def get_default_inventory_handling(conn, household_id: str, household_article_id: str) -> dict[str, Any]:
    ensure_day_article_schema(conn)
    row = conn.execute(text("""
        SELECT id, household_id, naam, COALESCE(default_inventory_handling, 'STOCK') AS default_inventory_handling,
               inventory_handling_updated_at, inventory_handling_updated_by_user_id
        FROM household_articles
        WHERE id = :article_id AND household_id = :household_id
        LIMIT 1
    """), {"article_id": str(household_article_id), "household_id": str(household_id)}).mappings().first()
    if not row:
        raise LookupError("Huishoudartikel niet gevonden")
    return dict(row)


def set_default_inventory_handling(conn, *, household_id: str, household_article_id: str,
                                   handling: str, actor_user_id: str) -> dict[str, Any]:
    normalized = str(handling or "").strip().upper()
    if normalized not in VALID_HANDLING:
        raise ValueError("Onbekende voorraadverwerking")
    current = get_default_inventory_handling(conn, household_id, household_article_id)
    conn.execute(text("""
        UPDATE household_articles
        SET default_inventory_handling = :handling,
            inventory_handling_updated_at = CURRENT_TIMESTAMP,
            inventory_handling_updated_by_user_id = :actor_user_id,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :article_id AND household_id = :household_id
    """), {"handling": normalized, "actor_user_id": str(actor_user_id),
            "article_id": str(household_article_id), "household_id": str(household_id)})
    write_authorization_audit(conn, actor_user_id=str(actor_user_id), actor_type="household_member",
                              household_id=str(household_id), action="article.inventory_handling.updated",
                              object_type="household_article", object_id=str(household_article_id),
                              old_value={"default_inventory_handling": current["default_inventory_handling"]},
                              new_value={"default_inventory_handling": normalized})
    return get_default_inventory_handling(conn, household_id, household_article_id)


def record_direct_consumption(conn, *, household_id: str, household_article_id: str,
                              quantity: Decimal | int | float | str, idempotency_key: str,
                              actor_user_id: str) -> dict[str, Any]:
    article = get_default_inventory_handling(conn, household_id, household_article_id)
    amount = Decimal(str(quantity))
    if amount <= 0:
        raise ValueError("quantity moet groter zijn dan nul")
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        raise ValueError("idempotency_key is verplicht")
    location = ensure_direct_location(conn, household_id)
    existing = conn.execute(text("""
        SELECT COUNT(*) FROM day_article_processing_events
        WHERE household_id = :household_id AND idempotency_key = :idempotency_key
    """), {"household_id": str(household_id), "idempotency_key": normalized_key}).scalar_one()
    if int(existing or 0) == 0:
        for event_type in ("RECEIPT", "DIRECT_CONSUMPTION"):
            conn.execute(text("""
                INSERT INTO day_article_processing_events
                  (id, household_id, household_article_id, idempotency_key, event_type, quantity,
                   space_id, sublocation_id, actor_user_id)
                VALUES (:id, :household_id, :article_id, :idempotency_key, :event_type, :quantity,
                        :space_id, :sublocation_id, :actor_user_id)
            """), {"id": str(uuid.uuid4()), "household_id": str(household_id),
                    "article_id": str(household_article_id), "idempotency_key": normalized_key,
                    "event_type": event_type, "quantity": str(amount),
                    "space_id": location["space_id"], "sublocation_id": location["sublocation_id"],
                    "actor_user_id": str(actor_user_id)})
    return {"household_id": str(household_id), "household_article_id": str(household_article_id),
            "article_name": article.get("naam"), "handling": DIRECT_CONSUMPTION,
            "quantity_received": str(amount), "quantity_consumed": str(amount),
            "net_inventory_change": "0", "idempotency_key": normalized_key,
            "idempotent_replay": int(existing or 0) > 0, **location}
