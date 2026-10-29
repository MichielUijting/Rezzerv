"""Offline tests proef 7 – geen PostgreSQL, OFF-netwerk of datamutaties."""

from pathlib import Path

from tools.inhuis_taxonomy_proof6_core import classify_off_product, load_indexes
from tools.inhuis_taxonomy_proof7_core import NAME_RULES, classify_proof7


INDEXES = load_indexes()


def evaluate(name, categories="", tags=(), off_name=None):
    product = {"product_name": name if off_name is None else off_name,
               "categories": categories, "category_tags": list(tags)}
    p6 = classify_off_product(product, name, INDEXES)
    return classify_proof7(product, name, INDEXES, baseline=p6)


def run():
    variants = (
        ("Rookworst", "Rookworst, Vlees, Worsten", "fb-2-12-2-3-1"),
        ("Rundersalami", "Cured sausages", "fb-2-12-2-3-1"),
        ("Bouillon", "Bouillon pots", "fb-2-18"),
        ("Krokante ontbijt granen", "Breakfast cereals", "fb-2-11-4"),
        ("Teriyaki Sauce", "Teriyaki sauces", "fb-2-4"),
        ("Gemengd gehakt", "", "fb-2-12-2"),
        ("Kipfilet Mexicaanse stijl", "", "fb-2-12-2"),
        ("Mini gehaktballetjes", "", "fb-2-12-2"),
        ("Grillworst", "", "fb-2-12-2"),
        ("Uienpoeder", "", "fb-2-16-1"),
        ("Zoete aardappel friet", "", "fb-2-15-1-3"),
    )
    for name, categories, expected in variants:
        result = evaluate(name, categories)
        assert result["shopify_id"] == expected, (name, result)
        assert result["nieuw_voorstel7"], (name, result)
        assert result["status"] in {
            "OFF_NL_LABEL_VOORSTEL", "OFF_TEKST_BREED_VOORSTEL", "OFF_NAAM_BREED_CONTROLEREN"}, result
        assert result["shopify_pad"].startswith("Eten, drinken en tabak"), name

    dutch = evaluate("Rookworst", "", tags=["nl:rookworst"])
    assert dutch["shopify_id"] == "fb-2-12-2-3-1", dutch
    # Geen false-positive van rauwe aardappel bij voorbereide gerechten.
    assert evaluate("Aardappelschijfjes")["shopify_id"] == ""
    assert evaluate("Chocopops")["shopify_id"] == ""
    assert evaluate("Product 0000000000000")["shopify_id"] == ""
    # Zonder herkenbare gedeelde productstam geen naamfallback, zelfs wanneer
    # OFF op de barcode een totaal andere productnaam zou retourneren.
    mismatch = evaluate("Kipgehakt", "", off_name="Chocoladepasta")
    assert mismatch["shopify_id"] == ""
    assert mismatch["methode7"] == "OFF_NAAMCONFLICT_GEEN_FALLBACK", mismatch

    # Conflicterende OFF-tags zijn leidend boven de zwakkere fallback.
    ambiguous = evaluate("Cayennepeper", "", tags=["en:peppers", "en:herbs-and-spices"])
    assert ambiguous["shopify_id"] == "", ambiguous
    assert ambiguous["status"] == "MEERDUIDIGE_SHOPIFY_CATEGORIE", ambiguous
    assert not ambiguous["nieuw_voorstel7"]
    unchanged = evaluate("Bananen", "", tags=["en:bananas"])
    assert unchanged["shopify_id"] == "fb-2-10-7-5" and not unchanged["nieuw_voorstel7"]
    composite = evaluate("Bobotie", "Mixed herbs", tags=["en:mixed-herbs"])
    assert "SAMENGESTELD_PRODUCT_CONTROLEREN" in composite["waarschuwing"]
    assert not composite["nieuw_voorstel7"]

    # Geen niet-bestaande Shopify-code en geen herintroductie van ED2/writes.
    for _, code, _ in NAME_RULES:
        assert code in INDEXES[0], code
    source = (Path(__file__).parent / "inhuis_taxonomy_proof7.py").read_text(encoding="utf-8")
    assert "SET TRANSACTION READ ONLY" in source
    assert "conn.rollback()" in source
    assert "list_all_external_articles" not in source
    assert "FROM global_products" in source
    assert "time.sleep(6)" in source
    print("GESLAAGD: proef7 OFF-NL/EN, brede naamfallback, conflictsignalen, bestaande GTIN, read-only")


if __name__ == "__main__":
    run()
