"""Confirm a retailer article identity from a verified, scanned GTIN.

Only an explicit authorized user action may call this service. It is never
called by receipt imports or on application startup. Classification is not
part of the identity proof.
"""
from __future__ import annotations

import uuid
from sqlalchemy import bindparam, text

from app.services.barcode_identity_service import validate_barcode
from app.services.catalog_identity_resolution_service import resolve_catalog_identity
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)
from app.services.catalog_retailer_identity_keys import (
    canonical_catalog_retailer, catalog_retailer_aliases,
)


def confirm_scanned_retailer_identity(
    conn, *, retailer_code: str, external_article_code: str,
    scanned_gtin: str, confirmed_by: str, receipt_text: str | None = None,
) -> dict:
    """Bind the exact retailer/receipt description/code to the active GTIN owner.

    Caller is responsible for authenticated authorization and transaction
    commit/rollback. No household article or stock is updated here.
    """
    retailer = canonical_catalog_retailer(retailer_code)
    article_code = normalize_external_link_article_code(external_article_code)
    receipt_label = normalize_external_link_receipt_text(receipt_text)
    actor = str(confirmed_by or "").strip()
    checked = validate_barcode(scanned_gtin, "gtin")
    if not retailer or not article_code or not actor or not checked["valid"]:
        raise ValueError("Winkel, artikelcode, geldige barcode en bevestiger zijn verplicht")
    if conn.dialect.name != "postgresql":
        raise RuntimeError("Artikelidentiteit bevestigen vereist PostgreSQL")

    # Lock the exact code so two concurrent confirmations cannot create
    # competing active identities for the same retailer.
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 672))"),
        {"key": "|".join((retailer, receipt_label, article_code))},
    )
    gtin = checked["normalized_value"]
    gtin_match = resolve_catalog_identity(conn, gtin=gtin)
    if gtin_match["status"] != "matched":
        raise ValueError("Barcode hoort niet uniek bij een actief Catalogusproduct")
    product_id = gtin_match["global_product_id"]

    existing = conn.execute(text("""
        SELECT id, global_product_id, status FROM external_article_product_links
        WHERE retailer_code IN :retailer_aliases
          AND external_article_code = :code
          AND (:receipt_label = '' OR receipt_text_normalized = :receipt_label
               OR COALESCE(receipt_text_normalized, '') = '')
          AND status IN ('confirmed', 'classification_pending')
        FOR UPDATE
    """).bindparams(bindparam("retailer_aliases", expanding=True)),
    {"retailer_aliases": catalog_retailer_aliases(retailer), "code": article_code,
     "receipt_label": receipt_label}).mappings().all()
    if any(str(row["global_product_id"]) != product_id for row in existing):
        raise ValueError("Winkelartikelcode heeft een tegenstrijdige Cataloguskoppeling")
    confirmed = [row for row in existing if row["status"] == "confirmed"]
    if len(confirmed) > 1:
        raise ValueError("Winkelartikelcode heeft meerdere bevestigde koppelingen")
    if confirmed:
        return {
            "status": "already_confirmed",
            "global_product_id": product_id,
            "retailer_code": retailer,
            "external_article_code": article_code,
            "gtin": gtin,
            "changes": 0,
        }

    # The matching pending row can now be confirmed by explicit user proof.
    # Inactive duplicates are not silently promoted.
    pending = [row for row in existing if row["status"] == "classification_pending"]
    if len(pending) > 1:
        raise ValueError("Winkelartikelcode heeft meerdere voorlopige koppelingen")
    if pending:
        conn.execute(text("""
            UPDATE external_article_product_links
            SET status = 'confirmed', confirmed_by = :actor,
                confirmed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND status = 'classification_pending'
        """), {"id": pending[0]["id"], "actor": actor})
    else:
        conn.execute(text("""
            INSERT INTO external_article_product_links (
                id, retailer_code, receipt_text_normalized, external_article_code,
                global_product_id, status, confirmed_by, confirmed_at,
                source_candidate_id, created_at, updated_at
            ) VALUES (
                :id, :retailer, :receipt_label, :code,
                :product, 'confirmed', :actor, CURRENT_TIMESTAMP,
                NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "id": str(uuid.uuid4()), "retailer": retailer,
            "code": article_code, "receipt_label": receipt_label,
            "product": product_id, "actor": actor,
        })
    return {
        "status": "confirmed", "global_product_id": product_id,
        "retailer_code": retailer, "external_article_code": article_code,
        "gtin": gtin, "changes": 1,
    }
