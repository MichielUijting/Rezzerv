"""Read-only trusted historical receipt source -> automatic household stock policy.

Historical Kassa hiding is not a requirement to mark old receipts approved.
The evidence is a proven, durable article match, physical line role, original
receipt date and household cutover. No on-screen or per-item confirmation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, InvalidOperation
import json

from sqlalchemy import text

from app.receipt_ingestion.receipt_line_semantics import derive_receipt_line_semantics
from app.services.historical_household_stock_replay import (
    replay_historical_stock, MAX_HISTORICAL_PURCHASE_LINES,
)
from app.services.receipt_historical_learning_service import (
    OBSERVATION_DAYS, _HISTORICAL_PRODUCT_LINES_SQL, _date,
)
from app.services.receipt_historical_import_policy import read_household_cutover
from app.services.product_day_auto_consume_service import (
    AUTO_CONSUME_NONE, AUTO_CONSUME_PURCHASED_QUANTITY,
    AUTO_CONSUME_ALL_EXISTING,
)
from app.services.synonym_auto_consume_identity import (
    confirmed_household_synonym_group,
)
from app.services.synonym_auto_consume_service import _verified_household_package_factors

# Do not alter PR2's separate "approved receipt" learning contract. An
# already parsed historical receipt never needs ordinary Kassa approval just
# to determine its household's autonomous historical stock.
_HISTORICAL_AUTO_SOURCE_SQL = _HISTORICAL_PRODUCT_LINES_SQL.replace(
    "  AND rt.approved_at IS NOT NULL\n",
    "  AND lower(trim(COALESCE(rt.parse_status, ''))) IN ('parsed', 'approved')\n",
).replace(
    "rt.store_name, rr.sha256_hash,",
    "rt.store_name, rr.sha256_hash, rs.type AS source_type, rs.source_path AS source_provider, "
    "rtl.raw_label, rtl.corrected_raw_label, rtl.external_article_code, rtl.barcode,",
).replace(
    "JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id",
    "JOIN raw_receipts rr ON rr.id = rt.raw_receipt_id AND rr.household_id = rt.household_id "
    "LEFT JOIN receipt_sources rs ON rs.id = rr.source_id AND rs.household_id = rt.household_id",
).replace(
    "AND rt.deleted_at IS NULL AND rr.deleted_at IS NULL",
    "AND rt.deleted_at IS NULL AND rr.deleted_at IS NULL "
    "AND rr.duplicate_of_raw_receipt_id IS NULL "
    "AND COALESCE(rt.workflow_state, 'active') = 'active'",
)

_CANONICAL_MODE = {
    AUTO_CONSUME_NONE, AUTO_CONSUME_PURCHASED_QUANTITY, AUTO_CONSUME_ALL_EXISTING,
}
_UNITS_PIECES = frozenset(("stuk", "stuks", "st"))


def _stock_units(value, unit, *, digital_receipt=False) -> int | None:
    normalized = str(unit or "").strip().lower()
    if normalized not in _UNITS_PIECES and not (digital_receipt and not normalized):
        return None
    if isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not amount.is_finite() or amount < 1 or amount > 10000 or amount != amount.to_integral_value():
        return None
    return int(amount)


def _is_digital_purchase(row):
    return row.get("source_type") == "retailer_api" and row.get("source_provider") in {"ah", "jumbo", "lidl"}


def _setting_modes(conn, owner):
    """Read canonical setting keys; match main's currently shipped values."""
    rows = conn.execute(text("""
        SELECT setting_key, setting_value
        FROM household_settings
        WHERE household_id=:household_id
          AND setting_key IN (
            'consumable_auto_deduction_mode', 'article_auto_consume_overrides'
          )
    """), {"household_id": owner}).mappings().all()
    options = {str(row["setting_key"]): row.get("setting_value") for row in rows}
    raw = str(options.get("consumable_auto_deduction_mode") or "").strip().lower()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    if raw in {"true", "1", "yes", "on", "aan", "waar"}:
        raw = AUTO_CONSUME_PURCHASED_QUANTITY
    household_mode = raw if raw in _CANONICAL_MODE else AUTO_CONSUME_NONE
    raw_overrides = options.get("article_auto_consume_overrides")
    try:
        overrides = json.loads(raw_overrides) if raw_overrides else {}
    except (TypeError, ValueError):
        overrides = {}
    if not isinstance(overrides, dict):
        overrides = {}
    return household_mode, overrides


def _effective_mode(article: dict, household_mode: str, overrides: dict) -> str:
    # A newly matched household article may have no explicit consumable
    # classification yet. A NULL is not a user choice to disable repurchase;
    # trusted physical matches follow the household policy. Explicit False/0
    # remains the canonical prohibition, as for the live receipt path.
    consumable = article.get("consumable")
    if consumable is not None and not bool(consumable):
        return AUTO_CONSUME_NONE
    override = str(overrides.get(str(article["id"])) or "follow_household").lower()
    if override == "always_on":
        override = AUTO_CONSUME_PURCHASED_QUANTITY
    elif override == "always_off":
        override = AUTO_CONSUME_NONE
    return override if override in _CANONICAL_MODE else household_mode


def _owned_articles(conn, owner: str) -> dict:
    rows = conn.execute(text("""
        SELECT ha.id, ha.naam, ha.global_product_id, ha.consumable,
               ha.default_inventory_handling,
               gp.status AS global_product_status,
               gp.size_value, gp.size_unit
        FROM household_articles ha
        LEFT JOIN global_products gp ON gp.id = ha.global_product_id
        WHERE ha.household_id = :household_id
          AND COALESCE(ha.status, 'active') = 'active'
        ORDER BY ha.id
    """), {"household_id": owner}).mappings().all()
    if len(rows) > MAX_HISTORICAL_PURCHASE_LINES:
        raise ValueError("Te veel huishoudartikelen voor veilige automatische voorraad")
    return {str(row["id"]): dict(row) for row in rows}


def _resolve_article_from_line(line: dict, articles: dict, unique_catalog: dict):
    requested = str(line.get("matched_article_id") or "").strip()
    explicit = str(line.get("explicit_household_article_id") or "").strip()
    pid = str(line.get("product_id") or "").strip()
    status = str(line.get("article_match_status") or "").strip().lower()
    if requested and (requested != explicit or explicit not in articles):
        return None
    if pid and (str(line.get("product_status") or "").lower() != "active"
                or status not in {"matched", "product_matched"}):
        return None
    if requested:
        article = articles[requested]
        linked = str(article.get("global_product_id") or "").strip()
        if pid and linked and linked != pid:
            return None
        return requested
    if not pid:
        return None
    candidates = unique_catalog.get(pid, ())
    return candidates[0] if len(candidates) == 1 else None


def _confirmed_group_factors(conn, *, owner, articles, modes, candidates):
    """Resolve only confirmed edges and verified Catalogus pack contents.

    The existing live synonym auto-consume service is the authority. An
    incomplete/ambiguous/override-conflicting component retains independent
    article processing, never speculative cross-product deduction.
    """
    mapping = {}
    factors = {}
    seen = set()
    for article_id in sorted(candidates):
        if article_id in seen:
            continue
        article = articles[article_id]
        if not article.get("global_product_id"):
            continue
        if str(article.get("global_product_status") or "active").lower() != "active":
            continue
        group = confirmed_household_synonym_group(conn, owner, article_id)
        if len(group) < 2:
            continue
        seen.update(group)
        if any(member not in articles for member in group):
            continue
        if any(str(articles[member].get("default_inventory_handling") or "STOCK").upper()
               == "DIRECT_CONSUMPTION" for member in group):
            continue
        if len({modes[member] for member in group}) != 1:
            continue
        verified = _verified_household_package_factors(conn, owner, group)
        if verified is None:
            continue
        _, size_by_article = verified
        for member in group:
            mapping[member] = tuple(group)
            factors[member] = size_by_article[member]
    return mapping, factors


def load_automatic_historical_stock(conn, *, household_id: str) -> dict:
    """Read-only complete replay for the entire household, no page truncation."""
    owner = str(household_id or "").strip()
    if not owner or owner == "0":
        raise ValueError("Actief regulier huishouden ontbreekt")
    cutoff = read_household_cutover(conn, owner)
    if cutoff is None:
        return {"status": "legacy_not_enabled", "household_id": owner,
                "writes_inventory": False, "quantities": {}, "source_line_count": 0}

    source = conn.execute(text(_HISTORICAL_AUTO_SOURCE_SQL), {
        "household_id": owner,
        "earliest_date": cutoff - timedelta(days=OBSERVATION_DAYS),
        "row_limit": MAX_HISTORICAL_PURCHASE_LINES + 1,
    }).mappings().all()
    if len(source) > MAX_HISTORICAL_PURCHASE_LINES:
        return {"status": "source_limit_reached", "household_id": owner,
                "writes_inventory": False, "quantities": {}, "source_line_count": 0}
    articles = _owned_articles(conn, owner)
    household_mode, overrides = _setting_modes(conn, owner)
    modes = {aid: _effective_mode(article, household_mode, overrides)
             for aid, article in articles.items()}
    by_catalog = defaultdict(list)
    for article in articles.values():
        pid = str(article.get("global_product_id") or "").strip()
        if pid and str(article.get("global_product_status") or "").lower() == "active":
            by_catalog[pid].append(str(article["id"]))
    purchases = []
    excluded = 0
    for raw in source:
        row = dict(raw)
        day = _date(row.get("purchase_at"))
        if not day or day >= cutoff or day < cutoff - timedelta(days=OBSERVATION_DAYS):
            excluded += 1
            continue
        if str(row.get("purchase_at_source") or "").strip().lower() == "import_default":
            excluded += 1
            continue
        semantics = derive_receipt_line_semantics(row)
        if semantics.get("line_role") != "product" or not semantics.get("inventory_eligible"):
            excluded += 1
            continue
        quantity = _stock_units(row.get("quantity"), row.get("unit"),
                                digital_receipt=_is_digital_purchase(row))
        if quantity is None:
            excluded += 1
            continue
        article_id = _resolve_article_from_line(row, articles, by_catalog)
        if article_id is None:
            excluded += 1
            continue
        article = articles[article_id]
        if str(article.get("default_inventory_handling") or "STOCK").upper() == "DIRECT_CONSUMPTION":
            excluded += 1
            continue
        if not row.get("sha256_hash"):
            excluded += 1
            continue
        purchases.append({
            "household_id": owner,
            "household_article_id": article_id,
            "purchase_date": day.isoformat(),
            "quantity": quantity,
            "receipt_id": str(row["receipt_table_id"]),
            "line_id": str(row["line_id"]),
            "raw_sha": str(row["sha256_hash"]),
        })

    groups, package_sizes = _confirmed_group_factors(
        conn, owner=owner, articles=articles, modes=modes,
        candidates={p["household_article_id"] for p in purchases},
    )
    result = replay_historical_stock(
        household_id=owner, cutoff=cutoff, purchases=purchases, modes=modes,
        synonym_groups=groups, package_sizes=package_sizes,
    )
    return {
        **result,
        "status": "calculated",
        "source_rows": len(source),
        "excluded_untrusted_rows": excluded,
        "confirmed_synonym_groups": len(set(groups.values())),
        "synonym_groups": groups,
        "writes_inventory": False,
    }
