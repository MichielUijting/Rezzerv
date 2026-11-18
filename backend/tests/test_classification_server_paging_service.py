"""Read-only full-Catalogus server pagination without SQLite or live data."""
import csv
from io import StringIO

import pytest

from app.services import classification_server_paging_service as svc


def product(identifier):
    return {
        "id": identifier,
        "name": "Artikel " + identifier,
        "brand": "=Merk" if identifier == "01" else "",
        "primary_gtin": "000000000000" + identifier,
        "gpc_code": "" if identifier != "09" else "10000001",
        "cbs_code": "",
        "cbs_active": False,
        "cbs_reference_version": "",
        "cbs_version": 0,
        "cbs_name": "",
        "confirmed_source_links": 0,
        "confirmed_synonyms": 0,
    }


class QueryResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self.value


class ReadOnlyConnection:
    def __init__(self):
        self.ids = [f"{i:02d}" for i in range(1, 11)]
        self.statements = []

    def execute(self, query, params=None):
        sql = str(query)
        params = params or {}
        self.statements.append((sql, params))
        assert not any(f" {verb} " in sql.upper() for verb in
                       [" INSERT ", " UPDATE ", " DELETE ", " DROP ", " ALTER ", " TRUNCATE "])
        if sql.lstrip().startswith("SELECT COUNT(*) FROM global_products gp"):
            return QueryResult(10)
        if sql.lstrip().startswith("SELECT gp.id FROM global_products gp"):
            assert "LIMIT :limit OFFSET :offset" in sql
            assert "ORDER BY " in sql and "gp.id ASC" in sql
            return QueryResult(self.ids[params["offset"]:params["offset"] + params["limit"]])
        assert "WITH requested_page AS MATERIALIZED" in sql
        assert "product_ids" in params
        assert "IN (__[POSTCOMPILE_product_ids])" in sql
        return QueryResult([product(pid) for pid in reversed(params["product_ids"])])


def test_real_server_page_fetches_only_eight_enriched_product_identities():
    conn = ReadOnlyConnection()
    page1 = svc.load_server_classification_page(conn, offset=0, limit=8)
    assert page1["total"] == 10
    assert len(page1["items"]) == 8
    assert [row["id"] for row in page1["items"]] == conn.ids[:8]
    assert page1["task_count_scope"] == "page"
    assert len(page1["tasks"]) == 16
    assert conn.statements[2][1]["product_ids"] == conn.ids[:8]

    page2 = svc.load_server_classification_page(conn, offset=8, limit=8)
    assert len(page2["items"]) == 2
    assert [row["id"] for row in page2["items"]] == conn.ids[8:]
    assert "10:cbs" in {task["key"] for task in page2["tasks"]}

    end = svc.load_server_classification_page(conn, offset=16, limit=8)
    assert end["items"] == []
    assert len(conn.statements) == 8  # no enrichment when page is empty


def test_query_uses_parameterized_whole_catalog_filters_and_safe_sort():
    where, parameters = svc._filter_sql({
        "name": "Melk%_", "gtin": "=nietleeg", "gpc_status": "=leeg",
        "cbs_status": "niet geclassificeerd",
    })
    assert "LOWER(" in where
    assert "LIKE :filter_name" in where
    assert parameters["filter_name"] == "%melk\\%\\_%"
    assert "TRIM(" in where and "IS NOT NULL" in where
    assert "global_product_gpc_bricks" in where
    assert "global_product_cbs_classifications" in where
    assert "LIKE :filter_cbs_status" in where
    for key in svc._SORT_KEYS:
        for direction in ("asc", "desc"):
            assert "gp.id ASC" in svc._order_sql(key, direction)
    with pytest.raises(ValueError):
        svc._order_sql("gp.id;DROP TABLE global_products", "asc")
    with pytest.raises(ValueError):
        svc._order_sql("name", "sideways")
    with pytest.raises(ValueError):
        svc.load_server_classification_page(ReadOnlyConnection(), limit=9)


def test_explicit_filtered_id_selection_does_not_enrich_all_rows():
    conn = ReadOnlyConnection()
    result = svc.load_server_classification_ids(conn, offset=0, limit=10)
    assert result["ids"] == conn.ids
    assert result["total"] == 10
    assert len(conn.statements) == 2
    assert not any("requested_page" in sql for sql, _ in conn.statements)


def test_csv_export_preserves_selected_order_exact_ids_and_injection_protection():
    conn = ReadOnlyConnection()
    output = svc.build_selected_classification_csv(conn, ["02", "01"])
    assert output.startswith(b"\xef\xbb\xbf")
    reader = list(csv.reader(StringIO(output.decode("utf-8-sig")), delimiter=";"))
    assert reader[0][:4] == ["product_id", "Artikel", "Merk", "Barcode"]
    assert [row[0] for row in reader[1:]] == ["02", "01"]
    assert reader[2][2] == "'=Merk"
    assert reader[1][-2:] == ["Niet geclassificeerd", "Niet geclassificeerd"]
    assert len(conn.statements) == 1  # only selected two IDs, no full Catalogus
    with pytest.raises(ValueError, match="Dubbele"):
        svc.build_selected_classification_csv(conn, ["01", "01"])
    with pytest.raises(ValueError):
        svc.build_selected_classification_csv(conn, [])
    with pytest.raises(ValueError):
        svc.build_selected_classification_csv(conn, ["x"] * (svc.MAX_EXPORT_IDS + 1))


def test_legacy_classification_workqueue_is_still_available():
    from app.services.article_workqueue_service import load_classification_workqueue
    assert callable(load_classification_workqueue)
    assert svc.PAGE_SIZE == 8
    assert "AND gp.id IN :product_ids" in svc._SELECTED_PROJECTION_SQL
