from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa

from app.maintenance import postgresql_data_migration_head
from app.maintenance.postgresql_data_migration import (
    MigrationError,
    _canonical_value,
    _coerce_boolean,
    _coerce_value,
    _digest_multiset,
    _order_self_referential_rows,
    _row_digest,
    _topological_table_order,
    create_consistent_snapshot,
)


def _expect_failure(callback, fragment: str) -> None:
    try:
        callback()
    except MigrationError as exc:
        if fragment not in str(exc):
            raise AssertionError(f"Expected {fragment!r} in {exc!r}") from exc
    else:
        raise AssertionError(f"Expected MigrationError containing {fragment!r}")


def test_boolean_canonicalization() -> None:
    for value in (1, True, "1", "true", "YES", "on"):
        assert _coerce_boolean(value, label="flag") is True
    for value in (0, False, "0", "false", "No", "off"):
        assert _coerce_boolean(value, label="flag") is False
    assert _coerce_boolean(None, label="flag") is None
    _expect_failure(lambda: _coerce_boolean("maybe", label="flag"), "invalid legacy Boolean")


def test_timestamp_and_numeric_canonicalization() -> None:
    timestamp_type = sa.DateTime(timezone=True)
    actual = _coerce_value("2026-08-30T12:00:00", timestamp_type, label="created_at")
    assert actual == datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
    assert _canonical_value(actual, timestamp_type, label="created_at") == "2026-08-30T12:00:00.000000Z"
    numeric = sa.Numeric(18, 6)
    assert _coerce_value("0.10", numeric, label="quantity") == Decimal("0.10")
    assert _canonical_value(Decimal("1.000"), numeric, label="quantity") == "1"
    assert _canonical_value(Decimal("0.1000"), numeric, label="quantity") == "0.1"


def test_row_fingerprint_semantics() -> None:
    metadata = sa.MetaData()
    table = sa.Table(
        "example",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
    )
    source = {
        "id": 7,
        "enabled": 1,
        "created_at": "2026-08-30T12:00:00",
        "quantity": "0.1000",
    }
    target = {
        "id": 7,
        "enabled": True,
        "created_at": datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
        "quantity": Decimal("0.10"),
    }
    source_digest = _row_digest(source, list(table.columns), table_name="example")
    target_digest = _row_digest(target, list(table.columns), table_name="example")
    assert source_digest == target_digest
    assert _digest_multiset([source_digest, target_digest]) == _digest_multiset(
        [target_digest, source_digest]
    )


def test_dependency_order_and_cycles() -> None:
    order = _topological_table_order(
        {"parent": set(), "child": {"parent"}, "grandchild": {"child"}}
    )
    assert order.index("parent") < order.index("child") < order.index("grandchild")
    _expect_failure(
        lambda: _topological_table_order({"a": {"b"}, "b": {"a"}}),
        "foreign-key cycle",
    )


def test_self_reference_order() -> None:
    rows = [
        {"id": 3, "parent_id": 2},
        {"id": 1, "parent_id": None},
        {"id": 2, "parent_id": 1},
    ]
    fk = {
        "constrained_columns": ["parent_id"],
        "referred_columns": ["id"],
        "referred_table": "nodes",
    }
    ordered = _order_self_referential_rows(rows, [fk], table_name="nodes")
    assert [row["id"] for row in ordered] == [1, 2, 3]


def test_consistent_snapshot() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        source = Path(temporary_directory) / "source.sqlite"
        snapshot = Path(temporary_directory) / "snapshot.sqlite"
        connection = sqlite3.connect(source)
        try:
            connection.execute("CREATE TABLE example (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO example (id, value) VALUES (1, 'before')")
            connection.commit()
        finally:
            connection.close()
        digest = create_consistent_snapshot(source, snapshot)
        assert len(digest) == 64
        connection = sqlite3.connect(source)
        try:
            connection.execute("UPDATE example SET value='after' WHERE id=1")
            connection.commit()
        finally:
            connection.close()
        snapshot_connection = sqlite3.connect(snapshot)
        try:
            value = snapshot_connection.execute("SELECT value FROM example WHERE id=1").fetchone()[0]
        finally:
            snapshot_connection.close()
        assert value == "before"


def test_locked_head_snapshot_preserves_legacy_fk_drift_for_adoption() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        source = Path(temporary_directory) / "legacy-source.sqlite"
        snapshot = Path(temporary_directory) / "legacy-snapshot.sqlite"
        connection = sqlite3.connect(source)
        try:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            connection.execute(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
                "FOREIGN KEY(parent_id) REFERENCES parent(id))"
            )
            connection.execute("INSERT INTO child (id, parent_id) VALUES (1, 999)")
            connection.commit()
            assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            assert connection.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            connection.close()

        digest = postgresql_data_migration_head._create_consistent_snapshot_for_locked_head(
            source,
            snapshot,
        )
        assert len(digest) == 64

        snapshot_connection = sqlite3.connect(snapshot)
        try:
            assert snapshot_connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            violations = snapshot_connection.execute("PRAGMA foreign_key_check").fetchall()
        finally:
            snapshot_connection.close()
        assert violations


def main() -> None:
    test_boolean_canonicalization()
    print("POSTGRESQL_DATA_MIGRATION_BOOLEAN_GREEN")
    test_timestamp_and_numeric_canonicalization()
    print("POSTGRESQL_DATA_MIGRATION_TYPES_GREEN")
    test_row_fingerprint_semantics()
    print("POSTGRESQL_DATA_MIGRATION_FINGERPRINT_GREEN")
    test_dependency_order_and_cycles()
    test_self_reference_order()
    print("POSTGRESQL_DATA_MIGRATION_FK_ORDER_GREEN")
    test_consistent_snapshot()
    test_locked_head_snapshot_preserves_legacy_fk_drift_for_adoption()
    print("POSTGRESQL_DATA_MIGRATION_SNAPSHOT_SELFTEST_GREEN")
    print("POSTGRESQL_DATA_MIGRATION_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
