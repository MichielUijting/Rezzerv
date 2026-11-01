"""Canonical guard against reintroducing the deleted Externe databases v1 UI.

Keep shared `/api/external-databases/*` routes required by ED2; reject only
precisely identified old-screen wrappers.
"""
from pathlib import Path

from app.api import system_routes
from app.services import platform_feature_flag_service as flags

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"

RETIRED_ENDPOINTS = {
    ("POST", "/api/external-databases/gtin/lookup"),
    ("POST", "/api/external-databases/candidates/confirm-external"),
    ("GET", "/api/external-databases/summary"),
    ("GET", "/api/external-databases/retailers"),
    ("POST", "/api/external-databases/retailers/{retailer_code}/match-preview"),
    ("POST", "/api/external-databases/retailers/{retailer_code}/save-candidates"),
    ("GET", "/api/external-databases/receipt-items"),
    ("POST", "/api/external-databases/catalog/unlink"),
}

PRESERVED_ED2_ENDPOINTS = {
    ("GET", "/api/external-databases/articles-overview"),
    ("POST", "/api/external-databases/products/search-preview"),
    ("POST", "/api/external-databases/off/link-selected"),
    ("POST", "/api/external-databases/off/unlink-selected"),
    ("POST", "/api/external-databases/off/classify-pending"),
    ("POST", "/api/external-databases/articles/delete-selected"),
    ("POST", "/api/external-products/off/search"),
}


def _routes():
    return {
        (method, route.path)
        for route in system_routes.router.routes
        for method in (getattr(route, "methods", None) or [])
    }


def test_removed_legacy_wrappers_are_absent_but_ed2_routes_remain():
    existing = _routes()
    assert not (RETIRED_ENDPOINTS & existing)
    assert PRESERVED_ED2_ENDPOINTS <= existing


def test_only_ed2_startpage_action_is_registered():
    obsolete_flag = "action.home.externe_databases"
    assert obsolete_flag not in flags.FEATURE_FLAG_DEFINITIONS
    assert obsolete_flag not in flags.HOME_ACTION_DEFAULT_ORDER
    ed2 = flags.ACTION_HOME_EXTERNE_DATABASES_2
    assert ed2 in flags.FEATURE_FLAG_DEFINITIONS
    assert flags.FEATURE_FLAG_DEFINITIONS[ed2]["home_tile_key"] == "externe-databases-2"
    assert ed2 in flags.HOME_ACTION_DEFAULT_ORDER


def test_no_hidden_legacy_screen_route_or_imports():
    old_dir = FRONTEND / "features" / "externalDatabases"
    for filename in (
        "ExternalDatabasesPage.jsx",
        "ReceiptItemsOverview.jsx",
        "RecognitionConfirmationDetail.jsx",
        "externalDatabasesRecovery.css",
    ):
        assert not (old_dir / filename).exists(), filename
    router = (FRONTEND / "app" / "router" / "AppRouter.jsx").read_text(encoding="utf-8")
    assert "import ExternalDatabasesPage " not in router
    assert "path: '/externe-databases'," not in router
    assert "path: '/externe-databases-2'," in router
    home = (FRONTEND / "features" / "home" / "HomePage.jsx").read_text(encoding="utf-8")
    assert "'externe-databases': '/externe-databases'" not in home
    assert "'externe-databases-2': '/externe-databases-2'" in home
