from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected patch anchor missing in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


frontteam_old = '''def ensure_frontteam_personal_household_schema(conn: Connection) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE} (
            user_id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
'''
frontteam_new = '''def ensure_frontteam_personal_household_schema(conn: Connection) -> None:
    """Validate the Alembic-owned Frontteam personal-household contract."""
    inspector = inspect(conn)
    if not inspector.has_table(FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE):
        raise RuntimeError(
            "frontteam_personal_households ontbreekt; voer eerst Alembic-migraties uit"
        )
    columns = _columns(conn, FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE)
    required = {"user_id", "household_id", "created_at", "updated_at"}
    missing = required - columns
    if missing:
        raise RuntimeError(
            "frontteam_personal_households mist canonieke kolommen: "
            + ", ".join(sorted(missing))
        )
    primary_key = tuple(
        str(column or "")
        for column in (inspector.get_pk_constraint(FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE).get("constrained_columns") or ())
    )
    if primary_key != ("user_id",):
        raise RuntimeError(
            "frontteam_personal_households.user_id moet de primaire sleutel zijn"
        )
    unique_sets = {
        tuple(str(column or "") for column in (constraint.get("column_names") or ()))
        for constraint in inspector.get_unique_constraints(FRONTTEAM_PERSONAL_HOUSEHOLD_TABLE)
    }
    if ("household_id",) not in unique_sets:
        raise RuntimeError(
            "frontteam_personal_households.household_id moet uniek zijn"
        )
'''
replace(
    "backend/app/services/frontteam_household_provisioning.py",
    frontteam_old,
    frontteam_new,
)

fixture_anchor = '''    conn.execute(text("""
        CREATE TABLE app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE
        )
    """))
'''
fixture_replacement = '''    conn.execute(text("""
        CREATE TABLE frontteam_personal_households (
            user_id TEXT PRIMARY KEY,
            household_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    conn.execute(text("""
        CREATE TABLE app_users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE
        )
    """))
'''
replace(
    "backend/tests/test_frontteam_household_provisioning.py",
    fixture_anchor,
    fixture_replacement,
)

replace(
    "backend/tests/migration_foundation_selftest.py",
    'HEAD_REVISION = "20260828_03"',
    'HEAD_REVISION = "20260828_04"',
)
replace(
    "backend/tests/migration_foundation_selftest.py",
    'EXPECTED_POSTGRESQL_APPLICATION_TABLES = 50',
    'EXPECTED_POSTGRESQL_APPLICATION_TABLES = 51',
)
replace(
    "backend/tests/migration_foundation_selftest.py",
    '        "-- table: server_sessions (table=server_sessions)",\n',
    '        "-- table: server_sessions (table=server_sessions)",\n        "-- table: frontteam_personal_households (table=frontteam_personal_households)",\n',
)

replace(
    ".github/workflows/postgresql-runtime-startup-schema-authority.yml",
    "'revision': '20260828_03'",
    "'revision': '20260828_04'",
)

migration = ROOT / "backend/alembic/versions/20260828_04_runtime_startup_schema_authority.py"
if migration.exists():
    raise SystemExit(f"Migration already exists: {migration}")
migration.write_text('''"""Move Frontteam runtime startup schema authority to Alembic.

Revision ID: 20260828_04
Revises: 20260828_03
Create Date: 2026-08-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260828_04"
down_revision: Union[str, None] = "20260828_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "frontteam_personal_households"
_REQUIRED_COLUMNS = {"user_id", "household_id", "created_at", "updated_at"}


def _timestamp_type(dialect_name: str) -> sa.types.TypeEngine:
    if dialect_name == "postgresql":
        return sa.DateTime(timezone=True)
    if dialect_name == "sqlite":
        return sa.Text()
    raise RuntimeError(f"Unsupported Rezzerv migration dialect: {dialect_name}")


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        raise RuntimeError(f"{_TABLE} ontbreekt")
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(_TABLE)
    }
    missing = _REQUIRED_COLUMNS - columns
    if missing:
        raise RuntimeError(
            f"{_TABLE} mist canonieke kolommen: {sorted(missing)}"
        )
    primary_key = tuple(
        str(column or "")
        for column in (inspector.get_pk_constraint(_TABLE).get("constrained_columns") or ())
    )
    if primary_key != ("user_id",):
        raise RuntimeError(f"{_TABLE}.user_id moet de primaire sleutel zijn")
    unique_sets = {
        tuple(str(column or "") for column in (constraint.get("column_names") or ()))
        for constraint in inspector.get_unique_constraints(_TABLE)
    }
    if ("household_id",) not in unique_sets:
        raise RuntimeError(f"{_TABLE}.household_id moet uniek zijn")


def upgrade() -> None:
    bind = op.get_bind()
    timestamp_type = _timestamp_type(bind.dialect.name)
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        op.create_table(
            _TABLE,
            sa.Column("user_id", sa.Text(), primary_key=True),
            sa.Column("household_id", sa.Text(), nullable=False, unique=True),
            sa.Column(
                "created_at",
                timestamp_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                timestamp_type,
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
    else:
        existing_columns = {
            str(column.get("name") or "")
            for column in inspector.get_columns(_TABLE)
        }
        required_legacy_columns = {"user_id", "household_id", "created_at"}
        missing_legacy = required_legacy_columns - existing_columns
        if missing_legacy:
            raise RuntimeError(
                f"{_TABLE} legacy contract mist kolommen: {sorted(missing_legacy)}"
            )
        if "updated_at" not in existing_columns:
            op.add_column(
                _TABLE,
                sa.Column(
                    "updated_at",
                    timestamp_type,
                    nullable=True,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                ),
            )
            bind.execute(sa.text(
                f"UPDATE {_TABLE} "
                "SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP) "
                "WHERE updated_at IS NULL"
            ))
            if bind.dialect.name == "postgresql":
                op.alter_column(_TABLE, "updated_at", nullable=False)
            else:
                # SQLite cannot tighten this column in-place without rebuilding the table;
                # existing legacy rows are backfilled and runtime validation remains fail-closed.
                pass
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The runtime-startup schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
''', encoding="utf-8")

print("PR336_RUNTIME_AUTHORITY_PATCH_APPLIED")
