from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.services.temporal_inventory_service import (
    ensure_temporal_inventory_schema,
    replay_inventory_events,
)


def _receipt_source_reference(receipt_table_id: str) -> str:
    return f"receipt:{str(receipt_table_id).strip()}"


def _event_quantity(row: dict[str, Any]) -> Decimal:
    old_quantity = Decimal(str(row.get("old_quantity") or 0))
    new_quantity = Decimal(str(row.get("new_quantity") or 0))
    return new_quantity - old_quantity


def _reconcile_article_projection(conn, *, household_id: str, article_id: str) -> None:
    replay = replay_inventory_events(conn, household_id=household_id, article_id=article_id)
    target_quantity = Decimal(str(replay.get("final_quantity") or 0))

    current_quantity = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(CAST(quantity AS NUMERIC)), 0)
            FROM inventory_location_quantities
            WHERE household_id = :household_id
              AND article_id = :article_id
            """
        ),
        {"household_id": household_id, "article_id": article_id},
    ).scalar()
    current_quantity = Decimal(str(current_quantity or 0))
    delta = target_quantity - current_quantity
    if delta == 0:
        return

    location_row = conn.execute(
        text(
            """
            SELECT location_id, quantity
            FROM inventory_location_quantities
            WHERE household_id = :household_id
              AND article_id = :article_id
            ORDER BY CASE WHEN CAST(quantity AS NUMERIC) > 0 THEN 0 ELSE 1 END,
                     location_id
            LIMIT 1
            """
        ),
        {"household_id": household_id, "article_id": article_id},
    ).mappings().first()
    if not location_row:
        # No location projection exists. The normal unpacking flow creates it;
        # lifecycle replay must not invent a household location silently.
        return

    conn.execute(
        text(
            """
            UPDATE inventory_location_quantities
            SET quantity = CAST(quantity AS NUMERIC) + :delta,
                updated_at = CURRENT_TIMESTAMP
            WHERE household_id = :household_id
              AND article_id = :article_id
              AND location_id = :location_id
            """
        ),
        {
            "delta": float(delta),
            "household_id": household_id,
            "article_id": article_id,
            "location_id": location_row["location_id"],
        },
    )


def remove_receipt_inventory_events(conn, *, receipt_table_id: str, household_id: str | None = None) -> dict[str, Any]:
    """Remove inventory effects of an already unpacked receipt and replay affected articles.

    This is intentionally source-based. A receipt can have been imported at any time;
    deleting it removes the events tied to its stable receipt source reference and then
    rebuilds the chronological projection for every affected article.
    """
    ensure_temporal_inventory_schema(conn)
    source_reference = _receipt_source_reference(receipt_table_id)
    params: dict[str, Any] = {"source_reference": source_reference}
    household_clause = ""
    if household_id:
        household_clause = " AND household_id = :household_id"
        params["household_id"] = household_id

    rows = conn.execute(
        text(
            f"""
            SELECT id, household_id, article_id, old_quantity, new_quantity
            FROM inventory_events
            WHERE source_reference = :source_reference
              {household_clause}
            ORDER BY article_id, id
            """
        ),
        params,
    ).mappings().all()
    affected = sorted({(str(row["household_id"]), str(row["article_id"])) for row in rows})

    conn.execute(
        text(
            f"""
            DELETE FROM inventory_events
            WHERE source_reference = :source_reference
              {household_clause}
            """
        ),
        params,
    )

    for affected_household_id, article_id in affected:
        _reconcile_article_projection(
            conn,
            household_id=affected_household_id,
            article_id=article_id,
        )

    return {
        "receipt_table_id": receipt_table_id,
        "removed_event_count": len(rows),
        "affected_articles": [article_id for _, article_id in affected],
    }


def retime_receipt_inventory_events(
    conn,
    *,
    receipt_table_id: str,
    purchase_at: str | None,
    household_id: str | None = None,
) -> dict[str, Any]:
    """Move existing unpacked receipt events to a corrected receipt timestamp and replay."""
    ensure_temporal_inventory_schema(conn)
    if purchase_at in (None, ""):
        return {"receipt_table_id": receipt_table_id, "updated_event_count": 0, "affected_articles": []}

    source_reference = _receipt_source_reference(receipt_table_id)
    params: dict[str, Any] = {
        "source_reference": source_reference,
        "purchase_at": str(purchase_at),
    }
    household_clause = ""
    if household_id:
        household_clause = " AND household_id = :household_id"
        params["household_id"] = household_id

    rows = conn.execute(
        text(
            f"""
            SELECT household_id, article_id
            FROM inventory_events
            WHERE source_reference = :source_reference
              {household_clause}
            """
        ),
        params,
    ).mappings().all()
    affected = sorted({(str(row["household_id"]), str(row["article_id"])) for row in rows})

    precision = "datetime" if ("T" in str(purchase_at) or " " in str(purchase_at).strip()) else "date"
    conn.execute(
        text(
            f"""
            UPDATE inventory_events
            SET effective_at = :purchase_at,
                purchase_date = CASE
                    WHEN instr(:purchase_at, 'T') > 0 THEN substr(:purchase_at, 1, 10)
                    WHEN instr(:purchase_at, ' ') > 0 THEN substr(:purchase_at, 1, 10)
                    ELSE :purchase_at
                END,
                effective_at_precision = :precision
            WHERE source_reference = :source_reference
              {household_clause}
            """
        ),
        {**params, "precision": precision},
    )

    for affected_household_id, article_id in affected:
        _reconcile_article_projection(
            conn,
            household_id=affected_household_id,
            article_id=article_id,
        )

    return {
        "receipt_table_id": receipt_table_id,
        "updated_event_count": len(rows),
        "affected_articles": [article_id for _, article_id in affected],
    }
