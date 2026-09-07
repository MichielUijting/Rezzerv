"""Ordered DML/bootstrap initialization performed after migration preflight."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text

from app.services.receipt_source_helper_service import configure_receipt_source_helper_service


def _normalize_receipt_source_household_id(value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("household_id is verplicht")
    return normalized


def _serialize_receipt_source_row(row: Any) -> dict[str, Any]:
    data = dict(row or {})
    if "is_active" in data:
        data["is_active"] = bool(data.get("is_active"))
    for key in ("last_scan_at", "created_at", "updated_at"):
        current = data.get(key)
        if isinstance(current, (datetime, date, time)):
            data[key] = current.isoformat()
    return data


def _configure_receipt_source_helper_runtime(engine) -> None:
    """Wire the extracted receipt-source helper at the normal runtime boundary."""

    configure_receipt_source_helper_service(
        engine=engine,
        text=text,
        normalize_household_id=_normalize_receipt_source_household_id,
        serialize_receipt_source=_serialize_receipt_source_row,
    )


def run_runtime_initialization(
    *,
    engine,
    logger,
    deactivate_incomplete_confirmed_external_links: Callable[[Any], int],
    bootstrap_auth_registry: Callable[[], None],
    migrate_legacy_household_memberships: Callable[[Any], Any],
    refresh_runtime_users_from_db: Callable[[], None],
    ensure_receipt_storage_root: Callable[[], None],
    seed_store_providers: Callable[[], None],
    ensure_household: Callable[[str], dict[str, Any]],
    ensure_default_receipt_sources: Callable[[Any, Path, str], Any],
    dedupe_receipts_for_household: Callable[[Any, str], Any],
    receipt_storage_root: Path,
) -> None:
    _configure_receipt_source_helper_runtime(engine)

    with engine.begin() as connection:
        cleanup_count = deactivate_incomplete_confirmed_external_links(connection)
    logger.info(
        "Incomplete kassabonartikelkoppelingen gedeactiveerd: %s",
        cleanup_count,
    )

    bootstrap_auth_registry()
    with engine.begin() as connection:
        migrate_legacy_household_memberships(connection)
    refresh_runtime_users_from_db()
    ensure_receipt_storage_root()
    seed_store_providers()

    admin_household = ensure_household("admin@rezzerv.local")
    admin_household_id = str(admin_household.get("id") or "1")
    ensure_default_receipt_sources(engine, receipt_storage_root, admin_household_id)
    dedupe_receipts_for_household(engine, admin_household_id)
