from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "frontend/src/features/stores/StoreBatchDetailPage.jsx"
BACKEND_MAIN = ROOT / "backend/app/main.py"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _backend_source() -> str:
    return BACKEND_MAIN.read_text(encoding="utf-8")


def test_article_group_is_not_an_unpacking_readiness_gate():
    source = _source()
    assert "&& hasArticleGroup\n    && hasValidLocation" not in source
    assert "statusReason = 'Artikelgroep ontbreekt.'" not in source
    assert "artikel/product, locatie of artikelgroep" not in source


def test_unpacking_requires_positive_quantity_and_location():
    source = _source()
    assert "hasValidQuantity" in source
    assert "effectiveQuantity" in source
    assert "&& hasValidQuantity" in source
    assert "&& hasValidLocation" in source


def test_unknown_receipt_article_can_get_household_anchor_without_catalog_identity():
    source = _source()
    assert "&& hasArticleGroup\n          && hasValidLocation" not in source
    assert "&& !hasGlobalProduct\n          && hasRawArticleName" not in source


def test_article_group_is_visible_optional_household_metadata():
    source = _source()
    assert ">Mijn artikel</ResizableHeaderCell>" not in source
    assert ">Artikelgroep</ResizableHeaderCell>" in source
    assert '<option value="">Niet ingedeeld</option>' in source


def test_household_article_remains_internal_inventory_anchor():
    source = _source()
    assert "matched_household_article_id" in source
    assert "articleId" in source


def test_backend_does_not_require_article_group_for_inventory_processing():
    source = _backend_source()
    assert 'if not article_group_id:\n                    error = "Geen geldige artikelgroep gekozen"' not in source


def test_backend_validates_article_group_only_when_one_is_selected():
    source = _backend_source()
    assert 'if article_group_id:' in source
    assert 'FROM article_groups' in source
    assert 'household_id = :household_id' in source
