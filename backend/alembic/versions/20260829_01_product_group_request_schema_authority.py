"""Move product taxonomy and inventory-group request schema authority to Alembic.

Revision ID: 20260829_01
Revises: 20260828_05
Create Date: 2026-08-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_01"
down_revision: Union[str, None] = "20260828_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE_COLUMNS: dict[str, dict[str, sa.Column]] = {
    "product_taxonomy": {
        "intent_key": sa.Column("intent_key", sa.Text(), nullable=False),
        "canonical_name": sa.Column("canonical_name", sa.Text(), nullable=False),
        "category": sa.Column("category", sa.Text(), nullable=True),
        "product_type": sa.Column("product_type", sa.Text(), nullable=True),
        "parent_intent_key": sa.Column("parent_intent_key", sa.Text(), nullable=True),
        "default_base_unit": sa.Column(
            "default_base_unit", sa.Text(), nullable=True, server_default=sa.text("'st'")
        ),
        "is_active": sa.Column(
            "is_active", sa.Integer(), nullable=True, server_default=sa.text("1")
        ),
        "created_at": sa.Column("created_at", sa.Text(), nullable=True),
        "updated_at": sa.Column("updated_at", sa.Text(), nullable=True),
        "created_by": sa.Column("created_by", sa.Text(), nullable=True),
        "updated_by": sa.Column("updated_by", sa.Text(), nullable=True),
    },
    "product_taxonomy_synonyms": {
        "id": sa.Column("id", sa.Text(), nullable=False),
        "intent_key": sa.Column("intent_key", sa.Text(), nullable=False),
        "synonym": sa.Column("synonym", sa.Text(), nullable=False),
        "normalized_synonym": sa.Column("normalized_synonym", sa.Text(), nullable=False),
        "priority": sa.Column("priority", sa.Integer(), nullable=True, server_default=sa.text("100")),
        "is_active": sa.Column("is_active", sa.Integer(), nullable=True, server_default=sa.text("1")),
        "source": sa.Column("source", sa.Text(), nullable=True),
    },
    "retailer_receipt_terms": {
        "id": sa.Column("id", sa.Text(), nullable=False),
        "retailer_code": sa.Column("retailer_code", sa.Text(), nullable=False),
        "receipt_term": sa.Column("receipt_term", sa.Text(), nullable=False),
        "normalized_receipt_term": sa.Column("normalized_receipt_term", sa.Text(), nullable=False),
        "normalized_term": sa.Column("normalized_term", sa.Text(), nullable=True),
        "intent_key": sa.Column("intent_key", sa.Text(), nullable=False),
        "confidence": sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
        "is_active": sa.Column("is_active", sa.Integer(), nullable=True, server_default=sa.text("1")),
        "source": sa.Column("source", sa.Text(), nullable=True),
    },
    "product_taxonomy_terms": {
        "id": sa.Column("id", sa.Text(), nullable=False),
        "intent_key": sa.Column("intent_key", sa.Text(), nullable=False),
        "term": sa.Column("term", sa.Text(), nullable=False),
        "term_type": sa.Column("term_type", sa.Text(), nullable=True),
        "language": sa.Column("language", sa.Text(), nullable=True, server_default=sa.text("'nl'")),
        "confidence": sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
        "source": sa.Column("source", sa.Text(), nullable=True),
        "active": sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
        "created_at": sa.Column("created_at", sa.Text(), nullable=True),
        "updated_at": sa.Column("updated_at", sa.Text(), nullable=True),
    },
    "product_inventory_groups": {
        "inventory_group_key": sa.Column("inventory_group_key", sa.Text(), nullable=False),
        "display_name": sa.Column("display_name", sa.Text(), nullable=False),
        "default_base_unit": sa.Column("default_base_unit", sa.Text(), nullable=False),
        "aggregation_mode": sa.Column(
            "aggregation_mode", sa.Text(), nullable=True, server_default=sa.text("'sum_quantity'")
        ),
        "active": sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
        "created_at": sa.Column("created_at", sa.Text(), nullable=True),
        "updated_at": sa.Column("updated_at", sa.Text(), nullable=True),
        "source": sa.Column("source", sa.Text(), nullable=True),
    },
    "product_group_memberships": {
        "id": sa.Column("id", sa.Text(), nullable=False),
        "global_product_id": sa.Column("global_product_id", sa.Text(), nullable=False),
        "inventory_group_key": sa.Column("inventory_group_key", sa.Text(), nullable=False),
        "comparison_group_key": sa.Column("comparison_group_key", sa.Text(), nullable=True),
        "confidence": sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
        "source": sa.Column("source", sa.Text(), nullable=True),
        "confirmed_by_user": sa.Column(
            "confirmed_by_user", sa.Integer(), nullable=True, server_default=sa.text("0")
        ),
        "active": sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
        "created_at": sa.Column("created_at", sa.Text(), nullable=True),
        "updated_at": sa.Column("updated_at", sa.Text(), nullable=True),
    },
    "product_unit_conversions": {
        "id": sa.Column("id", sa.Text(), nullable=False),
        "global_product_id": sa.Column("global_product_id", sa.Text(), nullable=False),
        "inventory_group_key": sa.Column("inventory_group_key", sa.Text(), nullable=True),
        "content_value": sa.Column("content_value", sa.Float(), nullable=True),
        "content_unit": sa.Column("content_unit", sa.Text(), nullable=True),
        "base_quantity": sa.Column("base_quantity", sa.Float(), nullable=True),
        "base_unit": sa.Column("base_unit", sa.Text(), nullable=True),
        "confidence": sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
        "source": sa.Column("source", sa.Text(), nullable=True),
        "created_at": sa.Column("created_at", sa.Text(), nullable=True),
        "updated_at": sa.Column("updated_at", sa.Text(), nullable=True),
    },
    "inventory_item_group_assignments": {
        "inventory_id": sa.Column("inventory_id", sa.Text(), nullable=False),
        "inventory_group_key": sa.Column("inventory_group_key", sa.Text(), nullable=False),
        "source": sa.Column("source", sa.Text(), nullable=True),
        "confirmed_by_user": sa.Column(
            "confirmed_by_user", sa.Integer(), nullable=True, server_default=sa.text("1")
        ),
        "active": sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
        "created_at": sa.Column("created_at", sa.Text(), nullable=True),
        "updated_at": sa.Column("updated_at", sa.Text(), nullable=True),
    },
}

_INDEXES: dict[str, tuple[str, tuple[str, ...], bool]] = {
    "ux_product_taxonomy_intent_key": ("product_taxonomy", ("intent_key",), True),
    "idx_product_taxonomy_synonyms_norm": (
        "product_taxonomy_synonyms", ("normalized_synonym",), False
    ),
    "idx_product_taxonomy_synonyms_intent": (
        "product_taxonomy_synonyms", ("intent_key",), False
    ),
    "idx_retailer_receipt_terms_norm": (
        "retailer_receipt_terms", ("retailer_code", "normalized_receipt_term"), False
    ),
    "idx_retailer_receipt_terms_intent": (
        "retailer_receipt_terms", ("intent_key",), False
    ),
    "idx_product_taxonomy_terms_intent": (
        "product_taxonomy_terms", ("intent_key", "active"), False
    ),
    "idx_product_group_memberships_product": (
        "product_group_memberships", ("global_product_id", "inventory_group_key"), False
    ),
    "idx_inventory_item_group_assignments_group": (
        "inventory_item_group_assignments", ("inventory_group_key", "active"), False
    ),
}


def _create_missing_table(table_name: str) -> None:
    if table_name == "product_taxonomy":
        op.create_table(
            table_name,
            sa.Column("intent_key", sa.Text(), primary_key=True),
            sa.Column("canonical_name", sa.Text(), nullable=False),
            sa.Column("category", sa.Text(), nullable=True),
            sa.Column("product_type", sa.Text(), nullable=True),
            sa.Column("parent_intent_key", sa.Text(), nullable=True),
            sa.Column("default_base_unit", sa.Text(), nullable=True, server_default=sa.text("'st'")),
            sa.Column("is_active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.Text(), nullable=True),
        )
        return
    if table_name == "product_taxonomy_synonyms":
        op.create_table(
            table_name,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("intent_key", sa.Text(), nullable=False),
            sa.Column("synonym", sa.Text(), nullable=False),
            sa.Column("normalized_synonym", sa.Text(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=True, server_default=sa.text("100")),
            sa.Column("is_active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("source", sa.Text(), nullable=True),
        )
        return
    if table_name == "retailer_receipt_terms":
        op.create_table(
            table_name,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("retailer_code", sa.Text(), nullable=False),
            sa.Column("receipt_term", sa.Text(), nullable=False),
            sa.Column("normalized_receipt_term", sa.Text(), nullable=False),
            sa.Column("normalized_term", sa.Text(), nullable=True),
            sa.Column("intent_key", sa.Text(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
            sa.Column("is_active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("source", sa.Text(), nullable=True),
        )
        return
    if table_name == "product_taxonomy_terms":
        op.create_table(
            table_name,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("intent_key", sa.Text(), nullable=False),
            sa.Column("term", sa.Text(), nullable=False),
            sa.Column("term_type", sa.Text(), nullable=True),
            sa.Column("language", sa.Text(), nullable=True, server_default=sa.text("'nl'")),
            sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
            sa.Column("source", sa.Text(), nullable=True),
            sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=True),
        )
        return
    if table_name == "product_inventory_groups":
        op.create_table(
            table_name,
            sa.Column("inventory_group_key", sa.Text(), primary_key=True),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("default_base_unit", sa.Text(), nullable=False),
            sa.Column("aggregation_mode", sa.Text(), nullable=True, server_default=sa.text("'sum_quantity'")),
            sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=True),
            sa.Column("source", sa.Text(), nullable=True),
        )
        return
    if table_name == "product_group_memberships":
        op.create_table(
            table_name,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("global_product_id", sa.Text(), nullable=False),
            sa.Column("inventory_group_key", sa.Text(), nullable=False),
            sa.Column("comparison_group_key", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
            sa.Column("source", sa.Text(), nullable=True),
            sa.Column("confirmed_by_user", sa.Integer(), nullable=True, server_default=sa.text("0")),
            sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=True),
        )
        return
    if table_name == "product_unit_conversions":
        op.create_table(
            table_name,
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("global_product_id", sa.Text(), nullable=False),
            sa.Column("inventory_group_key", sa.Text(), nullable=True),
            sa.Column("content_value", sa.Float(), nullable=True),
            sa.Column("content_unit", sa.Text(), nullable=True),
            sa.Column("base_quantity", sa.Float(), nullable=True),
            sa.Column("base_unit", sa.Text(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True, server_default=sa.text("1.0")),
            sa.Column("source", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=True),
        )
        return
    if table_name == "inventory_item_group_assignments":
        op.create_table(
            table_name,
            sa.Column("inventory_id", sa.Text(), primary_key=True),
            sa.Column("inventory_group_key", sa.Text(), nullable=False),
            sa.Column("source", sa.Text(), nullable=True),
            sa.Column("confirmed_by_user", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
            sa.Column("created_at", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.Text(), nullable=True),
        )
        return
    raise RuntimeError(f"Geen canonical create-contract voor {table_name}")


def _ensure_columns(bind: sa.engine.Connection, table_name: str) -> None:
    inspector = sa.inspect(bind)
    existing = {str(column.get("name") or "") for column in inspector.get_columns(table_name)}
    for column_name, column in _TABLE_COLUMNS[table_name].items():
        if column_name not in existing:
            op.add_column(table_name, column.copy())


def _ensure_taxonomy_identity(bind: sa.engine.Connection) -> None:
    null_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM product_taxonomy WHERE intent_key IS NULL OR trim(intent_key) = ''")
    ).scalar_one()
    if int(null_count or 0) > 0:
        raise RuntimeError("product_taxonomy bevat rijen zonder canonical intent_key")
    duplicates = bind.execute(
        sa.text(
            "SELECT intent_key FROM product_taxonomy "
            "GROUP BY intent_key HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates is not None:
        raise RuntimeError("product_taxonomy bevat dubbele intent_key waarden")


def _backfill_taxonomy_compatibility(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    columns = {str(column.get("name") or "") for column in inspector.get_columns("product_taxonomy")}
    if "active" in columns:
        bind.execute(
            sa.text(
                "UPDATE product_taxonomy "
                "SET is_active = COALESCE(is_active, active, 1) "
                "WHERE is_active IS NULL"
            )
        )
    else:
        bind.execute(
            sa.text("UPDATE product_taxonomy SET is_active = 1 WHERE is_active IS NULL")
        )
    bind.execute(
        sa.text(
            "UPDATE product_taxonomy SET default_base_unit = 'st' "
            "WHERE default_base_unit IS NULL OR trim(default_base_unit) = ''"
        )
    )


def _ensure_index(bind: sa.engine.Connection, name: str, table: str, columns: tuple[str, ...], unique: bool) -> None:
    inspector = sa.inspect(bind)
    indexes = {str(index.get("name") or ""): index for index in inspector.get_indexes(table)}
    existing = indexes.get(name)
    if existing is None:
        op.create_index(name, table, list(columns), unique=unique)
        return
    actual_columns = tuple(str(column or "") for column in (existing.get("column_names") or ()))
    if actual_columns != columns or bool(existing.get("unique")) != unique:
        raise RuntimeError(
            f"Bestaande index {name} wijkt af: expected={columns!r}/{unique} "
            f"actual={actual_columns!r}/{bool(existing.get('unique'))}"
        )


def _deduplicate_active_product_type_memberships(bind: sa.engine.Connection) -> None:
    """Preserve one deterministic active product-type membership per global product."""
    rows = bind.execute(
        sa.text(
            "SELECT id, global_product_id "
            "FROM product_group_memberships "
            "WHERE COALESCE(active, 1) = 1 "
            "ORDER BY global_product_id, COALESCE(confirmed_by_user, 0) DESC, "
            "COALESCE(updated_at, created_at, '') DESC, id DESC"
        )
    ).mappings().all()
    seen: set[str] = set()
    for row in rows:
        product_id = str(row.get("global_product_id") or "").strip()
        membership_id = str(row.get("id") or "").strip()
        if not product_id or not membership_id:
            continue
        if product_id in seen:
            bind.execute(
                sa.text(
                    "UPDATE product_group_memberships "
                    "SET active = 0, updated_at = CURRENT_TIMESTAMP "
                    "WHERE id = :id"
                ),
                {"id": membership_id},
            )
        else:
            seen.add(product_id)


def _ensure_primary_product_membership_index(bind: sa.engine.Connection) -> None:
    name = "idx_product_group_memberships_one_active_product_type"
    inspector = sa.inspect(bind)
    indexes = {str(index.get("name") or ""): index for index in inspector.get_indexes("product_group_memberships")}
    if name in indexes:
        return
    op.create_index(
        name,
        "product_group_memberships",
        ["global_product_id"],
        unique=True,
        postgresql_where=sa.text("COALESCE(active, 1) = 1"),
        sqlite_where=sa.text("COALESCE(active, 1) = 1"),
    )


def _validate_contract(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    for table_name, required_columns in _TABLE_COLUMNS.items():
        if not inspector.has_table(table_name):
            raise RuntimeError(f"{table_name} ontbreekt na schema-authority migratie")
        actual = {str(column.get("name") or "") for column in inspector.get_columns(table_name)}
        missing = set(required_columns) - actual
        if missing:
            raise RuntimeError(f"{table_name} mist canonical kolommen: {sorted(missing)}")
    _ensure_taxonomy_identity(bind)
    for index_name, (table_name, columns, unique) in _INDEXES.items():
        indexes = {
            str(index.get("name") or ""): index
            for index in sa.inspect(bind).get_indexes(table_name)
        }
        index = indexes.get(index_name)
        if index is None:
            raise RuntimeError(f"Canonical index {index_name} ontbreekt")
        actual_columns = tuple(str(column or "") for column in (index.get("column_names") or ()))
        if actual_columns != columns or bool(index.get("unique")) != unique:
            raise RuntimeError(f"Canonical index {index_name} wijkt af")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"sqlite", "postgresql"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    for table_name in _TABLE_COLUMNS:
        inspector = sa.inspect(bind)
        if not inspector.has_table(table_name):
            _create_missing_table(table_name)
        else:
            _ensure_columns(bind, table_name)

    _ensure_taxonomy_identity(bind)
    _backfill_taxonomy_compatibility(bind)

    for index_name, (table_name, columns, unique) in _INDEXES.items():
        _ensure_index(bind, index_name, table_name, columns, unique)
    _deduplicate_active_product_type_memberships(bind)
    _ensure_primary_product_membership_index(bind)
    _validate_contract(bind)


def downgrade() -> None:
    raise RuntimeError(
        "The product-group request schema-authority revision is intentionally "
        "non-destructive and cannot be downgraded."
    )
