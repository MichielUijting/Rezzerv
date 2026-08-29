from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text

import migration_foundation_core_selftest as foundation

HEAD_REVISION = "20260829_12"
EXPECTED_POSTGRESQL_APPLICATION_TABLES = 81
DAY_ARTICLE_EVENT_TABLE = "day_article_processing_events"


def _configure_revision_12_contract() -> None:
    foundation.HEAD_REVISION = HEAD_REVISION
    foundation.EXPECTED_POSTGRESQL_APPLICATION_TABLES = EXPECTED_POSTGRESQL_APPLICATION_TABLES
    foundation.PR2L_GPC_RESIDUAL_SCHEMA_AUTHORITY_TABLES = set(
        foundation.PR2L_GPC_RESIDUAL_SCHEMA_AUTHORITY_TABLES
    ) | {DAY_ARTICLE_EVENT_TABLE}
    foundation.EXPECTED_BOOLEAN_COLUMNS = set(foundation.EXPECTED_BOOLEAN_COLUMNS) | {
        ("spaces", "protected"),
        ("sublocations", "protected"),
    }


def _column_map(inspector, table_name: str) -> dict[str, dict]:
    return {
        str(column.get("name") or ""): column
        for column in inspector.get_columns(table_name)
    }


def _assert_index(
    inspector,
    table_name: str,
    index_name: str,
    columns: tuple[str, ...],
    *,
    unique: bool,
) -> None:
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes(table_name)
    }
    index = indexes.get(index_name)
    if (
        index is None
        or bool(index.get("unique")) is not unique
        or tuple(index.get("column_names") or ()) != columns
    ):
        raise AssertionError(
            f"Invalid {index_name}: expected_columns={columns!r} unique={unique} "
            f"actual={index!r}"
        )


def _assert_day_article_direct_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if DAY_ARTICLE_EVENT_TABLE not in tables:
        raise AssertionError("Alembic head is missing day_article_processing_events")

    required_columns = {
        "household_articles": {
            "default_inventory_handling",
            "inventory_handling_updated_at",
            "inventory_handling_updated_by_user_id",
        },
        "spaces": {"system_key", "protected"},
        "sublocations": {"system_key", "protected"},
        DAY_ARTICLE_EVENT_TABLE: {
            "id",
            "household_id",
            "household_article_id",
            "idempotency_key",
            "event_type",
            "quantity",
            "space_id",
            "sublocation_id",
            "actor_user_id",
            "created_at",
        },
    }
    for table_name, required in required_columns.items():
        missing = required - set(_column_map(inspector, table_name))
        if missing:
            raise AssertionError(
                f"{table_name} mist dagartikel/Direct-kolommen: {sorted(missing)}"
            )

    _assert_index(
        inspector,
        "spaces",
        "idx_spaces_household_system_key",
        ("household_id", "system_key"),
        unique=True,
    )
    _assert_index(
        inspector,
        "sublocations",
        "idx_sublocations_space_system_key",
        ("space_id", "system_key"),
        unique=True,
    )
    _assert_index(
        inspector,
        DAY_ARTICLE_EVENT_TABLE,
        "idx_day_article_events_article",
        ("household_id", "household_article_id", "created_at"),
        unique=False,
    )

    unique_sets = {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(DAY_ARTICLE_EVENT_TABLE)
    }
    unique_sets.update(
        tuple(index.get("column_names") or ())
        for index in inspector.get_indexes(DAY_ARTICLE_EVENT_TABLE)
        if bool(index.get("unique"))
    )
    if ("household_id", "idempotency_key", "event_type") not in unique_sets:
        raise AssertionError("day_article_processing_events mist idempotency uniqueness")

    checks = inspector.get_check_constraints(DAY_ARTICLE_EVENT_TABLE)
    normalized_checks = " ".join(
        str(check.get("sqltext") or "").lower()
        for check in checks
    )
    for fragment in ("event_type", "receipt", "direct_consumption"):
        if fragment not in normalized_checks:
            raise AssertionError(
                "day_article_processing_events mist event_type CHECK-contract: "
                f"missing={fragment!r} checks={checks!r}"
            )

    handling = _column_map(inspector, "household_articles")["default_inventory_handling"]
    if bool(handling.get("nullable")):
        raise AssertionError("household_articles.default_inventory_handling must be NOT NULL")

    if connection.dialect.name == "postgresql":
        for table_name in ("spaces", "sublocations"):
            protected = _column_map(inspector, table_name)["protected"]
            if not isinstance(protected["type"], sa.Boolean):
                raise AssertionError(
                    f"Expected BOOLEAN for {table_name}.protected, got {protected['type']}"
                )
            if bool(protected.get("nullable")):
                raise AssertionError(f"{table_name}.protected must be NOT NULL")

        for table_name, column_name in (
            ("household_articles", "inventory_handling_updated_at"),
            (DAY_ARTICLE_EVENT_TABLE, "created_at"),
        ):
            column_type = _column_map(inspector, table_name)[column_name]["type"]
            if not isinstance(column_type, sa.DateTime) or not bool(
                getattr(column_type, "timezone", False)
            ):
                raise AssertionError(
                    f"Expected TIMESTAMPTZ for {table_name}.{column_name}, got {column_type}"
                )
        print("POSTGRESQL_DAY_ARTICLE_DIRECT_SCHEMA_AUTHORITY_GREEN")
    else:
        print("SQLITE_DAY_ARTICLE_DIRECT_SCHEMA_AUTHORITY_GREEN")


def main() -> None:
    _configure_revision_12_contract()
    foundation.main()

    engine = create_engine(foundation._engine_url())
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision != HEAD_REVISION:
                raise AssertionError(
                    f"Expected Alembic revision {HEAD_REVISION}, got {revision}"
                )
            _assert_day_article_direct_schema(connection)
    finally:
        engine.dispose()

    print("MIGRATION_FOUNDATION_REVISION_12_GREEN")


if __name__ == "__main__":
    main()
