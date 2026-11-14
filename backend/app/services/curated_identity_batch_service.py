"""One reviewed, atomic batch for strongly curated barcode-free receipt identities.

This is a reusable matching pipeline: explicitly confirmed (retailer, receipt
description, article number) becomes durable knowledge. The current automatic
proposal family is deliberately restricted to the PO-approved fresh courgette
examples. The preview performs *no writes*. It must not invent a GTIN or
derive household identity from shared names.
"""
from __future__ import annotations

from hashlib import sha256
import json

from app.services.article_synonym_service import load_products
from app.services.ed2_receipt_family_link_service import (
    _parts, _family_variant, _matching_target, _snapshot,
    _guard_preexisting_claims, confirm_courgette_receipt,
)
from app.services.external_article_confirmation_service import resolve_external_article_identity
from app.services.external_unlinked_articles_service import list_all_external_articles
from app.services.external_article_product_link_service import normalize_external_link_receipt_text


MAX_BATCH = 50


def _catalog_anchor(product):
    label = normalize_external_link_receipt_text(
        " ".join((str(product.get("name") or ""), str(product.get("variant") or ""))))
    return (
        _family_variant(label) == "standard"
        and bool(product.get("primary_gtin") or product.get("article_codes"))
    )


def _fingerprint(root, entries):
    return sha256(json.dumps({
        "rule": "curated_exact_receipt_batch_v1",
        "target_id": root["id"],
        "target_name": root["name"],
        "target_gtin": root.get("primary_gtin") or "",
        "sources": [
            {"id": row["receipt_item_id"], "source": row["source_key"],
             "mode": row["mode"], "target_fingerprint": row["target_fingerprint"]}
            for row in sorted(entries, key=lambda item: item["receipt_item_id"])
        ],
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def matching_batch_preview(conn, *, target_product_id=None):
    """Return only strongly approved, independently supported source candidates.

    A consumer-provided target is checked against current Catalogus evidence.
    The caller must confirm an exact set after reviewing this read-only plan.
    """
    products = load_products(conn)
    roots = [product for product in products if _catalog_anchor(product)]
    roots.sort(key=lambda product: (str(product["name"]).casefold(), product["id"]))
    options = [{
        "product_id": product["id"],
        "product_name": product["name"],
        "barcode": product.get("primary_gtin") or "",
    } for product in roots[:50]]
    response = {"family": "verse_courgette_v1", "targets": options,
                "items": [], "blocked": [], "fingerprint": None}
    if not target_product_id:
        return response
    root = next((p for p in roots if p["id"] == target_product_id), None)
    if root is None:
        raise ValueError("Het geselecteerde Catalogusproduct is geen bewezen gewone verse courgette.")

    # Reuse the already protected source listing. It excludes deleted receipts,
    # financial items and duplicate receipt lines and distinguishes identity
    # from the independent GS1 classification status.
    source_rows = list_all_external_articles(conn=conn)["items"]
    seen_keys = set()
    proposed_variants = set()
    for item in source_rows:
        label = str(item.get("receipt_line_text") or "")
        variant = _family_variant(normalize_external_link_receipt_text(label))
        if not variant:
            continue
        if item.get("identity_status") != "not_identified":
            continue
        if item.get("article_code") or item.get("manual_barcode"):
            continue
        source = {
            "retailer_code": item.get("retailer_code"),
            "receipt_text": label,
            "external_article_code": item.get("receipt_article_number"),
        }
        try:
            key = _parts(source)
        except ValueError:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        mode = _matching_target(variant, root)
        if not mode:
            continue
        entry = {
            "receipt_item_id": str(item["id"]),
            "retailer": key[0],
            "receipt_line_text": label,
            "receipt_article_number": key[2],
            "source_key": list(key),
            "mode": mode,
            "mode_label": "Zelfde verse courgette" if mode == "same_product"
                          else "Afzonderlijk Catalogusproduct als synoniem",
            "target_fingerprint": _snapshot(source, root, mode),
        }
        # An existing exact barcode/legacy claim is stronger than this
        # curated text family; never overwrite or skip a conflict.
        try:
            _guard_preexisting_claims(conn, source)
        except ValueError as exc:
            response["blocked"].append({**entry, "reason": str(exc)})
            continue
        # A label-specific variant is created once, never once per receipt.
        # Repeat variants are reviewed after the first confirmed relation.
        if mode == "synonym_variant":
            vkey = (variant, normalize_external_link_receipt_text(label))
            if vkey in proposed_variants:
                response["blocked"].append({
                    **entry, "reason": "Dezelfde variant komt meermaals voor: bevestig eerst één artikel.",
                })
                continue
            proposed_variants.add(vkey)
        response["items"].append(entry)
    response["items"].sort(key=lambda row: (
        row["mode"] != "same_product", row["retailer"],
        row["receipt_line_text"].casefold(), row["receipt_article_number"],
    ))
    response["fingerprint"] = _fingerprint(root, response["items"])
    return response


def confirm_matching_batch(conn, *, target_product_id, receipt_item_ids,
                           expected_fingerprint, actor_id):
    """Apply only the exact reviewed preview in one outer transaction.

    No receipt, household or inventory objects are updated. If even one
    confirmation fails, the caller rolls back all central link/synonym writes.
    """
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise ValueError("Centrale batchbevestiging vereist PostgreSQL.")
    ids = [str(item or "").strip() for item in receipt_item_ids]
    if not ids or len(ids) > MAX_BATCH or len(set(ids)) != len(ids):
        raise ValueError("Selecteer 1 tot en met 50 unieke bonartikelen.")
    plan = matching_batch_preview(conn, target_product_id=target_product_id)
    available = {row["receipt_item_id"]: row for row in plan["items"]}
    if any(item not in available for item in ids):
        raise ValueError("De selectie is gewijzigd of bevat een reeds gekoppeld artikel.")
    if not plan["fingerprint"] or expected_fingerprint != plan["fingerprint"]:
        raise ValueError("De voorbeeldlijst is gewijzigd. Vernieuw en beoordeel opnieuw.")
    if not actor_id:
        raise ValueError("Een bevoegde bevestiger ontbreekt.")
    results = []
    for receipt_id in ids:
        row = available[receipt_id]
        source = resolve_external_article_identity(conn, receipt_id)
        if list(_parts(source)) != row["source_key"]:
            raise ValueError("Het bonartikel is tijdens de bevestiging gewijzigd.")
        results.append(confirm_courgette_receipt(
            conn, source=source, receipt_item_id=receipt_id,
            target_product_id=target_product_id, match_mode=row["mode"],
            expected_fingerprint=row["target_fingerprint"], actor_id=actor_id,
        ))
    return {
        "ok": True, "linked": len(results),
        "synonyms_created": sum(bool(x["synonym_created"]) for x in results),
        "barcode_written": False, "receipt_changes": 0,
        "household_changes": 0, "stock_changes": 0,
    }
