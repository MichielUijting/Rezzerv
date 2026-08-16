from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OVERVIEW_PATH = "frontend/src/features/articles/tabs/ArticleOverviewTab.jsx"
MAIN_PATH = "backend/app/main.py"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _between(source: str, start: str, end: str) -> str:
    assert start in source, f"start marker ontbreekt: {start}"
    tail = source.split(start, 1)[1]
    assert end in tail, f"end marker ontbreekt: {end}"
    return tail.split(end, 1)[0]


def test_general_household_editor_owns_only_custom_name():
    source = _read(OVERVIEW_PATH)
    fields = _between(source, "const EDITABLE_FORM_FIELDS = [", "]\n\nconst HOUSEHOLD_SETTINGS_STATUS_OPTIONS")

    assert "key: 'custom_name'" in fields
    for forbidden in (
        "key: 'article_type'",
        "key: 'category'",
        "key: 'brand_or_maker'",
        "key: 'short_description'",
        "key: 'barcode'",
        "key: 'article_number'",
        "key: 'min_stock'",
        "key: 'ideal_stock'",
        "key: 'favorite_store'",
        "key: 'notes'",
    ):
        assert forbidden not in fields

    editor = _between(source, "function ArticleDetailsEditor", "function normalizeSettingsFormValue")
    payload = _between(editor, "const payload = {", "}\n      const response")
    assert "custom_name: formState.custom_name.trim()" in payload
    for forbidden in (
        "article_type:",
        "category:",
        "brand_or_maker:",
        "short_description:",
        "barcode:",
        "article_number:",
        "min_stock:",
        "ideal_stock:",
        "favorite_store:",
        "notes:",
    ):
        assert forbidden not in payload


def test_household_settings_have_one_dedicated_mutation_owner():
    source = _read(OVERVIEW_PATH)
    settings = _between(source, "function HouseholdArticleSettingsCard", "function ProductDetailsCard")

    assert "/settings`" in settings
    assert "method: 'PUT'" in settings
    for field in (
        "min_stock:",
        "ideal_stock:",
        "favorite_store:",
        "average_price:",
        "status:",
        "default_location_id:",
        "default_sublocation_id:",
        "auto_restock:",
        "packaging_unit:",
        "packaging_quantity:",
        "notes:",
    ):
        assert field in settings


def test_external_product_identity_uses_dedicated_flow_and_role_gate():
    source = _read(OVERVIEW_PATH)
    external = _between(source, "function ExternalLinkCard", "export default function ArticleOverviewTab")

    assert "displayRole === 'admin' || displayRole === 'lid'" in external
    assert "/external-product-link`" in external
    assert "if (!inventoryId || !canEdit) return" in external
    assert "if (!editMode || !canEdit) return" in external
    assert "const actions = canEdit ? (" in external
    assert "disabled={!canEdit || saveState.saving}" in external


def test_article_automation_override_matches_admin_only_backend_contract():
    source = _read(OVERVIEW_PATH)
    automation = _between(source, "function AutomationOverrideCard", "function EditableHouseholdFieldRow")

    assert "const canEdit = displayRole === 'admin'" in automation
    assert "if (!canEdit) return" in automation
    assert "disabled={!consumable || !canEdit}" in automation


def test_article_metadata_mutation_does_not_write_inventory_quantity_or_events():
    source = _read(MAIN_PATH)
    mutation = _between(source, "def update_household_article_details_by_id", "def update_household_article_details(")

    assert "UPDATE household_articles" in mutation
    assert "UPDATE inventory" not in mutation
    assert "INSERT INTO inventory_events" not in mutation
    assert "write_inventory_event" not in mutation


def run_contract() -> None:
    test_general_household_editor_owns_only_custom_name()
    test_household_settings_have_one_dedicated_mutation_owner()
    test_external_product_identity_uses_dedicated_flow_and_role_gate()
    test_article_automation_override_matches_admin_only_backend_contract()
    test_article_metadata_mutation_does_not_write_inventory_quantity_or_events()
    print("ARTICLE_DETAIL_MUTATION_CONTRACT_GREEN")


if __name__ == "__main__":
    run_contract()
