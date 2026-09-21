from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.api import catalog_routes
from app.services.global_product_service import get_or_create_global_product
from app.services.shopping_list_service import search_shopping_catalog


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE global_products (
                id TEXT PRIMARY KEY,
                primary_gtin TEXT,
                name TEXT NOT NULL,
                brand TEXT,
                variant TEXT,
                category TEXT,
                size_value NUMERIC,
                size_unit TEXT,
                product_fingerprint TEXT,
                image_url TEXT,
                source TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            )
        """))
        conn.execute(text("""
            INSERT INTO global_products(
                id, primary_gtin, name, brand, image_url, source, status, created_at, updated_at
            ) VALUES
              ('gp-delete', '8711111111111', 'Te verwijderen', 'Test', 'https://example.test/delete.jpg', 'user', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
              ('gp-keep', '8722222222222', 'Te behouden', 'Test', 'https://example.test/keep.jpg', 'user', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """))
    return engine


def _list_catalog():
    return catalog_routes.list_catalog(
        name="",
        brand="",
        primary_gtin="",
        catalog_kind="",
        product_type="",
        source="",
        household_article_count="",
        sort_by="name",
        sort_direction="asc",
        limit=10,
        offset=0,
    )


def test_bulk_delete_requires_real_platform_superuser(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(catalog_routes, "engine", engine)
    monkeypatch.setattr(
        catalog_routes,
        "resolve_current_server_session",
        lambda: SimpleNamespace(is_platform_superuser=False),
    )

    with pytest.raises(HTTPException) as exc:
        catalog_routes.bulk_delete_catalog_products(
            catalog_routes.CatalogBulkDeleteRequest(global_product_ids=["gp-delete"])
        )

    assert exc.value.status_code == 403
    with engine.begin() as conn:
        status = conn.execute(
            text("SELECT status FROM global_products WHERE id = 'gp-delete'")
        ).scalar_one()
    assert status == "active"


def test_superuser_bulk_delete_hides_selected_product_and_preserves_other_rows(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(catalog_routes, "engine", engine)
    monkeypatch.setattr(
        catalog_routes,
        "resolve_current_server_session",
        lambda: SimpleNamespace(is_platform_superuser=True),
    )

    result = catalog_routes.bulk_delete_catalog_products(
        catalog_routes.CatalogBulkDeleteRequest(
            global_product_ids=["gp-delete", "gp-delete", "missing-product"]
        )
    )

    assert result["deleted_count"] == 1
    assert result["deleted_ids"] == ["gp-delete"]
    assert result["not_found_ids"] == ["missing-product"]

    catalog = _list_catalog()
    assert catalog["total"] == 1
    assert [row["id"] for row in catalog["items"]] == ["gp-keep"]
    assert catalog_routes._catalog_row("gp-delete") is None

    with engine.begin() as conn:
        statuses = dict(conn.execute(
            text("SELECT id, status FROM global_products ORDER BY id")
        ).all())
    assert statuses == {"gp-delete": "deleted", "gp-keep": "active"}


def test_deleted_exact_product_is_not_offered_in_shopping_search():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE global_products SET status = 'deleted' WHERE id = 'gp-delete'"))
        deleted = search_shopping_catalog(
            conn,
            "household-1",
            scope="global_products",
            query="verwijderen",
            limit=10,
        )
        active = search_shopping_catalog(
            conn,
            "household-1",
            scope="global_products",
            query="behouden",
            limit=10,
        )

    assert deleted["items"] == []
    assert [row["source_id"] for row in active["items"]] == ["gp-keep"]


def test_exact_gtin_reappearing_reactivates_soft_deleted_product():
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text("UPDATE global_products SET status = 'deleted' WHERE id = 'gp-delete'"))
        product_id = get_or_create_global_product(
            conn,
            gtin="8711111111111",
            name="Te verwijderen",
            brand="Test",
            source="test",
        )
        status = conn.execute(
            text("SELECT status FROM global_products WHERE id = :id"),
            {"id": product_id},
        ).scalar_one()

    assert product_id == "gp-delete"
    assert status == "active"
