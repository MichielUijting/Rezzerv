from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import uuid

from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "app" / "main.py"
MIGRATION_PATH = ROOT / "alembic" / "versions" / "20260828_03_inventory_temporal_schema_authority.py"


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _load_resolver():
    module = ast.parse(MAIN_PATH.read_text(encoding="utf-8"), filename=str(MAIN_PATH))
    node = next(
        item for item in module.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "resolve_or_create_inventory_household_article"
    )
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace = {
        "HTTPException": _HTTPException,
        "normalize_household_article_name": lambda value: " ".join(str(value or "").strip().split()),
        "text": text,
        "uuid": uuid,
    }
    exec(compile(isolated, str(MAIN_PATH), "exec"), namespace)
    return namespace["resolve_or_create_inventory_household_article"]


def _load_migration():
    spec = importlib.util.spec_from_file_location("inventory_temporal_authority_review", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url, future=True)
    resolver = _load_resolver()
    migration = _load_migration()

    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TEMP TABLE household_articles (
                id TEXT PRIMARY KEY,
                household_id TEXT NOT NULL,
                naam TEXT,
                custom_name TEXT,
                status TEXT,
                created_at TIMESTAMPTZ
            ) ON COMMIT DROP
        """))
        connection.execute(text("""
            INSERT INTO household_articles (id, household_id, naam, status, created_at)
            VALUES ('ha-review', 'house-review', 'Melk', 'active', NOW())
        """))
        resolved = resolver(
            connection,
            household_id="house-review",
            article_name="Melk",
            preferred_household_article_id=None,
            source="review-selftest",
        )
        assert resolved == "ha-review"
    print("POSTGRESQL_INVENTORY_WRITER_FALLBACK_GREEN")

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("DROP INDEX uq_inventory_active_locationless_household_article"))
            connection.execute(text("""
                CREATE UNIQUE INDEX uq_inventory_active_locationless_household_article
                ON inventory (household_id, household_article_id)
                WHERE COALESCE(status, 'active') <> 'active'
                  AND household_article_id IS NOT NULL
                  AND space_id IS NULL
                  AND sublocation_id IS NULL
            """))
            try:
                migration._validate_locationless_identity_index(connection)
            except RuntimeError as exc:
                assert "predicate wijkt af" in str(exc)
            else:
                raise AssertionError("Malformed PostgreSQL locationless predicate was accepted")
        finally:
            transaction.rollback()
    print("POSTGRESQL_LOCATIONLESS_PREDICATE_DRIFT_REJECTED_GREEN")

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("DROP INDEX idx_inventory_events_temporal_order"))
            connection.execute(text("""
                CREATE UNIQUE INDEX idx_inventory_events_temporal_order
                ON inventory_events (household_id, household_article_id, effective_at, event_priority, id)
            """))
            try:
                migration._validate_contract(connection)
            except RuntimeError as exc:
                assert "expected_unique=False" in str(exc)
            else:
                raise AssertionError("Unique temporal index lookalike was accepted")
        finally:
            transaction.rollback()
    print("POSTGRESQL_TEMPORAL_UNIQUE_DRIFT_REJECTED_GREEN")
    print("POSTGRESQL_INVENTORY_REVIEW_SELFTEST_GREEN")
    engine.dispose()


if __name__ == "__main__":
    main()
