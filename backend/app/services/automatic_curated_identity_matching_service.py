"""Automatic application of *proven* curated receipt-family identities.

Only an explicit, tested family with ONE independently identified Catalogus
anchor may be applied. The independent retailer article number is mandatory:
an unqualified text label is never sufficient for a new central identity.
Each item is re-read inside a savepoint so a disputed item stays reviewable
without undoing other independently safe matches. This service never edits
source receipts, household articles, stock or barcodes.
"""
from __future__ import annotations

from fastapi import HTTPException

from app.services.curated_identity_batch_service import matching_batch_preview, MAX_BATCH
from app.services.ed2_receipt_family_link_service import (
    _parts, confirm_courgette_receipt,
)
from app.services.external_article_confirmation_service import resolve_external_article_identity


def automatically_match_curated_receipts(conn, *, actor_id: str) -> dict:
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise ValueError("Automatische centrale matching vereist PostgreSQL.")
    if not actor_id:
        raise ValueError("Een geautoriseerde gebruiker ontbreekt.")

    options = matching_batch_preview(conn)["targets"]
    # Never arbitrarily choose between different proven products. In the
    # ambiguous case the existing human-reviewed batch remains available.
    if len(options) != 1:
        return {
            "ok": True, "status": "anchor_review_required",
            "linked": 0, "synonyms_created": 0,
            "requires_review": True, "barcode_written": False,
            "blocked": 0, "unprocessed": 0,
        }
    target_id = options[0]["product_id"]
    plan = matching_batch_preview(conn, target_product_id=target_id)
    eligible = [
        row for row in plan["items"]
        if row.get("receipt_article_number")
        and row["mode"] in {"same_product", "synonym_variant"}
    ]
    linked, synonyms, conflicts = 0, 0, 0
    for row in eligible[:MAX_BATCH]:
        # Concurrency, stale source edits and classification/synonym group
        # clashes fail closed for this row, without hiding the other candidates.
        try:
            with conn.begin_nested():
                source = resolve_external_article_identity(
                    conn, row["receipt_item_id"]
                )
                if list(_parts(source)) != row["source_key"]:
                    raise ValueError("De bronidentiteit is gewijzigd.")
                result = confirm_courgette_receipt(
                    conn, source=source,
                    receipt_item_id=row["receipt_item_id"],
                    target_product_id=target_id,
                    match_mode=row["mode"],
                    expected_fingerprint=row["target_fingerprint"],
                    actor_id=actor_id,
                    automatic=True,
                )
            if not result.get("already_confirmed"):
                linked += 1
                synonyms += bool(result.get("synonym_created"))
        except (ValueError, HTTPException):
            conflicts += 1
    remaining = len(plan["items"]) - linked
    return {
        "ok": True, "status": "applied",
        "linked": linked, "synonyms_created": synonyms,
        "barcode_written": False,
        "blocked": len(plan["blocked"]) + conflicts,
        "unprocessed": remaining + len(plan["blocked"]),
        "requires_review": bool(remaining or plan["blocked"] or conflicts),
        "target_product_id": target_id,
        "limit_reached": len(eligible) > MAX_BATCH,
    }
