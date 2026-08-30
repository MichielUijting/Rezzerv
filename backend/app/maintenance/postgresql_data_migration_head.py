"""Locked-head entrypoint for PostgreSQL production-data migration."""
from __future__ import annotations

from typing import Sequence

from app.maintenance import postgresql_data_migration as migration

HEAD_REVISION = "20260830_02"


def _configure_locked_head() -> None:
    migration.HEAD_REVISION = HEAD_REVISION


def main(argv: Sequence[str] | None = None) -> int:
    _configure_locked_head()
    return migration.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
