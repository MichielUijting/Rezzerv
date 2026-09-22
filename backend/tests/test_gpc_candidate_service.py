from __future__ import annotations

from app.services import gpc_candidate_service as service


def _row(code: str, brick: str, class_name: str = "", family: str = "", segment: str = ""):
    return {
        "brick_code": code,
        "brick_description": brick,
        "brick_description_en": brick,
        "class_code": "50100000",
        "class_description": class_name,
        "family_code": "50010000",
        "family_description": family,
        "segment_code": "50000000",
        "segment_description": segment,
    }


def test_build_product_signals_reuses_existing_taxonomy(monkeypatch):
    monkeypatch.setattr(
        service,
        "classify_product_intent_from_taxonomy",
        lambda value: "saus.bouillon",
    )
    monkeypatch.setattr(
        service,
        "get_taxonomy_metadata_for_intent",
        lambda key: {
            "intent_key": key,
            "canonical_name": "Bouillon",
            "category": "soep",
            "product_type": "bouillon",
        },
    )
    monkeypatch.setattr(
        service,
        "load_gpc_candidate_terms",
        lambda key: (),
    )
    monkeypatch.setattr(
        service,
        "load_taxonomy_rules",
        lambda: (
            {
                "intent_key": "saus.bouillon",
                "normalized_term": "groentebouillonblok",
                "priority": 1000,
                "source": "seed",
            },
            {
                "intent_key": "saus.bouillon",
                "normalized_term": "bouillon",
                "priority": 999,
                "source": "seed",
            },
        ),
    )

    bundle = service.build_product_signals({
        "product_name": "AH Bouillon kip",
        "category": "",
        "external_product_name": "Bouillonblokjes kip",
        "external_category": "Soep en bouillon",
        "external_categories": "",
        "external_search_text": "ah bouillon kip bouillonblok",
    })

    assert bundle["intent_key"] == "saus.bouillon"
    normalized = {signal["normalized"] for signal in bundle["signals"]}
    assert "bouillon" in normalized
    assert "groentebouillonblok" in normalized
    assert "soep" in normalized
    assert len(bundle["signals"]) <= 28


def test_rank_gpc_candidates_returns_explainable_top_five():
    signals = {
        "intent_key": "saus.bouillon",
        "signals": [
            {
                "text": "Bouillon",
                "normalized": "bouillon",
                "tokens": ["bouillon"],
                "source": "taxonomy_product_type",
                "weight": 1.5,
            },
            {
                "text": "Soep",
                "normalized": "soep",
                "tokens": ["soep"],
                "source": "taxonomy_category",
                "weight": 1.05,
            },
        ],
    }
    rows = [
        _row("10000001", "Bouillonblokjes", "Bouillon en fond", "Soepen"),
        _row("10000002", "Bouillonpoeder", "Bouillon en fond", "Soepen"),
        _row("10000003", "Vloeibare bouillon", "Bouillon en fond", "Soepen"),
        _row("10000004", "Soepbasis", "Soepbereidingen", "Soepen"),
        _row("10000005", "Kruidenmix voor soep", "Kruiden en specerijen", "Soepen"),
        _row("10000006", "Kant-en-klare soep", "Soepen", "Soepen"),
        _row("10000007", "Smeerkaas", "Kaas", "Zuivel"),
    ]

    ranked = service.rank_gpc_candidates(rows, signals, limit=5)

    assert len(ranked) == 5
    assert ranked[0]["brick_code"] in {"10000001", "10000002", "10000003"}
    assert {row["brick_code"] for row in ranked[:3]} == {"10000001", "10000002", "10000003"}
    assert ranked[0]["match_strength_percent"] >= ranked[-1]["match_strength_percent"]
    assert ranked[0]["confidence_label"] in {"hoog", "redelijk", "laag"}
    assert ranked[0]["suggestion_source"] == "gpc_candidate_engine"
    assert ranked[0]["suggestion_reason"].startswith("Overeenkomst met productgegevens:")
    assert "matched_terms" in ranked[0]
    assert all(row["brick_code"] != "10000007" for row in ranked)


def test_rank_gpc_candidates_never_returns_more_than_five():
    signals = {
        "intent_key": "zuivel.kaas",
        "signals": [
            {
                "text": "Kaas",
                "normalized": "kaas",
                "tokens": ["kaas"],
                "source": "taxonomy_product_type",
                "weight": 1.5,
            },
        ],
    }
    rows = [
        _row(f"1000000{index}", f"Kaas variant {index}", "Kaas")
        for index in range(1, 8)
    ]

    ranked = service.rank_gpc_candidates(rows, signals, limit=100)

    assert len(ranked) == 5
    assert len({row["brick_code"] for row in ranked}) == 5


def test_rank_gpc_candidates_matches_meaningful_dutch_compound_tokens():
    signals = {"intent_key": "", "signals": [{
        "text": "boerenmetworst",
        "normalized": "boerenmetworst",
        "tokens": ["boerenmetworst"],
        "source": "product_name",
        "weight": 1.45,
    }]}
    rows = [
        _row("10001001", "Worst en worstproducten", "Vleeswaren", "Vleesproducten"),
        _row("10001002", "Roomkaas", "Kaas", "Zuivel"),
    ]
    ranked = service.rank_gpc_candidates(rows, signals, limit=5)
    assert ranked
    assert ranked[0]["brick_code"] == "10001001"
    assert all(row["brick_code"] != "10001002" for row in ranked)



def test_boerenmetworst_semantic_bridge_ranks_official_pork_and_mixed_species_bricks(monkeypatch):
    monkeypatch.setattr(
        service,
        "classify_product_intent_from_taxonomy",
        lambda value: "vleeswaren.worst",
    )
    monkeypatch.setattr(
        service,
        "get_taxonomy_metadata_for_intent",
        lambda key: {
            "intent_key": key,
            "canonical_name": "Worst",
            "category": "Vleeswaren",
            "product_type": "Worst",
        },
    )
    monkeypatch.setattr(
        service,
        "load_gpc_candidate_terms",
        lambda key: (
            "Pork Sausages - Prepared/Processed",
            "Mixed Species Sausages - Prepared/Processed",
            "Meat/Poultry/Other Animals Sausages - Prepared/Processed",
        ),
    )
    monkeypatch.setattr(
        service,
        "load_taxonomy_rules",
        lambda: (
            {
                "intent_key": "vleeswaren.worst",
                "normalized_term": "boerenmetworst",
                "priority": 999,
                "source": "seed",
            },
        ),
    )

    bundle = service.build_product_signals({
        "product_name": "'t Slagershuys boerenmetworst",
        "category": "",
        "external_product_name": "Boerenmetworst",
        "external_category": "",
        "external_categories": "",
        "external_search_text": "slagershuys boerenmetworst",
    })

    semantic_signals = [
        signal
        for signal in bundle["signals"]
        if signal["source"] == "taxonomy_gpc_candidate_term"
    ]
    assert semantic_signals
    assert all(signal["weight"] == 0.55 for signal in semantic_signals)

    sausage_class = "MEAT/POULTRY/OTHER ANIMALS SAUSAGES - PREPARED/PROCESSED"
    rows = [
        _row("10005833", "BEEF SAUSAGES - PREPARED/PROCESSED", sausage_class, "MEAT/POULTRY/OTHER ANIMALS"),
        _row("10005834", "CHICKEN SAUSAGES - PREPARED/PROCESSED", sausage_class, "MEAT/POULTRY/OTHER ANIMALS"),
        _row("10005835", "LAMB/MUTTON SAUSAGES - PREPARED/PROCESSED", sausage_class, "MEAT/POULTRY/OTHER ANIMALS"),
        _row("10005836", "MIXED SPECIES SAUSAGES - PREPARED/PROCESSED", sausage_class, "MEAT/POULTRY/OTHER ANIMALS"),
        _row("10005837", "TURKEY SAUSAGES - PREPARED/PROCESSED", sausage_class, "MEAT/POULTRY/OTHER ANIMALS"),
        _row("10005838", "VEAL SAUSAGES - PREPARED/PROCESSED", sausage_class, "MEAT/POULTRY/OTHER ANIMALS"),
        _row("10005840", "PORK SAUSAGES - PREPARED/PROCESSED", sausage_class, "MEAT/POULTRY/OTHER ANIMALS"),
        _row("10000007", "CHEESE", "CHEESE", "DAIRY"),
    ]

    ranked = service.rank_gpc_candidates(rows, bundle, limit=5)

    assert len(ranked) == 5
    assert {row["brick_code"] for row in ranked[:2]} == {"10005836", "10005840"}
    assert ranked[0]["match_strength_percent"] >= 60
    assert ranked[1]["match_strength_percent"] >= 60
    assert all(
        row["suggestion_reason"].startswith("Semantische GPC-overeenkomst via producttype:")
        for row in ranked[:2]
    )
    assert all(row["brick_code"] != "10000007" for row in ranked)


def test_soepgr_basis_semantic_bridge_ranks_official_prepared_vegetable_bricks(monkeypatch):
    monkeypatch.setattr(
        service,
        "classify_product_intent_from_taxonomy",
        lambda value: "soep.groentebasis",
    )
    monkeypatch.setattr(
        service,
        "get_taxonomy_metadata_for_intent",
        lambda key: {
            "intent_key": key,
            "canonical_name": "Soepgroente",
            "category": "Soep",
            "product_type": "Soepgroente",
        },
    )
    monkeypatch.setattr(
        service,
        "load_gpc_candidate_terms",
        lambda key: (
            "Vegetables - Prepared/Processed (Perishable)",
            "Vegetables - Prepared/Processed (Frozen)",
            "Vegetables - Prepared/Processed (Shelf Stable)",
        ),
    )
    monkeypatch.setattr(
        service,
        "load_taxonomy_rules",
        lambda: (
            {
                "intent_key": "soep.groentebasis",
                "normalized_term": "soepgr basis",
                "priority": 1200,
                "source": "seed",
            },
        ),
    )

    bundle = service.build_product_signals({
        "product_name": "SOEPGR BASIS",
        "category": "",
        "external_product_name": "Soepgroenten",
        "external_category": "",
        "external_categories": "",
        "external_search_text": "SOEPGR BASIS soepgroenten",
    })

    semantic_signals = [
        signal
        for signal in bundle["signals"]
        if signal["source"] == "taxonomy_gpc_candidate_term"
    ]
    assert len(semantic_signals) == 3

    vegetable_class = "VEGETABLES - PREPARED/PROCESSED"
    rows = [
        _row(
            "10000270",
            "VEGETABLES - PREPARED/PROCESSED (FROZEN)",
            vegetable_class,
            "VEGETABLES",
        ),
        _row(
            "10000271",
            "VEGETABLES - PREPARED/PROCESSED (PERISHABLE)",
            vegetable_class,
            "VEGETABLES",
        ),
        _row(
            "10000272",
            "VEGETABLES - PREPARED/PROCESSED (SHELF STABLE)",
            vegetable_class,
            "VEGETABLES",
        ),
        _row(
            "10005840",
            "PORK SAUSAGES - PREPARED/PROCESSED",
            "MEAT/POULTRY/OTHER ANIMALS SAUSAGES - PREPARED/PROCESSED",
            "MEAT/POULTRY/OTHER ANIMALS",
        ),
    ]

    ranked = service.rank_gpc_candidates(rows, bundle, limit=5)

    assert [row["brick_code"] for row in ranked[:3]] == [
        "10000270",
        "10000271",
        "10000272",
    ] or set(row["brick_code"] for row in ranked[:3]) == {
        "10000270",
        "10000271",
        "10000272",
    }
    assert all(
        row["suggestion_reason"].startswith(
            "Semantische GPC-overeenkomst via producttype:"
        )
        for row in ranked[:3]
    )
    assert all(row["brick_code"] != "10005840" for row in ranked)

def test_ground_meat_semantic_variants_prefer_official_species_bricks(monkeypatch):
    monkeypatch.setattr(service, "classify_product_intent_from_taxonomy", lambda value: "vlees.gehakt")
    monkeypatch.setattr(
        service,
        "get_taxonomy_metadata_for_intent",
        lambda key: {
            "intent_key": key,
            "canonical_name": "Gehakt",
            "category": "Vlees",
            "product_type": "Gehakt",
        },
    )
    monkeypatch.setattr(
        service,
        "load_gpc_candidate_terms",
        lambda key: (
            "Mixed Species Meat/Poultry/Other Animal - Alternative Meat - Prepared/Processed",
            "Beef - Prepared/Processed",
            "Pork - Prepared/Processed",
        ),
    )
    monkeypatch.setattr(
        service,
        "load_product_variant_terms",
        lambda key: (
            {
                "normalized_variant_term": "gemengd gehakt",
                "gpc_candidate_terms": (
                    "Mixed Species Meat/Poultry/Other Animal - Alternative Meat - Prepared/Processed",
                ),
            },
            {"normalized_variant_term": "rundergehakt", "gpc_candidate_terms": ("Beef - Prepared/Processed",)},
            {"normalized_variant_term": "varkensgehakt", "gpc_candidate_terms": ("Pork - Prepared/Processed",)},
        ),
    )
    monkeypatch.setattr(service, "load_taxonomy_rules", lambda: ())

    meat_class = "Meat/Poultry/Other Animals - Prepared/Processed"
    rows = [
        _row("10005767", "Beef - Prepared/Processed", meat_class, "Meat/Poultry/Other Animals"),
        _row(
            "10005778",
            "Mixed Species Meat/Poultry/Other Animal - Alternative Meat - Prepared/Processed",
            meat_class,
            "Meat/Poultry/Other Animals",
        ),
        _row("10005781", "Pork - Prepared/Processed", meat_class, "Meat/Poultry/Other Animals"),
        _row(
            "10005836",
            "Mixed Species Sausages - Prepared/Processed",
            "Meat/Poultry/Other Animals Sausages - Prepared/Processed",
            "Meat/Poultry/Other Animals",
        ),
    ]

    cases = (
        ("'t Slagershuys gemengd gehakt", "10005778"),
        ("Rundergehakt", "10005767"),
        ("Varkensgehakt", "10005781"),
    )
    for product_name, expected_brick in cases:
        bundle = service.build_product_signals({
            "product_name": product_name,
            "category": "",
            "external_product_name": product_name,
            "external_category": "",
            "external_categories": "",
            "external_search_text": product_name,
        })
        ranked = service.rank_gpc_candidates(rows, bundle, limit=5)
        assert ranked, product_name
        assert ranked[0]["brick_code"] == expected_brick, (product_name, ranked)
        assert ranked[0]["suggestion_reason"].startswith(
            "Semantische GPC-overeenkomst via producttype:"
        )
        assert all(row["brick_code"] != "10005836" for row in ranked[:3])


def test_ground_meat_generic_semantic_bridge_keeps_official_species_candidates(monkeypatch):
    monkeypatch.setattr(service, "classify_product_intent_from_taxonomy", lambda value: "vlees.gehakt")
    monkeypatch.setattr(
        service,
        "get_taxonomy_metadata_for_intent",
        lambda key: {
            "intent_key": key,
            "canonical_name": "Gehakt",
            "category": "Vlees",
            "product_type": "Gehakt",
        },
    )
    monkeypatch.setattr(
        service,
        "load_gpc_candidate_terms",
        lambda key: (
            "Mixed Species Meat/Poultry/Other Animal - Alternative Meat - Prepared/Processed",
            "Beef - Prepared/Processed",
            "Pork - Prepared/Processed",
        ),
    )
    monkeypatch.setattr(service, "load_product_variant_terms", lambda key: ())
    monkeypatch.setattr(service, "load_taxonomy_rules", lambda: ())

    rows = [
        _row("10005767", "Beef - Prepared/Processed", "Meat/Poultry/Other Animals - Prepared/Processed"),
        _row(
            "10005778",
            "Mixed Species Meat/Poultry/Other Animal - Alternative Meat - Prepared/Processed",
            "Meat/Poultry/Other Animals - Prepared/Processed",
        ),
        _row("10005781", "Pork - Prepared/Processed", "Meat/Poultry/Other Animals - Prepared/Processed"),
    ]
    bundle = service.build_product_signals({
        "product_name": "Gehakt",
        "external_search_text": "gehakt",
    })
    ranked = service.rank_gpc_candidates(rows, bundle, limit=5)
    assert {row["brick_code"] for row in ranked[:3]} == {"10005767", "10005778", "10005781"}



def _nl_row(code: str, brick_nl: str, brick_en: str):
    return {
        "brick_code": code,
        "brick_description": brick_nl or brick_en,
        "brick_description_nl": brick_nl,
        "brick_description_en": brick_en,
        "class_code": "50100000",
        "class_description": "",
        "class_description_nl": "",
        "class_description_en": "",
        "family_code": "50010000",
        "family_description": "",
        "family_description_nl": "",
        "family_description_en": "",
        "segment_code": "50000000",
        "segment_description": "",
        "segment_description_nl": "",
        "segment_description_en": "",
    }


def test_dutch_gpc_translation_is_primary_for_compound_kipfiletblokjes():
    bundle = service.build_product_signals({
        "product_name": "'t Slagershuys kipfiletblokjes",
        "external_product_name": "kipfiletblokjes",
        "external_search_text": "slagershuys kipfiletblokjes",
    })
    assert any(signal["normalized"] == "kipfilet" and signal["source"] == "compound_stem" for signal in bundle["signals"])
    rows = [
        _nl_row("19000001", "Kipfilet - onbereid/onbewerkt", "Chicken Fillet - Unprepared/Unprocessed"),
        _nl_row("19000002", "Kipfilet - bereid/bewerkt", "Chicken Fillet - Prepared/Processed"),
        _nl_row("19000003", "Kipfiletproducten - overig", "Chicken Fillet Products - Other"),
        _row("19000004", "Pork - Prepared/Processed", "Pork"),
    ]
    ranked = service.rank_gpc_candidates(rows, bundle, limit=5)
    assert len(ranked) == 3
    assert {row["brick_code"] for row in ranked} == {"19000001", "19000002", "19000003"}
    assert all(row["suggestion_match_basis"] == "dutch_gpc_translation" for row in ranked)


def test_dutch_gpc_match_outranks_english_fallback():
    signals = {"intent_key": "", "signals": [{"text": "kaas", "normalized": "kaas", "tokens": ["kaas"], "source": "product_name", "weight": 1.45}]}
    ranked = service.rank_gpc_candidates([_nl_row("19000010", "Kaas", "Cheese"), _row("19000011", "Kaas")], signals, limit=5)
    assert [row["brick_code"] for row in ranked] == ["19000010", "19000011"]
    assert ranked[0]["suggestion_match_basis"] == "dutch_gpc_translation"
    assert ranked[1]["suggestion_match_basis"] == "semantic_or_english_fallback"


def test_valid_product_intent_hint_is_reused_for_candidate_signals(monkeypatch):
    monkeypatch.setattr(service, "load_gpc_candidate_strategy", lambda key: "taxonomy_rank" if key == "groente.broccoli" else "")
    monkeypatch.setattr(
        service,
        "get_taxonomy_metadata_for_intent",
        lambda key: {
            "intent_key": key,
            "canonical_name": "Broccoli",
            "category": "Groente",
            "product_type": "Broccoli",
        },
    )
    monkeypatch.setattr(service, "load_product_variant_terms", lambda key: ())
    monkeypatch.setattr(service, "load_gpc_candidate_terms", lambda key: ())
    monkeypatch.setattr(service, "load_taxonomy_rules", lambda: ())

    bundle = service.build_product_signals({
        "product_name": "onduidelijke externe naam",
        "product_intent": "groente.broccoli",
    })

    assert bundle["intent_key"] == "groente.broccoli"
    assert any(signal["normalized"] == "broccoli" for signal in bundle["signals"])
