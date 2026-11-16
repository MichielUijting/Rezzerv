"""Explicit catalog-only identification of a physical product by scanned GTIN.

The scan/lookup itself is read-only. This service is called only after an
authorized Frontteam operator explicitly confirms the barcode and a product
name. It creates no receipt, household article, inventory row or event.
Retailer-scoped codes must be confirmed through the existing ED2 receipt flow.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from app.services.barcode_identity_service import lookup_gtin, validate_barcode
from app.services.barcode_scope_service import classify_barcode_scope


class UniversalScanIdentityError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def confirm_scanned_catalog_gtin(conn: Any, *, barcode: Any, product_name: Any) -> dict[str, Any]:
    checked = validate_barcode(barcode, "gtin")
    if not checked["valid"]:
        raise UniversalScanIdentityError(422, "Barcode heeft geen geldig formaat of controlecijfer.")
    gtin = str(checked["normalized_value"])
    if classify_barcode_scope(gtin)["scope"] != "global_candidate":
        raise UniversalScanIdentityError(
            409, "Dit is een winkelinterne barcode. Beoordeel deze per winkelartikel via Identificeren."
        )
    name = " ".join(str(product_name or "").split())
    if not name or len(name) > 200:
        raise UniversalScanIdentityError(422, "Vul een productnaam van maximaal 200 tekens in.")

    # The same lock namespace/order as ED2 for globally scoped barcodes.
    if conn.dialect.name == "postgresql":
        conn.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:key, 677))"
        ), {"key": "ed2-barcode:global:" + gtin})

    existing = lookup_gtin(conn, gtin)
    status = existing["match_status"]
    if status == "matched":
        return {
            "saved": False, "status": "already_known",
            "gtin": gtin, "product": existing["product"],
            "stock_changes": 0, "receipt_changes": 0, "household_changes": 0,
        }
    if status != "not_found":
        raise UniversalScanIdentityError(
            409, "Deze barcode heeft al een onvolledige of conflicterende identiteit. Controleer eerst de Catalogus."
        )

    # Old ean/upc identities are still ownership evidence. Never put an
    # alternate global GTIN claim on a freshly inserted product.
    owners = conn.execute(text("""
        SELECT DISTINCT global_product_id FROM product_identities
         WHERE identity_type IN ('gtin', 'ean', 'upc')
           AND identity_value = :gtin
    """), {"gtin": gtin}).mappings().all()
    if owners:
        raise UniversalScanIdentityError(409, "Deze barcode is al als productidentiteit in gebruik.")

    product_id = str(uuid.uuid4())
    conn.execute(text("""
        INSERT INTO global_products (
            id, primary_gtin, name, brand, variant, category, size_value,
            size_unit, product_fingerprint, source, status, created_at, updated_at
        ) VALUES (
            :id, :gtin, :name, NULL, NULL, NULL, NULL,
            NULL, NULL, 'manual_scan_identification', 'active',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {"id": product_id, "gtin": gtin, "name": name})
    conn.execute(text("""
        INSERT INTO product_identities (
            id, household_article_id, global_product_id, identity_type,
            identity_value, source, confidence_score, is_primary,
            created_at, updated_at
        ) VALUES (
            :id, '', :product_id, 'gtin', :gtin, 'manual_scan_identification',
            1.0, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {"id": str(uuid.uuid4()), "product_id": product_id, "gtin": gtin})
    return {
        "saved": True, "status": "created", "gtin": gtin,
        "product": {
            "global_product_id": product_id, "name": name,
            "primary_gtin": gtin, "status": "active",
        },
        "stock_changes": 0, "receipt_changes": 0, "household_changes": 0,
    }
