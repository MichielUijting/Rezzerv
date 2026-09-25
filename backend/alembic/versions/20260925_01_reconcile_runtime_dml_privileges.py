"""Reconcile PostgreSQL runtime DML privileges for Alembic-owned objects.

Revision ID: 20260925_01
Revises: 20260924_01

Long-lived PostgreSQL volumes can predate the split migration/runtime role
bootstrap. Default privileges only affect objects created after they are set, so
an existing table can remain readable yet reject an application write. Alembic
owns this one-time privilege reconciliation and restores the default policy for
future objects created by the migration role.
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import make_url


revision = "20260925_01"
down_revision = "20260924_01"
branch_labels = None
depends_on = None

CI_IMPACT_DOMAINS = ["shared"]

_TARGET_TABLE = "purchase_import_line_inventory_handling_overrides"
_DML_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE")


def _runtime_role() -> str:
    raw_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not raw_url:
        raise RuntimeError(
            "DATABASE_URL ontbreekt; PostgreSQL runtime-role kan niet fail-closed "
            "worden vastgesteld"
        )
    try:
        role = str(make_url(raw_url).username or "").strip()
    except Exception as exc:
        raise RuntimeError("DATABASE_URL bevat geen leesbare PostgreSQL runtime-role") from exc
    if not role:
        raise RuntimeError("DATABASE_URL bevat geen PostgreSQL runtime-role")
    return role


def _quote_identifier(bind, value: str) -> str:
    return bind.dialect.identifier_preparer.quote_identifier(str(value))


def _grant_owned_runtime_objects(bind, *, runtime_role: str, migration_role: str) -> None:
    quoted_role = _quote_identifier(bind, runtime_role)
    quoted_schema = _quote_identifier(bind, "public")

    tables = bind.execute(
        sa.text(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
              AND tableowner = :owner
            ORDER BY tablename
            """
        ),
        {"owner": migration_role},
    ).scalars().all()
    for table_name in tables:
        quoted_table = _quote_identifier(bind, str(table_name))
        bind.exec_driver_sql(
            "GRANT SELECT, INSERT, UPDATE, DELETE "
            f"ON TABLE {quoted_schema}.{quoted_table} TO {quoted_role}"
        )

    sequences = bind.execute(
        sa.text(
            """
            SELECT sequencename
            FROM pg_catalog.pg_sequences
            WHERE schemaname = 'public'
              AND sequenceowner = :owner
            ORDER BY sequencename
            """
        ),
        {"owner": migration_role},
    ).scalars().all()
    for sequence_name in sequences:
        quoted_sequence = _quote_identifier(bind, str(sequence_name))
        bind.exec_driver_sql(
            "GRANT USAGE, SELECT "
            f"ON SEQUENCE {quoted_schema}.{quoted_sequence} TO {quoted_role}"
        )

    bind.exec_driver_sql(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA "
        f"{quoted_schema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted_role}"
    )
    bind.exec_driver_sql(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA "
        f"{quoted_schema} GRANT USAGE, SELECT ON SEQUENCES TO {quoted_role}"
    )


def _validate_runtime_boundary(bind, *, runtime_role: str, migration_role: str) -> None:
    target = f"public.{_TARGET_TABLE}"
    if bind.execute(sa.text("SELECT to_regclass(:target)"), {"target": target}).scalar_one() is None:
        raise RuntimeError(f"Canonical runtime-tabel ontbreekt: {target}")

    missing = []
    for privilege in _DML_PRIVILEGES:
        allowed = bool(
            bind.execute(
                sa.text("SELECT has_table_privilege(:role, :target, :privilege)"),
                {
                    "role": runtime_role,
                    "target": target,
                    "privilege": privilege,
                },
            ).scalar_one()
        )
        if not allowed:
            missing.append(privilege)
    if missing:
        raise RuntimeError(
            f"PostgreSQL runtime-role {runtime_role!r} mist DML-rechten op "
            f"{target}: {missing}"
        )

    if runtime_role != migration_role:
        can_create = bool(
            bind.execute(
                sa.text(
                    "SELECT has_schema_privilege(:role, 'public', 'CREATE')"
                ),
                {"role": runtime_role},
            ).scalar_one()
        )
        if can_create:
            raise RuntimeError(
                f"PostgreSQL runtime-role {runtime_role!r} mag onverwacht schema-objecten aanmaken"
            )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    if bind.dialect.name != "postgresql":
        raise RuntimeError(
            f"Unsupported Rezzerv privilege-reconciliation dialect: {bind.dialect.name}"
        )

    runtime_role = _runtime_role()
    migration_role = str(bind.execute(sa.text("SELECT current_user")).scalar_one()).strip()
    if not migration_role:
        raise RuntimeError("PostgreSQL migration-role kon niet worden vastgesteld")

    role_exists = bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :role"),
            {"role": runtime_role},
        ).first()
    )
    if not role_exists:
        raise RuntimeError(
            f"PostgreSQL runtime-role bestaat niet: {runtime_role!r}"
        )

    _grant_owned_runtime_objects(
        bind,
        runtime_role=runtime_role,
        migration_role=migration_role,
    )
    _validate_runtime_boundary(
        bind,
        runtime_role=runtime_role,
        migration_role=migration_role,
    )


def downgrade() -> None:
    raise RuntimeError(
        "Runtime DML privilege reconciliation is intentionally non-destructive "
        "and cannot be reversed safely."
    )
