from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def normalize_product_fingerprint_text(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def normalize_product_fingerprint_number(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return ""
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return normalize_product_fingerprint_text(value)
    normalized = format(number.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def build_global_product_fingerprint(name: Any, brand: Any = None, variant: Any = None, size_value: Any = None, size_unit: Any = None) -> str:
    normalized_name = normalize_product_fingerprint_text(name)
    if not normalized_name:
        return ""
    canonical = "|".join((
        normalized_name,
        normalize_product_fingerprint_text(brand),
        normalize_product_fingerprint_text(variant),
        normalize_product_fingerprint_number(size_value),
        normalize_product_fingerprint_text(size_unit),
    ))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_or_create_global_product(
    conn,
    *,
    gtin: str | None,
    name: str,
    brand: str | None = None,
    variant: str | None = None,
    category: str | None = None,
    size_value: Any = None,
    size_unit: str | None = None,
    source: str = "user",
    status: str = "active",
    normalize_gtin: Callable[[str], str | None] | None = None,
) -> str:
    normalized_gtin = normalize_gtin(gtin) if gtin and normalize_gtin else (str(gtin).strip() if gtin else None)
    normalized_gtin = normalized_gtin or None
    normalized_name = " ".join(str(name or "").strip().split())
    if not normalized_name:
        raise ValueError("Productnaam is verplicht")

    fingerprint = build_global_product_fingerprint(normalized_name, brand, variant, size_value, size_unit)

    existing = None
    if normalized_gtin:
        existing = conn.execute(
            text("SELECT id FROM global_products WHERE primary_gtin = :primary_gtin LIMIT 1"),
            {"primary_gtin": normalized_gtin},
        ).mappings().first()
    elif fingerprint:
        existing = conn.execute(
            text("""
                SELECT id FROM global_products
                WHERE product_fingerprint = :product_fingerprint
                  AND status = 'active'
                  AND COALESCE(trim(primary_gtin), '') = ''
                LIMIT 1
            """),
            {"product_fingerprint": fingerprint},
        ).mappings().first()

    if existing:
        product_id = str(existing["id"])
        conn.execute(
            text("""
                UPDATE global_products
                SET name = CASE WHEN COALESCE(trim(name), '') = '' THEN :name ELSE name END,
                    brand = COALESCE(brand, :brand),
                    variant = COALESCE(variant, :variant),
                    category = COALESCE(category, :category),
                    size_value = COALESCE(size_value, :size_value),
                    size_unit = COALESCE(size_unit, :size_unit),
                    product_fingerprint = COALESCE(NULLIF(product_fingerprint, ''), :product_fingerprint),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {
                "id": product_id,
                "name": normalized_name,
                "brand": brand,
                "variant": variant,
                "category": category,
                "size_value": size_value,
                "size_unit": size_unit,
                "product_fingerprint": fingerprint or None,
            },
        )
        return product_id

    product_id = str(uuid.uuid4())
    try:
        conn.execute(
            text("""
                INSERT INTO global_products (
                    id, primary_gtin, name, brand, variant, category,
                    size_value, size_unit, product_fingerprint,
                    source, status, created_at, updated_at
                ) VALUES (
                    :id, :primary_gtin, :name, :brand, :variant, :category,
                    :size_value, :size_unit, :product_fingerprint,
                    :source, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "id": product_id,
                "primary_gtin": normalized_gtin,
                "name": normalized_name,
                "brand": brand,
                "variant": variant,
                "category": category,
                "size_value": size_value,
                "size_unit": size_unit,
                "product_fingerprint": fingerprint or None,
                "source": source,
                "status": status,
            },
        )
        return product_id
    except IntegrityError:
        if normalized_gtin:
            winner = conn.execute(text("SELECT id FROM global_products WHERE primary_gtin = :value LIMIT 1"), {"value": normalized_gtin}).mappings().first()
        else:
            winner = conn.execute(
                text("""
                    SELECT id FROM global_products
                    WHERE product_fingerprint = :value
                      AND status = 'active'
                      AND COALESCE(trim(primary_gtin), '') = ''
                    LIMIT 1
                """),
                {"value": fingerprint},
            ).mappings().first()
        if winner:
            return str(winner["id"])
        raise
