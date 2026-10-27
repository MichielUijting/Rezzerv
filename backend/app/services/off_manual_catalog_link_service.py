"""Bevestig een OFF-hit als centraal Catalogusartikel via de bestaande koppeldiensten.

De browser levert alleen bronidentiteit en GTIN. De backend valideert beide opnieuw,
leest het OFF-product exact op GTIN en gebruikt alleen bestaande domeinservices.
Geen huishoudartikel, voorraadmutatie of handmatige database-migratie.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.db import engine
from app.services.external_article_confirmation_service import (
    confirm_external_article_for_receipt_item,
    resolve_external_article_identity,
)
from app.services.external_article_product_link_service import (
    _complete_global_product_link_data,
)
from app.services.external_product_identity_policy import (
    assert_external_product_identity_compatible,
)
from app.services.gtin_validation_service import is_valid_gtin
from app.services.off_product_link_service import link_off_product_with_product_type
from app.services.off_manual_search_proof import verify_manual_off_proof
from app.services.automatic_product_type_service import official_bricks
from app.services.product_taxonomy_store import normalize_taxonomy_text, _seed_payload


def _verified_official_gpc_for_exact_name(product: dict[str, Any]) -> str:
    """Return only a GS1-verified, seed-declared exact product-name bridge.

    This is intentionally NOT fuzzy GS1 classification. Current official
    GS1 guidance explicitly identifies cured pork ham as brick 10005781.
    Ambiguous variants, other meat species and unknown terms remain blocked.
    """
    title = normalize_taxonomy_text(product.get("product_name"))
    if not title:
        return ""
    possible = {
        str(code)
        for entry in _seed_payload().get("taxonomy", [])
        for name, code in (entry.get("verified_official_gpc_by_exact_name") or {}).items()
        if normalize_taxonomy_text(name) == title
    }
    if len(possible) != 1:
        return ""
    code = possible.pop()
    if not re.fullmatch(r"[0-9]{8}", code) or code not in official_bricks():
        return ""
    return code


def confirm_selected_off_catalog_product(payload: dict[str, Any]) -> dict[str, Any]:
    """Koppel pas na expliciete UI-OK; server-verifieer naam, GTIN en classificatie."""
    receipt_item_id = str(payload.get("receipt_item_id") or "").strip()
    gtin = str(payload.get("gtin") or "").strip()
    if not receipt_item_id or not is_valid_gtin(gtin):
        raise ValueError("Een geldig bonartikel en een geldige OFF-barcode zijn verplicht")

    # De server heeft dit resultaat zojuist zelf van OFF ontvangen en
    # ondertekend. Controleer het kortlevende bron- en GTIN-gebonden bewijs
    # zonder een tweede externe OFF-call. Browservelden worden genegeerd.
    product = verify_manual_off_proof(
        payload.get("selection_proof"),
        receipt_item_id=receipt_item_id,
        gtin=gtin,
    )

    # Centrale artikelidentiteit komt uitsluitend uit de oorspronkelijke bronregel.
    with engine.begin() as conn:
        identity = resolve_external_article_identity(conn, receipt_item_id)
        assert_external_product_identity_compatible(
            retailer_code=identity["retailer_code"],
            receipt_text=identity["receipt_text"],
            candidate_brand=product.get("brand"),
            candidate_name=product.get("product_name"),
        )

        # Een bestaand volledig Catalogusproduct heeft al een officieel GPC-type.
        # Hergebruik daarvan is toegestaan en vereist geen nieuw product of taxonomie.
        existing = conn.execute(
            text("SELECT id FROM global_products WHERE primary_gtin = :gtin LIMIT 1"),
            {"gtin": gtin},
        ).mappings().first()
        if existing:
            product_id = str(existing["id"])
            complete = _complete_global_product_link_data(conn, product_id)
            if complete.get("complete") and complete.get("primary_gtin") == gtin:
                linked = confirm_external_article_for_receipt_item(
                    conn,
                    receipt_item_id=receipt_item_id,
                    global_product_id=product_id,
                    confirmed_by="external_databases_off_manual_link",
                )
                if (
                    not isinstance(linked, dict)
                    or linked.get("status") != "confirmed"
                    or str(linked.get("global_product_id") or "") != product_id
                ):
                    raise RuntimeError("Cataloguskoppeling kon niet worden bevestigd; transactie teruggedraaid")
                return {
                    "ok": True, "linked": True, "global_product_id": product_id,
                    "gtin": gtin, "link": linked, "creates_inventory_event": False,
                }

    # Een nieuw Catalogusproduct mag uitsluitend met een échte officiële GS1
    # GPC-brick worden aangemaakt. Nooit een klasse raden op basis van bonnaam.
    brick = str(product.get("explicit_gpc_brick_code") or "").strip()
    if not re.fullmatch(r"[0-9]{8}", brick):
        brick = _verified_official_gpc_for_exact_name(product)
    if not re.fullmatch(r"[0-9]{8}", brick):
        raise ValueError(
            "Dit OFF-artikel heeft geen officiële GS1 GPC-classificatie. "
            "Koppelen is daarom nog niet mogelijk; er is niets opgeslagen."
        )
    linked = link_off_product_with_product_type(
        receipt_item_id=receipt_item_id,
        off_product=product,
        product_type_assignment={
            "product_type_id": f"gpc:{brick}",
            "gpc_source": "external",
            "confidence_score": 1.0,
        },
    )
    return {
        "ok": bool(linked.get("ok")),
        "linked": bool(linked.get("linked")),
        "global_product_id": linked.get("global_product", {}).get("id"),
        "gtin": gtin,
        "creates_inventory_event": False,
    }
