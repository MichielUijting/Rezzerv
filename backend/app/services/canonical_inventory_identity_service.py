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

from app.services.temporal_inventory_service import (
    ensure_temporal_inventory_schema,
    reconcile_inventory_total,
)


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


def _table_exists(conn, table_name: str) -> bool:
    return bool(conn.execute(text(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name LIMIT 1"
    ), {"name": str(table_name)}).scalar())


def _temporal_ledger_available_for_article(conn, household_id: str, household_article_id: str) -> bool:
    if not _table_exists(conn, "inventory_events"):
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


def _hydrate_latest_receipt_purchase_event(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    quantity: int,
    space_id: str | None,
    sublocation_id: str | None,
) -> None:
    """Attach the exact receipt purchase timestamp to the event just created by Uitpakken.

    The legacy batch payload deliberately stores a date label. The authoritative
    receipt row still contains ``purchase_at`` (including time when detected). The
    stock event is therefore linked back to that receipt before chronological replay.
    No match means this was not a receipt-driven purchase and nothing is changed.
    """
    required_tables = {
        "inventory_events",
        "purchase_import_batches",
        "purchase_import_lines",
        "receipt_tables",
    }
    if not all(_table_exists(conn, table_name) for table_name in required_tables):
        return

    ensure_temporal_inventory_schema(conn)
    location_id = _normalize(sublocation_id) or _normalize(space_id) or None

    event = conn.execute(text(
        """
        SELECT id, location_id, quantity, source_reference
        FROM inventory_events
        WHERE household_id = :household_id
          AND household_article_id = :household_article_id
          AND lower(COALESCE(event_type, '')) = 'purchase'
          AND lower(COALESCE(source, '')) = 'store_import'
          AND COALESCE(trim(source_reference), '') = ''
          AND ABS(COALESCE(quantity, 0) - :quantity) < 0.000001
          AND (:location_id IS NULL OR COALESCE(location_id, '') = COALESCE(:location_id, ''))
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 1
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
        "quantity": int(quantity),
        "location_id": location_id,
    }).mappings().first()
    if not event:
        return

    line = conn.execute(text(
        """
        SELECT pil.id AS line_id,
               pib.source_reference,
               pil.target_location_id,
               pil.quantity_raw,
               COALESCE(pil.processing_status, 'pending') AS processing_status,
               pib.created_at AS batch_created_at
        FROM purchase_import_lines pil
        JOIN purchase_import_batches pib ON pib.id = pil.batch_id
        WHERE pib.household_id = :household_id
          AND pib.source_type = 'receipt'
          AND pil.matched_household_article_id = :household_article_id
          AND COALESCE(pil.processing_status, 'pending') <> 'processed'
          AND ABS(COALESCE(pil.quantity_raw, 0) - :quantity) < 0.000001
          AND (:location_id IS NULL OR COALESCE(pil.target_location_id, '') = COALESCE(:location_id, ''))
          AND pib.source_reference LIKE 'receipt:%'
        ORDER BY datetime(COALESCE(pil.updated_at, pil.created_at)) DESC,
                 datetime(pib.created_at) DESC,
                 COALESCE(pil.ui_sort_order, 0) DESC,
                 pil.id DESC
        LIMIT 1
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
        "quantity": int(quantity),
        "location_id": location_id,
    }).mappings().first()
    if not line:
        return

    source_reference = str(line.get("source_reference") or "").strip()
    if not source_reference.startswith("receipt:"):
        return
    receipt_table_id = source_reference.split(":", 1)[1].strip()
    if not receipt_table_id:
        return

    receipt = conn.execute(text(
        """
        SELECT purchase_at, purchase_at_source
        FROM receipt_tables
        WHERE id = :receipt_table_id
          AND household_id = :household_id
        LIMIT 1
        """
    ), {
        "receipt_table_id": receipt_table_id,
        "household_id": str(household_id),
    }).mappings().first()
    if not receipt or not str(receipt.get("purchase_at") or "").strip():
        return

    purchase_at = str(receipt.get("purchase_at") or "").strip()
    purchase_at_source = str(receipt.get("purchase_at_source") or "").strip().lower()
    # Import-default midnight is not a detected time and must remain date-precision.
    precision = "date" if purchase_at_source == "import_default" else "datetime"
    if len(purchase_at) == 10:
        purchase_at = f"{purchase_at}T00:00:00+00:00"
        precision = "date"

    conn.execute(text(
        """
        UPDATE inventory_events
        SET effective_at = :effective_at,
            effective_at_precision = :precision,
            event_priority = 10,
            source_reference = :source_reference,
            source_line_id = :source_line_id
        WHERE id = :event_id
        """
    ), {
        "effective_at": purchase_at,
        "precision": precision,
        "source_reference": source_reference,
        "source_line_id": str(line.get("line_id") or ""),
        "event_id": str(event.get("id")),
    })


def _reconcile_if_temporal_event_exists(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    inventory_id: str,
    quantity: int,
    space_id: str | None,
    sublocation_id: str | None,
) -> None:
    # Some deliberately minimal isolated tests do not create inventory_events.
    if not _temporal_ledger_available_for_article(conn, household_id, household_article_id):
        return
    _hydrate_latest_receipt_purchase_event(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
        quantity=int(quantity),
        space_id=space_id,
        sublocation_id=sublocation_id,
    )
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
            quantity=quantity_value,
            space_id=normalized_space_id,
            sublocation_id=normalized_sublocation_id,
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
        quantity=quantity_value,
        space_id=normalized_space_id,
        sublocation_id=normalized_sublocation_id,
    )
    return inventory_id
