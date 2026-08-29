from __future__ import annotations

import uuid

from sqlalchemy import inspect, text


DIRECT_LOCATION_NAME = "Direct"
_DIRECT_INDEX_NAME = "ux_spaces_household_direct"
_REQUIRED_SPACE_COLUMNS = {"id", "naam", "household_id", "active", "is_direct"}


def _validate_direct_location_schema(conn) -> None:
    inspector = inspect(conn)
    if not inspector.has_table("spaces"):
        raise RuntimeError(
            "Canonical Direct-location foundation mist spaces. "
            "Voer Alembic migrations uit met MIGRATION_DATABASE_URL."
        )
    columns = {
        str(column.get("name") or "")
        for column in inspector.get_columns("spaces")
    }
    missing = _REQUIRED_SPACE_COLUMNS - columns
    if missing:
        raise RuntimeError(
            f"Canonical Direct-location foundation wijkt af: spaces mist {sorted(missing)}. "
            "Voer Alembic migrations uit."
        )
    indexes = {
        str(index.get("name") or ""): index
        for index in inspector.get_indexes("spaces")
    }
    direct_index = indexes.get(_DIRECT_INDEX_NAME)
    if not direct_index:
        raise RuntimeError(
            f"Canonical Direct-location foundation mist {_DIRECT_INDEX_NAME}. "
            "Voer Alembic migrations uit."
        )
    if not bool(direct_index.get("unique")) or tuple(direct_index.get("column_names") or ()) != (
        "household_id",
    ):
        raise RuntimeError(
            f"Canonical Direct-location index wijkt af: {_DIRECT_INDEX_NAME}. "
            "Voer Alembic migrations uit."
        )


def ensure_canonical_direct_location(conn, *, household_id: str) -> str:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    _validate_direct_location_schema(conn)

    marked = conn.execute(text("""
        SELECT id
        FROM spaces
        WHERE household_id = :household_id
          AND is_direct = :is_direct
        LIMIT 1
    """), {
        "household_id": normalized_household_id,
        "is_direct": 1,
    }).mappings().first()

    direct_id = str(marked.get("id") or "").strip() if marked else ""
    if not direct_id:
        legacy = conn.execute(text("""
            SELECT id
            FROM spaces
            WHERE household_id = :household_id
              AND lower(trim(naam)) LIKE 'direct%'
            ORDER BY
              CASE WHEN lower(trim(naam)) = 'direct' THEN 0 ELSE 1 END,
              id
            LIMIT 1
        """), {"household_id": normalized_household_id}).mappings().first()
        direct_id = str(legacy.get("id") or "").strip() if legacy else ""

    if not direct_id:
        direct_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO spaces (id, naam, household_id, active, is_direct)
            VALUES (:id, :naam, :household_id, :active, :is_direct)
        """), {
            "id": direct_id,
            "naam": DIRECT_LOCATION_NAME,
            "household_id": normalized_household_id,
            "active": True,
            "is_direct": 1,
        })
    else:
        conn.execute(text("""
            UPDATE spaces
            SET naam = :naam,
                active = :active,
                is_direct = :is_direct
            WHERE id = :id
              AND household_id = :household_id
        """), {
            "id": direct_id,
            "household_id": normalized_household_id,
            "naam": DIRECT_LOCATION_NAME,
            "active": True,
            "is_direct": 1,
        })

    return direct_id
