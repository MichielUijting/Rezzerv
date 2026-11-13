"""Explicit barcode-free ED2 receipt recognition for the curated fresh courgette family.

A text label is allowed to make a *read-only suggestion*; it is never
identification proof. Only the authorized operator's exact confirmed
retailer + normalized receipt + article number tuple becomes durable proof.
No fabricated GTIN, no barcode overwrites, no household or receipt updates.
"""
from __future__ import annotations

from hashlib import sha256
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import bindparam, inspect, text

from app.services.catalog_retailer_identity_keys import (
    canonical_catalog_retailer, catalog_retailer_aliases,
)
from app.services.external_article_product_link_service import (
    normalize_external_link_article_code, normalize_external_link_receipt_text,
)
from app.services.synonym_product_family_rules import approved_family
from app.services.article_synonym_service import (
    load_products, confirmed_pairs, confirm_pairs, _fingerprint,
)
from app.services.authorization_foundation_service import write_authorization_audit


def _parts(source):
    retailer = canonical_catalog_retailer(source.get("retailer_code"))
    label = normalize_external_link_receipt_text(source.get("receipt_text"))
    code = normalize_external_link_article_code(source.get("external_article_code"))
    if retailer not in {"ah", "jumbo", "lidl"} or not label or len(label) > 200 or len(code) > 100:
        raise ValueError("Een volledige, ondersteunde winkel-/bonartikelidentiteit ontbreekt.")
    return (retailer, label, code)


def _family_variant(label):
    if approved_family({"name": label}) != "verse_courgette_v1":
        return ""
    words = set(label.split())
    if words & {"geel", "gele"}:
        return "yellow"
    if words & {"bio", "biologisch", "biologische"}:
        return "organic"
    return "standard"  # ordinary/green; no hidden weight or package inference


def _matching_target(source_variant, target):
    variant = _family_variant(normalize_external_link_receipt_text(
        " ".join((str(target.get("name") or ""), str(target.get("variant") or "")))
    ))
    if not variant or not source_variant:
        return None
    if variant == source_variant:
        return "same_product"
    if source_variant in {"yellow", "organic"} and variant == "standard":
        return "synonym_variant"
    # A green/ordinary receipt cannot become a yellow/organic trade item.
    return None


def _snapshot(source, target, mode):
    return sha256(json.dumps({
        "source": _parts(source), "target": str(target["id"]),
        "name": str(target.get("name") or ""),
        "variant": str(target.get("variant") or ""),
        "barcode": str(target.get("primary_gtin") or ""),
        "mode": mode, "rule": "fresh_courgette_explicit_v1",
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def family_options(conn, source):
    retailer, label, code = _parts(source)
    variant = _family_variant(label)
    if not variant:
        return {"family": None, "options": [], "reason": "Geen geteste productfamilie; geen automatische naamherkenning."}
    products = load_products(conn)
    options = []
    for target in products:
        mode = _matching_target(variant, target)
        if mode:
            options.append({
                "product_id": target["id"], "product_name": target["name"],
                "mode": mode,
                "mode_label": "Zelfde verse courgette" if mode == "same_product"
                    else "Afzonderlijke variant als synoniem",
                "fingerprint": _snapshot(source, target, mode),
                "barcode": str(target.get("primary_gtin") or ""),
            })
    options.sort(key=lambda x: (
        x["mode"] != "same_product",
        x["product_name"].casefold(), x["product_id"]
    ))
    return {"family": "verse_courgette_v1", "options": options[:40],
            "receipt_label": label, "retailer": retailer, "article_code": code}


def _guard_preexisting_claims(conn, source):
    retailer, label, code = _parts(source)
    aliases = list(catalog_retailer_aliases(retailer))
    saved = conn.execute(text("""
        SELECT gtin FROM ed2_manual_barcodes
        WHERE retailer_code IN :aliases
          AND receipt_text_normalized = :label AND external_article_code = :code
        LIMIT 1
    """).bindparams(bindparam("aliases", expanding=True)), {
        "aliases": aliases, "label": label, "code": code,
    }).first()
    if saved:
        raise ValueError("Er is al een bewaarde barcode. Controleer eerst de barcode-identiteit.")
    if code:
        identity_filter = "external_article_code = :code"
    else:
        identity_filter = ("receipt_text_normalized = :label "
                           "AND COALESCE(TRIM(external_article_code), '') = ''")
    legacy = conn.execute(text(f"""
        SELECT DISTINCT global_product_id FROM external_article_product_links
        WHERE retailer_code IN :aliases AND status IN ('confirmed', 'classification_pending')
          AND {identity_filter}
    """).bindparams(bindparam("aliases", expanding=True)), {
        "aliases": aliases, "label": label, "code": code,
    }).scalars().all()
    if legacy:
        raise ValueError("Dit bonartikel heeft al een andere Catalogusidentiteit of classificatiewachtstand.")


def confirm_courgette_receipt(conn, *, source, receipt_item_id, target_product_id,
                             match_mode, expected_fingerprint, actor_id):
    if getattr(getattr(conn, "dialect", None), "name", None) != "postgresql":
        raise ValueError("Bevestiging van centrale bonartikelen vereist PostgreSQL.")
    if not actor_id:
        raise ValueError("Een bevoegde bevestiger ontbreekt.")
    retailer, label, code = _parts(source)
    # Serialize overlapping requests and the synonym lock before any write.
    conn.execute(text("SELECT pg_advisory_xact_lock(639643644)"))
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 677))"), {
        "key": "ed2-receipt:" + "|".join((retailer, label, code)),
    })
    # Re-resolve target from the live central Catalogus, no browser-supplied names.
    options = family_options(conn, source)["options"]
    selection = next((o for o in options
                      if o["product_id"] == target_product_id
                      and o["mode"] == match_mode
                      and o["fingerprint"] == expected_fingerprint), None)
    if selection is None:
        raise ValueError("De kandidaat of de productgegevens zijn gewijzigd. Beoordeel opnieuw.")
    existing = conn.execute(text("""
        SELECT global_product_id, match_mode FROM ed2_receipt_family_links
        WHERE retailer_code=:retailer AND receipt_text_normalized=:label
          AND external_article_code=:code FOR UPDATE
    """), {"retailer": retailer, "label": label, "code": code}).mappings().first()
    if existing:
        # An older user confirmation wins; do not overwrite it on name match.
        if (str(existing["global_product_id"]) == target_product_id
                and existing["match_mode"] == "same_product"
                and match_mode == "same_product"):
            return {"ok": True, "already_confirmed": True,
                    "global_product_id": target_product_id, "synonym_created": False,
                    "barcode_written": False}
        raise ValueError("Dit bonartikel heeft al een bevestigde Cataloguskoppeling.")
    _guard_preexisting_claims(conn, source)
    product_id = target_product_id
    synonym_created = False
    if match_mode == "synonym_variant":
        # Avoid duplicate Catalogus variants: a matching verified product must
        # be selected directly, never silently bypassed by a new row.
        source_name = " ".join(str(source.get("receipt_text") or "").split())
        other = conn.execute(text("""
            SELECT id FROM global_products WHERE status='active'
              AND LOWER(TRIM(name)) = LOWER(:name) LIMIT 1
        """), {"name": source_name}).first()
        if other:
            raise ValueError("Deze variant bestaat al in de Catalogus. Selecteer dat artikel afzonderlijk.")
        product_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO global_products (
                id, primary_gtin, name, brand, variant, category,
                size_value, size_unit, product_fingerprint, source, status,
                created_at, updated_at
            ) VALUES (:id, NULL, :name, NULL, NULL, NULL,
                      NULL, NULL, NULL, 'ed2_receipt_family_confirmed',
                      'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """), {"id": product_id, "name": source_name})
    conn.execute(text("""
        INSERT INTO ed2_receipt_family_links
            (retailer_code, receipt_text_normalized, external_article_code,
             global_product_id, match_mode, confirmed_by, confirmed_at)
        VALUES (:retailer, :label, :code, :product, :mode, :actor,
                CURRENT_TIMESTAMP)
    """), {"retailer": retailer, "label": label, "code": code,
           "product": product_id, "mode": match_mode, "actor": actor_id})
    if match_mode == "synonym_variant":
        # Reuse exact existing synonym group/transitive and classification safety.
        products = {p["id"]: p for p in load_products(conn)}
        if product_id not in products or target_product_id not in products:
            raise ValueError("De bevestigde Catalogusvariant is niet vindbaar.")
        a, b = sorted((product_id, target_product_id))
        outcome = confirm_pairs(conn, [{
            "left_product_id": a, "right_product_id": b,
            "fingerprint": _fingerprint(products[a], products[b]), "manual": True,
        }], actor_id)
        synonym_created = bool(outcome.get("linked"))
    write_authorization_audit(
        conn, actor_user_id=actor_id, actor_type="platform_user",
        action="catalog.ed2.barcode_free_courgette.confirmed",
        object_type="ed2_receipt_family_link",
        object_id="|".join((retailer, label, code)),
        old_value=None,
        new_value={"global_product_id": product_id, "mode": match_mode,
                   "synonym_reference": target_product_id if synonym_created else None},
        reason="explicit_curated_courgette_confirmation",
    )
    return {"ok": True, "already_confirmed": False, "global_product_id": product_id,
            "synonym_created": synonym_created, "barcode_written": False,
            "receipt_changes": 0, "household_changes": 0, "stock_changes": 0}
