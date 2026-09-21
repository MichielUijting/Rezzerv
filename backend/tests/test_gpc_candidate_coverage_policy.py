from app.services.product_taxonomy_store import (
    audit_gpc_candidate_coverage_policy,
    load_gpc_candidate_strategy,
    load_gpc_candidate_terms,
)


def test_every_seeded_taxonomy_intent_declares_a_gpc_candidate_strategy():
    report = audit_gpc_candidate_coverage_policy()

    assert report["ok"] is True, report["violations"]
    assert report["taxonomy_count"] >= 78
    assert report["counts"]["taxonomy_rank"] >= 1
    assert report["counts"]["semantic_terms"] >= 4


def test_clear_operational_product_intents_have_explicit_gpc_candidate_paths():
    assert load_gpc_candidate_strategy("soep.groentebasis") == "semantic_terms"
    assert load_gpc_candidate_strategy("saus.bouillon") == "semantic_terms"
    assert load_gpc_candidate_strategy("vleeswaren.chorizo") == "semantic_terms"
    assert load_gpc_candidate_strategy("vleeswaren.worst") == "semantic_terms"
    assert load_gpc_candidate_strategy("groente.broccoli") == "taxonomy_rank"


def test_soepgroente_semantic_terms_cover_official_storage_variants():
    assert load_gpc_candidate_terms("soep.groentebasis") == (
        "Vegetables - Prepared/Processed (Perishable)",
        "Vegetables - Prepared/Processed (Frozen)",
        "Vegetables - Prepared/Processed (Shelf Stable)",
    )
