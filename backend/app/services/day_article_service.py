from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy import inspect, text

from app.services.authorization_foundation_service import write_authorization_audit

STOCK = "STOCK"
DIRECT_CONSUMPTION = "DIRECT_CONSUMPTION"
VALID_HANDLING = {STOCK, DIRECT_CONSUMPTION}
DIRECT_LOCATION_KEY = "system.direct"

_ARTICLE_COLUMNS = {
    "id",
    "household_id",
    "naam",
    "default_inventory_handling",
    "inventory_handling_updated_at",
    "inventory_handling_updated_by_user_id",
}
_SPACE_COLUMNS = {"id", "naam", "household_id", "system_key", "protected"}
_SUBLOCATION_COLUMNS = {"id", "naam", "space_id", "system_key", "protected"}
_EVENT_COLUMNS = {
    "id",
    "household_id",
    "household_article_id",
    "idempotency_key",
    "event_type",
    "quantity",
    "space_id",
    "sublocation_id",
    "actor_user_id",
    "created_at",
}


def _columns(conn, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _require_columns(conn, table_name: str, required: set[str]) -> None:
    columns = _columns(conn, table_name)
    if not columns:
        raise RuntimeError(
            f"Canonical dagartikel/Direct-schema mist {table_name}. "
            "Voer Alembic migrations uit met MIGRATION_DATABASE_URL."
        )
    missing = required - columns
    if missing:
        raise RuntimeError(
            f"Canonical dagartikel/Direct-schema wijkt af: {table_name} mist "
            f"{sorted(missing)}. Voer Alembic migrations uit."
        )


def _require_index(
    conn,
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
    *,
    unique: bool,
) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in inspect(conn).get_indexes(table_name)
    }
    index = indexes.get(index_name)
    if (
        index is None
        or bool(index.get("unique")) is not unique
        or tuple(index.get("column_names") or ()) != columns
    ):
        raise RuntimeError(
            f"Canonical dagartikel/Direct-index wijkt af: {index_name}. "
            "Voer Alembic migrations uit."
        )


def _event_unique_sets(conn) -> set[tuple[str, ...]]:
    inspector = inspect(conn)
    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints("day_article_processing_events")
    }
    unique_sets.update(
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes("day_article_processing_events")
        if bool(index.get("unique"))
    )
    return unique_sets


def ensure_day_article_schema(conn) -> None:
    """Validate the Alembic-owned day-article/Direct contract without mutation."""
    _require_columns(conn, "household_articles", _ARTICLE_COLUMNS)
    _require_columns(conn, "spaces", _SPACE_COLUMNS)
    _require_columns(conn, "sublocations", _SUBLOCATION_COLUMNS)
    _require_columns(conn, "day_article_processing_events", _EVENT_COLUMNS)

    _require_index(
        conn,
        "spaces",
        "idx_spaces_household_system_key",
        ("household_id", "system_key"),
        unique=True,
    )
    _require_index(
        conn,
        "sublocations",
        "idx_sublocations_space_system_key",
        ("space_id", "system_key"),
        unique=True,
    )
    _require_index(
        conn,
        "day_article_processing_events",
        "idx_day_article_events_article",
        ("household_id", "household_article_id", "created_at"),
        unique=False,
    )
    if (
        "household_id",
        "idempotency_key",
        "event_type",
    ) not in _event_unique_sets(conn):
        raise RuntimeError(
            "Canonical dagartikel-idempotency constraint ontbreekt. "
            "Voer Alembic migrations uit."
        )

    if conn.dialect.name == "postgresql":
        inspector = inspect(conn)
        for table_name in ("spaces", "sublocations"):
            protected = next(
                column
                for column in inspector.get_columns(table_name)
                if str(column.get("name") or "") == "protected"
            )
            if not isinstance(protected["type"], sa.Boolean):
                raise RuntimeError(
                    f"Canonical {table_name}.protected moet BOOLEAN zijn. "
                    "Voer Alembic migrations uit."
                )
        for table_name, column_name in (
            ("household_articles", "inventory_handling_updated_at"),
            ("day_article_processing_events", "created_at"),
        ):
            column = next(
                item
                for item in inspector.get_columns(table_name)
                if str(item.get("name") or "") == column_name
            )
            if not isinstance(column["type"], sa.DateTime) or not bool(
                getattr(column["type"], "timezone", False)
            ):
                raise RuntimeError(
                    f"Canonical {table_name}.{column_name} moet TIMESTAMPTZ zijn. "
                    "Voer Alembic migrations uit."
                )


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
        VALUES (:id, 'Direct', :household_id, :system_key, TRUE)
        ON CONFLICT(id) DO UPDATE SET naam = 'Direct', household_id = excluded.household_id,
          system_key = excluded.system_key, protected = TRUE
    """), {"id": space_id, "household_id": normalized_household_id, "system_key": DIRECT_LOCATION_KEY})
    conn.execute(text("""
        INSERT INTO sublocations (id, naam, space_id, system_key, protected)
        VALUES (:id, 'Direct', :space_id, :system_key, TRUE)
        ON CONFLICT(id) DO UPDATE SET naam = 'Direct', space_id = excluded.space_id,
          system_key = excluded.system_key, protected = TRUE
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


def get_default_inventory_handling_batch(
    conn,
    household_id: str,
    household_article_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Return defaults for unique article ids that belong to one household.

    Unknown ids and ids from another household are deliberately omitted. This
    prevents a batch lookup from becoming an article-existence oracle across
    household boundaries. The caller can treat omitted ids as unlinked rows.
    """

    ensure_day_article_schema(conn)
    normalized_household_id = str(household_id or "").strip()
    unique_ids = list(dict.fromkeys(
        str(article_id or "").strip()
        for article_id in household_article_ids
        if str(article_id or "").strip()
    ))
    if not unique_ids:
        return []

    results: list[dict[str, Any]] = []
    for article_id in unique_ids:
        row = conn.execute(text("""
            SELECT id, household_id, naam,
                   COALESCE(default_inventory_handling, 'STOCK') AS default_inventory_handling,
                   inventory_handling_updated_at, inventory_handling_updated_by_user_id
            FROM household_articles
            WHERE id = :article_id AND household_id = :household_id
            LIMIT 1
        """), {
            "article_id": article_id,
            "household_id": normalized_household_id,
        }).mappings().first()
        if row:
            results.append(dict(row))
    return results


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
    event_rows = conn.execute(text("""
        SELECT id, event_type
        FROM day_article_processing_events
        WHERE household_id = :household_id AND idempotency_key = :idempotency_key
        ORDER BY CASE event_type WHEN 'RECEIPT' THEN 0 ELSE 1 END
    """), {
        "household_id": str(household_id),
        "idempotency_key": normalized_key,
    }).mappings().all()
    event_ids = {str(row.get("event_type") or ""): str(row.get("id") or "") for row in event_rows}
    return {"household_id": str(household_id), "household_article_id": str(household_article_id),
            "article_name": article.get("naam"), "handling": DIRECT_CONSUMPTION,
            "quantity_received": str(amount), "quantity_consumed": str(amount),
            "net_inventory_change": "0", "idempotency_key": normalized_key,
            "receipt_event_id": event_ids.get("RECEIPT") or None,
            "direct_consumption_event_id": event_ids.get("DIRECT_CONSUMPTION") or None,
            "idempotent_replay": int(existing or 0) > 0, **location}
