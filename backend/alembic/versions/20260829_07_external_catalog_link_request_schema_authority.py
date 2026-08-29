"""Move external catalog/link request-path schema authority to Alembic.

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


def _columns(bind: sa.engine.Connection, table_name: str) -> set[str]:
    return {
        str(column.get("name") or "")
        for column in sa.inspect(bind).get_columns(table_name)
    }


def _boolean_type(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    return sa.Boolean() if bind.dialect.name == "postgresql" else sa.Integer()


def _timestamp_type(bind: sa.engine.Connection) -> sa.types.TypeEngine:
    return sa.DateTime(timezone=True) if bind.dialect.name == "postgresql" else sa.Text()


def _boolean_default(bind: sa.engine.Connection, value: bool = False) -> sa.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text("true" if value else "false")
    return sa.text("1" if value else "0")


def _ensure_external_product_candidates(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    boolean_type = _boolean_type(bind)
    timestamp_type = _timestamp_type(bind)
    if not inspector.has_table("external_product_candidates"):
        op.create_table(
            "external_product_candidates",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("receipt_line_id", sa.Text(), nullable=True),
            sa.Column("purchase_import_line_id", sa.Text(), nullable=True),
            sa.Column("context_key", sa.Text(), nullable=True),
            sa.Column("retailer_code", sa.Text(), nullable=True),
            sa.Column("receipt_line_text", sa.Text(), nullable=True),
            sa.Column("candidate_name", sa.Text(), nullable=True),
            sa.Column("candidate_brand", sa.Text(), nullable=True),
            sa.Column("candidate_category", sa.Text(), nullable=True),
            sa.Column("candidate_source_name", sa.Text(), nullable=True),
            sa.Column("candidate_source_product_code", sa.Text(), nullable=True),
            sa.Column("candidate_source_url", sa.Text(), nullable=True),
            sa.Column("source_name", sa.Text(), nullable=True),
            sa.Column("source_product_code", sa.Text(), nullable=True),
            sa.Column("retailer_article_number", sa.Text(), nullable=True),
            sa.Column("quantity_label", sa.Text(), nullable=True),
            sa.Column("variant", sa.Text(), nullable=True),
            sa.Column("source_url", sa.Text(), nullable=True),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("score_breakdown_json", sa.Text(), nullable=True),
            sa.Column("raw_payload", sa.Text(), nullable=True),
            sa.Column("global_product_id", sa.Text(), nullable=True),
            sa.Column("status", sa.Text(), nullable=True),
            sa.Column("candidate_status", sa.Text(), nullable=True),
            sa.Column("is_probable", boolean_type, nullable=False, server_default=_boolean_default(bind)),
            sa.Column("is_user_confirmed", boolean_type, nullable=False, server_default=_boolean_default(bind)),
            sa.Column("is_external_database_override", boolean_type, nullable=False, server_default=_boolean_default(bind)),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.Column("created_at", timestamp_type, nullable=True),
            sa.Column("updated_at", timestamp_type, nullable=True),
        )
    else:
        existing = _columns(bind, "external_product_candidates")
        missing_columns = {
            "receipt_line_id": sa.Column("receipt_line_id", sa.Text(), nullable=True),
            "purchase_import_line_id": sa.Column("purchase_import_line_id", sa.Text(), nullable=True),
            "context_key": sa.Column("context_key", sa.Text(), nullable=True),
            "retailer_code": sa.Column("retailer_code", sa.Text(), nullable=True),
            "receipt_line_text": sa.Column("receipt_line_text", sa.Text(), nullable=True),
            "candidate_name": sa.Column("candidate_name", sa.Text(), nullable=True),
            "candidate_brand": sa.Column("candidate_brand", sa.Text(), nullable=True),
            "candidate_category": sa.Column("candidate_category", sa.Text(), nullable=True),
            "candidate_source_name": sa.Column("candidate_source_name", sa.Text(), nullable=True),
            "candidate_source_product_code": sa.Column("candidate_source_product_code", sa.Text(), nullable=True),
            "candidate_source_url": sa.Column("candidate_source_url", sa.Text(), nullable=True),
            "source_name": sa.Column("source_name", sa.Text(), nullable=True),
            "source_product_code": sa.Column("source_product_code", sa.Text(), nullable=True),
            "retailer_article_number": sa.Column("retailer_article_number", sa.Text(), nullable=True),
            "quantity_label": sa.Column("quantity_label", sa.Text(), nullable=True),
            "variant": sa.Column("variant", sa.Text(), nullable=True),
            "source_url": sa.Column("source_url", sa.Text(), nullable=True),
            "score": sa.Column("score", sa.Float(), nullable=True),
            "score_breakdown_json": sa.Column("score_breakdown_json", sa.Text(), nullable=True),
            "raw_payload": sa.Column("raw_payload", sa.Text(), nullable=True),
            "global_product_id": sa.Column("global_product_id", sa.Text(), nullable=True),
            "status": sa.Column("status", sa.Text(), nullable=True),
            "candidate_status": sa.Column("candidate_status", sa.Text(), nullable=True),
            "is_probable": sa.Column("is_probable", boolean_type, nullable=False, server_default=_boolean_default(bind)),
            "is_user_confirmed": sa.Column("is_user_confirmed", boolean_type, nullable=False, server_default=_boolean_default(bind)),
            "is_external_database_override": sa.Column("is_external_database_override", boolean_type, nullable=False, server_default=_boolean_default(bind)),
            "created_by": sa.Column("created_by", sa.Text(), nullable=True),
            "created_at": sa.Column("created_at", timestamp_type, nullable=True),
            "updated_at": sa.Column("updated_at", timestamp_type, nullable=True),
        }
        for column_name, column in missing_columns.items():
            if column_name not in existing:
                op.add_column("external_product_candidates", column)

    indexes = {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes("external_product_candidates")
    }
    if "idx_external_product_candidates_context" not in indexes:
        op.create_index(
            "idx_external_product_candidates_context",
            "external_product_candidates",
            [
                "context_key",
                "retailer_code",
                "candidate_source_name",
                "candidate_source_product_code",
                "variant",
            ],
            unique=False,
        )


def _ensure_external_product_index(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    timestamp_type = _timestamp_type(bind)
    column_specs = {
        "source_name": sa.Column("source_name", sa.Text(), nullable=True),
        "source_product_code": sa.Column("source_product_code", sa.Text(), nullable=True),
        "gtin": sa.Column("gtin", sa.Text(), nullable=True),
        "ean": sa.Column("ean", sa.Text(), nullable=True),
        "code": sa.Column("code", sa.Text(), nullable=True),
        "product_name": sa.Column("product_name", sa.Text(), nullable=True),
        "brand": sa.Column("brand", sa.Text(), nullable=True),
        "brands": sa.Column("brands", sa.Text(), nullable=True),
        "quantity": sa.Column("quantity", sa.Text(), nullable=True),
        "net_content": sa.Column("net_content", sa.Text(), nullable=True),
        "packaging": sa.Column("packaging", sa.Text(), nullable=True),
        "category": sa.Column("category", sa.Text(), nullable=True),
        "categories": sa.Column("categories", sa.Text(), nullable=True),
        "product_type": sa.Column("product_type", sa.Text(), nullable=True),
        "search_terms": sa.Column("search_terms", sa.Text(), nullable=True),
        "image_url": sa.Column("image_url", sa.Text(), nullable=True),
        "source_url": sa.Column("source_url", sa.Text(), nullable=True),
        "retailer_code": sa.Column("retailer_code", sa.Text(), nullable=True),
        "normalized_search_text": sa.Column("normalized_search_text", sa.Text(), nullable=True),
        "created_at": sa.Column("created_at", timestamp_type, nullable=True),
        "updated_at": sa.Column("updated_at", timestamp_type, nullable=True),
    }
    if not inspector.has_table("external_product_index"):
        op.create_table(
            "external_product_index",
            sa.Column("id", sa.Text(), primary_key=True),
            *column_specs.values(),
        )
    else:
        existing = _columns(bind, "external_product_index")
        for column_name, column in column_specs.items():
            if column_name not in existing:
                op.add_column("external_product_index", column)

    indexes = {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes("external_product_index")
    }
    for index_name, columns in (
        ("idx_external_product_index_gtin", ["gtin"]),
        ("idx_external_product_index_source", ["source_name"]),
        ("idx_external_product_index_search", ["normalized_search_text"]),
    ):
        if index_name not in indexes:
            op.create_index(index_name, "external_product_index", columns, unique=False)


def _ensure_external_relation_batch(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    timestamp_type = _timestamp_type(bind)
    if not inspector.has_table("external_relation_batch_decisions"):
        op.create_table(
            "external_relation_batch_decisions",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("candidate_id", sa.Text(), nullable=False),
            sa.Column("household_article_id", sa.Text(), nullable=True),
            sa.Column("global_product_id", sa.Text(), nullable=True),
            sa.Column("decision", sa.Text(), nullable=False),
            sa.Column("decision_reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Text(), nullable=True),
            sa.Column("created_at", timestamp_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", timestamp_type, nullable=True),
        )
    else:
        required = {
            "id",
            "candidate_id",
            "household_article_id",
            "global_product_id",
            "decision",
            "decision_reason",
            "created_by",
            "created_at",
            "updated_at",
        }
        missing = required - _columns(bind, "external_relation_batch_decisions")
        if missing:
            raise RuntimeError(
                "external_relation_batch_decisions mist legacy contractkolommen: "
                f"{sorted(missing)}"
            )

    indexes = {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes("external_relation_batch_decisions")
    }
    if "idx_external_relation_batch_decisions_candidate" not in indexes:
        op.create_index(
            "idx_external_relation_batch_decisions_candidate",
            "external_relation_batch_decisions",
            ["candidate_id", "household_article_id", "decision"],
            unique=False,
        )


def _ensure_gpc_product_groups(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    timestamp_type = _timestamp_type(bind)
    specs = {
        "gpc_brick_name": sa.Column("gpc_brick_name", sa.Text(), nullable=False),
        "gpc_brick_name_en": sa.Column("gpc_brick_name_en", sa.Text(), nullable=True),
        "gpc_class_code": sa.Column("gpc_class_code", sa.Text(), nullable=True),
        "gpc_class_name": sa.Column("gpc_class_name", sa.Text(), nullable=True),
        "gpc_class_name_en": sa.Column("gpc_class_name_en", sa.Text(), nullable=True),
        "gpc_family_code": sa.Column("gpc_family_code", sa.Text(), nullable=True),
        "gpc_family_name": sa.Column("gpc_family_name", sa.Text(), nullable=True),
        "gpc_family_name_en": sa.Column("gpc_family_name_en", sa.Text(), nullable=True),
        "gpc_segment_code": sa.Column("gpc_segment_code", sa.Text(), nullable=True),
        "gpc_segment_name": sa.Column("gpc_segment_name", sa.Text(), nullable=True),
        "gpc_segment_name_en": sa.Column("gpc_segment_name_en", sa.Text(), nullable=True),
        "brick_definition_includes_en": sa.Column("brick_definition_includes_en", sa.Text(), nullable=True),
        "brick_definition_excludes_en": sa.Column("brick_definition_excludes_en", sa.Text(), nullable=True),
        "language_code": sa.Column("language_code", sa.Text(), nullable=True),
        "source_version": sa.Column("source_version", sa.Text(), nullable=True),
        "source": sa.Column("source", sa.Text(), nullable=True),
        "active": sa.Column("active", sa.Integer(), nullable=True, server_default=sa.text("1")),
        "created_at": sa.Column("created_at", timestamp_type, nullable=True),
        "updated_at": sa.Column("updated_at", timestamp_type, nullable=True),
    }
    if not inspector.has_table("gpc_product_groups"):
        op.create_table(
            "gpc_product_groups",
            sa.Column("gpc_brick_code", sa.Text(), primary_key=True),
            *specs.values(),
        )
    else:
        existing = _columns(bind, "gpc_product_groups")
        if "gpc_brick_code" not in existing or "gpc_brick_name" not in existing:
            raise RuntimeError("gpc_product_groups mist canonical sleutelkolommen")
        for column_name, column in specs.items():
            if column_name not in existing:
                op.add_column("gpc_product_groups", column)


def _ensure_product_inventory_group_gpc_columns(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("product_inventory_groups"):
        raise RuntimeError("product_inventory_groups ontbreekt")
    existing = _columns(bind, "product_inventory_groups")
    for column_name in (
        "gpc_family_code",
        "gpc_family_name",
        "gpc_class_code",
        "gpc_class_name",
        "gpc_brick_code",
    ):
        if column_name not in existing:
            op.add_column(
                "product_inventory_groups",
                sa.Column(column_name, sa.Text(), nullable=True),
            )


def _ensure_global_product_gpc_assignment(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    timestamp_type = _timestamp_type(bind)
    if not inspector.has_table("global_product_gpc_bricks"):
        op.create_table(
            "global_product_gpc_bricks",
            sa.Column("global_product_id", sa.Text(), primary_key=True),
            sa.Column("brick_code", sa.String(length=8), nullable=False),
            sa.Column(
                "assignment_source",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'manual_catalog_detail'"),
            ),
            sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
            sa.Column("migrated_from", sa.Text(), nullable=True),
            sa.Column("updated_at", timestamp_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["global_product_id"], ["global_products.id"]),
            sa.ForeignKeyConstraint(["brick_code"], ["gpc_bricks.brick_code"]),
        )
    else:
        existing = _columns(bind, "global_product_gpc_bricks")
        if not {"global_product_id", "brick_code"}.issubset(existing):
            raise RuntimeError("global_product_gpc_bricks mist canonical sleutelkolommen")
        for column_name, column in {
            "assignment_source": sa.Column(
                "assignment_source", sa.Text(), nullable=False, server_default=sa.text("'manual_catalog_detail'")
            ),
            "confidence": sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
            "migrated_from": sa.Column("migrated_from", sa.Text(), nullable=True),
            "updated_at": sa.Column(
                "updated_at", timestamp_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
            ),
        }.items():
            if column_name not in existing:
                op.add_column("global_product_gpc_bricks", column)

    indexes = {
        str(index.get("name") or ""): index
        for index in sa.inspect(bind).get_indexes("global_product_gpc_bricks")
    }
    if "idx_global_product_gpc_brick_code" not in indexes:
        op.create_index(
            "idx_global_product_gpc_brick_code",
            "global_product_gpc_bricks",
            ["brick_code"],
            unique=False,
        )

    if not sa.inspect(bind).has_table("global_product_gpc_migration_suppressions"):
        op.create_table(
            "global_product_gpc_migration_suppressions",
            sa.Column("global_product_id", sa.Text(), primary_key=True),
            sa.Column("created_at", timestamp_type, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["global_product_id"], ["global_products.id"]),
        )


def _backfill_confirmed_legacy_gpc_assignments(bind: sa.engine.Connection) -> None:
    inspector = sa.inspect(bind)
    required_tables = {
        "product_group_memberships",
        "product_inventory_groups",
        "gpc_bricks",
        "global_product_gpc_bricks",
        "global_product_gpc_migration_suppressions",
    }
    if not all(inspector.has_table(table_name) for table_name in required_tables):
        return

    membership_columns = _columns(bind, "product_group_memberships")
    group_columns = _columns(bind, "product_inventory_groups")
    if not {
        "global_product_id",
        "inventory_group_key",
        "confirmed_by_user",
    }.issubset(membership_columns):
        return
    if not {"inventory_group_key", "gpc_brick_code"}.issubset(group_columns):
        return

    active_predicate = "COALESCE(pgm.active, 1) = 1" if "active" in membership_columns else "1 = 1"
    confidence_expr = "COALESCE(pgm.confidence, 1.0)" if "confidence" in membership_columns else "1.0"
    source_expr = "COALESCE(pgm.source, 'product_group_membership')" if "source" in membership_columns else "'product_group_membership'"
    updated_expr = "pgm.updated_at" if "updated_at" in membership_columns else "NULL"
    rows = bind.execute(sa.text(f"""
        SELECT
            pgm.global_product_id,
            pig.gpc_brick_code AS brick_code,
            {confidence_expr} AS confidence,
            pgm.inventory_group_key,
            {source_expr} AS legacy_source,
            {updated_expr} AS membership_updated_at
        FROM product_group_memberships pgm
        JOIN product_inventory_groups pig
          ON pig.inventory_group_key = pgm.inventory_group_key
        JOIN gpc_bricks b
          ON b.brick_code = pig.gpc_brick_code
        WHERE COALESCE(pgm.confirmed_by_user, 0) = 1
          AND {active_predicate}
          AND length(trim(COALESCE(pig.gpc_brick_code, ''))) = 8
        ORDER BY pgm.global_product_id, {confidence_expr} DESC, {updated_expr} DESC
    """)).mappings().all()

    seen_products: set[str] = set()
    for row in rows:
        product_id = str(row.get("global_product_id") or "").strip()
        brick_code = str(row.get("brick_code") or "").strip()
        if not product_id or not brick_code or product_id in seen_products:
            continue
        seen_products.add(product_id)
        if bind.execute(
            sa.text("SELECT 1 FROM global_product_gpc_bricks WHERE global_product_id = :id LIMIT 1"),
            {"id": product_id},
        ).first():
            continue
        if bind.execute(
            sa.text(
                "SELECT 1 FROM global_product_gpc_migration_suppressions "
                "WHERE global_product_id = :id LIMIT 1"
            ),
            {"id": product_id},
        ).first():
            continue
        bind.execute(
            sa.text("""
                INSERT INTO global_product_gpc_bricks (
                    global_product_id,
                    brick_code,
                    assignment_source,
                    confidence,
                    migrated_from,
                    updated_at
                ) VALUES (
                    :global_product_id,
                    :brick_code,
                    'migrated_confirmed_product_group',
                    :confidence,
                    :migrated_from,
                    CURRENT_TIMESTAMP
                )
            """),
            {
                "global_product_id": product_id,
                "brick_code": brick_code,
                "confidence": float(row.get("confidence") or 1.0),
                "migrated_from": str(
                    row.get("inventory_group_key")
                    or row.get("legacy_source")
                    or "product_group_membership"
                ),
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_external_product_candidates(bind)
    _ensure_external_product_index(bind)
    _ensure_external_relation_batch(bind)
    _ensure_gpc_product_groups(bind)
    _ensure_product_inventory_group_gpc_columns(bind)
    _ensure_global_product_gpc_assignment(bind)
    _backfill_confirmed_legacy_gpc_assignments(bind)


def downgrade() -> None:
    # Authority/adoption migration: existing production schema/data is intentionally
    # not destructively removed on downgrade.
    pass
