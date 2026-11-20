"""Read-only historical buying cadence and *unconfirmed* opening-stock estimates.

PR2 builds on the receipt cutover in PR1. Nothing here updates inventory,
inventory_events, receipt data or household article identity. Receipt text
and retailer codes are never used as product identity.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import math

from sqlalchemy import text

from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.services.receipt_historical_import_policy import read_household_cutover

MAX_SOURCE_ROWS = 20000
OBSERVATION_DAYS = 365
MIN_PURCHASE_DAYS = 3
MIN_OBSERVED_SPAN_DAYS = 28
MAX_LAST_PURCHASE_AGE_DAYS = 90

# Only explicit, dimensionally equivalent quantity units are comparable.
_UNITS = {
    "stuk": ("stuk", 1.0), "stuks": ("stuk", 1.0), "st": ("stuk", 1.0),
    "kg": ("kg", 1.0), "g": ("kg", 0.001),
    "l": ("l", 1.0), "liter": ("l", 1.0),
    "ml": ("l", 0.001), "cl": ("l", 0.01), "dl": ("l", 0.1),
}

_HISTORICAL_PRODUCT_LINES_SQL = """
SELECT rt.id AS receipt_table_id, rt.purchase_at, rt.purchase_at_source,
       rt.store_name, rr.sha256_hash,
       rtl.id AS line_id, rtl.line_type, rtl.line_role, rtl.inventory_eligible,
       rtl.article_match_status, rtl.matched_article_id,
       rtl.matched_global_product_id,
       COALESCE(rtl.corrected_quantity, rtl.quantity) AS quantity,
       COALESCE(NULLIF(rtl.corrected_unit, ''), rtl.unit) AS unit,
       gp.id AS product_id, gp.name AS product_name, gp.status AS product_status,
       gp.variant AS variant, gp.size_value, gp.size_unit,
       ha.id AS explicit_household_article_id,
       ha.global_product_id AS article_product_id,
       ha.naam AS household_article_name, ha.status AS article_status
FROM receipt_tables rt
JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id
JOIN household_receipt_history_cutovers hrc ON hrc.household_id = rt.household_id
JOIN receipt_table_lines rtl ON rtl.receipt_table_id = rt.id
LEFT JOIN global_products gp ON gp.id = rtl.matched_global_product_id
LEFT JOIN household_articles ha
  ON ha.id = rtl.matched_article_id AND ha.household_id = rt.household_id
WHERE rt.household_id = :household_id
  AND rt.deleted_at IS NULL AND rr.deleted_at IS NULL
  AND COALESCE(rtl.is_deleted, FALSE) = FALSE
  AND rt.approved_at IS NOT NULL
  AND rt.purchase_at IS NOT NULL
  AND lower(trim(COALESCE(rt.purchase_at_source, ''))) <> 'import_default'
  AND CAST(rt.purchase_at AS DATE) < hrc.first_current_purchase_date
  AND CAST(rt.purchase_at AS DATE) >= :earliest_date
ORDER BY rt.purchase_at DESC, rt.id DESC, rtl.id ASC
LIMIT :row_limit
"""


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _quantity(value, unit):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or not 0 < number <= 10000:
        return None
    factor = _UNITS.get(str(unit or "").strip().lower())
    if factor is None:
        return None
    return (number * factor[1], factor[0])


def _empty(*, status, cutoff=None, source_rows=0, excluded_rows=0):
    return {
        "status": status,
        "first_current_purchase_date": cutoff.isoformat() if cutoff else None,
        "historical_window_days": OBSERVATION_DAYS,
        "source_rows": source_rows,
        "excluded_rows": excluded_rows,
        "requires_confirmation": True,
        "writes_inventory": False,
        "total": 0,
        "items": [],
    }


def project_historical_learning(rows, *, cutoff, synonym_factors=None):
    """Pure bounded projection. Every candidate stays explicitly unconfirmed.

    Source rows have already been household-filtered. The only matching keys
    are a persisted central product ID or an explicit *owned* household ID.
    Confirmed synonym factors come only from the existing conservative
    central synonym authority; caller-supplied names never form a group.
    """
    cutoff = _date(cutoff)
    if cutoff is None:
        return _empty(status="legacy_not_enabled")
    if len(rows) > MAX_SOURCE_ROWS:
        return _empty(status="source_limit_reached", cutoff=cutoff,
                      source_rows=len(rows))
    factors = synonym_factors or {}
    grouped = defaultdict(lambda: {"days": defaultdict(float),
                                   "receipts": set(), "products": set(),
                                   "article_ids": set(), "label": ""})
    excluded = 0
    source_hash_owner = {}
    unit_sets = defaultdict(set)
    for raw in rows:
        line = dict(raw)
        receipt_id = str(line.get("receipt_table_id") or "")
        sha = str(line.get("sha256_hash") or "").strip().lower()
        # The same SHA across separate receipt records cannot count twice.
        if sha:
            previous_owner = source_hash_owner.setdefault(sha, receipt_id)
            if previous_owner != receipt_id:
                excluded += 1
                continue
        observed = _date(line.get("purchase_at"))
        if not observed or observed >= cutoff or observed < cutoff - timedelta(days=OBSERVATION_DAYS):
            excluded += 1
            continue
        if str(line.get("purchase_at_source") or "").strip().lower() == "import_default":
            excluded += 1
            continue
        semantics = derive_receipt_line_semantics(line)
        if semantics.get("line_role") != "product" or not semantics.get("inventory_eligible"):
            excluded += 1
            continue
        qty = _quantity(line.get("quantity"), line.get("unit"))
        if qty is None:
            excluded += 1
            continue
        household_article_id = str(line.get("explicit_household_article_id") or "").strip()
        requested_article_id = str(line.get("matched_article_id") or "").strip()
        product_id = str(line.get("product_id") or "").strip()
        if requested_article_id and household_article_id != requested_article_id:
            # A deleted, missing or other-household article is never inherited.
            excluded += 1
            continue
        if household_article_id and str(line.get("article_status") or "active").lower() != "active":
            excluded += 1
            continue
        article_product_id = str(line.get("article_product_id") or "").strip()
        if product_id and household_article_id and article_product_id and product_id != article_product_id:
            excluded += 1
            continue
        if product_id:
            if str(line.get("product_status") or "active").lower() != "active":
                excluded += 1
                continue
            if str(line.get("article_match_status") or "").lower() not in {"matched", "product_matched"}:
                excluded += 1
                continue
            identity = "product:" + product_id
            label = str(line.get("product_name") or "Catalogusartikel")
        elif household_article_id:
            identity = "article:" + household_article_id
            label = str(line.get("household_article_name") or "Huishoudartikel")
        else:
            excluded += 1
            continue

        amount, unit = qty
        factor = factors.get(product_id) if product_id and unit == "stuk" else None
        if factor:
            synonym_key, content_factor = factor
            # Equivalent packages may be compared only through validated
            # central size metadata. No inferred piece/weight conversion.
            if not math.isfinite(float(content_factor)) or float(content_factor) <= 0:
                excluded += 1
                continue
            identity = "confirmed_synonym:" + str(synonym_key[1])
            unit = str(synonym_key[-1])
            amount *= float(content_factor)
            label = "Bevestigde artikelsynoniemen"
        unit_sets[identity].add(unit)
        key = (identity, unit)
        bucket = grouped[key]
        bucket["days"][observed] += amount
        bucket["receipts"].add(receipt_id)
        if product_id:
            bucket["products"].add(product_id)
        if household_article_id:
            bucket["article_ids"].add(household_article_id)
        bucket["label"] = label

    items = []
    for (identity, unit), bucket in grouped.items():
        days = sorted(bucket["days"])
        first, last = days[0], days[-1]
        span = (last - first).days
        age = (cutoff - last).days
        gaps = [(b - a).days for a, b in zip(days, days[1:])]
        interval = (span / (len(days) - 1)) if len(days) >= 2 else None
        reason = None
        if len(unit_sets[identity]) != 1:
            reason = "incompatible_units"
        elif len(days) < MIN_PURCHASE_DAYS:
            reason = "too_few_purchase_days"
        elif span < MIN_OBSERVED_SPAN_DAYS:
            reason = "short_observation_period"
        elif gaps and max(gaps) > MAX_LAST_PURCHASE_AGE_DAYS:
            reason = "irregular_observation_gap"
        elif age > MAX_LAST_PURCHASE_AGE_DAYS:
            reason = "stale_last_purchase"
        # Replenishment-rate heuristic, never a physical-stock fact.
        # Purchases *before* the latest one approximate consumption across
        # the first-to-last interval; the last acquisition is the starting
        # point for a reviewable remaining-stock suggestion.
        rate = (sum(bucket["days"][d] for d in days[:-1]) / span) if not reason and span else None
        estimate = max(0.0, bucket["days"][last] - rate * age) if rate is not None else None
        article_ids = sorted(bucket["article_ids"])
        items.append({
            "key": identity,
            "display_name": bucket["label"],
            "unit": unit,
            "product_ids": sorted(bucket["products"]),
            "household_article_id": article_ids[0] if len(article_ids) == 1 else None,
            "source_receipt_count": len(bucket["receipts"]),
            "purchase_day_count": len(days),
            "first_purchase_date": first.isoformat(),
            "last_purchase_date": last.isoformat(),
            "average_purchase_interval_days": round(interval, 2) if interval else None,
            "average_daily_purchase_quantity": round(rate, 4) if rate is not None else None,
            "estimated_opening_quantity": round(estimate, 3) if estimate is not None else None,
            "estimate_status": "indicative_unconfirmed" if reason is None else "insufficient_data",
            "reason": reason,
            "requires_confirmation": True,
        })
    items.sort(key=lambda it: (it["display_name"].casefold(), it["key"], it["unit"]))
    return {
        **_empty(status="analysis_only", cutoff=cutoff,
                 source_rows=len(rows), excluded_rows=excluded),
        "total": len(items),
        "items": items,
    }


def load_historical_learning(conn, *, household_id: str, page: int = 1,
                             page_size: int = 20):
    """Authorized caller supplies the *server-resolved* household ID.

    This function is strictly SELECT-only. The endpoint runs it in a read
    connection and NEVER invokes Kassa initialization or auto-approval.
    """
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        raise ValueError("Een geldig actief huishouden is vereist")
    cutoff = read_household_cutover(conn, owner)
    if cutoff is None:
        return {**_empty(status="legacy_not_enabled"), "page": page, "page_size": page_size}
    observed = conn.execute(text(_HISTORICAL_PRODUCT_LINES_SQL), {
        "household_id": owner,
        "earliest_date": cutoff - timedelta(days=OBSERVATION_DAYS),
        "row_limit": MAX_SOURCE_ROWS + 1,
    }).mappings().all()
    if len(observed) > MAX_SOURCE_ROWS:
        return {**_empty(status="source_limit_reached", cutoff=cutoff,
                         source_rows=len(observed)), "page": page,
                "page_size": page_size}
    from app.services.almost_out_group_service import confirmed_synonym_factors
    metadata = {}
    for row in observed:
        pid = str(row.get("product_id") or "")
        if pid and pid not in metadata:
            metadata[pid] = {
                "global_product_id": pid,
                "product_name": row.get("product_name"),
                "product_status": row.get("product_status"),
                "variant": row.get("variant"),
                "size_value": row.get("size_value"),
                "size_unit": row.get("size_unit"),
            }
    factors = confirmed_synonym_factors(conn, list(metadata.values())) if len(metadata) > 1 else {}
    result = project_historical_learning(observed, cutoff=cutoff, synonym_factors=factors)
    result["items"] = result["items"][(page - 1) * page_size: page * page_size]
    result["page"] = page
    result["page_size"] = page_size
    return result
