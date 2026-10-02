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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "t", "yes", "on"}


def _tables(conn: Connection) -> set[str]:
    return set(inspect(conn).get_table_names())


def _columns(conn: Connection, table_name: str) -> set[str]:
    if table_name not in _tables(conn):
        return set()
    return {str(column.get("name") or "") for column in inspect(conn).get_columns(table_name)}


def _all_rows(conn: Connection, table_name: str) -> list[dict[str, Any]]:
    if table_name not in _tables(conn):
        return []
    return [dict(row) for row in conn.execute(text(f'SELECT * FROM "{table_name}"')).mappings().all()]


def _household_rows(conn: Connection, table_name: str, household_id: str) -> list[dict[str, Any]]:
    columns = _columns(conn, table_name)
    if "household_id" not in columns:
        return []
    rows = conn.execute(
        text(f'SELECT * FROM "{table_name}" WHERE CAST(household_id AS TEXT) = :household_id'),
        {"household_id": str(household_id)},
    ).mappings().all()
    return [dict(row) for row in rows]


def _active_receipt_rows(conn: Connection, household_id: str, *, approved_only: bool) -> list[dict[str, Any]]:
    rows = _household_rows(conn, "receipt_tables", household_id)
    columns = _columns(conn, "receipt_tables")
    result: list[dict[str, Any]] = []
    for row in rows:
        if "deleted_at" in columns and row.get("deleted_at") is not None:
            continue
        workflow_state = str(row.get("workflow_state") or "active").strip().lower()
        if workflow_state in {"archived", "deleted", "removed", "legacy_deleted", "removed_reimport_allowed"}:
            continue
        if approved_only and ("approved_at" in columns or "parse_status" in columns):
            parse_status = str(row.get("parse_status") or "").strip().lower()
            if not row.get("approved_at") and parse_status not in {"approved", "approved_override"}:
                continue
        purchase_at = _to_datetime(row.get("purchase_at")) or _to_datetime(row.get("created_at"))
        if not purchase_at:
            continue
        result.append({
            **row,
            "_purchase_at": purchase_at,
            "_store": str(row.get("store_name") or row.get("store_branch") or "Onbekende winkel").strip() or "Onbekende winkel",
        })
    return result


def _eligible_receipt_lines(conn: Connection, household_id: str) -> list[dict[str, Any]]:
    receipt_rows = _active_receipt_rows(conn, household_id, approved_only=False)
    receipt_ids = {str(row.get("id") or "") for row in receipt_rows}
    if not receipt_ids or "receipt_table_lines" not in _tables(conn):
        return []

    columns = _columns(conn, "receipt_table_lines")
    if "receipt_table_id" not in columns:
        return []

    result: list[dict[str, Any]] = []
    for row in _all_rows(conn, "receipt_table_lines"):
        if str(row.get("receipt_table_id") or "") not in receipt_ids:
            continue
        if "is_deleted" in columns and _truthy(row.get("is_deleted")):
            continue
        if "inventory_eligible" in columns:
            if not _truthy(row.get("inventory_eligible")):
                continue
        elif "line_role" in columns:
            if str(row.get("line_role") or "product").strip().lower() != "product":
                continue
        result.append(row)
    return result


def _approved_receipts(conn: Connection, household_id: str) -> list[dict[str, Any]]:
    return _active_receipt_rows(conn, household_id, approved_only=True)


def _receipt_quantities(conn: Connection, household_id: str) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in _eligible_receipt_lines(conn, household_id):
        quantity = _number(row.get("quantity"))
        totals[str(row.get("receipt_table_id") or "")] += quantity if quantity > 0 else 1.0
    return dict(totals)


def _receipt_article_details(conn: Connection, household_id: str) -> dict[str, list[dict[str, Any]]]:
    columns = _columns(conn, "receipt_table_lines")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _eligible_receipt_lines(conn, household_id):
        label = "Artikel"
        for column in ("corrected_raw_label", "normalized_label", "raw_label", "article_name"):
            if column in columns and str(row.get(column) or "").strip():
                label = str(row.get(column)).strip()
                break
        grouped[str(row.get("receipt_table_id") or "")].append({
            "line_id": row.get("id"),
            "label": label,
            "quantity": _number(row.get("quantity")) or 1.0,
            "unit": row.get("unit"),
            "line_total": round(_number(row.get("line_total")), 2) if row.get("line_total") is not None else None,
            "household_article_id": row.get("matched_article_id") or row.get("household_article_id"),
            "global_product_id": row.get("matched_global_product_id") or row.get("global_product_id"),
        })
    for items in grouped.values():
        items.sort(key=lambda item: str(item.get("label") or "").lower())
    return dict(grouped)


def _receipt_detail(row: dict[str, Any], article_details: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    receipt_id = str(row.get("id") or "")
    articles = article_details.get(receipt_id, [])
    return {
        "receipt_id": receipt_id,
        "store": row.get("_store") or "Onbekende winkel",
        "date": row["_purchase_at"].date().isoformat(),
        "purchase_at": row["_purchase_at"].isoformat(),
        "total": round(_number(row.get("total_amount")), 2),
        "currency": row.get("currency") or "EUR",
        "article_count": round(sum(_number(item.get("quantity")) for item in articles), 2),
        "articles": articles,
    }


def _shopping_count(conn: Connection, household_id: str) -> int:
    lists = _household_rows(conn, "shopping_lists", household_id)
    active_ids = {
        str(row.get("id") or "")
        for row in lists
        if str(row.get("status") or "active").strip().lower() == "active"
    }
    if not active_ids or "shopping_list_items" not in _tables(conn):
        return 0

    item_columns = _columns(conn, "shopping_list_items")
    count = 0
    for row in _all_rows(conn, "shopping_list_items"):
        if str(row.get("shopping_list_id") or "") not in active_ids:
            continue
        if "household_id" in item_columns and str(row.get("household_id") or "") != str(household_id):
            continue
        if not _truthy(row.get("checked")):
            count += 1
    return count


def _notification_count(conn: Connection, household_id: str, user_id: str) -> int:
    rows = _household_rows(conn, "household_notifications", household_id)
    columns = _columns(conn, "household_notifications")
    if not rows:
        return 0
    count = 0
    for row in rows:
        if "recipient_user_id" in columns:
            recipient = str(row.get("recipient_user_id") or "").strip()
            if recipient and recipient != str(user_id):
                continue
        if "read_at" in columns and row.get("read_at") is not None:
            continue
        count += 1
    return count


def _put_away_counts(conn: Connection, household_id: str) -> tuple[int, int]:
    receipt_rows = _active_receipt_rows(conn, household_id, approved_only=False)
    receipt_ids = {str(row.get("id") or "") for row in receipt_rows}
    if not receipt_ids:
        return 0, 0

    eligible_lines = [
        row
        for row in _eligible_receipt_lines(conn, household_id)
        if str(row.get("receipt_table_id") or "") in receipt_ids
    ]

    batches = _household_rows(conn, "purchase_import_batches", household_id)
    batch_columns = _columns(conn, "purchase_import_batches")
    receipt_batch_by_receipt: dict[str, str] = {}
    if {"id", "source_type", "source_reference"}.issubset(batch_columns):
        for batch in batches:
            if str(batch.get("source_type") or "").strip().lower() != "receipt":
                continue
            reference = str(batch.get("source_reference") or "").strip()
            if reference.startswith("receipt:"):
                receipt_id = reference.split(":", 1)[1]
                if receipt_id in receipt_ids:
                    receipt_batch_by_receipt[receipt_id] = str(batch.get("id") or "")

    kassa = sum(
        1
        for row in eligible_lines
        if str(row.get("receipt_table_id") or "") not in receipt_batch_by_receipt
    )

    if not receipt_batch_by_receipt or "purchase_import_lines" not in _tables(conn):
        return int(kassa), 0

    import_columns = _columns(conn, "purchase_import_lines")
    if "batch_id" not in import_columns or "processing_status" not in import_columns:
        return int(kassa), 0

    receipt_batch_ids = set(receipt_batch_by_receipt.values())
    unpack = 0
    for row in _all_rows(conn, "purchase_import_lines"):
        if str(row.get("batch_id") or "") not in receipt_batch_ids:
            continue
        if str(row.get("processing_status") or "pending").strip().lower() == "processed":
            continue
        if "review_decision" in import_columns and str(row.get("review_decision") or "pending").strip().lower() == "removed":
            continue
        unpack += 1
    return int(kassa), int(unpack)


def build_household_dashboard(
    conn: Connection,
    *,
    household_id: str,
    user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    current_start = now - timedelta(days=7)
    previous_start = now - timedelta(days=14)
    history_start = now - timedelta(days=56)

    receipts = _approved_receipts(conn, household_id)
    quantities = _receipt_quantities(conn, household_id)
    article_details = _receipt_article_details(conn, household_id)

    current = [row for row in receipts if current_start <= row["_purchase_at"] <= now]
    previous = [row for row in receipts if previous_start <= row["_purchase_at"] < current_start]
    history = [row for row in receipts if history_start <= row["_purchase_at"] <= now]

    def article_count(rows: list[dict[str, Any]]) -> float:
        return sum(quantities.get(str(row.get("id") or ""), 0.0) for row in rows)

    def spend(rows: list[dict[str, Any]]) -> float:
        return round(sum(_number(row.get("total_amount")) for row in rows), 2)

    daily_articles: list[dict[str, Any]] = []
    daily_spend: list[dict[str, Any]] = []
    for offset in range(6, -1, -1):
        day = (now - timedelta(days=offset)).date()
        rows = [row for row in current if row["_purchase_at"].date() == day]
        daily_articles.append({"date": day.isoformat(), "value": round(article_count(rows), 2)})
        daily_spend.append({"date": day.isoformat(), "value": spend(rows)})

    stores: dict[str, dict[str, Any]] = {}
    store_visit_days: set[tuple[str, str]] = set()
    for row in current:
        key = row["_store"].strip().lower()
        item = stores.setdefault(key, {"name": row["_store"], "visits": 0, "spend": 0.0})
        visit_key = (key, row["_purchase_at"].date().isoformat())
        if visit_key not in store_visit_days:
            item["visits"] += 1
            store_visit_days.add(visit_key)
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

    current_receipts = [
        _receipt_detail(row, article_details)
        for row in sorted(current, key=lambda item: item["_purchase_at"], reverse=True)
    ]
    history_receipts = [
        _receipt_detail(row, article_details)
        for row in sorted(history, key=lambda item: item["_purchase_at"], reverse=True)
    ]

    store_receipts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for receipt in current_receipts:
        store_receipts[str(receipt.get("store") or "").strip().lower()].append(receipt)
    for key, item in stores.items():
        item["receipts"] = store_receipts.get(key, [])

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
            "receipts": current_receipts,
        },
        "spend": {
            "current": current_spend,
            "previous": previous_spend,
            "delta": round(current_spend - previous_spend, 2),
            "daily": daily_spend,
            "currency": "EUR",
            "receipts": current_receipts,
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
            "basis_receipts": history_receipts,
        },
        "generated_at": now.isoformat(),
    }
