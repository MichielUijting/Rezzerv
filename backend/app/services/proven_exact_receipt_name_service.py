"""Safely reuse independently confirmed receipt identity by exact name.

This is central product identity, NOT a synonym link or a household article
identity. No product, GTIN, receipt source, inventory or household is created
or modified. Automatic writes are initiated only by the explicit authorized
POST, never while opening or filtering Artikelbeheer.

A normalized label may be reused when an independently confirmed retailer
article number OR a verified Catalogus-linked GTIN proves exactly ONE active
central Catalogus product
across ALL retailers. Any conflicting or disputed evidence fails closed.
"""
from __future__ import annotations

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
from app.services.gtin_validation_service import is_valid_gtin

MAX_EXACT_NAME_BATCH = 50


def _key(store, label, number):
    retailer = canonical_catalog_retailer(store)
    name = normalize_external_link_receipt_text(label)
    code = normalize_external_link_article_code(number)
    if (not retailer or not re.fullmatch(r"[a-z0-9-]{1,80}", retailer)
            or not name or len(name) > 200 or len(code) > 100):
        return None
    return retailer, name, code


# Receipt names are compared store-neutrally ONLY for this explicitly
# authorized central matching route. The original name and store+number
# tuple remain untouched in all persisted identity records.
#
# Only remove an actual retailer's own name at the BEGINNING or END of
# its receipt line. Do not remove arbitrary interior words or another
# retailer's name (e.g. an AH-labelled brand sold at Lidl).
_RETAILER_LABEL_MARKERS = {
    "ah": (("albert", "heijn"), ("ah",)),
    "jumbo": (("jumbo",),),
    "lidl": (("lidl",),),
    "aldi": (("aldi",),),
    "plus": (("plus",),),
    "picnic": (("picnic",),),
    "dirk": (("dirk",),),
    "hoogvliet": (("hoogvliet",),),
    "vomar": (("vomar",),),
    "dekamarkt": (("dekamarkt",),),
    "spar": (("spar",),),
    "coop": (("coop",),),
    "boni": (("boni",),),
    "nettorama": (("nettorama",),),
}


def _matching_name(retailer, receipt_name):
    """Remove ONLY the receipt's own retailer name at either outer edge.

    This is a transient evidence-comparison key, never a barcode, Catalogus
    ID, receipt source, or stored retailer/name/number identity.
    """
    words = normalize_external_link_receipt_text(receipt_name).split()
    markers = _RETAILER_LABEL_MARKERS.get(canonical_catalog_retailer(retailer), ())
    while words:
        for marker in markers:
            length = len(marker)
            if len(words) <= length:
                continue  # Do not reduce a name to nothing.
            if tuple(words[:length]) == marker:
                words = words[length:]
                break
            if tuple(words[-length:]) == marker:
                words = words[:-length]
                break
        else:
            break
    return " ".join(words)


def _confirmed_catalog_barcode(row):
    """One verified barcode for this receipt identity, never inferred by name.

    A merely saved (not Catalogus-confirmed) barcode is insufficient.
    Barcode-free family links do not inherit the central product's GTIN.
    """
    if (str(row.get("identity_status") or "") != "catalog_linked" or
            row.get("barcode_free_catalog_link")):
        return ""
    saved = str(row.get("manual_barcode") or "").strip()
    linked = str(row.get("article_code") or "").strip()
    if saved and linked and saved != linked:
        return ""  # Existing conflict guard rejects inconsistent source.
    for barcode in (saved, linked):
        if barcode and is_valid_gtin(barcode):
            return barcode
    return ""


def _proven_name_targets(rows):
    """Map each exact bonnaam to one independently proven Catalogus-ID.

    Different article numbers (even in the same retailer) are intentionally
    allowed. A code-free receipt with a verified Catalogus-linked GTIN
    can also independently prove its product. Saved-only barcodes, disputed
    and competing identity claims still block the complete name group.
    A name alone never creates a product identity.
    """
    ids, witnesses, disputed = {}, {}, set()
    for row in rows:
        key = _key(row.get("retailer_code"), row.get("receipt_line_text"),
                   row.get("receipt_article_number"))
        if not key:
            continue
        retailer, original_name, code = key
        name = _matching_name(retailer, original_name)
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
        confirmed_barcode = _confirmed_catalog_barcode(row)
        if code or confirmed_barcode:
            witnesses.setdefault(name, []).append({
                "retailer": key[0], "receipt_article_number": code,
                "confirmed_barcode": confirmed_barcode,
                "product_id": product_id,
            })
    return {
        name: {"product_id": next(iter(product_ids)),
               "witness": sorted(witnesses[name], key=lambda w: (
                   not bool(w["receipt_article_number"]), w["retailer"],
                   w["receipt_article_number"], w["confirmed_barcode"]))[0]}
        for name, product_ids in ids.items()
        if len(product_ids) == 1 and name not in disputed
        and witnesses.get(name)
    }, disputed | {name for name, product_ids in ids.items()
                   if len(product_ids) > 1}



def confirmed_product_variant_review_reasons(rows):
    """Explain multiple distinct confirmed Catalogus identities per neutral name.

    Several barcodes attached to ONE Catalogusproduct are not a conflict.
    This is read-only presentation data, never an identity or write decision.
    """
    products_by_name = {}
    for row in rows:
        if row.get("identity_status") != "catalog_linked":
            continue
        key = _key(row.get("retailer_code"), row.get("receipt_line_text"),
                   row.get("receipt_article_number"))
        if not key:
            continue
        explicit = str(row.get("identity_catalog_product_id") or "").strip()
        central = str(row.get("catalog_product_id") or "").strip()
        if (explicit and central and explicit != central) or not (explicit or central):
            continue
        product = explicit or central
        name = _matching_name(key[0], key[1])
        barcode = _confirmed_catalog_barcode(row)
        product_name = str(row.get("catalog_product_name") or "").strip()
        label = product_name or "Catalogusproduct"
        if barcode:
            label += " (barcode " + barcode + ")"
        products_by_name.setdefault(name, {}).setdefault(product, set()).add(label)

    reasons_by_name = {}
    for name, products in products_by_name.items():
        if len(products) < 2:
            continue
        examples = sorted(sorted(labels)[0] for labels in products.values())
        details = "; ".join(examples[:3])
        if len(examples) > 3:
            details += "; en " + str(len(examples) - 3) + " andere"
        reasons_by_name[name] = (
            "Niet automatisch gematcht: deze bonnaam hoort bij "
            + str(len(products)) + " verschillende bevestigde "
            "Catalogusproducten of uitvoeringen"
            + (": " + details if details else "")
            + ". Kies het juiste product; Inhuis kiest geen willekeurige barcode."
        )
    result = {}
    for row in rows:
        if row.get("identity_status") != "not_identified":
            continue
        key = _key(row.get("retailer_code"), row.get("receipt_line_text"),
                   row.get("receipt_article_number"))
        if not key:
            continue
        reason = reasons_by_name.get(_matching_name(key[0], key[1]))
        if reason:
            result[str(row.get("id") or "")] = reason
    return result

def _candidate_plan(rows, aliases=None):
    """All unresolved shop+label+number tuples may reuse a unique proven ID.

    A PO-approved alias is directed from one exact receipt name to another
    exact name, and can only apply if that target still has the original
    unique independently proven coded identity. No transitive alias guessing.
    """
    proofs, disputed = _proven_name_targets(rows)
    aliases = aliases or {}
    candidates, blocked, without_proof = [], 0, 0
    seen = set()
    for row in rows:
        key = _key(row.get("retailer_code"), row.get("receipt_line_text"),
                   row.get("receipt_article_number"))
        if not key or key in seen or row.get("identity_status") != "not_identified":
            continue
        if (row.get("article_code") or row.get("manual_barcode") or
                row.get("identity_catalog_product_id") or
                row.get("catalog_product_id")):
            blocked += 1
            continue
        seen.add(key)
        comparable_name = _matching_name(key[0], key[1])
        if comparable_name in disputed:
            blocked += 1
            continue
        proof = proofs.get(comparable_name)
        alias = aliases.get(comparable_name)
        if alias:
            target = proofs.get(alias["target_name"])
            # An explicit alias is not an override of old central claims.
            if (alias["target_name"] in disputed or not target or
                    target["product_id"] != str(alias["product_id"]) or
                    (proof and proof["product_id"] != target["product_id"])):
                blocked += 1
                continue
            proof = target
        if not proof:
            without_proof += 1
            continue
        candidates.append({
            "receipt_item_id": str(row["id"]),
            "source_key": key,
            "product_id": proof["product_id"],
            "witness": proof["witness"],
            "proof_name": alias["target_name"] if alias else comparable_name,
        })
    candidates.sort(key=lambda c: c["source_key"])
    return candidates, blocked, without_proof


def load_confirmed_bonnaam_aliases(conn):
    """Persisted central PO-reviewed receipt-name equivalences, no GET writes."""
    return {
        str(row["alias_name_normalized"]): {
            "target_name": str(row["target_name_normalized"]),
            "product_id": str(row["global_product_id"]),
        }
        for row in conn.execute(text("""
            SELECT alias_name_normalized, target_name_normalized, global_product_id
              FROM ed2_receipt_name_aliases
        """)).mappings()
    }


def confirm_bonnaam_alias(conn, *, alias_name, target_name, actor_id):
    """Confirm ONE globally applicable name alias, never overwrite old proof.

    The authorized operator explicitly declares the naming equivalence. The
    target must already have exactly one independently confirmed receipt number or verified barcode
    product. Any conflicting source/product evidence requires manual review.
    """
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise ValueError("Het vastleggen van bonnaamsynoniemen vereist PostgreSQL.")
    if not actor_id:
        raise ValueError("Een geautoriseerde bevestiger ontbreekt.")
    alias = normalize_external_link_receipt_text(alias_name)
    target = normalize_external_link_receipt_text(target_name)
    if (not alias or not target or alias == target or
            len(alias) > 200 or len(target) > 200):
        raise ValueError("Kies twee verschillende volledige bonnamen.")
    conn.execute(text("SELECT pg_advisory_xact_lock(639643644)"))
    rows = list_all_external_articles(conn=conn)["items"]
    proofs, disputed = _proven_name_targets(rows)
    confirmed = proofs.get(target)
    if not confirmed or target in disputed:
        raise ValueError("De doelbonnaam heeft geen unieke bevestigde bron met winkelartikelnummer of Catalogusbarcode.")
    product_id = confirmed["product_id"]
    if not _ensure_active_product(conn, product_id):
        raise ValueError("Het bewezen Catalogusproduct is niet actief.")
    source_proof = proofs.get(alias)
    if alias in disputed or (source_proof and source_proof["product_id"] != product_id):
        raise ValueError("De gekozen bonnaam heeft al een tegenstrijdige productidentiteit.")
    aliases = load_confirmed_bonnaam_aliases(conn)
    if target in aliases:
        raise ValueError("De doelbonnaam is zelf een alias: kies een bewezen originele bonnaam.")
    existing = aliases.get(alias)
    if existing:
        if existing == {"target_name": target, "product_id": product_id}:
            return {"ok": True, "already_confirmed": True,
                    "alias_name": alias, "target_name": target,
                    "catalog_product_id": product_id}
        raise ValueError("Deze bonnaam heeft al een andere bevestigde synoniemrelatie.")
    conn.execute(text("""
        INSERT INTO ed2_receipt_name_aliases
          (alias_name_normalized, target_name_normalized, global_product_id,
           confirmed_by, confirmed_at)
        VALUES (:alias, :target, :product, :actor, CURRENT_TIMESTAMP)
    """), {"alias": alias, "target": target,
           "product": product_id, "actor": actor_id})
    write_authorization_audit(
        conn, actor_user_id=actor_id, actor_type="platform_user",
        action="catalog.ed2.receipt_name_alias.confirmed",
        object_type="ed2_receipt_name_alias", object_id=alias,
        old_value=None,
        new_value={"target_name": target, "global_product_id": product_id},
        reason="explicit_authorized_global_receipt_name_alias_v1",
    )
    return {"ok": True, "already_confirmed": False,
            "alias_name": alias, "target_name": target,
            "catalog_product_id": product_id}


def _ensure_active_product(conn, product_id):
    return conn.execute(text("""
        SELECT id FROM global_products WHERE id=:product_id AND status='active'
        LIMIT 1
    """), {"product_id": product_id}).first() is not None


def _persist_exact_name_match(conn, *, source_key, product_id, witness, actor_id):
    """Store one exact retailer+name+number tuple under the central write lock.

    Receipt item numbers are NOT GTINs. A different number is no reason to
    reject an independently proven name, but existing claims on that exact
    tuple or its store-bound number are never overwritten.
    """
    retailer, name, code = source_key
    if not _ensure_active_product(conn, product_id):
        raise ValueError("Het bewezen Catalogusproduct is niet meer actief.")
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 677))"), {
        "key": "ed2-receipt:" + "|".join(source_key),
    })
    existing = conn.execute(text("""
        SELECT global_product_id, match_mode FROM ed2_receipt_family_links
        WHERE retailer_code=:retailer AND receipt_text_normalized=:name
          AND external_article_code=:code FOR UPDATE
    """), {"retailer": retailer, "name": name, "code": code}).mappings().first()
    if existing:
        if (str(existing["global_product_id"]) == product_id
                and existing["match_mode"] == "same_product"):
            return False
        raise ValueError("Het bonartikel heeft al een andere bevestigde Catalogusidentiteit.")

    aliases = list(catalog_retailer_aliases(retailer))
    # Store-code collisions and historically saved barcodes always override
    # name-derived suggestions. Never promote a retailer number into a GTIN.
    saved = conn.execute(text("""
        SELECT 1 FROM ed2_manual_barcodes
        WHERE retailer_code IN :aliases
          AND (receipt_text_normalized=:name AND
                COALESCE(TRIM(external_article_code), '')=:code
               OR (:has_code AND external_article_code=:code))
        LIMIT 1
    """).bindparams(bindparam("aliases", expanding=True)), {
        "aliases": aliases, "name": name, "code": code,
        "has_code": bool(code),
    }).first()
    if saved:
        raise ValueError("Het bonartikel heeft al een bewaarde barcode.")
    central = conn.execute(text("""
        SELECT 1 FROM external_article_product_links
        WHERE retailer_code IN :aliases
          AND status IN ('confirmed', 'classification_pending')
          AND (receipt_text_normalized=:name AND
                COALESCE(TRIM(external_article_code), '')=:code
               OR (:has_code AND external_article_code=:code))
        LIMIT 1
    """).bindparams(bindparam("aliases", expanding=True)), {
        "aliases": aliases, "name": name, "code": code,
        "has_code": bool(code),
    }).first()
    if central:
        raise ValueError("Het bonartikel heeft al een bestaande of wachtende koppeling.")
    if code:
        conflicting_number = conn.execute(text("""
            SELECT 1 FROM ed2_receipt_family_links
            WHERE retailer_code=:retailer AND external_article_code=:code
              AND global_product_id<>:product LIMIT 1
        """), {"retailer": retailer, "code": code, "product": product_id}).first()
        if conflicting_number:
            raise ValueError("Dit winkelartikelnummer verwijst al naar een ander product.")

    conn.execute(text("""
        INSERT INTO ed2_receipt_family_links
          (retailer_code, receipt_text_normalized, external_article_code,
           global_product_id, match_mode, confirmed_by, confirmed_at)
        VALUES (:retailer, :name, :code, :product, 'same_product', :actor,
                CURRENT_TIMESTAMP)
    """), {
        "retailer": retailer, "name": name, "code": code,
        "product": product_id, "actor": actor_id,
    })
    write_authorization_audit(
        conn, actor_user_id=actor_id, actor_type="platform_user",
        action="catalog.ed2.proven_receipt_name.confirmed",
        object_type="ed2_receipt_family_link",
        object_id="|".join(source_key),
        old_value=None,
        new_value={
            "global_product_id": product_id, "mode": "same_product",
            "receipt_article_number": code,
            "witness_store": witness["retailer"],
            "witness_article_number": witness["receipt_article_number"],
            "witness_confirmed_barcode": witness.get("confirmed_barcode") or "",
        },
        reason="automatic_confirmed_receipt_name_v2",
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
    # The complete ED2 projection is expensive: real local diagnostics
    # observed 15-17 seconds for 1,175 unique receipt identities. Never
    # rebuild it once for EACH candidate (previously up to 51 scans).
    # Instead collect the proof once and re-check the entire projection ONCE
    # before the first write under the same serialized batch transaction.
    # Per-row raw identity and exact-tuple database guards still run inside
    # independent savepoints and block stale or conflicting records.
    candidates, ambiguous, no_proof = _candidate_plan(
        list_all_external_articles(conn=conn)["items"],
        load_confirmed_bonnaam_aliases(conn))
    selected = candidates[:MAX_EXACT_NAME_BATCH]
    verified_by_key = {}
    if selected:
        refreshed, _, _ = _candidate_plan(
            list_all_external_articles(conn=conn)["items"],
            load_confirmed_bonnaam_aliases(conn))
        verified_by_key = {
            (row["source_key"], row["receipt_item_id"]): row
            for row in refreshed
        }
    linked, conflicts, codefree_linked = 0, 0, 0
    for candidate in selected:
        try:
            current = verified_by_key.get(
                (candidate["source_key"], candidate["receipt_item_id"]))
            if (not current or
                    current["product_id"] != candidate["product_id"] or
                    current["witness"] != candidate["witness"] or
                    current["proof_name"] != candidate["proof_name"]):
                raise ValueError("De unieke bewijsbron is veranderd.")
            with conn.begin_nested():
                source = resolve_external_article_identity(conn, candidate["receipt_item_id"])
                if _key(source.get("retailer_code"), source.get("receipt_text"),
                        source.get("external_article_code")) != candidate["source_key"]:
                    raise ValueError("De bonartikelbron is gewijzigd.")
                if _persist_exact_name_match(
                    conn, source_key=candidate["source_key"],
                    product_id=candidate["product_id"],
                    witness=candidate["witness"], actor_id=actor_id,
                ):
                    linked += 1
                    if not candidate["source_key"][2]:
                        codefree_linked += 1
        except (ValueError, HTTPException, IntegrityError):
            conflicts += 1
    return {
        "ok": True, "status": "applied",
        "linked": linked, "linked_without_article_number": codefree_linked,
        "synonyms_created": 0, "barcode_written": False,
        "blocked": ambiguous + conflicts,
        "without_proof": no_proof,
        "unprocessed": max(0, len(candidates) - linked) + ambiguous + no_proof,
        "limit_reached": len(candidates) > MAX_EXACT_NAME_BATCH,
        "requires_review": bool(conflicts or ambiguous or no_proof or
                                len(candidates) > MAX_EXACT_NAME_BATCH),
    }
