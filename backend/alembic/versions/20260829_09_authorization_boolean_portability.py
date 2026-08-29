"""Normalize canonical authorization Boolean columns for PostgreSQL.

Revision ID: 20260829_09
Revises: 20260829_08
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_09"
down_revision: Union[str, None] = "20260829_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUTHORIZATION_BOOLEAN_COLUMNS = (
    ("auth_permissions", "active"),
    ("auth_roles", "system_role"),
    ("auth_roles", "active"),
    ("auth_membership_roles", "active"),
    ("auth_platform_user_roles", "active"),
)
_IP_OWNER_INDEX = "idx_auth_single_active_ip_owner"


def _column_map(bind: sa.engine.Connection, table_name: str) -> dict[str, dict]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        raise RuntimeError(f"Canonical authorization table ontbreekt: {table_name}")
    return {
        str(column.get("name") or ""): column
        for column in inspector.get_columns(table_name)
    }


def _index_map(bind: sa.engine.Connection, table_name: str) -> dict[str, dict]:
    return {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes(table_name)
    }


def _normalize_boolean_column_postgresql(
    bind: sa.engine.Connection,
    *,
    table_name: str,
    column_name: str,
) -> None:
    columns = _column_map(bind, table_name)
    column = columns.get(column_name)
    if column is None:
        raise RuntimeError(
            f"Canonical authorization kolom ontbreekt: {table_name}.{column_name}"
        )

    if not isinstance(column["type"], sa.Boolean):
        bind.execute(sa.text(
            f'ALTER TABLE "{table_name}" '
            f'ALTER COLUMN "{column_name}" DROP DEFAULT'
        ))
        bind.execute(sa.text(
            f'ALTER TABLE "{table_name}" '
            f'ALTER COLUMN "{column_name}" TYPE BOOLEAN '
            f'USING CASE '
            f'WHEN "{column_name}" IS NULL THEN NULL '
            f'WHEN CAST("{column_name}" AS INTEGER) = 0 THEN FALSE '
            f'ELSE TRUE END'
        ))

    bind.execute(sa.text(
        f'ALTER TABLE "{table_name}" '
        f'ALTER COLUMN "{column_name}" SET DEFAULT TRUE'
    ))
    bind.execute(sa.text(
        f'ALTER TABLE "{table_name}" '
        f'ALTER COLUMN "{column_name}" SET NOT NULL'
    ))


def _drop_postgresql_ip_owner_index(bind: sa.engine.Connection) -> None:
    if _IP_OWNER_INDEX in _index_map(bind, "auth_platform_user_roles"):
        op.drop_index(_IP_OWNER_INDEX, table_name="auth_platform_user_roles")


def _create_postgresql_ip_owner_index(bind: sa.engine.Connection) -> None:
    op.create_index(
        _IP_OWNER_INDEX,
        "auth_platform_user_roles",
        ["role_key"],
        unique=True,
        postgresql_where=sa.text(
            "role_key = 'platform.ip_owner' AND active IS TRUE"
        ),
    )


def _validate_contract(bind: sa.engine.Connection) -> None:
    for table_name, column_name in _AUTHORIZATION_BOOLEAN_COLUMNS:
        column = _column_map(bind, table_name).get(column_name)
        if column is None:
            raise RuntimeError(
                f"Canonical authorization kolom ontbreekt: {table_name}.{column_name}"
            )
        if bool(column.get("nullable")):
            raise RuntimeError(
                f"Canonical authorization Boolean moet NOT NULL zijn: "
                f"{table_name}.{column_name}"
            )
        if bind.dialect.name == "postgresql" and not isinstance(
            column["type"], sa.Boolean
        ):
            raise RuntimeError(
                f"PostgreSQL authorization Boolean drift: "
                f"{table_name}.{column_name}={column['type']}"
            )

    index = _index_map(bind, "auth_platform_user_roles").get(_IP_OWNER_INDEX)
    if not index:
        raise RuntimeError(f"Canonical authorization index ontbreekt: {_IP_OWNER_INDEX}")
    if not bool(index.get("unique")) or tuple(index.get("column_names") or ()) != (
        "role_key",
    ):
        raise RuntimeError(
            f"Canonical authorization index drift: {_IP_OWNER_INDEX}"
        )

    if bind.dialect.name == "postgresql":
        indexdef = bind.execute(sa.text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'auth_platform_user_roles'
              AND indexname = :index_name
            """
        ), {"index_name": _IP_OWNER_INDEX}).scalar_one_or_none()
        normalized = " ".join(str(indexdef or "").lower().split())
        for fragment in (
            "create unique index",
            "role_key",
            "platform.ip_owner",
            "active is true",
        ):
            if fragment not in normalized:
                raise RuntimeError(
                    f"PostgreSQL authorization partial index drift: "
                    f"missing={fragment!r} index={indexdef!r}"
                )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(
            f"Unsupported Rezzerv migration dialect: {bind.dialect.name}"
        )

    if bind.dialect.name == "postgresql":
        # The legacy partial index depends on auth_platform_user_roles.active as
        # INTEGER. PostgreSQL will not alter that column type while the predicate
        # depends on it, so recreate it around the canonical Boolean conversion.
        _drop_postgresql_ip_owner_index(bind)
        for table_name, column_name in _AUTHORIZATION_BOOLEAN_COLUMNS:
            _normalize_boolean_column_postgresql(
                bind,
                table_name=table_name,
                column_name=column_name,
            )
        _create_postgresql_ip_owner_index(bind)

    # SQLite intentionally retains the immutable integer-Boolean storage contract.
    # TRUE/FALSE and IS TRUE remain SQL-compatible there, so no table rebuild is
    # necessary. Both dialects are validated against the same canonical semantics.
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The authorization Boolean portability revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
