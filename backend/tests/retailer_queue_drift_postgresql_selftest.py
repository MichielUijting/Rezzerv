"""Real PostgreSQL repair rehearsal, CI isolated database only.

Reconstruct the proven local failure (Alembic head, missing queue) inside
the disposable GitHub Actions migration database. Never run on user data.
"""
from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    raw = os.environ.get("DATABASE_URL", "")
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Refusing retailer queue drift rehearsal outside GitHub Actions")
    parsed = make_url(raw)
    if (parsed.get_backend_name() != "postgresql"
            or parsed.database != "rezzerv_migrations"):
        raise RuntimeError("Refusing any database other than isolated rezzerv_migrations")
    engine = create_engine(parsed.set(drivername="postgresql+psycopg"))
    try:
        with engine.begin() as conn:
            assert conn.execute(text("SELECT current_database()")).scalar_one() == "rezzerv_migrations"
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261111_01"
            assert conn.execute(text("SELECT count(*) FROM retailer_import_queue")).scalar_one() == 0
            household_before = conn.execute(
                text("SELECT count(*) FROM household_articles")
            ).scalar_one()
            # Controlled, isolated reproduction of the real drift. This is
            # NEVER executed on the PO's PostgreSQL database.
            conn.execute(text("DROP TABLE retailer_import_queue"))
            conn.execute(text("""
                UPDATE alembic_version SET version_num = '20261104_01'
                WHERE version_num = '20261111_01'
            """))
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, "head")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261111_01"
            assert conn.execute(text("SELECT count(*) FROM retailer_import_queue")).scalar_one() == 0
            assert conn.execute(text("SELECT count(*) FROM household_articles")).scalar_one() == household_before
            trigger = conn.execute(text("""
                SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t
                WHERE t.tgrelid=to_regclass('retailer_import_queue')
                  AND t.tgname='inhuis_maintenance_write_gate'
                  AND NOT t.tgisinternal
            """)).scalar_one()
            assert "inhuis_maintenance_write_barrier" in trigger
        print("RETAILER_QUEUE_SCHEMA_DRIFT_REPAIR_POSTGRESQL_GREEN")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
