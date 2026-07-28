from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "backend/app/services/gpc_article_assignment_service.py"
GUARD = ROOT / "backend/app/services/article_detail_write_guard.py"
FRONTEND = ROOT / "frontend/src/features/articles/ArticleGpcPage.jsx"
ROUTER = ROOT / "frontend/src/app/router/AppRouter.jsx"


def test_backend_routes_cover_search_read_write_and_clear():
    source = SERVICE.read_text(encoding="utf-8")
    assert '@app.get("/api/gpc/bricks")' in source
    assert '@app.get("/api/household-articles/{article_id}/gpc-brick")' in source
    assert '@app.put("/api/household-articles/{article_id}/gpc-brick")' in source
    assert '@app.delete("/api/household-articles/{article_id}/gpc-brick")' in source


def test_assignment_is_scoped_to_active_household_and_known_brick():
    source = SERVICE.read_text(encoding="utf-8")
    assert "household_id = :household_id" in source
    assert "require_inventory_write_context" in source
    assert "SELECT 1 FROM gpc_bricks WHERE brick_code" in source


def test_dutch_text_has_official_english_fallback():
    source = SERVICE.read_text(encoding="utf-8")
    assert "COALESCE((SELECT translated_text FROM gpc_translations" in source
    assert "brick_description_en" in source
    assert "tr.language_code='nl'" in source


def test_write_guard_discovers_gpc_mutations():
    source = GUARD.read_text(encoding="utf-8")
    assert '"set_household_article_gpc_brick"' in source
    assert '"clear_household_article_gpc_brick"' in source
    assert "install_gpc_article_assignment_routes(main_module)" in source


def test_frontend_exposes_search_assignment_and_article_route():
    page = FRONTEND.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    assert "Zoek op Brickcode, Nederlandse of Engelse omschrijving" in page
    assert "GPC-classificatie opgeslagen." in page
    assert "segment_description" in page
    assert "brick_description_en" in page
    assert "'/voorraad/:articleId/gpc'" in router
