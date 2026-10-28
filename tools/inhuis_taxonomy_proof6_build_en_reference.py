"""Maak een kleine Engelse voedselnamenindex uit dezelfde officiële Shopify-release.

Eenmalige bouwstap in ontwikkelomgeving:
  python -m tools.inhuis_taxonomy_proof6_build_en_reference \
    --source /tmp/inhuis_shopify_2026_08_categories_en.json.gz

De uitgegeven proef gebruikt uitsluitend de vastgepinde, meegeleverde index.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from tools.inhuis_taxonomy_proof5_core import load_references


DESTINATION = Path(__file__).resolve().parent / "taxonomy_proof5_references" / "shopify_2026_08_en_food.json.gz"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    nl, _ = load_references()
    with gzip.open(args.source, "rt", encoding="utf-8") as handle:
        source = json.load(handle)
    if source.get("version") != "2026-08":
        raise RuntimeError("VEILIG GESTOPT: Engelse Shopify-bron heeft andere versie")
    all_categories = [c for v in source["verticals"] for c in v["categories"]]
    if len(all_categories) != len(nl["categorieen"]):
        raise RuntimeError("VEILIG GESTOPT: Shopify NL/EN categorieaantal verschilt")
    en_ids = {c["id"].rsplit("/", 1)[-1] for c in all_categories}
    nl_ids = {c["id"] for c in nl["categorieen"]}
    if en_ids != nl_ids:
        raise RuntimeError("VEILIG GESTOPT: Shopify NL/EN categorie-ID's verschillen")
    food = [{"id": c["id"].rsplit("/", 1)[-1], "en": c["name"]}
            for c in all_categories
            if c["id"].rsplit("/", 1)[-1] == "fb"
            or c["id"].rsplit("/", 1)[-1].startswith("fb-")]
    food.sort(key=lambda c: c["id"])
    if not 500 < len(food) < 1500:
        raise RuntimeError("VEILIG GESTOPT: onverwacht aantal Shopify-voedselcategorieen")
    binary = json.dumps({"versie": "2026-08", "categorieen": food},
                        ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with DESTINATION.open("wb") as handle:
        with gzip.GzipFile(filename="", fileobj=handle, mode="wb", mtime=0, compresslevel=9) as output:
            output.write(binary)
    print("Shopify EN bron SHA256:", hashlib.sha256(args.source.read_bytes()).hexdigest())
    print("Shopify EN voedselcategorieen:", len(food))
    print("Gegenereerde referentie:", DESTINATION)


if __name__ == "__main__":
    main()
