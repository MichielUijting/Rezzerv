"""Align canonical account-status authority with platform suspension.

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

_TABLE = "app_users"
_STATUS_COLUMN = "account_status"
_SUSPENDED_AT_COLUMN = "suspended_at"
_CHECK_NAME = "ck_app_users_account_status"
_INSERT_TRIGGER = "trg_app_users_account_status_insert"
_UPDATE_TRIGGER = "trg_app_users_account_status_update"
_ALLOWED_STATUSES = ("active", "disabled", "suspended")


def _validate_columns(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_TABLE):
        raise RuntimeError("app_users ontbreekt")
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns(_TABLE)
    }
    missing = {_STATUS_COLUMN, _SUSPENDED_AT_COLUMN} - columns
    if missing:
        raise RuntimeError(
            "app_users mist canonical account-suspension kolommen: "
            f"{sorted(missing)}"
        )


def _validate_existing_statuses(bind: sa.engine.Connection) -> None:
    rows = bind.execute(sa.text(
        """
        SELECT DISTINCT lower(trim(account_status)) AS account_status
        FROM app_users
        WHERE account_status IS NULL
           OR trim(account_status) = ''
           OR lower(trim(account_status)) NOT IN ('active', 'disabled', 'suspended')
        ORDER BY account_status
        """
    )).all()
    if rows:
        invalid = [row[0] for row in rows]
        raise RuntimeError(
            "app_users bevat niet-canonical account_status waarden: "
            f"{invalid!r}"
        )


def _upgrade_postgresql(bind: sa.engine.Connection) -> None:
    checks = {
        str(item.get("name") or "")
        for item in sa.inspect(bind).get_check_constraints(_TABLE)
    }
    if _CHECK_NAME not in checks:
        raise RuntimeError(f"{_CHECK_NAME} ontbreekt vóór account-status cutover")
    op.drop_constraint(_CHECK_NAME, _TABLE, type_="check")
    op.create_check_constraint(
        _CHECK_NAME,
        _TABLE,
        "account_status IN ('active', 'disabled', 'suspended')",
    )


def _upgrade_sqlite(bind: sa.engine.Connection) -> None:
    for trigger_name in (_INSERT_TRIGGER, _UPDATE_TRIGGER):
        bind.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{trigger_name}"')

    bind.exec_driver_sql(
        f"""
        CREATE TRIGGER {_INSERT_TRIGGER}
        BEFORE INSERT ON app_users
        FOR EACH ROW
        WHEN NEW.account_status IS NULL
          OR NEW.account_status NOT IN ('active', 'disabled', 'suspended')
        BEGIN
            SELECT RAISE(ABORT, 'invalid app_users.account_status');
        END
        """
    )
    bind.exec_driver_sql(
        f"""
        CREATE TRIGGER {_UPDATE_TRIGGER}
        BEFORE UPDATE OF account_status ON app_users
        FOR EACH ROW
        WHEN NEW.account_status IS NULL
          OR NEW.account_status NOT IN ('active', 'disabled', 'suspended')
        BEGIN
            SELECT RAISE(ABORT, 'invalid app_users.account_status');
        END
        """
    )


def _validate_guard(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "postgresql":
        checks = {
            str(item.get("name") or ""): str(item.get("sqltext") or "")
            for item in sa.inspect(bind).get_check_constraints(_TABLE)
        }
        sqltext = " ".join(checks.get(_CHECK_NAME, "").lower().split())
        for status in _ALLOWED_STATUSES:
            if f"'{status}'" not in sqltext:
                raise RuntimeError(
                    f"{_CHECK_NAME} mist canonical status {status!r}: {sqltext!r}"
                )
        return

    if bind.dialect.name == "sqlite":
        trigger_rows = bind.execute(sa.text(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'trigger'
              AND name IN (
                  'trg_app_users_account_status_insert',
                  'trg_app_users_account_status_update'
              )
            ORDER BY name
            """
        )).all()
        triggers = {str(row[0]): str(row[1] or "") for row in trigger_rows}
        if set(triggers) != {_INSERT_TRIGGER, _UPDATE_TRIGGER}:
            raise RuntimeError(
                "SQLite account-status triggers ontbreken na migration: "
                f"{sorted(triggers)}"
            )
        for trigger_name, sqltext in triggers.items():
            normalized = " ".join(sqltext.lower().split())
            for status in _ALLOWED_STATUSES:
                if f"'{status}'" not in normalized:
                    raise RuntimeError(
                        f"{trigger_name} mist canonical status {status!r}"
                    )
        return

    raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")


def upgrade() -> None:
    bind = op.get_bind()
    _validate_columns(bind)
    _validate_existing_statuses(bind)

    if bind.dialect.name == "postgresql":
        _upgrade_postgresql(bind)
    elif bind.dialect.name == "sqlite":
        _upgrade_sqlite(bind)
    else:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    _validate_guard(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The account-suspension status-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
