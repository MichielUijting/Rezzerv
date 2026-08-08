"""Controlled migration of legacy household-article identities.

Slice 2B1 only inventories and migrates historical references. It deliberately
leaves API canonisation and resolver removal to later slices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine


LIVE_PREFIX = "live::"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class TargetReport:
    table: str
    column: str
    already_canonical: int = 0
    migrated: int = 0
    unresolved: int = 0
    ambiguous: int = 0
    skipped_missing_schema: bool = False
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MigrationReport:
    dry_run: bool
    targets: list[TargetReport] = field(default_factory=list)

    @property
    def already_canonical(self) -> int:
        return sum(item.already_canonical for item in self.targets)

    @property
    def migrated(self) -> int:
        return sum(item.migrated for item in self.targets)

    @property
    def unresolved(self) -> int:
        return sum(item.unresolved for item in self.targets)

    @property
    def ambiguous(self) -> int:
        return sum(item.ambiguous for item in self.targets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "already_canonical": self.already_canonical,
            "migrated": self.migrated,
            "unresolved": self.unresolved,
            "ambiguous": self.ambiguous,
            "targets": [item.to_dict() for item in self.targets],
        }


@dataclass(frozen=True)
class Target:
    table: str
    column: str
    household_join: str
    household_expression: str


TARGETS = (
    Target(
        "purchase_import_lines",
        "matched_household_article_id",
        "JOIN purchase_import_batches pib ON pib.id = src.batch_id",
        "pib.household_id",
    ),
    Target(
        "purchase_import_lines",
        "suggested_household_article_id",
        "JOIN purchase_import_batches pib ON pib.id = src.batch_id",
        "pib.household_id",
    ),
    Target("store_import_memory", "matched_household_article_id", "", "src.household_id"),
    Target("inventory", "household_article_id", "", "src.household_id"),
    Target(
        "inventory_events",
        "household_article_id",
        "LEFT JOIN inventory inv ON inv.id = src.inventory_id",
        "COALESCE(src.household_id, inv.household_id)",
    ),
)


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def _normalize_name(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _columns(conn: Connection, table_name: str) -> set[str]:
    inspector = inspect(conn)
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name)}


def _article_name_column(conn: Connection) -> str:
    available = _columns(conn, "household_articles")
    for candidate in ("naam", "custom_name", "name"):
        if candidate in available:
            return candidate
    raise RuntimeError("household_articles has no supported name column")


def _target_supported(conn: Connection, target: Target) -> bool:
    source_columns = _columns(conn, target.table)
    if not source_columns or target.column not in source_columns or "id" not in source_columns:
        return False
    if target.table == "purchase_import_lines":
        return bool(_columns(conn, "purchase_import_batches")) and "batch_id" in source_columns
    if target.table == "inventory_events":
        return "household_id" in source_columns or "inventory_id" in source_columns
    return "household_id" in source_columns


def _effective_inventory_events_target(conn: Connection, target: Target) -> Target:
    if target.table != "inventory_events":
        return target
    columns = _columns(conn, "inventory_events")
    if "household_id" in columns and "inventory_id" in columns:
        return target
    if "household_id" in columns:
        return Target(target.table, target.column, "", "src.household_id")
    return Target(
        target.table,
        target.column,
        "JOIN inventory inv ON inv.id = src.inventory_id",
        "inv.household_id",
    )


def _load_articles(conn: Connection) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], list[str]]]:
    name_column = _safe_identifier(_article_name_column(conn))
    rows = conn.execute(
        text(
            f"SELECT id, household_id, {name_column} AS article_name "
            "FROM household_articles"
        )
    ).mappings().all()
    canonical: dict[tuple[str, str], str] = {}
    by_name: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        household_id = str(row.get("household_id") or "").strip()
        article_id = str(row.get("id") or "").strip()
        if not household_id or not article_id:
            continue
        canonical[(household_id, article_id)] = article_id
        normalized_name = _normalize_name(row.get("article_name"))
        if normalized_name:
            by_name.setdefault((household_id, normalized_name), []).append(article_id)
    return canonical, by_name


def _scan_target(
    conn: Connection,
    target: Target,
    *,
    dry_run: bool,
    canonical: dict[tuple[str, str], str],
    by_name: dict[tuple[str, str], list[str]],
) -> TargetReport:
    report = TargetReport(table=target.table, column=target.column)
    if not _target_supported(conn, target):
        report.skipped_missing_schema = True
        return report

    target = _effective_inventory_events_target(conn, target)
    table = _safe_identifier(target.table)
    column = _safe_identifier(target.column)
    rows = conn.execute(
        text(
            f"SELECT src.id AS row_id, src.{column} AS legacy_value, "
            f"{target.household_expression} AS household_id "
            f"FROM {table} src {target.household_join} "
            f"WHERE src.{column} IS NOT NULL AND trim(CAST(src.{column} AS TEXT)) <> ''"
        )
    ).mappings().all()

    for row in rows:
        row_id = str(row.get("row_id") or "")
        household_id = str(row.get("household_id") or "").strip()
        legacy_value = str(row.get("legacy_value") or "").strip()
        detail = {"row_id": row_id, "household_id": household_id, "value": legacy_value}

        if household_id and (household_id, legacy_value) in canonical:
            report.already_canonical += 1
            continue

        if not household_id or not legacy_value.startswith(LIVE_PREFIX):
            report.unresolved += 1
            detail["reason"] = "missing_household_or_noncanonical_value"
            report.details.append(detail)
            continue

        normalized_name = _normalize_name(legacy_value[len(LIVE_PREFIX) :])
        candidates = by_name.get((household_id, normalized_name), [])
        if len(candidates) == 0:
            report.unresolved += 1
            detail["reason"] = "no_household_article_match"
            report.details.append(detail)
            continue
        if len(candidates) > 1:
            report.ambiguous += 1
            detail["reason"] = "multiple_household_article_matches"
            detail["candidate_ids"] = list(candidates)
            report.details.append(detail)
            continue

        canonical_id = candidates[0]
        detail["canonical_id"] = canonical_id
        if not dry_run:
            conn.execute(
                text(f"UPDATE {table} SET {column} = :canonical_id WHERE id = :row_id"),
                {"canonical_id": canonical_id, "row_id": row_id},
            )
        report.migrated += 1
        report.details.append(detail)

    return report


def migrate_household_article_identities(
    bind: Engine | Connection,
    *,
    dry_run: bool = True,
) -> MigrationReport:
    """Inventory and optionally migrate legacy household-article references.

    A value is updated only when one normalized ``live::<name>`` value resolves
    to exactly one household article inside the same household. The operation is
    idempotent: a second run counts migrated values as already canonical.
    """

    owns_transaction = isinstance(bind, Engine)
    context = bind.begin() if owns_transaction else None
    conn = context.__enter__() if context is not None else bind
    try:
        canonical, by_name = _load_articles(conn)
        report = MigrationReport(dry_run=dry_run)
        for target in TARGETS:
            report.targets.append(
                _scan_target(
                    conn,
                    target,
                    dry_run=dry_run,
                    canonical=canonical,
                    by_name=by_name,
                )
            )
        if context is not None:
            context.__exit__(None, None, None)
        return report
    except Exception as exc:
        if context is not None:
            context.__exit__(type(exc), exc, exc.__traceback__)
        raise
