"""InHuis proef 5: Shopify (MIT) + CBS ECOICOPv2 + beperkte OFF-toets.

In de reeds draaiende backend: python -m tools.inhuis_taxonomy_proof5
Geen schema-/server-/Git-/Artikelgroep-/Producttype- of databasewijzigingen.
"""

import collections
import datetime
import os
import re
import sys
import time
import traceback

from sqlalchemy import text

from app.db import DATASTORE_KIND, engine
from app.services.external_unlinked_articles_service import list_all_external_articles
from app.services.gtin_validation_service import is_valid_gtin
from tools.inhuis_taxonomy_proof5_core import (
    Matcher, load_references, off_evidence_tags, safe,
)


def _safe_unhandled_error(error_type, error, tb):
    details = "".join(traceback.format_exception(error_type, error, tb))
    details = re.sub(r"(?i)postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]+",
                     "[DATABASEVERBINDING AFGESCHERMD]", details)
    details = re.sub(r"(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*)[^\s,'\"]+",
                     r"\1\2[AFGESCHERMD]", details)
    print("INHUIS - PROEF 5 - VEILIG GESTOPT: geen databasewijzigingen", file=sys.stderr)
    print("\n".join(details.splitlines()[-24:]), file=sys.stderr)


sys.excepthook = _safe_unhandled_error


def _optional_off(gtins):
    """Maximaal zes publieke product-GETs, nooit zoeken of data opslaan."""
    selected = list(dict.fromkeys(gtins))[:6]
    evidence = {}
    stats = collections.Counter()
    if not selected:
        stats["geen_geldige_catalogusgtin"] += 1
        return evidence, stats
    try:
        from app.services.off_search_service import lookup_off_product_by_gtin
    except ImportError:
        stats["off_service_niet_beschikbaar"] += 1
        return evidence, stats
    os.environ["REZZERV_OFF_SEARCH_TIMEOUT_SECONDS"] = "5"
    for index, gtin in enumerate(selected):
        if index:
            time.sleep(6)
        try:
            response = lookup_off_product_by_gtin(gtin)
            if response.get("mutated") is not False:
                raise RuntimeError("OFF-aanroep is niet expliciet read-only")
            product = response.get("product") or {}
            status = safe(response.get("status"), 40)
            stats[status] += 1
            evidence[gtin] = {
                "status": status,
                "naam": safe(product.get("product_name"), 70),
                "categorie": safe(product.get("categories"), 85),
                "richting": off_evidence_tags(product.get("category_tags") or []),
            }
        except Exception:
            stats["niet_beschikbaar"] += 1
            evidence[gtin] = {"status": "niet_beschikbaar"}
    return evidence, stats


def main():
    if DATASTORE_KIND != "postgresql":
        raise RuntimeError("VEILIG GESTOPT: de bestaande InHuis-backend gebruikt geen PostgreSQL")
    shopify, cbs = load_references()
    matcher = Matcher(shopify, cbs)

    with engine.connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        try:
            products = [dict(row) for row in conn.execute(text(
                "SELECT id, name, primary_gtin FROM global_products ORDER BY name, id"
            )).mappings().all()]
            overview = list_all_external_articles(conn=conn)
        finally:
            conn.rollback()

    rows = []
    stats = collections.defaultdict(collections.Counter)
    gtins = []

    def assess(source, name, retailer, gtin, linkstatus):
        proposal = matcher.match(name, retailer)
        stats[source][proposal["status"]] += 1
        names = proposal["shopify"]
        shopify_category = " / ".join(safe(category["id"], 50) for category in names)
        shopify_paths = " || ".join(safe(category["pad"], 220) for category in names)
        eco_direct = " ; ".join(safe(r["code"] + " " + r["naam"], 110)
                                for r in proposal["cbs_letterlijk"])
        eco_derived = " ; ".join(safe(code + " " + title, 110)
                                 for code, title in proposal["cbs_vergelijking"])
        rows.append((source, name, retailer, linkstatus, proposal["status"],
                     shopify_category, shopify_paths, eco_direct,
                     eco_derived, gtin, proposal["aantal_candidates"]))

    for item in products:
        gtin = str(item.get("primary_gtin") or "").strip()
        valid_gtin = gtin if is_valid_gtin(gtin) else ""
        assess("Catalogus", safe(item.get("name"), 130), "", valid_gtin, "catalogus")
        if valid_gtin and not str(item.get("name") or "").lower().startswith("product "):
            gtins.append(valid_gtin)

    for item in overview.get("items") or []:
        gtin = str(item.get("article_code") or "").strip()
        valid_gtin = gtin if is_valid_gtin(gtin) else ""
        assess("Bonartikelen ED2", safe(item.get("receipt_line_text"), 130),
               safe(item.get("retailer_code"), 45), valid_gtin,
               safe(item.get("link_status"), 32))

    # OFF-opvragen worden expliciet gescheiden van alle DB-transacties.
    # Een OFF-resultaat is dus nooit bewijs van een GS1-code of Shopify-id.
    off_evidence, off_stats = _optional_off(gtins)
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("============================================================")
    print("INHUIS - TAXONOMIE-EERST - PROEF 5 MET SHOPIFY")
    print("============================================================")
    print("Datum:", now)
    print("Shopify: v2026-08 NL, MIT,", len(shopify["categorieen"]), "officiele categorieen")
    print("CBS: ECOICOPv2 2026,", len(cbs["codes"]), "officiele codes; bron CBS, CC BY 4.0")
    print("OFF: maximaal 6 read-only GTIN-productopvragen, ten minste 6 seconden uit elkaar")
    print("Database: PostgreSQL, SET TRANSACTION READ ONLY, rollback")
    print("Kosten / abonnements- of licentieafdrachten: GEEN")
    print("Alleen de reeds in InHuis aanwezige records, geen Shopify-product- of barcode-API")
    print("GEEN mutaties: database, GS1, Producttype, Artikelgroep, bon, voorraad en container")
    print("BELANGRIJK: Shopify/ECOICOP herkennen geen barcode zelf. Labelmatch blijft voorstel.")
    print("BELANGRIJK: een CBS-vertaalsleutel is GEEN onafhankelijke productverificatie.")
    print("BELANGRIJK: Catalogus en ED2 kunnen overlappen: geen unieke artikeltotaal-telling.")
    print("Geen GS1-externe verbinding; gebruikersbarcode-autorisatie niet uitgebreid.")
    print()
    print("AANTALLEN EN KWALITEIT – voorstellen, niet gevalideerde nauwkeurigheid")
    for source in ("Catalogus", "Bonartikelen ED2"):
        print(f"{source}: {sum(stats[source].values())} regels")
        for key in ("EXACTE_NAAM_VOORSTEL", "WOORDMATCH_CONTROLEREN",
                    "MEERDUIDIGE_SHOPIFY_CATEGORIE", "INGREDIËNTGEVAAR",
                    "BEREIDINGSVORM_ONZEKER", "HOMONIEM_CONTROLEREN",
                    "NONFOOD_CONTEXT_CONTROLEREN", "GEEN_VERANTWOORDE_MATCH"):
            count = stats[source][key]
            print(f"  {key}: {count}")
    print("ED2 huidige koppelingen (niet veranderd):", overview.get("counts") or {})
    print("OFF steekproef: ", dict(off_stats), "; totaal aangevraagd:", len(off_evidence))
    print()
    print("OFF STEEKPROEF – UITSLUITEND VALIDATIE VAN BARCODEBEWIJS")
    for gtin, response in off_evidence.items():
        print(" | ".join(safe(v, 110) for v in (
            gtin, response.get("status"), response.get("naam"),
            response.get("categorie"), response.get("richting"))))
    print()
    print("ALLE REGELS, ZONDER DATABASEWIJZIGINGEN")
    print("Bron | Artikel | Winkel | Bestaande linkstatus | Voorstelstatus | "
          "Shopify-ID | SHOPIFY HIERARCHIE (VOORSTEL) | CBS letterlijke labelmatch | "
          "CBS verwantschap (geen productbewijs) | Bestaande GTIN | Aantal Shopify-labelmatches")
    for record in rows:
        print(" | ".join(safe(value, 300) for value in record))
    print()
    print("AFGEROND: alleen voorstellen, geen gewijzigde gegevens. Handmatige kwaliteitscheck verplicht.")


if __name__ == "__main__":
    main()
