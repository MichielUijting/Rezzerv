"""Current Rezzerv SQLite schema baseline and PostgreSQL lineage root.

Revision ID: 20260827_01
Revises: None
Create Date: 2026-08-27
"""
from __future__ import annotations

import gzip
import sqlite3
from pathlib import Path
from typing import Iterator, Sequence, Union

from alembic import op


revision: str = "20260827_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SQLITE_BASELINE_PATH = Path(__file__).resolve().parents[1] / "baseline_sqlite.sql.gz"


def _sqlite_statements(script: str) -> Iterator[str]:
    buffer: list[str] = []
    for line in script.splitlines(keepends=True):
        buffer.append(line)
        candidate = "".join(buffer).strip()
        if candidate and sqlite3.complete_statement(candidate):
            yield candidate
            buffer = []

    remainder = "".join(buffer).strip()
    if remainder:
        raise RuntimeError("SQLite baseline contains an incomplete SQL statement")


def _assert_empty_sqlite_baseline_target() -> None:
    bind = op.get_bind()
    existing = bind.exec_driver_sql(
        """
        SELECT name
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
          AND name <> 'alembic_version'
        ORDER BY name
        """
    ).scalars().all()
    if existing:
        preview = ", ".join(str(name) for name in existing[:8])
        raise RuntimeError(
            "The SQLite baseline upgrade is only for a fresh database. "
            "Existing Rezzerv SQLite databases must first pass the schema-contract "
            "validation and then use 'alembic stamp 20260827_01'. "
            f"Existing objects include: {preview}"
        )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        _assert_empty_sqlite_baseline_target()
        with gzip.open(_SQLITE_BASELINE_PATH, "rt", encoding="utf-8") as baseline_file:
            script = baseline_file.read()
        for statement in _sqlite_statements(script):
            bind.exec_driver_sql(statement)
        return

    if dialect == "postgresql":
        # PR2a establishes the canonical migration lineage without pretending
        # that the still SQLite-specific application schema is portable. PR2b
        # adds the PostgreSQL application schema as the next immutable revision.
        return

    raise RuntimeError(f"Unsupported Rezzerv migration dialect: {dialect}")


def downgrade() -> None:
    raise RuntimeError(
        "The Rezzerv baseline revision is intentionally non-destructive and cannot be downgraded."
    )
