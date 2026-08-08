from pathlib import Path

from app.services.external_database_matchflow_evidence import match_retailer_receipt_line
from app.services.retailer_catalog_enrichment import enrich_receipt_product_line_dict


CODE_FILES = [
    Path("app/services/retailer_catalog_enrichment.py"),
    Path("app/services/external_retailer_taxonomy.py"),
    Path("app/services/external_product_index_store.py"),
]

FORBIDDEN_PRODUCT_TERMS = [
    "Mexicaanse kruidenmix",
    "Courgette",
    "Zoete aardappel",
    "Bananen",
    "Halfvolle melk",
]


def test_product_knowledge_is_not_hardcoded_in_python_services():
    backend_root = Path(__file__).resolve().parents[1]
    for relative_path in CODE_FILES:
        source = (backend_root / relative_path).read_text(encoding="utf-8")
        for term in FORBIDDEN_PRODUCT_TERMS:
            assert term not in source


def test_lidl_catalog_enrichment_is_loaded_from_json_seed():
    result = enrich_receipt_product_line_dict("Mexicaanse kruiden", retailer_code="lidl")
    assert result["matched"] is True
    assert result["source_product_code"] == "21175"
    assert result["creates_global_product"] is False if "creates_global_product" in result else True


def test_common_lidl_fresh_products_have_real_candidates_from_data_seed():
    for receipt_text in ["courgette", "zoete aardappel"]:
        result = match_retailer_receipt_line("lidl", receipt_text, include_below_threshold=True)
        assert result["candidates"], result
        assert result["candidate_source"] != "receipt_unresolved_fallback"
        assert result["candidate_source"] != "receipt_product_intent_fallback"
        assert all(candidate["creates_global_product"] is False for candidate in result["candidates"])
        assert all(candidate["creates_household_article"] is False for candidate in result["candidates"])
        assert all(candidate["creates_inventory_event"] is False for candidate in result["candidates"])
