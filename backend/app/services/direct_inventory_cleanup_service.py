"""Controlled cleanup of obsolete Direct / Direct inventory artifacts.

DIRECT_CONSUMPTION is a financial/processing concept, not physical stock.
This service therefore removes only inventory rows stored on the exact protected
Direct / Direct location. Purchase and processing history are deliberately not
touched.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine


@dataclass
class DirectInventoryCleanupReport:
    dry_run: bool
    stale_rows: int = 0
    stale_quantity: int = 0
    removed_rows: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _required_schema_available(conn: Connection) -> bool:
    inspector = inspect(conn)
    required = {"inventory", "spaces", "sublocations"}
    return required.issubset(set(inspector.get_table_names()))


def _load_direct_inventory_rows(conn: Connection, household_id: str | None = None):
    household_filter = ""
    params: dict[str, Any] = {}
    normalized_household_id = str(household_id or "").strip()
    if normalized_household_id:
        household_filter = " AND i.household_id = :household_id"
        params["household_id"] = normalized_household_id

    return conn.execute(
        text(
            f"""
            SELECT
                i.id AS inventory_id,
                i.household_id,
                i.household_article_id,
                i.naam AS article_name,
                COALESCE(i.aantal, 0) AS quantity,
                i.space_id,
                i.sublocation_id
            FROM inventory i
            JOIN spaces s
              ON s.id = i.space_id
             AND s.household_id = i.household_id
            JOIN sublocations sl
              ON sl.id = i.sublocation_id
             AND sl.space_id = s.id
            WHERE lower(trim(COALESCE(s.naam, ''))) = 'direct'
              AND lower(trim(COALESCE(sl.naam, ''))) = 'direct'
              {household_filter}
            ORDER BY i.household_id, i.household_article_id, i.id
            """
        ),
        params,
    ).mappings().all()


def cleanup_direct_inventory_artifacts(
    bind: Engine | Connection,
    *,
    dry_run: bool = True,
    household_id: str | None = None,
) -> DirectInventoryCleanupReport:
    """Report or delete invalid physical stock stored at Direct / Direct.

    The operation is idempotent. A dry-run performs no writes. Apply mode only
    deletes matching inventory rows; inventory_events, purchase-import data and
    day_article_processing_events remain untouched for reporting/audit purposes.
    """
    owns_transaction = isinstance(bind, Engine)
    context = bind.begin() if owns_transaction else None
    conn = context.__enter__() if context is not None else bind
    try:
        report = DirectInventoryCleanupReport(dry_run=dry_run)
        if not _required_schema_available(conn):
            if context is not None:
                context.__exit__(None, None, None)
            return report

        rows = _load_direct_inventory_rows(conn, household_id)
        report.stale_rows = len(rows)
        report.stale_quantity = sum(int(row.get("quantity") or 0) for row in rows)
        report.details = [
            {
                "inventory_id": str(row.get("inventory_id") or ""),
                "household_id": str(row.get("household_id") or ""),
                "household_article_id": str(row.get("household_article_id") or ""),
                "article_name": str(row.get("article_name") or ""),
                "quantity": int(row.get("quantity") or 0),
            }
            for row in rows
        ]

        if not dry_run and rows:
            ids = [str(row["inventory_id"]) for row in rows]
            for inventory_id in ids:
                result = conn.execute(
                    text("DELETE FROM inventory WHERE id = :inventory_id"),
                    {"inventory_id": inventory_id},
                )
                report.removed_rows += int(result.rowcount or 0)

        if context is not None:
            context.__exit__(None, None, None)
        return report
    except Exception as exc:
        if context is not None:
            context.__exit__(type(exc), exc, exc.__traceback__)
        raise
