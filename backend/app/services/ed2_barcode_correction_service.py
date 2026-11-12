"""Explicit, single-Lidl-article correction of an already saved ED2 barcode.

A preview is read-only. The confirmation repeats it under database locks and
requires the exact same fingerprint. Only ED2-owned retailer identities are
retired; historical Catalogus, receipt and household rows are never deleted.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import bindparam, text

from app.services.authorization_foundation_service import write_authorization_audit
from app.services.barcode_identity_service import validate_barcode
from app.services.barcode_scope_service import classify_barcode_scope
from app.services.catalog_retailer_identity_keys import (
    canonical_catalog_retailer, catalog_retailer_aliases,
)
from app.services.ed2_confirmed_barcode_service import (
    _owner, materialize_saved_ed2_barcode,
)
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)


def _query(conn, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]


def _inspect_lidl_correction(
    conn, *, source: dict[str, Any], receipt_item_id: str,
    new_gtin: str, household_table: str | None, lock: bool = False,
) -> dict[str, Any]:
    retailer = canonical_catalog_retailer(source["retailer_code"])
    if retailer != "lidl":
        raise ValueError("Deze individuele correctie is alleen voor Lidl-artikelen.")
    label = normalize_external_link_receipt_text(source["receipt_text"])
    code = normalize_external_link_article_code(source["external_article_code"])
    if not label or not str(receipt_item_id or "").strip():
        raise ValueError("Een exacte Lidl-bonartikelidentiteit ontbreekt.")
    verified = validate_barcode(new_gtin, "gtin")
    if not verified["valid"]:
        raise ValueError("Vul een geldige nieuwe barcode met controlecijfer in.")
    barcode = verified["normalized_value"]
    new_scope = classify_barcode_scope(barcode)["scope"]
    if new_scope not in ("global_candidate", "restricted"):
        raise ValueError("De scope van de nieuwe barcode kon niet worden bepaald.")

    query = """
        SELECT retailer_code, receipt_text_normalized, external_article_code,
               gtin, barcode_scope, global_product_id, updated_at
        FROM ed2_manual_barcodes
        WHERE retailer_code IN :aliases
          AND receipt_text_normalized = :label
          AND external_article_code = :code
    """
    if lock:
        query += " FOR UPDATE"
    stmt = text(query).bindparams(bindparam("aliases", expanding=True))
    manual = [dict(row) for row in conn.execute(stmt, {
        "aliases": list(catalog_retailer_aliases(retailer)),
        "label": label, "code": code,
    }).mappings().all()]
    if len(manual) != 1:
        raise ValueError(
            "Er is niet precies één eerder bewaarde Lidl-barcode voor dit bonartikel."
        )
    old = manual[0]
    old_barcode = str(old["gtin"] or "").strip()
    if not old_barcode or old_barcode == barcode:
        raise ValueError("De nieuwe barcode moet afwijken van de eerder bewaarde barcode.")

    old_id = str(old.get("global_product_id") or "").strip() or None
    old_scope = classify_barcode_scope(old_barcode)["scope"]
    old_product = _query(conn, """
        SELECT id, name, status, primary_gtin FROM global_products WHERE id = :id
    """, {"id": old_id}) if old_id else []
    old_status = str(old_product[0].get("status") or "") if old_product else ""
    blocks = []
    if old_id and len(old_product) != 1:
        blocks.append("Het oude Catalogusproduct ontbreekt; corrigeer de koppeling eerst.")
    if old.get("barcode_scope") not in (None, "", old_scope):
        blocks.append("De opgeslagen barcode-scope stemt niet overeen met de oude code.")

    # The old identity is only removable when it is precisely the ED2-owned
    # restricted claim for this one retailer + receipt description + item code.
    old_key = retailer + ":" + label + ":" + code + ":" + old_barcode
    old_identities = _query(conn, """
        SELECT id, global_product_id, source
        FROM product_identities
        WHERE identity_type = 'retailer_barcode' AND identity_value = :value
    """, {"value": old_key}) if old_scope == "restricted" else []
    if old_scope == "restricted" and any(
        str(row.get("global_product_id") or "") != str(old_id or "")
        or row.get("source") != "ed2_saved_barcode"
        for row in old_identities
    ):
        blocks.append("De oude winkelbarcode heeft andere identiteitsbronnen; automatische correctie is niet veilig.")
    if len(old_identities) > 1:
        blocks.append("Er bestaan meerdere oude winkelbarcode-identiteiten.")

    # Never silently reassign another established OFF/retailer association.
    # An explicit future historical repair must assess those links separately.
    legacy_stmt = text("""
        SELECT id, global_product_id, status
        FROM external_article_product_links
        WHERE retailer_code IN :aliases
          AND status IN ('confirmed', 'classification_pending')
          AND external_article_code = :code
          AND (receipt_text_normalized = :label
               OR COALESCE(receipt_text_normalized, '') = '')
        ORDER BY id
    """).bindparams(bindparam("aliases", expanding=True))
    legacy = [dict(row) for row in conn.execute(legacy_stmt, {
        "aliases": list(catalog_retailer_aliases(retailer)),
        "label": label, "code": code,
    }).mappings().all()]
    if legacy:
        blocks.append(
            "Er bestaat nog een bevestigde of wachtende andere Cataloguskoppeling; "
            "die wordt niet zonder gerichte historische herstelcontrole overschreven."
        )

    household_count = 0
    if old_id and household_table:
        household_count = int(conn.execute(text(
            "SELECT COUNT(*) FROM " + household_table
            + " WHERE global_product_id = :id"
        ), {"id": old_id}).scalar() or 0)
    # Household references are reported, not rewritten by this correction.
    if household_count:
        blocks.append(
            "Huishoudartikelen verwijzen nog naar het oude Catalogusproduct. "
            "Eerst gecontroleerd historisch herstel ontwerpen en uitvoeren."
        )

    new_owner = None
    try:
        new_owner, _ = _owner(
            conn, barcode=barcode, retailer=retailer,
            label=label, code=code, scope=new_scope,
        )
    except ValueError as error:
        blocks.append(str(error))
    snapshot = {
        "receipt_item_id": receipt_item_id, "retailer": retailer,
        "receipt_text": label, "article_code": code,
        "old_gtin": old_barcode, "new_gtin": barcode,
        "old_scope": old_scope, "new_scope": new_scope,
        "old_product_id": old_id, "old_status": old_status,
        "old_product_name": str(old_product[0].get("name") or "") if old_product else "",
        "old_updated_at": str(old.get("updated_at") or ""),
        "old_stored_scope": str(old.get("barcode_scope") or ""),
        "old_identity_rows": sorted(
            (str(row.get("id")), str(row.get("global_product_id")),
             str(row.get("source"))) for row in old_identities
        ),
        "legacy_links": sorted(
            (str(row.get("id")), str(row.get("global_product_id")),
             str(row.get("status"))) for row in legacy
        ),
        "household_count": household_count, "new_owner": new_owner,
        "blocked": blocks,
    }
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "receipt_item_id": receipt_item_id,
        "retailer_code": retailer,
        "receipt_text": source["receipt_text"],
        "article_code": code,
        "old_gtin": old_barcode, "new_gtin": barcode,
        "old_scope": old_scope, "new_scope": new_scope,
        "old_product_id": old_id, "old_product_status": old_status or None,
        "old_product_name": snapshot["old_product_name"],
        "new_product_id": new_owner, "new_product_will_be_created": not bool(new_owner),
        "old_identity_rows": old_identities,
        "saved_retailer": old["retailer_code"],
        "legacy_link_count": len(legacy),
        "household_article_count": household_count,
        "blocked_reasons": blocks, "can_confirm": not bool(blocks),
        "preview_fingerprint": fingerprint,
        "catalog_product_kept": True,
        "receipts_changed": 0, "household_changes": 0, "stock_changes": 0,
    }


def preview_lidl_barcode_correction(
    conn, *, source: dict[str, Any], receipt_item_id: str,
    new_gtin: str, household_table: str | None = None,
) -> dict[str, Any]:
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise RuntimeError("Barcodecorrectie vereist PostgreSQL.")
    preview = _inspect_lidl_correction(
        conn, source=source, receipt_item_id=receipt_item_id,
        new_gtin=new_gtin, household_table=household_table,
    )
    # Internal database identities are never exposed as part of the UI contract.
    return {key: value for key, value in preview.items()
            if key not in {"old_identity_rows", "saved_retailer"}}


def confirm_lidl_barcode_correction(
    conn, *, source: dict[str, Any], receipt_item_id: str,
    new_gtin: str, expected_old_gtin: str, preview_fingerprint: str,
    actor_user_id: str, household_table: str | None = None,
) -> dict[str, Any]:
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise RuntimeError("Barcodecorrectie vereist PostgreSQL.")
    verified = validate_barcode(new_gtin, "gtin")
    if not verified["valid"]:
        raise ValueError("Ongeldige nieuwe barcode.")
    barcode = verified["normalized_value"]
    retailer = canonical_catalog_retailer(source["retailer_code"])
    label = normalize_external_link_receipt_text(source["receipt_text"])
    code = normalize_external_link_article_code(source["external_article_code"])
    old = str(expected_old_gtin or "").strip()
    old_scope = classify_barcode_scope(old)["scope"]
    new_scope = classify_barcode_scope(barcode)["scope"]
    if retailer != "lidl" or not old or old == barcode:
        raise ValueError("Alleen expliciete correctie van een bestaande Lidl-barcode is toegestaan.")

    # These exact keys are shared with ordinary barcode materialization.
    # Acquire all in canonical order to avoid inverted advisory locks.
    keys = {
        "ed2-receipt:" + retailer + "|" + label + "|" + code,
        "ed2-barcode:" + ("global" if old_scope == "global_candidate" else retailer) + ":" + old,
        "ed2-barcode:" + ("global" if new_scope == "global_candidate" else retailer) + ":" + barcode,
    }
    for key in sorted(keys):
        conn.execute(text(
            "SELECT pg_advisory_xact_lock(hashtextextended(:key, 677))"
        ), {"key": key})

    preview = _inspect_lidl_correction(
        conn, source=source, receipt_item_id=receipt_item_id,
        new_gtin=barcode, household_table=household_table, lock=True,
    )
    if preview["old_gtin"] != old or preview["preview_fingerprint"] != preview_fingerprint:
        raise ValueError("De artikelgegevens zijn gewijzigd. Bekijk eerst opnieuw de gevolgen.")
    if not preview["can_confirm"]:
        raise ValueError("Correctie is geblokkeerd: " + "; ".join(preview["blocked_reasons"]))
    if not str(actor_user_id or "").strip():
        raise ValueError("De bevestigende gebruiker ontbreekt.")

    # Retire only the obsolete retailer-specific ED2 identity; never erase
    # a globally claimed GTIN or alter a product shared by another article.
    if preview["old_scope"] == "restricted":
        for row in preview["old_identity_rows"]:
            retired = conn.execute(text("""
                DELETE FROM product_identities
                WHERE id = :id AND identity_type = 'retailer_barcode'
                  AND source = 'ed2_saved_barcode'
                  AND global_product_id = :product_id
            """), {"id": row["id"], "product_id": preview["old_product_id"]})
            if retired.rowcount != 1:
                raise ValueError("De oude identiteit is tussentijds gewijzigd.")

    result = conn.execute(text("""
        UPDATE ed2_manual_barcodes
        SET gtin = :new_gtin, barcode_scope = NULL,
            global_product_id = NULL, confirmed_by = NULL,
            confirmed_at = NULL, updated_at = CURRENT_TIMESTAMP
        WHERE retailer_code = :saved_retailer
          AND receipt_text_normalized = :label
          AND external_article_code = :code
          AND gtin = :old_gtin
          AND global_product_id IS NOT DISTINCT FROM :old_product_id
    """), {
        "saved_retailer": preview["saved_retailer"],
        "label": label, "code": code,
        "new_gtin": barcode, "old_gtin": old,
        "old_product_id": preview["old_product_id"],
    })
    if result.rowcount != 1:
        raise ValueError("De bewaarde barcode is tussentijds gewijzigd.")

    linked = materialize_saved_ed2_barcode(
        conn, retailer_code=source["retailer_code"],
        receipt_text=source["receipt_text"],
        external_article_code=source["external_article_code"],
        barcode=barcode, confirmed_by=actor_user_id,
        require_existing=True,
    )
    audit_id = write_authorization_audit(
        conn, actor_user_id=actor_user_id, actor_type="platform_user",
        action="catalog.ed2.lidl_barcode.corrected",
        object_type="ed2_manual_barcode",
        object_id=retailer + "|" + label + "|" + code,
        old_value={
            "gtin": old, "barcode_scope": preview["old_scope"],
            "global_product_id": preview["old_product_id"],
        },
        new_value={
            "gtin": barcode, "barcode_scope": linked["barcode_scope"],
            "global_product_id": linked["global_product_id"],
        },
        reason="confirmed_individual_lidl_correction",
    )
    return {
        "corrected": True, "old_gtin": old, "gtin": barcode,
        "barcode_scope": linked["barcode_scope"],
        "old_global_product_id": preview["old_product_id"],
        "global_product_id": linked["global_product_id"],
        "catalog_product_created": linked["catalog_product_created"],
        "audit_id": audit_id, "receipts_changed": 0,
        "household_changes": 0, "stock_changes": 0,
    }
