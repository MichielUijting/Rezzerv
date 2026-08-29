"""Move roles-v2 account/household request schema authority to Alembic.

Revision ID: 20260829_07
Revises: 20260829_06
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_07"
down_revision: Union[str, None] = "20260829_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HOUSEHOLDS = "household_registry"
_USERS = "app_users"


def _columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        raise RuntimeError(f"Canonical table ontbreekt: {table_name}")
    return {str(column.get("name") or "") for column in inspector.get_columns(table_name)}


def _ensure_columns(bind: sa.engine.Connection) -> None:
    household_columns = _columns(bind, _HOUSEHOLDS)
    if "context_type" not in household_columns:
        op.add_column(
            _HOUSEHOLDS,
            sa.Column("context_type", sa.Text(), nullable=False, server_default=sa.text("'regular'")),
        )

    user_columns = _columns(bind, _USERS)
    if "account_status" not in user_columns:
        op.add_column(
            _USERS,
            sa.Column("account_status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        )
    if "password_hash" not in user_columns:
        op.add_column(_USERS, sa.Column("password_hash", sa.Text(), nullable=True))


def _backfill(bind: sa.engine.Connection) -> None:
    bind.execute(sa.text(
        "UPDATE household_registry SET context_type = 'regular' "
        "WHERE context_type IS NULL OR trim(context_type) = ''"
    ))
    bind.execute(sa.text(
        "UPDATE household_registry SET context_type = 'system' WHERE CAST(id AS TEXT) = '0'"
    ))
    bind.execute(sa.text(
        "UPDATE app_users SET account_status = 'active' "
        "WHERE account_status IS NULL OR trim(account_status) = ''"
    ))


def _ensure_sqlite_guards(bind: sa.engine.Connection) -> None:
    if bind.dialect.name != "sqlite":
        return
    bind.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS trg_household_context_type_insert
        BEFORE INSERT ON household_registry
        WHEN NEW.context_type NOT IN ('regular', 'system')
        BEGIN
            SELECT RAISE(ABORT, 'invalid household context_type');
        END
    """))
    bind.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS trg_household_context_type_update
        BEFORE UPDATE OF context_type ON household_registry
        WHEN NEW.context_type NOT IN ('regular', 'system')
        BEGIN
            SELECT RAISE(ABORT, 'invalid household context_type');
        END
    """))
    bind.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS trg_household_zero_system_insert
        AFTER INSERT ON household_registry
        WHEN CAST(NEW.id AS TEXT) = '0' AND NEW.context_type <> 'system'
        BEGIN
            UPDATE household_registry SET context_type = 'system' WHERE id = NEW.id;
        END
    """))
    bind.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS trg_app_users_account_status_insert
        BEFORE INSERT ON app_users
        WHEN NEW.account_status NOT IN ('active', 'disabled')
        BEGIN
            SELECT RAISE(ABORT, 'invalid account_status');
        END
    """))
    bind.execute(sa.text("""
        CREATE TRIGGER IF NOT EXISTS trg_app_users_account_status_update
        BEFORE UPDATE OF account_status ON app_users
        WHEN NEW.account_status NOT IN ('active', 'disabled')
        BEGIN
            SELECT RAISE(ABORT, 'invalid account_status');
        END
    """))


def _validate(bind: sa.engine.Connection) -> None:
    household_columns = _columns(bind, _HOUSEHOLDS)
    user_columns = _columns(bind, _USERS)
    missing_household = {"id", "context_type"} - household_columns
    missing_users = {"id", "account_status", "password_hash"} - user_columns
    if missing_household:
        raise RuntimeError(f"household_registry mist roles-v2 kolommen: {sorted(missing_household)}")
    if missing_users:
        raise RuntimeError(f"app_users mist roles-v2 kolommen: {sorted(missing_users)}")

    invalid_households = int(bind.execute(sa.text(
        "SELECT COUNT(*) FROM household_registry "
        "WHERE context_type IS NULL OR context_type NOT IN ('regular', 'system')"
    )).scalar_one())
    invalid_users = int(bind.execute(sa.text(
        "SELECT COUNT(*) FROM app_users "
        "WHERE account_status IS NULL OR account_status NOT IN ('active', 'disabled')"
    )).scalar_one())
    if invalid_households:
        raise RuntimeError("household_registry bevat ongeldige context_type waarden")
    if invalid_users:
        raise RuntimeError("app_users bevat ongeldige account_status waarden")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    _ensure_columns(bind)
    _backfill(bind)
    _ensure_sqlite_guards(bind)
    _validate(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The roles-v2 request schema authority revision is intentionally non-destructive "
        "and cannot be downgraded."
    )
