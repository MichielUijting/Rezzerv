"""Compatibility entrypoint for strict legacy production SQLite recovery.

The production recovery implementation now uses a canonical Alembic rebuild
instead of assigning an unproven historical revision to the source snapshot.
This module keeps the established maintenance command/import path stable.
"""
from __future__ import annotations

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
    _application_tables,
    _assert_integrity_only,
    _build_canonical_head,
    _has_table,
    _readonly_connection,
    _revision,
    _schema_dump,
    _sha256_file,
    adopt_legacy_production_snapshot,
    classify_known_legacy_fk_drift,
    main,
)

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
