"""Offline regression tests voor de uitsluitend-lezen taxonomieproef 5."""

from tools.inhuis_taxonomy_proof5_core import Matcher, load_references, off_evidence_tags


def run():
    shopify, cbs = load_references()
    matcher = Matcher(shopify, cbs)
    assert len(shopify["categorieen"]) == 14606
    assert len(cbs["codes"]) == 440
    checks = {
        "Tomaten": "fb-2-10-8-51",
        "Magere yoghurt": "fb-2-6-8",
        "Ham gerookt": "fb-2-12-2",
    }
    for name, expected_prefix in checks.items():
        result = matcher.match(name)
        matched = [candidate["id"] for candidate in result["shopify"]]
        assert any(item.startswith(expected_prefix) for item in matched), (name, result)
        assert result["status"] in {"WOORDMATCH_CONTROLEREN", "EXACTE_NAAM_VOORSTEL"}, name

    # Niet-bestaande of dubbelzinnige winkelbenamingen mogen nooit automatisch
    # als officiële catalogus- of GS1-identiteit worden gepresenteerd.
    for name in ("Product 02081281", "AH GRF ROOKV", "NIEUW VITAMIEN 778"):
        result = matcher.match(name)
        assert result["status"] == "GEEN_VERANTWOORDE_MATCH", (name, result)
    assert matcher.match("Achterham, gerookt")["status"] == "GEEN_VERANTWOORDE_MATCH"

    composite = matcher.match("Ovenschotel prei")
    assert composite["status"] in ("INGREDIËNTGEVAAR", "GEEN_VERANTWOORDE_MATCH"), composite
    assert matcher.match("Tomaten gezeefd")["status"] == "BEREIDINGSVORM_ONZEKER"
    assert matcher.match("Zoete aardappel frites")["status"] == "BEREIDINGSVORM_ONZEKER"
    assert matcher.match("TRIANGEL")["status"] == "NONFOOD_CONTEXT_CONTROLEREN"
    assert matcher.match("SNOEP TOMAAT")["status"] == "HOMONIEM_CONTROLEREN"
    milk = matcher.match("melk")
    assert milk["status"] == "MEERDUIDIGE_SHOPIFY_CATEGORIE", milk
    assert "Zuivel / melk" == off_evidence_tags(["en:milks"])
    assert off_evidence_tags([]) == "geen herkende OFF-richting"

    print("GESLAAGD: proef5 referenties, woordmatching, ambiguiteit en OFF-labels")


if __name__ == "__main__":
    run()
