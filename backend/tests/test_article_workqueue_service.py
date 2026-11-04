"""Fail-closed identity projections; no live or household database used."""
import pytest

from app.services.article_workqueue_service import (
    project_classification_tasks,
    project_identification_tasks,
    load_classification_workqueue,
)


def product(product_id="p1", **overrides):
    data = {
        "id": product_id, "name": "Melk", "brand": "", "primary_gtin": "",
        "gpc_code": "", "cbs_code": "", "cbs_reference_version": "",
        "cbs_version": 0, "cbs_active": False, "cbs_name": "",
        "confirmed_source_links": 3, "confirmed_synonyms": 2,
    }
    data.update(overrides)
    return data


def test_unique_gpc_and_cbs_tasks_are_not_receipt_or_synonym_tasks():
    items, tasks = project_classification_tasks([
        product("p1"), product("p2", gpc_code="10000001"),
        product("p3", cbs_active=True, cbs_code="011420",
                cbs_reference_version="CBS-2026", cbs_version=2),
    ])
    assert len(items) == 3
    assert [(task["global_product_id"], task["system"]) for task in tasks] == [
        ("p1", "gpc"), ("p1", "cbs"), ("p2", "cbs"), ("p3", "gpc")
    ]
    assert items[0]["confirmed_source_links"] == 3
    assert items[0]["confirmed_synonyms"] == 2
    assert items[2]["cbs_version"] == 2
    assert items[2]["cbs_status"] == "classified"


def test_duplicate_canonical_id_is_rejected_not_silently_de_duplicated():
    with pytest.raises(ValueError, match="dubbele"):
        project_classification_tasks([product("p1"), product("p1")])
    with pytest.raises(ValueError, match="productidentiteit"):
        project_classification_tasks([product("")])


def test_identity_queue_uses_exact_source_evidence_not_name_or_barcode():
    sources = [
        {"id": "r1", "retailer_code": "ah", "receipt_line_text": "Melk",
         "receipt_article_number": "1", "manual_barcode": "8712345678901",
         "link_status": "unlinked"},
        {"id": "r2", "retailer_code": "jumbo", "receipt_line_text": "Melk",
         "receipt_article_number": "1", "manual_barcode": "8712345678901",
         "link_status": "unlinked"},
        {"id": "r3", "retailer_code": "ah", "receipt_line_text": "Melk",
         "receipt_article_number": "2", "link_status": "unlinked"},
        {"id": "r4", "retailer_code": "ah", "receipt_line_text": "Melk",
         "receipt_article_number": "3", "link_status": "linked"},
    ]
    items = project_identification_tasks(sources)
    assert len(items) == 3
    assert len({item["key"] for item in items}) == 3
    assert all(item["global_product_id"] is None for item in items)
    assert all(item["status"] == "needs_identification" for item in items)


def test_duplicate_receipt_identity_fails_closed():
    record = {"id": "r1", "retailer_code": "ah",
              "receipt_line_text": "Melk", "receipt_article_number": "",
              "link_status": "unlinked"}
    with pytest.raises(ValueError, match="Dubbele"):
        project_identification_tasks([record, dict(record, id="r2")])
    with pytest.raises(ValueError, match="ontbreekt"):
        project_identification_tasks([dict(record, id="")])


class StubConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "COUNT(*) FROM global_products" in sql:
            return self

        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def mappings(self):
                return self

            def all(self):
                return self.rows

        return Rows(self.rows)

    def scalar_one(self):
        return len(self.rows)


def test_read_only_query_and_explicit_count_scopes():
    conn = StubConnection([product("p1"), product("p2", gpc_code="10000001")])
    result = load_classification_workqueue(conn)
    assert result["total"] == 2
    assert result["product_count_scope"] == "global"
    assert result["task_count_scope"] == "page"
    assert len(result["tasks"]) == 3
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in conn.statements)
    assert all("household_articles" not in sql for sql in conn.statements)
    assert all("receipt_lines" not in sql for sql in conn.statements)
