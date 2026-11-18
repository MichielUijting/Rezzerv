"""Classification workqueue: canonical identity and page-first read contract."""
from app.services.article_workqueue_service import (
    CLASSIFICATION_SQL, project_classification_tasks,
)


def test_sql_limits_products_before_relationship_joins():
    sql = CLASSIFICATION_SQL.lower()
    assert "with requested_page as materialized" in sql
    assert sql.count("limit :limit offset :offset") == 1
    assert sql.index("limit :limit offset :offset") < sql.index("left join global_product_gpc_bricks")
    assert sql.index("limit :limit offset :offset") < sql.index("left join global_product_cbs_classifications")
    assert "join requested_page page on page.id = e.global_product_id" in sql
    assert "join requested_page page on page.id = s.left_product_id" in sql
    assert "join requested_page page on page.id = s.right_product_id" in sql
    assert "order by lower(page.name), page.id" in sql


def test_classification_projection_still_counts_both_systems_once_per_id():
    rows = [{
        "id": "canonical-a", "name": "Rijst", "brand": "", "primary_gtin": "",
        "gpc_code": None, "cbs_code": None, "cbs_active": False,
        "cbs_name": None, "cbs_reference_version": None, "cbs_version": None,
        "confirmed_source_links": 2, "confirmed_synonyms": 1,
    }]
    items, tasks = project_classification_tasks(rows)
    assert len(items) == 1
    assert {item["key"] for item in tasks} == {"canonical-a:gpc", "canonical-a:cbs"}
    assert items[0]["confirmed_source_links"] == 2
    assert items[0]["confirmed_synonyms"] == 1


def test_duplicate_product_identity_is_not_silently_collapsed():
    row = {
        "id": "canonical-a", "name": "Rijst", "brand": "", "primary_gtin": "",
        "gpc_code": None, "cbs_code": None, "cbs_active": False,
        "cbs_name": None, "cbs_reference_version": None, "cbs_version": None,
        "confirmed_source_links": 0, "confirmed_synonyms": 0,
    }
    import pytest
    with pytest.raises(ValueError, match="dubbele"):
        project_classification_tasks([row, row])
