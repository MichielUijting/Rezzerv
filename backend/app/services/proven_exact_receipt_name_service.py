"""Safely reuse independently confirmed code-bearing receipt identity by exact name.

This is central product identity, NOT a synonym link or a household article
identity. No product, GTIN, receipt source, inventory or household is created
or modified. Automatic writes are initiated only by the explicit authorized
POST, never while opening or filtering Artikelbeheer.

A normalized label may be reused only if at least one *coded*, independently
confirmed receipt proves exactly ONE still-active central Catalogus product
across ALL retailers. Any conflicting or disputed evidence fails closed.
"""
from __future__ import annotations

from contextlib import suppress
import re

from fastapi import HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError

from app.services.authorization_foundation_service import write_authorization_audit
from app.services.catalog_retailer_identity_keys import (
    canonical_catalog_retailer, catalog_retailer_aliases,
)
from app.services.external_article_confirmation_service import resolve_external_article_identity
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)
from app.services.external_unlinked_articles_service import list_all_external_articles

MAX_EXACT_NAME_BATCH = 50


def _key(store, label, number):
    retailer = canonical_catalog_retailer(store)
    name = normalize_external_link_receipt_text(label)
    code = normalize_external_link_article_code(number)
    if (not retailer or not re.fullmatch(r"[a-z0-9-]{1,80}", retailer)
            or not name or len(name) > 200 or len(code) > 100):
        return None
    return retailer, name, code


def _proven_name_targets(rows):
    """Return (proofs, disputed), requiring a real coded receipt for each name.

    The overview is the existing central identity authority. Names and shop
    text alone are never evidence. Distinct known product IDs, pending saved
    barcodes or disputed claims close the entire name, even across retailers.
    """
    ids, witnesses, disputed = {}, {}, set()
    for row in rows:
        key = _key(row.get("retailer_code"), row.get("receipt_line_text"),
                   row.get("receipt_article_number"))
        if not key or not key[2]:
            continue
        _, name, code = key
        status = str(row.get("identity_status") or "")
        if status in {"saved_only", "review"}:
            disputed.add(name)
            continue
        if status != "catalog_linked":
            if row.get("manual_barcode"):
                disputed.add(name)
            continue
        explicit = str(row.get("identity_catalog_product_id") or "").strip()
        central = str(row.get("catalog_product_id") or "").strip()
        if ((explicit and central and explicit != central) or
                not (explicit or central) or
                (row.get("article_code") and row.get("manual_barcode") and
                 str(row["article_code"]) != str(row["manual_barcode"]))):
            disputed.add(name)
            continue
        product_id = explicit or central
        ids.setdefault(name, set()).add(product_id)
        witnesses.setdefault(name, []).append({
            "retailer": key[0], "receipt_article_number": code,
            "product_id": product_id,
        })
    return {
        name: {"product_id": next(iter(product_ids)),
               "witness": sorted(witnesses[name], key=lambda w: (
                   w["retailer"], w["receipt_article_number"]))[0]}
        for name, product_ids in ids.items()
        if len(product_ids) == 1 and name not in disputed
    }, disputed | {name for name, product_ids in ids.items()
                   if len(product_ids) > 1}


def _candidate_plan(rows):
    proofs, disputed = _proven_name_targets(rows)
    candidates, blocked, without_proof = [], 0, 0
    seen = set()
    for row in rows:
        key = _key(row.get("retailer_code"), row.get("receipt_line_text"),
                   row.get("receipt_article_number"))
        if not key or key[2] or key in seen:
            continue
        if row.get("identity_status") != "not_identified":
            continue
        if (row.get("article_code") or row.get("manual_barcode") or
                row.get("identity_catalog_product_id") or
                row.get("catalog_product_id")):
            blocked += 1
            continue
        seen.add(key)
        if key[1] in disputed:
            blocked += 1
            continue
        proof = proofs.get(key[1])
        if not proof:
            without_proof += 1
            continue
        candidates.append({
            "receipt_item_id": str(row["id"]),
            "source_key": key,
            "product_id": proof["product_id"],
            "witness": proof["witness"],
        })
    candidates.sort(key=lambda c: c["source_key"])
    return candidates, blocked, without_proof


def _ensure_active_product(conn, product_id):
    return conn.execute(text("""
        SELECT id FROM global_products WHERE id=:product_id AND status='active'
        LIMIT 1
    """), {"product_id": product_id}).first() is not None


def _persist_exact_name_match(conn, *, source_key, product_id, witness, actor_id):
    """One idempotent, guarded central tuple insert inside the caller's savepoint."""
    retailer, name, code = source_key
    if code:
        raise ValueError("Deze route verwerkt uitsluitend bonartikelen zonder winkelartikelnummer.")
    if not _ensure_active_product(conn, product_id):
        raise ValueError("Het bewezen Catalogusproduct is niet meer actief.")
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 677))"), {
        "key": "ed2-receipt:" + "|".join(source_key),
    })
    existing = conn.execute(text("""
        SELECT global_product_id, match_mode FROM ed2_receipt_family_links
        WHERE retailer_code=:retailer AND receipt_text_normalized=:name
          AND external_article_code='' FOR UPDATE
    """), {"retailer": retailer, "name": name}).mappings().first()
    if existing:
        if (str(existing["global_product_id"]) == product_id
                and existing["match_mode"] == "same_product"):
            return False
        raise ValueError("Het bonartikel heeft al een andere bevestigde Catalogusidentiteit.")

    aliases = list(catalog_retailer_aliases(retailer))
    saved = conn.execute(text("""
        SELECT 1 FROM ed2_manual_barcodes
        WHERE retailer_code IN :aliases AND receipt_text_normalized=:name
          AND COALESCE(TRIM(external_article_code), '')=''
        LIMIT 1
    """).bindparams(bindparam("aliases", expanding=True)), {
        "aliases": aliases, "name": name,
    }).first()
    if saved:
        raise ValueError("Het bonartikel heeft al een bewaarde barcode.")
    central = conn.execute(text("""
        SELECT 1 FROM external_article_product_links
        WHERE retailer_code IN :aliases AND receipt_text_normalized=:name
          AND COALESCE(TRIM(external_article_code), '')=''
          AND status IN ('confirmed', 'classification_pending')
        LIMIT 1
    """).bindparams(bindparam("aliases", expanding=True)), {
        "aliases": aliases, "name": name,
    }).first()
    if central:
        raise ValueError("Het bonartikel heeft al een bestaande of wachtende koppeling.")

    conn.execute(text("""
        INSERT INTO ed2_receipt_family_links
          (retailer_code, receipt_text_normalized, external_article_code,
           global_product_id, match_mode, confirmed_by, confirmed_at)
        VALUES (:retailer, :name, '', :product, 'same_product', :actor,
                CURRENT_TIMESTAMP)
    """), {
        "retailer": retailer, "name": name,
        "product": product_id, "actor": actor_id,
    })
    write_authorization_audit(
        conn, actor_user_id=actor_id, actor_type="platform_user",
        action="catalog.ed2.exact_name_without_code.confirmed",
        object_type="ed2_receipt_family_link",
        object_id="|".join(source_key),
        old_value=None,
        new_value={
            "global_product_id": product_id, "match_mode": "same_product",
            "witness_store": witness["retailer"],
            "witness_article_number": witness["receipt_article_number"],
        },
        reason="automatic_unique_confirmed_coded_receipt_name_v1",
    )
    return True


def automatically_match_proven_exact_names(conn, *, actor_id):
    """One controlled PostgreSQL batch, max 50 matches; no GET-time mutation."""
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise ValueError("Automatische centrale matching vereist PostgreSQL.")
    if not actor_id:
        raise ValueError("Een geautoriseerde gebruiker ontbreekt.")
    # Uses the same global central-identity write lock as curated-family writes.
    conn.execute(text("SELECT pg_advisory_xact_lock(639643644)"))
    candidates, ambiguous, no_proof = _candidate_plan(
        list_all_external_articles(conn=conn)["items"])
    linked, conflicts = 0, 0
    for candidate in candidates[:MAX_EXACT_NAME_BATCH]:
        try:
            with conn.begin_nested():
                source = resolve_external_article_identity(conn, candidate["receipt_item_id"])
                if _key(source.get("retailer_code"), source.get("receipt_text"),
                        source.get("external_article_code")) != candidate["source_key"]:
                    raise ValueError("De bonartikelbron is gewijzigd.")
                # Other authorities can update coded proof. Rebuild the full
                # central projection in this savepoint just before the write.
                current, _, _ = _candidate_plan(
                    list_all_external_articles(conn=conn)["items"])
                verified = next((row for row in current
                    if row["source_key"] == candidate["source_key"]
                    and row["receipt_item_id"] == candidate["receipt_item_id"]), None)
                if (not verified or
                        verified["product_id"] != candidate["product_id"] or
                        verified["witness"] != candidate["witness"]):
                    raise ValueError("De unieke bewijsbron is veranderd.")
                if _persist_exact_name_match(
                    conn, source_key=candidate["source_key"],
                    product_id=candidate["product_id"],
                    witness=candidate["witness"], actor_id=actor_id,
                ):
                    linked += 1
        except (ValueError, HTTPException, IntegrityError):
            conflicts += 1
    return {
        "ok": True, "status": "applied",
        "linked": linked, "linked_without_article_number": linked,
        "synonyms_created": 0, "barcode_written": False,
        "blocked": ambiguous + conflicts,
        "without_proof": no_proof,
        "unprocessed": max(0, len(candidates) - linked) + ambiguous + no_proof,
        "limit_reached": len(candidates) > MAX_EXACT_NAME_BATCH,
        "requires_review": bool(conflicts or ambiguous or no_proof or
                                len(candidates) > MAX_EXACT_NAME_BATCH),
    }
