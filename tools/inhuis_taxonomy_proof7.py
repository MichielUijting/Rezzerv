"""Inhuis Proef 7: brede OFF->Shopify-voorstellen uitsluitend voor bestaande GTIN.

In reeds draaiende backend:
    python -u -m tools.inhuis_taxonomy_proof7
Geen schema-, Catalogus-, ED2-, GS1-, Artikelgroep- of voorraadmutaties.
"""

import collections
import datetime
import re
import sys
import time
import traceback

from sqlalchemy import text

from app.db import DATASTORE_KIND, engine
from tools.inhuis_taxonomy_proof5_core import safe
from tools.inhuis_taxonomy_proof6 import _existing_code_rows
from tools.inhuis_taxonomy_proof6_core import classify_off_product, load_indexes
from tools.inhuis_taxonomy_proof7_core import classify_proof7


def _safe_error(error_type, error, tb):
    msg = "".join(traceback.format_exception(error_type, error, tb))
    msg = re.sub(r"(?i)postgres(?:ql)?(?:\+psycopg)?://[^\s'\"]+",
                 "[DATABASEVERBINDING AFGESCHERMD]", msg)
    msg = re.sub(r"(?i)(password|secret|token|api[_-]?key)(\s*[:=]\s*)[^\s,'\"]+",
                 r"\1\2[AFGESCHERMD]", msg)
    print("VEILIG GESTOPT - proef 7; geen databasewijzigingen", file=sys.stderr)
    print("\n".join(msg.splitlines()[-20:]), file=sys.stderr)


sys.excepthook = _safe_error


def main():
    if DATASTORE_KIND != "postgresql":
        raise RuntimeError("VEILIG GESTOPT: backend is geen bestaande PostgreSQL-backend")
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
    unique = list(dict.fromkeys(row["code"] for row in eligible))
    if len(unique) > 100:
        raise RuntimeError("VEILIG GESTOPT: meer dan 100 barcodes; nieuwe scope nodig")

    print("============================================================", flush=True)
    print("INHUIS - TAXONOMIEPROEF 7 - BREDERE PRODUCTINDELING - CATALOGUS", flush=True)
    print("============================================================", flush=True)
    print("Datum:", datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("Shopify v2026-08: NL 14606 categorieën, EN 764 voedsel/drank-labels (MIT)")
    print("CBS ECOICOPv2 2026: alleen lokaal indicatieve vergelijking (CC BY 4.0)")
    print("Open Food Facts: bestaande openbare exact-GTIN-service, 6 sec tussen GETs")
    print("GEEN betaalde licenties, GS1-netwerkaansluiting of betaalde AI")
    print("Catalogus: PostgreSQL TRANSACTION READ ONLY, altijd rollback vóór netwerk")
    print("Geen ED2-bonartikelen; nooit een barcode raden of op naam extern zoeken")
    print("Nul database-, GS1-, Artikelgroep-, Producttype-, voorraad- of containerwijzigingen")
    print("Shopify/CBS-voorstellen zijn NIET officieel bevestigd en worden NIET opgeslagen")
    print("Wie de oorspronkelijke barcode toewees is in deze proef niet bewijsbaar")
    print()
    print("SCOPE")
    print("  Catalogus totaal:", len(products))
    print("  Zonder code - buiten proef:", no_code)
    print("  Met code maar zonder geldige GTIN - geen OFF:", len(invalid))
    print("  Met geldige bestaande GTIN:", len(eligible))
    print("  Unieke GETs:", len(unique))
    print("  Minimaal wachtinterval totaal:", max(0, len(unique)-1) * 6, "seconden")
    print(flush=True)

    from app.services.off_search_service import lookup_off_product_by_gtin

    results = {}
    for index, gtin in enumerate(unique, 1):
        if index > 1:
            time.sleep(6)
        print(f"VOORTGANG OFF {index}/{len(unique)}: {gtin}", flush=True)
        try:
            result = lookup_off_product_by_gtin(gtin)
        except Exception:
            results[gtin] = {"status": "external_source_unavailable", "product": None}
        else:
            if result.get("mutated") is not False or result.get("gtin") != gtin:
                raise RuntimeError("VEILIG GESTOPT: OFF-read-only / exact-GTIN-contract geschonden")
            results[gtin] = result

    p6_counts, p7_counts = collections.Counter(), collections.Counter()
    off_counts = collections.Counter()
    improvements = 0
    print()
    print("VOLLEDIG OVERZICHT - GEEN DATABASEWIJZIGINGEN")
    print("Catalogusartikel | GTIN | OFF-status | Proef6-status | Proef7-status | "
          "Nieuw sinds proef6 | Methode | Shopify-ID | Nederlandse Shopify-hiërarchie | "
          "CBS vergelijking | OFF-productnaam | OFF-categorieomschrijving | "
          "OFF-categorietags | Herkomst van voorstel | Alternatieven | Waarschuwing")
    for item in eligible:
        response = results[item["code"]]
        status = safe(response.get("status"), 40)
        off_counts[status] += 1
        product = response.get("product") if status == "found" else None
        if product:
            old = classify_off_product(product, item["naam"], indexes)
            new = classify_proof7(product, item["naam"], indexes, baseline=old)
            old_status, new_status = old["status"], new["status"]
            if new.get("nieuw_voorstel7"):
                improvements += 1
        else:
            old_status = new_status = ("GEEN_OFF_PRODUCT" if status == "not_found"
                                      else "OFF_NIET_BESCHIKBAAR")
            new = {}
        p6_counts[old_status] += 1
        p7_counts[new_status] += 1
        vals = (item["naam"], item["code"], status, old_status, new_status,
                "JA" if new.get("nieuw_voorstel7") else "NEE",
                new.get("methode7"), new.get("shopify_id"), new.get("shopify_pad"),
                new.get("cbs_vergelijking"), new.get("off_naam"),
                new.get("off_categorie"), new.get("off_tags"), new.get("bewijs"),
                new.get("alternatieven"), new.get("waarschuwing"))
        print(" | ".join(safe(value, 250) for value in vals))

    print()
    print("CODE IN CATALOGUS MAAR GEEN GELDIGE GTIN – GEEN OFF-OPVRAAG")
    for item in invalid:
        print(" | ".join((item["naam"], item["code"], "GEEN_GELDIGE_GTIN")))
    print()
    print("SAMENVATTING – RECHTSTREEKS VERGELEKEN MET PROEF6 OP DEZE RUN")
    print("  OFF-resultaten:", dict(off_counts))
    print("  Oude voorstelstatussen proef6:", dict(sorted(p6_counts.items())))
    print("  Nieuwe voorstelstatussen proef7:", dict(sorted(p7_counts.items())))
    print("  Nieuwe Shopify-ID-voorstellen bij eerdere nulmatch:", improvements)
    print("  Bereik huidige proef:", len(eligible), "artikelen met bestaande geldige GTIN")
    print("  Geen nauwkeurigheidsscore: NAAM_BREED is zwakker dan OFF-label")
    print("  Bij twijfel geen categorietoewijzing; menselijke controle voor opslag vereist")
    print("AFGEROND: GEEN DATABASE-, CONTAINER-, GIT- OF SOFTWAREMUTATIE", flush=True)


if __name__ == "__main__":
    main()
