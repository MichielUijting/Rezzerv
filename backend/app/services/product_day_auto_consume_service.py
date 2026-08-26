from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


AUTO_CONSUME_NONE = "none"
AUTO_CONSUME_PURCHASED_QUANTITY = "consume_purchased_quantity"
AUTO_CONSUME_ALL_EXISTING = "consume_all_existing_before_purchase"


def _as_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _canonical_purchase_day(value: Any) -> str | None:
    """Return the receipt-local YYYY-MM-DD product-day key when possible."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    raw = str(value or "").strip()
    if not raw:
        return None

    match = re.match(r"^(\d{4}-\d{2}-\d{2})(?:$|[T\s])", raw)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1)).isoformat()
    except ValueError:
        return None


def _legacy_requested_deduction(mode: str, pre_purchase_total: Any, purchased_quantity: Any) -> int:
    pre_purchase_total_int = _as_non_negative_int(pre_purchase_total)
    purchased_quantity_int = _as_non_negative_int(purchased_quantity)
    normalized_mode = str(mode or "").strip().lower()
    if pre_purchase_total_int <= 0:
        return 0
    if normalized_mode == AUTO_CONSUME_PURCHASED_QUANTITY:
        return purchased_quantity_int
    if normalized_mode == AUTO_CONSUME_ALL_EXISTING:
        return pre_purchase_total_int
    return 0


def _fallback_result(
    *,
    requested: int,
    purchase_day: str | None,
    pre_purchase_total: int,
    purchased_quantity: int,
) -> dict[str, Any]:
    return {
        "requested_deduction_quantity": requested,
        "product_day_applied": False,
        "purchase_day": purchase_day,
        "day_start_stock": pre_purchase_total,
        "prior_day_purchased_quantity": 0,
        "prior_day_auto_consumed_quantity": 0,
        "cumulative_day_purchased_quantity": purchased_quantity,
    }


def _read_product_day_state(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    purchase_day: str,
) -> tuple[int, int, int | None]:
    """Read all prior product-day state with one indexed-scope SQL statement.

    The canonical event table already carries household/article/date lineage.
    Avoiding per-line schema introspection keeps this rule out of the Uitpakken
    performance hot path. If an older datastore lacks a required temporal/event
    column, the caller catches the SQL error and deliberately uses legacy logic.
    """
    row = conn.execute(
        text(
            """
            WITH day_events AS (
                SELECT
                    id,
                    event_type,
                    source,
                    quantity,
                    old_quantity,
                    effective_at,
                    event_priority,
                    source_reference,
                    source_line_id,
                    purchase_date
                FROM inventory_events
                WHERE household_id = :household_id
                  AND household_article_id = :household_article_id
                  AND substr(trim(COALESCE(purchase_date, '')), 1, 10) = :purchase_day
            )
            SELECT
                COALESCE(SUM(
                    CASE
                        WHEN event_type = 'purchase' AND source = 'store_import'
                        THEN ABS(COALESCE(quantity, 0))
                        ELSE 0
                    END
                ), 0) AS purchased_quantity,
                COALESCE(SUM(
                    CASE
                        WHEN event_type = 'auto_repurchase' AND source = 'auto_repurchase'
                        THEN ABS(COALESCE(quantity, 0))
                        ELSE 0
                    END
                ), 0) AS auto_consumed_quantity,
                (
                    SELECT old_quantity
                    FROM day_events first_purchase
                    WHERE first_purchase.event_type = 'purchase'
                      AND first_purchase.source = 'store_import'
                    ORDER BY
                        datetime(COALESCE(first_purchase.effective_at, first_purchase.purchase_date)) ASC,
                        COALESCE(first_purchase.event_priority, 0) ASC,
                        COALESCE(first_purchase.source_reference, '') ASC,
                        COALESCE(first_purchase.source_line_id, '') ASC,
                        first_purchase.id ASC
                    LIMIT 1
                ) AS first_purchase_old_quantity
            FROM day_events
            """
        ),
        {
            "household_id": str(household_id),
            "household_article_id": str(household_article_id),
            "purchase_day": purchase_day,
        },
    ).mappings().one()

    first_old_raw = row.get("first_purchase_old_quantity")
    return (
        _as_non_negative_int(row.get("purchased_quantity")),
        _as_non_negative_int(row.get("auto_consumed_quantity")),
        None if first_old_raw is None else _as_non_negative_int(first_old_raw),
    )


def compute_product_day_auto_deduction(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    purchase_date: Any,
    mode: str,
    pre_purchase_total: Any,
    purchased_quantity: Any,
) -> dict[str, Any]:
    """Compute the incremental auto-consume quantity for one product-day.

    All receipt purchases for the same household + canonical household article
    + receipt purchase calendar day form one cumulative purchase. Stock bought
    earlier on that same day therefore cannot reset the old-stock target when a
    second or later receipt is unpacked.
    """
    normalized_mode = str(mode or "").strip().lower()
    pre_purchase_total_int = _as_non_negative_int(pre_purchase_total)
    purchased_quantity_int = _as_non_negative_int(purchased_quantity)
    legacy_requested = _legacy_requested_deduction(
        normalized_mode,
        pre_purchase_total_int,
        purchased_quantity_int,
    )

    purchase_day = _canonical_purchase_day(purchase_date)
    normalized_article_id = str(household_article_id or "").strip()
    if not purchase_day or not normalized_article_id:
        return _fallback_result(
            requested=legacy_requested,
            purchase_day=purchase_day,
            pre_purchase_total=pre_purchase_total_int,
            purchased_quantity=purchased_quantity_int,
        )

    try:
        prior_day_purchased, prior_day_auto_consumed, first_old_quantity = _read_product_day_state(
            conn,
            household_id=str(household_id),
            household_article_id=normalized_article_id,
            purchase_day=purchase_day,
        )
    except SQLAlchemyError:
        return _fallback_result(
            requested=legacy_requested,
            purchase_day=purchase_day,
            pre_purchase_total=pre_purchase_total_int,
            purchased_quantity=purchased_quantity_int,
        )

    day_start_stock = pre_purchase_total_int if first_old_quantity is None else first_old_quantity
    cumulative_day_purchased = prior_day_purchased + purchased_quantity_int

    if normalized_mode == AUTO_CONSUME_PURCHASED_QUANTITY:
        desired_total_auto_consumed = min(day_start_stock, cumulative_day_purchased)
    elif normalized_mode == AUTO_CONSUME_ALL_EXISTING:
        desired_total_auto_consumed = day_start_stock if cumulative_day_purchased > 0 else 0
    else:
        desired_total_auto_consumed = 0

    incremental = max(0, desired_total_auto_consumed - prior_day_auto_consumed)
    # The existing inventory mutation protects the current purchase quantity.
    # Never request more consumption than stock that existed immediately before
    # the current receipt was added.
    incremental = min(incremental, pre_purchase_total_int)

    return {
        "requested_deduction_quantity": incremental,
        "product_day_applied": True,
        "purchase_day": purchase_day,
        "day_start_stock": day_start_stock,
        "prior_day_purchased_quantity": prior_day_purchased,
        "prior_day_auto_consumed_quantity": prior_day_auto_consumed,
        "cumulative_day_purchased_quantity": cumulative_day_purchased,
    }
