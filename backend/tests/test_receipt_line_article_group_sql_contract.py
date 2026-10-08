"""Regression guard for the PostgreSQL article-group linkage 500 seen on 2026-10-08.

PostgreSQL/psycopg cannot infer a bind type used exclusively as
`CASE WHEN :article_group_id IS NULL`. The earlier query failed even when
the parameter held a non-null, valid article-group UUID.
"""
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects import postgresql


def test_receipt_line_article_group_null_check_has_explicit_postgresql_type():
    main_source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
    endpoint = main_source.split(
        'def set_purchase_import_line_article_group(', 1
    )[1].split('@app.post("/api/purchase-import-lines/{line_id}/target-location")', 1)[0]

    assert "review_decision = CASE WHEN CAST(:article_group_id AS TEXT) IS NULL" in endpoint
    assert "CASE WHEN :article_group_id IS NULL" not in endpoint


def test_article_group_update_query_compiles_with_typed_null_check():
    statement = text("""
        UPDATE purchase_import_lines
        SET selected_article_group_id = :article_group_id,
            review_decision = CASE WHEN CAST(:article_group_id AS TEXT) IS NULL
                THEN 'pending' ELSE review_decision END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :line_id
    """)
    compiled = str(statement.compile(dialect=postgresql.dialect(paramstyle="pyformat")))
    assert "CAST(%(article_group_id)s AS TEXT) IS NULL" in compiled
    assert "selected_article_group_id = %(article_group_id)s" in compiled
