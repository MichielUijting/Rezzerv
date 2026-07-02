from app.services.external_retailer_taxonomy import (
    build_off_query_terms,
    expand_receipt_terms,
    get_taxonomy_summary,
    list_taxonomy_entries,
)


def test_lidl_taxonomy_summary_is_non_mutating():
    summary = get_taxonomy_summary("Lidl")

    assert summary["retailer_code"] == "lidl"
    assert summary["taxonomy_entry_count"] >= 5
    assert summary["term_library_count"] >= 1
    assert summary["creates_global_product"] is False
    assert summary["creates_household_article"] is False
    assert summary["creates_inventory_event"] is False


def test_lidl_receipt_terms_expand_abbreviated_kruidenmix():
    terms = expand_receipt_terms("Mexicaanse kruidenm.", "lidl")

    assert "mexicaanse kruidenm" in terms
    assert any("kruidenmix" in term for term in terms)
    assert any("specerijenmix" in term for term in terms)


def test_lidl_off_query_terms_use_taxonomy_without_mutation():
    terms = build_off_query_terms("Mexicaanse kruidenm.", "lidl")

    assert "mexicaanse kruidenm" in terms
    assert "kania taco specerijenmix" in terms
    assert "kanig taco kruidenmix" in terms
    assert "taco seasoning mix" in terms


def test_lidl_taxonomy_entries_remain_reviewable_templates():
    entries = list_taxonomy_entries("lidl")

    assert entries
    assert all(entry.retailer_code == "lidl" for entry in entries)
    assert all(entry.canonical_name for entry in entries)
    assert all(entry.off_query_terms for entry in entries)
