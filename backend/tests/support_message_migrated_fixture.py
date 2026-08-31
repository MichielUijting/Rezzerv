from __future__ import annotations

from sqlalchemy import text

from app.testing.postgresql_onboarding_selftest_fixture import (
    create_postgresql_runtime_test_engine,
    reset_postgresql_test_database,
)


HEAD_REVISION = "20260830_02"


def migrated_support_engine():
    """Return a clean DML-only PostgreSQL engine on the canonical Alembic head."""
    reset_postgresql_test_database()
    engine = create_postgresql_runtime_test_engine()
    with engine.connect() as conn:
        revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        if revision != HEAD_REVISION:
            engine.dispose()
            raise AssertionError(
                f"Expected Alembic revision {HEAD_REVISION}, got {revision}"
            )
    return engine
