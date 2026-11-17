"""Household-scoped, page-sized Kassa inbox. The legacy /api/receipts API remains intact.

The canonical receipt-status service is the sole source of status labels. One
household-scoped line aggregation replaces the old per-receipt subqueries; only
the visible ten summaries are returned to the frontend.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from functools import cmp_to_key
from time import perf_counter
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, Query
from sqlalchemy import text

from app.db import engine
from app.services.receipt_service import serialize_receipt_row
from app.services.receipt_ssot_status import apply_po_norm_status

router = APIRouter()

# A single DML-free read, scoped before aggregating any receipt lines.
# No product / household identity is inferred from retailer text.
_KASSA_SUMMARIES_SQL = """
WITH active_lines AS (
    SELECT rtl.receipt_table_id,
           COUNT(*) AS line_count,
           COALESCE(SUM(COALESCE(rtl.corrected_line_total, rtl.line_total, 0)), 0) AS line_total_sum,
           COALESCE(SUM(COALESCE(rtl.discount_amount, 0)), 0) AS line_discount_sum,
           COALESCE(SUM(COALESCE(rtl.corrected_line_total, rtl.line_total, 0)
                        + COALESCE(rtl.discount_amount, 0)), 0) AS net_line_total_sum
    FROM receipt_table_lines rtl
    JOIN receipt_tables target ON target.id = rtl.receipt_table_id
    WHERE target.household_id = :household_id
      AND target.approved_at IS NULL
      AND target.deleted_at IS NULL
      AND COALESCE(rtl.is_deleted, FALSE) = FALSE
    GROUP BY rtl.receipt_table_id
)
SELECT rt.id AS receipt_table_id,
       rt.raw_receipt_id, rt.store_name, rt.store_branch,
       rt.purchase_at, rt.store_name_source, rt.purchase_at_source,
       rt.total_amount, rt.discount_total, rt.reference, rt.notes,
       rt.approved_at, rt.approved_by_user_email, rt.currency,
       rt.parse_status, COALESCE(lines.line_count, 0) AS line_count,
       COALESCE(rs.label, 'Manual upload') AS source_label,
       rem.sender_email, rem.sender_name, rem.subject AS email_subject,
       rem.received_at AS email_received_at,
       rr.sha256_hash, rt.created_at,
       COALESCE(lines.line_total_sum, 0) AS line_total_sum,
       COALESCE(lines.line_discount_sum, 0) AS line_discount_sum,
       COALESCE(rt.discount_total, 0) AS discount_total_effective,
       COALESCE(lines.net_line_total_sum, 0) + COALESCE(rt.discount_total, 0)
         AS net_line_total_sum
FROM receipt_tables rt
JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
LEFT JOIN receipt_sources rs ON rs.id = rr.source_id
LEFT JOIN receipt_email_messages rem ON rem.raw_receipt_id = rr.id
LEFT JOIN active_lines lines ON lines.receipt_table_id = rt.id
WHERE rt.household_id = :household_id
  AND rt.approved_at IS NULL
  AND rt.deleted_at IS NULL
  AND rr.deleted_at IS NULL
ORDER BY COALESCE(rt.purchase_at, rt.created_at) DESC, rt.created_at DESC, rt.id DESC
"""


def _normalized_key_part(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _deduped_receipts(rows):
    """Preserve the legacy SHA-or-fingerprint precedence and status SSOT."""
    items = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        store = _normalized_key_part(row.get("store_name"))
        purchase_at = _normalized_key_part(row.get("purchase_at"))
        amount = row.get("total_amount")
        try:
            amount_key = f"{float(amount):.2f}" if amount is not None else ""
        except (TypeError, ValueError):
            amount_key = _normalized_key_part(amount)
        fingerprint = (store, purchase_at, amount_key,
                       str(row.get("line_count") or 0),
                       _normalized_key_part(row.get("source_label")))
        key = _normalized_key_part(row.get("sha256_hash")) or "|".join(fingerprint)
        if key in seen:
            continue
        seen.add(key)
        item = apply_po_norm_status(serialize_receipt_row(row))
        item.pop("sha256_hash", None)
        items.append(item)
    return items


def _datetime_for_filter(value):
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone(ZoneInfo("Europe/Amsterdam"))
        return parsed.strftime("%d-%m-%Y %H:%M")
    except ValueError:
        return str(value)


def _money_for_filter(value, currency):
    if value is None or value == "":
        return "-"
    try:
        amount = f"{float(value):,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
    except (ValueError, TypeError):
        return str(value)
    symbol = "€" if (currency or "EUR") == "EUR" else (currency or "EUR")
    return symbol + "\u00a0" + amount


def _compare_text(left, right):
    def key(value):
        stripped = unicodedata.normalize("NFKD", str(value).strip().casefold())
        stripped = "".join(char for char in stripped if not unicodedata.combining(char))
        return [int(bit) if bit.isdigit() else bit for bit in re.split(r"(\d+)", stripped)]
    a, b = key(left), key(right)
    for aa, bb in zip(a, b):
        if aa == bb:
            continue
        if type(aa) is type(bb):
            return -1 if aa < bb else 1
        return -1 if isinstance(aa, int) else 1
    return (len(a) > len(b)) - (len(a) < len(b))


def _sort_receipts(items, sort_key, direction):
    # The original browser pre-sorted by created_at before its stable column sort.
    items = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def value(item):
        if sort_key == "store":
            return item.get("store_name") or ""
        if sort_key == "total":
            return float(item.get("total_amount") or 0)
        if sort_key == "items":
            return int(item.get("line_count") or 0)
        return item.get("purchase_at") or ""

    def compare(left, right):
        a, b = value(left), value(right)
        if a in ("", None) and b in ("", None):
            return 0
        if a in ("", None):
            return 1
        if b in ("", None):
            return -1
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            result = (a > b) - (a < b)
        else:
            result = _compare_text(a, b)
        return -result if direction == "desc" else result

    return sorted(items, key=cmp_to_key(compare))


def _filter_receipts(items, winkel, datum, totaal, artikelen, status):
    terms = [str(term or "").strip().lower() for term in (winkel, datum, totaal, artikelen)]
    return [
        row for row in items
        if terms[0] in str(row.get("store_name") or "").lower()
        and terms[1] in _datetime_for_filter(row.get("purchase_at")).lower()
        and terms[2] in _money_for_filter(row.get("total_amount"), row.get("currency")).lower()
        and terms[3] in str(row.get("line_count") or 0)
        and (not status or row.get("inbox_status") == status)
    ]


def _page_payload(rows, *, page, page_size, winkel="", datum="", totaal="",
                  artikelen="", status="", sort_key="date", sort_direction="desc"):
    items = _deduped_receipts(rows)
    counts = {
        "Controle nodig": sum(item["inbox_status"] == "Controle nodig" for item in items),
        "Gecontroleerd": sum(item["inbox_status"] == "Gecontroleerd" for item in items),
    }
    filtered = _filter_receipts(items, winkel, datum, totaal, artikelen, status)
    sorted_items = _sort_receipts(filtered, sort_key, sort_direction)
    start = (page - 1) * page_size
    return {
        "items": sorted_items[start:start + page_size],
        "total": len(sorted_items),
        "counts": counts,
        "page": page,
        "page_size": page_size,
    }


@router.get("/api/kassa/receipts-page")
def list_kassa_receipts_page(
    householdId: str = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=10),
    winkel: str = Query(default="", max_length=200),
    datum: str = Query(default="", max_length=200),
    totaal: str = Query(default="", max_length=100),
    artikelen: str = Query(default="", max_length=100),
    status: str = Query(default="", pattern="^(|Controle nodig|Gecontroleerd)$"),
    sort_key: str = Query(default="date", pattern="^(store|date|total|items)$"),
    sort_direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    initialize: bool = Query(default=False),
    authorization: str | None = Header(default=None),
):
    # Use the exact legacy authorization + initialization authority, but never
    # run an auto-approval/write merely because someone changed table pages.
    from app import main as legacy
    started = perf_counter()
    household_id = legacy.resolve_authorized_household_id(
        authorization, householdId, require_authorization=True,
    )
    if initialize:
        legacy.ensure_default_receipt_sources(
            engine, legacy.RECEIPT_STORAGE_ROOT, household_id,
        )
        legacy._auto_approve_pending_receipts_for_household(household_id)
    initialized = perf_counter()
    with engine.connect() as conn:
        rows = conn.execute(text(_KASSA_SUMMARIES_SQL), {"household_id": household_id}).mappings().all()
    queried = perf_counter()
    result = _page_payload(
        rows, page=page, page_size=page_size, winkel=winkel, datum=datum,
        totaal=totaal, artikelen=artikelen, status=status,
        sort_key=sort_key, sort_direction=sort_direction,
    )
    elapsed = perf_counter() - started
    if elapsed >= 0.5:
        logging.getLogger("uvicorn.error").info(
            "kassa_page_timing total_ms=%.1f initialization_ms=%.1f query_ms=%.1f "
            "project_ms=%.1f source_rows=%d page_rows=%d",
            elapsed * 1000, (initialized - started) * 1000,
            (queried - initialized) * 1000, (perf_counter() - queried) * 1000,
            len(rows), len(result["items"]),
        )
    return result
