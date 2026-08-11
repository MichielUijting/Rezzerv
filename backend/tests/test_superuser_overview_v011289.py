from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_overview_route_is_superuser_protected_and_read_only():
    source = _read("backend/app/api/superuser_routes.py")
    assert '@router.get("/api/superuser/overview")' in source
    assert "_require_platform_superuser" in source
    assert '"access": "read_only"' in source
    assert 'action="superuser.overview.viewed"' in source


def test_overview_uses_only_existing_concrete_attention_signals():
    source = _read("backend/app/api/superuser_routes.py")
    assert "COALESCE(aantal, 0) < 0" in source
    assert "status IN ('Open', 'In behandeling')" in source
    assert "negatieve voorraadregel(s)" in source
    assert "open melding(en)" in source


def test_overview_reuses_existing_meldingen_route_instead_of_reimplementing_support():
    source = _read("frontend/src/features/superuser/SuperuserOverviewSection.jsx")
    assert "navigate(notificationRoute)" in source
    assert "Meldingen (" in source
    assert "'/superuser/meldingen'" in source
    assert "PlatformSupportPage" not in source
    assert "createPlatformBroadcast" not in source


def test_overview_reuses_standard_rezzerv_components():
    source = _read("frontend/src/features/superuser/SuperuserOverviewSection.jsx")
    assert "import Button from '../../ui/Button.jsx'" in source
    assert "import Card from '../../ui/Card.jsx'" in source
    assert "import DataTable from '../../ui/DataTable.jsx'" in source
    assert "<Button" in source
    assert "<Card" in source
    assert "<DataTable" in source
    assert "<button" not in source


def test_attention_table_can_open_existing_read_only_household_inspector():
    overview_source = _read("frontend/src/features/superuser/SuperuserOverviewSection.jsx")
    dashboard_source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    assert "onDoubleClick={() => onOpenHousehold?.(item.household_id)}" in overview_source
    assert "function openHouseholdFromOverview(householdId)" in dashboard_source
    assert "setSelectedHouseholdId(householdId)" in dashboard_source
    assert "setActiveTab('Huishoudens')" in dashboard_source


def test_landing_meldingen_tile_remains_until_po_migration_go():
    source = _read("frontend/src/features/home/HomePage.jsx")
    assert "{ key: 'meldingen', label: 'Meldingen'" in source
    assert "'/superuser/meldingen'" in source
