"""Compatibility entrypoint for strict legacy production SQLite recovery.

The production recovery implementation uses a canonical Alembic rebuild
instead of assigning an unproven historical revision to the source snapshot.
Semantic quantities are preserved exactly; there is no generic decimal-scale
normalization for quantity_raw.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from . import postgresql_legacy_production_rebuild as _rebuild
from .postgresql_legacy_production_rebuild import (
    ALEMBIC_CONFIG,
    BACKEND_ROOT,
    BASELINE_REVISION,
    EXPECTED_APPLICATION_TABLES,
    LegacyAdoptionError,
    RECEIPT_HOUSEHOLD_TABLES,
    SQLITE_BASELINE,
    SYSTEM_TABLES,
    classify_known_legacy_fk_drift,
)


HEAD_REVISION = "20260903_01"
PURCHASE_IMPORT_LINES_TABLE = "purchase_import_lines"
PURCHASE_IMPORT_QUANTITY_COLUMN = "quantity_raw"


def _legacy_quantity_decimal(value: Any, *, line_id: str) -> Decimal:
    try:
        decimal_value = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise LegacyAdoptionError(
            "purchase_import_lines.quantity_raw bevat geen geldige decimale waarde: "
            f"id={line_id!r} value={value!r}"
        ) from exc
    if not decimal_value.is_finite():
        raise LegacyAdoptionError(
            "purchase_import_lines.quantity_raw bevat geen eindige decimale waarde: "
            f"id={line_id!r} value={value!r}"
        )
    return decimal_value


def _validate_legacy_purchase_import_quantities(working_copy: Path) -> dict[str, int]:
    """Validate numeric readability without changing quantity precision."""
    validated_rows = 0
    with sqlite3.connect(str(working_copy)) as connection:
        if not _rebuild._has_table(connection, PURCHASE_IMPORT_LINES_TABLE):
            raise LegacyAdoptionError("Canonical working copy mist purchase_import_lines")
        rows = connection.execute(
            "SELECT id, quantity_raw FROM purchase_import_lines "
            "WHERE quantity_raw IS NOT NULL ORDER BY id"
        ).fetchall()
        for raw_id, raw_value in rows:
            line_id = str(raw_id or "").strip()
            _legacy_quantity_decimal(raw_value, line_id=line_id)
            validated_rows += 1
    return {"validated_rows": validated_rows, "normalized_rows": 0}


def adopt_legacy_production_snapshot(
    source: Path,
    working_copy: Path,
    *,
    allow_working_copy_reset: bool,
) -> dict[str, Any]:
    """Run strict rebuild while preserving all valid quantity precision."""
    source_path = source.expanduser().resolve(strict=True)
    working_path = working_copy.expanduser().resolve()
    source_sha_before = _rebuild._sha256_file(source_path)

    # Keep the legacy-rebuild compatibility boundary aligned with the current
    # canonical Alembic head without stamping or mutating the immutable source.
    _rebuild.HEAD_REVISION = HEAD_REVISION
    report = _rebuild.adopt_legacy_production_snapshot(
        source_path,
        working_path,
        allow_working_copy_reset=allow_working_copy_reset,
    )
    if report.get("source_sha256") != source_sha_before:
        raise LegacyAdoptionError("Canonical rebuild source SHA wijkt af")

    quantity_report = _validate_legacy_purchase_import_quantities(working_path)

    if _rebuild._sha256_file(source_path) != source_sha_before:
        raise LegacyAdoptionError("Immutable source changed during quantity validation")
    if _rebuild._revision(working_path) != HEAD_REVISION:
        raise LegacyAdoptionError(
            "Working copy revision changed after quantity validation: "
            f"{_rebuild._revision(working_path)!r}"
        )

    with sqlite3.connect(str(working_path)) as connection:
        _rebuild._assert_integrity_only(connection)
        _rebuild._assert_runtime_invariants(connection)

    report["legacy_value_normalizations"] = []
    report["purchase_import_quantity_contract"] = {
        "maximum_meaningful_decimal_places": None,
        "normalized_rows": 0,
        "validated_rows": quantity_report["validated_rows"],
        "policy": "preserve-source-precision",
    }
    report["working_copy_sha256"] = _rebuild._sha256_file(working_path)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = _rebuild._build_parser().parse_args(argv)
    report = adopt_legacy_production_snapshot(
        args.source,
        args.working_copy,
        allow_working_copy_reset=bool(args.allow_working_copy_reset),
    )
    _rebuild._write_report(report, args.report_json)
    print(
        "POSTGRESQL_LEGACY_ADOPTION_SOURCE_GREEN "
        f"sha256={report['source_sha256']} "
        f"tables={report['source_unversioned_tables']} rows={report['source_rows']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_FK_DRIFT_GREEN "
        f"violations={report['initial_foreign_key_drift']['violations']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_CANONICAL_REBUILD_GREEN "
        f"source_tables={report['source_unversioned_tables']} "
        f"target_tables={report['application_tables']} "
        f"manual_sources_added={report['manual_sources_added']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_SOURCE_DATA_PRESERVED_GREEN "
        f"tables={len(report['source_data_proofs'])}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_MIGRATION_OWNED_DATA_GREEN "
        f"seeded_tables={len(report['canonical_only_seeded_tables'])}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_QUANTITY_PRECISION_PRESERVED_GREEN "
        f"validated_rows={report['purchase_import_quantity_contract']['validated_rows']}"
    )
    print(
        "POSTGRESQL_LEGACY_ADOPTION_HEAD_GREEN "
        f"revision={report['target_revision']} tables={report['application_tables']}"
    )
    print("POSTGRESQL_LEGACY_ADOPTION_GREEN")
    return 0


__all__ = [
    "ALEMBIC_CONFIG",
    "BACKEND_ROOT",
    "BASELINE_REVISION",
    "EXPECTED_APPLICATION_TABLES",
    "HEAD_REVISION",
    "LegacyAdoptionError",
    "RECEIPT_HOUSEHOLD_TABLES",
    "SQLITE_BASELINE",
    "SYSTEM_TABLES",
    "adopt_legacy_production_snapshot",
    "classify_known_legacy_fk_drift",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
