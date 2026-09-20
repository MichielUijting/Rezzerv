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
