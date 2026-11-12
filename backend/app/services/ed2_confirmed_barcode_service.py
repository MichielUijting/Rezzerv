"""A saved ED2 barcode is confirmed identification, mapped to a Catalogus product.

Separate global GTINs from retailer-scoped restricted codes. Saving in Identificeren is the confirmation; no second review and no OFF
verification is required. Legacy evidence remains trusted while safe historical
materialization is a separately controlled operation. No receipt, household, stock or synonym writes.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import bindparam, text

from app.services.barcode_identity_service import validate_barcode
from app.services.barcode_scope_service import classify_barcode_scope
from app.services.catalog_retailer_identity_keys import (
    canonical_catalog_retailer, catalog_retailer_aliases,
)
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)

_TABLE = "ed2_manual_barcodes"


def _rows(conn, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]


def _owner(conn, *, barcode: str, retailer: str, label: str, code: str, scope: str) -> tuple[str | None, bool]:
    """Resolve a unique product owner, including old primary-GTIN identities."""
    if scope == "global_candidate":
        product_rows = _rows(conn, """
            SELECT id AS product_id, status, primary_gtin
            FROM global_products WHERE primary_gtin = :barcode
        """, {"barcode": barcode})
        identity_rows = _rows(conn, """
            SELECT global_product_id AS product_id
            FROM product_identities
            WHERE identity_type = 'gtin' AND identity_value = :barcode
              AND global_product_id IS NOT NULL
        """, {"barcode": barcode})
        ids = {str(row["product_id"]) for row in product_rows + identity_rows
               if row.get("product_id")}
    else:
        # A historic globally recorded restricted code is not proof of global
        # identity; stop instead of claiming ownership or creating a duplicate.
        global_rows = _rows(conn, """
            SELECT id FROM global_products WHERE primary_gtin = :barcode
        """, {"barcode": barcode})
        if global_rows:
            raise ValueError(
                "Deze winkelinterne barcode is historisch als mondiale code opgeslagen. "
                "Controleer eerst de bestaande Cataloguskoppeling."
            )
        identity_rows = _rows(conn, """
            SELECT global_product_id AS product_id
            FROM product_identities
            WHERE identity_type = 'retailer_barcode'
              AND identity_value = :identity_value
              AND global_product_id IS NOT NULL
        """, {"identity_value": retailer + ":" + label + ":" + code + ":" + barcode})
        ids = {str(row["product_id"]) for row in identity_rows
               if row.get("product_id")}
    if len(ids) > 1:
        raise ValueError("Deze barcode verwijst naar meerdere Catalogusproducten.")
    if not ids:
        return None, False
    product_id = next(iter(ids))
    matches = _rows(conn, """
        SELECT id, status, primary_gtin FROM global_products WHERE id = :id
    """, {"id": product_id})
    if len(matches) != 1 or str(matches[0]["status"] or "").lower() != "active":
        raise ValueError("Het bestaande Catalogusproduct is niet actief of ontbreekt.")
    primary = str(matches[0]["primary_gtin"] or "").strip()
    if scope == "global_candidate" and primary not in ("", barcode):
        raise ValueError("Het bestaande Catalogusproduct heeft een andere primaire GTIN.")
    if scope == "restricted" and primary:
        raise ValueError("Winkelinterne barcode verwijst naar een globale barcode-identiteit.")
    return product_id, True


def materialize_saved_ed2_barcode(
    conn, *, retailer_code: Any, receipt_text: Any,
    external_article_code: Any, barcode: Any, confirmed_by: Any,
    require_existing: bool = False,
) -> dict[str, Any]:
    """One idempotent PostgreSQL transaction; the caller authenticates the actor."""
    retailer = canonical_catalog_retailer(retailer_code)
    label = normalize_external_link_receipt_text(receipt_text)
    code = normalize_external_link_article_code(external_article_code)
    title = " ".join(str(receipt_text or "").strip().split())
    actor = str(confirmed_by or "").strip()
    checked = validate_barcode(barcode, "gtin")
    if not checked["valid"]:
        raise ValueError("Vul een barcode met een geldig formaat en controlecijfer in.")
    value = checked["normalized_value"]
    scope = classify_barcode_scope(value)["scope"]
    if not retailer or not label or not actor or scope not in ("global_candidate", "restricted"):
        raise ValueError("Een echte winkel, kassabonomschrijving en bevestiger zijn verplicht.")
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise RuntimeError("Centrale artikelbevestiging vereist PostgreSQL.")

    # Single deterministic lock order across manual barcode and receipt tuple.
    identity_key = retailer + "|" + label + "|" + code
    for key in sorted(("ed2-barcode:" + ("global" if scope == "global_candidate" else retailer)
                       + ":" + value, "ed2-receipt:" + identity_key)):
        conn.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:key, 677))"
        ), {"key": key})

    params = {"retailer": retailer, "label": label, "code": code}
    # The already-saved barcode is the authoritative evidence. Resolve the
    # same exact tuple across known retailer aliases without creating a second
    # authoritative identity registry.
    manual_stmt = text("""
        SELECT retailer_code, gtin, barcode_scope, global_product_id
        FROM ed2_manual_barcodes
        WHERE retailer_code IN :aliases
          AND receipt_text_normalized = :label
          AND external_article_code = :code FOR UPDATE
    """).bindparams(bindparam("aliases", expanding=True))
    manual = [dict(row) for row in conn.execute(manual_stmt, {
        **params, "aliases": list(catalog_retailer_aliases(retailer)),
    }).mappings().all()]
    if len(manual) > 1:
        raise ValueError("Dubbele opgeslagen winkelidentiteit; veilige koppeling gestopt.")
    if require_existing and not manual:
        raise ValueError(
            "Voor dit bonartikel is geen eerder opgeslagen barcode gevonden; "
            "er is niets nieuw bevestigd."
        )
    if manual and str(manual[0]["gtin"]) != value:
        raise ValueError(
            "Dit bonartikel heeft een andere opgeslagen barcode. "
            "Een correctie vereist een afzonderlijke gevolgencontrole."
        )
    if manual and manual[0].get("global_product_id"):
        old = manual[0]
        if old.get("barcode_scope") != scope:
            raise ValueError("De scope van de bestaande barcodekoppeling wijkt af.")
        products = _rows(conn, """
            SELECT id FROM global_products WHERE id = :id AND status = 'active'
        """, {"id": old["global_product_id"]})
        if len(products) != 1:
            raise ValueError("De bestaande Catalogusidentiteit is niet langer actief.")
        return {
            "status": "already_confirmed", "barcode": value, "barcode_scope": scope,
            "global_product_id": old["global_product_id"],
            "catalog_product_created": False, "household_changes": 0,
            "stock_changes": 0,
        }

    product_id, known = _owner(conn, barcode=value, retailer=retailer, label=label, code=code, scope=scope)

    # Legacy confirmed and waiting identities may be superseded only by an
    # explicitly authorised correction, never as a side effect of confirming.
    stmt = text("""
        SELECT DISTINCT global_product_id AS product_id
        FROM external_article_product_links
        WHERE retailer_code IN :aliases
          AND status IN ('confirmed', 'classification_pending')
          AND external_article_code = :code
          AND (receipt_text_normalized = :label
               OR COALESCE(receipt_text_normalized, '') = '')
    """).bindparams(bindparam("aliases", expanding=True))
    legacy = [dict(row) for row in conn.execute(stmt, {
        **params, "aliases": list(catalog_retailer_aliases(retailer)),
    }).mappings().all()]
    legacy_ids = {str(row["product_id"]) for row in legacy if row.get("product_id")}
    if (product_id and any(owner != product_id for owner in legacy_ids)) or (
        not product_id and legacy_ids
    ):
        raise ValueError(
            "Deze bonartikelidentiteit heeft al een andere Cataloguskoppeling. "
            "Er is niets gewijzigd."
        )

    created = not known
    if not product_id:
        product_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO global_products (
                id, primary_gtin, name, brand, variant, category,
                size_value, size_unit, product_fingerprint, source, status,
                created_at, updated_at
            ) VALUES (
                :id, :gtin, :name, NULL, NULL, NULL,
                NULL, NULL, NULL, :source, 'active',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "id": product_id,
            "gtin": value if scope == "global_candidate" else None,
            "name": title,
            "source": "ed2_manual_gtin" if scope == "global_candidate" else "ed2_retailer_barcode",
        })
    elif scope == "global_candidate":
        conn.execute(text("""
            UPDATE global_products SET primary_gtin = :gtin, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND (primary_gtin IS NULL OR TRIM(primary_gtin) = '')
        """), {"id": product_id, "gtin": value})

    identity_type = "gtin" if scope == "global_candidate" else "retailer_barcode"
    identity_value = value if scope == "global_candidate" else retailer + ":" + label + ":" + code + ":" + value
    existing_ident = _rows(conn, """
        SELECT global_product_id AS product_id FROM product_identities
        WHERE identity_type = :type AND identity_value = :value
          AND global_product_id IS NOT NULL
    """, {"type": identity_type, "value": identity_value})
    if any(str(row["product_id"]) != product_id for row in existing_ident):
        raise ValueError("Barcode-identiteit heeft meerdere producteigenaren.")
    if not existing_ident:
        conn.execute(text("""
            INSERT INTO product_identities (
                id, household_article_id, global_product_id, identity_type,
                identity_value, source, confidence_score, is_primary,
                created_at, updated_at
            ) VALUES (
                :id, '', :product_id, :type, :value, 'ed2_saved_barcode',
                1.0, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            "id": str(uuid.uuid4()), "product_id": product_id,
            "type": identity_type, "value": identity_value,
        })

    if not manual:
        conn.execute(text("""
            INSERT INTO ed2_manual_barcodes (
                retailer_code, receipt_text_normalized, external_article_code,
                gtin, barcode_scope, global_product_id, confirmed_by,
                confirmed_at, created_at, updated_at
            ) VALUES (
                :retailer, :label, :code,
                :barcode, :scope, :product_id, :actor,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """), {
            **params, "barcode": value, "scope": scope,
            "product_id": product_id, "actor": actor,
        })
    else:
        # Backward-compatible materialization: existing user confirmation
        # remains the proof, never silently replace its original barcode.
        result = conn.execute(text("""
            UPDATE ed2_manual_barcodes
            SET barcode_scope = :scope, global_product_id = :product_id,
                confirmed_by = :actor, confirmed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE retailer_code = :saved_retailer
              AND receipt_text_normalized = :label
              AND external_article_code = :code AND gtin = :barcode
              AND global_product_id IS NULL
        """), {
            **params, "saved_retailer": manual[0]["retailer_code"],
            "barcode": value, "scope": scope,
            "product_id": product_id, "actor": actor,
        })
        if result.rowcount != 1:
            raise RuntimeError("De opgeslagen barcode is tussentijds gewijzigd.")

    return {
        "status": "confirmed", "barcode": value, "barcode_scope": scope,
        "global_product_id": product_id, "catalog_product_created": created,
        "household_changes": 0, "stock_changes": 0,
    }
