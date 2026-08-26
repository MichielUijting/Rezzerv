"""Canonical inventory identity operations for Slice 2B4.

Inventory identity is household_id + household_article_id + location.
The inventory.naam column is maintained only as a presentation/snapshot value.

From v01.12.78 the current inventory projection is reconciled with the existing
inventory_events ledger after a purchase mutation. This keeps the visible stock
independent from receipt import order while preserving the existing location model.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import uuid

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.services.temporal_inventory_service import (
    ensure_temporal_inventory_schema,
    reconcile_inventory_total,
)


LOCATIONLESS_ACTIVE_IDENTITY_INDEX = "uq_inventory_active_locationless_household_article"
TEMPORAL_PURCHASE_FAST_PATH_COLUMNS = {
    "household_article_id",
    "effective_at",
    "recorded_at",
    "effective_at_precision",
    "event_priority",
    "source_reference",
    "source_line_id",
}


def _normalize(value: object | None) -> str:
    return str(value or "").strip()


def _as_decimal_or_none(value: object | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


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


def _index_exists(conn, index_name: str) -> bool:
    return bool(conn.execute(text(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name LIMIT 1"
    ), {"name": str(index_name)}).scalar())


def _inventory_event_columns(conn) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(text("PRAGMA table_info(inventory_events)")).fetchall()
    }


def _ensure_temporal_purchase_fast_path_schema(conn) -> None:
    """Only run the legacy global schema/backfill ensure when columns are missing.

    Current databases already carry the temporal columns. Normal Uitpakken purchases
    must not scan the full inventory_events ledger merely to prove that again. Older
    databases still fall back to the canonical full ensure once before using this path.
    """
    columns = _inventory_event_columns(conn)
    if TEMPORAL_PURCHASE_FAST_PATH_COLUMNS.issubset(columns):
        return
    ensure_temporal_inventory_schema(conn)
    columns = _inventory_event_columns(conn)
    if not TEMPORAL_PURCHASE_FAST_PATH_COLUMNS.issubset(columns):
        raise RuntimeError("Temporeel inventory_events schema is niet volledig geinitialiseerd")


def ensure_locationless_inventory_identity_guard(conn) -> None:
    """Protect the single active NULL/NULL row per household article in SQLite.

    The expensive duplicate scan is only needed before the unique index exists. Once
    SQLite has installed that index, the index itself is the canonical race/integrity
    guard and repeating the full grouped scan on every purchase is unnecessary.
    """
    if not _table_exists(conn, "inventory"):
        return
    if _index_exists(conn, LOCATIONLESS_ACTIVE_IDENTITY_INDEX):
        return

    columns = {
        str(row[1])
        for row in conn.execute(text("PRAGMA table_info(inventory)")).fetchall()
    }
    required_columns = {
        "household_id",
        "household_article_id",
        "space_id",
        "sublocation_id",
        "status",
    }
    if not required_columns.issubset(columns):
        return

    duplicate = conn.execute(text(
        """
        SELECT household_id, household_article_id, COUNT(*) AS row_count
        FROM inventory
        WHERE COALESCE(status, 'active') = 'active'
          AND household_article_id IS NOT NULL
          AND space_id IS NULL
          AND sublocation_id IS NULL
        GROUP BY household_id, household_article_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    )).mappings().first()
    if duplicate:
        raise RuntimeError(
            "Dubbele actieve locationless voorraadidentiteit gevonden voor "
            f"household_id={duplicate['household_id']} en "
            f"household_article_id={duplicate['household_article_id']}"
        )

    conn.execute(text(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {LOCATIONLESS_ACTIVE_IDENTITY_INDEX}
        ON inventory (household_id, household_article_id)
        WHERE COALESCE(status, 'active') = 'active'
          AND household_article_id IS NOT NULL
          AND space_id IS NULL
          AND sublocation_id IS NULL
        """
    ))


def _temporal_ledger_available_for_article(conn, household_id: str, household_article_id: str) -> bool:
    if not _table_exists(conn, "inventory_events"):
        return False
    columns = _inventory_event_columns(conn)
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
) -> str | None:
    """Attach the exact receipt timestamp to the event just created by Uitpakken.

    The legacy batch payload deliberately stores a date label. The authoritative
    receipt row still contains ``purchase_at`` (including time when detected). The
    stock event is linked back to that receipt before chronological evaluation.
    No match means this was not a receipt-driven purchase and nothing is changed.
    """
    required_tables = {
        "inventory_events",
        "purchase_import_batches",
        "purchase_import_lines",
        "receipt_tables",
    }
    if not all(_table_exists(conn, table_name) for table_name in required_tables):
        return None

    _ensure_temporal_purchase_fast_path_schema(conn)
    location_id = _normalize(sublocation_id) or _normalize(space_id) or None

    event = conn.execute(text(
        """
        SELECT id, location_id, quantity, source_reference, created_at
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
        return None

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
        return None

    source_reference = str(line.get("source_reference") or "").strip()
    if not source_reference.startswith("receipt:"):
        return None
    receipt_table_id = source_reference.split(":", 1)[1].strip()
    if not receipt_table_id:
        return None

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
        return None

    purchase_at = str(receipt.get("purchase_at") or "").strip()
    purchase_at_source = str(receipt.get("purchase_at_source") or "").strip().lower()
    # Import-default midnight is not a detected time and must remain date-precision.
    precision = "date" if purchase_at_source == "import_default" else "datetime"
    if len(purchase_at) == 10:
        purchase_at = f"{purchase_at}T00:00:00+00:00"
        precision = "date"

    event_id = str(event.get("id"))
    conn.execute(text(
        """
        UPDATE inventory_events
        SET effective_at = :effective_at,
            recorded_at = COALESCE(NULLIF(trim(recorded_at), ''), :recorded_at),
            effective_at_precision = :precision,
            event_priority = 10,
            source_reference = :source_reference,
            source_line_id = :source_line_id
        WHERE id = :event_id
        """
    ), {
        "effective_at": purchase_at,
        "recorded_at": str(event.get("created_at") or "").strip() or purchase_at,
        "precision": precision,
        "source_reference": source_reference,
        "source_line_id": str(line.get("line_id") or ""),
        "event_id": event_id,
    })
    return event_id


def _receipt_purchase_can_use_append_fast_path(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    purchase_event_id: str,
) -> bool:
    """Return True only when the new receipt event is a safe chronological tail append.

    The fast path is deliberately conservative. Any incomplete temporal history,
    backdated/tie-reordered purchase, balance mismatch, or projection drift falls back
    to the canonical full chronological reconcile.
    """
    normalized_event_id = _normalize(purchase_event_id)
    if not normalized_event_id:
        return False

    incomplete = conn.execute(text(
        """
        SELECT 1
        FROM inventory_events
        WHERE household_id = :household_id
          AND COALESCE(household_article_id, article_id) = :household_article_id
          AND (
                COALESCE(trim(effective_at), '') = ''
             OR COALESCE(trim(recorded_at), '') = ''
             OR COALESCE(trim(effective_at_precision), '') = ''
             OR event_priority IS NULL
             OR old_quantity IS NULL
             OR new_quantity IS NULL
          )
        LIMIT 1
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
    }).scalar()
    if incomplete:
        return False

    tail = conn.execute(text(
        """
        SELECT id, event_type, quantity, old_quantity, new_quantity,
               source, source_reference, source_line_id
        FROM inventory_events
        WHERE household_id = :household_id
          AND COALESCE(household_article_id, article_id) = :household_article_id
        ORDER BY datetime(effective_at) DESC,
                 event_priority DESC,
                 COALESCE(source_reference, '') DESC,
                 COALESCE(source_line_id, '') DESC,
                 id DESC
        LIMIT 2
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
    }).mappings().all()
    if not tail or str(tail[0].get("id") or "") != normalized_event_id:
        return False

    purchase = tail[0]
    if str(purchase.get("event_type") or "").strip().lower() != "purchase":
        return False
    if str(purchase.get("source") or "").strip().lower() != "store_import":
        return False
    if not str(purchase.get("source_reference") or "").strip():
        return False
    if not str(purchase.get("source_line_id") or "").strip():
        return False

    old_quantity = _as_decimal_or_none(purchase.get("old_quantity"))
    new_quantity = _as_decimal_or_none(purchase.get("new_quantity"))
    quantity = _as_decimal_or_none(purchase.get("quantity"))
    if old_quantity is None or new_quantity is None or quantity is None:
        return False
    if new_quantity != old_quantity + abs(quantity):
        return False

    if len(tail) == 1:
        if old_quantity != Decimal("0"):
            return False
    else:
        previous_new = _as_decimal_or_none(tail[1].get("new_quantity"))
        if previous_new is None or previous_new != old_quantity:
            return False

    projected_total = _as_decimal_or_none(conn.execute(text(
        """
        SELECT COALESCE(SUM(aantal), 0)
        FROM inventory
        WHERE household_id = :household_id
          AND household_article_id = :household_article_id
          AND COALESCE(status, 'active') = 'active'
        """
    ), {
        "household_id": str(household_id),
        "household_article_id": str(household_article_id),
    }).scalar())
    return projected_total is not None and projected_total == new_quantity


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
    purchase_event_id = _hydrate_latest_receipt_purchase_event(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
        quantity=int(quantity),
        space_id=space_id,
        sublocation_id=sublocation_id,
    )
    if purchase_event_id and _receipt_purchase_can_use_append_fast_path(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
        purchase_event_id=purchase_event_id,
    ):
        return
    reconcile_inventory_total(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
        preferred_inventory_id=str(inventory_id),
    )


def _find_inventory_identity(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    space_id: str | None,
    sublocation_id: str | None,
):
    return conn.execute(
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
            "household_id": household_id,
            "household_article_id": household_article_id,
            "space_id": space_id,
            "sublocation_id": sublocation_id,
        },
    ).mappings().first()


def _increase_existing_inventory(
    conn,
    *,
    inventory_id: str,
    household_id: str,
    household_article_id: str,
    article_name_snapshot: str,
    quantity: int,
) -> None:
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
            "household_id": household_id,
            "household_article_id": household_article_id,
            "article_name_snapshot": article_name_snapshot,
            "quantity": quantity,
        },
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

    ensure_locationless_inventory_identity_guard(conn)
    existing = _find_inventory_identity(
        conn,
        household_id=normalized_household_id,
        household_article_id=normalized_article_id,
        space_id=normalized_space_id,
        sublocation_id=normalized_sublocation_id,
    )

    if existing:
        inventory_id = str(existing["id"])
        _increase_existing_inventory(
            conn,
            inventory_id=inventory_id,
            household_id=normalized_household_id,
            household_article_id=normalized_article_id,
            article_name_snapshot=article_name_snapshot,
            quantity=quantity_value,
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
    try:
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
    except IntegrityError:
        # Only the locationless identity has a database-level race guard in this slice.
        # If another writer won that race, merge into the canonical row it created.
        if normalized_space_id is not None or normalized_sublocation_id is not None:
            raise
        existing = _find_inventory_identity(
            conn,
            household_id=normalized_household_id,
            household_article_id=normalized_article_id,
            space_id=None,
            sublocation_id=None,
        )
        if not existing:
            raise
        inventory_id = str(existing["id"])
        _increase_existing_inventory(
            conn,
            inventory_id=inventory_id,
            household_id=normalized_household_id,
            household_article_id=normalized_article_id,
            article_name_snapshot=article_name_snapshot,
            quantity=quantity_value,
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
