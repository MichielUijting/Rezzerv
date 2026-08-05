from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.services.day_article_service import (
    DIRECT_CONSUMPTION,
    STOCK,
    get_default_inventory_handling,
    record_direct_consumption,
)


def get_line_inventory_handling_override(conn, *, household_id: str, line_id: str) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT inventory_handling
            FROM purchase_import_line_inventory_handling_overrides
            WHERE purchase_import_line_id = :line_id
              AND household_id = :household_id
            LIMIT 1
            """
        ),
        {"line_id": str(line_id), "household_id": str(household_id)},
    ).mappings().first()
    if not row:
        return None
    value = str(row.get("inventory_handling") or "").strip().upper()
    return value if value in {STOCK, DIRECT_CONSUMPTION} else None


def resolve_effective_line_inventory_handling(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    line_id: str,
) -> str:
    override = get_line_inventory_handling_override(
        conn,
        household_id=household_id,
        line_id=line_id,
    )
    if override:
        return override
    article = get_default_inventory_handling(
        conn,
        household_id,
        household_article_id,
    )
    value = str(article.get("default_inventory_handling") or STOCK).strip().upper()
    return value if value in {STOCK, DIRECT_CONSUMPTION} else STOCK


def process_direct_purchase_import_line(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    line_id: str,
    quantity: Decimal | int | float | str,
    actor_user_id: str,
) -> dict[str, Any]:
    """Register receipt and immediate consumption without changing inventory.

    The purchase-import line id is stable and therefore forms the idempotency
    key. Replaying the same batch action cannot create a second receipt or
    consumption pair.
    """
    result = record_direct_consumption(
        conn,
        household_id=household_id,
        household_article_id=household_article_id,
        quantity=quantity,
        idempotency_key=f"purchase-import-line:{str(line_id)}",
        actor_user_id=actor_user_id,
    )
    return {
        **result,
        "purchase_import_line_id": str(line_id),
        "inventory_mutation_skipped": True,
    }
