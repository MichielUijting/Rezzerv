"""Targeted identity, permission, and data-preservation regression for ED2 deletion."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from app.services import external_ed2_delete_service as service
from app.api import system_routes


def _make_database(monkeypatch, *, shared=False, with_product=True, synonym=False):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE ed2_removed_articles (
                retailer_code TEXT NOT NULL, receipt_text TEXT NOT NULL,
                external_article_code TEXT NOT NULL, removed_at TEXT NOT NULL,
                PRIMARY KEY (retailer_code, receipt_text, external_article_code))
        """))
        conn.execute(text("""
            CREATE TABLE global_products (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT)
        """))
        conn.execute(text("""
            CREATE TABLE external_article_product_links (
                id TEXT PRIMARY KEY, retailer_code TEXT, receipt_text_normalized TEXT,
                external_article_code TEXT, global_product_id TEXT,
                status TEXT, updated_at TEXT)
        """))
        conn.execute(text("CREATE TABLE receipt_history (description TEXT)"))
        conn.execute(text("INSERT INTO receipt_history VALUES ('historische bon behouden')"))
        conn.execute(text("CREATE TABLE inventory_history (description TEXT)"))
        conn.execute(text("INSERT INTO inventory_history VALUES ('voorraad behouden')"))
        if with_product:
            conn.execute(text("INSERT INTO global_products(id,status) VALUES ('gp-1','active')"))
            conn.execute(text("""
                INSERT INTO external_article_product_links
                (id,retailer_code,receipt_text_normalized,external_article_code,global_product_id,status)
                VALUES('ln-1','lidl','melk','123','gp-1','confirmed')
            """))
        if synonym:
            conn.execute(text("""
                CREATE TABLE article_synonym_links (left_product_id TEXT, right_product_id TEXT)
            """))
            conn.execute(text("INSERT INTO article_synonym_links VALUES ('gp-1', 'gp-2')"))

    rows = [
        {"id": "receipt-table-line:r1", "retailer_code": "lidl", "receipt_line_text": "Melk",
         "receipt_article_number": "123",
         "catalog_product_id": "gp-1" if with_product else ""},
    ]
    if shared:
        rows.append({
            "id": "receipt-table-line:r2", "retailer_code": "lidl",
            "receipt_line_text": "Andere melk", "receipt_article_number": "456",
            "catalog_product_id": "gp-1",
        })

    def overview(*, conn):
        hidden = set(conn.execute(text("""
            SELECT retailer_code, receipt_text, external_article_code
            FROM ed2_removed_articles
        """)).all())
        visible = [
            row for row in rows if (
                row["retailer_code"], row["receipt_line_text"], row["receipt_article_number"]
            ) not in hidden
        ]
        return {"items": visible, "total": len(visible)}

    monkeypatch.setattr(service, "engine", engine)
    monkeypatch.setattr(service, "list_all_external_articles", overview)
    return engine


def test_removal_is_atomic_and_preserves_receipts_and_inventory(monkeypatch):
    engine = _make_database(monkeypatch)
    result = service.remove_selected_ed2_articles([
        {"receipt_item_id": "receipt-table-line:r1"},
    ])
    assert result["ok"] is True
    assert result["removed_articles"] == 1
    assert result["removed_catalog_products"] == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT status FROM global_products WHERE id='gp-1'")).scalar_one() == "deleted"
        assert conn.execute(text("SELECT status FROM external_article_product_links WHERE id='ln-1'")).scalar_one() == "inactive"
        assert conn.execute(text("SELECT receipt_text FROM ed2_removed_articles")).scalar_one() == "Melk"
        assert conn.execute(text("SELECT description FROM receipt_history")).scalar_one() == "historische bon behouden"
        assert conn.execute(text("SELECT description FROM inventory_history")).scalar_one() == "voorraad behouden"


def test_unlinked_article_only_disappears_from_ed2(monkeypatch):
    engine = _make_database(monkeypatch, with_product=False)
    result = service.remove_selected_ed2_articles([{"receipt_item_id": "receipt-table-line:r1"}])
    assert result["removed_catalog_products"] == 0
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ed2_removed_articles")).scalar_one() == 1


def test_shared_catalog_identity_blocks_every_write(monkeypatch):
    engine = _make_database(monkeypatch, shared=True)
    with pytest.raises(ValueError, match="andere bonartikelen"):
        service.remove_selected_ed2_articles([{"receipt_item_id": "receipt-table-line:r1"}])
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ed2_removed_articles")).scalar_one() == 0
        assert conn.execute(text("SELECT status FROM global_products")).scalar_one() == "active"


def test_synonym_catalog_identity_blocks_every_write(monkeypatch):
    engine = _make_database(monkeypatch, synonym=True)
    with pytest.raises(ValueError, match="artikelsynoniemen"):
        service.remove_selected_ed2_articles([{"receipt_item_id": "receipt-table-line:r1"}])
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ed2_removed_articles")).scalar_one() == 0


@pytest.mark.parametrize("selection", [[], [{"receipt_item_id": ""}],
    [{"receipt_item_id": "r1"}, {"receipt_item_id": "r1"}],
    [{"receipt_item_id": "no-such-source"}]])
def test_invalid_or_stale_selection_is_fail_closed(monkeypatch, selection):
    engine = _make_database(monkeypatch)
    with pytest.raises(ValueError):
        service.remove_selected_ed2_articles(selection)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ed2_removed_articles")).scalar_one() == 0
        assert conn.execute(text("SELECT status FROM global_products")).scalar_one() == "active"


def test_delete_route_requires_catalog_superuser_not_only_external_link_permission(monkeypatch):
    def deny():
        raise HTTPException(status_code=403, detail="Alleen de superuser")
    monkeypatch.setattr(system_routes, "_require_catalog_delete_superuser", deny)
    monkeypatch.setattr(system_routes, "remove_selected_ed2_articles",
                        lambda *_: pytest.fail("Deletion must not run without superuser"))
    with pytest.raises(HTTPException) as exc:
        system_routes.external_databases_delete_selected_articles(
            {"selections": [{"receipt_item_id": "receipt-table-line:r1"}]}
        )
    assert exc.value.status_code == 403
