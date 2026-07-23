"""Projecteer de centrale winkelartikelkoppeling naar Externe databases.

Alleen een actieve rij in external_article_product_links mag de UI-status
'Gekoppeld' veroorzaken. Kandidaatstatussen blijven voorstel of historie.
"""
from __future__ import annotations

from typing import Any

from app.services.external_article_product_link_service import (
    get_confirmed_external_article_product_link,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


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
        next_row["linked_candidate_name"] = central_product_name
        next_row["global_product_id"] = central_product_id
        next_row["matched_global_product_id"] = central_product_id
    elif str(next_row.get("status") or "").strip().lower() == "linked_to_catalog":
        next_row["status"] = "candidate"
        next_row["candidate_status"] = "candidate"

    candidates = []
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
