from __future__ import annotations

import gzip
import hashlib
import importlib
import os
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.maintenance.postgresql_legacy_production_adoption import (
    HEAD_REVISION,
    SQLITE_BASELINE,
    LegacyAdoptionError,
    _normalize_legacy_purchase_import_quantities,
    adopt_legacy_production_snapshot,
    classify_known_legacy_fk_drift,
)
from app.services.purchase_import_quantity_contract import (
    PurchaseImportQuantityPrecisionError,
    validate_purchase_import_quantity_raw,
)


APPROVED_QUANTITY_ID_ONE = "239ccbf1-6880-4390-9c83-cb141836f72c"
APPROVED_QUANTITY_ID_TWO = "572f88a8-1bca-4e47-ac8c-0d903188ca4b"


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


def _build_quantity_fixture(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE purchase_import_lines (
                id TEXT PRIMARY KEY,
                quantity_raw NUMERIC(10, 2) NOT NULL,
                package_count NUMERIC(12, 3),
                content_value NUMERIC(12, 3)
            )
            """
        )
        connection.executemany(
            "INSERT INTO purchase_import_lines "
            "(id, quantity_raw, package_count, content_value) VALUES (?, ?, ?, ?)",
            rows,
        )
        connection.commit()
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


def test_approved_legacy_quantity_precision_is_normalized_only_at_canonical_boundary() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "approved-quantity.sqlite"
        _build_quantity_fixture(
            path,
            [
                (APPROVED_QUANTITY_ID_ONE, "0.404", "1.234", "2.345"),
                (APPROVED_QUANTITY_ID_TWO, "1.224", "3.456", "4.567"),
                ("valid-two-decimals", "7.230", "5.678", "6.789"),
            ],
        )

        normalizations = _normalize_legacy_purchase_import_quantities(path)
        assert normalizations == [
            {
                "table": "purchase_import_lines",
                "column": "quantity_raw",
                "id": APPROVED_QUANTITY_ID_ONE,
                "source": "0.404",
                "canonical": "0.40",
            },
            {
                "table": "purchase_import_lines",
                "column": "quantity_raw",
                "id": APPROVED_QUANTITY_ID_TWO,
                "source": "1.224",
                "canonical": "1.22",
            },
        ], normalizations

        connection = sqlite3.connect(path)
        try:
            rows = {
                str(row[0]): tuple(row[1:])
                for row in connection.execute(
                    "SELECT id, quantity_raw, package_count, content_value "
                    "FROM purchase_import_lines ORDER BY id"
                ).fetchall()
            }
        finally:
            connection.close()

        assert Decimal(str(rows[APPROVED_QUANTITY_ID_ONE][0])) == Decimal("0.40"), rows
        assert Decimal(str(rows[APPROVED_QUANTITY_ID_TWO][0])) == Decimal("1.22"), rows
        assert Decimal(str(rows["valid-two-decimals"][0])) == Decimal("7.230"), rows
        assert Decimal(str(rows[APPROVED_QUANTITY_ID_ONE][1])) == Decimal("1.234"), rows
        assert Decimal(str(rows[APPROVED_QUANTITY_ID_ONE][2])) == Decimal("2.345"), rows
        assert Decimal(str(rows[APPROVED_QUANTITY_ID_TWO][1])) == Decimal("3.456"), rows
        assert Decimal(str(rows[APPROVED_QUANTITY_ID_TWO][2])) == Decimal("4.567"), rows


def test_unknown_legacy_quantity_precision_fails_before_any_normalization() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "unknown-quantity.sqlite"
        _build_quantity_fixture(
            path,
            [
                (APPROVED_QUANTITY_ID_ONE, "0.404", "1.234", "2.345"),
                ("unexpected-quantity-precision", "1.234", "3.456", "4.567"),
            ],
        )

        try:
            _normalize_legacy_purchase_import_quantities(path)
        except LegacyAdoptionError as exc:
            assert "Onbekende legacy quantity_raw precision drift" in str(exc), exc
        else:
            raise AssertionError("Unknown >2-decimal legacy quantity must fail closed")

        connection = sqlite3.connect(path)
        try:
            still_original = connection.execute(
                "SELECT quantity_raw FROM purchase_import_lines WHERE id=?",
                (APPROVED_QUANTITY_ID_ONE,),
            ).fetchone()[0]
        finally:
            connection.close()
        assert Decimal(str(still_original)) == Decimal("0.404"), still_original


def test_known_legacy_quantity_id_with_unapproved_value_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "changed-known-quantity.sqlite"
        _build_quantity_fixture(
            path,
            [(APPROVED_QUANTITY_ID_ONE, "0.405", "1.234", "2.345")],
        )
        try:
            _normalize_legacy_purchase_import_quantities(path)
        except LegacyAdoptionError as exc:
            assert "onverwachte waarde" in str(exc), exc
        else:
            raise AssertionError("Known legacy id with changed value must fail closed")


def test_runtime_quantity_contract_and_engine_guard() -> None:
    assert validate_purchase_import_quantity_raw("1") == Decimal("1")
    assert validate_purchase_import_quantity_raw("1.2") == Decimal("1.2")
    assert validate_purchase_import_quantity_raw("1.23") == Decimal("1.23")
    assert validate_purchase_import_quantity_raw("1.230") == Decimal("1.230")
    try:
        validate_purchase_import_quantity_raw("1.231")
    except PurchaseImportQuantityPrecisionError as exc:
        assert "at most 2 meaningful decimal places" in str(exc), exc
    else:
        raise AssertionError("Meaningful third decimal must be rejected")

    with tempfile.TemporaryDirectory() as directory:
        runtime_path = Path(directory) / "runtime-quantity.sqlite"
        old_url = os.environ.get("DATABASE_URL")
        old_policy = os.environ.get("REZZERV_DATASTORE_POLICY")
        os.environ["DATABASE_URL"] = f"sqlite:///{runtime_path.as_posix()}"
        os.environ["REZZERV_DATASTORE_POLICY"] = "compatibility"
        runtime_db = None
        try:
            import app.db as runtime_db_module

            runtime_db = importlib.reload(runtime_db_module)
            with runtime_db.engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE purchase_import_lines "
                        "(id TEXT PRIMARY KEY, quantity_raw NUMERIC(10,2) NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO purchase_import_lines (id, quantity_raw) "
                        "VALUES (:id, :quantity_raw)"
                    ),
                    {"id": "valid", "quantity_raw": "2.30"},
                )
                try:
                    connection.execute(
                        text(
                            "INSERT INTO purchase_import_lines (id, quantity_raw) "
                            "VALUES (:id, :quantity_raw)"
                        ),
                        {"id": "invalid", "quantity_raw": "2.301"},
                    )
                except PurchaseImportQuantityPrecisionError:
                    pass
                else:
                    raise AssertionError("Runtime engine must reject >2-decimal quantity_raw")
                count = connection.execute(
                    text("SELECT COUNT(*) FROM purchase_import_lines")
                ).scalar_one()
                assert count == 1, count
        finally:
            if runtime_db is not None:
                runtime_db.engine.dispose()
            if old_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old_url
            if old_policy is None:
                os.environ.pop("REZZERV_DATASTORE_POLICY", None)
            else:
                os.environ["REZZERV_DATASTORE_POLICY"] = old_policy


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
        assert report["application_tables"] == 88, report
        assert len(report["source_data_proofs"]) == report["source_unversioned_tables"], report
        assert report["manual_sources_added"] >= 1, report
        assert report["canonical_only_seeded_tables"].get("external_product_index", 0) > 0, report
        assert report["legacy_value_normalizations"] == [], report
        assert report["purchase_import_quantity_contract"] == {
            "maximum_meaningful_decimal_places": 2,
            "normalized_rows": 0,
            "policy": "explicit-known-legacy-values-only",
        }, report

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
            assert len(tables) == 88, len(tables)
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
    test_approved_legacy_quantity_precision_is_normalized_only_at_canonical_boundary()
    print("POSTGRESQL_LEGACY_ADOPTION_QUANTITY_NORMALIZATION_GREEN")
    test_unknown_legacy_quantity_precision_fails_before_any_normalization()
    print("POSTGRESQL_LEGACY_ADOPTION_UNKNOWN_QUANTITY_PRECISION_REJECTED_GREEN")
    test_known_legacy_quantity_id_with_unapproved_value_is_rejected()
    print("POSTGRESQL_LEGACY_ADOPTION_CHANGED_KNOWN_QUANTITY_REJECTED_GREEN")
    test_runtime_quantity_contract_and_engine_guard()
    print("PURCHASE_IMPORT_QUANTITY_RUNTIME_GUARD_GREEN")
    test_canonical_rebuild_preserves_source_and_migration_owned_data()
    print("POSTGRESQL_LEGACY_ADOPTION_CANONICAL_REBUILD_GREEN")
    print("POSTGRESQL_LEGACY_ADOPTION_SOURCE_DATA_PRESERVED_GREEN")
    print("POSTGRESQL_LEGACY_ADOPTION_MIGRATION_OWNED_DATA_GREEN")
    print("POSTGRESQL_LEGACY_ADOPTION_SELFTEST_GREEN")


if __name__ == "__main__":
    main()
