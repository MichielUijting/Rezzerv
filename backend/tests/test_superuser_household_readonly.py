from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_s2_backend_exposes_only_get_household_data_routes():
    source = _read("backend/app/api/superuser_household_routes.py")
    assert '@router.get("/api/superuser/households")' in source
    assert '@router.get("/api/superuser/households/{household_id}")' in source
    assert '@router.get("/api/superuser/households/{household_id}/screens/{screen_key}")' in source
    assert "@router.post(" not in source
    assert "@router.put(" not in source
    assert "@router.patch(" not in source
    assert "@router.delete(" not in source


def test_s2_household_listing_keeps_household_zero_selectable():
    source = _read("backend/app/api/superuser_household_routes.py")
    assert "CAST({id_col} AS TEXT) <> '0'" not in source
    assert 'clauses = ["1=1"]' in source


def test_s2_never_rotates_superuser_session_into_target_household():
    source = _read("backend/app/api/superuser_household_routes.py")
    assert "rotate_active_household" not in source
    assert "create_server_session" not in source
    assert '"access": "read_only"' in source


def test_every_household_inspection_is_audited():
    source = _read("backend/app/api/superuser_household_routes.py")
    assert "superuser.households.searched" in source
    assert "superuser.household.viewed" in source
    assert "superuser.household.screen_viewed" in source
    assert "write_authorization_audit" in source


def test_s2_frontend_uses_canonical_components_and_double_click_inspector():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    assert "HouseholdsSection" in source
    assert "HouseholdInspector" in source
    assert "import DataTable from '../../ui/DataTable.jsx'" in source
    assert "import Button from '../../ui/Button.jsx'" in source
    assert "import Checkbox from '../../ui/Checkbox.jsx'" in source
    assert "import Tabs from '../../ui/Tabs.jsx'" in source
    assert "<DataTable" in source
    assert "<Button" in source
    assert "<Checkbox" in source
    assert "<Tabs" in source
    assert "onDoubleClick" in source
    assert "Dubbelklik op een huishouden" in source
    assert ">Bekijken<" not in source
    assert "Alleen lezen" in source
    assert "<button" not in source
    for label in ("Start", "Kassa", "Uitpakken", "Voorraad", "Bijna op", "Winkelen", "Prognoses", "Diagnose"):
        assert label in source


def test_s2_selection_table_contains_header_checkbox_and_stable_member_columns():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    users_heading = source.index('>Gebruikers</h2>')
    detail_tabs = source.index('HOUSEHOLD_SCREENS.map')
    assert users_heading < detail_tabs
    assert "key: 'selection'" in source
    assert 'aria-label="Selecteer alle gebruikerscategorieën"' in source
    assert "header: 'Selectie'" not in source
    assert "header: 'Gebruiker'" in source
    assert "header: 'Rol'" in source
    assert "header: 'Status'" in source
    assert "UNATTRIBUTED_KEY = '__unattributed__'" in source
    assert "selectionRows" in source
    assert "email: 'Niet aan gebruiker herleidbaar'" in source
    assert "data={selectionRows}" in source
    assert "setSelectedUserKeys([...members.map" in source
    assert "UNATTRIBUTED_KEY])" in source
    assert "const includeUnattributed = selectedUserKeys.includes(UNATTRIBUTED_KEY)" in source
    assert "if (!actorUserId) return includeUnattributed" in source
    assert "return selectedUserIds.has(actorUserId)" in source
    assert "setIncludeUnattributed" not in source
    assert "Toon items die niet aan een gebruiker herleidbaar zijn" not in source
    assert "Terug naar huishoudens" not in source
    assert "handleTopTabChange" in source
    assert "if (tab === 'Huishoudens') setSelectedHouseholdId(null)" in source


def test_s2_detail_tables_reuse_bulk_export_pagination_and_view_selectors():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    data_table_source = _read("frontend/src/ui/DataTable.jsx")
    pagination_source = _read("frontend/src/ui/Pagination.jsx")
    checkbox_source = _read("frontend/src/ui/Checkbox.jsx")

    assert 'aria-label="Selecteer alle zichtbare detailregels"' in source
    assert "exportSelectedRows" in source
    assert ">Exporteren</Button>" in source
    assert "pagination" in source
    assert "pageSize={PAGE_SIZE}" in source
    assert "showTechnicalIds" in source
    assert "Technische ID's:" in source
    assert "includeArchived" in source
    assert "Gearchiveerd:" in source
    assert "useState(false)" in source
    assert "isTechnicalKey" in source
    assert "isArchivedRow" in source

    assert "import Pagination from './Pagination.jsx'" in data_table_source
    assert "pagination = false" in data_table_source
    assert "pageSize = 10" in data_table_source
    assert "<Pagination" in data_table_source
    assert "import Button from './Button.jsx'" in pagination_source
    assert 'type="checkbox"' in checkbox_source
    assert "accentColor: '#1A3E2B'" in checkbox_source


def test_s2_diagnose_shows_attribution_coverage_for_real_household_data():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    assert "ATTRIBUTION_DIAGNOSTIC_SCREENS" in source
    assert "Gebruikersherkomst" in source
    assert "Met gebruiker" in source
    assert "Niet herleidbaar" in source
    assert "superuser-attribution-diagnostics-table" in source
    assert "met_gebruiker: metGebruiker" in source
    assert "niet_herleidbaar: rows.length - metGebruiker" in source


def test_s2_actor_attribution_is_bound_from_authoritative_server_session():
    context_source = _read("backend/app/services/session_request_context.py")
    entrypoint_source = _read("backend/app/session_entrypoint.py")
    attribution_source = _read("backend/app/services/actor_attribution_service.py")
    assert "bind_current_actor(context.user_id, context.active_household_id)" in context_source
    assert "clear_current_actor()" in context_source
    assert "install_actor_attribution_tracking(legacy_main.engine)" in entrypoint_source
    assert '"receipt_tables": "receipt"' in attribution_source
    assert '"purchase_import_batches": "unpack_batch"' in attribution_source
    assert '"inventory_events": "inventory_event"' in attribution_source
    assert "actor_object_attributions" in attribution_source
    assert "auth_audit_log" in attribution_source


def test_s2_backend_projects_actor_for_receipt_unpacking_and_inventory_events():
    source = _read("backend/app/api/superuser_household_routes.py")
    assert "def _actor_rows" in source
    assert "a.actor_user_id AS actor_user_id" in source
    assert 'conn, "receipt_tables", "receipt"' in source
    assert 'conn, "purchase_import_batches", "unpack_batch"' in source
    assert 'conn, "inventory_events", "inventory_event"' in source
    assert "CAST(a.actor_user_id AS TEXT)=:user_id" in source
    assert "ensure_actor_attribution_schema" in source


def test_s2_backend_selected_user_filter_remains_defensive_and_read_only():
    source = _read("backend/app/api/superuser_household_routes.py")
    assert "def _member_exists" in source
    assert "user_id: str | None = Query(default=None)" in source
    assert "Gebruiker behoort niet tot dit huishouden" in source
    assert 'if user_id and "user_id" not in cols:' in source
    assert 'params["user_id"] = user_id' in source


def test_s2_routes_are_registered_in_server_session_runtime():
    source = _read("backend/app/session_entrypoint.py")
    assert "create_superuser_household_router" in source
    assert "app.include_router(create_superuser_household_router(legacy_main.engine))" in source
