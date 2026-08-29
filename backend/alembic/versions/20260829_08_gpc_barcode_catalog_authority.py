"""Move GPC catalog schema authority and barcode support contract to Alembic.

Revision ID: 20260829_08
Revises: 20260829_07
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_08"
down_revision: Union[str, None] = "20260829_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GPC_REFERENCE_TABLES: dict[str, tuple[str, ...]] = {
    "gpc_segments": ("segment_code", "description"),
    "gpc_families": ("family_code", "description", "segment_code"),
    "gpc_classes": ("class_code", "description", "family_code"),
    "gpc_bricks": ("brick_code", "description", "class_code"),
    "gpc_attribute_types": ("att_type_code", "att_type_text"),
    "gpc_attribute_values": ("att_value_code", "att_value_text"),
    "gpc_brick_attribute_types": ("brick_code", "att_type_code"),
    "gpc_attribute_type_values": ("att_type_code", "att_value_code"),
    "gpc_import_runs": (
        "id",
        "source_name",
        "source_version",
        "language_code",
        "source_sha256",
        "imported_at",
        "status",
        "counts_json",
        "message",
    ),
}
_GPC_PRODUCT_GROUP_COLUMNS = (
    "gpc_brick_code",
    "gpc_brick_name",
    "gpc_class_code",
    "gpc_class_name",
    "gpc_family_code",
    "gpc_family_name",
    "gpc_segment_code",
    "gpc_segment_name",
    "language_code",
    "source_version",
    "active",
    "created_at",
    "updated_at",
    "gpc_brick_name_en",
    "gpc_class_name_en",
    "gpc_family_name_en",
    "gpc_segment_name_en",
    "brick_definition_includes_en",
    "brick_definition_excludes_en",
    "source",
)
_PRODUCT_INVENTORY_GPC_COLUMNS = {
    "gpc_family_code": sa.Text(),
    "gpc_family_name": sa.Text(),
    "gpc_class_code": sa.Text(),
    "gpc_class_name": sa.Text(),
    "gpc_brick_code": sa.Text(),
}
_GPC_INDEXES: dict[str, tuple[str, tuple[str, ...]]] = {
    "idx_gpc_families_segment": ("gpc_families", ("segment_code",)),
    "idx_gpc_classes_family": ("gpc_classes", ("family_code",)),
    "idx_gpc_bricks_class": ("gpc_bricks", ("class_code",)),
}


def _inspector(bind: sa.engine.Connection) -> sa.Inspector:
    return sa.inspect(bind)


def _column_map(bind: sa.engine.Connection, table_name: str) -> dict[str, dict[str, Any]]:
    return {
        str(column.get("name") or ""): column
        for column in _inspector(bind).get_columns(table_name)
    }


def _active_column(bind: sa.engine.Connection) -> sa.Column[Any]:
    if bind.dialect.name == "postgresql":
        return sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        )
    return sa.Column(
        "active",
        sa.Integer(),
        nullable=False,
        server_default=sa.text("1"),
    )


def _create_reference_tables(bind: sa.engine.Connection) -> None:
    inspector = _inspector(bind)

    if not inspector.has_table("gpc_segments"):
        op.create_table(
            "gpc_segments",
            sa.Column("segment_code", sa.String(length=8), primary_key=True),
            sa.Column("description", sa.Text(), nullable=False),
        )
    if not _inspector(bind).has_table("gpc_families"):
        op.create_table(
            "gpc_families",
            sa.Column("family_code", sa.String(length=8), primary_key=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("segment_code", sa.String(length=8), nullable=False),
            sa.ForeignKeyConstraint(["segment_code"], ["gpc_segments.segment_code"]),
        )
    if not _inspector(bind).has_table("gpc_classes"):
        op.create_table(
            "gpc_classes",
            sa.Column("class_code", sa.String(length=8), primary_key=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("family_code", sa.String(length=8), nullable=False),
            sa.ForeignKeyConstraint(["family_code"], ["gpc_families.family_code"]),
        )
    if not _inspector(bind).has_table("gpc_bricks"):
        op.create_table(
            "gpc_bricks",
            sa.Column("brick_code", sa.String(length=8), primary_key=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("class_code", sa.String(length=8), nullable=False),
            sa.ForeignKeyConstraint(["class_code"], ["gpc_classes.class_code"]),
        )
    if not _inspector(bind).has_table("gpc_attribute_types"):
        op.create_table(
            "gpc_attribute_types",
            sa.Column("att_type_code", sa.String(length=8), primary_key=True),
            sa.Column("att_type_text", sa.Text(), nullable=False),
        )
    if not _inspector(bind).has_table("gpc_attribute_values"):
        op.create_table(
            "gpc_attribute_values",
            sa.Column("att_value_code", sa.String(length=8), primary_key=True),
            sa.Column("att_value_text", sa.Text(), nullable=False),
        )
    if not _inspector(bind).has_table("gpc_brick_attribute_types"):
        op.create_table(
            "gpc_brick_attribute_types",
            sa.Column("brick_code", sa.String(length=8), nullable=False),
            sa.Column("att_type_code", sa.String(length=8), nullable=False),
            sa.PrimaryKeyConstraint("brick_code", "att_type_code"),
            sa.ForeignKeyConstraint(["brick_code"], ["gpc_bricks.brick_code"]),
            sa.ForeignKeyConstraint(["att_type_code"], ["gpc_attribute_types.att_type_code"]),
        )
    if not _inspector(bind).has_table("gpc_attribute_type_values"):
        op.create_table(
            "gpc_attribute_type_values",
            sa.Column("att_type_code", sa.String(length=8), nullable=False),
            sa.Column("att_value_code", sa.String(length=8), nullable=False),
            sa.PrimaryKeyConstraint("att_type_code", "att_value_code"),
            sa.ForeignKeyConstraint(["att_type_code"], ["gpc_attribute_types.att_type_code"]),
            sa.ForeignKeyConstraint(["att_value_code"], ["gpc_attribute_values.att_value_code"]),
        )
    if not _inspector(bind).has_table("gpc_import_runs"):
        op.create_table(
            "gpc_import_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("source_name", sa.Text(), nullable=False),
            sa.Column("source_version", sa.Text()),
            sa.Column("language_code", sa.String(length=12), nullable=False),
            sa.Column("source_sha256", sa.String(length=64), nullable=False),
            sa.Column("imported_at", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("counts_json", sa.Text(), nullable=False),
            sa.Column("message", sa.Text()),
        )


def _ensure_gpc_product_groups(bind: sa.engine.Connection) -> None:
    if not _inspector(bind).has_table("gpc_product_groups"):
        op.create_table(
            "gpc_product_groups",
            sa.Column("gpc_brick_code", sa.Text(), primary_key=True),
            sa.Column("gpc_brick_name", sa.Text(), nullable=False),
            sa.Column("gpc_class_code", sa.Text()),
            sa.Column("gpc_class_name", sa.Text()),
            sa.Column("gpc_family_code", sa.Text()),
            sa.Column("gpc_family_name", sa.Text()),
            sa.Column("gpc_segment_code", sa.Text()),
            sa.Column("gpc_segment_name", sa.Text()),
            sa.Column("language_code", sa.Text()),
            sa.Column("source_version", sa.Text()),
            _active_column(bind),
            sa.Column("created_at", sa.Text()),
            sa.Column("updated_at", sa.Text()),
            sa.Column("gpc_brick_name_en", sa.Text()),
            sa.Column("gpc_class_name_en", sa.Text()),
            sa.Column("gpc_family_name_en", sa.Text()),
            sa.Column("gpc_segment_name_en", sa.Text()),
            sa.Column("brick_definition_includes_en", sa.Text()),
            sa.Column("brick_definition_excludes_en", sa.Text()),
            sa.Column("source", sa.Text()),
        )
        return

    columns = _column_map(bind, "gpc_product_groups")
    if "gpc_brick_code" not in columns or "gpc_brick_name" not in columns:
        raise RuntimeError("gpc_product_groups mist canonical GPC-identiteit")

    text_columns = {
        name
        for name in _GPC_PRODUCT_GROUP_COLUMNS
        if name not in {"gpc_brick_code", "gpc_brick_name", "active"}
    }
    for name in sorted(text_columns):
        if name not in columns:
            op.add_column("gpc_product_groups", sa.Column(name, sa.Text()))

    columns = _column_map(bind, "gpc_product_groups")
    if "active" not in columns:
        op.add_column("gpc_product_groups", _active_column(bind))
    elif bind.dialect.name == "postgresql" and not isinstance(columns["active"]["type"], sa.Boolean):
        op.alter_column(
            "gpc_product_groups",
            "active",
            existing_type=columns["active"]["type"],
            type_=sa.Boolean(),
            existing_nullable=bool(columns["active"].get("nullable", True)),
            server_default=sa.text("true"),
            postgresql_using="CASE WHEN COALESCE(active, 0) <> 0 THEN TRUE ELSE FALSE END",
        )


def _ensure_product_inventory_gpc_columns(bind: sa.engine.Connection) -> None:
    inspector = _inspector(bind)
    if not inspector.has_table("product_inventory_groups"):
        raise RuntimeError(
            "product_inventory_groups ontbreekt; voer eerdere Alembic revisions eerst uit"
        )
    columns = _column_map(bind, "product_inventory_groups")
    for name, column_type in _PRODUCT_INVENTORY_GPC_COLUMNS.items():
        if name not in columns:
            op.add_column(
                "product_inventory_groups",
                sa.Column(name, column_type, nullable=True),
            )


def _ensure_indexes(bind: sa.engine.Connection) -> None:
    for index_name, (table_name, expected_columns) in _GPC_INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in _inspector(bind).get_indexes(table_name)
        }
        existing = indexes.get(index_name)
        if existing is None:
            op.create_index(index_name, table_name, list(expected_columns), unique=False)
            continue
        actual_columns = tuple(existing.get("column_names") or ())
        if actual_columns != expected_columns or bool(existing.get("unique")):
            raise RuntimeError(
                f"{index_name} wijkt af van het canonical GPC-indexcontract"
            )


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = _inspector(bind)
    for table_name, required_columns in _GPC_REFERENCE_TABLES.items():
        if not inspector.has_table(table_name):
            raise RuntimeError(f"Canonical GPC-tabel ontbreekt na migratie: {table_name}")
        actual = set(_column_map(bind, table_name))
        missing = set(required_columns) - actual
        if missing:
            raise RuntimeError(
                f"Canonical GPC-tabel {table_name} mist kolommen: {sorted(missing)}"
            )

    if not inspector.has_table("gpc_product_groups"):
        raise RuntimeError("Canonical GPC-tabel ontbreekt na migratie: gpc_product_groups")
    product_group_columns = _column_map(bind, "gpc_product_groups")
    missing_product_group = set(_GPC_PRODUCT_GROUP_COLUMNS) - set(product_group_columns)
    if missing_product_group:
        raise RuntimeError(
            "gpc_product_groups mist canonical kolommen: "
            + ", ".join(sorted(missing_product_group))
        )
    if bind.dialect.name == "postgresql" and not isinstance(
        product_group_columns["active"]["type"], sa.Boolean
    ):
        raise RuntimeError("PostgreSQL gpc_product_groups.active is geen BOOLEAN")

    inventory_group_columns = set(_column_map(bind, "product_inventory_groups"))
    missing_inventory_gpc = set(_PRODUCT_INVENTORY_GPC_COLUMNS) - inventory_group_columns
    if missing_inventory_gpc:
        raise RuntimeError(
            "product_inventory_groups mist GPC-kolommen: "
            + ", ".join(sorted(missing_inventory_gpc))
        )

    for index_name, (table_name, expected_columns) in _GPC_INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in _inspector(bind).get_indexes(table_name)
        }
        index = indexes.get(index_name)
        if (
            index is None
            or tuple(index.get("column_names") or ()) != expected_columns
            or bool(index.get("unique"))
        ):
            raise RuntimeError(f"Canonical GPC-index ontbreekt of wijkt af: {index_name}")


def upgrade() -> None:
    bind = op.get_bind()
    _create_reference_tables(bind)
    _ensure_gpc_product_groups(bind)
    _ensure_product_inventory_gpc_columns(bind)
    _ensure_indexes(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "20260829_08 is een schema-authority cutover en wordt niet destructief gedowngraded"
    )
