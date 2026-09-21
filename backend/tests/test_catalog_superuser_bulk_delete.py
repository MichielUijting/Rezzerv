from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import catalog_routes
from app.services import global_product_service, shopping_list_service
from app.services.global_product_service import get_or_create_global_product


class _Mappings:
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def mappings(self):
        return _Mappings(self._rows)


class _CatalogConnection:
    def __init__(self):
        self.products = {
            "gp-delete": {"id": "gp-delete", "status": "active"},
            "gp-keep": {"id": "gp-keep", "status": "active"},
        }

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        product_id = str(params.get("global_product_id") or "")
        if "SELECT id, status" in sql:
            row = self.products.get(product_id)
            return _Result([dict(row)] if row else [])
        if "UPDATE global_products" in sql and "status = 'deleted'" in sql:
            self.products[product_id]["status"] = "deleted"
            return _Result()
        raise AssertionError(f"Onverwachte SQL in bulk-delete contract: {sql}")


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    class _Begin:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, exc_type, exc, tb):
            return False

    def begin(self):
        return self._Begin(self.connection)


class _CaptureSearchConnection:
    def __init__(self):
        self.sql = ""

    def execute(self, statement, params=None):
        self.sql = str(statement)
        return _Result()


class _ExistingProductConnection:
    def __init__(self):
        self.update_sql = ""
        self.update_params = {}

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "SELECT id FROM global_products WHERE primary_gtin" in sql:
            return _Result([{"id": "gp-delete"}])
        if "UPDATE global_products" in sql:
            self.update_sql = sql
            self.update_params = dict(params)
            return _Result()
        raise AssertionError(f"Onverwachte SQL in reactivatiecontract: {sql}")


def _install_catalog_table_contract(monkeypatch, engine):
    monkeypatch.setattr(catalog_routes, "engine", engine)
    monkeypatch.setattr(catalog_routes, "_tables", lambda: {"global_products"})
    monkeypatch.setattr(
        catalog_routes,
        "_columns",
        lambda table_name: {
            "id",
            "name",
            "primary_gtin",
            "brand",
            "image_url",
            "source",
            "status",
            "created_at",
            "updated_at",
        } if table_name == "global_products" else set(),
    )


def test_bulk_delete_requires_real_platform_superuser(monkeypatch):
    connection = _CatalogConnection()
    _install_catalog_table_contract(monkeypatch, _Engine(connection))
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
    assert connection.products["gp-delete"]["status"] == "active"


def test_superuser_bulk_delete_soft_deletes_only_selected_rows(monkeypatch):
    connection = _CatalogConnection()
    _install_catalog_table_contract(monkeypatch, _Engine(connection))
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
    assert connection.products == {
        "gp-delete": {"id": "gp-delete", "status": "deleted"},
        "gp-keep": {"id": "gp-keep", "status": "active"},
    }


def test_catalog_projection_hides_soft_deleted_products(monkeypatch):
    monkeypatch.setattr(catalog_routes, "_tables", lambda: {"global_products"})
    monkeypatch.setattr(
        catalog_routes,
        "_columns",
        lambda table_name: {
            "id",
            "name",
            "primary_gtin",
            "brand",
            "image_url",
            "source",
            "status",
            "created_at",
            "updated_at",
        } if table_name == "global_products" else set(),
    )
    monkeypatch.setattr(catalog_routes, "_household_table", lambda: None)

    _, _, expressions = catalog_routes._catalog_projection()

    visibility = expressions["catalog_visible"].lower()
    assert "status" in visibility
    assert "deleted" in visibility
    assert "<>" in visibility


def test_deleted_exact_product_is_filtered_from_shopping_search_sql(monkeypatch):
    connection = _CaptureSearchConnection()
    monkeypatch.setattr(
        shopping_list_service,
        "_table_columns",
        lambda conn, table_name: {
            "id",
            "name",
            "primary_gtin",
            "brand",
            "image_url",
            "status",
        } if table_name == "global_products" else set(),
    )
    monkeypatch.setattr(
        shopping_list_service,
        "_global_product_type_expression",
        lambda conn: "''",
    )

    result = shopping_list_service._search_global_products(
        connection,
        query="bananen",
        limit=10,
    )

    assert result == []
    normalized_sql = " ".join(connection.sql.lower().split())
    assert "status" in normalized_sql
    assert "<> 'deleted'" in normalized_sql


def test_exact_gtin_reappearing_reactivates_soft_deleted_product(monkeypatch):
    connection = _ExistingProductConnection()
    product_columns = (
        "id",
        "primary_gtin",
        "name",
        "brand",
        "variant",
        "category",
        "size_value",
        "size_unit",
        "product_fingerprint",
        "image_url",
        "source",
        "status",
        "created_at",
        "updated_at",
    )
    monkeypatch.setattr(
        global_product_service,
        "inspect",
        lambda conn: SimpleNamespace(
            get_columns=lambda table_name: [{"name": name} for name in product_columns]
        ),
    )

    product_id = get_or_create_global_product(
        connection,
        gtin="8711111111111",
        name="Te verwijderen",
        brand="Test",
        source="test",
    )

    assert product_id == "gp-delete"
    normalized_sql = " ".join(connection.update_sql.lower().split())
    assert "status = case" in normalized_sql
    assert "= 'deleted' then :reactivation_status" in normalized_sql
    assert connection.update_params["reactivation_status"] == "active"
