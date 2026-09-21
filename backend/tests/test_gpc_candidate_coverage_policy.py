import json

from app.services.product_taxonomy_store import (
    TAXONOMY_SEED_PATH,
    audit_gpc_candidate_coverage_policy,
    load_gpc_candidate_strategy,
    load_gpc_candidate_terms,
    load_product_variant_terms,
    normalize_taxonomy_text,
)


def test_every_seeded_taxonomy_intent_declares_a_gpc_candidate_strategy():
    report = audit_gpc_candidate_coverage_policy()

    assert report["ok"] is True, report["violations"]
    assert report["taxonomy_count"] >= 78
    assert report["counts"]["taxonomy_rank"] >= 1
    assert report["counts"]["semantic_terms"] >= 5


def test_clear_operational_product_intents_have_explicit_gpc_candidate_paths():
    assert load_gpc_candidate_strategy("soep.groentebasis") == "semantic_terms"
    assert load_gpc_candidate_strategy("saus.bouillon") == "semantic_terms"
    assert load_gpc_candidate_strategy("vleeswaren.chorizo") == "semantic_terms"
    assert load_gpc_candidate_strategy("vleeswaren.worst") == "semantic_terms"
    assert load_gpc_candidate_strategy("vlees.gehakt") == "semantic_terms"
    assert load_gpc_candidate_strategy("groente.broccoli") == "taxonomy_rank"


def test_soepgroente_semantic_terms_cover_official_storage_variants():
    assert load_gpc_candidate_terms("soep.groentebasis") == (
        "Vegetables - Prepared/Processed (Perishable)",
        "Vegetables - Prepared/Processed (Frozen)",
        "Vegetables - Prepared/Processed (Shelf Stable)",
    )

def test_ground_meat_semantic_terms_and_variants_are_explicit():
    assert load_gpc_candidate_terms("vlees.gehakt") == (
        "Mixed Species Meat/Poultry/Other Animal - Alternative Meat - Prepared/Processed",
        "Beef - Prepared/Processed",
        "Pork - Prepared/Processed",
    )
    variants = {
        row["normalized_variant_term"]: tuple(row["gpc_candidate_terms"])
        for row in load_product_variant_terms("vlees.gehakt")
        if row.get("gpc_candidate_terms")
    }
    assert variants["gemengd gehakt"] == (
        "Mixed Species Meat/Poultry/Other Animal - Alternative Meat - Prepared/Processed",
    )
    assert variants["half om half gehakt"] == variants["gemengd gehakt"]
    assert variants["rundergehakt"] == ("Beef - Prepared/Processed",)
    assert variants["varkensgehakt"] == ("Pork - Prepared/Processed",)


def test_all_semantic_candidate_terms_resolve_to_bundled_official_gpc_reference():
    seed = json.loads(TAXONOMY_SEED_PATH.read_text(encoding="utf-8"))
    reference_path = TAXONOMY_SEED_PATH.parent / "gpc_bricks_2026_05_en.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference_rows = reference.get("bricks") or []

    official_terms = set()
    for row in reference_rows:
        for field in (
            "gpc_brick_name_en",
            "gpc_class_name_en",
            "gpc_family_name_en",
            "gpc_segment_name_en",
        ):
            normalized = normalize_taxonomy_text(row.get(field))
            if normalized:
                official_terms.add(normalized)

    declared_terms = []
    for item in seed.get("taxonomy") or []:
        if item.get("gpc_candidate_strategy") != "semantic_terms":
            continue
        declared_terms.extend(item.get("gpc_candidate_terms") or [])
    for item in seed.get("product_variant_terms") or []:
        declared_terms.extend(item.get("gpc_candidate_terms") or [])

    missing = sorted({
        term
        for term in declared_terms
        if normalize_taxonomy_text(term) not in official_terms
    })
    assert not missing, f"Semantic GPC-termen ontbreken in officiële reference: {missing}"

