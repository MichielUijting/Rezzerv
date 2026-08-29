"""Complete core request-path schema authority closure.

Revision ID: 20260829_06
Revises: 20260829_05
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_06"
down_revision: Union[str, None] = "20260829_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRODUCT_CONFIG = "household_product_configuration"
_SPACES = "spaces"
_DIRECT_INDEX = "ux_spaces_household_direct"
_DIRECT_UPDATE_TRIGGER = "trg_spaces_direct_immutable_update"
_DIRECT_DELETE_TRIGGER = "trg_spaces_direct_immutable_delete"
_DIRECT_GUARD_FUNCTION = "rezzerv_spaces_direct_immutable_guard"
_ACCOUNT_TABLE = "app_users"
_ACCOUNT_CHECK = "ck_app_users_account_status"
_ACCOUNT_INSERT_TRIGGER = "trg_app_users_account_status_insert"
_ACCOUNT_UPDATE_TRIGGER = "trg_app_users_account_status_update"
_ACCOUNT_ALLOWED_STATUSES = ("active", "disabled", "suspended")

_PRODUCT_CONFIG_COLUMNS = {
    "household_id",
    "inventory_tracking_level",
    "location_tracking_level",
    "shopping_enabled",
    "almost_out_enabled",
    "almost_out_notifications_enabled",
    "receipt_processing_enabled",
    "recipes_enabled",
    "unpacking_enabled",
    "created_at",
    "updated_at",
}
_PRODUCT_CONFIG_LEGACY_COLUMNS = _PRODUCT_CONFIG_COLUMNS - {"unpacking_enabled"}
_SPACE_DIRECT_COLUMNS = {"id", "naam", "household_id", "active", "is_direct"}


def _columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _ensure_product_configuration(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_PRODUCT_CONFIG):
        op.create_table(
            _PRODUCT_CONFIG,
            sa.Column("household_id", sa.Text(), primary_key=True),
            sa.Column("inventory_tracking_level", sa.Text(), nullable=False),
            sa.Column("location_tracking_level", sa.Text(), nullable=False),
            sa.Column("shopping_enabled", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("almost_out_enabled", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "almost_out_notifications_enabled",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "receipt_processing_enabled",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("recipes_enabled", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("unpacking_enabled", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint(
                "inventory_tracking_level IN ('none', 'presence', 'quantity')",
                name="ck_hpc_inventory_tracking",
            ),
            sa.CheckConstraint(
                "location_tracking_level IN ('none', 'global', 'exact')",
                name="ck_hpc_location_tracking",
            ),
            sa.CheckConstraint(
                "shopping_enabled IN (0, 1)",
                name="ck_hpc_shopping",
            ),
            sa.CheckConstraint(
                "almost_out_enabled IN (0, 1)",
                name="ck_hpc_almost_out",
            ),
            sa.CheckConstraint(
                "almost_out_notifications_enabled IN (0, 1)",
                name="ck_hpc_almost_out_notify",
            ),
            sa.CheckConstraint(
                "receipt_processing_enabled IN (0, 1)",
                name="ck_hpc_receipt_processing",
            ),
            sa.CheckConstraint(
                "recipes_enabled IN (0, 1)",
                name="ck_hpc_recipes",
            ),
            sa.CheckConstraint(
                "unpacking_enabled IN (0, 1)",
                name="ck_hpc_unpacking",
            ),
        )
        return

    columns = _columns(bind, _PRODUCT_CONFIG)
    missing_legacy = _PRODUCT_CONFIG_LEGACY_COLUMNS - columns
    if missing_legacy:
        raise RuntimeError(
            "household_product_configuration legacy contract mist kolommen: "
            f"{sorted(missing_legacy)}"
        )
    if "unpacking_enabled" not in columns:
        op.add_column(
            _PRODUCT_CONFIG,
            sa.Column(
                "unpacking_enabled",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )


def _ensure_direct_location_schema(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_SPACES):
        raise RuntimeError("spaces ontbreekt; Direct-location authority kan niet worden geadopteerd")

    columns = _columns(bind, _SPACES)
    required_legacy = _SPACE_DIRECT_COLUMNS - {"is_direct"}
    missing_legacy = required_legacy - columns
    if missing_legacy:
        raise RuntimeError(f"spaces legacy contract mist kolommen: {sorted(missing_legacy)}")
    if "is_direct" not in columns:
        op.add_column(
            _SPACES,
            sa.Column("is_direct", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )

    inspector = sa.inspect(bind)
    indexes = {str(index.get("name") or ""): index for index in inspector.get_indexes(_SPACES)}
    direct_index = indexes.get(_DIRECT_INDEX)
    if direct_index is None:
        index_kwargs: dict[str, object] = {}
        if bind.dialect.name == "sqlite":
            index_kwargs["sqlite_where"] = sa.text("is_direct = 1")
        elif bind.dialect.name == "postgresql":
            index_kwargs["postgresql_where"] = sa.text("is_direct = 1")
        op.create_index(
            _DIRECT_INDEX,
            _SPACES,
            ["household_id"],
            unique=True,
            **index_kwargs,
        )
    else:
        if not bool(direct_index.get("unique")) or tuple(direct_index.get("column_names") or ()) != (
            "household_id",
        ):
            raise RuntimeError(f"{_DIRECT_INDEX} wijkt af van het canonical Direct-location contract")

    if bind.dialect.name == "sqlite":
        bind.execute(sa.text(f"""
            CREATE TRIGGER IF NOT EXISTS {_DIRECT_UPDATE_TRIGGER}
            BEFORE UPDATE OF naam, active ON spaces
            FOR EACH ROW
            WHEN OLD.is_direct = 1
              AND (
                lower(trim(COALESCE(NEW.naam, ''))) <> 'direct'
                OR COALESCE(NEW.active, 1) <> 1
              )
            BEGIN
                SELECT RAISE(ABORT, 'Direct is een vaste locatie');
            END
        """))
        bind.execute(sa.text(f"""
            CREATE TRIGGER IF NOT EXISTS {_DIRECT_DELETE_TRIGGER}
            BEFORE DELETE ON spaces
            FOR EACH ROW
            WHEN OLD.is_direct = 1
            BEGIN
                SELECT RAISE(ABORT, 'Direct is een vaste locatie');
            END
        """))
    else:
        bind.execute(sa.text(f"""
            CREATE OR REPLACE FUNCTION {_DIRECT_GUARD_FUNCTION}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Direct is een vaste locatie';
                END IF;
                IF lower(trim(COALESCE(NEW.naam, ''))) <> 'direct'
                   OR lower(COALESCE(NEW.active::text, 'true')) NOT IN ('1', 't', 'true') THEN
                    RAISE EXCEPTION 'Direct is een vaste locatie';
                END IF;
                RETURN NEW;
            END;
            $$
        """))
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {_DIRECT_UPDATE_TRIGGER} ON spaces"))
        bind.execute(sa.text(f"""
            CREATE TRIGGER {_DIRECT_UPDATE_TRIGGER}
            BEFORE UPDATE OF naam, active ON spaces
            FOR EACH ROW
            WHEN (OLD.is_direct = 1)
            EXECUTE FUNCTION {_DIRECT_GUARD_FUNCTION}()
        """))
        bind.execute(sa.text(f"DROP TRIGGER IF EXISTS {_DIRECT_DELETE_TRIGGER} ON spaces"))
        bind.execute(sa.text(f"""
            CREATE TRIGGER {_DIRECT_DELETE_TRIGGER}
            BEFORE DELETE ON spaces
            FOR EACH ROW
            WHEN (OLD.is_direct = 1)
            EXECUTE FUNCTION {_DIRECT_GUARD_FUNCTION}()
        """))


def _ensure_account_status_authority(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_ACCOUNT_TABLE):
        raise RuntimeError("app_users ontbreekt")
    account_columns = _columns(bind, _ACCOUNT_TABLE)
    missing = {"account_status", "suspended_at"} - account_columns
    if missing:
        raise RuntimeError(
            "app_users mist canonical account-suspension kolommen: "
            f"{sorted(missing)}"
        )

    invalid_rows = bind.execute(sa.text(
        """
        SELECT DISTINCT lower(trim(account_status)) AS account_status
        FROM app_users
        WHERE account_status IS NULL
           OR trim(account_status) = ''
           OR lower(trim(account_status)) NOT IN ('active', 'disabled', 'suspended')
        ORDER BY account_status
        """
    )).all()
    if invalid_rows:
        raise RuntimeError(
            "app_users bevat niet-canonical account_status waarden: "
            f"{[row[0] for row in invalid_rows]!r}"
        )

    if bind.dialect.name == "postgresql":
        checks = {
            str(item.get("name") or "")
            for item in inspector.get_check_constraints(_ACCOUNT_TABLE)
        }
        if _ACCOUNT_CHECK not in checks:
            raise RuntimeError(f"{_ACCOUNT_CHECK} ontbreekt vóór account-status cutover")
        op.drop_constraint(_ACCOUNT_CHECK, _ACCOUNT_TABLE, type_="check")
        op.create_check_constraint(
            _ACCOUNT_CHECK,
            _ACCOUNT_TABLE,
            "account_status IN ('active', 'disabled', 'suspended')",
        )
        return

    if bind.dialect.name != "sqlite":
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    for trigger_name in (_ACCOUNT_INSERT_TRIGGER, _ACCOUNT_UPDATE_TRIGGER):
        bind.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{trigger_name}"')
    bind.exec_driver_sql(f"""
        CREATE TRIGGER {_ACCOUNT_INSERT_TRIGGER}
        BEFORE INSERT ON app_users
        FOR EACH ROW
        WHEN NEW.account_status IS NULL
          OR NEW.account_status NOT IN ('active', 'disabled', 'suspended')
        BEGIN
            SELECT RAISE(ABORT, 'invalid app_users.account_status');
        END
    """)
    bind.exec_driver_sql(f"""
        CREATE TRIGGER {_ACCOUNT_UPDATE_TRIGGER}
        BEFORE UPDATE OF account_status ON app_users
        FOR EACH ROW
        WHEN NEW.account_status IS NULL
          OR NEW.account_status NOT IN ('active', 'disabled', 'suspended')
        BEGIN
            SELECT RAISE(ABORT, 'invalid app_users.account_status');
        END
    """)


def _validate_account_status_authority(bind: sa.engine.Connection) -> None:
    if bind.dialect.name == "postgresql":
        checks = {
            str(item.get("name") or ""): str(item.get("sqltext") or "")
            for item in sa.inspect(bind).get_check_constraints(_ACCOUNT_TABLE)
        }
        sqltext = " ".join(checks.get(_ACCOUNT_CHECK, "").lower().split())
        for status in _ACCOUNT_ALLOWED_STATUSES:
            if f"'{status}'" not in sqltext:
                raise RuntimeError(
                    f"{_ACCOUNT_CHECK} mist canonical status {status!r}: {sqltext!r}"
                )
        return

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
    if set(triggers) != {_ACCOUNT_INSERT_TRIGGER, _ACCOUNT_UPDATE_TRIGGER}:
        raise RuntimeError(
            "SQLite account-status triggers ontbreken na migration: "
            f"{sorted(triggers)}"
        )
    for trigger_name, sqltext in triggers.items():
        normalized = " ".join(sqltext.lower().split())
        for status in _ACCOUNT_ALLOWED_STATUSES:
            if f"'{status}'" not in normalized:
                raise RuntimeError(
                    f"{trigger_name} mist canonical status {status!r}"
                )


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table(_PRODUCT_CONFIG):
        raise RuntimeError("Canonical productconfiguratie ontbreekt")
    missing_product_columns = _PRODUCT_CONFIG_COLUMNS - _columns(bind, _PRODUCT_CONFIG)
    if missing_product_columns:
        raise RuntimeError(
            "household_product_configuration mist canonical kolommen: "
            f"{sorted(missing_product_columns)}"
        )

    if not inspector.has_table(_SPACES):
        raise RuntimeError("Canonical spaces-tabel ontbreekt")
    missing_space_columns = _SPACE_DIRECT_COLUMNS - _columns(bind, _SPACES)
    if missing_space_columns:
        raise RuntimeError(f"spaces mist Direct-location kolommen: {sorted(missing_space_columns)}")

    indexes = {str(index.get("name") or ""): index for index in inspector.get_indexes(_SPACES)}
    direct_index = indexes.get(_DIRECT_INDEX)
    if not direct_index or not bool(direct_index.get("unique")):
        raise RuntimeError(f"Canonical Direct-location index ontbreekt: {_DIRECT_INDEX}")
    if tuple(direct_index.get("column_names") or ()) != ("household_id",):
        raise RuntimeError(f"Canonical Direct-location index wijkt af: {_DIRECT_INDEX}")

    if bind.dialect.name == "sqlite":
        triggers = {
            str(row[0])
            for row in bind.execute(sa.text("""
                SELECT name
                FROM sqlite_master
                WHERE type = 'trigger'
                  AND name IN (
                    'trg_spaces_direct_immutable_update',
                    'trg_spaces_direct_immutable_delete'
                  )
            """)).all()
        }
    else:
        triggers = {
            str(row[0])
            for row in bind.execute(sa.text("""
                SELECT t.tgname
                FROM pg_trigger t
                JOIN pg_class c ON c.oid = t.tgrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = current_schema()
                  AND c.relname = 'spaces'
                  AND NOT t.tgisinternal
                  AND t.tgname IN (
                    'trg_spaces_direct_immutable_update',
                    'trg_spaces_direct_immutable_delete'
                  )
            """)).all()
        }
    expected_triggers = {_DIRECT_UPDATE_TRIGGER, _DIRECT_DELETE_TRIGGER}
    if triggers != expected_triggers:
        raise RuntimeError(
            "Canonical Direct-location immutability guards ontbreken: "
            f"expected={sorted(expected_triggers)} actual={sorted(triggers)}"
        )
    _validate_account_status_authority(bind)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    _ensure_product_configuration(bind)
    _ensure_direct_location_schema(bind)
    _ensure_account_status_authority(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The PR2g core request-path authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
