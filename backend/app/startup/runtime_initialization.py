"""Ordered DML/bootstrap initialization performed after migration preflight."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


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
