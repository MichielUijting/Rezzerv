"""Reproduceer compacte, alleen-lezen referenties uit OFFICIELE bronbestanden.

Eenmalig uitvoeren in de ontwikkelomgeving (niet op de InHuis-server):
  python -m tools.inhuis_taxonomy_proof5_build_references \
      --shopify /tmp/categories.nl.json.gz --cbs /tmp/bijlageecoicopv2indeling.xlsx

Deze bouwstap is niet vereist voor de eenklikproef; de resultaten worden versiegepind
meegeleverd. Vereist voor de eenmalige CBS-Excel-extractie: openpyxl.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shopify", required=True, type=Path)
    parser.add_argument("--cbs", required=True, type=Path)
    args = parser.parse_args()
    from openpyxl import load_workbook

    with gzip.open(args.shopify, "rt", encoding="utf-8") as source:
        upstream = json.load(source)
    if upstream.get("version") != "2026-08":
        raise ValueError("Onverwachte Shopify-taxonomieversie")
    categories = [{
        "id": category["id"].rsplit("/", 1)[-1],
        "naam": category["name"],
        "pad": category["full_name"],
        "parent": (category["parent_id"] or "").rsplit("/", 1)[-1],
    } for vertical in upstream["verticals"] for category in vertical["categories"]]
    if not 10000 < len(categories) < 50000:
        raise ValueError("Onverwachte Shopify-categorieomvang")

    workbook = load_workbook(args.cbs, read_only=True, data_only=True)
    sheet = workbook["1-ECOICOPv2"]
    ecoicop = [{"code": str(row[0]), "naam": str(row[1])} for row in list(sheet.values)[1:]
               if row[0] and row[1] and len(str(row[0])) == 6]
    workbook.close()
    if not 350 < len(ecoicop) < 700:
        raise ValueError("Onverwachte CBS ECOICOPv2-tabelomvang")

    root = Path(__file__).resolve().parent / "taxonomy_proof5_references"
    root.mkdir(parents=True, exist_ok=True)
    compact = {"bron": "Shopify Standard Product Taxonomy", "versie": "2026-08",
               "categorieen": categories}
    with gzip.open(root / "shopify_2026_08_nl.json.gz", "wt", encoding="utf-8", compresslevel=9) as target:
        json.dump(compact, target, ensure_ascii=False, separators=(",", ":"))
    (root / "cbs_ecoicop_v2_2026.json").write_text(
        json.dumps({"bron": "CBS ECOICOPv2, gepubliceerd 12-02-2026", "codes": ecoicop},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, path in (("Shopify", args.shopify), ("CBS", args.cbs)):
        print(name, "SHA256 origineel:", hashlib.sha256(path.read_bytes()).hexdigest())
    print("Shopify-categorieen:", len(categories), "CBS-codes:", len(ecoicop))


if __name__ == "__main__":
    main()
