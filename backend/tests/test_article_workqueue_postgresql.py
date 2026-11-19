"""Issue #648: isolated PostgreSQL authority, identity and read-only contract.

Never connect to a user's Inhuis database. The test requires an explicitly
configured separate database whose name ends in '_article_workqueue_test' or '_cbs_test'.
"""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.article_workqueue_service import load_classification_workqueue


@pytest.fixture
def workqueue_database():
    url = os.environ.get("INHUIS_ARTICLE_WORKQUEUE_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("Afzonderlijke PostgreSQL-artikelwerkvoorraad-testdatabase niet ingesteld.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith(("_article_workqueue_test", "_cbs_test")):
        raise RuntimeError("Weiger niet-geisoleerde PostgreSQL-database.")
    owner = create_engine(url)
    schema = "article_workqueue_" + uuid4().hex
    with owner.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE global_products (id TEXT PRIMARY KEY, name TEXT NOT NULL, brand TEXT, primary_gtin TEXT, status TEXT)")
            conn.exec_driver_sql("CREATE TABLE global_product_gpc_bricks (global_product_id TEXT PRIMARY KEY, brick_code TEXT)")
            conn.exec_driver_sql("CREATE TABLE global_product_cbs_classifications (global_product_id TEXT PRIMARY KEY, cbs_code TEXT, reference_version TEXT, version INTEGER, is_active BOOLEAN)")
            conn.exec_driver_sql("CREATE TABLE cbs_ecoicop_categories (cbs_code TEXT, reference_version TEXT, name_nl TEXT, PRIMARY KEY(cbs_code, reference_version))")
            conn.exec_driver_sql("CREATE TABLE external_article_product_links (id TEXT PRIMARY KEY, global_product_id TEXT, status TEXT, retailer_code TEXT, receipt_text_normalized TEXT, external_article_code TEXT)")
            conn.exec_driver_sql("CREATE TABLE article_synonym_links (left_product_id TEXT, right_product_id TEXT, PRIMARY KEY(left_product_id, right_product_id))")
            conn.exec_driver_sql("""INSERT INTO global_products (id, name, status) VALUES
                ('p1', 'Melk A', 'active'), ('p2', 'Melk B', 'active'),
                ('p3', 'Melk C', 'active'), ('p4', 'Verwijderd', 'deleted')""")
            conn.exec_driver_sql("INSERT INTO global_product_gpc_bricks VALUES ('p2', '10000001')")
            conn.exec_driver_sql("INSERT INTO global_product_cbs_classifications VALUES ('p3', '011420', 'CBS-2026', 2, TRUE)")
            conn.exec_driver_sql("INSERT INTO cbs_ecoicop_categories VALUES ('011420','CBS-2026','Melk')")
            conn.exec_driver_sql("""INSERT INTO external_article_product_links VALUES
                ('l1','p1','confirmed','ah','melk a','1'),
                ('l2','p1','confirmed','jumbo','melk a','2'),
                ('l3','p1','classification_pending','lidl','melk a','3')""")
            conn.exec_driver_sql("INSERT INTO article_synonym_links VALUES ('p1','p2')")
        yield engine
    finally:
        engine.dispose()
        with owner.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        owner.dispose()


def test_postgresql_unique_two_system_tasks_with_proven_links(workqueue_database):
    with workqueue_database.connect() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
        result = load_classification_workqueue(conn)
        after = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
    assert before == after == 4
    assert result["total"] == 3  # soft-deleted products excluded
    assert len(result["items"]) == 3
    assert {task["key"] for task in result["tasks"]} == {
        "p1:gpc", "p1:cbs", "p2:cbs", "p3:gpc"
    }
    p1 = next(row for row in result["items"] if row["id"] == "p1")
    assert p1["confirmed_source_links"] == 2
    assert p1["confirmed_synonyms"] == 1
    assert not any("household" in task["key"] for task in result["tasks"])
    assert next(row for row in result["items"] if row["id"] == "p3")["cbs_version"] == 2


def test_route_denies_nonplatform_role_before_database_access(monkeypatch):
    from app.api import cbs_classification_routes as routes

    def viewer(_permission):
        return SimpleNamespace(is_platform_superuser=False, is_frontteam=False,
                               context_type="regular", user_id="household-owner")
    monkeypatch.setattr(routes, "require_platform_permission_from_session", viewer)
    with pytest.raises(HTTPException) as exc:
        routes.classification_workqueue()
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        routes.identification_workqueue()
    assert exc.value.status_code == 403


def test_superuser_context_must_be_system_context(monkeypatch):
    from app.api import cbs_classification_routes as routes

    def invalid_context(_permission):
        return SimpleNamespace(is_platform_superuser=True, is_frontteam=False,
                               context_type="regular", user_id="superuser")
    monkeypatch.setattr(routes, "require_platform_permission_from_session", invalid_context)
    with pytest.raises(HTTPException) as exc:
        routes.classification_workqueue()
    assert exc.value.status_code == 403


def test_postgresql_classification_server_paging_filters_summary_and_export(workqueue_database):
    """Execute the real SQL, not only a stub string contract, on isolated PG."""
    import csv
    from io import StringIO
    from app.services.classification_server_paging_service import (
        load_server_classification_page, load_server_classification_ids,
        load_classification_counts, build_selected_classification_csv,
    )

    with workqueue_database.connect() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
        first = load_server_classification_page(conn, limit=2, offset=0)
        second = load_server_classification_page(conn, limit=2, offset=2)
        assert first["total"] == second["total"] == 3
        assert [item["id"] for item in first["items"]] == ["p1", "p2"]
        assert [item["id"] for item in second["items"]] == ["p3"]
        assert {task["key"] for task in first["tasks"]} == {
            "p1:gpc", "p1:cbs", "p2:cbs",
        }
        p1 = first["items"][0]
        assert p1["confirmed_source_links"] == 2
        assert p1["confirmed_synonyms"] == 1

        by_name = load_server_classification_page(
            conn, limit=8, filters={"name": "Melk B"},
        )
        assert by_name["total"] == 1
        assert [item["id"] for item in by_name["items"]] == ["p2"]

        missing_gpc = load_server_classification_page(
            conn, limit=8, filters={"gpc_status": "Niet geclassificeerd"},
        )
        assert [item["id"] for item in missing_gpc["items"]] == ["p1", "p3"]
        classified_cbs = load_server_classification_page(
            conn, limit=8, filters={"cbs_status": "011420 Melk"},
        )
        assert [item["id"] for item in classified_cbs["items"]] == ["p3"]

        count = load_classification_counts(conn)
        assert count == {
            "product_total": 3, "task_total": 4,
            "task_count_scope": "global", "product_count_scope": "global",
        }

        all_ids = load_server_classification_ids(conn, limit=10)
        assert all_ids["ids"] == ["p1", "p2", "p3"]
        assert all_ids["total"] == 3

        exported = build_selected_classification_csv(conn, ["p3", "p1"])
        contents = list(csv.reader(
            StringIO(exported.decode("utf-8-sig")), delimiter=";",
        ))
        assert contents[0][:4] == ["product_id", "Artikel", "Merk", "Barcode"]
        assert [entry[0] for entry in contents[1:]] == ["p3", "p1"]
        after = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
        assert before == after == 4  # No actual writes; soft-deleted stays stored.



def test_postgresql_selected_cbs_bulk_snapshots_are_bounded_read_only(workqueue_database):
    """Real SQL in the existing disposable PostgreSQL schema, never production."""
    from app.services.classification_server_paging_service import load_selected_cbs_snapshots

    with workqueue_database.connect() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
        selected = load_selected_cbs_snapshots(conn, ["p3", "p1"])
        assert selected == {"total": 2, "items": [
            {"id": "p3", "name": "Melk C", "version": 2, "classified": True},
            {"id": "p1", "name": "Melk A", "version": 0, "classified": False},
        ]}
        with pytest.raises(ValueError, match="veranderd"):
            load_selected_cbs_snapshots(conn, ["p1", "p4"])
        with pytest.raises(ValueError, match="Dubbele"):
            load_selected_cbs_snapshots(conn, ["p1", "p1"])
        after = conn.execute(text("SELECT COUNT(*) FROM global_products")).scalar_one()
        assert before == after == 4
