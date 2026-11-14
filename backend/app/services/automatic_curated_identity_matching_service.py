"""Automatic application of *proven* curated receipt-family identities.

Only an explicit, tested family with ONE independently identified Catalogus
anchor may be applied. A missing retailer article number can reuse exactly one independently proven,
code-bearing receipt identity with the same canonical text in this approved
family. The name alone never creates a GTIN, product or synonym edge.
Each item is re-read inside a savepoint so a disputed item stays reviewable
without undoing other independently safe matches. This service never edits
source receipts, household articles, stock or barcodes.
"""
from __future__ import annotations

from fastapi import HTTPException

from app.services.article_synonym_service import load_products
from app.services.external_unlinked_articles_service import list_all_external_articles
from app.services.external_article_product_link_service import (
    normalize_external_link_receipt_text, normalize_external_link_article_code,
)

from app.services.curated_identity_batch_service import matching_batch_preview, MAX_BATCH
from app.services.ed2_receipt_family_link_service import (
    _parts, _family_variant, _matching_target, _snapshot,
    confirm_courgette_receipt,
)
from app.services.external_article_confirmation_service import resolve_external_article_identity


def _independently_proven_exact_names(conn):
    """Map exact normalized receipt names to a UNIQUE already-confirmed product.

    Names never establish a new central identity on their own. Proof comes
    from a DIFFERENT code-bearing, confirmed receipt tuple. Any conflicting
    confirmed product or disputed barcode for that name closes this path.
    Only the same explicitly approved product variant may be reused; no new
    synonym product, barcode or household article is inferred.
    """
    products = {str(p["id"]): p for p in load_products(conn)}
    choices, disputed = {}, set()
    for item in list_all_external_articles(conn=conn)["items"]:
        label = normalize_external_link_receipt_text(item.get("receipt_line_text"))
        code = normalize_external_link_article_code(item.get("receipt_article_number"))
        if not label or not code or not _family_variant(label):
            continue
        status = str(item.get("identity_status") or "")
        if status in {"review", "saved_only"}:
            disputed.add(label)
            continue
        if status != "catalog_linked":
            continue
        family_id = str(item.get("identity_catalog_product_id") or "").strip()
        link_id = str(item.get("catalog_product_id") or "").strip()
        if family_id and link_id and family_id != link_id:
            disputed.add(label)
            continue
        product_id = family_id or link_id
        product = products.get(product_id)
        if not product or _matching_target(_family_variant(label), product) != "same_product":
            disputed.add(label)
            continue
        choices.setdefault(label, set()).add(product_id)
    return {
        label: products[next(iter(ids))]
        for label, ids in choices.items()
        if len(ids) == 1 and label not in disputed
    }


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
    linked, synonyms, conflicts, name_linked = 0, 0, 0, 0
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

    # Second phase: a code-free receipt with the EXACT same normalized name
    # can inherit a proven, code-bearing source's central product. This may
    # include a source matched by the first phase of this same transaction.
    # Do not choose a merely similarly named product or a competing identity.
    code_free = [row for row in plan["items"] if not row.get("receipt_article_number")
                 and row["mode"] in {"same_product", "synonym_variant"}]
    if code_free and linked < MAX_BATCH:
        names = _independently_proven_exact_names(conn)
        for row in code_free[:MAX_BATCH - min(len(eligible), MAX_BATCH)]:
            label = row["source_key"][1]
            product = names.get(label)
            if not product:
                continue
            # A code-free synonym variant already proven by a coded receipt
            # maps to that SAME variant product; do not create another one.
            try:
                with conn.begin_nested():
                    source = resolve_external_article_identity(conn, row["receipt_item_id"])
                    if list(_parts(source)) != row["source_key"]:
                        raise ValueError("De bronidentiteit is gewijzigd.")
                    # Re-evaluate evidence inside the write savepoint, rather
                    # than trusting a name match computed before other writes.
                    refreshed = _independently_proven_exact_names(conn)
                    current = refreshed.get(label)
                    if not current or str(current["id"]) != str(product["id"]):
                        raise ValueError("De bewezen naamkoppeling is gewijzigd.")
                    if _matching_target(_family_variant(label), current) != "same_product":
                        raise ValueError("De artikelvariant is niet dezelfde.")
                    result = confirm_courgette_receipt(
                        conn, source=source,
                        receipt_item_id=row["receipt_item_id"],
                        target_product_id=current["id"],
                        match_mode="same_product",
                        expected_fingerprint=_snapshot(source, current, "same_product"),
                        actor_id=actor_id, automatic=True,
                    )
                if not result.get("already_confirmed"):
                    linked += 1
                    name_linked += 1
            except (ValueError, HTTPException):
                conflicts += 1
    remaining = len(plan["items"]) - linked
    return {
        "ok": True, "status": "applied",
        "linked": linked, "linked_without_article_number": name_linked,
        "synonyms_created": synonyms,
        "barcode_written": False,
        "blocked": len(plan["blocked"]) + conflicts,
        "unprocessed": remaining + len(plan["blocked"]),
        "requires_review": bool(remaining or plan["blocked"] or conflicts),
        "target_product_id": target_id,
        "limit_reached": len(eligible) + len(code_free) > MAX_BATCH,
    }
