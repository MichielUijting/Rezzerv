"""Proef 6: uitsluitend bestaande gecodeerde *centrale Catalogusartikelen*.

Uitvoeren in reeds draaiende backend: python -u -m tools.inhuis_taxonomy_proof6
Geen ED2, geen data-mutaties, geen lokale productcode naar OFF. De OFF-opvragen
volgen pas na het rollbacken van een expliciete PostgreSQL-read-only transactie.
"""

import collections
import datetime
import re
import sys
import time
import traceback

from sqlalchemy import text

from app.db import DATASTORE_KIND, engine
from app.services.gtin_validation_service import is_valid_gtin
from tools.inhuis_taxonomy_proof5_core import safe
from tools.inhuis_taxonomy_proof6_core import classify_off_product, load_indexes


def _safe_error(error_type, error, tb):
    report = "".join(traceback.format_exception(error_type, error, tb))
    report = re.sub(r"(?i)postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]+",
                    "[DATABASEVERBINDING AFGESCHERMD]", report)
    report = re.sub(r"(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*)[^\s,'\"]+",
                    r"\1\2[AFGESCHERMD]", report)
    print("VEILIG GESTOPT - proef 6; geen databasewijzigingen", file=sys.stderr)
    print("\n".join(report.splitlines()[-20:]), file=sys.stderr)


sys.excepthook = _safe_error


def _existing_code_rows(products):
    """Unieke codes categoriseren; niet-gecodeerde artikelen nooit doorgeven."""
    eligible, invalid, unmarked = [], [], 0
    for item in products:
        code = str(item.get("primary_gtin") or "").strip()
        if not code:
            unmarked += 1
            continue
        if not code.isascii() or not code.isdecimal() or not is_valid_gtin(code):
            invalid.append({"naam": safe(item.get("name"), 120), "code": safe(code, 50)})
            continue
        eligible.append({"naam": safe(item.get("name"), 120), "code": code,
                         "status": safe(item.get("status"), 20)})
    return eligible, invalid, unmarked


def main():
    if DATASTORE_KIND != "postgresql":
        raise RuntimeError("VEILIG GESTOPT: geen bestaande PostgreSQL-backend")
    indexes = load_indexes()

    with engine.connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        try:
            products = [dict(row) for row in conn.execute(text(
                "SELECT id, name, primary_gtin, status FROM global_products ORDER BY name, id"
            )).mappings().all()]
        finally:
            conn.rollback()

    eligible, invalid, no_code = _existing_code_rows(products)
    gtins = list(dict.fromkeys(item["code"] for item in eligible))
    if len(gtins) > 100:
        raise RuntimeError("VEILIG GESTOPT: meer dan 100 GTINs; scope eerst expliciet herijken")

    print("============================================================", flush=True)
    print("INHUIS - TAXONOMIE-EERST - PROEF 6: ALLEEN GECODEERDE CATALOGUS", flush=True)
    print("============================================================", flush=True)
    print("Datum:", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("Shopify: officiële versie 2026-08, 14606 NL categorieën; 764 EN voedselnamen (MIT)")
    print("CBS ECOICOPv2 2026: officiële categorieën, lokale indicatieve vergelijking (CC BY 4.0)")
    print("OFF: exacte barcode via bestaande InHuis-service, publiek, max 1 GET per 6 seconden")
    print("Kosten: GEEN licentieafdracht / betaalde API / externe GS1-aansluiting")
    print("PostgreSQL: SET TRANSACTION READ ONLY, expliciete rollback vóór OFF")
    print("BUITEN SCOPE: ED2-bonartikelen, codevrije Catalogusartikelen, herclassificatie in database")
    print("GEEN mutatie aan Artikelgroep, Producttype, GS1, Catalogus, bon, voorraad of software")
    print("EEN BARCODE is geen garantie dat OFF-gegevens of een taxonomievoorstel juist zijn")
    print("HERKOMST: dit rapport kan niet controleren wie de bestaande GTIN ooit heeft toegekend")
    print()
    print("CATALOGUS-SCOPE")
    print("  Totaal in Catalogus:", len(products))
    print("  Met geldige bestaande GTIN:", len(eligible))
    print("  Met code, maar géén geldige GTIN (GEEN OFF):", len(invalid))
    print("  Zonder code (niet onderzocht):", no_code)
    print("  Unieke geldige barcode-opvragen:", len(gtins))
    print("  Verwachte minimumwachttijd tussen GETs: ~", max(0, len(gtins)-1)*6, "sec")
    print(flush=True)

    # OFF-service heeft geen database-updatepad. Geen externe GET voor ongeldige
    # codes of ongecodeerde Catalogusartikelen. Never retry failed requests.
    from app.services.off_search_service import lookup_off_product_by_gtin

    replies = {}
    for index, gtin in enumerate(gtins, 1):
        if index > 1:
            time.sleep(6)
        print(f"VOORTGANG OFF {index}/{len(gtins)}: barcode {gtin}", flush=True)
        try:
            result = lookup_off_product_by_gtin(gtin)
            if result.get("mutated") is not False or result.get("gtin") != gtin:
                raise RuntimeError("OFF-service heeft het read-only / exact-GTIN-contract geschonden")
            replies[gtin] = result
        except Exception:
            replies[gtin] = {"status": "external_source_unavailable", "product": None}

    stats = collections.Counter()
    print()
    print("ALLE GECODEERDE CATALOGUSARTIKELEN – VOORSTELLEN TER BEOORDELING")
    print("Artikel | Bestaande GTIN | OFF-status | OFF-naam | OFF-categorieën | "
          "Voorstelstatus | Shopify-ID | Nederlandse Shopify-hiërarchie | "
          "CBS ECOICOPv2 vergelijkbaar | OFF-bewijsregel | "
          "Alternatieve Shopify-ID's | Waarschuwing")
    for item in eligible:
        gtin = item["code"]
        reply = replies[gtin]
        off_status = safe(reply.get("status"), 45)
        product = reply.get("product") if off_status == "found" else None
        if product:
            classification = classify_off_product(product, item["naam"], indexes)
            proposal_status = classification["status"]
        else:
            classification = {}
            proposal_status = "GEEN_OFF_PRODUCT" if off_status == "not_found" else "OFF_NIET_BESCHIKBAAR"
        stats[proposal_status] += 1
        values = (item["naam"], gtin, off_status, classification.get("off_naam"),
                  classification.get("off_categorie"), proposal_status,
                  classification.get("shopify_id"), classification.get("shopify_pad"),
                  classification.get("cbs_vergelijking"), classification.get("bewijs"),
                  classification.get("alternatieven"), classification.get("waarschuwing"))
        print(" | ".join(safe(value, 250) for value in values))

    print()
    print("ONREGELMATIGE OF NIET-GTIN CODES – WEL IN CATALOGUS, NOOIT NAAR OFF")
    for item in invalid:
        print(" | ".join((item["naam"], item["code"], "NIET_GELDIGE_GTIN")))
    print()
    print("EINDSAMENVATTING (NIET DE NAUWKEURIGHEID!)")
    for key, count in sorted(stats.items()):
        print(f"  {key}: {count}")
    print(f"  Totaal beoordeeld met bestaande geldige GTIN: {sum(stats.values())}")
    print("  GEEN OFF-GET voor niet-gecodeerde of niet-valide codes")
    print("  Geen Shopify-ID of CBS-code vastgelegd; voorstellen zijn GEEN officiële GS1-classificatie")
    print("  Eerst inhoudelijke steekproef en expliciete autorisatie voor eventuele latere opslag")
    print("AFGEROND: bestaande database ongemoeid, geen deployment of herstart", flush=True)


if __name__ == "__main__":
    main()
