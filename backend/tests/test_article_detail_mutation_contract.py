import ast
from pathlib import Path
from types import SimpleNamespace


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


def _load_partial_patch_function():
    source = _read(MAIN_PATH)
    tree = ast.parse(source)
    function_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "update_household_article_details_by_id"
    )

    class StubHTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class StubRequest:
        pass

    executions = []
    side_effects = []
    article_row = {
        "id": "article-a",
        "naam": "Testartikel",
        "custom_name": "Oude naam",
        "article_type": "Voedsel & drank",
        "notes": "legacy-notitie",
        "min_stock": 2.0,
        "ideal_stock": 5.0,
        "favorite_store": "Oude winkel",
        "barcode": "8712345678901",
        "article_number": "OLD-1",
        "external_source": "existing-source",
    }

    class StubConnection:
        def execute(self, statement, params=None):
            executions.append((str(statement), dict(params or {})))
            return SimpleNamespace()

    def normalize_optional_text_field(value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def normalize_optional_numeric_field(value):
        if value in (None, ""):
            return None
        return float(value)

    namespace = {
        "ArticleHouseholdDetailsUpdateRequest": StubRequest,
        "HTTPException": StubHTTPException,
        "get_household_article_row_by_id": lambda conn, household_id, article_id: dict(article_row),
        "get_household_article_details": lambda conn, household_id, name: {"id": "article-a", "naam": name},
        "normalize_optional_text_field": normalize_optional_text_field,
        "normalize_optional_numeric_field": normalize_optional_numeric_field,
        "normalize_barcode_value": lambda value: str(value).strip() if value not in (None, "") else None,
        "get_household_article_by_barcode": lambda conn, household_id, barcode: None,
        "text": lambda value: value,
        "clear_primary_barcode_identity_for_article": lambda *args: side_effects.append("clear-barcode"),
        "upsert_product_identity": lambda *args, **kwargs: side_effects.append("upsert-identity"),
        "ensure_household_article_global_product_link": lambda *args, **kwargs: side_effects.append("global-link"),
        "ensure_article_product_enrichment": lambda *args, **kwargs: side_effects.append("enrich"),
        "write_product_enrichment_audit": lambda *args, **kwargs: side_effects.append("audit"),
    }
    isolated_module = ast.Module(body=[function_node], type_ignores=[])
    ast.fix_missing_locations(isolated_module)
    exec(compile(isolated_module, MAIN_PATH, "exec"), namespace)
    return namespace["update_household_article_details_by_id"], StubConnection(), executions, side_effects, StubHTTPException


def _payload(**provided):
    defaults = {
        "custom_name": None,
        "article_type": None,
        "category": None,
        "brand_or_maker": None,
        "short_description": None,
        "notes": None,
        "min_stock": None,
        "ideal_stock": None,
        "favorite_store": None,
        "barcode": None,
        "article_number": None,
        "source": None,
    }
    defaults.update(provided)
    return SimpleNamespace(**defaults, model_fields_set=set(provided), __fields_set__=set(provided))


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


def test_household_mutation_cards_use_central_role_ssot_and_fail_closed():
    source = _read(OVERVIEW_PATH)
    assert "isHouseholdAdminFromContext" in source
    assert "isHouseholdViewerFromContext" in source

    general = _between(source, "function ArticleDetailsEditor", "function normalizeSettingsFormValue")
    settings = _between(source, "function HouseholdArticleSettingsCard", "function ProductDetailsCard")
    external = _between(source, "function ExternalLinkCard", "export default function ArticleOverviewTab")
    for section in (general, settings, external):
        assert "const canEdit = Boolean(authContext) && !isHouseholdViewerFromContext(authContext)" in section
        assert "displayRole === 'admin' || displayRole === 'lid'" not in section


def test_external_product_identity_uses_dedicated_flow_and_role_gate():
    source = _read(OVERVIEW_PATH)
    external = _between(source, "function ExternalLinkCard", "export default function ArticleOverviewTab")

    assert "const canEdit = Boolean(authContext) && !isHouseholdViewerFromContext(authContext)" in external
    assert "/external-product-link`" in external
    assert "if (!inventoryId || !canEdit) return" in external
    assert "if (!editMode || !canEdit) return" in external
    assert "const actions = canEdit ? (" in external
    assert "disabled={!canEdit || saveState.saving}" in external


def test_article_automation_override_matches_admin_only_backend_contract():
    source = _read(OVERVIEW_PATH)
    automation = _between(source, "function AutomationOverrideCard", "function EditableHouseholdFieldRow")

    assert "const canEdit = isHouseholdAdminFromContext(authContext)" in automation
    assert "if (!canEdit) return" in automation
    assert "disabled={!consumable || !canEdit}" in automation


def test_article_metadata_mutation_does_not_write_inventory_quantity_or_events():
    source = _read(MAIN_PATH)
    mutation = _between(source, "def update_household_article_details_by_id", "def update_household_article_details(")

    assert "UPDATE household_articles" in mutation
    assert "UPDATE inventory" not in mutation
    assert "INSERT INTO inventory_events" not in mutation
    assert "write_inventory_event" not in mutation


def test_custom_name_patch_preserves_omitted_metadata_and_identity_side_effects():
    function, conn, executions, side_effects, _ = _load_partial_patch_function()

    result = function(conn, "household-a", "article-a", _payload(custom_name="PO TEST PR251"))

    assert result["id"] == "article-a"
    assert len(executions) == 1
    statement, params = executions[0]
    assert "custom_name = :custom_name" in statement
    for forbidden_column in (
        "article_type =",
        "notes =",
        "min_stock =",
        "ideal_stock =",
        "favorite_store =",
        "barcode =",
        "article_number =",
        "external_source =",
    ):
        assert forbidden_column not in statement
    assert params == {
        "custom_name": "PO TEST PR251",
        "household_id": "household-a",
        "household_article_id": "article-a",
    }
    assert side_effects == []


def test_single_stock_threshold_patch_validates_against_omitted_existing_threshold():
    function, conn, executions, side_effects, StubHTTPException = _load_partial_patch_function()

    try:
        function(conn, "household-a", "article-a", _payload(min_stock=6))
    except StubHTTPException as exc:
        assert exc.status_code == 400
        assert "Minimumvoorraad" in exc.detail
    else:
        raise AssertionError("min_stock boven bestaande ideal_stock had geweigerd moeten worden")

    assert executions == []
    assert side_effects == []


def test_unsupported_product_knowledge_fields_are_not_silently_accepted():
    function, conn, executions, side_effects, StubHTTPException = _load_partial_patch_function()

    try:
        function(conn, "household-a", "article-a", _payload(category="Nieuwe categorie"))
    except StubHTTPException as exc:
        assert exc.status_code == 400
        assert "category" in exc.detail
    else:
        raise AssertionError("productkennisveld category had geweigerd moeten worden")

    assert executions == []
    assert side_effects == []


def run_contract() -> None:
    test_general_household_editor_owns_only_custom_name()
    test_household_settings_have_one_dedicated_mutation_owner()
    test_household_mutation_cards_use_central_role_ssot_and_fail_closed()
    test_external_product_identity_uses_dedicated_flow_and_role_gate()
    test_article_automation_override_matches_admin_only_backend_contract()
    test_article_metadata_mutation_does_not_write_inventory_quantity_or_events()
    test_custom_name_patch_preserves_omitted_metadata_and_identity_side_effects()
    test_single_stock_threshold_patch_validates_against_omitted_existing_threshold()
    test_unsupported_product_knowledge_fields_are_not_silently_accepted()
    print("ARTICLE_DETAIL_MUTATION_CONTRACT_GREEN")


if __name__ == "__main__":
    run_contract()
