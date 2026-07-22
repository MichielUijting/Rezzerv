from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services.product_route_household_guard import (
    AUTHENTICATED_ROUTES,
    PLATFORM_ADMIN_MUTATIONS,
    authorize_product_route_request,
    build_store_review_articles,
    canonical_route_key,
)


def require_household_context(authorization: str | None, requested_household_id: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if authorization == "Bearer other-household" and requested_household_id == "h1":
        raise HTTPException(status_code=403, detail="Geen toegang tot huishouden")
    return {"active_household_id": requested_household_id or "h1", "display_role": "lid"}


def require_inventory_write_context(authorization: str | None, requested_household_id: str | None):
    context = require_household_context(authorization, requested_household_id)
    if authorization == "Bearer viewer":
        raise HTTPException(status_code=403, detail="Schrijfrecht vereist")
    return context


def require_platform_admin_user(authorization: str | None):
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if authorization != "Bearer platform-admin":
        raise HTTPException(status_code=403, detail="Platformbeheerder vereist")
    return {"role": "platform_admin"}


def assert_http_error(status_code: int, callback) -> None:
    try:
        callback()
    except HTTPException as exc:
        assert exc.status_code == status_code, exc
    else:
        raise AssertionError(f"HTTP {status_code} verwacht")


def run_contract() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE inventory (id TEXT PRIMARY KEY, household_id TEXT, naam TEXT)"))
        conn.execute(text("CREATE TABLE household_articles (id TEXT PRIMARY KEY, household_id TEXT, naam TEXT, consumable INTEGER, brand_or_maker TEXT)"))
        conn.execute(text("INSERT INTO inventory (id, household_id, naam) VALUES ('i-h1', 'h1', 'H1 voorraad'), ('i-h2', 'h2', 'H2 geheim')"))
        conn.execute(text("INSERT INTO household_articles (id, household_id, naam, consumable, brand_or_maker) VALUES ('a-h1', 'h1', 'H1 artikel', 1, 'Merk 1'), ('a-h2', 'h2', 'H2 geheim artikel', 1, 'Merk 2')"))

    assert canonical_route_key("PUT", "/api/product-groups/foo/bar") == (
        "PUT",
        "/api/product-groups/{inventory_group_key:path}",
    )
    assert canonical_route_key("POST", "/api/products/gp-1/inventory-group") == (
        "POST",
        "/api/products/{global_product_id}/inventory-group",
    )

    with engine.begin() as conn:
        for method, template_path in sorted(PLATFORM_ADMIN_MUTATIONS):
            path = template_path.replace("{inventory_group_key:path}", "groep/x").replace("{global_product_id}", "gp-1")
            assert_http_error(
                401,
                lambda method=method, path=path: authorize_product_route_request(
                    conn, method, path, None, None,
                    require_household_context, require_inventory_write_context, require_platform_admin_user,
                ),
            )
            assert_http_error(
                403,
                lambda method=method, path=path: authorize_product_route_request(
                    conn, method, path, "Bearer household-user", None,
                    require_household_context, require_inventory_write_context, require_platform_admin_user,
                ),
            )
            result = authorize_product_route_request(
                conn, method, path, "Bearer platform-admin", None,
                require_household_context, require_inventory_write_context, require_platform_admin_user,
            )
            assert result == {"role": "platform_admin"}

        for method, path in sorted(AUTHENTICATED_ROUTES):
            assert_http_error(
                401,
                lambda method=method, path=path: authorize_product_route_request(
                    conn, method, path, None, None,
                    require_household_context, require_inventory_write_context, require_platform_admin_user,
                ),
            )
            result = authorize_product_route_request(
                conn, method, path, "Bearer household-user", None,
                require_household_context, require_inventory_write_context, require_platform_admin_user,
            )
            assert result["active_household_id"] == "h1"

        assert_http_error(
            403,
            lambda: authorize_product_route_request(
                conn, "GET", "/api/inventory/groups", "Bearer other-household", "h1",
                require_household_context, require_inventory_write_context, require_platform_admin_user,
            ),
        )
        result = authorize_product_route_request(
            conn, "GET", "/api/inventory/groups", "Bearer household-user", "h1",
            require_household_context, require_inventory_write_context, require_platform_admin_user,
        )
        assert result["active_household_id"] == "h1"

        assert_http_error(
            403,
            lambda: authorize_product_route_request(
                conn, "POST", "/api/inventory/items/i-h1/group", "Bearer viewer", None,
                require_household_context, require_inventory_write_context, require_platform_admin_user,
            ),
        )
        result = authorize_product_route_request(
            conn, "POST", "/api/inventory/items/i-h1/group", "Bearer household-user", None,
            require_household_context, require_inventory_write_context, require_platform_admin_user,
        )
        assert result["active_household_id"] == "h1"
        assert_http_error(
            403,
            lambda: authorize_product_route_request(
                conn, "POST", "/api/inventory/items/i-h1/group", "Bearer other-household", None,
                require_household_context, require_inventory_write_context, require_platform_admin_user,
            ),
        )

    fake_module = SimpleNamespace(
        engine=engine,
        MOCK_ARTICLE_OPTIONS=[{"id": "mock", "name": "Mock artikel", "brand": "", "consumable": True}],
        get_household_article_location_defaults=lambda conn, ids: {},
        infer_consumable_from_name=lambda name: True,
        build_live_article_option_id=lambda name: f"live:{name.lower()}",
    )
    h1_items = build_store_review_articles(fake_module, "h1", "")
    names = {item["name"] for item in h1_items}
    assert "H1 artikel" in names
    assert "H1 voorraad" in names
    assert "H2 geheim artikel" not in names
    assert "H2 geheim" not in names
    filtered = build_store_review_articles(fake_module, "h1", "voorraad")
    assert [item["name"] for item in filtered] == ["H1 voorraad"]

    print("PRODUCT_ROUTE_HOUSEHOLD_GUARD_GREEN")


if __name__ == "__main__":
    run_contract()
