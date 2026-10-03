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



def _month_shift(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + offset
    return absolute // 12, absolute % 12 + 1


def _comparison_series(
    receipts: list[dict[str, Any]],
    quantities: dict[str, float],
    *,
    now: datetime,
    granularity: str,
    metric: str,
) -> list[dict[str, Any]]:
    def row_value(row: dict[str, Any]) -> float:
        if metric == "purchases":
            return quantities.get(str(row.get("id") or ""), 0.0)
        return _number(row.get("total_amount"))

    points: list[dict[str, Any]] = []
    if granularity == "days":
        for offset in range(3, -1, -1):
            current_day = (now - timedelta(days=offset)).date()
            previous_day = current_day - timedelta(days=4)
            current_value = sum(row_value(row) for row in receipts if row["_purchase_at"].date() == current_day)
            previous_value = sum(row_value(row) for row in receipts if row["_purchase_at"].date() == previous_day)
            points.append({
                "label": current_day.strftime("%d-%m"),
                "current": round(current_value, 2),
                "previous": round(previous_value, 2),
            })
        return points

    if granularity == "weeks":
        current_monday = (now - timedelta(days=now.weekday())).date()
        for offset in range(3, -1, -1):
            start = current_monday - timedelta(weeks=offset)
            end = start + timedelta(days=7)
            previous_start = start - timedelta(weeks=4)
            previous_end = previous_start + timedelta(days=7)
            current_value = sum(
                row_value(row)
                for row in receipts
                if start <= row["_purchase_at"].date() < end
            )
            previous_value = sum(
                row_value(row)
                for row in receipts
                if previous_start <= row["_purchase_at"].date() < previous_end
            )
            points.append({
                "label": f"W{start.isocalendar().week}",
                "current": round(current_value, 2),
                "previous": round(previous_value, 2),
            })
        return points

    year, month = now.year, now.month
    for offset in range(3, -1, -1):
        current_year, current_month = _month_shift(year, month, -offset)
        previous_year, previous_month = _month_shift(current_year, current_month, -4)
        current_value = sum(
            row_value(row)
            for row in receipts
            if row["_purchase_at"].year == current_year and row["_purchase_at"].month == current_month
        )
        previous_value = sum(
            row_value(row)
            for row in receipts
            if row["_purchase_at"].year == previous_year and row["_purchase_at"].month == previous_month
        )
        label = datetime(current_year, current_month, 1, tzinfo=timezone.utc).strftime("%b")
        points.append({
            "label": label,
            "current": round(current_value, 2),
            "previous": round(previous_value, 2),
        })
    return points



def _spend_year_over_year_series(
    receipts: list[dict[str, Any]],
    *,
    now: datetime,
    granularity: str,
) -> list[dict[str, Any]]:
    def spend_for(start, end) -> float:
        return round(sum(
            _number(row.get("total_amount"))
            for row in receipts
            if start <= row["_purchase_at"] < end
        ), 2)

    points: list[dict[str, Any]] = []
    if granularity == "days":
        for offset in range(3, -1, -1):
            current_day = (now - timedelta(days=offset)).date()
            try:
                previous_day = current_day.replace(year=current_day.year - 1)
            except ValueError:
                previous_day = current_day.replace(year=current_day.year - 1, day=28)
            current_value = sum(
                _number(row.get("total_amount"))
                for row in receipts
                if row["_purchase_at"].date() == current_day
            )
            previous_value = sum(
                _number(row.get("total_amount"))
                for row in receipts
                if row["_purchase_at"].date() == previous_day
            )
            points.append({
                "label": current_day.strftime("%d-%m"),
                "current": round(current_value, 2),
                "previous": round(previous_value, 2),
            })
        return points

    if granularity == "weeks":
        current_monday = (now - timedelta(days=now.weekday())).date()
        for offset in range(3, -1, -1):
            start_date = current_monday - timedelta(weeks=offset)
            end_date = start_date + timedelta(days=7)
            previous_start_date = start_date - timedelta(days=364)
            previous_end_date = previous_start_date + timedelta(days=7)
            current_start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            current_end = datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc)
            previous_start = datetime.combine(previous_start_date, datetime.min.time(), tzinfo=timezone.utc)
            previous_end = datetime.combine(previous_end_date, datetime.min.time(), tzinfo=timezone.utc)
            points.append({
                "label": f"W{start_date.isocalendar().week}",
                "current": spend_for(current_start, current_end),
                "previous": spend_for(previous_start, previous_end),
            })
        return points

    for offset in range(3, -1, -1):
        current_year, current_month = _month_shift(now.year, now.month, -offset)
        current_value = sum(
            _number(row.get("total_amount"))
            for row in receipts
            if row["_purchase_at"].year == current_year
            and row["_purchase_at"].month == current_month
        )
        previous_value = sum(
            _number(row.get("total_amount"))
            for row in receipts
            if row["_purchase_at"].year == current_year - 1
            and row["_purchase_at"].month == current_month
        )
        label = datetime(current_year, current_month, 1, tzinfo=timezone.utc).strftime("%b")
        points.append({
            "label": label,
            "current": round(current_value, 2),
            "previous": round(previous_value, 2),
        })
    return points


def _period_windows(now: datetime, granularity: str) -> tuple[datetime, datetime, datetime]:
    if granularity == "days":
        current_start = now - timedelta(days=4)
        previous_start = now - timedelta(days=8)
        return current_start, previous_start, current_start
    if granularity == "weeks":
        current_start = now - timedelta(weeks=4)
        previous_start = now - timedelta(weeks=8)
        return current_start, previous_start, current_start
    current_start = now - timedelta(days=122)
    previous_start = now - timedelta(days=244)
    return current_start, previous_start, current_start


def _store_period_views(receipts: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for granularity in ("days", "weeks", "months"):
        current_start, previous_start, previous_end = _period_windows(now, granularity)
        current_rows = [row for row in receipts if current_start <= row["_purchase_at"] <= now]
        previous_rows = [row for row in receipts if previous_start <= row["_purchase_at"] < previous_end]

        def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
            unique_stores = {str(row.get("_store") or "").strip().lower() for row in rows if str(row.get("_store") or "").strip()}
            visit_days = {
                (str(row.get("_store") or "").strip().lower(), row["_purchase_at"].date().isoformat())
                for row in rows
                if str(row.get("_store") or "").strip()
            }
            return {"unique": len(unique_stores), "visits": len(visit_days)}

        if granularity == "days":
            points = []
            for offset in range(3, -1, -1):
                current_day = (now - timedelta(days=offset)).date()
                previous_day = current_day - timedelta(days=4)
                current_visits = {
                    str(row.get("_store") or "").strip().lower()
                    for row in receipts
                    if row["_purchase_at"].date() == current_day and str(row.get("_store") or "").strip()
                }
                previous_visits = {
                    str(row.get("_store") or "").strip().lower()
                    for row in receipts
                    if row["_purchase_at"].date() == previous_day and str(row.get("_store") or "").strip()
                }
                points.append({
                    "label": current_day.strftime("%d-%m"),
                    "current": len(current_visits),
                    "previous": len(previous_visits),
                })
        elif granularity == "weeks":
            points = []
            current_monday = (now - timedelta(days=now.weekday())).date()
            for offset in range(3, -1, -1):
                start = current_monday - timedelta(weeks=offset)
                end = start + timedelta(days=7)
                previous_start = start - timedelta(weeks=4)
                previous_end = previous_start + timedelta(days=7)
                current_visits = {
                    (str(row.get("_store") or "").strip().lower(), row["_purchase_at"].date().isoformat())
                    for row in receipts
                    if start <= row["_purchase_at"].date() < end and str(row.get("_store") or "").strip()
                }
                previous_visits = {
                    (str(row.get("_store") or "").strip().lower(), row["_purchase_at"].date().isoformat())
                    for row in receipts
                    if previous_start <= row["_purchase_at"].date() < previous_end and str(row.get("_store") or "").strip()
                }
                points.append({
                    "label": f"W{start.isocalendar().week}",
                    "current": len(current_visits),
                    "previous": len(previous_visits),
                })
        else:
            points = []
            for offset in range(3, -1, -1):
                current_year, current_month = _month_shift(now.year, now.month, -offset)
                previous_year, previous_month = _month_shift(current_year, current_month, -4)
                current_visits = {
                    (str(row.get("_store") or "").strip().lower(), row["_purchase_at"].date().isoformat())
                    for row in receipts
                    if row["_purchase_at"].year == current_year and row["_purchase_at"].month == current_month and str(row.get("_store") or "").strip()
                }
                previous_visits = {
                    (str(row.get("_store") or "").strip().lower(), row["_purchase_at"].date().isoformat())
                    for row in receipts
                    if row["_purchase_at"].year == previous_year and row["_purchase_at"].month == previous_month and str(row.get("_store") or "").strip()
                }
                label = datetime(current_year, current_month, 1, tzinfo=timezone.utc).strftime("%b")
                points.append({
                    "label": label,
                    "current": len(current_visits),
                    "previous": len(previous_visits),
                })

        result[granularity] = {
            "current": summary(current_rows),
            "previous": summary(previous_rows),
            "points": points,
        }
    return result


def _forecast_views(items: list[dict[str, Any]], *, now: datetime) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    days = []
    for offset in range(4):
        day = now.date() + timedelta(days=offset)
        value = sum(
            _number(item.get("expected_amount"))
            for item in items
            if item.get("expected_date") == day.isoformat()
        )
        days.append({"label": day.strftime("%d-%m"), "value": round(value, 2)})
    result["days"] = days

    weeks = []
    for index in range(4):
        start = now.date() + timedelta(days=index * 7)
        end = start + timedelta(days=7)
        value = sum(
            _number(item.get("expected_amount"))
            for item in items
            if start <= datetime.fromisoformat(str(item.get("expected_date"))).date() < end
        )
        weeks.append({"label": f"W{index + 1}", "value": round(value, 2)})
    result["weeks"] = weeks

    months = []
    for offset in range(4):
        year, month = _month_shift(now.year, now.month, offset)
        value = sum(
            _number(item.get("expected_amount"))
            for item in items
            if datetime.fromisoformat(str(item.get("expected_date"))).year == year
            and datetime.fromisoformat(str(item.get("expected_date"))).month == month
        )
        label = datetime(year, month, 1, tzinfo=timezone.utc).strftime("%b")
        months.append({"label": label, "value": round(value, 2)})
    result["months"] = months
    return result


def _repeat_purchase_forecast(
    receipts: list[dict[str, Any]],
    article_details: dict[str, list[dict[str, Any]]],
    *,
    now: datetime,
) -> dict[str, Any]:
    cutoff = now - timedelta(days=180)
    article_events: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for receipt in receipts:
        if receipt["_purchase_at"] < cutoff or receipt["_purchase_at"] > now:
            continue
        receipt_id = str(receipt.get("id") or "")
        purchase_date = receipt["_purchase_at"].date()
        for article in article_details.get(receipt_id, []):
            identity = (
                article.get("household_article_id")
                or article.get("global_product_id")
                or str(article.get("label") or "").strip().lower()
            )
            if not identity:
                continue
            article_events[str(identity)].append({
                "date": purchase_date,
                "label": article.get("label") or "Artikel",
                "amount": _number(article.get("line_total")),
                "quantity": _number(article.get("quantity")) or 1.0,
                "household_article_id": article.get("household_article_id"),
                "global_product_id": article.get("global_product_id"),
            })

    horizon_end = (now + timedelta(days=183)).date()
    forecast_items: list[dict[str, Any]] = []
    weekly_totals = [0.0, 0.0, 0.0, 0.0]

    for identity, events in article_events.items():
        by_date: dict[Any, dict[str, Any]] = {}
        for event in events:
            day = event["date"]
            aggregate = by_date.setdefault(day, {
                **event,
                "amount": 0.0,
                "quantity": 0.0,
            })
            aggregate["amount"] += event["amount"]
            aggregate["quantity"] += event["quantity"]
        ordered = [by_date[day] for day in sorted(by_date)]
        if len(ordered) < 2:
            continue

        intervals = [
            (ordered[index]["date"] - ordered[index - 1]["date"]).days
            for index in range(1, len(ordered))
            if (ordered[index]["date"] - ordered[index - 1]["date"]).days > 0
        ]
        if not intervals:
            continue
        intervals.sort()
        cadence_days = intervals[len(intervals) // 2]
        if cadence_days < 2 or cadence_days > 120:
            continue

        positive_amounts = [event["amount"] for event in ordered if event["amount"] > 0]
        expected_amount = round(sum(positive_amounts) / len(positive_amounts), 2) if positive_amounts else 0.0
        expected_quantity = round(sum(event["quantity"] for event in ordered) / len(ordered), 2)
        next_date = ordered[-1]["date"] + timedelta(days=cadence_days)
        while next_date <= now.date():
            next_date += timedelta(days=cadence_days)

        representative = ordered[-1]
        while next_date <= horizon_end:
            days_ahead = (next_date - now.date()).days
            if days_ahead < 28:
                week_index = min(3, max(0, days_ahead // 7))
                weekly_totals[week_index] += expected_amount
            forecast_items.append({
                "identity": identity,
                "label": representative["label"],
                "expected_date": next_date.isoformat(),
                "cadence_days": cadence_days,
                "expected_amount": expected_amount,
                "expected_quantity": expected_quantity,
                "household_article_id": representative.get("household_article_id"),
                "global_product_id": representative.get("global_product_id"),
            })
            next_date += timedelta(days=cadence_days)

    forecast_items.sort(key=lambda item: (item["expected_date"], str(item["label"]).lower()))
    weeks = [
        {"week": index + 1, "value": round(value, 2)}
        for index, value in enumerate(weekly_totals)
    ]
    views = _forecast_views(forecast_items, now=now)
    return {
        "total": round(sum(weekly_totals), 2),
        "weeks": weeks,
        "views": views,
        "currency": "EUR",
        "method": "Herhalingskoop op basis van het historische koopritme per artikel",
        "items": forecast_items,
    }



def _dashboard_bucket_window(
    *,
    now: datetime,
    granularity: str,
    bucket_index: int,
    series: str,
    comparison: str,
) -> tuple[datetime, datetime, str]:
    if granularity not in {"days", "weeks", "months"}:
        raise ValueError("Ongeldige dashboardperiode")
    if bucket_index < 0 or bucket_index > 3:
        raise ValueError("Ongeldige dashboardstaaf")
    if series not in {"current", "previous"}:
        raise ValueError("Ongeldige dashboardreeks")
    if comparison not in {"previous", "year"}:
        raise ValueError("Ongeldige dashboardvergelijking")

    if granularity == "days":
        current_day = (now - timedelta(days=3 - bucket_index)).date()
        target_day = current_day
        if series == "previous":
            if comparison == "year":
                try:
                    target_day = current_day.replace(year=current_day.year - 1)
                except ValueError:
                    target_day = current_day.replace(year=current_day.year - 1, day=28)
            else:
                target_day = current_day - timedelta(days=4)
        start = datetime.combine(target_day, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        return start, end, target_day.strftime("%d-%m-%Y")

    if granularity == "weeks":
        current_monday = (now - timedelta(days=now.weekday())).date()
        current_start_date = current_monday - timedelta(weeks=3 - bucket_index)
        target_start_date = current_start_date
        if series == "previous":
            target_start_date = (
                current_start_date - timedelta(days=364)
                if comparison == "year"
                else current_start_date - timedelta(weeks=4)
            )
        start = datetime.combine(target_start_date, datetime.min.time(), tzinfo=timezone.utc)
        end = start + timedelta(days=7)
        return start, end, f"W{target_start_date.isocalendar().week} {target_start_date.isocalendar().year}"

    current_year, current_month = _month_shift(now.year, now.month, -(3 - bucket_index))
    target_year, target_month = current_year, current_month
    if series == "previous":
        if comparison == "year":
            target_year -= 1
        else:
            target_year, target_month = _month_shift(current_year, current_month, -4)
    start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
    next_year, next_month = _month_shift(target_year, target_month, 1)
    end = datetime(next_year, next_month, 1, tzinfo=timezone.utc)
    return start, end, start.strftime("%m-%Y")


def build_household_dashboard_drilldown(
    conn: Connection,
    *,
    household_id: str,
    user_id: str,
    metric: str,
    granularity: str,
    bucket_index: int,
    series: str = "current",
    comparison: str = "previous",
    now: datetime | None = None,
) -> dict[str, Any]:
    del user_id
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start, end, label = _dashboard_bucket_window(
        now=now,
        granularity=granularity,
        bucket_index=bucket_index,
        series=series,
        comparison=comparison,
    )

    receipts = _approved_receipts(conn, household_id)
    article_details = _receipt_article_details(conn, household_id)
    selected_rows = [row for row in receipts if start <= row["_purchase_at"] < end]
    selected_receipts = [
        _receipt_detail(row, article_details)
        for row in sorted(selected_rows, key=lambda item: item["_purchase_at"], reverse=True)
    ]

    stores: dict[str, dict[str, Any]] = {}
    for receipt in selected_receipts:
        key = str(receipt.get("store") or "Onbekende winkel").strip().lower()
        store = stores.setdefault(key, {
            "name": receipt.get("store") or "Onbekende winkel",
            "visits": 0,
            "spend": 0.0,
            "receipts": [],
        })
        store["visits"] += 1
        store["spend"] = round(store["spend"] + _number(receipt.get("total")), 2)
        store["receipts"].append(receipt)

    response: dict[str, Any] = {
        "metric": metric,
        "granularity": granularity,
        "bucket_index": bucket_index,
        "series": series,
        "comparison": comparison,
        "label": label,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "receipts": selected_receipts,
        "stores": sorted(stores.values(), key=lambda item: (-item["spend"], item["name"].lower())),
        "spend": round(sum(_number(row.get("total_amount")) for row in selected_rows), 2),
        "article_count": round(sum(
            _number(article.get("quantity"))
            for receipt in selected_receipts
            for article in receipt.get("articles", [])
        ), 2),
    }

    if metric == "forecast":
        repeat_forecast = _repeat_purchase_forecast(receipts, article_details, now=now)
        items = [
            item for item in repeat_forecast.get("items", [])
            if start.date() <= datetime.fromisoformat(str(item.get("expected_date"))).date() < end.date()
        ]
        response["forecast_items"] = items
        response["forecast_total"] = round(sum(_number(item.get("expected_amount")) for item in items), 2)

    return response


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

    purchase_views = {
        "days": _comparison_series(receipts, quantities, now=now, granularity="days", metric="purchases"),
        "weeks": _comparison_series(receipts, quantities, now=now, granularity="weeks", metric="purchases"),
        "months": _comparison_series(receipts, quantities, now=now, granularity="months", metric="purchases"),
    }
    spend_views = {
        "days": _comparison_series(receipts, quantities, now=now, granularity="days", metric="spend"),
        "weeks": _comparison_series(receipts, quantities, now=now, granularity="weeks", metric="spend"),
        "months": _comparison_series(receipts, quantities, now=now, granularity="months", metric="spend"),
    }
    spend_year_over_year_views = {
        "days": _spend_year_over_year_series(receipts, now=now, granularity="days"),
        "weeks": _spend_year_over_year_series(receipts, now=now, granularity="weeks"),
        "months": _spend_year_over_year_series(receipts, now=now, granularity="months"),
    }
    repeat_forecast = _repeat_purchase_forecast(receipts, article_details, now=now)
    store_views = _store_period_views(receipts, now=now)

    kassa_count, unpack_count = _put_away_counts(conn, household_id)
    put_away_total = kassa_count + unpack_count
    put_away_route = "/kassa?view=bonnen"

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
            "views": purchase_views,
            "receipts": current_receipts,
        },
        "spend": {
            "current": current_spend,
            "previous": previous_spend,
            "delta": round(current_spend - previous_spend, 2),
            "daily": daily_spend,
            "views": spend_views,
            "currency": "EUR",
            "receipts": current_receipts,
        },
        "spend_year_over_year": {
            "views": spend_year_over_year_views,
            "currency": "EUR",
        },
        "stores": {
            "unique": len(stores),
            "visits": sum(item["visits"] for item in stores.values()),
            "views": store_views,
            "items": sorted(stores.values(), key=lambda item: (-item["visits"], item["name"].lower())),
        },
        "forecast": {
            **repeat_forecast,
            "basis_receipts": history_receipts,
        },
        "generated_at": now.isoformat(),
    }
