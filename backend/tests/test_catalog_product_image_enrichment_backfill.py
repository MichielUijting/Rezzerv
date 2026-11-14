from pathlib import Path

from app.services.catalog_product_image_backfill_service import (
    backfill_catalog_product_images_from_enrichments,
)


class _Mappings:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return _Mappings(self._rows)


class _Connection:
    def __init__(self):
        self.updated = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = dict(params or {})
        if sql.startswith("SELECT pe.global_product_id, pe.image_url FROM product_enrichments"):
            return _Result(
                rows=[
                    {
                        "global_product_id": "gp-1",
                        "image_url": "https://images.example.test/newest.jpg",
                    },
                    {
                        "global_product_id": "gp-1",
                        "image_url": "https://images.example.test/older.jpg",
                    },
                    {
                        "global_product_id": "gp-2",
                        "image_url": "https://images.example.test/other.jpg",
                    },
                ]
            )
        if sql.startswith("UPDATE global_products SET image_url = :image_url"):
            self.updated.append((params["global_product_id"], params["image_url"]))
            return _Result(rowcount=1)
        raise AssertionError(f"Onverwachte SQL: {sql}")


class _Begin:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _Begin(self.conn)


def test_backfill_uses_latest_stored_image_once_per_catalog_product():
    conn = _Connection()

    updated = backfill_catalog_product_images_from_enrichments(_Engine(conn))

    assert updated == 2
    assert conn.updated == [
        ("gp-1", "https://images.example.test/newest.jpg"),
        ("gp-2", "https://images.example.test/other.jpg"),
    ]


def test_runtime_sync_persists_image_without_overwriting_existing_catalog_photo():
    source = (
        Path(__file__).resolve().parents[1] / "app" / "main.py"
    ).read_text(encoding="utf-8")

    assert "NULLIF(trim(CAST(:image_url AS TEXT)), '')" in source
    assert "'image_url': normalize_optional_text_field((enrichment or {}).get('image_url'))" in source
    assert "materialize_household_representative_images(conn, linked_household_article_ids)" in source
    assert "backfill_catalog_product_images_from_enrichments(engine)" in source


# Delayed OFF enrichment uses only exact, verified CENTRAL Catalogus identities.
from contextlib import contextmanager

from app.services.catalog_photo_refresh_service import (
    _trusted_off_image_url,
    refresh_missing_catalog_photos,
)


class PhotoResult:
    def __init__(self, *, rows=(), rowcount=0):
        self.rows = list(rows)
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return self.rows


class PhotoConnection:
    def __init__(self, state):
        self.state = state

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = dict(params or {})
        if sql.startswith("SELECT id, primary_gtin FROM global_products"):
            return PhotoResult(rows=[
                {"id": key, "primary_gtin": value["gtin"]}
                for key, value in sorted(self.state.items())
                if not value["image"]
            ])
        if sql.startswith("UPDATE global_products SET image_url = :image_url"):
            current = self.state[params["product_id"]]
            if current["image"] or current["gtin"] != params["gtin"]:
                return PhotoResult(rowcount=0)
            current["image"] = params["image_url"]
            return PhotoResult(rowcount=1)
        raise AssertionError(f"Unrecognized photo SQL: {sql}")


class PhotoEngine:
    def __init__(self, state):
        self.state = state

    @contextmanager
    def connect(self):
        yield PhotoConnection(self.state)

    @contextmanager
    def begin(self):
        yield PhotoConnection(self.state)


def test_off_photo_refresh_updates_only_empty_verified_gtin_and_is_idempotent():
    gtin = "8718265614512"
    state = {"product-1": {"gtin": gtin, "image": ""}}
    engine = PhotoEngine(state)
    calls = []
    def lookup(value):
        calls.append(value)
        return {"status": "found", "gtin": value, "product": {
            "image_url": "https://images.openfoodfacts.org/images/products/test.jpg"
        }}
    attempted = set()
    first = refresh_missing_catalog_photos(engine, lookup=lookup, attempted=attempted)
    second = refresh_missing_catalog_photos(engine, lookup=lookup, attempted=attempted)
    assert first["updated"] == 1
    assert second["queried"] == 0
    assert calls == [gtin]
    assert state["product-1"]["image"] == "https://images.openfoodfacts.org/images/products/test.jpg"


def test_off_photo_refresh_never_accepts_untrusted_url_or_wrong_off_gtin():
    gtin = "8718265614512"
    state = {"one": {"gtin": gtin, "image": ""}}
    for off_gtin, url in (
        (gtin, "https://unknown.example.org/photo.jpg"),
        ("8718907974196", "https://images.openfoodfacts.org/photo.jpg"),
    ):
        result = refresh_missing_catalog_photos(
            PhotoEngine(state),
            lookup=lambda _code: {"status": "found", "gtin": off_gtin,
                                  "product": {"image_url": url}},
        )
        assert result["updated"] == 0
        assert state["one"]["image"] == ""


def test_off_photo_refresh_does_not_retry_outage_as_not_found():
    gtin = "8718265614512"
    state = {"one": {"gtin": gtin, "image": ""}}
    attempted = set()
    result = refresh_missing_catalog_photos(
        PhotoEngine(state), attempted=attempted,
        lookup=lambda _code: {"status": "external_source_unavailable", "product": None},
    )
    assert result["unavailable"] == 1
    assert result["queried"] == 0
    assert attempted == set()
    assert state["one"]["image"] == ""


def test_off_photo_refresh_rejects_invalid_barcode_without_network():
    state = {"one": {"gtin": "123", "image": ""}}
    calls = []
    result = refresh_missing_catalog_photos(
        PhotoEngine(state), lookup=lambda value: calls.append(value),
    )
    assert result["invalid_barcode"] == 1
    assert calls == []
    assert state["one"]["image"] == ""


def test_off_photo_image_url_requires_known_https_host():
    assert _trusted_off_image_url("https://images.openfoodfacts.org/a.jpg")
    for url in (
        "http://images.openfoodfacts.org/a.jpg",
        "https://images.openfoodfacts.org.evil.test/a.jpg",
        "https://images.openfoodfacts.org:bad/a.jpg",
        "https://example.org/a.jpg",
        "file:///etc/passwd",
    ):
        assert _trusted_off_image_url(url) == ""


def test_off_photo_refresh_never_replaces_concurrent_catalog_image():
    gtin = "8718265614512"
    state = {"one": {"gtin": gtin, "image": ""}}
    def lookup(value):
        state["one"]["image"] = "https://images.example.test/existing.jpg"
        return {"status": "found", "gtin": value,
                "product": {"image_url": "https://images.openfoodfacts.org/new.jpg"}}
    result = refresh_missing_catalog_photos(PhotoEngine(state), lookup=lookup)
    assert result["updated"] == 0
    assert state["one"]["image"] == "https://images.example.test/existing.jpg"
