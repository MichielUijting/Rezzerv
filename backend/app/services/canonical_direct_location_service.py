from __future__ import annotations

import uuid

from sqlalchemy import text


DIRECT_LOCATION_NAME = "Direct"


def ensure_canonical_direct_location(conn, *, household_id: str) -> str:
    normalized_household_id = str(household_id or "").strip()
    if not normalized_household_id:
        raise ValueError("Huishouden ontbreekt")

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS spaces (
            id TEXT PRIMARY KEY,
            naam TEXT NOT NULL,
            household_id TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
    """))

    columns = {str(row[1]) for row in conn.execute(text("PRAGMA table_info(spaces)")).fetchall()}
    if "is_direct" not in columns:
        conn.execute(text("ALTER TABLE spaces ADD COLUMN is_direct INTEGER NOT NULL DEFAULT 0"))

    conn.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_spaces_household_direct
        ON spaces(household_id)
        WHERE is_direct = 1
    """))

    marked = conn.execute(text("""
        SELECT id
        FROM spaces
        WHERE household_id = :household_id
          AND is_direct = 1
        LIMIT 1
    """), {"household_id": normalized_household_id}).mappings().first()

    direct_id = str(marked.get("id") or "").strip() if marked else ""
    if not direct_id:
        legacy = conn.execute(text("""
            SELECT id
            FROM spaces
            WHERE household_id = :household_id
              AND lower(trim(naam)) LIKE 'direct%'
            ORDER BY
              CASE WHEN lower(trim(naam)) = 'direct' THEN 0 ELSE 1 END,
              rowid
            LIMIT 1
        """), {"household_id": normalized_household_id}).mappings().first()
        direct_id = str(legacy.get("id") or "").strip() if legacy else ""

    if not direct_id:
        direct_id = str(uuid.uuid4())
        conn.execute(text("""
            INSERT INTO spaces (id, naam, household_id, active, is_direct)
            VALUES (:id, :naam, :household_id, 1, 1)
        """), {
            "id": direct_id,
            "naam": DIRECT_LOCATION_NAME,
            "household_id": normalized_household_id,
        })
    else:
        conn.execute(text("""
            UPDATE spaces
            SET naam = :naam,
                active = 1,
                is_direct = 1
            WHERE id = :id
              AND household_id = :household_id
        """), {
            "id": direct_id,
            "household_id": normalized_household_id,
            "naam": DIRECT_LOCATION_NAME,
        })

    conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS trg_spaces_direct_immutable_update
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
    conn.execute(text("""
        CREATE TRIGGER IF NOT EXISTS trg_spaces_direct_immutable_delete
        BEFORE DELETE ON spaces
        FOR EACH ROW
        WHEN OLD.is_direct = 1
        BEGIN
            SELECT RAISE(ABORT, 'Direct is een vaste locatie');
        END
    """))

    return direct_id
