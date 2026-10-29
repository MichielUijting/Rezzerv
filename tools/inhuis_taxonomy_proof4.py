"""Inhuis taxonomy-first proof 4: read-only quality and group hypotheses.

Run in the already running backend, using the existing tools read-only mount:
    python -m tools.inhuis_taxonomy_proof4

Never assigns an official GS1 Brick, changes a product type or touches stock.
There is no external network call, AI dependency or paid product-data source.
"""

import collections
import datetime
import json
import re
import sys
import traceback
from pathlib import Path

from sqlalchemy import text

from app.db import DATASTORE_KIND, engine
from app.services.external_unlinked_articles_service import list_all_external_articles
from app.services.gtin_validation_service import is_valid_gtin

from tools.inhuis_taxonomy_proof4_core import (
    build_brick_term_index,
    build_gpc_classes,
    build_seed_index,
    class_hypothesis,
    combined_direction,
    existing_code_warnings,
    safe,
)


def _safe_unhandled_error(error_type, error, traceback_object):
    details = "".join(traceback.format_exception(error_type, error, traceback_object))
    details = re.sub(
        r"(?i)postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]+",
        "[DATABASEVERBINDING AFGESCHERMD]", details,
    )
    details = re.sub(
        r"(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*)[^\s,'\"]+",
        r"\1\2[AFGESCHERMD]", details,
    )
    print("INHUIS - TAXONOMIEPROEF 4 - VEILIG GESTOPT", file=sys.stderr)
    print("Geen wijzigingen in de Inhuis-database uitgevoerd.", file=sys.stderr)
    print("\n".join(details.splitlines()[-30:]), file=sys.stderr)


sys.excepthook = _safe_unhandled_error


def main():
    if DATASTORE_KIND != "postgresql":
        raise RuntimeError("VEILIG GESTOPT: de bestaande backend gebruikt geen PostgreSQL")

    data = Path(__import__("app").__file__).resolve().parent / "data"
    reference_path = data / "gpc_bricks_nl.json"
    seed_path = data / "product_taxonomy_seed.json"
    if not reference_path.is_file() or not seed_path.is_file():
        raise RuntimeError("VEILIG GESTOPT: de bestaande GS1- of woordenlijstreferentie ontbreekt")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    rows = reference.get("bricks") or []
    official = {
        str(row.get("gpc_brick_code")): row for row in rows
        if re.fullmatch(r"\d{8}", str(row.get("gpc_brick_code") or ""))
    }
    if len(official) < 5000:
        raise RuntimeError("VEILIG GESTOPT: Nederlandse GS1-referentie onverwacht onvolledig")

    seed_index = build_seed_index(seed)
    classes = build_gpc_classes(reference)
    official_term_index = build_brick_term_index(reference)

    with engine.connect() as conn:
        # Server-enforced protection: write attempts in this transaction fail.
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        try:
            products = [dict(row) for row in conn.execute(text(
                "SELECT id, name, primary_gtin FROM global_products ORDER BY name, id"
            )).mappings().all()]
            memberships = conn.execute(text("""
                SELECT pgm.global_product_id, pig.gpc_brick_code AS brick_code
                  FROM product_group_memberships pgm
                  JOIN product_inventory_groups pig
                    ON pig.inventory_group_key = pgm.inventory_group_key
                 WHERE pgm.active = 1 AND pig.active = 1
                   AND pig.gpc_brick_code IS NOT NULL
            """)).mappings().all()
            assignments = conn.execute(text(
                "SELECT global_product_id, brick_code FROM global_product_gpc_bricks"
            )).mappings().all()
            overview = list_all_external_articles(conn=conn)
        finally:
            conn.rollback()

    product_codes = collections.defaultdict(set)
    invalid_codes = collections.defaultdict(set)
    for row in [*memberships, *assignments]:
        code = str(row.get("brick_code") or "")
        key = str(row.get("global_product_id") or "")
        if code in official:
            product_codes[key].add(code)
        else:
            invalid_codes[key].add(code)

    gtin_products = collections.defaultdict(set)
    for product in products:
        gtin = str(product.get("primary_gtin") or "").strip()
        if is_valid_gtin(gtin):
            gtin_products[gtin].add(str(product.get("id") or ""))

    result_rows = []
    stats = collections.defaultdict(collections.Counter)
    groups = collections.defaultdict(collections.Counter)
    source_examples = collections.defaultdict(list)

    def examine(source, name, retailer, identities, catalog_gtin, linked_status):
        direction = combined_direction(name, retailer, seed_index, official_term_index)
        codes = {code for item_id in identities for code in product_codes[item_id]}
        bad_codes = {code for item_id in identities for code in invalid_codes[item_id]}
        warnings = []
        proposal = ""
        if len(codes) > 1:
            status = "GS1_CONFLICT"
            warnings.append("Meerdere verschillende bestaande GS1-codes")
        elif bad_codes:
            status = "GS1_ONGELDIGE_REFERENTIE"
            warnings.append("Een huidige GS1-code ontbreekt in de officiële referentie")
        elif codes:
            status = "GS1_BESTAAND_NIET_BEVESTIGD"
            code = next(iter(codes))
            warnings.extend(existing_code_warnings(name, direction, official[code]))
            if warnings:
                status = "GS1_VERDACHT_CONTROLEREN"
        elif direction["conflict"]:
            status = "LOKALE_RICHTING_CONFLICT"
        elif direction["group"]:
            status = "GROEP_VOORSTEL_GEEN_BRICK"
            proposal = class_hypothesis(name, direction["group"], classes)
        else:
            status = "BEWIJS_ONTBREEKT"

        code = ",".join(sorted(codes | bad_codes))
        stats[source][status] += 1
        if direction["group"]:
            groups[source][direction["group"]] += 1
        if len(source_examples[(source, status)]) < 8:
            source_examples[(source, status)].append(safe(name, 80))
        result_rows.append((
            source, name, retailer, linked_status, status,
            direction["group"], direction["evidence"], code,
            "; ".join(warnings), proposal, catalog_gtin,
        ))

    for product in products:
        product_id = str(product.get("id") or "")
        gtin = str(product.get("primary_gtin") or "").strip()
        examine("Catalogus", safe(product.get("name"), 110), "", {product_id},
                gtin if is_valid_gtin(gtin) else "", "catalogus")

    for item in overview.get("items") or []:
        name = safe(item.get("receipt_line_text"), 110)
        gtin = str(item.get("article_code") or "").strip()
        gtin = gtin if is_valid_gtin(gtin) else ""
        examine("Bonartikelen ED2", name, safe(item.get("retailer_code"), 50),
                gtin_products.get(gtin, set()) if gtin else set(), gtin,
                safe(item.get("link_status"), 30))

    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("============================================================")
    print("INHUIS - TAXONOMIE-EERST - VERBETERDE HERKENNING - PROEF 4")
    print("============================================================")
    print("Datum:", now)
    print("Nederlandse GS1 GPC:", reference.get("publication_version"))
    print("Officiële Bricks in bestaande referentie:", len(official))
    print("Inhuis-woordenlijst:", seed.get("version"))
    print("Database: PostgreSQL, expliciete READ ONLY-transactie, ROLLBACK")
    print("Netwerk/OFF-opvragen: GEEN; geen AI, geen betaalde externe productdienst")
    print("Database-, GS1-, Artikelgroep-, Producttype-, bon- en voorraadwrites: GEEN")
    print("LET OP: lokale groep = voorstel, geen officiële GS1-classificatie")
    print("LET OP: bestaande GS1 zonder waarschuwing is nog niet inhoudelijk bewezen")
    print("LET OP: Catalogus en ED2 hebben mogelijke overlap; tel niet samen als producten")
    print()
    print("RESULTATEN")
    for source in ("Catalogus", "Bonartikelen ED2"):
        print(f"{source}: {sum(stats[source].values())} beoordeeld")
        for key in (
            "GS1_VERDACHT_CONTROLEREN", "GS1_ONGELDIGE_REFERENTIE",
            "GS1_CONFLICT", "GS1_BESTAAND_NIET_BEVESTIGD",
            "GROEP_VOORSTEL_GEEN_BRICK", "LOKALE_RICHTING_CONFLICT",
            "BEWIJS_ONTBREEKT",
        ):
            print(f"  {key}: {stats[source][key]}")
        print("  Lokale groepen (geen GS1-bewijs):")
        for category, count in groups[source].most_common():
            print(f"    {safe(category, 40)}: {count}")
    print("Bestaande ED2-koppelstatussen:", overview.get("counts") or {})
    if len(products) == 43 and len(overview.get("items") or []) == 1161:
        print("Historische proef 3 (dezelfde aantallen, maar niet per record vergeleken):")
        print("  Catalogus: 8 waarschuwingen, 5 zonder richting")
        print("  ED2: 799 zonder richting; 98 klassevoorstellen; 246 lokale richtingen")
        print("  Deze aantallen zijn GEEN gemeten nauwkeurigheid of winst.")
    else:
        print("Andere aantallen dan proef 3: geen kwantitatieve vergelijking mogelijk.")
    print()
    print("KWALITEITSWAARSCHUWINGEN / CONTROLEGROEP")
    for entry in result_rows:
        if entry[4] in {"GS1_VERDACHT_CONTROLEREN", "GS1_ONGELDIGE_REFERENTIE", "GS1_CONFLICT"}:
            print(" | ".join(safe(item, 160) for item in entry[:9]))
    print()
    print("VOORBEELDEN VOOR HANDMATIGE BEOORDELING (GEEN AUTOMATISCHE TOEKENNING)")
    for (source, status), names in sorted(source_examples.items()):
        if source == "Bonartikelen ED2":
            print(safe(status, 50), "-", ", ".join(names))
    print()
    print("ALLE ARTIKELEN - ALLEEN LEZEN")
    print("Bron | Artikel | Winkel | Koppelstatus | Beoordeling | Lokale groep (GEEN GS1) | Herkomst bewijs | Bestaande Brick | Waarschuwing | Officiële GS1-klasse ALS VOORSTEL | Catalogusbarcodes")
    for entry in result_rows:
        print(" | ".join(safe(field, 170) for field in entry))
    print()
    print("GESLAAGD: alle beschikbare artikelen met bestaande data beoordeeld, niets gewijzigd.")


if __name__ == "__main__":
    main()
