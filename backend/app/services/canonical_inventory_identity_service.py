"""Canonical inventory identity operations for Slice 2B4.

Inventory identity is household_id + household_article_id + location.
The inventory.naam column is maintained only as a presentation/snapshot value.

From v01.12.78 the current inventory projection is reconciled with the existing
inventory_events ledger after a purchase mutation. This keeps the visible stock
independent from receipt import order while preserving the existing location model.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import text

from app.services.temporal_inventory_service import reconcile_inventory_total


def _normalize(value: object | None) -> str:
    return str(value or "").strip()


def require_household_article(conn, household_id: str, household_article_id: str) -> dict:
    normalized_household_id = _normalize(household_id)
    normalized_article_id = _normalize(household_article_id)
    if not normalized_household_id or not normalized_article_id:
        raise HTTPException(status_code=400, detail="Huishouden en household_article_id zijn verplicht voor voorraadmutatie")

    row = conn.execute(
        text(
            """
            SELECT id, household_id, naam
            FROM household_articles
            WHERE id = :household_article_id
              AND household_id = :household_id
              AND COALESCE(status, 'active') = 'active'
            LIMIT 1
            """
        ),
        {
            "household_id": normalized_household_id,
            "household_article_id": normalized_article_id,
        },
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Huishoudartikel niet gevonden binnen actief huishouden")
    return dict(row)


def get_inventory_total_by_household_article(conn, household_id: str, household_article_id: str) -> int:
    article = require_household_article(conn, household_id, household_article_id)
    row = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(aantal), 0) AS total_quantity
            FROM inventory
            WHERE household_id = :household_id
              AND household_article_id = :household_article_id
              AND COALESCE(status, 'active') = 'active'
            """
        ),
        {
            "household_id": str(article["household_id"]),
            "household_article_id": str(article["id"]),
        },
    ).mappings().first()
    return int((row or {}).get("total_quantity") or 0)


def _temporal_ledger_available_for_article(conn, household_id: str, household_article_id: str) -> bool:
    table_exists = conn.execute(text(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inventory_events' LIMIT 1"
    )).scalar()
    if not table_exists:
        return False
    columns = {str(row[1]) for row in conn.execute(text("PRAGMA table_info(inventory_events)")).fetchall()}
    if "household_article_id" not in columns:
        return False
    event_exists = conn.execute(text(
        """
        SELECT 1
        FROM inventory_events
        WHERE household_id = :household_id
          AND household_article_id = :household_article_id
        LIMIT 1
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
    }).scalar()
    return bool(event_exists)


def _reconcile_if_temporal_event_exists(conn, *, household_id: str, household_article_id: str, inventory_id: str) -> None:
    # Some deliberately minimal isolated tests do not create inventory_events.
    # Preserve their legacy mutation behavior; production receipt/unpacking flows do.
    if not _temporal_ledger_available_for_article(conn, household_id, household_article_id):
        return
    reconcile_inventory_total(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
        preferred_inventory_id=str(inventory_id),
    )


def apply_inventory_purchase_by_identity(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    quantity: float,
    space_id: str | None,
    sublocation_id: str | None,
) -> str:
    article = require_household_article(conn, household_id, household_article_id)
    normalized_household_id = str(article["household_id"])
    normalized_article_id = str(article["id"])
    article_name_snapshot = str(article.get("naam") or "").strip()
    normalized_space_id = _normalize(space_id) or None
    normalized_sublocation_id = _normalize(sublocation_id) or None
    quantity_value = int(quantity)

    if quantity_value <= 0:
        raise HTTPException(status_code=400, detail="Voorraadaantal moet groter zijn dan 0")
    if not normalized_space_id and not normalized_sublocation_id:
        raise HTTPException(status_code=400, detail="Voorraadmutatie vereist een expliciete ruimte of sublocatie")

    existing = conn.execute(
        text(
            """
            SELECT id, aantal
            FROM inventory
            WHERE household_id = :household_id
              AND household_article_id = :household_article_id
              AND COALESCE(space_id, '') = COALESCE(:space_id, '')
              AND COALESCE(sublocation_id, '') = COALESCE(:sublocation_id, '')
              AND COALESCE(status, 'active') = 'active'
            LIMIT 1
            """
        ),
        {
            "household_id": normalized_household_id,
            "household_article_id": normalized_article_id,
            "space_id": normalized_space_id,
            "sublocation_id": normalized_sublocation_id,
        },
    ).mappings().first()

    if existing:
        inventory_id = str(existing["id"])
        conn.execute(
            text(
                """
                UPDATE inventory
                SET aantal = COALESCE(aantal, 0) + :quantity,
                    naam = :article_name_snapshot,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :inventory_id
                  AND household_id = :household_id
                  AND household_article_id = :household_article_id
                """
            ),
            {
                "inventory_id": inventory_id,
                "household_id": normalized_household_id,
                "household_article_id": normalized_article_id,
                "article_name_snapshot": article_name_snapshot,
                "quantity": quantity_value,
            },
        )
        _reconcile_if_temporal_event_exists(
            conn,
            household_id=normalized_household_id,
            household_article_id=normalized_article_id,
            inventory_id=inventory_id,
        )
        return inventory_id

    inventory_id = uuid.uuid4().hex
    conn.execute(
        text(
            """
            INSERT INTO inventory (
                id, naam, aantal, household_id, household_article_id,
                space_id, sublocation_id, status, updated_at
            ) VALUES (
                :id, :article_name_snapshot, :quantity, :household_id, :household_article_id,
                :space_id, :sublocation_id, 'active', CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "id": inventory_id,
            "article_name_snapshot": article_name_snapshot,
            "quantity": quantity_value,
            "household_id": normalized_household_id,
            "household_article_id": normalized_article_id,
            "space_id": normalized_space_id,
            "sublocation_id": normalized_sublocation_id,
        },
    )
    _reconcile_if_temporal_event_exists(
        conn,
        household_id=normalized_household_id,
        household_article_id=normalized_article_id,
        inventory_id=inventory_id,
    )
    return inventory_id
