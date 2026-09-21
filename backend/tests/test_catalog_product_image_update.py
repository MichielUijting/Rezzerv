import base64
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import catalog_routes


class _Mappings:
    def __init__(self, rows):
        self.rows = list(rows)

    def first(self):
        return self.rows[0] if self.rows else None


class _Result:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def mappings(self):
        return _Mappings(self.rows)


class _Connection:
    def __init__(self):
        self.image_url = None
        self.updated_id = None

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}
        if sql.startswith("SELECT id, status FROM global_products"):
            return _Result([{"id": "gp-photo", "status": "active"}])
        if sql.startswith("UPDATE global_products SET image_url"):
            self.image_url = params["image_data_url"]
            self.updated_id = params["global_product_id"]
            return _Result()
        raise AssertionError(f"Onverwachte SQL: {sql}")


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


def _jpeg_data_url(payload=b"\xff\xd8\xff\xe0compressed-image"):
    return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")


def _install_catalog_contract(monkeypatch, connection):
    monkeypatch.setattr(catalog_routes, "engine", _Engine(connection))
    monkeypatch.setattr(catalog_routes, "_tables", lambda: {"global_products"})
    monkeypatch.setattr(
        catalog_routes,
        "_columns",
        lambda table_name: {"id", "image_url", "status", "updated_at"}
        if table_name == "global_products"
        else set(),
    )
    monkeypatch.setattr(
        catalog_routes,
        "require_platform_permission_from_session",
        lambda permission_key: SimpleNamespace(user_id="catalog-editor"),
    )


def test_catalog_image_update_requires_platform_catalog_update_permission(monkeypatch):
    def deny(permission_key):
        assert permission_key == "platform.catalog.update"
        raise HTTPException(status_code=403, detail="denied")

    monkeypatch.setattr(catalog_routes, "require_platform_permission_from_session", deny)

    with pytest.raises(HTTPException) as exc:
        catalog_routes.update_catalog_product_image(
            "gp-photo",
            catalog_routes.CatalogImageUpdateRequest(image_data_url=_jpeg_data_url()),
        )

    assert exc.value.status_code == 403


def test_catalog_image_update_persists_valid_compressed_image(monkeypatch):
    connection = _Connection()
    _install_catalog_contract(monkeypatch, connection)
    image_data_url = _jpeg_data_url()

    result = catalog_routes.update_catalog_product_image(
        "gp-photo",
        catalog_routes.CatalogImageUpdateRequest(image_data_url=image_data_url),
    )

    assert result["global_product_id"] == "gp-photo"
    assert result["image_url"] == image_data_url
    assert connection.updated_id == "gp-photo"
    assert connection.image_url == image_data_url


@pytest.mark.parametrize(
    "data_url",
    [
        "https://example.test/photo.jpg",
        "data:text/plain;base64,SGVsbG8=",
        "data:image/gif;base64,R0lGODlhAQABAIAAAAUEBA==",
        "data:image/jpeg;base64,bm90LWEtanBlZw==",
    ],
)
def test_catalog_image_update_rejects_invalid_image_payload(monkeypatch, data_url):
    connection = _Connection()
    _install_catalog_contract(monkeypatch, connection)

    with pytest.raises(HTTPException) as exc:
        catalog_routes.update_catalog_product_image(
            "gp-photo",
            catalog_routes.CatalogImageUpdateRequest(image_data_url=data_url),
        )

    assert exc.value.status_code == 400
    assert connection.image_url is None


def test_catalog_image_update_rejects_oversized_compressed_image(monkeypatch):
    connection = _Connection()
    _install_catalog_contract(monkeypatch, connection)
    oversized = b"\xff\xd8\xff" + (b"x" * catalog_routes.CATALOG_IMAGE_MAX_BYTES)
    image_data_url = _jpeg_data_url(oversized)

    with pytest.raises(HTTPException) as exc:
        catalog_routes.update_catalog_product_image(
            "gp-photo",
            catalog_routes.CatalogImageUpdateRequest(image_data_url=image_data_url),
        )

    assert exc.value.status_code == 413
    assert connection.image_url is None
