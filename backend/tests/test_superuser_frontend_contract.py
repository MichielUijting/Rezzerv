from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_home_exposes_superuser_tile_only_through_superuser_visibility():
    source = _read("frontend/src/features/home/HomePage.jsx")
    assert "{ key: 'superuser', label: 'Superuser'" in source
    assert "if (tile.key === 'superuser') return visibility.isPlatformSuperuser" in source
    assert "navigate('/superuser')" in source


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
    assert "PLATFORM_SUPERUSER_EMAIL" not in auth
    assert "source?.is_platform_superuser" in auth


def test_superuser_api_is_registered_in_server_session_runtime():
    entrypoint = _read("backend/app/session_entrypoint.py")
    assert "from app.api.superuser_routes import create_superuser_router" in entrypoint
    assert "app.include_router(create_superuser_router(legacy_main.engine))" in entrypoint
