from __future__ import annotations

from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_STORES = (
    BACKEND_ROOT / "app" / "services" / "product_taxonomy_store.py",
    BACKEND_ROOT / "app" / "services" / "product_inventory_group_store.py",
    BACKEND_ROOT / "app" / "services" / "article_group_store.py",
    BACKEND_ROOT / "app" / "services" / "household_location_onboarding_service.py",
    BACKEND_ROOT / "app" / "services" / "shopping_list_service.py",
    BACKEND_ROOT / "app" / "services" / "loyalty_stamp_transaction_service.py",
)
FORBIDDEN_RUNTIME_SCHEMA_SQL = (
    "CREATE TABLE",
    "CREATE INDEX",
    "ALTER TABLE",
    "PRAGMA ",
    "rowid",
)


@pytest.mark.parametrize("store_path", RUNTIME_STORES)
def test_core_request_stores_are_schema_validation_only(store_path: Path) -> None:
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


def test_core_request_schema_authority_revisions_are_linear() -> None:
    revisions = (
        (
            "20260829_01_product_group_request_schema_authority.py",
            "20260829_01",
            "20260828_05",
        ),
        (
            "20260829_02_article_group_request_schema_authority.py",
            "20260829_02",
            "20260829_01",
        ),
        (
            "20260829_03_onboarding_location_request_schema_authority.py",
            "20260829_03",
            "20260829_02",
        ),
        (
            "20260829_04_shopping_list_request_schema_authority.py",
            "20260829_04",
            "20260829_03",
        ),
        (
            "20260829_05_loyalty_stamp_request_schema_authority.py",
            "20260829_05",
            "20260829_04",
        ),
    )

    for filename, revision, down_revision in revisions:
        migration = (
            BACKEND_ROOT / "alembic" / "versions" / filename
        ).read_text(encoding="utf-8")
        assert f'revision: str = "{revision}"' in migration
        assert f'down_revision: Union[str, None] = "{down_revision}"' in migration
