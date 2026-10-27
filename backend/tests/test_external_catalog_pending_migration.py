"""Isolated SQLite migration probes, including the legacy unnamed CHECKs."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


@pytest.mark.parametrize("named_status", [False, True])
def test_pending_migration_keeps_identity_guard_and_safe_downgrade(named_status):
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / (
        "20261027_02_external_catalog_pending_classification.py"
    )
    spec = spec_from_file_location("external_pending_schema_probe", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    constraint = "CONSTRAINT ck_external_article_product_links_status " if named_status else ""
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE external_article_product_links (
                id TEXT PRIMARY KEY, retailer_code TEXT NOT NULL,
                receipt_text_normalized TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                {constraint}CHECK (status IN ('confirmed', 'inactive')),
                CHECK (length(trim(receipt_text_normalized)) > 0)
            )
        """))
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        conn.execute(text("""
            INSERT INTO external_article_product_links
                (id, retailer_code, receipt_text_normalized, status)
            VALUES ('1', 'lidl', 'achterham', 'classification_pending')
        """))
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO external_article_product_links
                    (id, retailer_code, receipt_text_normalized, status)
                VALUES ('2', 'lidl', '', 'classification_pending')
            """))
        with pytest.raises(RuntimeError, match="Veilig gestopt"):
            migration.downgrade()
        conn.execute(text("DELETE FROM external_article_product_links WHERE id = '1'"))
        migration.downgrade()
        with pytest.raises(IntegrityError):
            conn.execute(text("""
                INSERT INTO external_article_product_links
                    (id, retailer_code, receipt_text_normalized, status)
                VALUES ('3', 'lidl', 'achterham', 'classification_pending')
            """))
