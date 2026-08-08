"""Centraal domeincontract voor algemene winkelartikelkoppelingen.

Een bevestigde koppeling geldt Rezzerv-breed voor alle huishoudens en voor
oude en nieuwe kassabonnen. Bon-, regel- en huishouden-ID's zijn daarom geen
onderdeel van de sleutel.

Deze laag is bewust klein: alle normalisatie, validatie, vervanging en opslag
blijven gedelegeerd aan ``external_article_product_link_service``. Zo ontstaat
er geen tweede bron van waarheid.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text

from app.services.external_article_product_link_service import (
    get_confirmed_external_article_product_link,
    normalize_external_link_article_code,
    normalize_external_link_receipt_text,
    normalize_external_link_retailer_code,
    save_external_article_product_link,
)


def confirm_global_external_article_product_link(
    conn,
    *,
    retailer_code: Any,
    global_product_id: Any,
    receipt_text: Any = None,
    external_article_code: Any = None,
    confirmed_by: Any = None,
    source_candidate_id: Any = None,
) -> dict[str, Any]:
    """Bevestig één algemene koppeling voor heel Rezzerv.

    De bestaande opslagservice borgt dat een nieuwe bevestiging eerdere
    actieve koppelingen voor dezelfde winkel + artikelcode en/of winkel +
    genormaliseerde bontekst inactief maakt.
    """
    return save_external_article_product_link(
        conn,
        retailer_code=retailer_code,
        global_product_id=global_product_id,
        receipt_text=receipt_text,
        external_article_code=external_article_code,
        confirmed_by=confirmed_by,
        source_candidate_id=source_candidate_id,
    )


def find_global_external_article_product_link(
    conn,
    *,
    retailer_code: Any,
    receipt_text: Any = None,
    external_article_code: Any = None,
) -> Optional[dict[str, Any]]:
    """Lees de algemene koppeling; artikelcode heeft voorrang op bontekst."""
    return get_confirmed_external_article_product_link(
        conn,
        retailer_code=retailer_code,
        receipt_text=receipt_text,
        external_article_code=external_article_code,
    )


def deactivate_global_external_article_product_link(
    conn,
    *,
    retailer_code: Any,
    receipt_text: Any = None,
    external_article_code: Any = None,
) -> int:
    """Beëindig actieve koppelingen zonder historie fysiek te verwijderen.

    Minimaal een winkelartikelcode of bontekst is verplicht. Wanneer beide
    aanwezig zijn, worden actieve koppelingen beëindigd die op één van beide
    stabiele sleutels overeenkomen, binnen dezelfde winkelketen.
    """
    normalized_retailer = normalize_external_link_retailer_code(retailer_code)
    normalized_code = normalize_external_link_article_code(external_article_code)
    normalized_text = normalize_external_link_receipt_text(receipt_text)

    if not normalized_retailer:
        raise ValueError("retailer_code ontbreekt")
    if not normalized_code and not normalized_text:
        raise ValueError("external_article_code of receipt_text is verplicht")

    conditions: list[str] = []
    if normalized_code:
        conditions.append("external_article_code = :external_article_code")
    if normalized_text:
        conditions.append("receipt_text_normalized = :receipt_text_normalized")

    result = conn.execute(
        text(
            f"""
            UPDATE external_article_product_links
            SET status = 'inactive',
                updated_at = CURRENT_TIMESTAMP
            WHERE retailer_code = :retailer_code
              AND status = 'confirmed'
              AND ({' OR '.join(conditions)})
            """
        ),
        {
            "retailer_code": normalized_retailer,
            "external_article_code": normalized_code,
            "receipt_text_normalized": normalized_text,
        },
    )
    return int(result.rowcount or 0)
