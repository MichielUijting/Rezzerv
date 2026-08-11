from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_home_exposes_superuser_tile_only_through_superuser_visibility():
    source = _read("frontend/src/features/home/HomePage.jsx")
    assert "{ key: 'superuser', label: 'Superuser'" in source
    assert "if (tile.key === 'superuser') return visibility.isPlatformSuperuser" in source
    assert "navigate('/superuser')" in source


def test_home_keeps_meldingen_for_regular_users_but_not_platform_superuser():
    source = _read("frontend/src/features/home/HomePage.jsx")
    assert "{ key: 'meldingen', label: 'Meldingen'" in source
    assert "if (tile.key === 'meldingen') return !visibility.isPlatformSuperuser" in source
    assert "if (key === 'meldingen') navigate('/meldingen')" in source
    assert "visibility.isPlatformSuperuser ? '/superuser/meldingen' : '/meldingen'" not in source


def test_superuser_route_has_dedicated_guard_and_manage_center_page():
    router = _read("frontend/src/app/router/AppRouter.jsx")
    guard = _read("frontend/src/app/router/SuperuserGuard.jsx")
    page = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    auth = _read("frontend/src/lib/authSession.js")

    assert "ProtectedSuperuser" in router
    assert "path: '/superuser'" in router
    assert "isPlatformSuperuserFromContext" in guard
    assert "Rezzerv Beheercentrum" in page
    assert "'/api/superuser/bootstrap'" in page
    assert "'/api/superuser/audit/open'" in page
    assert "alleen lezen" in page
    for label in ("Overzicht", "Huishoudens", "Gebruik", "Kassabonnen", "Systeem"):
        assert label in page
    assert "SuperuserUsageSection" in page
    assert "if (title === 'Gebruik')" in page
    assert "PLATFORM_SUPERUSER_EMAIL" not in auth
    assert "source?.is_platform_superuser" in auth


def test_superuser_usage_uses_standard_table_and_existing_data_only_contract():
    source = _read("frontend/src/features/superuser/SuperuserUsageSection.jsx")
    assert "DataTable" in source
    assert "'/api/superuser/usage'" in source
    assert "geen nieuwe gebruikers- of schermtracking toegevoegd" in source
    for label in ("Actieve gebruikers", "Kassabonnen", "Voorraadmutaties", "Meldingen", "Laatst actief"):
        assert label in source
    assert "pagination" in source
    assert "pageSize={PAGE_SIZE}" in source
    assert "onDoubleClick={() => onOpenHousehold?.(item.household_id)}" in source


def test_superuser_api_is_registered_in_server_session_runtime():
    entrypoint = _read("backend/app/session_entrypoint.py")
    assert "from app.api.superuser_routes import create_superuser_router" in entrypoint
    assert "app.include_router(create_superuser_router(legacy_main.engine))" in entrypoint
