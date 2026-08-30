from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from app.maintenance.postgresql_legacy_production_adoption import (
    LegacyAdoptionError,
    classify_known_legacy_fk_drift,
)


def _build_legacy(path: Path, *, unknown_source: bool = False) -> sqlite3.Connection:
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
        "INSERT INTO receipt_sources (id, household_id, type, label, is_active) VALUES (?, ?, ?, ?, ?)",
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


def test_known_drift_is_classified() -> None:
    with tempfile.TemporaryDirectory() as directory:
        connection = _build_legacy(Path(directory) / "known.sqlite")
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
        connection = _build_legacy(Path(directory) / "unknown.sqlite", unknown_source=True)
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
        connection = _build_legacy(path)
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


def main() -> None:
    test_known_drift_is_classified()
    print("POSTGRESQL_LEGACY_ADOPTION_KNOWN_DRIFT_GREEN")
    test_unknown_source_is_rejected()
    print("POSTGRESQL_LEGACY_ADOPTION_UNKNOWN_SOURCE_REJECTED_GREEN")
    test_unregistered_household_is_rejected()
    print("POSTGRESQL_LEGACY_ADOPTION_UNREGISTERED_HOUSEHOLD_REJECTED_GREEN")
    print("POSTGRESQL_LEGACY_ADOPTION_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
