"""Superuser-only ED2 barcode conflict resolution with read-only preview.

Only the exact store + receipt description + store article code can be changed.
The Catalogus products, historical receipts, household rows and inventory are
never deleted or rewritten. A shared/ambiguous central claim fails closed.
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

def _gtin_key(value: str) -> str:
    """Only checksum-valid GTINs compare equal as padded 14-digit identities."""
    checked = validate_barcode(value, "gtin")
    return str(checked["normalized_value"]).zfill(14) if checked["valid"] else ""


MODES = {"keep_catalog", "keep_manual", "use_other"}


def _inspect(conn, *, source: dict[str, Any], receipt_item_id: str,
             mode: str, new_gtin: str = "", lock: bool = False) -> dict[str, Any]:
    if conn.dialect.name != "postgresql":
        raise RuntimeError("Barcodecorrectie vereist PostgreSQL.")
    if mode not in MODES:
        raise ValueError("Kies een van de beschikbare barcodecorrecties.")
    retailer = canonical_catalog_retailer(source["retailer_code"])
    label = normalize_external_link_receipt_text(source["receipt_text"])
    code = normalize_external_link_article_code(source["external_article_code"])
    if not retailer or not label or not str(receipt_item_id or "").strip():
        raise ValueError("Een winkelketen en een exacte bonnaam zijn verplicht.")
    aliases = list(catalog_retailer_aliases(retailer))
    select_manual = """
        SELECT retailer_code, receipt_text_normalized, external_article_code,
               gtin, barcode_scope, global_product_id, confirmed_by,
               confirmed_at, updated_at
        FROM ed2_manual_barcodes
        WHERE retailer_code IN :aliases AND receipt_text_normalized = :label
          AND external_article_code = :code
    """
    if lock:
        select_manual += " FOR UPDATE"
    manual_rows = [dict(row) for row in conn.execute(
        text(select_manual).bindparams(bindparam("aliases", expanding=True)),
        {"aliases": aliases, "label": label, "code": code},
    ).mappings().all()]
    link_sql = """
        SELECT link.id, link.retailer_code, link.receipt_text_normalized,
               link.external_article_code, link.global_product_id, link.status,
               link.confirmed_by, link.updated_at,
               gp.name AS product_name, gp.primary_gtin, gp.status AS product_status
        FROM external_article_product_links link
        JOIN global_products gp ON gp.id = link.global_product_id
        WHERE link.retailer_code IN :aliases
          AND link.external_article_code = :code
          AND (:code <> '' OR link.receipt_text_normalized = :label)
          AND link.status IN ('confirmed', 'classification_pending')
        ORDER BY link.id
    """
    if lock:
        link_sql += " FOR UPDATE OF link"
    links = [dict(row) for row in conn.execute(
        text(link_sql).bindparams(bindparam("aliases", expanding=True)),
        {"aliases": aliases, "code": code},
    ).mappings().all()]
    blocks = []
    if len(manual_rows) != 1:
        blocks.append("Er is niet precies één bewaarde handmatige barcode voor dit bonartikel.")
    if len(links) != 1:
        blocks.append("De centrale winkelartikelcode heeft geen unieke actieve Cataloguskoppeling.")
    manual = manual_rows[0] if len(manual_rows) == 1 else {}
    central = links[0] if len(links) == 1 else {}
    old_gtin = str(manual.get("gtin") or "")
    catalog_gtin = str(central.get("primary_gtin") or "")
    if not old_gtin or not validate_barcode(old_gtin, "gtin")["valid"]:
        blocks.append("De handmatig opgeslagen barcode is niet betrouwbaar.")
    if not catalog_gtin or not validate_barcode(catalog_gtin, "gtin")["valid"]:
        blocks.append("De Catalogusbarcode is niet geldig of ontbreekt.")
    if str(central.get("product_status") or "").lower() != "active":
        blocks.append("Het gekoppelde Catalogusproduct is niet actief.")
    if _gtin_key(old_gtin) and _gtin_key(old_gtin) == _gtin_key(catalog_gtin):
        blocks.append(
            "Deze GTIN-13/GTIN-14 notaties beschrijven dezelfde barcode. "
            "Er is geen barcodecorrectie nodig; controleer een eventuele "
            "afwijkende Catalogusproductkoppeling afzonderlijk."
        )
    selected_gtin = catalog_gtin if mode == "keep_catalog" else old_gtin
    if mode == "use_other":
        checked = validate_barcode(new_gtin, "gtin")
        if not checked["valid"]:
            blocks.append("Voer een echte geldige EAN/GTIN met controlecijfer in.")
        selected_gtin = str(checked.get("normalized_value") or "")
        if _gtin_key(selected_gtin) and _gtin_key(selected_gtin) in (
            _gtin_key(old_gtin), _gtin_key(catalog_gtin)
        ):
            blocks.append("Kies voor een bestaande barcode de bijbehorende optie; een voorloopnul maakt geen andere GTIN.")
    # A code-only or aliased central link may serve many receipt identities.
    # Never change that shared link merely to solve one visible ED2 conflict.
    if central and str(central.get("receipt_text_normalized") or "") != label:
        blocks.append(
            "De Cataloguskoppeling is niet uniek voor deze exacte bonnaam. "
            "Controleer eerst welke artikelen de gedeelde koppeling gebruiken."
        )
    if mode != "keep_catalog" and central:
        if str(central.get("receipt_text_normalized") or "") != label:
            blocks.append("De Cataloguskoppeling geldt ook buiten deze exacte bonnaam. Deze gedeelde koppeling kan niet automatisch worden vervangen.")
        if str(central.get("retailer_code") or "") != retailer:
            blocks.append("De bestaande centrale koppeling gebruikt een afwijkende winkelalias; een afzonderlijke beoordeling is nodig.")
    if mode != "keep_catalog" and central and code:
        # Retailer article codes can be shared across receipt descriptions.
        # With NO article code the resolver instead requires an exact name,
        # so scanning all unrelated code-less receipts would be incorrect.
        other_receipt_names = conn.execute(text("""
            SELECT DISTINCT
                COALESCE(NULLIF(rt.store_chain, ''), rt.store_name, '') AS retailer,
                COALESCE(NULLIF(rtl.corrected_raw_label, ''),
                         NULLIF(rtl.normalized_label, ''),
                         NULLIF(rtl.raw_label, ''), '') AS bonnaam
            FROM receipt_table_lines rtl
            JOIN receipt_tables rt ON rt.id = rtl.receipt_table_id
            WHERE rtl.external_article_code = :code
              AND COALESCE(rtl.is_deleted, FALSE) = FALSE
              AND rt.deleted_at IS NULL
            LIMIT 101
        """), {"code": code}).mappings().all()
        if len(other_receipt_names) >= 101:
            # A bounded, unordered sample is not sufficient evidence that the
            # retailer-code link is exclusive to this receipt description.
            blocks.append(
                "Er zijn te veel verschillende kassabonbronnen voor deze "
                "winkelartikelcode; de gedeelde koppeling moet apart worden onderzocht."
            )
        if any(
            canonical_catalog_retailer(row["retailer"]) == retailer
            and normalize_external_link_receipt_text(row["bonnaam"]) != label
            for row in other_receipt_names
        ):
            blocks.append(
                "Dezelfde winkelartikelcode komt op originele bonnen met andere "
                "artikelnamen voor. Een gedeelde koppeling mag niet worden gewijzigd."
            )
    if not code:
        # A nameless retailer code may be absent on historical receipts.
        # Reassignment is only safe when the exact retailer+name has a single
        # central identity, not a second code-bound product with the same name.
        other_links = conn.execute(
            text("""
                SELECT DISTINCT global_product_id, external_article_code
                  FROM external_article_product_links
                 WHERE retailer_code IN :aliases
                   AND receipt_text_normalized = :label
                   AND status IN ('confirmed', 'classification_pending')
                 LIMIT 2
            """).bindparams(bindparam("aliases", expanding=True)),
            {"aliases": aliases, "label": label},
        ).mappings().all()
        if len(other_links) != 1 or str(other_links[0]["external_article_code"] or "") != "":
            blocks.append(
                "Voor deze winkel en bonnaam bestaan meerdere mogelijke "
                "Cataloguskoppelingen of bonartikelcodes. Een correctie "
                "zonder bonartikelnummer is daarom niet veilig."
            )
        matching_manuals = conn.execute(
            text("""
                SELECT DISTINCT external_article_code, gtin
                  FROM ed2_manual_barcodes
                 WHERE retailer_code IN :aliases
                   AND receipt_text_normalized = :label
                 LIMIT 2
            """).bindparams(bindparam("aliases", expanding=True)),
            {"aliases": aliases, "label": label},
        ).mappings().all()
        if len(matching_manuals) != 1 or str(matching_manuals[0]["external_article_code"] or ""):
            blocks.append(
                "Bij deze bonnaam bestaat ook een andere winkelartikelcode "
                "of barcodeclaim. Correctie zonder bonartikelnummer is niet eenduidig."
            )
    if mode != "keep_catalog" and manual:
        scope = classify_barcode_scope(selected_gtin)["scope"] if selected_gtin else ""
        if scope not in ("global_candidate", "restricted"):
            blocks.append("Deze code kan niet als betrouwbare barcode worden gebruikt.")
        if mode == "keep_manual" and manual.get("global_product_id"):
            product = conn.execute(text("""
                SELECT id, status, primary_gtin FROM global_products WHERE id = :id
            """), {"id": manual["global_product_id"]}).mappings().first()
            if not product or str(product.get("status") or "").lower() != "active":
                blocks.append("De eerder opgeslagen barcode heeft geen actief Catalogusproduct.")
            elif (scope == "global_candidate"
                  and str(product.get("primary_gtin") or "") != selected_gtin):
                blocks.append("De bewaarde barcode en zijn Catalogusidentiteit komen niet overeen.")
            elif (scope == "restricted" and product.get("primary_gtin")):
                blocks.append("Een winkelinterne barcode is ten onrechte globaal gekoppeld.")
            if str(manual.get("barcode_scope") or "") != scope:
                blocks.append("De opgeslagen barcode-scope is niet consistent.")
        try:
            if selected_gtin and scope in ("global_candidate", "restricted"):
                owner, _ = _owner(conn, barcode=selected_gtin, retailer=retailer,
                                  label=label, code=code, scope=scope)
                if mode == "keep_manual" and manual.get("global_product_id") and (
                    str(owner or "") != str(manual["global_product_id"])
                ):
                    blocks.append(
                        "De bewaarde barcode behoort volgens de Catalogusidentiteiten "
                        "niet aantoonbaar bij hetzelfde product als de handmatige koppeling."
                    )
        except ValueError as error:
            blocks.append(str(error))
    snapshot = {
        "id": receipt_item_id, "retailer": retailer, "label": label, "code": code,
        "mode": mode, "requested_gtin": new_gtin, "selected_gtin": selected_gtin,
        "manual": {key: str(manual.get(key) or "") for key in (
            "retailer_code", "gtin", "barcode_scope", "global_product_id",
            "confirmed_by", "confirmed_at", "updated_at"
        )},
        "central": {key: str(central.get(key) or "") for key in (
            "id", "retailer_code", "receipt_text_normalized",
            "external_article_code", "global_product_id", "status",
            "confirmed_by", "updated_at", "primary_gtin", "product_status"
        )},
        "blocked": blocks,
    }
    fingerprint = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "receipt_item_id": receipt_item_id, "retailer": retailer,
        "receipt_text": source["receipt_text"], "article_code": code,
        "mode": mode, "old_manual_gtin": old_gtin,
        "catalog_gtin": catalog_gtin, "new_gtin": selected_gtin,
        "catalog_product_name": central.get("product_name") or "",
        "blocked_reasons": blocks, "can_confirm": not bool(blocks),
        "preview_fingerprint": fingerprint,
        "manual_row": manual, "central_row": central,
        "household_changes": 0, "receipt_changes": 0, "stock_changes": 0,
    }


def preview_barcode_conflict_resolution(
    conn, *, source: dict[str, Any], receipt_item_id: str,
    mode: str, new_gtin: str = "",
) -> dict[str, Any]:
    result = _inspect(conn, source=source, receipt_item_id=receipt_item_id,
                      mode=mode, new_gtin=new_gtin)
    return {key: value for key, value in result.items()
            if key not in {"manual_row", "central_row"}}


def confirm_barcode_conflict_resolution(
    conn, *, source: dict[str, Any], receipt_item_id: str,
    mode: str, new_gtin: str, preview_fingerprint: str,
    actor_user_id: str,
) -> dict[str, Any]:
    actor = str(actor_user_id or "").strip()
    if not actor:
        raise ValueError("De bevoegde bevestiger ontbreekt.")
    retailer = canonical_catalog_retailer(source["retailer_code"])
    label = normalize_external_link_receipt_text(source["receipt_text"])
    code = normalize_external_link_article_code(source["external_article_code"])
    # Discover the old and selected GTIN before taking any advisory lock.
    # Revalidate the entire snapshot under row locks below. This preserves
    # the lock order shared with ordinary ED2 materialisation.
    candidate = _inspect(conn, source=source, receipt_item_id=receipt_item_id,
                         mode=mode, new_gtin=new_gtin)
    keys = {"ed2-receipt:" + retailer + "|" + label + "|" + code}
    for barcode in (candidate["old_manual_gtin"], candidate["new_gtin"]):
        if barcode:
            scope = classify_barcode_scope(barcode)["scope"]
            if scope in ("global_candidate", "restricted"):
                keys.add("ed2-barcode:" + ("global" if scope == "global_candidate" else retailer) + ":" + barcode)
    # Existing ordinary ED2 materialisation uses the same lock namespace.
    for key in sorted(keys):
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 677))"),
                     {"key": key})
    result = _inspect(conn, source=source, receipt_item_id=receipt_item_id,
                      mode=mode, new_gtin=new_gtin, lock=True)
    if result["preview_fingerprint"] != preview_fingerprint:
        raise ValueError("De barcodegegevens zijn veranderd. Bekijk eerst opnieuw de gevolgen.")
    if not result["can_confirm"]:
        raise ValueError("Correctie is niet veilig: " + "; ".join(result["blocked_reasons"]))
    manual = result["manual_row"]
    central = result["central_row"]
    old_gtin = result["old_manual_gtin"]
    code_params = {"retailer": manual["retailer_code"], "label": label, "code": code,
                   "old_gtin": old_gtin, "old_product": manual.get("global_product_id")}
    if mode == "keep_catalog":
        removed = conn.execute(text("""
            DELETE FROM ed2_manual_barcodes
            WHERE retailer_code = :retailer AND receipt_text_normalized = :label
              AND external_article_code = :code AND gtin = :old_gtin
              AND global_product_id IS NOT DISTINCT FROM :old_product
        """), code_params)
        if removed.rowcount != 1:
            raise ValueError("De handmatige barcode is inmiddels veranderd.")
        selected_product = str(central["global_product_id"])
    else:
        retired = conn.execute(text("""
            UPDATE external_article_product_links
               SET status = 'inactive', updated_at = CURRENT_TIMESTAMP
             WHERE id = :id AND retailer_code = :retailer
               AND receipt_text_normalized = :label
               AND external_article_code = :code
               AND global_product_id = :product
               AND status = :status
        """), {
            "id": central["id"], "retailer": central["retailer_code"],
            "label": label, "code": code, "product": central["global_product_id"],
            "status": central["status"],
        })
        if retired.rowcount != 1:
            raise ValueError("De centrale Cataloguskoppeling is inmiddels veranderd.")
        if mode == "use_other":
            revised = conn.execute(text("""
                UPDATE ed2_manual_barcodes
                   SET gtin = :new_gtin, barcode_scope = NULL,
                       global_product_id = NULL, confirmed_by = NULL,
                       confirmed_at = NULL, updated_at = CURRENT_TIMESTAMP
                 WHERE retailer_code = :retailer AND receipt_text_normalized = :label
                   AND external_article_code = :code AND gtin = :old_gtin
                   AND global_product_id IS NOT DISTINCT FROM :old_product
            """), {**code_params, "new_gtin": result["new_gtin"]})
            if revised.rowcount != 1:
                raise ValueError("De handmatige barcode is inmiddels veranderd.")
        materialized = materialize_saved_ed2_barcode(
            conn, retailer_code=source["retailer_code"],
            receipt_text=source["receipt_text"],
            external_article_code=source["external_article_code"],
            barcode=result["new_gtin"], confirmed_by=actor, require_existing=True,
        )
        selected_product = str(materialized["global_product_id"])
    write_authorization_audit(
        conn, actor_user_id=actor, actor_type="platform_user",
        action="catalog.ed2.barcode_conflict.resolved",
        object_type="ed2_manual_barcode",
        object_id=retailer + "|" + label + "|" + code,
        old_value={"catalog_gtin": result["catalog_gtin"], "manual_gtin": old_gtin,
                   "catalog_product_id": str(central["global_product_id"]),
                   "manual_product_id": str(manual.get("global_product_id") or "")},
        new_value={"mode": mode, "gtin": result["new_gtin"],
                   "global_product_id": selected_product},
        reason="superuser_confirmed_exact_receipt_barcode_correction",
    )
    return {
        "corrected": True, "mode": mode, "gtin": result["new_gtin"],
        "global_product_id": selected_product, "receipt_changes": 0,
        "household_changes": 0, "stock_changes": 0,
    }
