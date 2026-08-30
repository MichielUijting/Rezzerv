from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services.temporal_inventory_service import (
    ensure_temporal_inventory_schema,
    reconcile_inventory_total,
)


def _receipt_source_reference(receipt_table_id: str) -> str:
    return f"receipt:{str(receipt_table_id).strip()}"


def _reconcile_article_projection(conn, *, household_id: str, household_article_id: str) -> None:
    """Replay the canonical ledger and reconcile the production inventory projection."""
    reconcile_inventory_total(
        conn,
        household_id=household_id,
        household_article_id=household_article_id,
    )


def remove_receipt_inventory_events(
    conn,
    *,
    receipt_table_id: str,
    household_id: str | None = None,
) -> dict[str, Any]:
    """Remove inventory effects of an already unpacked receipt and replay affected articles.

    This is intentionally source-based. A receipt can have been imported at any time;
    deleting it removes the events tied to its stable receipt source reference and then
    rebuilds the chronological projection for every affected household article.
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
            SELECT id,
                   household_id,
                   COALESCE(household_article_id, article_id) AS household_article_id
            FROM inventory_events
            WHERE source_reference = :source_reference
              {household_clause}
            ORDER BY household_article_id, id
            """
        ),
        params,
    ).mappings().all()
    affected = sorted(
        {
            (str(row["household_id"]), str(row["household_article_id"]))
            for row in rows
            if row.get("household_article_id") not in (None, "")
        }
    )

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

    for affected_household_id, household_article_id in affected:
        _reconcile_article_projection(
            conn,
            household_id=affected_household_id,
            household_article_id=household_article_id,
        )

    return {
        "receipt_table_id": receipt_table_id,
        "removed_event_count": len(rows),
        "affected_articles": [household_article_id for _, household_article_id in affected],
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
        return {
            "receipt_table_id": receipt_table_id,
            "updated_event_count": 0,
            "affected_articles": [],
        }

    source_reference = _receipt_source_reference(receipt_table_id)
    normalized_purchase_at = str(purchase_at).strip()
    purchase_date = normalized_purchase_at[:10] if ("T" in normalized_purchase_at or " " in normalized_purchase_at) else normalized_purchase_at
    params: dict[str, Any] = {
        "source_reference": source_reference,
        "purchase_at": normalized_purchase_at,
        "purchase_date": purchase_date,
    }
    household_clause = ""
    if household_id:
        household_clause = " AND household_id = :household_id"
        params["household_id"] = household_id

    rows = conn.execute(
        text(
            f"""
            SELECT household_id,
                   COALESCE(household_article_id, article_id) AS household_article_id
            FROM inventory_events
            WHERE source_reference = :source_reference
              {household_clause}
            """
        ),
        params,
    ).mappings().all()
    affected = sorted(
        {
            (str(row["household_id"]), str(row["household_article_id"]))
            for row in rows
            if row.get("household_article_id") not in (None, "")
        }
    )

    precision = "datetime" if ("T" in normalized_purchase_at or " " in normalized_purchase_at) else "date"
    conn.execute(
        text(
            f"""
            UPDATE inventory_events
            SET effective_at = :purchase_at,
                purchase_date = :purchase_date,
                effective_at_precision = :precision
            WHERE source_reference = :source_reference
              {household_clause}
            """
        ),
        {**params, "precision": precision},
    )

    for affected_household_id, household_article_id in affected:
        _reconcile_article_projection(
            conn,
            household_id=affected_household_id,
            household_article_id=household_article_id,
        )

    return {
        "receipt_table_id": receipt_table_id,
        "updated_event_count": len(rows),
        "affected_articles": [household_article_id for _, household_article_id in affected],
    }
