"""Deterministic Catalogus identity resolution without product classification.

The resolver never uses article names, receipt text or classification.
It is read-only, and callers decide whether an authorized household link may
be written.  User-confirmed, GTIN-verified pending-classification links may be used as\nidentities without claiming that GS1/CBS classification is complete.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, inspect, text

from app.services.barcode_identity_service import validate_barcode
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)
from app.services.catalog_retailer_identity_keys import (
    canonical_catalog_retailer, catalog_retailer_aliases,
)


def resolve_catalog_identity(
    conn,
    *,
    gtin: str | None = None,
    retailer_code: str | None = None,
    external_article_code: str | None = None,
    receipt_text: str | None = None,
) -> dict[str, Any]:
    """Return a unique active product or a fail-closed non-match.

    Barcode and store-specific article code are separate identities. If both
    are supplied they must agree; neither a name nor a GPC/CBS assignment is
    a matching condition.
    """
    raw_gtin = str(gtin or "").strip()
    retailer = canonical_catalog_retailer(retailer_code)
    article_code = normalize_external_link_article_code(external_article_code)
    receipt_label = normalize_external_link_receipt_text(receipt_text)
    candidates: dict[str, set[str]] = {}
    evidence: list[str] = []

    if raw_gtin:
        checked = validate_barcode(raw_gtin, "gtin")
        if not checked["valid"]:
            return {"status": "invalid_gtin", "global_product_id": None, "evidence": []}
        normalized_gtin = checked["normalized_value"]
        gtin_rows = conn.execute(
            text("""
                SELECT DISTINCT gp.id
                FROM global_products gp
                LEFT JOIN product_identities pi
                  ON pi.global_product_id = gp.id
                 AND pi.identity_type = 'gtin'
                 AND pi.identity_value = :gtin
                WHERE LOWER(COALESCE(gp.status, 'active')) = 'active'
                  AND (gp.primary_gtin = :gtin OR pi.global_product_id IS NOT NULL)
            """),
            {"gtin": normalized_gtin},
        ).scalars().all()
        candidates["gtin"] = {str(value) for value in gtin_rows if value}
        evidence.append("gtin")

    if article_code:
        if not retailer:
            return {"status": "retailer_required", "global_product_id": None, "evidence": evidence}
        # Isolated historical fixtures can contain the legacy link table
        # without a receipt-description column. Code-only compatibility is
        # permitted only when no receipt label is being requested.
        columns = {col["name"] for col in inspect(conn).get_columns("external_article_product_links")}
        if "receipt_text_normalized" not in columns and receipt_label:
            return {"status": "not_found", "global_product_id": None, "evidence": evidence}
        description_clause = (
            "AND (:receipt_label = '' OR e.receipt_text_normalized = :receipt_label "
            "OR COALESCE(e.receipt_text_normalized, '') = '')"
            if "receipt_text_normalized" in columns else ""
        )
        code_rows = conn.execute(
            text(f"""
                SELECT DISTINCT gp.id
                FROM external_article_product_links e
                JOIN global_products gp ON gp.id = e.global_product_id
                WHERE e.retailer_code IN :retailer_aliases
                  AND e.external_article_code = :code
                  {description_clause}
                  AND (
                        e.status = 'confirmed'
                        OR (
                            e.status = 'classification_pending'
                            AND e.confirmed_by IN (
                                'external_databases_off_pending_gpc',
                                'external_databases_off_pending_gpc_brand_override'
                            )
                            AND EXISTS (
                                SELECT 1 FROM product_identities pi_verified
                                WHERE pi_verified.global_product_id = gp.id
                                  AND pi_verified.identity_type = 'gtin'
                                  AND pi_verified.identity_value = gp.primary_gtin
                            )
                        )
                  )
                  AND LOWER(COALESCE(gp.status, 'active')) = 'active'
            """).bindparams(bindparam("retailer_aliases", expanding=True)),
            {"retailer_aliases": catalog_retailer_aliases(retailer), "code": article_code,
             "receipt_label": receipt_label},
        ).scalars().all()
        candidates["retailer_code"] = {str(value) for value in code_rows if value}
        evidence.append("retailer_code")

    if not evidence:
        return {"status": "no_identity", "global_product_id": None, "evidence": []}
    if any(len(ids) > 1 for ids in candidates.values()):
        return {"status": "conflict", "global_product_id": None, "evidence": evidence}
    nonempty = [ids for ids in candidates.values() if ids]
    if len(nonempty) != len(candidates):
        return {"status": "not_found", "global_product_id": None, "evidence": evidence}
    matches = set.intersection(*nonempty)
    if len(matches) != 1:
        return {"status": "conflict", "global_product_id": None, "evidence": evidence}
    return {"status": "matched", "global_product_id": next(iter(matches)), "evidence": evidence}
