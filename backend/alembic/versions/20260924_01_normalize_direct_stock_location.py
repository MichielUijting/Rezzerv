"""Normalize stock that was incorrectly stored at the system Direct location.

Revision ID: 20260924_01
Revises: 20260921_01
"""

from __future__ import annotations

from decimal import Decimal

from alembic import op
import sqlalchemy as sa


revision = "20260924_01"
down_revision = "20260921_01"
branch_labels = None
depends_on = None

_DIRECT_HANDLING = "DIRECT_CONSUMPTION"


def _columns(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {
        str(column.get("name") or "")
        for column in inspector.get_columns(table_name)
    }


def _direct_spaces(bind) -> list[dict]:
    space_columns = _columns(bind, "spaces")
    predicates: list[str] = []
    if "is_direct" in space_columns:
        predicates.append("COALESCE(is_direct, FALSE) = TRUE")
    if "system_key" in space_columns:
        predicates.append("COALESCE(system_key, '') = 'system.direct'")
    if not predicates:
        raise RuntimeError("spaces mist canonical Direct-markering")
    rows = bind.execute(
        sa.text(
            "SELECT id, household_id FROM spaces WHERE "
            + " OR ".join(f"({predicate})" for predicate in predicates)
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _direct_location_ids(bind, space_id: str) -> list[str]:
    ids = [str(space_id)]
    if _columns(bind, "sublocations"):
        rows = bind.execute(
            sa.text(
                """
                SELECT id
                FROM sublocations
                WHERE space_id = :space_id
                """
            ),
            {"space_id": str(space_id)},
        ).scalars().all()
        ids.extend(str(value) for value in rows if str(value or "").strip())
    return list(dict.fromkeys(ids))


def _is_active(row: dict, inventory_columns: set[str]) -> bool:
    if "status" not in inventory_columns:
        return True
    return str(row.get("status") or "active").strip().lower() == "active"


def _normalize_inventory_for_space(bind, *, household_id: str, space_id: str) -> None:
    inventory_columns = _columns(bind, "inventory")
    if not inventory_columns:
        return
    required = {"id", "household_id", "household_article_id", "aantal", "space_id", "sublocation_id"}
    missing = required - inventory_columns
    if missing:
        raise RuntimeError(f"inventory mist kolommen voor Direct-normalisatie: {sorted(missing)}")

    status_select = ", i.status" if "status" in inventory_columns else ""
    rows = bind.execute(
        sa.text(
            f"""
            SELECT i.id, i.household_id, i.household_article_id, i.aantal
                   {status_select},
                   COALESCE(ha.default_inventory_handling, 'STOCK') AS inventory_handling
            FROM inventory i
            JOIN household_articles ha
              ON ha.id = i.household_article_id
             AND ha.household_id = i.household_id
            WHERE i.household_id = :household_id
              AND i.space_id = :space_id
            ORDER BY i.id
            """
        ),
        {"household_id": household_id, "space_id": space_id},
    ).mappings().all()

    updated_assignment = ", updated_at = CURRENT_TIMESTAMP" if "updated_at" in inventory_columns else ""
    for row in rows:
        inventory_id = str(row["id"])
        article_id = str(row["household_article_id"])
        handling = str(row.get("inventory_handling") or "STOCK").strip().upper()

        if handling == _DIRECT_HANDLING:
            bind.execute(
                sa.text("DELETE FROM inventory WHERE id = :inventory_id"),
                {"inventory_id": inventory_id},
            )
            continue

        existing = None
        if _is_active(dict(row), inventory_columns):
            status_filter = (
                "AND COALESCE(status, 'active') = 'active'"
                if "status" in inventory_columns
                else ""
            )
            existing = bind.execute(
                sa.text(
                    f"""
                    SELECT id
                    FROM inventory
                    WHERE household_id = :household_id
                      AND household_article_id = :article_id
                      AND space_id IS NULL
                      AND sublocation_id IS NULL
                      AND id <> :inventory_id
                      {status_filter}
                    ORDER BY id
                    LIMIT 1
                    """
                ),
                {
                    "household_id": household_id,
                    "article_id": article_id,
                    "inventory_id": inventory_id,
                },
            ).mappings().first()

        if existing:
            quantity = row.get("aantal")
            if quantity is None:
                quantity = Decimal("0")
            bind.execute(
                sa.text(
                    f"""
                    UPDATE inventory
                    SET aantal = COALESCE(aantal, 0) + :quantity
                        {updated_assignment}
                    WHERE id = :target_id
                    """
                ),
                {"quantity": quantity, "target_id": str(existing["id"])},
            )
            bind.execute(
                sa.text("DELETE FROM inventory WHERE id = :inventory_id"),
                {"inventory_id": inventory_id},
            )
            continue

        bind.execute(
            sa.text(
                f"""
                UPDATE inventory
                SET space_id = NULL,
                    sublocation_id = NULL
                    {updated_assignment}
                WHERE id = :inventory_id
                """
            ),
            {"inventory_id": inventory_id},
        )


def _normalize_inventory_events(bind, *, direct_location_ids: list[str]) -> None:
    event_columns = _columns(bind, "inventory_events")
    if not {"household_id", "location_id"} <= event_columns:
        return
    if "household_article_id" in event_columns:
        article_ref = "e.household_article_id"
    elif "article_id" in event_columns:
        article_ref = "e.article_id"
    else:
        return

    assignments = ["location_id = NULL"]
    if "location_label" in event_columns:
        assignments.append("location_label = NULL")

    for location_id in direct_location_ids:
        bind.execute(
            sa.text(
                f"""
                UPDATE inventory_events AS e
                SET {", ".join(assignments)}
                WHERE e.location_id = :location_id
                  AND EXISTS (
                      SELECT 1
                      FROM household_articles ha
                      WHERE ha.id = {article_ref}
                        AND ha.household_id = e.household_id
                        AND COALESCE(ha.default_inventory_handling, 'STOCK') <> :direct_handling
                  )
                """
            ),
            {
                "location_id": location_id,
                "direct_handling": _DIRECT_HANDLING,
            },
        )


def _normalize_purchase_import_lines(bind, *, direct_location_ids: list[str]) -> None:
    line_columns = _columns(bind, "purchase_import_lines")
    if not {
        "batch_id",
        "matched_household_article_id",
        "target_location_id",
    } <= line_columns:
        return
    if not _columns(bind, "purchase_import_batches"):
        return

    location_columns = [
        name
        for name in ("target_location_id", "suggested_location_id", "final_location_id")
        if name in line_columns
    ]
    for location_id in direct_location_ids:
        assignments = [
            f"{name} = CASE WHEN {name} = :location_id THEN NULL ELSE {name} END"
            for name in location_columns
        ]
        if "location_override_mode" in line_columns:
            assignments.append(
                "location_override_mode = CASE "
                "WHEN target_location_id = :location_id THEN 'cleared' "
                "ELSE location_override_mode END"
            )
        if "updated_at" in line_columns:
            assignments.append("updated_at = CURRENT_TIMESTAMP")

        location_predicate = " OR ".join(
            f"pil.{name} = :location_id" for name in location_columns
        )
        bind.execute(
            sa.text(
                f"""
                UPDATE purchase_import_lines AS pil
                SET {", ".join(assignments)}
                WHERE ({location_predicate})
                  AND EXISTS (
                      SELECT 1
                      FROM purchase_import_batches pib
                      JOIN household_articles ha
                        ON ha.id = pil.matched_household_article_id
                       AND ha.household_id = pib.household_id
                      WHERE pib.id = pil.batch_id
                        AND COALESCE(ha.default_inventory_handling, 'STOCK') <> :direct_handling
                  )
                """
            ),
            {
                "location_id": location_id,
                "direct_handling": _DIRECT_HANDLING,
            },
        )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"Unsupported Rezzerv migration dialect: {bind.dialect.name}")

    required_tables = {"spaces", "household_articles", "inventory"}
    actual_tables = set(sa.inspect(bind).get_table_names())
    missing = required_tables - actual_tables
    if missing:
        raise RuntimeError(
            "Direct-stock normalisatie mist verplichte tabellen: "
            f"{sorted(missing)}"
        )

    article_columns = _columns(bind, "household_articles")
    if "default_inventory_handling" not in article_columns:
        raise RuntimeError(
            "household_articles mist default_inventory_handling voor Direct-normalisatie"
        )

    for space in _direct_spaces(bind):
        space_id = str(space.get("id") or "").strip()
        household_id = str(space.get("household_id") or "").strip()
        if not space_id or not household_id:
            continue
        direct_location_ids = _direct_location_ids(bind, space_id)
        _normalize_inventory_for_space(
            bind,
            household_id=household_id,
            space_id=space_id,
        )
        _normalize_inventory_events(
            bind,
            direct_location_ids=direct_location_ids,
        )
        _normalize_purchase_import_lines(
            bind,
            direct_location_ids=direct_location_ids,
        )


def downgrade() -> None:
    raise RuntimeError(
        "Direct-stock location normalization is intentionally non-destructive "
        "and cannot be reversed safely."
    )
