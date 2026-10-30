"""Shared, household-scoped receipt-to-stock identity and quantity guards.

Kassa -> Voorraad and Uitpakken -> Voorraad use the same canonical article
resolution and quantity normalizer. Receipt text is a display hint, never an
article identifier or a reason to silently reuse an existing household item.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from sqlalchemy import text

COUNT_UNITS = frozenset({"", "stuk", "stuks", "pcs", "piece", "pieces"})
PACKAGE_UNITS = frozenset({
    "g", "gram", "grams", "kg", "kilogram", "kilograms",
    "ml", "milliliter", "milliliters", "l", "liter", "liters",
})


def checked_stock_quantity(quantity_raw, unit_raw) -> int:
    """Number of purchased stock units; zero means no defensible quantity.

    We track *packages* for weight/volume lines, as the existing inventory
    contract does. Unlike the legacy parser, missing/unknown quantities and
    fractional *piece* counts must not silently become a single item.
    """
    if quantity_raw is None or str(quantity_raw).strip() == "":
        return 0
    try:
        quantity = Decimal(str(quantity_raw))
    except (InvalidOperation, ValueError, TypeError):
        return 0
    if not quantity.is_finite() or quantity <= 0:
        return 0
    unit = str(unit_raw or "").strip().lower()
    if unit in PACKAGE_UNITS:
        return 1
    if unit in COUNT_UNITS and quantity == quantity.to_integral_value():
        return int(quantity)
    return 0


def normalized_store_memory_key(article_name, brand) -> str:
    return f"{str(article_name or '').strip().lower()}||{str(brand or '').strip().lower()}"


def get_confirmed_store_memory(
    conn, *, household_id, store_provider_code, article_name, brand,
) -> dict | None:
    """Only a previously confirmed store choice is reusable automatically."""
    if not household_id or not store_provider_code or not str(article_name or "").strip():
        return None
    row = conn.execute(text("""
        SELECT m.matched_household_article_id AS article_id,
               m.preferred_location_id AS preferred_location_id,
               m.times_confirmed AS times_confirmed
        FROM store_import_memory m
        JOIN household_articles ha
          ON ha.id = m.matched_household_article_id
         AND ha.household_id = m.household_id
        WHERE m.household_id = :household_id
          AND m.store_provider_code = :store_provider_code
          AND m.normalized_key = :normalized_key
          AND COALESCE(m.times_confirmed, 0) >= 1
          AND COALESCE(ha.status, 'active') = 'active'
        ORDER BY m.last_used_at DESC, m.id DESC
        LIMIT 1
    """), {
        "household_id": str(household_id),
        "store_provider_code": str(store_provider_code),
        "normalized_key": normalized_store_memory_key(article_name, brand),
    }).mappings().first()
    return dict(row) if row and row.get("article_id") else None


def find_confirmed_household_article_id(
    conn, *, household_id, store_provider_code, article_name, brand,
) -> str | None:
    memory = get_confirmed_store_memory(
        conn, household_id=household_id, store_provider_code=store_provider_code,
        article_name=article_name, brand=brand,
    )
    return str(memory["article_id"]) if memory else None


def resolve_stock_household_article(
    conn, *,
    main_module, household_id: str, line, store_provider_code: str,
    allow_new_receipt_article: bool = False,
) -> str | None:
    """Resolve one canonical household ID for either purchase-import path.

    Explicit saved selections, confirmed household memory, and catalog-linked
    global products take precedence. Creating a genuinely NEW household
    article is permitted only for an approved Kassa receipt. If a similarly
    named article already exists WITHOUT a confirmed link, refuse to assume
    it is the same physical article.
    """
    household_id = str(household_id or "").strip()
    if not household_id:
        return None
    article_id = str(line.get("matched_household_article_id") or "").strip()
    if article_id:
        selected = main_module.resolve_review_article_option(conn, article_id, household_id)
        if selected:
            return article_id
        return None  # Do not overwrite an invalid/cross-household explicit selection.

    global_id = str(line.get("matched_global_product_id") or "").strip()
    if global_id:
        return main_module.ensure_household_article_for_global_product(
            conn, household_id, global_id,
            article_name_hint=line.get("article_name_raw"),
            barcode=line.get("external_article_code"),
            brand=line.get("brand_raw"),
        )

    remembered = find_confirmed_household_article_id(
        conn, household_id=household_id,
        store_provider_code=store_provider_code,
        article_name=line.get("article_name_raw"),
        brand=line.get("brand_raw"),
    )
    if remembered:
        return remembered
    if not allow_new_receipt_article:
        return None

    name = main_module.normalize_household_article_name(line.get("article_name_raw"))
    if not name:
        return None

    # An existing same-name item is not proof of identical article identity.
    existing = conn.execute(text("""
        SELECT 1 FROM household_articles
        WHERE household_id = :household_id
          AND LOWER(TRIM(naam)) = LOWER(TRIM(:name))
          AND COALESCE(status, 'active') = 'active'
        LIMIT 1
    """), {"household_id": household_id, "name": name}).first()
    if existing:
        return None
    return main_module.ensure_household_article(conn, household_id, name)
