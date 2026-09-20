from pathlib import Path

from app.services.authorization_foundation_service import ROLE_PERMISSIONS
from app.services.product_route_household_guard import PLATFORM_ADMIN_MUTATIONS


ROOT = Path(__file__).resolve().parents[2]
ROUTES = ROOT / "backend/app/api/product_inventory_group_routes.py"


def test_off_link_uses_functional_external_product_capability_not_legacy_admin_guard():
    route_source = ROUTES.read_text(encoding="utf-8")

    assert ("POST", "/api/external-products/off/link") not in PLATFORM_ADMIN_MUTATIONS
    assert ("POST", "/api/external-products/generic/link") not in PLATFORM_ADMIN_MUTATIONS
    assert "@router.post('/api/external-products/off/link')" in route_source
    assert "@router.post('/api/external-products/generic/link')" in route_source
    assert "require_platform_permission_from_session" in route_source
    assert "'platform.external_products.link_existing'" in route_source


def test_external_link_capability_matrix_allows_frontteam_and_superuser_but_not_platform_admin():
    permission = "platform.external_products.link_existing"

    assert permission in ROLE_PERMISSIONS["platform.frontteam"]
    assert permission in ROLE_PERMISSIONS["platform.superuser"]
    assert permission not in ROLE_PERMISSIONS["platform.platform_admin"]
