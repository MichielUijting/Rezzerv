"""Consolidate duplicate canonical items on active shopping lists.

Revision ID: 20260918_01
Revises: 20260915_01
"""

from __future__ import annotations

from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "20260918_01"
down_revision = "20260915_01"
branch_labels = None
depends_on = None


def _as_count(value) -> Decimal:
    if value is None:
        return Decimal("1")
    return Decimal(str(value))


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if not {"shopping_lists", "shopping_list_items"}.issubset(tables):
        raise RuntimeError("Shopping-list tables must exist before duplicate consolidation")

    groups = bind.execute(sa.text("""
        SELECT
            items.shopping_list_id,
            items.household_id,
            lower(trim(COALESCE(items.source_type, 'manual'))) AS source_type,
            trim(COALESCE(items.source_id, '')) AS source_id,
            COUNT(*) AS duplicate_count
        FROM shopping_list_items items
        JOIN shopping_lists lists
          ON lists.id = items.shopping_list_id
         AND lists.household_id = items.household_id
        WHERE lists.status = 'active'
          AND trim(COALESCE(items.source_id, '')) <> ''
          AND lower(trim(COALESCE(items.source_type, 'manual'))) <> 'manual'
        GROUP BY
            items.shopping_list_id,
            items.household_id,
            lower(trim(COALESCE(items.source_type, 'manual'))),
            trim(COALESCE(items.source_id, ''))
        HAVING COUNT(*) > 1
    """)).mappings().all()

    for group in groups:
        rows = bind.execute(sa.text("""
            SELECT *
            FROM shopping_list_items
            WHERE shopping_list_id = :shopping_list_id
              AND household_id = :household_id
              AND lower(trim(COALESCE(source_type, 'manual'))) = :source_type
              AND trim(COALESCE(source_id, '')) = :source_id
            ORDER BY created_at ASC, id ASC
        """), {
            "shopping_list_id": group["shopping_list_id"],
            "household_id": group["household_id"],
            "source_type": group["source_type"],
            "source_id": group["source_id"],
        }).mappings().all()

        if len(rows) < 2:
            continue

        keeper = rows[0]
        merged_quantity = sum((_as_count(row.get("quantity")) for row in rows), Decimal("0"))
        all_checked = 1 if all(bool(row.get("checked")) for row in rows) else 0
        updated_at = max(str(row.get("updated_at") or row.get("created_at") or "") for row in rows)

        bind.execute(sa.text("""
            UPDATE shopping_list_items
            SET quantity = :quantity,
                checked = :checked,
                updated_at = :updated_at
            WHERE id = :id
              AND shopping_list_id = :shopping_list_id
              AND household_id = :household_id
        """), {
            "quantity": merged_quantity,
            "checked": all_checked,
            "updated_at": updated_at,
            "id": keeper["id"],
            "shopping_list_id": group["shopping_list_id"],
            "household_id": group["household_id"],
        })

        for duplicate in rows[1:]:
            bind.execute(sa.text("""
                DELETE FROM shopping_list_items
                WHERE id = :id
                  AND shopping_list_id = :shopping_list_id
                  AND household_id = :household_id
            """), {
                "id": duplicate["id"],
                "shopping_list_id": group["shopping_list_id"],
                "household_id": group["household_id"],
            })


def downgrade() -> None:
    # Data consolidation is intentionally irreversible: recreating historical
    # duplicate rows would require inventing identities and timestamps.
    pass
