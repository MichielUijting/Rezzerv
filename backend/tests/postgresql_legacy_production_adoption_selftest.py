from __future__ import annotations

import gzip
import hashlib
import sqlite3
import tempfile
from pathlib import Path

from app.maintenance.postgresql_legacy_production_adoption import (
    HEAD_REVISION,
    SQLITE_BASELINE,
    LegacyAdoptionError,
    adopt_legacy_production_snapshot,
    classify_known_legacy_fk_drift,
)


def _build_minimal_legacy(path: Path, *, unknown_source: bool = False) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.executescript(
        """
        CREATE TABLE households (id TEXT PRIMARY KEY, naam TEXT NOT NULL);
        CREATE TABLE household_registry (id TEXT PRIMARY KEY, naam TEXT NOT NULL);
        CREATE TABLE receipt_sources (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            type TEXT NOT NULL,
            label TEXT NOT NULL,
            source_path TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(household_id) REFERENCES households(id)
        );
        CREATE TABLE raw_receipts (
            id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL,
            source_id TEXT,
            FOREIGN KEY(household_id) REFERENCES households(id),
            FOREIGN KEY(source_id) REFERENCES receipt_sources(id)
        );
        CREATE TABLE receipt_tables (
            id TEXT PRIMARY KEY,
            raw_receipt_id TEXT NOT NULL,
            household_id TEXT NOT NULL,
            FOREIGN KEY(raw_receipt_id) REFERENCES raw_receipts(id),
            FOREIGN KEY(household_id) REFERENCES households(id)
        );
        INSERT INTO household_registry (id, naam) VALUES ('1', 'Huishouden');
        """
    )
    source_id = "1-unexpected-source" if unknown_source else "1-manual-upload"
    connection.execute(
        "INSERT INTO receipt_sources (id, household_id, type, label, is_active) "
        "VALUES (?, ?, ?, ?, ?)",
        ("1-local-folder", "1", "local_folder", "Local", 1),
    )
    connection.execute(
        "INSERT INTO raw_receipts (id, household_id, source_id) VALUES (?, ?, ?)",
        ("raw-1", "1", source_id),
    )
    connection.execute(
        "INSERT INTO receipt_tables (id, raw_receipt_id, household_id) VALUES (?, ?, ?)",
        ("receipt-1", "raw-1", "1"),
    )
    connection.commit()
    return connection


def _insert_baseline_receipt_fixture(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=OFF")
    connection.execute(
        "INSERT INTO household_registry (id, naam) VALUES (?, ?)",
        ("legacy-selftest-household", "Legacy selftest"),
    )
    connection.execute(
        """
        INSERT INTO receipt_sources (
            id, household_id, type, label, source_path, is_active
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-selftest-local-source",
            "legacy-selftest-household",
            "local_folder",
            "Legacy source",
            None,
            1,
        ),
    )
    connection.execute(
        """
        INSERT INTO raw_receipts (
            id, household_id, source_id, original_filename, mime_type,
            storage_path, sha256_hash, raw_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-selftest-raw",
            "legacy-selftest-household",
            "legacy-selftest-household-manual-upload",
            "selftest.jpg",
            "image/jpeg",
            "/legacy/selftest.jpg",
            "a" * 64,
            "imported",
        ),
    )
    connection.execute(
        """
        INSERT INTO receipt_tables (
            id, raw_receipt_id, household_id, workflow_state,
            currency, parse_status, line_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-selftest-receipt",
            "legacy-selftest-raw",
            "legacy-selftest-household",
            "active",
            "EUR",
            "parsed",
            0,
        ),
    )
    connection.commit()


def _build_baseline_production_shape(path: Path) -> None:
    with gzip.open(SQLITE_BASELINE, "rt", encoding="utf-8") as handle:
        sql = handle.read()
    connection = sqlite3.connect(path)
    try:
        connection.executescript(sql)
        _insert_baseline_receipt_fixture(connection)
    finally:
        connection.close()


def test_known_drift_is_classified() -> None:
    with tempfile.TemporaryDirectory() as directory:
        connection = _build_minimal_legacy(Path(directory) / "known.sqlite")
        try:
            report = classify_known_legacy_fk_drift(connection)
        finally:
            connection.close()
        assert report["violations"] == 4, report
        assert report["categories"] == {
            "raw_receipts.household_id->legacy-households": 1,
            "raw_receipts.source_id->missing-manual-upload": 1,
            "receipt_sources.household_id->legacy-households": 1,
            "receipt_tables.household_id->legacy-households": 1,
        }, report


def test_unknown_source_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        connection = _build_minimal_legacy(
            Path(directory) / "unknown.sqlite", unknown_source=True
        )
        try:
            try:
                classify_known_legacy_fk_drift(connection)
            except LegacyAdoptionError as exc:
                assert "Onbekende ontbrekende receipt source-parent" in str(exc), exc
            else:
                raise AssertionError("Unknown source drift must fail closed")
        finally:
            connection.close()


def test_unregistered_household_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "unregistered.sqlite"
        connection = _build_minimal_legacy(path)
        try:
            connection.execute("UPDATE household_registry SET id='different' WHERE id='1'")
            connection.commit()
            try:
                classify_known_legacy_fk_drift(connection)
            except LegacyAdoptionError as exc:
                assert "household_registry" in str(exc), exc
            else:
                raise AssertionError("Unregistered household drift must fail closed")
        finally:
            connection.close()


def test_canonical_rebuild_preserves_source_and_migration_owned_data() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "legacy-production.sqlite"
        working = root / "canonical-working.sqlite"
        _build_baseline_production_shape(source)
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()

        report = adopt_legacy_production_snapshot(
            source,
            working,
            allow_working_copy_reset=True,
        )

        assert report["recovery_mode"] == "canonical-rebuild", report
        assert report["source_sha256"] == source_sha, report
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
        assert report["source_unversioned_tables"] > 0, report
        assert report["source_rows"] > 0, report
        assert report["target_revision"] == HEAD_REVISION, report
        assert report["application_tables"] == 87, report
        assert len(report["source_data_proofs"]) == report["source_unversioned_tables"], report
        assert report["manual_sources_added"] >= 1, report
        assert report["canonical_only_seeded_tables"].get("external_product_index", 0) > 0, report

        connection = sqlite3.connect(working)
        try:
            revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()[0]
            assert revision == HEAD_REVISION, revision
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if not str(row[0]).startswith("sqlite_")
                and str(row[0]) != "alembic_version"
            }
            assert len(tables) == 87, len(tables)
            manual = connection.execute(
                """
                SELECT household_id, type
                FROM receipt_sources
                WHERE id='legacy-selftest-household-manual-upload'
                """
            ).fetchone()
            assert manual == ("legacy-selftest-household", "manual_upload"), manual
            fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
            assert fk_rows == [], fk_rows
            seed_count = connection.execute(
                "SELECT COUNT(*) FROM external_product_index"
            ).fetchone()[0]
            assert seed_count == report["canonical_only_seeded_tables"]["external_product_index"]
        finally:
            connection.close()


def main() -> None:
    test_known_drift_is_classified()
    print("POSTGRESQL_LEGACY_ADOPTION_KNOWN_DRIFT_GREEN")
    test_unknown_source_is_rejected()
    print("POSTGRESQL_LEGACY_ADOPTION_UNKNOWN_SOURCE_REJECTED_GREEN")
    test_unregistered_household_is_rejected()
    print("POSTGRESQL_LEGACY_ADOPTION_UNREGISTERED_HOUSEHOLD_REJECTED_GREEN")
    test_canonical_rebuild_preserves_source_and_migration_owned_data()
    print("POSTGRESQL_LEGACY_ADOPTION_CANONICAL_REBUILD_GREEN")
    print("POSTGRESQL_LEGACY_ADOPTION_SOURCE_DATA_PRESERVED_GREEN")
    print("POSTGRESQL_LEGACY_ADOPTION_MIGRATION_OWNED_DATA_GREEN")
    print("POSTGRESQL_LEGACY_ADOPTION_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
