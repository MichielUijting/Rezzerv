"""CBS classification: explicit, atomic and auditable product decisions.

No implicit OFF/GS1/Shopify-to-CBS conversion is performed. Category reference
rows must have been independently verified and loaded before confirming.
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence

from sqlalchemy import bindparam, text

from app.services.cbs_classification_authority import validate_cbs_code


class CBSDecisionError(ValueError):
    pass


class CBSConcurrentChange(CBSDecisionError):
    pass


def search_verified_categories(conn, query: str, *, limit: int = 40) -> list[dict]:
    needle = str(query or "").strip()
    if len(needle) < 2:
        return []
    limit = max(1, min(50, int(limit)))
    rows = conn.execute(text("""
        SELECT cbs_code, name_nl, parent_code, level, reference_version,
               valid_from, source_url
        FROM cbs_ecoicop_categories
        WHERE LOWER(name_nl) LIKE :needle OR cbs_code = :exact
        ORDER BY CASE WHEN cbs_code = :exact THEN 0 ELSE 1 END, level, name_nl, cbs_code
        LIMIT :limit
    """), {"needle": "%" + needle.lower().replace("%", "\\%").replace("_", "\\_") + "%",
           "exact": needle, "limit": limit}).mappings().all()
    return _enrich_verified_categories(conn, rows)

# Search helpers never change the official CBS reference or confirm classifications.
# This small, transparent dictionary maps everyday product words to independently
# verified lowest-level codes from the pinned CBS ECOICOPv2 appendix.
PRODUCT_TERMS_TO_CBS = {
    "pindakaas": "011840",  # Notenpuree, notenboter en notenpasta
}


def browse_verified_categories(conn, parent_code: str | None = None) -> list[dict]:
    """Return just the direct official children (or root categories)."""
    if parent_code is not None:
        parent_code = validate_cbs_code(parent_code)
        exists = conn.execute(text(
            "SELECT 1 FROM cbs_ecoicop_categories WHERE cbs_code = :code"
        ), {"code": parent_code}).first()
        if not exists:
            raise CBSDecisionError("De gekozen CBS-hoofdcategorie bestaat niet.")
    rows = conn.execute(text("""
        SELECT cbs_code, name_nl, parent_code, level, reference_version,
               valid_from, source_url
        FROM cbs_ecoicop_categories
        WHERE (:parent IS NULL AND parent_code IS NULL)
           OR parent_code = :parent
        ORDER BY cbs_code
    """), {"parent": parent_code}).mappings().all()
    # Reuse the same verified hierarchy and leaf calculation as search.
    return _enrich_verified_categories(conn, rows)


def _enrich_verified_categories(conn, rows) -> list[dict]:
    hierarchy = conn.execute(text("""
        SELECT cbs_code, parent_code, name_nl, reference_version
        FROM cbs_ecoicop_categories
    """)).mappings().all()
    index = {(row["reference_version"], row["cbs_code"]): row for row in hierarchy}
    parents = {(row["reference_version"], row["parent_code"])
               for row in hierarchy if row["parent_code"] is not None}
    results = []
    for result in rows:
        category = dict(result)
        key = (category["reference_version"], category["cbs_code"])
        category["lowest"] = key not in parents
        labels = []
        seen = set()
        node_key = key
        while node_key in index:
            if node_key in seen:
                raise CBSDecisionError("CBS-referentie bevat een cyclische hiërarchie.")
            seen.add(node_key)
            node = index[node_key]
            labels.append(str(node["name_nl"]))
            parent = node["parent_code"]
            if parent is None:
                break
            node_key = (category["reference_version"], parent)
        else:
            raise CBSDecisionError("CBS-referentie bevat een ontbrekende oudercategorie.")
        category["path"] = " › ".join(reversed(labels))
        results.append(category)
    return results


def suggest_verified_categories(conn, product_term: str, *, limit: int = 40) -> list[dict]:
    """Read-only, explainable candidate retrieval; never infer a confirmed link."""
    import re
    normalized = " ".join(re.findall(r"[a-z0-9]+", str(product_term or "").lower()))
    if len(normalized) < 2:
        return []
    limit = max(1, min(50, int(limit)))
    tokens = set(normalized.split())
    matched = [(term, code) for term, code in PRODUCT_TERMS_TO_CBS.items()
               if term in tokens]
    if not matched:
        return []
    codes = {code for _, code in matched}
    rows = conn.execute(text("""
        SELECT cbs_code, name_nl, parent_code, level, reference_version,
               valid_from, source_url
        FROM cbs_ecoicop_categories
        WHERE cbs_code IN :codes
        ORDER BY cbs_code LIMIT :limit
    """).bindparams(bindparam("codes", expanding=True)),
        {"codes": sorted(codes), "limit": limit}).mappings().all()
    result = _enrich_verified_categories(conn, rows)
    for category in result:
        category["suggestion_reason"] = (
            "Zoeksuggestie op basis van productwoord; controleer de betekenis zelf."
        )
    return result


def confirm_cbs_batch(conn, decisions: Sequence[Mapping], *, actor_id: str) -> dict:
    """Caller owns one transaction; any exception rolls back the whole batch."""
    if not actor_id or not str(actor_id).strip():
        raise CBSDecisionError("Bevoegde bevestiger ontbreekt.")
    if not decisions or len(decisions) > 100:
        raise CBSDecisionError("Kies 1 tot en met 100 artikelen.")
    ids = [str(item.get("global_product_id") or "").strip() for item in decisions]
    if len(set(ids)) != len(ids) or any(not i for i in ids):
        raise CBSDecisionError("Ontbrekende of dubbele artikelidentiteit.")
    prepared = []
    lock = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
    for item in sorted(decisions, key=lambda d: str(d["global_product_id"])):
        product_id = str(item["global_product_id"])
        code = validate_cbs_code(item.get("cbs_code"))
        reference_version = str(item.get("reference_version") or "").strip()
        expected_name = str(item.get("expected_product_name") or "").strip()
        version = item.get("expected_version")
        if type(version) is not int or version < 0 or not reference_version or not expected_name:
            raise CBSDecisionError("Artikelnaam, referentieversie of verwachte versie ontbreekt.")
        gp = conn.execute(text(
            "SELECT id, name, status FROM global_products WHERE id = :id" + lock
        ), {"id": product_id}).mappings().first()
        if not gp or str(gp["status"] or "").lower() == "deleted" or gp["name"] != expected_name:
            raise CBSConcurrentChange("Catalogusartikel is gewijzigd. Ververs de selectie.")
        category = conn.execute(text("""
            SELECT c.cbs_code FROM cbs_ecoicop_categories c
            WHERE c.cbs_code = :code AND c.reference_version = :reference
              AND NOT EXISTS (
                SELECT 1 FROM cbs_ecoicop_categories child
                WHERE child.parent_code = c.cbs_code
                  AND child.reference_version = c.reference_version
              )
        """), {"code": code, "reference": reference_version}).first()
        if not category:
            raise CBSDecisionError("CBS-categorie ontbreekt in de geverifieerde referentie of is geen laagste categorie.")
        current = conn.execute(text(
            "SELECT cbs_code, reference_version, version, is_active "
            "FROM global_product_cbs_classifications WHERE global_product_id = :id" + lock
        ), {"id": product_id}).mappings().first()
        current_version = int(current["version"]) if current else 0
        if current_version != version:
            raise CBSConcurrentChange("Artikelclassificatie is tussentijds gewijzigd.")
        if current and bool(current["is_active"]) and current["cbs_code"] == code and current["reference_version"] == reference_version:
            prepared.append((product_id, code, reference_version, current_version, "unchanged"))
        else:
            prepared.append((product_id, code, reference_version, current_version + 1, "insert" if not current else "update"))

    written = 0
    for product_id, code, reference_version, version, action in prepared:
        if action == "unchanged":
            continue
        params = {"id": product_id, "code": code, "reference": reference_version,
                  "version": version, "actor": str(actor_id), "source": "explicit_manual_confirmation",
                  "history_id": str(uuid.uuid4())}
        if action == "insert":
            conn.execute(text("""
                INSERT INTO global_product_cbs_classifications
                    (global_product_id, cbs_code, reference_version, version, is_active,
                     confirmed_by, confirmation_source)
                VALUES (:id, :code, :reference, :version, TRUE, :actor, :source)
            """), params)
        else:
            conn.execute(text("""
                UPDATE global_product_cbs_classifications
                SET cbs_code = :code, reference_version = :reference,
                    version = :version, is_active = TRUE,
                    confirmed_by = :actor, confirmation_source = :source,
                    confirmed_at = CURRENT_TIMESTAMP
                WHERE global_product_id = :id
            """), params)
        conn.execute(text("""
            INSERT INTO global_product_cbs_history
                (id, global_product_id, cbs_code, reference_version, version,
                 action, confirmed_by, confirmation_source)
            VALUES (:history_id, :id, :code, :reference, :version,
                    'confirmed', :actor, :source)
        """), params)
        written += 1
    return {"confirmed": written, "unchanged": len(prepared) - written}


def remove_cbs_batch(conn, decisions: Sequence[Mapping], *, actor_id: str) -> dict:
    if not actor_id or not str(actor_id).strip():
        raise CBSDecisionError("Bevoegde bevestiger ontbreekt.")
    if not decisions or len(decisions) > 100:
        raise CBSDecisionError("Kies 1 tot en met 100 artikelen.")
    ids = [str(d.get("global_product_id") or "").strip() for d in decisions]
    if len(set(ids)) != len(ids) or any(not i for i in ids):
        raise CBSDecisionError("Ontbrekende of dubbele artikelidentiteit.")
    lock = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
    prepared = []
    for item in sorted(decisions, key=lambda d: str(d["global_product_id"])):
        product_id = str(item["global_product_id"])
        version = item.get("expected_version")
        if type(version) is not int or version < 1:
            raise CBSDecisionError("Ongeldige classificatieversie.")
        gp = conn.execute(text("SELECT id, name, status FROM global_products WHERE id = :id" + lock), {"id": product_id}).mappings().first()
        if not gp or gp["name"] != item.get("expected_product_name") or str(gp["status"] or "").lower() == "deleted":
            raise CBSConcurrentChange("Catalogusartikel is gewijzigd.")
        current = conn.execute(text(
            "SELECT cbs_code, reference_version, version, is_active FROM global_product_cbs_classifications "
            "WHERE global_product_id = :id" + lock
        ), {"id": product_id}).mappings().first()
        if not current or not current["is_active"] or int(current["version"]) != version:
            raise CBSConcurrentChange("CBS-classificatie is gewijzigd. Niets verwijderd.")
        prepared.append((product_id, current["reference_version"], version + 1))
    for product_id, reference_version, version in prepared:
        params = {"id": product_id, "reference": reference_version,
                  "version": version, "actor": str(actor_id),
                  "source": "explicit_manual_removal", "history_id": str(uuid.uuid4())}
        conn.execute(text("""
            UPDATE global_product_cbs_classifications SET is_active = FALSE,
                version = :version, confirmed_by = :actor,
                confirmation_source = :source, confirmed_at = CURRENT_TIMESTAMP
            WHERE global_product_id = :id
        """), params)
        conn.execute(text("""
            INSERT INTO global_product_cbs_history
                (id, global_product_id, cbs_code, reference_version, version,
                 action, confirmed_by, confirmation_source)
            VALUES (:history_id, :id, NULL, :reference, :version,
                    'removed', :actor, :source)
        """), params)
    return {"removed": len(prepared)}
