"""Read-only snapshot of central Catalogus classifications for external review.

Exports explicit product IDs, verified classifications and confirmed central
relations only. Never reads private household, inventory or receipt history.
The archive format is versioned so a later importer can validate immutable IDs.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import text

FORMAT_VERSION = "inhuis-catalogus-classificatie-v1"

PRODUCT_FIELDS = (
    "product_id", "name", "brand", "variant", "category", "primary_gtin",
    "size_value", "size_unit", "source", "status", "gpc_brick_code",
    "gpc_brick_name_nl", "gpc_class_name_nl", "gpc_family_name_nl",
    "gpc_source", "cbs_code", "cbs_name_nl", "cbs_reference_version",
    "cbs_source", "cbs_version", "snapshot_sha256", "proposed_gpc_brick_code",
    "proposed_cbs_code", "proposal_explanation",
)
MATCH_FIELDS = ("product_id", "source", "retailer_code", "receipt_name", "receipt_article_number", "match_mode")
SYNONYM_FIELDS = ("left_product_id", "left_name", "right_product_id", "right_name")
GPC_FIELDS = ("brick_code", "brick_name_nl", "class_name_nl", "family_name_nl", "source_version")
CBS_FIELDS = ("cbs_code", "name_nl", "parent_code", "level", "reference_version", "is_leaf", "source_url")


def _csv_bytes(fields, records):
    target = io.StringIO(newline="")
    writer = csv.DictWriter(target, fieldnames=fields, delimiter=";", quoting=csv.QUOTE_ALL,
                            lineterminator="\r\n", extrasaction="ignore")
    writer.writeheader()
    for record in records:
        safe = {}
        for field in fields:
            value = str(record.get(field) if record.get(field) is not None else "")
            # Excel formula-injection protection for all external names/labels.
            if re.match(r"^\s*[=+@\-]", value):
                value = "'" + value
            safe[field] = value
        writer.writerow(safe)
    return ("\ufeff" + target.getvalue()).encode("utf-8")


def _read(conn, sql):
    return [dict(row) for row in conn.execute(text(sql)).mappings()]


def build_catalog_classification_export(conn) -> bytes:
    """Build one complete snapshot; caller owns the read-only transaction."""
    products = _read(conn, """
        SELECT gp.id AS product_id, gp.name, gp.brand, gp.variant, gp.category,
               gp.primary_gtin, gp.size_value, gp.size_unit, gp.source, gp.status,
               g.brick_code AS gpc_brick_code,
               gr.gpc_brick_name AS gpc_brick_name_nl,
               gr.gpc_class_name AS gpc_class_name_nl,
               gr.gpc_family_name AS gpc_family_name_nl,
               g.assignment_source AS gpc_source,
               CASE WHEN cc.is_active THEN cc.cbs_code ELSE NULL END AS cbs_code,
               CASE WHEN cc.is_active THEN cr.name_nl ELSE NULL END AS cbs_name_nl,
               CASE WHEN cc.is_active THEN cc.reference_version ELSE NULL END AS cbs_reference_version,
               CASE WHEN cc.is_active THEN cc.confirmation_source ELSE NULL END AS cbs_source,
               CASE WHEN cc.is_active THEN cc.version ELSE NULL END AS cbs_version
          FROM global_products gp
          LEFT JOIN global_product_gpc_bricks g ON g.global_product_id = gp.id
          LEFT JOIN gpc_product_groups gr ON gr.gpc_brick_code = g.brick_code
               AND LOWER(COALESCE(gr.language_code, '')) = 'nl'
          LEFT JOIN global_product_cbs_classifications cc ON cc.global_product_id = gp.id
          LEFT JOIN cbs_ecoicop_categories cr ON cr.cbs_code = cc.cbs_code
               AND cr.reference_version = cc.reference_version
         WHERE LOWER(COALESCE(gp.status, '')) <> 'deleted'
         ORDER BY LOWER(gp.name), gp.id
    """)
    identities = set()
    for product in products:
        product_id = str(product["product_id"] or "")
        if not product_id or product_id in identities:
            raise ValueError("Catalogusexport: ontbrekende of dubbele productidentiteit.")
        identities.add(product_id)
        identity_fields = {k: str(product.get(k) if product.get(k) is not None else "")
                           for k in PRODUCT_FIELDS if k not in {
                               "snapshot_sha256", "proposed_gpc_brick_code",
                               "proposed_cbs_code", "proposal_explanation"}}
        product["snapshot_sha256"] = sha256(json.dumps(
            identity_fields, sort_keys=True, ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        product["proposed_gpc_brick_code"] = ""
        product["proposed_cbs_code"] = ""
        product["proposal_explanation"] = ""

    matches = _read(conn, """
        SELECT l.global_product_id AS product_id, 'external_article_product_links' AS source,
               l.retailer_code, l.receipt_text_normalized AS receipt_name,
               l.external_article_code AS receipt_article_number, '' AS match_mode
          FROM external_article_product_links l
          JOIN global_products gp ON gp.id = l.global_product_id
         WHERE l.status = 'confirmed'
           AND LOWER(COALESCE(gp.status, '')) <> 'deleted'
         ORDER BY l.global_product_id, l.retailer_code,
                  l.receipt_text_normalized, l.external_article_code
    """)
    # This source is optional only on historical installations predating it.
    # Its existence is checked explicitly, not guessed from missing data.
    from sqlalchemy import inspect
    if inspect(conn).has_table("ed2_receipt_family_links"):
        matches.extend(_read(conn, """
            SELECT f.global_product_id AS product_id, 'ed2_receipt_family_links' AS source,
                   f.retailer_code, f.receipt_text_normalized AS receipt_name,
                   f.external_article_code AS receipt_article_number, f.match_mode
              FROM ed2_receipt_family_links f
              JOIN global_products gp ON gp.id = f.global_product_id
             WHERE TRIM(COALESCE(f.confirmed_by, '')) <> ''
               AND LOWER(COALESCE(gp.status, '')) <> 'deleted'
             ORDER BY f.global_product_id, f.retailer_code,
                      f.receipt_text_normalized, f.external_article_code
        """))
    matches.sort(key=lambda row: tuple(str(row.get(field) or "") for field in MATCH_FIELDS))

    synonyms = _read(conn, """
        SELECT s.left_product_id, gp1.name AS left_name,
               s.right_product_id, gp2.name AS right_name
          FROM article_synonym_links s
          JOIN global_products gp1 ON gp1.id = s.left_product_id
          JOIN global_products gp2 ON gp2.id = s.right_product_id
         WHERE LOWER(COALESCE(gp1.status, '')) <> 'deleted'
           AND LOWER(COALESCE(gp2.status, '')) <> 'deleted'
         ORDER BY s.left_product_id, s.right_product_id
    """)
    gpc_ref = _read(conn, """
        SELECT gpc_brick_code AS brick_code, gpc_brick_name AS brick_name_nl,
               gpc_class_name AS class_name_nl, gpc_family_name AS family_name_nl,
               source_version
          FROM gpc_product_groups
         WHERE LOWER(COALESCE(language_code, '')) = 'nl'
           AND COALESCE(active, TRUE) = TRUE
         ORDER BY gpc_brick_code
    """)
    cbs_ref = _read(conn, """
        SELECT c.cbs_code, c.name_nl, c.parent_code, c.level,
               c.reference_version,
               CASE WHEN EXISTS (
                   SELECT 1 FROM cbs_ecoicop_categories child
                    WHERE child.parent_code = c.cbs_code
                      AND child.reference_version = c.reference_version
               ) THEN 'nee' ELSE 'ja' END AS is_leaf,
               c.source_url
          FROM cbs_ecoicop_categories c
         ORDER BY c.reference_version, c.cbs_code
    """)
    stamps = datetime.now(timezone.utc).isoformat()
    manifest = {
        "format_version": FORMAT_VERSION, "created_utc": stamps,
        "scope": "central_catalog_non_deleted", "read_only": True,
        "source_of_truth": "global_products.id",
        "counts": {"products": len(products), "confirmed_matches": len(matches),
                   "confirmed_synonym_links": len(synonyms),
                   "official_gpc_bricks_nl": len(gpc_ref),
                   "official_cbs_categories": len(cbs_ref)},
        "no_household_receipt_or_stock_data": True,
        "future_import_supported": False,
    }
    notes = """INHUIS - CATALOGUSCLASSIFICATIEEXPORT
Formaat: inhuis-catalogus-classificatie-v1 (alleen lezen; géén importfunctie).
Upload het volledige ZIP-bestand in ChatGPT voor classificatievoorstellen.
catalogus.csv bevat alle niet-verwijderde Catalogusartikelen (ook zonder barcode),
de bestaande GPC/CBS-indelingen, hun bronnen en een identiteitssnapshot per ID.
De drie kolommen proposed_* / proposal_explanation zijn leeg en uitsluitend
voor latere externe voorstellen. Er is nog geen import- of goedkeuractie.
bevestigde_matches.csv bevat alleen centraal bevestigde winkel/bonartikelmatches.
bevestigde_synoniemen.csv bevat uitsluitend expliciet bevestigde productparen.
gpc_referentie_nl.csv en cbs_referentie.csv bevatten de aanwezige officiële
codetabellen. Gebruik voor CBS uitsluitend de eindcategorieën (is_leaf=ja).
Codes/GTIN/ID zijn tekstwaarden. Open CSV's zo nodig via 'Importeer als tekst'
in Excel om voorloopnullen te behouden. Geen privébonnen/voorraad/huishoudgegevens.
Classificatie op basis van één naam of een onbevestigd synoniem is niet bewezen.
Nieuwe classificatievoorstellen zijn nog geen geldige toekenningen.
"""
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for name, fields, records in (
            ("catalogus.csv", PRODUCT_FIELDS, products),
            ("bevestigde_matches.csv", MATCH_FIELDS, matches),
            ("bevestigde_synoniemen.csv", SYNONYM_FIELDS, synonyms),
            ("gpc_referentie_nl.csv", GPC_FIELDS, gpc_ref),
            ("cbs_referentie.csv", CBS_FIELDS, cbs_ref),
        ):
            archive.writestr(name, _csv_bytes(fields, records))
        archive.writestr("manifest.json", json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
        archive.writestr("LEESMIJ.txt", notes.encode("utf-8"))
    return output.getvalue()
