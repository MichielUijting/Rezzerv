"""Projecteer de centrale winkelartikelkoppeling naar Externe databases.

Alleen een actieve rij in external_article_product_links mag de UI-status
'Gekoppeld' veroorzaken. Kandidaatstatussen blijven voorstel of historie.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.services.external_article_product_link_service import (
    get_confirmed_external_article_product_link,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _central_product_details(
    conn,
    global_product_id: str,
) -> dict[str, Any]:
    product_id = _text(global_product_id)
    if not product_id:
        return {}

    row = conn.execute(
        text(
            """
            SELECT
                gp.name AS global_product_name,
                COALESCE(gp.brand, '') AS global_product_brand,
                COALESCE(gp.primary_gtin, '') AS primary_gtin,
                COALESCE(pgm.inventory_group_key, '') AS product_type_id,
                COALESCE(gpc.gpc_brick_code, '') AS gpc_brick_code,
                COALESCE(gpc.gpc_brick_name, '') AS gpc_brick_name,
                COALESCE(gpc.gpc_brick_name_en, '') AS gpc_brick_name_en,
                COALESCE(gpc.source_version, '') AS gpc_source_version
            FROM global_products gp
            LEFT JOIN product_group_memberships pgm
              ON pgm.global_product_id = gp.id
             AND pgm.active = 1
            LEFT JOIN gpc_product_groups gpc
              ON CAST(gpc.gpc_brick_code AS TEXT) =
                 CASE
                     WHEN pgm.inventory_group_key LIKE 'gpc:%'
                     THEN substr(pgm.inventory_group_key, 5)
                     ELSE ''
                 END
            WHERE gp.id = :global_product_id
            ORDER BY
                CASE
                    WHEN pgm.inventory_group_key LIKE 'gpc:%' THEN 0
                    ELSE 1
                END,
                pgm.updated_at DESC,
                pgm.created_at DESC
            LIMIT 1
            """
        ),
        {"global_product_id": product_id},
    ).mappings().first()

    return dict(row) if row else {}


def _catalog_product_by_gtin(
    conn,
    *values: Any,
) -> dict[str, Any] | None:
    gtin = ""

    for value in values:
        candidate = "".join(
            character
            for character in _text(value)
            if character.isdigit()
        )
        if len(candidate) in {8, 12, 13, 14}:
            gtin = candidate
            break

    if not gtin:
        return None

    row = conn.execute(
        text(
            """
            SELECT
                id AS global_product_id,
                name AS global_product_name,
                primary_gtin
            FROM global_products
            WHERE primary_gtin = :gtin
            LIMIT 1
            """
        ),
        {"gtin": gtin},
    ).mappings().first()

    return dict(row) if row else None


def project_central_link_truth(conn, row: dict[str, Any]) -> dict[str, Any]:
    next_row = dict(row)
    retailer_code = _text(next_row.get("retailer_code"))
    receipt_text = _text(next_row.get("receipt_line_text"))
    external_article_code = _text(
        next_row.get("external_article_code")
        or next_row.get("receipt_article_number")
    )

    central_link = get_confirmed_external_article_product_link(
        conn,
        retailer_code=retailer_code,
        receipt_text=receipt_text,
        external_article_code=external_article_code,
    ) if retailer_code and (receipt_text or external_article_code) else None

    if not central_link:
        candidate_gtin_values = []

        for candidate in next_row.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue

            candidate_gtin_values.extend(
                [
                    candidate.get("gtin"),
                    candidate.get("ean"),
                    candidate.get("barcode"),
                    candidate.get("code"),
                    candidate.get("external_source_product_code"),
                    candidate.get("candidate_source_product_code"),
                    candidate.get("source_product_code"),
                ]
            )

        catalog_product = _catalog_product_by_gtin(
            conn,
            next_row.get("gtin"),
            next_row.get("primary_gtin"),
            next_row.get("linked_gtin"),
            next_row.get("barcode"),
            external_article_code,
            *candidate_gtin_values,
        )

        if catalog_product:
            central_link = {
                "global_product_id": catalog_product.get(
                    "global_product_id"
                ),
                "global_product_name": catalog_product.get(
                    "global_product_name"
                ),
                "primary_gtin": catalog_product.get("primary_gtin"),
                "source": "catalog_gtin",
                "link_status": "active",
            }

    active = bool(central_link)
    central_product_id = _text((central_link or {}).get("global_product_id"))
    central_product_name = _text((central_link or {}).get("global_product_name"))

    next_row["central_link_active"] = active
    next_row["central_external_article_product_link"] = central_link
    next_row["central_global_product_id"] = central_product_id
    next_row["central_global_product_name"] = central_product_name
    next_row["is_linked_to_catalog"] = active
    next_row["is_existing_link_for_receipt_item"] = active

    if active:
        details = _central_product_details(conn, central_product_id)

        central_product_name = (
            _text(details.get("global_product_name"))
            or central_product_name
        )
        central_product_brand = _text(
            details.get("global_product_brand")
        )
        central_gtin = _text(details.get("primary_gtin"))
        product_type_id = _text(details.get("product_type_id"))
        gpc_brick_code = _text(details.get("gpc_brick_code"))
        gpc_brick_name = _text(details.get("gpc_brick_name"))
        gpc_brick_name_en = _text(
            details.get("gpc_brick_name_en")
        )
        gpc_source_version = _text(
            details.get("gpc_source_version")
        )

        enriched_link = dict(central_link or {})
        enriched_link.update(
            {
                "global_product_name": central_product_name,
                "global_product_brand": central_product_brand,
                "primary_gtin": central_gtin,
                "gtin": central_gtin,
                "product_type_id": product_type_id,
                "inventory_group_key": product_type_id,
                "gpc_brick_code": gpc_brick_code,
                "gpc_brick_name": gpc_brick_name,
                "gpc_brick_name_en": gpc_brick_name_en,
                "product_type_label": gpc_brick_name,
                "gpc_source_version": gpc_source_version,
            }
        )

        next_row["central_external_article_product_link"] = (
            enriched_link
        )
        next_row["central_global_product_name"] = (
            central_product_name
        )
        next_row["linked_candidate_name"] = central_product_name
        next_row["global_product_id"] = central_product_id
        next_row["matched_global_product_id"] = central_product_id
        next_row["canonical_catalog_product_id"] = (
            central_product_id
        )

        next_row["gtin"] = central_gtin
        next_row["primary_gtin"] = central_gtin
        next_row["product_type_id"] = product_type_id
        next_row["inventory_group_key"] = product_type_id
        next_row["gpc_brick_code"] = gpc_brick_code
        next_row["gpc_brick_name"] = gpc_brick_name
        next_row["gpc_brick_name_en"] = gpc_brick_name_en
        next_row["product_type_label"] = gpc_brick_name
        next_row["gpc_source_version"] = gpc_source_version

        next_row["status"] = "linked_to_catalog"
        next_row["candidate_status"] = "linked_to_catalog"
    elif str(next_row.get("status") or "").strip().lower() == "linked_to_catalog":
        next_row["status"] = "candidate"
        next_row["candidate_status"] = "candidate"

    candidates = []

    if active:
        candidates.append(
            {
                "candidate_name": central_product_name,
                "candidate_brand": central_product_brand,
                "candidate_source_name": "Artikelcatalogus",
                "source_name": "Artikelcatalogus",
                "gtin": central_gtin,
                "ean": central_gtin,
                "global_product_id": central_product_id,
                "matched_global_product_id": central_product_id,
                "canonical_catalog_product_id": central_product_id,
                "product_type_id": product_type_id,
                "inventory_group_key": product_type_id,
                "gpc_brick_code": gpc_brick_code,
                "gpc_brick_name": gpc_brick_name,
                "gpc_brick_name_en": gpc_brick_name_en,
                "product_type_label": gpc_brick_name,
                "gpc_source_version": gpc_source_version,
                "central_link_active": True,
                "is_linked_to_catalog": True,
                "is_existing_link_for_receipt_item": True,
                "status": "linked_to_catalog",
                "candidate_status": "linked_to_catalog",
            }
        )

    for raw_candidate in next_row.get("candidates") or []:
        if not isinstance(raw_candidate, dict):
            continue
        candidate = dict(raw_candidate)
        candidate_product_id = _text(
            candidate.get("global_product_id")
            or candidate.get("matched_global_product_id")
            or candidate.get("canonical_catalog_product_id")
        )
        candidate_is_central = bool(active and candidate_product_id == central_product_id)
        candidate["central_link_active"] = candidate_is_central
        candidate["is_linked_to_catalog"] = candidate_is_central
        candidate["is_existing_link_for_receipt_item"] = candidate_is_central
        if candidate_is_central:
            candidate["status"] = "linked_to_catalog"
            candidate["candidate_status"] = "linked_to_catalog"
        elif str(candidate.get("status") or "").strip().lower() == "linked_to_catalog":
            candidate["status"] = "candidate"
            candidate["candidate_status"] = "candidate"
        candidates.append(candidate)
    next_row["candidates"] = candidates
    return next_row


def project_central_link_truth_rows(conn, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [project_central_link_truth(conn, row) for row in rows]
