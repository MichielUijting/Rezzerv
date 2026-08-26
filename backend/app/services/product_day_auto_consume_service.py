from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from sqlalchemy import inspect, text


AUTO_CONSUME_NONE = "none"
AUTO_CONSUME_PURCHASED_QUANTITY = "consume_purchased_quantity"
AUTO_CONSUME_ALL_EXISTING = "consume_all_existing_before_purchase"


def _as_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _canonical_purchase_day(value: Any) -> str | None:
    """Return the canonical YYYY-MM-DD product-day key when possible.

    Receipt ingestion normally supplies an ISO date/time. The fallback regex
    deliberately accepts an ISO date prefix as well so timezone-bearing values
    keep their receipt-local calendar day. A non-ISO/unknown value fails closed
    to the legacy per-purchase behavior in the caller.
    """
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


def _inventory_event_columns(conn) -> set[str]:
    try:
        return {str(column.get("name") or "") for column in inspect(conn).get_columns("inventory_events")}
    except Exception:
        return set()


def _first_product_day_purchase_old_quantity(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    purchase_day: str,
    columns: set[str],
) -> int | None:
    if not {"household_id", "household_article_id", "purchase_date", "event_type", "source", "old_quantity"}.issubset(columns):
        return None

    if "effective_at" in columns:
        order_sql = "datetime(COALESCE(effective_at, purchase_date, created_at)) ASC"
    elif "created_at" in columns:
        order_sql = "datetime(COALESCE(purchase_date, created_at)) ASC"
    else:
        order_sql = "purchase_date ASC"

    if "event_priority" in columns:
        order_sql += ", event_priority ASC"
    if "source_reference" in columns:
        order_sql += ", COALESCE(source_reference, '') ASC"
    if "source_line_id" in columns:
        order_sql += ", COALESCE(source_line_id, '') ASC"
    order_sql += ", id ASC"

    row = conn.execute(
        text(
            f"""
            SELECT old_quantity
            FROM inventory_events
            WHERE household_id = :household_id
              AND household_article_id = :household_article_id
              AND event_type = 'purchase'
              AND source = 'store_import'
              AND substr(trim(COALESCE(purchase_date, '')), 1, 10) = :purchase_day
            ORDER BY {order_sql}
            LIMIT 1
            """
        ),
        {
            "household_id": str(household_id),
            "household_article_id": str(household_article_id),
            "purchase_day": purchase_day,
        },
    ).mappings().first()
    if not row:
        return None
    return _as_non_negative_int(row.get("old_quantity"))


def _product_day_totals(
    conn,
    *,
    household_id: str,
    household_article_id: str,
    purchase_day: str,
    columns: set[str],
) -> tuple[int, int]:
    required = {"household_id", "household_article_id", "purchase_date", "event_type", "source", "quantity"}
    if not required.issubset(columns):
        return 0, 0

    row = conn.execute(
        text(
            """
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
                ), 0) AS auto_consumed_quantity
            FROM inventory_events
            WHERE household_id = :household_id
              AND household_article_id = :household_article_id
              AND substr(trim(COALESCE(purchase_date, '')), 1, 10) = :purchase_day
            """
        ),
        {
            "household_id": str(household_id),
            "household_article_id": str(household_article_id),
            "purchase_day": purchase_day,
        },
    ).mappings().first()
    if not row:
        return 0, 0
    return (
        _as_non_negative_int(row.get("purchased_quantity")),
        _as_non_negative_int(row.get("auto_consumed_quantity")),
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
    + receipt purchase calendar day form one cumulative purchase. The amount
    bought earlier on that same day therefore never becomes fresh "old stock"
    merely because a second receipt is processed later.

    The function is deliberately fail-closed: if the purchase date or canonical
    event columns are unavailable, it returns the legacy per-purchase deduction.
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
    if not purchase_day or not str(household_article_id or "").strip():
        return {
            "requested_deduction_quantity": legacy_requested,
            "product_day_applied": False,
            "purchase_day": purchase_day,
            "day_start_stock": pre_purchase_total_int,
            "prior_day_purchased_quantity": 0,
            "prior_day_auto_consumed_quantity": 0,
            "cumulative_day_purchased_quantity": purchased_quantity_int,
        }

    columns = _inventory_event_columns(conn)
    required = {"id", "household_id", "household_article_id", "purchase_date", "event_type", "source", "quantity", "old_quantity"}
    if not required.issubset(columns):
        return {
            "requested_deduction_quantity": legacy_requested,
            "product_day_applied": False,
            "purchase_day": purchase_day,
            "day_start_stock": pre_purchase_total_int,
            "prior_day_purchased_quantity": 0,
            "prior_day_auto_consumed_quantity": 0,
            "cumulative_day_purchased_quantity": purchased_quantity_int,
        }

    prior_day_purchased, prior_day_auto_consumed = _product_day_totals(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
        purchase_day=purchase_day,
        columns=columns,
    )
    first_old_quantity = _first_product_day_purchase_old_quantity(
        conn,
        household_id=str(household_id),
        household_article_id=str(household_article_id),
        purchase_day=purchase_day,
        columns=columns,
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
    # Never ask the legacy inventory mutation to consume more stock than existed
    # immediately before the current purchase. This also keeps the newly added
    # current receipt quantity protected by the existing mutation contract.
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
