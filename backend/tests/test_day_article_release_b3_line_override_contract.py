from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "app" / "api" / "day_article_routes.py"


def test_b3_line_override_routes_are_household_scoped_and_persistent():
    source = ROUTES.read_text(encoding="utf-8")

    assert "purchase_import_line_inventory_handling_overrides" in source
    assert "/purchase-import-lines/inventory-handling-overrides/batch" in source
    assert "/purchase-import-lines/{line_id}/inventory-handling-override" in source
    assert '_require(conn, context, "unpacking.process")' in source
    assert "_line_household_id(conn, line_id)" in source
    assert "line_household_id != str(household_id)" in source
    assert "ON CONFLICT(purchase_import_line_id) DO UPDATE" in source
    assert "DELETE FROM purchase_import_line_inventory_handling_overrides" in source
    assert "inventory_handling_override moet STOCK, DIRECT_CONSUMPTION of leeg zijn" in source
