from __future__ import annotations

from contextlib import contextmanager

import app.services.household_representative_image_service as representative


ARTICLE_ID = "article-broccoli"
GROUP_ID = "group-broccoli"
BRICK_CODE = "10000164"


class Result:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self._row

    def all(self):
        return self._rows


class RepresentativeConnection:
    def __init__(self):
        self.state = {
            "representative_image_url": "",
            "representative_image_global_product_id": "",
            "representative_image_gpc_brick_code": "",
            "catalog_products": [
                {
                    "global_product_id": "exact-broccoli-picnic",
                    "image_url": "https://images.example.test/broccoli.jpg",
                    "gpc_brick_code": BRICK_CODE,
                    "updated_at": "2026-09-20T10:00:00",
                }
            ],
        }

    def execute(self, statement, params=None):
        sql = str(statement)
        params = dict(params or {})

        if "FROM household_articles ha" in sql and "representative_image_url" in sql:
            if self.state["representative_image_url"]:
                return Result(rows=[])
            return Result(rows=[{
                "id": ARTICLE_ID,
                "household_id": "household-a",
                "global_product_id": None,
                "article_group_id": GROUP_ID,
                "representative_image_url": "",
                "representative_image_global_product_id": "",
                "representative_image_gpc_brick_code": "",
            }])

        if "FROM article_groups ag" in sql and "JOIN gpc_bricks gb" in sql:
            return Result(rows=[{"brick_code": BRICK_CODE}])

        if "FROM global_product_gpc_bricks gpb" in sql and "JOIN global_products gp" in sql:
            candidates = [
                item for item in self.state["catalog_products"]
                if item["gpc_brick_code"] == params.get("brick_code")
            ]
            candidates.sort(key=lambda item: item["updated_at"], reverse=True)
            return Result(row=candidates[0] if candidates else None)

        if "UPDATE household_articles" in sql and "representative_image_url" in sql:
            self.state["representative_image_url"] = str(params.get("image_url") or "")
            self.state["representative_image_global_product_id"] = str(params.get("global_product_id") or "")
            self.state["representative_image_gpc_brick_code"] = str(params.get("gpc_brick_code") or "")
            return Result()

        if "FROM global_products gp" in sql and "WHERE gp.id = :global_product_id" in sql:
            return Result(row=None)

        raise AssertionError(f"Onverwachte representative-image SQL: {sql}")


def _patch_schema(monkeypatch):
    monkeypatch.setattr(
        representative,
        "_tables",
        lambda conn: {
            "household_articles",
            "article_groups",
            "gpc_bricks",
            "global_products",
            "global_product_gpc_bricks",
        },
    )

    def columns(_conn, table_name):
        mapping = {
            "household_articles": {
                "id",
                "household_id",
                "global_product_id",
                "article_group_id",
                "representative_image_url",
                "representative_image_global_product_id",
                "representative_image_gpc_brick_code",
            },
            "purchase_import_lines": set(),
        }
        return mapping.get(table_name, set())

    monkeypatch.setattr(representative, "_columns", columns)


def test_materializes_stable_household_image_from_exact_product_in_same_brick(monkeypatch):
    _patch_schema(monkeypatch)
    conn = RepresentativeConnection()

    resolved = representative.materialize_household_representative_images(
        conn,
        [ARTICLE_ID],
    )

    assert resolved == {
        ARTICLE_ID: "https://images.example.test/broccoli.jpg"
    }
    assert conn.state["representative_image_url"] == "https://images.example.test/broccoli.jpg"
    assert conn.state["representative_image_global_product_id"] == "exact-broccoli-picnic"
    assert conn.state["representative_image_gpc_brick_code"] == BRICK_CODE


def test_representative_image_remains_stable_when_another_store_product_is_added(monkeypatch):
    _patch_schema(monkeypatch)
    conn = RepresentativeConnection()

    representative.materialize_household_representative_images(conn, [ARTICLE_ID])
    conn.state["catalog_products"].append({
        "global_product_id": "exact-broccoli-ah",
        "image_url": "https://images.example.test/broccoli-ah.jpg",
        "gpc_brick_code": BRICK_CODE,
        "updated_at": "2026-09-21T10:00:00",
    })

    second = representative.materialize_household_representative_images(
        conn,
        [ARTICLE_ID],
    )

    assert second == {}
    assert conn.state["representative_image_url"] == "https://images.example.test/broccoli.jpg"
    assert conn.state["representative_image_global_product_id"] == "exact-broccoli-picnic"
