from pathlib import Path
import re


def test_incidental_purchase_barcode_scan_route_is_registered():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")

    assert re.search(
        r'@app\.post\("/api/articles/barcode-scan"\)\s+'
        r'def scan_article_barcode\(',
        source,
    ), "POST /api/articles/barcode-scan moet scan_article_barcode registreren"


def test_barcode_check_can_update_catalog_without_inventory_write():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")

    assert "article_name: Optional[str] = None" in source
    assert "product_name_hint=normalize_household_article_name(payload.article_name)" in source
    assert "explicit_catalog_name = normalize_household_article_name(payload.article_name)" in source
    assert "UPDATE global_products" in source
    assert "name = :name" in source
    assert "catalog_match['product']" in source
    route_start = source.index('@app.post("/api/articles/barcode-scan")')
    purchase_start = source.index('@app.post("/api/purchases/manual")', route_start)
    route_source = source[route_start:purchase_start]
    assert "apply_inventory_purchase_by_identity" not in route_source
    assert "create_inventory_event" not in route_source
