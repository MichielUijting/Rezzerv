"""Read-only, execution-time authority check for planned Inhuis maintenance.

No cached developer-time Alembic revision, no DDL, no migration execution.
This probe alone does NOT grant permission to reboot; writer drain is separate.
"""
from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text


class MaintenancePreflightError(RuntimeError):
    pass


def read_runtime_schema_evidence(connection, *, alembic_ini: str | Path) -> dict:
    """Compare actual live PostgreSQL identity/revisions with local release heads.

    Caller supplies the actual runtime connection; do not create a new connection
    from a guessed env file or Docker volume. No application data is modified.
    """
    if connection.dialect.name != "postgresql":
        raise MaintenancePreflightError("Actieve database is geen PostgreSQL")
    cfg = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(cfg)
    expected = set(script.get_heads())
    if not expected:
        raise MaintenancePreflightError("Alembic-revisies van de software ontbreken")
    try:
        row = connection.execute(text(
            "SELECT current_database() AS database, "
            "current_schema() AS schema_name, "
            "inet_server_addr()::text AS server_address, "
            "pg_postmaster_start_time() AS server_started_at"
        )).mappings().one()
        installed = set(connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all())
    except Exception as exc:
        raise MaintenancePreflightError("Actuele databaseversie is niet betrouwbaar uitleesbaar") from exc
    if not installed or installed != expected:
        raise MaintenancePreflightError(
            "Actieve Alembic-versie wijkt af van de geïnstalleerde Inhuis-software"
        )
    if not row["database"]:
        raise MaintenancePreflightError("Database-identiteit ontbreekt")
    return {
        "database": str(row["database"]),
        "schema_name": str(row["schema_name"] or ""),
        "server_address": str(row["server_address"] or ""),
        "server_started_at": str(row["server_started_at"]),
        "alembic_heads": sorted(installed),
        "schema_compatible": True,
        "checked_at_execution": True,
    }
