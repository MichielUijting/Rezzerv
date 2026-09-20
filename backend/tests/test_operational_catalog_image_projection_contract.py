from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
ALIAS_POLICY = (ROOT / "backend/app/services/household_alias_policy.py").read_text(encoding="utf-8")
SHOPPING_SERVICE = (ROOT / "backend/app/services/shopping_list_service.py").read_text(encoding="utf-8")

def test_inventory_preview_projects_catalog_image_url():
    assert "COALESCE(gp.image_url, '') AS image_url" in ALIAS_POLICY
    assert "row['image_url'] = image_url" in ALIAS_POLICY

def test_almost_out_projects_catalog_image_url():
    assert "COALESCE(gp.image_url, '') AS image_url" in MAIN
    assert "'image_url': normalize_optional_text_field(article_row.get('image_url'))" in MAIN

def test_shopping_list_projects_image_only_through_canonical_household_article_link():
    assert "def _shopping_list_image_projection" in SHOPPING_SERVICE
    assert "lower(trim(COALESCE(sli.source_type, 'manual'))) = 'household_article'" in SHOPPING_SERVICE
    assert "LEFT JOIN global_products gp" in SHOPPING_SERVICE
    assert "COALESCE(gp.image_url, '') AS image_url" in SHOPPING_SERVICE
    assert 'payload["image_url"] = str(row.get("image_url") or "").strip()' in SHOPPING_SERVICE
