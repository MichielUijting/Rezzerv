"""Deterministic Catalogus identity resolution without product classification.

The resolver never guesses an identity from an article name or classification.
Only independently validated barcodes, confirmed retailer codes or an EXACT
previously user-confirmed (store + receipt text + code) identity are evidence.
All paths are read-only; callers own household authorization and writes.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, inspect, text

from app.services.barcode_identity_service import validate_barcode
from app.services.barcode_scope_service import classify_barcode_scope
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
    """Return unique active product or a fail-closed non-match.

    A raw name is never identifying evidence. When available, receipt_text
    is considered ONLY as part of an explicitly confirmed exact store/label/code
    triple. The triple does not generate a barcode or bypass a conflicting GTIN.
    """
    raw_gtin = str(gtin or "").strip()
    retailer = canonical_catalog_retailer(retailer_code)
    article_code = normalize_external_link_article_code(external_article_code)
    candidates: dict[str, set[str]] = {}
    evidence: list[str] = []

    if raw_gtin:
        checked = validate_barcode(raw_gtin, "gtin")
        if not checked["valid"]:
            return {"status": "invalid_gtin", "global_product_id": None, "evidence": []}
        normalized_gtin = checked["normalized_value"]
        if classify_barcode_scope(normalized_gtin)["scope"] == "restricted":
            # A restricted code cannot authorize a global Catalogus lookup.
            # The confirmed retailer-scoped identity is handled separately.
            return {"status": "scope_required", "global_product_id": None, "evidence": []}
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
        code_rows = conn.execute(
            text("""
                SELECT DISTINCT gp.id
                FROM external_article_product_links e
                JOIN global_products gp ON gp.id = e.global_product_id
                WHERE e.retailer_code IN :retailer_aliases
                  AND e.external_article_code = :code
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
            {"retailer_aliases": catalog_retailer_aliases(retailer), "code": article_code},
        ).scalars().all()
        candidates["retailer_code"] = {str(value) for value in code_rows if value}
        evidence.append("retailer_code")

    # The operator's earlier exact receipt tuple is reusable identity proof.
    # Unlike a fuzzy name match it includes the actual shop and bonartikelcode.
    # Never use a code-only or label-only fallback when the exact source was
    # not confirmed, and never allow this proof to disagree with a real GTIN.
    label = normalize_external_link_receipt_text(receipt_text)
    exact_ids: set[str] = set()
    if retailer and label and inspect(conn).has_table("ed2_receipt_family_links"):
        rows = conn.execute(text("""
            SELECT DISTINCT f.global_product_id
            FROM ed2_receipt_family_links f
            JOIN global_products gp ON gp.id = f.global_product_id
            WHERE f.retailer_code IN :aliases
              AND f.receipt_text_normalized = :label
              AND f.external_article_code = :code
              AND TRIM(f.confirmed_by) <> ''
              AND LOWER(COALESCE(gp.status, 'active')) = 'active'
        """).bindparams(bindparam("aliases", expanding=True)), {
            "aliases": catalog_retailer_aliases(retailer),
            "label": label, "code": article_code,
        }).scalars().all()
        exact_ids = {str(row) for row in rows if row}
        if len(exact_ids) > 1:
            return {"status": "conflict", "global_product_id": None,
                    "evidence": evidence + ["confirmed_receipt_tuple"]}
        if exact_ids:
            candidates["confirmed_receipt_tuple"] = exact_ids
            evidence.append("confirmed_receipt_tuple")
            if article_code and not candidates.get("retailer_code"):
                # The EXACT confirmed tuple, including this same code, is
                # evidence even when no legacy code-only identity exists.
                # Never erase a conflicting non-empty code-only claim.
                candidates.pop("retailer_code", None)
                evidence = [x for x in evidence if x != "retailer_code"]

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
