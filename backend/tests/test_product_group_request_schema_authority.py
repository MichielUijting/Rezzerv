from __future__ import annotations

from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STORES = (
    BACKEND_ROOT / "app" / "services" / "product_taxonomy_store.py",
    BACKEND_ROOT / "app" / "services" / "product_inventory_group_store.py",
)
FORBIDDEN_RUNTIME_SCHEMA_SQL = (
    "CREATE TABLE",
    "CREATE INDEX",
    "ALTER TABLE",
    "PRAGMA ",
    "rowid",
)


@pytest.mark.parametrize("store_path", RUNTIME_STORES)
def test_product_group_request_stores_are_schema_validation_only(store_path: Path) -> None:
    source = store_path.read_text(encoding="utf-8")
    upper_source = source.upper()

    for forbidden in FORBIDDEN_RUNTIME_SCHEMA_SQL:
        if forbidden == "rowid":
            assert forbidden not in source.lower(), (
                f"{store_path.name} mag geen SQLite rowid-repair meer bevatten"
            )
            continue
        assert forbidden.upper() not in upper_source, (
            f"{store_path.name} bevat runtime schema-mutatie: {forbidden}"
        )


def test_product_group_schema_authority_revision_is_linear() -> None:
    migration = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260829_01_product_group_request_schema_authority.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "20260829_01"' in migration
    assert 'down_revision: Union[str, None] = "20260828_05"' in migration
