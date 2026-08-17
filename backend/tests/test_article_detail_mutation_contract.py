import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
OVERVIEW_PATH = "frontend/src/features/articles/tabs/ArticleOverviewTab.jsx"
OVERVIEW_WRAPPER_PATH = "frontend/src/features/articles/tabs/ArticleOverviewSubtabs.jsx"
CURATED_SUMMARY_PATH = "frontend/src/features/articles/components/ArticleOverviewCuratedSummaries.jsx"
ANALYSIS_WRAPPER_PATH = "frontend/src/features/articles/tabs/ArticleAnalyticsSubtabs.jsx"
ANALYSIS_PATH = "frontend/src/features/articles/tabs/ArticleAnalyticsTab.jsx"
POLICY_PATH = "frontend/src/features/articles/articleDetailMutationPolicy.css"
INPUT_CSS_PATH = "frontend/src/ui/components/input.css"
STOCK_PATH = "frontend/src/features/articles/tabs/ArticleStockTab.jsx"
LOCATIONS_PATH = "frontend/src/features/articles/tabs/ArticleLocationsTab.jsx"
TABS_PATH = "frontend/src/ui/Tabs.jsx"
GATEWAY_PATH = "backend/app/api/article_detail_admin_routes.py"
PRODUCT_ROUTER_PATH = "backend/app/api/product_inventory_group_routes.py"
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


def test_overview_wrapper_makes_member_and_viewer_read_only():
    source = _read(OVERVIEW_WRAPPER_PATH)
    assert "isHouseholdAdminFromContext" in source
    assert "const readOnly = !canMutate" in source
    assert "control.disabled = true" in source
    assert "button.disabled = true" in source
    assert "button:not(.rz-article-section-summary)" in source
    assert "Alleen-lezen. Alleen een beheerder of eigenaar" in source
    assert "isHouseholdViewerFromContext" not in source


def test_overview_has_compact_curated_functional_subtabs():
    source = _read(OVERVIEW_WRAPPER_PATH)
    summary = _read(CURATED_SUMMARY_PATH)
    policy = _read(POLICY_PATH)

    for label in ("'Artikel'", "'Huishouden'", "'Identiteit'", "'Productdata'"):
        assert label in source
    for mapping in (
        "'Artikelgegevens voor dit huishouden': 'article'",
        "'Instellingen voor dit huishouden': 'household'",
        "'Externe productkoppeling': 'legacy'",
        "Productverrijking: 'legacy'",
    ):
        assert mapping in source
    assert "ArticleIdentitySummary" in source
    assert "ArticleProductSummary" in source
    assert "Naam in dit huishouden is een optionele eigen benaming" in source
    assert "CURATED_BASIS_DUPLICATE_LABELS" in source
    assert "data-active-subtab={activeKey}" in source
    assert "section.dataset.articleSubtab" in source
    assert "section.hidden" not in source
    assert "className=\"rz-article-subtabs\"" in source
    assert "ariaLabel=\"Overzicht subtabs\"" in source
    assert '[data-article-subtab="legacy"]' in policy
    assert '[data-curated-hidden="true"]' in policy

    for test_id in ('article-identity-summary', 'article-product-summary'):
        assert test_id in summary
    for user_label in (
        'Barcode',
        'Extern artikelnummer',
        'Productnaam',
        'Merk',
        'Categorie',
        'Inhoud',
        'Ingrediënten',
        'Allergenen',
        'Bron',
    ):
        assert user_label in summary
    for technical_ballast in (
        'Bronketen',
        'Interne matchstatus',
        'Centrale product-ID',
        'Confidence',
        'Lookup melding',
        'Recente bronpogingen',
    ):
        assert technical_ballast not in summary


def test_editable_values_are_black_and_nonfunctional_settings_are_not_presented():
    policy = _read(POLICY_PATH)
    input_css = _read(INPUT_CSS_PATH)

    assert 'article-details-input-average_price' in policy
    assert 'article-household-settings-auto-restock' in policy
    assert '.rz-article-subtab-layout input:not(:disabled)' in policy
    assert '.rz-article-subtab-layout select:not(:disabled)' in policy
    assert '#000000' in policy
    assert '.rz-input:not(:disabled)' in input_css
    assert '#000000' in input_css


def test_analysis_has_compact_direct_functional_subtabs():
    wrapper = _read(ANALYSIS_WRAPPER_PATH)
    analysis = _read(ANALYSIS_PATH)
    policy = _read(POLICY_PATH)

    for label in ("'Trends'", "'Prijs'", "'Prognose'", "'Onderbouwing'"):
        assert label in wrapper
    assert "data-active-subtab={activeKey}" in wrapper
    assert "ariaLabel=\"Analyse subtabs\"" in wrapper
    assert "useLayoutEffect" not in wrapper
    assert "MutationObserver" not in wrapper
    assert "dataset.analysisSubtab" not in wrapper

    for anchor in (
        'data-testid="analysis-row-automation"',
        'data-testid="analysis-row-price"',
        'data-testid="analysis-row-consumption"',
        'data-testid="analysis-row-forecast"',
        'data-testid="analysis-row-advice"',
        'data-testid="analysis-row-quality"',
    ):
        assert anchor in analysis

    for selector in (
        '[data-active-subtab="trends"]',
        '[data-active-subtab="price"]',
        '[data-active-subtab="forecast"]',
        '[data-active-subtab="evidence"]',
        '[data-testid="analysis-row-consumption"]',
        '[data-testid="analysis-row-price"]',
        '[data-testid="analysis-row-forecast"]',
        '[data-testid="analysis-row-advice"]',
        '[data-testid="analysis-row-automation"]',
        '[data-testid="analysis-row-quality"]',
    ):
        assert selector in policy
    assert '[data-analysis-subtab]' not in policy


def test_shared_tabs_support_nested_accessible_navigation_without_breaking_defaults():
    source = _read(TABS_PATH)
    assert "ariaLabel = 'Artikeldetails tabs'" in source
    assert "rootTestId = 'tabs-root'" in source
    assert "tablistTestId = 'tabs-tablist'" in source
    assert "className = ''" in source
    assert "aria-label={ariaLabel}" in source


def test_stock_mutation_is_admin_only_and_uses_article_detail_gateway():
    source = _read(STOCK_PATH)
    assert "const canEditInventory = isHouseholdAdminFromContext(authContext)" in source
    assert "canCurrentUserPerform" not in source
    assert "inventory.update" not in source
    assert "/inventory-events`" in source
    assert "`/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-events`" in source
    assert "fetchJsonWithAuth('/api/inventory-events'" not in source
    assert "disabled={!canEditInventory" in source


def test_location_mutation_is_admin_only_and_uses_article_detail_gateway():
    source = _read(LOCATIONS_PATH)
    assert "const canMutate = isHouseholdAdminFromContext" in source
    assert "`/api/household-articles/${encodeURIComponent(householdArticleId)}/inventory-transfers`" in source
    assert "fetchJsonWithAuth('/api/inventory-transfers'" not in source
    assert "disabled={!canMutate" in source
    assert "Alleen een beheerder kan voorraad verplaatsen" in source


def test_article_detail_backend_gateway_is_admin_only_and_registered_first():
    gateway = _read(GATEWAY_PATH)
    product_router = _read(PRODUCT_ROUTER_PATH)
    main = _read(MAIN_PATH)

    for route in (
        "@router.patch('/api/household-articles/{household_article_id}')",
        "@router.put('/api/household-articles/{household_article_id}/settings')",
        "@router.post('/api/household-articles/{household_article_id}/inventory-events')",
        "@router.post('/api/household-articles/{household_article_id}/inventory-transfers')",
    ):
        assert route in gateway
    assert gateway.count("_require_admin(endpoint, authorization)") >= 2
    assert gateway.count("context = _require_admin(endpoint, authorization)") >= 2
    assert "_assert_inventory_belongs_to_article" in gateway

    gateway_include = "router.include_router(article_detail_admin_router)"
    assert gateway_include in product_router
    assert product_router.index(gateway_include) < product_router.index("router.include_router(authorization_membership_router)")

    early_router = "app.include_router(product_inventory_group_router)"
    old_patch = '@app.patch("/api/household-articles/{household_article_id}")'
    old_settings = '@app.put("/api/household-articles/{household_article_id}/settings")'
    assert early_router in main and old_patch in main and old_settings in main
    assert main.index(early_router) < main.index(old_patch)
    assert main.index(early_router) < main.index(old_settings)


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
    test_overview_wrapper_makes_member_and_viewer_read_only()
    test_overview_has_compact_curated_functional_subtabs()
    test_editable_values_are_black_and_nonfunctional_settings_are_not_presented()
    test_analysis_has_compact_direct_functional_subtabs()
    test_shared_tabs_support_nested_accessible_navigation_without_breaking_defaults()
    test_stock_mutation_is_admin_only_and_uses_article_detail_gateway()
    test_location_mutation_is_admin_only_and_uses_article_detail_gateway()
    test_article_detail_backend_gateway_is_admin_only_and_registered_first()
    test_household_settings_have_one_dedicated_mutation_owner()
    test_article_automation_override_matches_admin_only_backend_contract()
    test_article_metadata_mutation_does_not_write_inventory_quantity_or_events()
    test_custom_name_patch_preserves_omitted_metadata_and_identity_side_effects()
    test_single_stock_threshold_patch_validates_against_omitted_existing_threshold()
    test_unsupported_product_knowledge_fields_are_not_silently_accepted()
    print("ARTICLE_DETAIL_MEMBER_READONLY_CONTRACT_GREEN")
    print("ARTICLE_DETAIL_SUBTABS_CONTRACT_GREEN")
    print("ARTICLE_DETAIL_MUTATION_CONTRACT_GREEN")


if __name__ == "__main__":
    run_contract()
