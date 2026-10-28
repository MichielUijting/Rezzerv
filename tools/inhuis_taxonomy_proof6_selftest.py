"""Volledig offline bewijstest voor proef 6; geen OFF-netwerk of database."""

from pathlib import Path

from tools.inhuis_taxonomy_proof6_core import classify_off_product, load_indexes


def _classify(name, tags):
    return classify_off_product({"product_name": name, "categories": "test",
                                 "category_tags": tags}, name, load_indexes())


def run():
    nl, en, cbs = load_indexes()
    assert len(nl) == 14606
    assert "fb-2-10-7-5" in nl
    assert "bananas" not in en or isinstance(en["bananas"], list)
    assert "011600" in cbs

    cases = (
        ("Bananen", ["en:fruits-based-foods", "en:fruits", "en:bananas"], "fb-2-10-7-5"),
        ("Achterham", ["en:meats", "en:hams"], "fb-2-12-2-3-2"),
        ("Pittige pepitamix", ["en:nuts"], "fb-2-13"),
        ("Aardappelpuree", ["en:potatoes", "en:mashed-potatoes"], "fb-2-15-1-3"),
        ("Bobotie", ["en:mixed-herbs"], "fb-2-16-1"),
        ("Frisdrank", ["en:soft-drinks"], "fb-1-12"),
    )
    for name, tags, expected in cases:
        result = _classify(name, tags)
        assert result["shopify_id"] == expected, (name, result)
        assert result["shopify_pad"].startswith("Eten, drinken en tabak"), name
        assert result["status"].endswith("VOORSTEL"), result

    none = _classify("Onbekend product", [])
    assert none["shopify_id"] == "" and none["status"].startswith("GEEN"), none
    non_en = _classify("Aardappelpuree", ["nl:aardappelpuree"])
    assert non_en["shopify_id"] == "", non_en
    mixed = _classify("Bananen en ham", ["en:bananas", "en:hams"])
    assert mixed["status"] == "MEERDUIDIGE_SHOPIFY_CATEGORIE", mixed
    assert mixed["shopify_id"] == "", mixed
    milk = _classify("Halfvolle melk", ["en:milks"])
    assert milk["status"] == "MEERDUIDIGE_SHOPIFY_CATEGORIE", milk
    assert "fb-2-6-9" in milk["alternatieven"] and "fb-1-9" in milk["alternatieven"]
    name_conflict = classify_off_product({"product_name": "Yoghurt", "category_tags": ["en:bananas"]},
                                         "Achterham", load_indexes())
    assert "CONTROLEER_NAAMVERSCHIL" in name_conflict["waarschuwing"]
    assert "SAMENGESTELD_PRODUCT_CONTROLEREN" in _classify("Bobotie", ["en:mixed-herbs"])["waarschuwing"]

    # Zelfs een correct gekozen GTIN mag nooit tot opslag of ED2-scope leiden.
    source = (Path(__file__).parent / "inhuis_taxonomy_proof6.py").read_text(encoding="utf-8")
    assert "SET TRANSACTION READ ONLY" in source
    assert "conn.rollback()" in source
    assert "list_all_external_articles" not in source
    assert "FROM global_products" in source
    assert "time.sleep(6)" in source
    print("GESLAAGD: proef 6, Shopify NL/EN, OFF-tag-alternatieven, bereidingsvorm, read-only scope")


if __name__ == "__main__":
    run()
