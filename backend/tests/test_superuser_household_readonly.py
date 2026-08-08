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


def test_s2_frontend_uses_canonical_table_and_double_click_inspector():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    assert "HouseholdsSection" in source
    assert "HouseholdInspector" in source
    assert "import DataTable from '../../ui/DataTable.jsx'" in source
    assert "<DataTable" in source
    assert "onDoubleClick" in source
    assert "Dubbelklik op een huishouden" in source
    assert ">Bekijken<" not in source
    assert "Terug naar huishoudens" in source
    assert "Alleen lezen" in source
    for label in ("Start", "Kassa", "Uitpakken", "Voorraad", "Bijna op", "Winkelen", "Prognoses", "Diagnose"):
        assert label in source


def test_s2_routes_are_registered_in_server_session_runtime():
    source = _read("backend/app/session_entrypoint.py")
    assert "create_superuser_household_router" in source
    assert "app.include_router(create_superuser_household_router(legacy_main.engine))" in source
