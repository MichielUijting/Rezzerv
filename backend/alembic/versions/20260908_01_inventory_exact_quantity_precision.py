"""Make inventory and inventory-history quantities exact and unbounded.

Revision ID: 20260908_01
Revises: 20260903_01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260908_01"
down_revision = "20260903_01"
branch_labels = None
depends_on = None


_EXACT_QUANTITY_COLUMNS = {
    "inventory": ("aantal",),
    "inventory_events": ("quantity", "old_quantity", "new_quantity"),
}


def _column_contract(bind, table_name: str, column_name: str) -> dict:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        raise RuntimeError(f"Required inventory table ontbreekt: {table_name}")
    columns = {
        str(column.get("name") or ""): column
        for column in inspector.get_columns(table_name)
    }
    column = columns.get(column_name)
    if column is None:
        raise RuntimeError(f"Required inventory quantity column ontbreekt: {table_name}.{column_name}")
    return column


def _is_unbounded_numeric(column_type) -> bool:
    return (
        isinstance(column_type, sa.Numeric)
        and getattr(column_type, "precision", None) is None
        and getattr(column_type, "scale", None) is None
    )


def _alter_to_unbounded_numeric(bind, table_name: str, column_name: str) -> None:
    column = _column_contract(bind, table_name, column_name)
    existing_type = column["type"]
    if _is_unbounded_numeric(existing_type):
        return
    kwargs = {}
    if bind.dialect.name == "postgresql":
        kwargs["postgresql_using"] = f'"{column_name}"::numeric'
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            column_name,
            existing_type=existing_type,
            type_=sa.Numeric(),
            existing_nullable=bool(column.get("nullable")),
            **kwargs,
        )


def _validate_exact_contract(bind) -> None:
    for table_name, column_names in _EXACT_QUANTITY_COLUMNS.items():
        for column_name in column_names:
            column = _column_contract(bind, table_name, column_name)
            if not _is_unbounded_numeric(column["type"]):
                raise RuntimeError(
                    f"Exact inventory quantity contract ontbreekt voor {table_name}.{column_name}: "
                    f"actual_type={column['type']!r}"
                )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    for table_name, column_names in _EXACT_QUANTITY_COLUMNS.items():
        for column_name in column_names:
            _alter_to_unbounded_numeric(bind, table_name, column_name)
    _validate_exact_contract(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")
    # Historical contract used integer quantities. Downgrade is intentionally
    # lossy for fractional values and rounds them explicitly instead of relying
    # on an implicit database cast.
    for table_name, column_names in reversed(tuple(_EXACT_QUANTITY_COLUMNS.items())):
        for column_name in reversed(column_names):
            column = _column_contract(bind, table_name, column_name)
            kwargs = {}
            if bind.dialect.name == "postgresql":
                kwargs["postgresql_using"] = f'ROUND("{column_name}")::integer'
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.alter_column(
                    column_name,
                    existing_type=column["type"],
                    type_=sa.Integer(),
                    existing_nullable=bool(column.get("nullable")),
                    **kwargs,
                )
