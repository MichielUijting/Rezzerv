"""Compatibility entrypoint for strict legacy production SQLite recovery.

The production recovery implementation uses a canonical Alembic rebuild
instead of assigning an unproven historical revision to the source snapshot.
After the existing exact-copy preservation proof, this compatibility boundary
may apply only explicitly approved canonical value normalizations.
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
    HEAD_REVISION,
    LegacyAdoptionError,
    RECEIPT_HOUSEHOLD_TABLES,
    SQLITE_BASELINE,
    SYSTEM_TABLES,
    classify_known_legacy_fk_drift,
)
from app.services.purchase_import_quantity_contract import (
    has_meaningful_precision_beyond_two_decimals,
)


PURCHASE_IMPORT_LINES_TABLE = "purchase_import_lines"
PURCHASE_IMPORT_QUANTITY_COLUMN = "quantity_raw"
APPROVED_LEGACY_PURCHASE_IMPORT_QUANTITY_NORMALIZATIONS = {
    "239ccbf1-6880-4390-9c83-cb141836f72c": (Decimal("0.404"), Decimal("0.40")),
    "572f88a8-1bca-4e47-ac8c-0d903188ca4b": (Decimal("1.224"), Decimal("1.22")),
}


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


def _normalize_legacy_purchase_import_quantities(working_copy: Path) -> list[dict[str, str]]:
    """Apply only the two PO-approved historical quantity normalizations.

    The scan is two-phase: every precision violation is validated before any
    row is updated, so an unknown future drift cannot cause partial cleanup.
    """

    planned: list[tuple[str, Decimal, Decimal]] = []
    with sqlite3.connect(str(working_copy)) as connection:
        if not _rebuild._has_table(connection, PURCHASE_IMPORT_LINES_TABLE):
            raise LegacyAdoptionError(
                "Canonical working copy mist purchase_import_lines"
            )

        rows = connection.execute(
            "SELECT id, quantity_raw FROM purchase_import_lines "
            "WHERE quantity_raw IS NOT NULL ORDER BY id"
        ).fetchall()

        for raw_id, raw_value in rows:
            line_id = str(raw_id or "").strip()
            decimal_value = _legacy_quantity_decimal(raw_value, line_id=line_id)
            if not has_meaningful_precision_beyond_two_decimals(decimal_value):
                continue

            approved = APPROVED_LEGACY_PURCHASE_IMPORT_QUANTITY_NORMALIZATIONS.get(line_id)
            if approved is None:
                raise LegacyAdoptionError(
                    "Onbekende legacy quantity_raw precision drift; adoption geweigerd: "
                    f"id={line_id!r} value={str(decimal_value)!r}; maximaal 2 decimalen"
                )

            expected_source, canonical_value = approved
            if decimal_value != expected_source:
                raise LegacyAdoptionError(
                    "Bekende legacy quantity_raw-id bevat een onverwachte waarde; "
                    "adoption geweigerd: "
                    f"id={line_id!r} expected={str(expected_source)!r} "
                    f"actual={str(decimal_value)!r}"
                )
            planned.append((line_id, expected_source, canonical_value))

        for line_id, _expected_source, canonical_value in planned:
            connection.execute(
                "UPDATE purchase_import_lines SET quantity_raw=? WHERE id=?",
                (str(canonical_value), line_id),
            )

        for line_id, _expected_source, canonical_value in planned:
            actual = connection.execute(
                "SELECT quantity_raw FROM purchase_import_lines WHERE id=?",
                (line_id,),
            ).fetchone()
            if actual is None:
                raise LegacyAdoptionError(
                    f"Genormaliseerde purchase_import_line verdween: {line_id!r}"
                )
            actual_decimal = _legacy_quantity_decimal(actual[0], line_id=line_id)
            if actual_decimal != canonical_value:
                raise LegacyAdoptionError(
                    "Legacy quantity_raw normalisatie kon niet worden bewezen: "
                    f"id={line_id!r} expected={str(canonical_value)!r} "
                    f"actual={str(actual_decimal)!r}"
                )
            if has_meaningful_precision_beyond_two_decimals(actual_decimal):
                raise LegacyAdoptionError(
                    "Legacy quantity_raw bleef buiten het 2-decimalencontract: "
                    f"id={line_id!r} value={str(actual_decimal)!r}"
                )

    return [
        {
            "table": PURCHASE_IMPORT_LINES_TABLE,
            "column": PURCHASE_IMPORT_QUANTITY_COLUMN,
            "id": line_id,
            "source": str(source_value),
            "canonical": str(canonical_value),
        }
        for line_id, source_value, canonical_value in planned
    ]


def adopt_legacy_production_snapshot(
    source: Path,
    working_copy: Path,
    *,
    allow_working_copy_reset: bool,
) -> dict[str, Any]:
    """Run strict rebuild first, then the explicitly approved canonical normalization."""

    source_path = source.expanduser().resolve(strict=True)
    working_path = working_copy.expanduser().resolve()
    source_sha_before = _rebuild._sha256_file(source_path)

    report = _rebuild.adopt_legacy_production_snapshot(
        source_path,
        working_path,
        allow_working_copy_reset=allow_working_copy_reset,
    )
    if report.get("source_sha256") != source_sha_before:
        raise LegacyAdoptionError(
            "Canonical rebuild source SHA wijkt af vóór quantity-normalisatie"
        )

    normalizations = _normalize_legacy_purchase_import_quantities(working_path)

    if _rebuild._sha256_file(source_path) != source_sha_before:
        raise LegacyAdoptionError(
            "Immutable source changed during approved quantity normalization"
        )
    if _rebuild._revision(working_path) != HEAD_REVISION:
        raise LegacyAdoptionError(
            f"Working copy revision changed after quantity normalization: "
            f"{_rebuild._revision(working_path)!r}"
        )

    with sqlite3.connect(str(working_path)) as connection:
        _rebuild._assert_integrity_only(connection)
        fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if fk_rows:
            raise LegacyAdoptionError(
                "Canonical working copy has FK violations after quantity normalization: "
                f"{fk_rows[:10]!r}"
            )
        _rebuild._assert_runtime_invariants(connection)

    report["legacy_value_normalizations"] = normalizations
    report["purchase_import_quantity_contract"] = {
        "maximum_meaningful_decimal_places": 2,
        "normalized_rows": len(normalizations),
        "policy": "explicit-known-legacy-values-only",
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
        "POSTGRESQL_LEGACY_ADOPTION_QUANTITY_NORMALIZATION_GREEN "
        f"normalized_rows={report['purchase_import_quantity_contract']['normalized_rows']}"
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
