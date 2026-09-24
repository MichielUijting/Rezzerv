from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260924_01_normalize_direct_stock_location.py"
).read_text(encoding="utf-8")


def test_migration_preserves_stock_quantity_when_direct_location_is_removed():
    assert "COALESCE(aantal, 0) + :quantity" in SOURCE
    assert "SET space_id = NULL" in SOURCE
    assert "sublocation_id = NULL" in SOURCE
    assert "AND id <> :inventory_id" in SOURCE


def test_migration_deletes_only_direct_consumption_inventory_artifacts():
    assert '_DIRECT_HANDLING = "DIRECT_CONSUMPTION"' in SOURCE
    assert "if handling == _DIRECT_HANDLING:" in SOURCE
    assert 'DELETE FROM inventory WHERE id = :inventory_id' in SOURCE
    assert "COALESCE(ha.default_inventory_handling, 'STOCK') <> :direct_handling" in SOURCE


def test_migration_clears_direct_location_projection_for_stock_history_and_imports():
    assert 'assignments = ["location_id = NULL"]' in SOURCE
    assert 'assignments.append("location_label = NULL")' in SOURCE
    assert "target_location_id" in SOURCE
    assert "suggested_location_id" in SOURCE
    assert "final_location_id" in SOURCE
    assert 'assignments.append("location_override_mode = \'cleared\'")' in SOURCE


def test_migration_supports_boolean_and_integer_direct_markers():
    assert 'isinstance(direct_column.get("type"), sa.Boolean)' in SOURCE
    assert 'COALESCE(is_direct, FALSE) = TRUE' in SOURCE
    assert 'COALESCE(is_direct, 0) <> 0' in SOURCE
