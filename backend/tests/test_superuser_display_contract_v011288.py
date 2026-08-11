from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_empty_detail_tables_keep_screen_column_contract():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    assert "DETAIL_SCREEN_COLUMNS" in source
    assert "kassa: ['id', 'retailer', 'winkel', 'purchase_at'" in source
    assert "const keys = [...(DETAIL_SCREEN_COLUMNS[screenKey] || [])]" in source
    assert "screenKey={screen}" in source


def test_superuser_datetime_display_stops_at_seconds():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    assert "function formatDateTimeToSeconds" in source
    assert "(\\d{2}:\\d{2}:\\d{2})" in source
    assert "formatDateTimeToSeconds(row.last_active_at)" in source
    assert "formatDateTimeToSeconds(d.last_receipt_at)" in source


def test_superuser_visible_enum_values_are_dutch():
    source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    assert "DUTCH_VALUE_LABELS" in source
    for english, dutch in (("active", "Actief"), ("new", "Nieuw"), ("reviewed", "Gecontroleerd"), ("purchase", "Aankoop")):
        assert f"{english}: '{dutch}'" in source
    assert "getValue: (row) => displayValue(key, row?.[key])" in source
    assert "getValue: (row) => dutchValue(row.status" in source


def test_bulk_export_shares_control_row_with_standard_pagination():
    superuser_source = _read("frontend/src/features/superuser/SuperuserDashboardPage.jsx")
    table_source = _read("frontend/src/ui/DataTable.jsx")
    assert "paginationActions={<Button" in superuser_source
    assert ">Exporteren</Button>" in superuser_source
    assert "paginationActions = null" in table_source
    assert 'className="rz-data-table-controls"' in table_source
    assert "gridTemplateColumns: '1fr auto 1fr'" in table_source
    assert "<Pagination page={page} pageCount={pageCount} onPageChange={setPage} />" in table_source
