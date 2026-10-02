from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


def _to_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def _tables(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _columns(conn: Connection, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {str(column.get("name") or "") for column in inspect(conn).get_columns(table_name)}


def _approved_receipts(conn: Connection, household_id: str) -> list[dict[str, Any]]:
    if "receipt_tables" not in _tables(conn):
        return []
    rows = conn.execute(text("""
        SELECT id, store_name, store_branch, purchase_at, total_amount, currency,
               parse_status, workflow_state, approved_at, created_at
        FROM receipt_tables
        WHERE household_id = :household_id
    """), {"household_id": str(household_id)}).mappings().all()

    approved = []
    for row in rows:
        parse_status = str(row.get("parse_status") or "").strip().lower()
        workflow_state = str(row.get("workflow_state") or "active").strip().lower()
        if workflow_state in {"archived", "deleted", "removed"}:
            continue
        if not row.get("approved_at") and parse_status not in {"approved", "approved_override"}:
            continue
        purchase_at = _to_datetime(row.get("purchase_at")) or _to_datetime(row.get("created_at"))
        if not purchase_at:
            continue
        approved.append({
            **dict(row),
            "_purchase_at": purchase_at,
            "_store": str(row.get("store_name") or row.get("store_branch") or "Onbekende winkel").strip() or "Onbekende winkel",
        })
    return approved


def _receipt_quantities(conn: Connection, household_id: str) -> dict[str, float]:
    if "receipt_table_lines" not in _tables(conn) or "receipt_tables" not in _tables(conn):
        return {}
    rows = conn.execute(text("""
        SELECT rtl.receipt_table_id, rtl.quantity
        FROM receipt_table_lines rtl
        JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
        WHERE rt.household_id = :household_id
    """), {"household_id": str(household_id)}).mappings().all()
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        quantity = _number(row.get("quantity"))
        totals[str(row.get("receipt_table_id") or "")] += quantity if quantity > 0 else 1.0
    return dict(totals)


def _shopping_count(conn: Connection, household_id: str) -> int:
    tables = _tables(conn)
    if not {"shopping_lists", "shopping_list_items"}.issubset(tables):
        return 0
    list_columns = _columns(conn, "shopping_lists")
    item_columns = _columns(conn, "shopping_list_items")
    required_list = {"id", "household_id", "status"}
    required_item = {"shopping_list_id", "household_id", "checked"}
    if not required_list.issubset(list_columns) or not required_item.issubset(item_columns):
        return 0
    rows = conn.execute(text("""
        SELECT sli.checked
        FROM shopping_list_items sli
        JOIN shopping_lists sl ON sl.id = sli.shopping_list_id
        WHERE sl.household_id = :household_id
          AND lower(trim(COALESCE(sl.status, 'active'))) = 'active'
          AND sli.household_id = :household_id
    """), {"household_id": str(household_id)}).mappings().all()
    return sum(
        1
        for row in rows
        if str(row.get("checked") or "").strip().lower() not in {"1", "true", "yes", "on"}
    )


def _notification_count(conn: Connection, household_id: str, user_id: str) -> int:
    if "household_notifications" not in _tables(conn):
        return 0
    columns = _columns(conn, "household_notifications")
    required = {"household_id", "recipient_user_id", "read_at"}
    if not required.issubset(columns):
        return 0
    value = conn.execute(text("""
        SELECT COUNT(*)
        FROM household_notifications
        WHERE household_id = :household_id
          AND (recipient_user_id IS NULL OR recipient_user_id = :user_id)
          AND read_at IS NULL
    """), {"household_id": str(household_id), "user_id": str(user_id)}).scalar()
    return int(value or 0)


def _put_away_counts(conn: Connection, household_id: str) -> tuple[int, int]:
    tables = _tables(conn)
    if "receipt_tables" not in tables or "receipt_table_lines" not in tables:
        return 0, 0

    receipt_columns = _columns(conn, "receipt_tables")
    line_columns = _columns(conn, "receipt_table_lines")
    if not {"id", "household_id", "workflow_state"}.issubset(receipt_columns):
        return 0, 0
    if not {"receipt_table_id"}.issubset(line_columns):
        return 0, 0

    batch_columns = _columns(conn, "purchase_import_batches")
    can_link_batches = {
        "id", "household_id", "source_type", "source_reference"
    }.issubset(batch_columns)

    if can_link_batches:
        kassa = conn.execute(text("""
            SELECT COUNT(*)
            FROM receipt_table_lines rtl
            JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
            WHERE rt.household_id = :household_id
              AND lower(trim(COALESCE(rt.workflow_state, 'active'))) = 'active'
              AND NOT EXISTS (
                  SELECT 1
                  FROM purchase_import_batches pib
                  WHERE pib.household_id = rt.household_id
                    AND pib.source_type = 'receipt'
                    AND pib.source_reference = ('receipt:' || rt.id)
              )
        """), {"household_id": str(household_id)}).scalar() or 0
    else:
        kassa = conn.execute(text("""
            SELECT COUNT(*)
            FROM receipt_table_lines rtl
            JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
            WHERE rt.household_id = :household_id
              AND lower(trim(COALESCE(rt.workflow_state, 'active'))) = 'active'
        """), {"household_id": str(household_id)}).scalar() or 0

    unpack = 0
    import_line_columns = _columns(conn, "purchase_import_lines")
    can_count_unpack = can_link_batches and {
        "batch_id", "processing_status"
    }.issubset(import_line_columns)
    if can_count_unpack:
        unpack = conn.execute(text("""
            SELECT COUNT(*)
            FROM purchase_import_lines pil
            JOIN purchase_import_batches pib ON pib.id = pil.batch_id
            WHERE pib.household_id = :household_id
              AND pib.source_type = 'receipt'
              AND lower(trim(COALESCE(pil.processing_status, 'pending'))) <> 'processed'
        """), {"household_id": str(household_id)}).scalar() or 0
    return int(kassa or 0), int(unpack or 0)


def build_household_dashboard(conn: Connection, *, household_id: str, user_id: str, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    current_start = now - timedelta(days=7)
    previous_start = now - timedelta(days=14)
    history_start = now - timedelta(days=56)

    receipts = _approved_receipts(conn, household_id)
    quantities = _receipt_quantities(conn, household_id)

    current = [r for r in receipts if current_start <= r["_purchase_at"] <= now]
    previous = [r for r in receipts if previous_start <= r["_purchase_at"] < current_start]
    history = [r for r in receipts if history_start <= r["_purchase_at"] <= now]

    def article_count(rows: list[dict[str, Any]]) -> float:
        return sum(quantities.get(str(row.get("id") or ""), 0.0) for row in rows)

    def spend(rows: list[dict[str, Any]]) -> float:
        return round(sum(_number(row.get("total_amount")) for row in rows), 2)

    daily_articles: list[dict[str, Any]] = []
    daily_spend: list[dict[str, Any]] = []
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).date()
        rows = [r for r in current if r["_purchase_at"].date() == day]
        daily_articles.append({"date": day.isoformat(), "value": round(article_count(rows), 2)})
        daily_spend.append({"date": day.isoformat(), "value": spend(rows)})

    stores: dict[str, dict[str, Any]] = {}
    for row in current:
        key = row["_store"].strip().lower()
        item = stores.setdefault(key, {"name": row["_store"], "visits": 0, "spend": 0.0})
        item["visits"] += 1
        item["spend"] = round(item["spend"] + _number(row.get("total_amount")), 2)

    historical_spend = spend(history)
    weekly_average = round(historical_spend / 8.0, 2) if history else 0.0
    forecast_weeks = [{"week": index + 1, "value": weekly_average} for index in range(4)]

    kassa_count, unpack_count = _put_away_counts(conn, household_id)
    put_away_total = kassa_count + unpack_count
    put_away_route = "/kassa" if kassa_count > 0 else "/kassabonnen"

    current_articles = article_count(current)
    previous_articles = article_count(previous)
    current_spend = spend(current)
    previous_spend = spend(previous)

    return {
        "status": {
            "notifications": _notification_count(conn, household_id, user_id),
            "shopping": _shopping_count(conn, household_id),
            "put_away": put_away_total,
            "put_away_kassa": kassa_count,
            "put_away_unpack": unpack_count,
            "put_away_route": put_away_route,
        },
        "purchases": {
            "current": round(current_articles, 2),
            "previous": round(previous_articles, 2),
            "delta": round(current_articles - previous_articles, 2),
            "daily": daily_articles,
        },
        "spend": {
            "current": current_spend,
            "previous": previous_spend,
            "delta": round(current_spend - previous_spend, 2),
            "daily": daily_spend,
            "currency": "EUR",
        },
        "stores": {
            "unique": len(stores),
            "visits": sum(item["visits"] for item in stores.values()),
            "items": sorted(stores.values(), key=lambda item: (-item["visits"], item["name"].lower())),
        },
        "forecast": {
            "total": round(weekly_average * 4, 2),
            "weeks": forecast_weeks,
            "currency": "EUR",
            "method": "Gemiddelde uitgaven van de afgelopen 8 weken",
        },
        "generated_at": now.isoformat(),
    }
