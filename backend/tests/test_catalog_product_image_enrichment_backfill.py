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
